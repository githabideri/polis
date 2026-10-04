using System;
using System.Collections.Generic;
using System.Collections;
using System.Globalization;
using System.Linq;
using System.Reflection;
using System.Text;
using System.Text.Json;
using Vintagestory.API.Client;
using Vintagestory.API.Common;
using Vintagestory.API.Common.Entities;
using Vintagestory.API.Config;
using Vintagestory.API.Datastructures;
using Vintagestory.API.MathTools;
using Vintagestory.API.Server;
using Vintagestory.API.Util;
using Vintagestory.GameContent;
using Vintagestory.Essentials;
using Polis.Core;
using Polis.Actions.Navigation;
using Polis.Actions.Blocks;
using Polis.Actions.Harvesting;
using Polis.Actions.Entities;
using Polis.Actions.Workstations;
using Polis.Actions.Inventory;
using Polis.Helpers;
using Polis.Commands;

public partial class PolisSystem : ModSystem
{
    // Constants now in PolisConstants class

    ICoreServerAPI sapi;
    internal IServerNetworkChannel serverChannel;
    internal readonly Dictionary<long, BotState> bots = new Dictionary<long, BotState>();
    internal readonly Dictionary<string, long> selectedByPlayer = new Dictionary<string, long>();
    readonly Dictionary<string, long> highlightClearAtMs = new Dictionary<string, long>();
    readonly Dictionary<string, long> pathHighlightClearAtMs = new Dictionary<string, long>();
    readonly Dictionary<string, long> zoneHighlightClearAtMs = new Dictionary<string, long>();
    readonly Dictionary<string, PreviewState> previewByPlayer = new Dictionary<string, PreviewState>();
    long nextBotHighlightAtMs;
    long tickListenerId;
    bool debugEnabled;
    
    // Persistent bot registry - survives server restarts and chunk unloads
    PolisGlobalData globalData = new PolisGlobalData();

    // Persistent container registry - named references to storage containers
    PolisContainerRegistry containerRegistry = new PolisContainerRegistry();

    // Zone registry - named AABB zones (backed by globalData.Zones)
    PolisZoneRegistry zoneRegistry;
    // Zone tracking state: bot entity id -> set of zone names it was in last tick
    readonly Dictionary<long, HashSet<string>> botZoneState = new Dictionary<long, HashSet<string>>();

    // Active possessions: player UID -> (seat, npc entity id)
    readonly Dictionary<string, PolisPossessableSeat> activePossessions = new Dictionary<string, PolisPossessableSeat>();

    // HTTP test harness for external control
    PolisTestHarness testHarness;

    // Pending screenshot requests: requestId -> callback
    readonly Dictionary<string, Action<PolisScreenshotResponsePacket>> pendingScreenshots = new Dictionary<string, Action<PolisScreenshotResponsePacket>>();

    public override void Start(ICoreAPI api)
    {
        // Opt-in API probe (POLIS_API_PROBE=1): dumps the reflection-based
        // API surface to /tmp/polis-api-probe.txt for work against new
        // game versions. Off by default.
        if (Environment.GetEnvironmentVariable("POLIS_API_PROBE") == "1")
            Polis.PolisApiProbe.DumpTypes();
        api.RegisterEntity("EntityPolisBot", typeof(EntityPolisBot));
        api.RegisterEntityBehaviorClass("polisbotHunger", typeof(EntityBehaviorPolisHunger));
    }

    public override void StartServerSide(ICoreServerAPI api)
    {
        sapi = api;
        if (Environment.GetEnvironmentVariable("POLIS_API_PROBE") == "1")
            Polis.PolisApiProbe.DumpWorld(api);
        PolisHarmony.Apply(api);
        PolisCommandRegistry.RegisterCommands(api, this);
        tickListenerId = api.Event.RegisterGameTickListener(OnTick, 50);
        api.Event.RegisterGameTickListener(OnZoneTrackingTick, 1000);

        // Unattended-pilot fix (part 1 of 2): confirm character selection for
        // each player on join. The survival mod opens the character dialog
        // on join when the player lacks the "createCharacter" moddata, and
        // that dialog pauses the singleplayer server. Our join handler runs
        // after the survival mod's (it registers first), so the flag takes
        // effect from the NEXT join - the first one is made harmless by
        // PolisPauseGameBlockPatch (part 2), which keeps the tick running
        // even while a pause dialog is on screen.
        api.Event.PlayerJoin += OnPlayerJoinConfirmCharSelection;

        // Register the possession mountable so clients can reconstruct the seat
        api.RegisterMountable(PolisPossessableSeat.MountableClassName, PolisPossessableSeat.CreateFromTree);

        serverChannel = api.Network.RegisterChannel("polis")
            .RegisterMessageType<PolisBotListRequestPacket>()
            .RegisterMessageType<PolisBotListResponsePacket>()
            .RegisterMessageType<PolisBotActionPacket>()
            .RegisterMessageType<PolisPanicPacket>()
            .RegisterMessageType<PolisDebugStatePacket>()
            .RegisterMessageType<PolisScreenshotRequestPacket>()
            .RegisterMessageType<PolisScreenshotResponsePacket>()
            .RegisterMessageType<PolisSetViewDirectionPacket>()
            .SetMessageHandler<PolisBotListRequestPacket>(OnBotListRequest)
            .SetMessageHandler<PolisBotActionPacket>(OnBotAction)
            .SetMessageHandler<PolisScreenshotResponsePacket>(OnScreenshotResponse);
        
        // Register persistence events for bot registry
        api.Event.SaveGameLoaded += OnSaveGameLoaded;
        api.Event.GameWorldSave += OnGameWorldSave;
        
        // Register entity lifecycle events
        api.Event.OnEntityLoaded += OnEntityLoaded;
        api.Event.OnEntityDespawn += OnEntityDespawn;

        // Register possession mountable for network deserialization
        api.RegisterMountable(PolisPossessableSeat.MountableClassName, PolisPossessableSeat.CreateFromTree);

        // Start HTTP test harness for external control
        testHarness = new PolisTestHarness(
            sapi,
            GetTestStateResult,
            ExecuteHarnessCommand,
            RequestScreenshotForHarness
        );
        if (testHarness.Start())
        {
            sapi.Logger.Notification($"[polis] Test harness started on port {testHarness.Port}");
        }
    }

    /// <summary>
    /// Creates a BotState with the WebSocket event callback configured.
    /// </summary>
    private BotState CreateBotState(EntityAgent entity)
    {
        var bot = new BotState(entity) { Owner = this };
        bot.OnActionRecorded = (botId, action, ok, msg, ms, actionId) =>
        {
            testHarness?.Broadcaster?.QueueEvent("action_complete", PolisLogLevel.Normal, new
            {
                botId,
                action,
                ok,
                msg,
                ms,
                actionId
            });
        };
        return bot;
    }

    private void OnSaveGameLoaded()
    {
        byte[] data = sapi.WorldManager.SaveGame.GetData("polis-bots");
        globalData = data == null ? new PolisGlobalData()
                    : SerializerUtil.Deserialize<PolisGlobalData>(data);

        if (globalData.Bots == null)
        {
            globalData.Bots = new Dictionary<long, BotRecord>();
        }

        foreach (var record in globalData.Bots.Values)
        {
            if (string.IsNullOrWhiteSpace(record.EntityCode) ||
                record.EntityCode == "survival:playerbot" ||
                record.EntityCode == "game:playerbot" ||
                record.EntityCode == "playerbot")
            {
                record.EntityCode = PolisConstants.DefaultBotCode;
            }
        }

        sapi.Logger.Notification($"[polis] Loaded bot registry: {globalData.Bots.Count} bot(s)");

        // (character-selection confirmation happens on PlayerJoin -
        // OnPlayerJoinConfirmCharSelection - because players don't exist
        // at save-load time yet)

        // Load container registry
        byte[] containerData = sapi.WorldManager.SaveGame.GetData("polis-containers");
        containerRegistry = containerData == null ? new PolisContainerRegistry()
                          : SerializerUtil.Deserialize<PolisContainerRegistry>(containerData);

        if (containerRegistry.Containers == null)
        {
            containerRegistry.Containers = new Dictionary<string, ContainerRecord>();
        }

        sapi.Logger.Notification($"[polis] Loaded container registry: {containerRegistry.Containers.Count} container(s)");

        // Initialize zone registry from globalData
        if (globalData.Zones == null)
        {
            globalData.Zones = new Dictionary<string, ZoneRecord>();
        }
        zoneRegistry = new PolisZoneRegistry(globalData.Zones);
        sapi.Logger.Notification($"[polis] Loaded zone registry: {zoneRegistry.Count} zone(s)");

        // Initialize viewpoints registry
        if (globalData.Viewpoints == null)
        {
            globalData.Viewpoints = new Dictionary<string, ViewpointRecord>();
        }
        sapi.Logger.Notification($"[polis] Loaded viewpoint registry: {globalData.Viewpoints.Count} viewpoint(s)");

        // Sync in-memory bots dict with registry for any already-loaded entities
        foreach (var record in globalData.Bots.Values)
        {
            var entity = sapi.World.GetEntityById(record.EntityId) as EntityAgent;
            if (entity != null && entity.Alive)
            {
                record.IsLoaded = true;
                record.LastKnownPos = entity.ServerPos.XYZ.Clone();
                if (!bots.ContainsKey(record.EntityId))
                {
                    var bot = CreateBotState(entity);
                    bot.Activity.Load(null);
                    bot.Activity.PauseAutoSelection(true);
                    bot.Activity.Debug = debugEnabled;
                    bots[record.EntityId] = bot;
                }
            }
            else
            {
                record.IsLoaded = false;
            }
        }
    }
    
    private void OnGameWorldSave()
    {
        // Update positions before save for all loaded bots
        foreach (var record in globalData.Bots.Values)
        {
            if (bots.TryGetValue(record.EntityId, out var bot) && bot.Entity != null && bot.Entity.Alive)
            {
                record.LastKnownPos = bot.Entity.ServerPos.XYZ.Clone();
                record.IsLoaded = true;
            }
        }

        sapi.WorldManager.SaveGame.StoreData("polis-bots", SerializerUtil.Serialize(globalData));
        sapi.Logger.Notification($"[polis] Saved bot registry: {globalData.Bots.Count} bot(s)");

        // Save container registry
        sapi.WorldManager.SaveGame.StoreData("polis-containers", SerializerUtil.Serialize(containerRegistry));
        sapi.Logger.Notification($"[polis] Saved container registry: {containerRegistry.Containers.Count} container(s)");
    }
    
    // --- daylock (permadey, 2026-09-26) ------------------------------------
    // Keeps the test world's clock in the day window: fast-forwards (100x)
    // until the window is reached, then stops the clock for real by setting
    // GameCalendar.CalendarSpeedMul = 0 (time AND date freeze). Speed
    // modifiers alone can't do it (inherent base 60; negatives clamp to 0),
    // and calling GameCalendar.SetDayTime every tick corrupts the date
    // counter (observed: +years per minute) - never do that.
    // Enable: `daylock on [start end]` (time units 0-10000; default
    // 3333-6667, i.e. ~08:00-16:00). Disable: `daylock off` restores the
    // vanilla 48-min day (mul back to 0.5).
    int daylockWinStart = 3333, daylockWinEnd = 6667;
    bool daylockOn, daylockFrozen;
    const float VanillaCalendarSpeedMul = 0.5f; // vanilla: 48-min day

    void DaylockTick(float dt)
    {
        if (!daylockOn || sapi?.World?.Calendar == null) return;
        var cal = sapi.World.Calendar;
        if (daylockFrozen)
        {
            if (cal is Vintagestory.Common.GameCalendar gcal && gcal.CalendarSpeedMul != 0f)
                gcal.CalendarSpeedMul = 0f; // re-assert (defensive)
            return;
        }
        float h = (float)cal.HourOfDay;
        float ws = daylockWinStart * 24f / 10000f;
        float we = daylockWinEnd * 24f / 10000f;
        if (h >= ws && h < we)
        {
            daylockFrozen = true;
            cal.SetTimeSpeedModifier("polis-harness", 0f); // back to vanilla sum (harmless while stopped)
            if (cal is Vintagestory.Common.GameCalendar gcal)
                gcal.CalendarSpeedMul = 0f; // true freeze: no time, no date advance
            sapi.Logger.Notification($"[polis] daylock: clock stopped at {h:F2}h (window {ws:F1}-{we:F1}h)");
        }
        else if (cal.SpeedOfTime < 100f)
        {
            cal.SetTimeSpeedModifier("polis-harness", 6000f); // ~100x until the window
        }
    }

    private void OnZoneTrackingTick(float dt)
    {
        if (zoneRegistry == null || zoneRegistry.Count == 0) return;

        foreach (var kvp in bots)
        {
            var botId = kvp.Key;
            var bot = kvp.Value;
            if (bot.Entity == null || !bot.Entity.Alive) continue;

            var pos = bot.Entity.ServerPos.AsBlockPos;
            var currentZones = new HashSet<string>(zoneRegistry.GetZonesAt(pos));

            if (!botZoneState.TryGetValue(botId, out var previousZones))
            {
                previousZones = new HashSet<string>();
            }

            // Detect enters
            foreach (var zone in currentZones)
            {
                if (!previousZones.Contains(zone))
                {
                    testHarness?.Broadcaster?.QueueEvent("zone_enter", PolisLogLevel.Info, new { botId, zone });
                }
            }

            // Detect exits
            foreach (var zone in previousZones)
            {
                if (!currentZones.Contains(zone))
                {
                    testHarness?.Broadcaster?.QueueEvent("zone_exit", PolisLogLevel.Info, new { botId, zone });
                }
            }

            botZoneState[botId] = currentZones;
        }
    }

    private void OnEntityLoaded(Entity entity)
    {
        if (entity == null) return;
        
        // Check if this entity is in our registry
        if (globalData.Bots.TryGetValue(entity.EntityId, out var record))
        {
            record.IsLoaded = true;
            record.LastKnownPos = entity.ServerPos.XYZ.Clone();
            
            // Re-add to in-memory tracking if it's an agent
            if (entity is EntityAgent agent && !bots.ContainsKey(entity.EntityId))
            {
                var bot = CreateBotState(agent);
                bot.Activity.Load(null);
                bot.Activity.PauseAutoSelection(true);
                bot.Activity.Debug = debugEnabled;
                bots[entity.EntityId] = bot;

                // Emit bot_spawned event (re-loaded from chunk)
                testHarness?.Broadcaster?.QueueEvent("bot_spawned", PolisLogLevel.Normal, new
                {
                    botId = entity.EntityId,
                    pos = new[] { entity.ServerPos.X, entity.ServerPos.Y, entity.ServerPos.Z },
                    type = entity.Code?.Path ?? "unknown",
                    source = "chunk_reload"
                });

                if (debugEnabled)
                {
                    sapi.Logger.Notification($"[polis] Bot {entity.EntityId} re-loaded from chunk");
                }
            }
        }
        // Also check if entity has ownerUid attribute (recovery from lost registry)
        else if (entity is EntityAgent agent)
        {
            string ownerUid = entity.WatchedAttributes.GetString("polisOwnerUid", null);
            if (!string.IsNullOrEmpty(ownerUid))
            {
                // Recover bot into registry
                var newRecord = new BotRecord
                {
                    EntityId = entity.EntityId,
                    OwnerUid = ownerUid,
                    Name = entity.WatchedAttributes.GetString("polisName", $"Bot {entity.EntityId}"),
                    LastKnownPos = entity.ServerPos.XYZ.Clone(),
                    IsLoaded = true,
                    EntityCode = entity.Code.ToShortString()
                };
                globalData.Bots[entity.EntityId] = newRecord;

                var bot = CreateBotState(agent);
                bot.Activity.Load(null);
                bot.Activity.PauseAutoSelection(true);
                bot.Activity.Debug = debugEnabled;
                bots[entity.EntityId] = bot;

                // Emit bot_spawned event (recovered from attributes)
                testHarness?.Broadcaster?.QueueEvent("bot_spawned", PolisLogLevel.Normal, new
                {
                    botId = entity.EntityId,
                    pos = new[] { entity.ServerPos.X, entity.ServerPos.Y, entity.ServerPos.Z },
                    type = entity.Code?.Path ?? "unknown",
                    source = "attribute_recovery"
                });

                sapi.Logger.Notification($"[polis] Recovered bot {entity.EntityId} from entity attributes");
            }
        }

        // Saturation persistence fix: a bot saved while starving reloads
        // starving (the hunger tree is persisted with the entity) and would
        // otherwise sit at the starvation-damage floor until something fed
        // it. Refuel to 75% of max so a reloaded bot can work — and can eat
        // right away if a job's food-pressure check trips (trigger sits at
        // 25%). Fresh spawns already start at 100% (entity JSON default),
        // so this only fires for actually starved loads.
        if (entity is EntityPolisBot pbot)
        {
            RefuelStarvedBot(pbot);
        }
    }

    /// <summary>
    /// Refuel a bot that reloaded below the forage trigger (25% of max)
    /// up to 75% of max. Writes the synced hunger tree directly (no
    /// ReceiveSaturation: a refuel is not an eating event, it must not
    /// move the nutrition levels or their loss delays).
    /// </summary>
    void RefuelStarvedBot(EntityPolisBot bot)
    {
        var hunger = bot.WatchedAttributes.GetTreeAttribute("hunger");
        if (hunger == null) return;
        float max = hunger.GetFloat("maxsaturation", 0f);
        if (max <= 0f) return;
        float cur = hunger.GetFloat("currentsaturation", 0f);
        if (cur >= 0.25f * max) return;

        hunger.SetFloat("currentsaturation", 0.75f * max);
        bot.WatchedAttributes.MarkPathDirty("hunger");
        sapi.Logger.Notification($"[polis] Bot {bot.EntityId} reloaded starving ({cur:F0}/{max:F0}) — refueled to 75% ({0.75f * max:F0})");
    }
    
    private void OnEntityDespawn(Entity entity, EntityDespawnData data)
    {
        if (entity == null) return;

        if (globalData.Bots.TryGetValue(entity.EntityId, out var record))
        {
            if (data.Reason == EnumDespawnReason.Unload)
            {
                // Chunk unload - keep in registry, mark as unloaded
                record.IsLoaded = false;
                record.LastKnownPos = entity.ServerPos.XYZ.Clone();

                // Emit bot_unloaded event (Info level - less important than death)
                testHarness?.Broadcaster?.QueueEvent("bot_unloaded", PolisLogLevel.Info, new
                {
                    botId = entity.EntityId
                });

                if (debugEnabled)
                {
                    sapi.Logger.Notification($"[polis] Bot {entity.EntityId} unloaded (chunk)");
                }
            }
            else if (data.Reason == EnumDespawnReason.Death ||
                     data.Reason == EnumDespawnReason.Removed ||
                     data.Reason == EnumDespawnReason.Combusted)
            {
                // Permanent removal - remove from registry
                globalData.Bots.Remove(entity.EntityId);

                // Emit bot_died event
                testHarness?.Broadcaster?.QueueEvent("bot_died", PolisLogLevel.Normal, new
                {
                    botId = entity.EntityId,
                    cause = data.Reason.ToString()
                });

                if (debugEnabled)
                {
                    sapi.Logger.Notification($"[polis] Bot {entity.EntityId} removed from registry (reason: {data.Reason})");
                }
            }
        }

        // Always remove from in-memory tracking
        bots.Remove(entity.EntityId);
    }

    private void OnBotListRequest(IServerPlayer fromPlayer, PolisBotListRequestPacket packet)
    {
        var entries = new List<PolisBotEntry>();
        
        // Include ALL bots from registry (both loaded and unloaded)
        foreach (var record in globalData.Bots.Values)
        {
            double x = record.LastKnownPos?.X ?? 0;
            double y = record.LastKnownPos?.Y ?? 0;
            double z = record.LastKnownPos?.Z ?? 0;
            string code = record.EntityCode ?? PolisConstants.DefaultBotCode;
            
            // If loaded, get live position
            if (record.IsLoaded && bots.TryGetValue(record.EntityId, out var bot) && bot.Entity != null)
            {
                x = bot.Entity.ServerPos.X;
                y = bot.Entity.ServerPos.Y;
                z = bot.Entity.ServerPos.Z;
                code = bot.Entity.Code.ToShortString();
            }
            
            entries.Add(new PolisBotEntry
            {
                EntityId = record.EntityId,
                Code = code,
                X = x,
                Y = y,
                Z = z,
                IsSelected = selectedByPlayer.TryGetValue(fromPlayer.PlayerUID, out var selectedId) && selectedId == record.EntityId,
                IsLoaded = record.IsLoaded,
                OwnerUid = record.OwnerUid
            });
        }
        
        var response = new PolisBotListResponsePacket { Bots = entries.ToArray() };
        serverChannel.SendPacket(response, fromPlayer);
    }

    private void OnBotAction(IServerPlayer fromPlayer, PolisBotActionPacket packet)
    {
        // DEADLOCK PREVENTION: Always move network-triggered actions to the main thread highway.
        sapi.Event.EnqueueMainThreadTask(() => {
            if (packet.Action == "spawn")
            {
                CmdSpawn(new TextCommandCallingArgs
                {
                    Caller = new Caller { Player = fromPlayer, Type = EnumCallerType.Player },
                    Parsers = new List<ICommandArgumentParser> { new WordArgParser("entitycode", false) }
                });
                return;
            }

            // Check if bot exists in registry (may be unloaded)
            bool inRegistry = globalData.Bots.ContainsKey(packet.EntityId);
            bool inMemory = bots.TryGetValue(packet.EntityId, out var bot);
            
            if (!inRegistry && !inMemory) return;

            switch (packet.Action)
            {
                case "select":
                    // Only allow selection if bot is loaded
                    if (inMemory && bot.Entity != null && bot.Entity.Alive)
                    {
                        selectedByPlayer[fromPlayer.PlayerUID] = packet.EntityId;
                    }
                    // Mirror the selection update back to the UI
                    OnBotListRequest(fromPlayer, new PolisBotListRequestPacket());
                    break;
                case "delete":
                    // Remove from registry (persistent)
                    globalData.Bots.Remove(packet.EntityId);

                    // If loaded, kill the entity
                    if (inMemory && bot.Entity != null && bot.Entity.Alive)
                    {
                        bot.Entity.Die(EnumDespawnReason.Removed);
                    }

                    // Remove from in-memory tracking
                    bots.Remove(packet.EntityId);

                    // Clear selection if this bot was selected
                    if (selectedByPlayer.TryGetValue(fromPlayer.PlayerUID, out var sid) && sid == packet.EntityId)
                    {
                        selectedByPlayer.Remove(fromPlayer.PlayerUID);
                    }

                    // Refresh list for the player after deletion
                    OnBotListRequest(fromPlayer, new PolisBotListRequestPacket());
                    break;

                case "possession":
                    // Select and possess the bot
                    if (inMemory && bot.Entity != null && bot.Entity.Alive)
                    {
                        selectedByPlayer[fromPlayer.PlayerUID] = packet.EntityId;
                        // Trigger possession via the command handler
                        CmdPossess(new TextCommandCallingArgs
                        {
                            Caller = new Caller { Player = fromPlayer, Type = EnumCallerType.Player }
                        });
                    }
                    break;
            }
        }, "polis-bot-action");
    }

    private void OnScreenshotResponse(IServerPlayer fromPlayer, PolisScreenshotResponsePacket packet)
    {
        if (string.IsNullOrEmpty(packet.RequestId)) return;

        Action<PolisScreenshotResponsePacket> callback;
        lock (pendingScreenshots)
        {
            if (!pendingScreenshots.TryGetValue(packet.RequestId, out callback))
            {
                sapi.Logger.Debug($"[polis] Screenshot response received but no pending request: {packet.RequestId}");
                return;
            }
            pendingScreenshots.Remove(packet.RequestId);
        }

        sapi.Logger.Debug($"[polis] Screenshot response from {fromPlayer.PlayerName}: {packet.Success}, {packet.Width}x{packet.Height}");
        callback?.Invoke(packet);
    }

    /// <summary>
    /// Request a screenshot from a specific player's client.
    /// </summary>
    /// <param name="player">Player to capture from</param>
    /// <param name="saveToFile">Whether client should also save to file</param>
    /// <param name="callback">Callback when capture completes</param>
    /// <returns>Request ID for tracking</returns>
    internal string RequestScreenshot(IServerPlayer player, bool saveToFile, Action<PolisScreenshotResponsePacket> callback)
    {
        var requestId = Guid.NewGuid().ToString("N").Substring(0, 8);

        lock (pendingScreenshots)
        {
            pendingScreenshots[requestId] = callback;
        }

        var request = new PolisScreenshotRequestPacket
        {
            RequestId = requestId,
            SaveToFile = saveToFile
        };

        serverChannel.SendPacket(request, player);
        sapi.Logger.Debug($"[polis] Screenshot request sent to {player.PlayerName}: {requestId}");

        return requestId;
    }

    /// <summary>
    /// Harness-compatible screenshot request function (takes UID instead of player object).
    /// </summary>
    private string RequestScreenshotForHarness(string playerUid, bool saveToFile, Action<PolisScreenshotResponsePacket> callback)
    {
        var player = sapi.World.PlayerByUid(playerUid) as IServerPlayer;
        if (player == null)
        {
            callback?.Invoke(new PolisScreenshotResponsePacket
            {
                Success = false,
                Error = "Player not found"
            });
            return null;
        }

        return RequestScreenshot(player, saveToFile, callback);
    }

    public override void Dispose()
    {
        testHarness?.Dispose();
        if (tickListenerId != 0)
        {
            sapi?.Event.UnregisterGameTickListener(tickListenerId);
        }
        PolisHarmony.Unapply(sapi);
    }

    float hbAccum;
    PathfinderTask pathProbeTask;
    int pathProbeAgeSec;
    bool pathProbeDone;

    void OnTick(float dt)
    {
        DaylockTick(dt);
        hbAccum += dt;
        if (hbAccum >= 10f)
        {
            hbAccum = 0f;
            int nullActs = 0;
            foreach (var b in bots.Values) if (b?.Activity == null) nullActs++;
            sapi?.Logger?.Notification($"[polis] system-tick heartbeat: bots={bots.Count} nullActivity={nullActs}");

            // Pathfinder-thread liveness probe (diagnostic; enable with POLIS_PATH_PROBE=1)
            if (Environment.GetEnvironmentVariable("POLIS_PATH_PROBE") == "1")
            try
            {
                var pfa = sapi?.World?.Api?.ModLoader?.GetModSystem<Vintagestory.Essentials.PathfindingAsync>(true);
                if (pfa != null)
                {
                    string extra = "";
                    if (pathProbeTask != null && !pathProbeDone)
                    {
                        pathProbeAgeSec += 10;
                        extra = " probe[finished=" + pathProbeTask.Finished
                            + " wp=" + (pathProbeTask.waypoints == null ? "null" : pathProbeTask.waypoints.Count.ToString())
                            + " age=" + pathProbeAgeSec + "s]";
                        if (pathProbeTask.Finished) pathProbeDone = true;
                    }
                    else if (pathProbeTask == null)
                    {
                        var pl = sapi?.World?.AllOnlinePlayers?.FirstOrDefault();
                        if (pl?.Entity != null && pl.Entity.Alive)
                        {
                            var sp = pl.Entity.Pos.AsBlockPos;
                            var tp = new BlockPos(sp.X + 3, sp.Y, sp.Z);
                            pathProbeTask = new PathfinderTask(sp, tp, 0f, 12, 0.6f, pl.Entity.CollisionBox, 999);
                            pfa.EnqueuePathfinderTask(pathProbeTask);
                            sapi?.Logger?.Notification($"[polis] pathprobe armed: {sp} -> {tp}");
                        }
                    }
                    sapi?.Logger?.Notification($"[polis] pathfinder: queue={pfa.PathfinderTasks.Count}{extra}");
                }
            }
            catch (System.Exception ex)
            {
                sapi?.Logger?.Notification("[polis] pathprobe error: " + ex.Message);
            }
        }
        if (bots.Count > 0)
        {
            var toRemoveFromMemory = new List<long>();
            foreach (var entry in bots)
            {
                var bot = entry.Value;
                if (bot.Entity == null || !bot.Entity.Alive)
                {
                    // Remove from in-memory dict, but registry handles persistence
                    // The OnEntityDespawn event will update the registry appropriately
                    toRemoveFromMemory.Add(entry.Key);
                    continue;
                }
                bot.Activity?.OnTick(dt);
            }
            ForageOnTick(dt);
            for (int i = 0; i < toRemoveFromMemory.Count; i++)
            {
                bots.Remove(toRemoveFromMemory[i]);
            }
        }

        // Route possession controls from player to NPC
        UpdatePossessions(dt);

        UpdateHighlights();
        UpdatePathHighlights();
        UpdatePreviewPaths();
        UpdateBotHighlights();
        UpdateZoneHighlights();
    }

    /// <summary>
    /// Routes player controls to possessed NPC movement during possession.
    /// This is the heart of the possession system - converting player input
    /// into NPC locomotion.
    /// </summary>
    void UpdatePossessions(float dt)
    {
        if (activePossessions.Count == 0) return;

        var toRemove = new List<string>();

        foreach (var kvp in activePossessions)
        {
            var playerUid = kvp.Key;
            var seat = kvp.Value;

            var npc = seat.Entity as EntityAgent;
            if (npc == null || !npc.Alive)
            {
                toRemove.Add(playerUid);
                continue;
            }

            // Find the player entity
            var player = sapi.World.PlayerByUid(playerUid)?.Entity;
            if (player == null) continue;

            // Update seat position to follow NPC
            seat.UpdateSeatPosition();

            // Lock NPC yaw to possessor's camera yaw FIRST
            // This ensures the WalkVector rotation is based on where the player is looking
            npc.ServerPos.Yaw = player.ServerPos.Yaw;
            npc.ServerPos.HeadYaw = player.ServerPos.HeadYaw;
            npc.ServerPos.HeadPitch = player.ServerPos.HeadPitch;

            // Route controls from seat (which receives player input via mounting system)
            var seatControls = seat.Controls;
            var npcControls = npc.ServerControls;

            // Copy boolean inputs to NPC
            npcControls.Forward = seatControls.Forward;
            npcControls.Backward = seatControls.Backward;
            npcControls.Left = seatControls.Left;
            npcControls.Right = seatControls.Right;
            npcControls.Jump = seatControls.Jump;
            npcControls.Sneak = seatControls.Sneak;
            npcControls.Sprint = seatControls.Sprint;

            // Use the engine's CalcMovementVectors() to compute WalkVector correctly
            // This matches the engine's exact rotation formula: (pi/2 - yaw) not cos(yaw)/sin(yaw)
            // with proper diagonal normalization and input inversion (Forward = -dz, Right = +dx)
            npcControls.CalcMovementVectors(npc.ServerPos, dt);

            // Debug: log movement state
            if (debugEnabled && npcControls.TriesToMove)
            {
                sapi.Logger.Notification($"[polis] Possession: controls=({npcControls.Forward},{npcControls.Left},{npcControls.Right},{npcControls.Backward}) walkVec=({npcControls.WalkVector.X:F3},{npcControls.WalkVector.Y:F3},{npcControls.WalkVector.Z:F3})");
            }
        }

        // Clean up dead possessions
        foreach (var uid in toRemove)
        {
            var player = sapi.World.PlayerByUid(uid);
            if (player?.Entity != null)
            {
                player.Entity.TryUnmount();
            }
            activePossessions.Remove(uid);
        }
    }

    internal TextCommandResult CmdPanic(TextCommandCallingArgs args)
    {
        var player = args.Caller.Player as IServerPlayer;
        if (player != null)
        {
            serverChannel.SendPacket(new PolisPanicPacket(), player);
        }
        return TextCommandResult.Success("Panic signal sent to client.");
    }

    internal TextCommandResult CmdPossess(TextCommandCallingArgs args)
    {
        var player = args.Caller.Player as IServerPlayer;
        sapi.Logger.Notification("[polis] CmdPossess called");

        if (player == null)
        {
            sapi.Logger.Warning("[polis] CmdPossess: No server player");
            return TextCommandResult.Error("Server player required");
        }

        sapi.Logger.Notification($"[polis] CmdPossess: Player {player.PlayerName}");

        if (!TryGetSelectedBot(player, out var bot, out var error))
        {
            sapi.Logger.Warning($"[polis] CmdPossess: No bot selected");
            return error;
        }

        sapi.Logger.Notification($"[polis] CmdPossess: Bot {bot.Entity.EntityId} selected");

        // Check if player is already possessing something
        if (activePossessions.ContainsKey(player.PlayerUID))
        {
            sapi.Logger.Warning("[polis] CmdPossess: Already possessing");
            return TextCommandResult.Error("Already possessing a bot. Use /polis unpossess first.");
        }

        // Check if bot is already possessed
        foreach (var kvp in activePossessions)
        {
            if (kvp.Value.Entity?.EntityId == bot.Entity.EntityId)
            {
                sapi.Logger.Warning("[polis] CmdPossess: Bot already possessed by someone else");
                return TextCommandResult.Error("This bot is already being possessed.");
            }
        }

        // Create the possession seat (pass debug flag for diagnostic logging)
        sapi.Logger.Notification("[polis] CmdPossess: Creating seat");
        var seat = new PolisPossessableSeat(bot.Entity, debugEnabled);
        seat.OnPossessionStart = (passenger) =>
        {
            sapi.Logger.Notification($"[polis] OnPossessionStart: Player {player.PlayerName} -> Bot {bot.Entity.EntityId}");
            // Pause the bot's AI while possessed
            bot.Activity?.CancelAll();
        };
        seat.OnPossessionEnd = (passenger) =>
        {
            sapi.Logger.Notification($"[polis] OnPossessionEnd: Player {player.PlayerName}");
            activePossessions.Remove(player.PlayerUID);
        };

        // Mount the player onto the possession seat
        sapi.Logger.Notification("[polis] CmdPossess: Attempting TryMount");

        if (player.Entity == null)
        {
            sapi.Logger.Error("[polis] CmdPossess: player.Entity is NULL");
            return TextCommandResult.Error("Player entity is null.");
        }

        try
        {
            bool mounted = player.Entity.TryMount(seat);
            if (!mounted)
            {
                sapi.Logger.Error("[polis] CmdPossess: TryMount returned false");
                return TextCommandResult.Error("Failed to mount for possession.");
            }
        }
        catch (Exception ex)
        {
            sapi.Logger.Error($"[polis] CmdPossess: TryMount exception: {ex.Message}");
            sapi.Logger.Error($"[polis] Stack: {ex.StackTrace}");
            return TextCommandResult.Error($"Mount exception: {ex.Message}");
        }

        sapi.Logger.Notification("[polis] CmdPossess: TryMount SUCCESS");
        activePossessions[player.PlayerUID] = seat;
        return TextCommandResult.Success($"Now possessing bot {bot.Entity.EntityId}. Use /polis unpossess or press Alt+Shift+U to exit.");
    }

    internal TextCommandResult CmdUnpossess(TextCommandCallingArgs args)
    {
        var player = args.Caller.Player as IServerPlayer;
        if (player == null) return TextCommandResult.Error("Server player required");

        if (!activePossessions.TryGetValue(player.PlayerUID, out var seat))
        {
            return TextCommandResult.Error("Not currently possessing a bot.");
        }

        // Unmount the player
        if (!player.Entity.TryUnmount())
        {
            return TextCommandResult.Error("Failed to unmount from possession.");
        }

        // Seat's OnPossessionEnd callback will clean up activePossessions
        return TextCommandResult.Success("Exited possession mode.");
    }

    internal TextCommandResult CmdTestState(TextCommandCallingArgs args)
    {
        var player = args.Caller.Player as IServerPlayer;
        if (player == null) return TextCommandResult.Error("Server player required");
        if (!TryGetSelectedBot(player, out var bot, out var error)) return error;

        float radius = !args.Parsers[0].IsMissing ? (float)args.Parsers[0].GetValue() : 10f;
        radius = GameMath.Clamp(radius, 1f, 50f);

        var entity = bot.Entity;
        var pos = entity.ServerPos.XYZ;

        // Build human-readable output
        var sb = new StringBuilder();
        sb.AppendLine("=== POLIS TESTSTATE ===");
        sb.AppendLine($"Bot #{entity.EntityId} @ ({pos.X:0.0}, {pos.Y:0.0}, {pos.Z:0.0})");

        // Hand slots
        var rightStack = entity.RightHandItemSlot?.Itemstack;
        var leftStack = entity.LeftHandItemSlot?.Itemstack;
        sb.AppendLine($"  RightHand: {FormatStack(rightStack)}");
        sb.AppendLine($"  LeftHand: {FormatStack(leftStack)}");

        // Nearby EntityItem entities
        var nearbyItems = sapi.World.GetEntitiesAround(pos, radius, radius / 2f, e => e is EntityItem && e.Alive);
        sb.AppendLine($"Items (r={radius:0}): {nearbyItems.Length} found");

        // Sort by distance
        var itemList = nearbyItems
            .Cast<EntityItem>()
            .Select(item => new {
                Entity = item,
                Dist = item.ServerPos.XYZ.DistanceTo(pos)
            })
            .OrderBy(x => x.Dist)
            .Take(10) // Limit output
            .ToList();

        foreach (var item in itemList)
        {
            var stack = item.Entity.Itemstack;
            var code = stack?.Collectible?.Code?.ToString() ?? "unknown";
            var qty = stack?.StackSize ?? 0;
            sb.AppendLine($"  #{item.Entity.EntityId} {code} x{qty} @ {item.Dist:0.0}m");
        }

        // Last action result
        if (!string.IsNullOrEmpty(bot.LastActionName))
        {
            var okStr = bot.LastActionOk ? "ok=true" : "ok=false";
            sb.AppendLine($"LastAction: {bot.LastActionName} {okStr} \"{bot.LastActionMsg}\"");
        }
        else
        {
            sb.AppendLine("LastAction: (none)");
        }

        // Output to chat
        player.SendMessage(GlobalConstants.GeneralChatGroup, sb.ToString(), EnumChatType.Notification);

        // Also output JSON to log for machine parsing
        var jsonObj = new {
            bot = new {
                id = entity.EntityId,
                pos = new[] { pos.X, pos.Y, pos.Z },
                rightHand = rightStack != null ? new { code = rightStack.Collectible?.Code?.ToString(), qty = rightStack.StackSize } : null,
                leftHand = leftStack != null ? new { code = leftStack.Collectible?.Code?.ToString(), qty = leftStack.StackSize } : null
            },
            items = itemList.Select(i => new {
                id = i.Entity.EntityId,
                code = i.Entity.Itemstack?.Collectible?.Code?.ToString(),
                qty = i.Entity.Itemstack?.StackSize ?? 0,
                dist = Math.Round(i.Dist, 2)
            }),
            lastAction = !string.IsNullOrEmpty(bot.LastActionName) ? new {
                name = bot.LastActionName,
                ok = bot.LastActionOk,
                msg = bot.LastActionMsg
            } : null
        };

        // Use simple JSON serialization (System.Text.Json or manual)
        var json = SerializeTestStateJson(jsonObj);
        sapi.Logger.Notification($"[polis] TESTSTATE {json}");

        return TextCommandResult.Success();
    }

    static string FormatStack(ItemStack stack)
    {
        if (stack == null || stack.StackSize <= 0) return "(empty)";
        var code = stack.Collectible?.Code?.ToString() ?? "unknown";
        return $"{code} x{stack.StackSize}";
    }

    static string SerializeTestStateJson(object obj)
    {
        // Simple manual JSON serialization to avoid dependency issues
        // For a proper implementation, use System.Text.Json or Newtonsoft
        try
        {
            return System.Text.Json.JsonSerializer.Serialize(obj);
        }
        catch
        {
            return "{}";
        }
    }

    internal TextCommandResult CmdZoneDefine(TextCommandCallingArgs args)
    {
        var player = args.Caller.Player as IServerPlayer;
        string name = (string)args[0];
        int x1 = (int)args[1], y1 = (int)args[2], z1 = (int)args[3];
        int x2 = (int)args[4], y2 = (int)args[5], z2 = (int)args[6];

        var bounds = new Cuboidi(
            Math.Min(x1, x2), Math.Min(y1, y2), Math.Min(z1, z2),
            Math.Max(x1, x2), Math.Max(y1, y2), Math.Max(z1, z2)
        );
        zoneRegistry.RegisterZone(name, bounds);

        if (player != null)
        {
            HighlightZone(player, bounds);
        }

        return TextCommandResult.Success($"Zone '{name}' defined: ({bounds.X1},{bounds.Y1},{bounds.Z1}) to ({bounds.X2},{bounds.Y2},{bounds.Z2})");
    }

    internal TextCommandResult CmdZoneRemove(TextCommandCallingArgs args)
    {
        string name = (string)args[0];
        if (!zoneRegistry.RemoveZone(name))
            return TextCommandResult.Error($"Zone '{name}' not found");
        return TextCommandResult.Success($"Zone '{name}' removed");
    }

    internal TextCommandResult CmdZoneList(TextCommandCallingArgs args)
    {
        var zones = zoneRegistry.GetAllZones();
        if (zones.Count == 0) return TextCommandResult.Success("No zones defined.");

        var lines = new List<string>();
        foreach (var kvp in zones)
        {
            var b = kvp.Value.Bounds;
            lines.Add($"  {kvp.Key}: ({b.X1},{b.Y1},{b.Z1}) to ({b.X2},{b.Y2},{b.Z2})");
        }
        return TextCommandResult.Success($"{zones.Count} zone(s):\n" + string.Join("\n", lines));
    }

    internal TextCommandResult CmdZoneCheck(TextCommandCallingArgs args)
    {
        var player = args.Caller.Player as IServerPlayer;
        if (player == null) return TextCommandResult.Error("Server player required");
        if (!TryGetSelectedBot(player, out var bot, out var error)) return error;

        var pos = bot.Entity.ServerPos.AsBlockPos;
        var zones = zoneRegistry.GetZonesAt(pos);
        if (zones.Count == 0) return TextCommandResult.Success("Bot is not in any zone.");
        return TextCommandResult.Success($"Bot is in: {string.Join(", ", zones)}");
    }

    internal TextCommandResult CmdZoneShow(TextCommandCallingArgs args)
    {
        var player = args.Caller.Player as IServerPlayer;
        if (player == null) return TextCommandResult.Error("Server player required");

        string name = (string)args[0];
        var zone = zoneRegistry.GetZone(name);
        if (zone == null) return TextCommandResult.Error($"Zone '{name}' not found");

        HighlightZone(player, zone.Bounds);
        return TextCommandResult.Success($"Highlighting zone '{name}'");
    }

    internal TextCommandResult CmdAnimate(TextCommandCallingArgs args)
    {
        var player = args.Caller.Player as IServerPlayer;
        if (player == null) return TextCommandResult.Error("Server player required");
        if (!TryGetSelectedBot(player, out var bot, out var error)) return error;

        // Build args array from parsed values
        var cmdArgs = new List<string>();
        for (int i = 0; i < 3; i++)
        {
            if (!args.Parsers[i].IsMissing)
            {
                var val = args.Parsers[i].GetValue() as string;
                if (!string.IsNullOrEmpty(val))
                    cmdArgs.Add(val);
            }
        }

        var result = ExecuteAnimateCommand(
            cmdArgs.ToArray(),
            new PolisTestHarness.CommandContext { PlayerUid = player.PlayerUID }
        );

        return result.Ok
            ? TextCommandResult.Success(result.Message)
            : TextCommandResult.Error(result.Message);
    }

    // --- HTTP Test Harness Callbacks ---

    /// <summary>
    /// Generate test state result for HTTP API.
    /// </summary>
    /// <param name="unused">Unused parameter (for interface compatibility)</param>
    /// <param name="botId">Bot ID to query, or null for first available bot</param>
    PolisTestHarness.TestStateResult GetTestStateResult(string unused, long? botId)
    {
        var result = new PolisTestHarness.TestStateResult();
        result.Items = new List<PolisTestHarness.TestStateResult.ItemInfo>();

        // Find the bot
        BotState bot = null;
        if (botId.HasValue)
        {
            bots.TryGetValue(botId.Value, out bot);
        }
        else if (bots.Count > 0)
        {
            bot = bots.Values.First();
        }

        if (bot == null || bot.Entity == null)
        {
            result.Error = botId.HasValue
                ? $"Bot {botId.Value} not found or not loaded"
                : "No bots available";
            return result;
        }

        var entity = bot.Entity;
        var pos = entity.ServerPos.XYZ;
        var healthTree = entity.WatchedAttributes?.GetTreeAttribute("health");
        float? currentHealth = null;
        float? maxHealth = null;
        if (healthTree != null)
        {
            var max = healthTree.GetFloat("maxhealth", 0f);
            if (max > 0f)
            {
                maxHealth = max;
                currentHealth = healthTree.GetFloat("currenthealth", max);
            }
        }

        // Bot info
        var rightStack = entity.RightHandItemSlot?.Itemstack;
        var leftStack = entity.LeftHandItemSlot?.Itemstack;

        // Query all non-empty cargo grid slots (2..15)
        PolisTestHarness.TestStateResult.SlotInfo[] backpackInfo = null;
        var invbh = PolisInventoryHelpers.BotCargo(entity);
        if (invbh != null && invbh.Count > PolisConstants.CargoBackpackSlot1)
        {
            var slots = new List<PolisTestHarness.TestStateResult.SlotInfo>();
            for (int i = PolisConstants.CargoBackpackSlot0; i < invbh.Count; i++)
            {
                var gslot = invbh[i];
                if (gslot?.Itemstack?.StackSize > 0)
                {
                    slots.Add(new PolisTestHarness.TestStateResult.SlotInfo
                    {
                        Code = gslot.Itemstack.Collectible?.Code?.ToString(),
                        Qty = gslot.Itemstack.StackSize
                    });
                }
            }
            if (slots.Count > 0) backpackInfo = slots.ToArray();
        }

        // Query backpack contents (items inside equipped backpacks)
        PolisTestHarness.TestStateResult.SlotInfo[][] backpackContentsInfo = null;
        if (invbh != null && invbh.Count > PolisConstants.CargoBackpackSlot1)
        {
            var contentsList = new List<PolisTestHarness.TestStateResult.SlotInfo[]>();
            ItemSlot[] bagSlots = { invbh[PolisConstants.CargoBackpackSlot0], invbh[PolisConstants.CargoBackpackSlot1] };

            for (int bagIndex = 0; bagIndex < bagSlots.Length; bagIndex++)
            {
                var bagSlot = bagSlots[bagIndex];
                if (bagSlot?.Itemstack == null) continue;

                var bag = bagSlot.Itemstack.Collectible?.GetCollectibleInterface<IHeldBag>();
                if (bag == null) continue;

                var contents = bag.GetOrCreateSlots(bagSlot.Itemstack, invbh, bagIndex, entity.World);
                if (contents == null) continue;

                var slotInfos = contents
                    .Where(s => s?.Itemstack?.StackSize > 0)
                    .Select(s => new PolisTestHarness.TestStateResult.SlotInfo
                    {
                        Code = s.Itemstack.Collectible?.Code?.ToString(),
                        Qty = s.Itemstack.StackSize
                    })
                    .ToArray();

                if (slotInfos.Length > 0) contentsList.Add(slotInfos);
            }
            if (contentsList.Count > 0) backpackContentsInfo = contentsList.ToArray();
        }

        result.Bot = new PolisTestHarness.TestStateResult.BotInfo
        {
            Id = entity.EntityId,
            Pos = new[] { pos.X, pos.Y, pos.Z },
            CurrentHealth = currentHealth,
            MaxHealth = maxHealth,
            Foraging = IsForaging(entity.EntityId),
            Saturation = PolisEatService.SaturationOf(entity) is float satv && satv > 0f ? (float)Math.Round(satv, 1) : null,
            MaxSaturation = PolisEatService.MaxSaturationOf(entity) is float maxsv && maxsv > 0f ? (float)Math.Round(maxsv, 1) : null,
            RightHand = rightStack != null && rightStack.StackSize > 0
                ? new PolisTestHarness.TestStateResult.SlotInfo
                {
                    Code = rightStack.Collectible?.Code?.ToString(),
                    Qty = rightStack.StackSize
                }
                : null,
            LeftHand = leftStack != null && leftStack.StackSize > 0
                ? new PolisTestHarness.TestStateResult.SlotInfo
                {
                    Code = leftStack.Collectible?.Code?.ToString(),
                    Qty = leftStack.StackSize
                }
                : null,
            Backpack = backpackInfo,
            BackpackContents = backpackContentsInfo
        };

        // Nearby items
        float radius = 10f;
        var nearbyItems = sapi.World.GetEntitiesAround(pos, radius, radius / 2f, e => e is EntityItem && e.Alive);

        foreach (var item in nearbyItems.Cast<EntityItem>().OrderBy(i => i.ServerPos.XYZ.DistanceTo(pos)).Take(20))
        {
            var stack = item.Itemstack;
            result.Items.Add(new PolisTestHarness.TestStateResult.ItemInfo
            {
                Id = item.EntityId,
                Code = stack?.Collectible?.Code?.ToString(),
                Qty = stack?.StackSize ?? 0,
                Dist = Math.Round(item.ServerPos.XYZ.DistanceTo(pos), 2)
            });
        }

        // Last action
        if (!string.IsNullOrEmpty(bot.LastActionName))
        {
            result.LastAction = new PolisTestHarness.TestStateResult.ActionInfo
            {
                Name = bot.LastActionName,
                Ok = bot.LastActionOk,
                Msg = bot.LastActionMsg
            };
            result.LastActionMs = bot.LastActionMs;
            result.LastActionId = bot.LastActionId;
        }

        return result;
    }


    internal TextCommandResult CmdManage(TextCommandCallingArgs args)
    {
        var player = args.Caller.Player as IServerPlayer;
        if (player == null) return TextCommandResult.Error("Server player required");

        // We can't open a UI directly from the server handler for the player.
        // We need to send a packet to trigger it, or just use a client-side command.
        // Actually, many mods register the command on both sides.
        // Let's just send a packet to the client to open the UI.
        // But better: define the command on both sides.
        
        // For now, let's just trigger it via packet.
        serverChannel.SendPacket(new PolisBotListResponsePacket { Bots = null }, player); // Bots=null as a signal to open UI
        return TextCommandResult.Success();
    }

    ICoreClientAPI capi;
    IClientNetworkChannel clientChannel;
    GuiDialogBotManager botManagerDialog;
    bool clientDebugEnabled;
    PolisScreenCaptureRenderer screenshotRenderer;

    public override void StartClientSide(ICoreClientAPI api)
    {
        capi = api;
        clientChannel = api.Network.RegisterChannel("polis")
            .RegisterMessageType<PolisBotListRequestPacket>()
            .RegisterMessageType<PolisBotListResponsePacket>()
            .RegisterMessageType<PolisBotActionPacket>()
            .RegisterMessageType<PolisPanicPacket>()
            .RegisterMessageType<PolisDebugStatePacket>()
            .RegisterMessageType<PolisScreenshotRequestPacket>()
            .RegisterMessageType<PolisScreenshotResponsePacket>()
            .RegisterMessageType<PolisSetViewDirectionPacket>()
            .SetMessageHandler<PolisBotListResponsePacket>(OnBotListResponse)
            .SetMessageHandler<PolisPanicPacket>(OnPanicPacket)
            .SetMessageHandler<PolisDebugStatePacket>(OnDebugStatePacket)
            .SetMessageHandler<PolisScreenshotRequestPacket>(OnScreenshotRequest)
            .SetMessageHandler<PolisSetViewDirectionPacket>(OnSetViewDirection);

        // Register the possession mountable so clients can reconstruct the seat
        api.RegisterMountable(PolisPossessableSeat.MountableClassName, PolisPossessableSeat.CreateFromTree);

        // Register screenshot capture renderer
        screenshotRenderer = new PolisScreenCaptureRenderer();
        screenshotRenderer.Register(api);

        // Bounded watcher that closes the survival mod's
        // character-selection dialog if it opened at join (see
        // OnPlayerJoinConfirmCharSelection + PolisPauseGameBlockPatch for
        // the full "startup wedge" story).
        StartClientSide_CharSelectWatcher(api);
        api.Event.LevelFinalize += () => charSelectWatcher?.Arm();

        // Client-side Harmony: block ClientMain.PauseGame(true) so no
        // pause dialog can ever suspend the singleplayer server tick.
        PolisHarmony.ApplyClient(api);
    }

    // --- Character-selection confirmation (prevents the join-time pause) ---

    /// <summary>
    /// Sets the survival mod's "createCharacter" moddata for a player on
    /// join, so the character dialog (which pauses the singleplayer game -
    /// PauseGame(true) in its OnGuiOpened, and ClientProgram suspends the
    /// server tick while IsGamePaused) does not open on the player's NEXT
    /// join. Runs after CharacterSystem's own PlayerJoin handler (which
    /// registered first), so this join already got DidSelect=false - that
    /// one is covered by the client-side PauseGame block + the dialog
    /// watcher. Idempotent.
    /// </summary>
    void OnPlayerJoinConfirmCharSelection(IServerPlayer p)
    {
        try
        {
            if (p.GetModData<bool>("createCharacter", false))
                return;
            p.SetModData("createCharacter", true);
            sapi.Logger.Notification($"[polis] confirmed character selection for {p.Name} (dialog won't open on the next join)");
        }
        catch (Exception ex)
        {
            sapi.Logger.Debug($"[polis] character-selection confirm failed: {ex.Message}");
        }
    }

    // Client-side safety net (see PolisCharSelectWatchRenderer): if the
    // character-selection dialog is open in the first moments after level
    // finalize (flag race, or a world where the moddata was not yet
    // written), the renderer closes it frame-by-frame - it works even
    // while the game is suspended, because render frames keep running
    // (the pause menu renders), whereas game-tick listeners do not.
    // Armed on LevelFinalize for ~15s wall-clock, so a dialog a human
    // opens later (F10//charsel) is never touched.
    PolisCharSelectWatchRenderer charSelectWatcher;

    void StartClientSide_CharSelectWatcher(ICoreClientAPI api)
    {
        charSelectWatcher = new PolisCharSelectWatchRenderer(api);
        charSelectWatcher.Register();
    }

    private void OnPanicPacket(PolisPanicPacket packet)
    {
        botManagerDialog?.TryClose();
        capi.ShowChatMessage("Polis Emergency Reset Executed.");
    }

    private void OnDebugStatePacket(PolisDebugStatePacket packet)
    {
        clientDebugEnabled = packet.DebugEnabled;
    }

    private void OnScreenshotRequest(PolisScreenshotRequestPacket packet)
    {
        if (screenshotRenderer == null)
        {
            capi.Logger.Warning("[polis] Screenshot requested but renderer not initialized");
            return;
        }

        capi.Logger.Debug($"[polis] Screenshot request received: {packet.RequestId}");

        // Request capture - callback will send response back to server
        screenshotRenderer.RequestCapture(packet.SaveToFile, null, result =>
        {
            var response = new PolisScreenshotResponsePacket
            {
                RequestId = packet.RequestId,
                Success = result.Success,
                Width = result.Width,
                Height = result.Height,
                Base64Png = result.Base64,
                FilePath = result.FilePath,
                Error = result.Error,
                CaptureTimeMs = result.CaptureTimeMs
            };

            clientChannel.SendPacket(response);
            capi.Logger.Debug($"[polis] Screenshot response sent: {result.Success}, {result.Width}x{result.Height}");
        });
    }

    private void OnSetViewDirection(PolisSetViewDirectionPacket packet)
    {
        // Set the client camera direction
        var player = capi.World.Player;
        if (player != null)
        {
            player.CameraYaw = packet.Yaw;
            player.CameraPitch = packet.Pitch;

            // Also update entity Pos to sync HUD/minimap display
            // The HUD reads from entity.Pos.Yaw, not player.CameraYaw
            if (player.Entity != null)
            {
                player.Entity.Pos.Yaw = packet.Yaw;
                player.Entity.Pos.Pitch = packet.Pitch;
                player.Entity.Pos.HeadYaw = packet.Yaw;
                player.Entity.Pos.HeadPitch = packet.Pitch;
            }

            capi.Logger.Debug($"[polis] Set view direction: yaw={packet.Yaw:F2}, pitch={packet.Pitch:F2}");
        }
    }

    private void OnBotListResponse(PolisBotListResponsePacket packet)
    {
        if (botManagerDialog == null)
        {
            botManagerDialog = new GuiDialogBotManager(capi, clientChannel);
        }

        if (!botManagerDialog.IsOpened())
        {
            botManagerDialog.TryOpen();
            if (clientDebugEnabled) capi.ShowChatMessage("[polis] Bot Manager opened");
        }

        if (packet.Bots != null)
        {
            botManagerDialog.UpdateBots(packet.Bots);
        }
    }

    internal TextCommandResult CmdSpawn(TextCommandCallingArgs args)
    {
        var player = args.Caller.Player as IServerPlayer;
        if (player == null) return TextCommandResult.Error("Server player required");

        string arg = args.Parsers[0].IsMissing ? null : (string)args.Parsers[0].GetValue();

        // Check if the arg is a profession name; otherwise treat as entity code
        string professionName = null;
        string requestedCode = null;
        if (arg != null && PolisProfessions.All.ContainsKey(arg))
        {
            professionName = arg;
        }
        else if (arg == null)
        {
            professionName = PolisProfessions.DefaultProfession;
        }
        else
        {
            requestedCode = arg;
        }

        if (!TryResolveEntityType(requestedCode, out var type, out var resolvedCode, out var errorText))
        {
            return TextCommandResult.Error(errorText);
        }

        var entity = sapi.World.ClassRegistry.CreateEntity(type) as EntityAgent;
        if (entity == null) return TextCommandResult.Error("Failed to create entity: " + resolvedCode);

        var yaw = player.Entity.ServerPos.Yaw;
        var spawnPos = player.Entity.ServerPos.XYZ.AddCopy(Math.Sin(yaw), 0, Math.Cos(yaw));
        entity.ServerPos.SetPos(spawnPos);
        entity.ServerPos.Dimension = player.Entity.ServerPos.Dimension;
        entity.ServerPos.Yaw = yaw;
        entity.Pos.SetFrom(entity.ServerPos);
        entity.PositionBeforeFalling.Set(entity.ServerPos.X, entity.ServerPos.Y, entity.ServerPos.Z);
        entity.AllowDespawn = false;

        sapi.World.SpawnEntity(entity);

        // Set ownership attributes on entity (backup for registry recovery)
        entity.WatchedAttributes.SetString("polisOwnerUid", player.PlayerUID);
        entity.WatchedAttributes.SetString("polisName", $"Bot {entity.EntityId}");
        entity.WatchedAttributes.MarkPathDirty("polisOwnerUid");

        // Apply profession loadout
        if (professionName != null && PolisProfessions.All.TryGetValue(professionName, out var loadout))
        {
            PolisProfessionHelper.ApplyLoadout(
                entity, loadout,
                (code, qty) => TryResolveStack(code, qty, out var s, out var e) ? (s, null) : (null, e),
                msg => { if (debugEnabled) sapi.Logger.Debug(msg); },
                out _);
            entity.WatchedAttributes.SetString("polisProfession", professionName);
        }

        var bot = CreateBotState(entity);
        bot.Activity.Load(null);
        bot.Activity.PauseAutoSelection(true);
        bot.Activity.Debug = debugEnabled;
        bots[entity.EntityId] = bot;
        selectedByPlayer[player.PlayerUID] = entity.EntityId;

        // Add to persistent registry
        globalData.Bots[entity.EntityId] = new BotRecord
        {
            EntityId = entity.EntityId,
            OwnerUid = player.PlayerUID,
            Name = $"Bot {entity.EntityId}",
            LastKnownPos = entity.ServerPos.XYZ.Clone(),
            IsLoaded = true,
            EntityCode = resolvedCode,
            Profession = professionName
        };

        // Emit bot_spawned event
        testHarness?.Broadcaster?.QueueEvent("bot_spawned", PolisLogLevel.Normal, new
        {
            botId = entity.EntityId,
            pos = new[] { spawnPos.X, spawnPos.Y, spawnPos.Z },
            type = resolvedCode,
            profession = professionName,
            source = "player_command"
        });

        var profLabel = professionName != null ? $", profession={professionName}" : "";
        LogDebug(player, $"Spawned bot {entity.EntityId} at {FormatPos(spawnPos)} ({resolvedCode}{profLabel})");

        // Refresh list for the player after spawn
        OnBotListRequest(player, new PolisBotListRequestPacket());

        return TextCommandResult.Success($"Spawned bot {entity.EntityId}{profLabel} (selected)");
    }

    internal TextCommandResult CmdList(TextCommandCallingArgs args)
    {
        if (bots.Count == 0) return TextCommandResult.Success("No bots tracked.");

        var lines = new List<string>();
        foreach (var entry in bots)
        {
            var entity = entry.Value.Entity;
            var pos = entity?.ServerPos?.XYZ;
            lines.Add($"{entry.Key}: {FormatPos(pos)}");
        }
        return TextCommandResult.Success(string.Join("\n", lines));
    }

    internal TextCommandResult CmdSelect(TextCommandCallingArgs args)
    {
        var player = args.Caller.Player as IServerPlayer;
        if (player == null) return TextCommandResult.Error("Server player required");

        long id = (long)args.Parsers[0].GetValue();
        if (!bots.ContainsKey(id)) return TextCommandResult.Error("Bot not found: " + id);

        selectedByPlayer[player.PlayerUID] = id;
        return TextCommandResult.Success("Selected bot " + id);
    }

    internal TextCommandResult CmdSelectLook(TextCommandCallingArgs args)
    {
        var player = args.Caller.Player as IServerPlayer;
        if (player == null) return TextCommandResult.Error("Server player required");

        var selection = player.CurrentEntitySelection;
        if (selection?.Entity == null) return TextCommandResult.Error("No entity selected.");

        long id = selection.Entity.EntityId;
        if (!bots.ContainsKey(id)) return TextCommandResult.Error("Selected entity is not a tracked bot.");

        selectedByPlayer[player.PlayerUID] = id;
        return TextCommandResult.Success("Selected bot " + id);
    }

    internal TextCommandResult CmdDespawn(TextCommandCallingArgs args)
    {
        var player = args.Caller.Player as IServerPlayer;
        if (player == null) return TextCommandResult.Error("Server player required");

        if (!TryGetSelectedBot(player, out var bot, out var error)) return error;

        bot.Entity.Die(EnumDespawnReason.Removed);
        bots.Remove(bot.Entity.EntityId);
        return TextCommandResult.Success("Despawned bot " + bot.Entity.EntityId);
    }

    internal TextCommandResult CmdGoto(TextCommandCallingArgs args)
    {
        var player = args.Caller.Player as IServerPlayer;
        if (player == null) return TextCommandResult.Error("Server player required");
        if (!TryGetSelectedBot(player, out var bot, out var error)) return error;
        ClearLockedPreview(player);
        ClearEnginePathDebugHighlight();

        var pos = (Vec3d)args.Parsers[0].GetValue();
        bool astar = args.Parsers[1].IsMissing ? true : (bool)args.Parsers[1].GetValue();
        float speed = !args.Parsers[2].IsMissing ? (float)args.Parsers[2].GetValue() : 0.02f;
        bool fallback = !args.Parsers[3].IsMissing && (bool)args.Parsers[3].GetValue();

        var movePos = GetApproachPosition(player, pos);
        var action = new PolisGotoAction(
            bot.Activity,
            movePos,
            astar,
            "walk",
            speed,
            1f,
            debugEnabled ? msg => LogDebug(player, msg) : null,
            debugEnabled ? path => HighlightPath(player, path) : null,
            debugEnabled,
            fallback
        );
        StartSingleAction(bot, "goto", action);

        LogDebug(player, $"Bot {bot.Entity.EntityId} goto {FormatPos(movePos)} astar={astar} speed={speed.ToString(CultureInfo.InvariantCulture)} fallback={fallback}");
        return TextCommandResult.Success("Goto started");
    }

    internal TextCommandResult CmdStop(TextCommandCallingArgs args)
    {
        var player = args.Caller.Player as IServerPlayer;
        if (player == null) return TextCommandResult.Error("Server player required");
        if (!TryGetSelectedBot(player, out var bot, out var error)) return error;

        bot.Activity.CancelAll();
        bot.Entity.Controls.StopAllMovement();
        ClearLockedPreview(player);
        return TextCommandResult.Success("Stopped bot actions");
    }

    internal TextCommandResult CmdGotoLook(TextCommandCallingArgs args)
    {
        var player = args.Caller.Player as IServerPlayer;
        if (player == null) return TextCommandResult.Error("Server player required");
        if (!TryGetSelectedBot(player, out var bot, out var error)) return error;
        ClearLockedPreview(player);

        float range = !args.Parsers[0].IsMissing ? (float)args.Parsers[0].GetValue() : 48f;
        bool astar = args.Parsers[1].IsMissing ? true : (bool)args.Parsers[1].GetValue();
        float speed = !args.Parsers[2].IsMissing ? (float)args.Parsers[2].GetValue() : 0.02f;
        bool fallback = !args.Parsers[3].IsMissing && (bool)args.Parsers[3].GetValue();
        return StartGotoLookAction(player, bot, range, astar, speed, fallback, "Goto look started", out _);
    }

    internal TextCommandResult CmdPreview(TextCommandCallingArgs args)
    {
        var player = args.Caller.Player as IServerPlayer;
        if (player == null) return TextCommandResult.Error("Server player required");

        string mode = args.Parsers[0].IsMissing ? "toggle" : ((string)args.Parsers[0].GetValue() ?? "toggle");
        mode = mode.ToLowerInvariant();
        float? range = args.Parsers[1].IsMissing ? null : (float?)args.Parsers[1].GetValue();

        if (!previewByPlayer.TryGetValue(player.PlayerUID, out var state))
        {
            state = new PreviewState { Range = PolisConstants.PreviewDefaultRange };
            previewByPlayer[player.PlayerUID] = state;
        }

        if (range.HasValue)
        {
            state.Range = GameMath.Clamp(range.Value, 2f, PolisConstants.MaxGotoLookRange);
        }

        if (mode == "commit")
        {
            if (!TryGetSelectedBot(player, out var bot, out var error)) return error;

            var result = StartGotoLookAction(player, bot, state.Range, true, 0.02f, false, "Preview committed", out var movePos);
            if (result.Status == EnumCommandStatus.Success)
            {
                state.Enabled = false;
                state.Locked = true;
                state.LockedTarget = movePos?.Clone();
                state.NextUpdateAtMs = 0;
                ClearPreviewHighlight(player);
            }

            return result;
        }

        bool enable;
        switch (mode)
        {
            case "on":
                enable = true;
                break;
            case "off":
                enable = false;
                break;
            case "toggle":
                enable = state.Enabled || state.Locked ? false : true;
                break;
            default:
                return TextCommandResult.Error("Usage: /polis preview [on|off|toggle|commit] [range]");
        }

        state.Enabled = enable;
        state.Locked = false;
        state.LockedTarget = null;
        state.NextUpdateAtMs = 0;

        if (!enable)
        {
            ClearPreviewHighlight(player);
        }

        return TextCommandResult.Success(enable
            ? $"Preview on (range={state.Range.ToString(CultureInfo.InvariantCulture)})"
            : "Preview off");
    }

    void ClearLockedPreview(IServerPlayer player)
    {
        if (player == null) return;
        if (!previewByPlayer.TryGetValue(player.PlayerUID, out var state)) return;
        if (!state.Locked) return;

        state.Locked = false;
        state.LockedTarget = null;
        if (!state.Enabled)
        {
            ClearPreviewHighlight(player);
        }
    }

    TextCommandResult StartGotoLookAction(
        IServerPlayer player,
        BotState bot,
        float range,
        bool astar,
        float speed,
        bool fallback,
        string successMessage,
        out Vec3d resolvedMovePos
    )
    {
        return StartGotoLookActionWithOffset(
            player,
            bot,
            range,
            astar,
            speed,
            fallback,
            successMessage,
            out resolvedMovePos,
            null,
            null
        );
    }

    TextCommandResult StartGotoLookActionWithOffset(
        IServerPlayer player,
        BotState bot,
        float range,
        bool astar,
        float speed,
        bool fallback,
        string successMessage,
        out Vec3d resolvedMovePos,
        Vec3d moveOffset,
        Action<bool, string> onResult
    )
    {
        resolvedMovePos = null;
        range = GameMath.Clamp(range, 2f, PolisConstants.MaxGotoLookRange);

        if (!ResolveGotoLookTarget(player, range, out var blockSel, out var targetPos, out var movePos, out var usedTallGrassFallback, out var snappedToGround))
        {
            return TextCommandResult.Error("No look target found");
        }

        ClearEnginePathDebugHighlight();

        if (snappedToGround)
        {
            if (usedTallGrassFallback)
            {
                LogDebug(player, $"[goto] tall grass hit, snapped to ground {FormatPos(targetPos)}");
            }
            else
            {
                LogDebug(player, $"[goto] snapped target to ground {FormatPos(targetPos)}");
            }
        }
        else if (usedTallGrassFallback && debugEnabled)
        {
            LogDebug(player, $"[goto] tall grass hit, using {FormatPos(targetPos)}");
        }

        if (moveOffset != null)
        {
            movePos = movePos.AddCopy(moveOffset);
        }

        var action = new PolisGotoAction(
            bot.Activity,
            movePos,
            astar,
            "walk",
            speed,
            1f,
            debugEnabled ? msg => LogDebug(player, msg) : null,
            debugEnabled ? path => HighlightPath(player, path) : null,
            debugEnabled,
            fallback,
            onResult
        );
        StartSingleAction(bot, "gotolook", action);

        LogDebug(player, $"Bot {bot.Entity.EntityId} gotolook {FormatPos(movePos)} range={range.ToString(CultureInfo.InvariantCulture)} astar={astar} speed={speed.ToString(CultureInfo.InvariantCulture)} fallback={fallback}");
        resolvedMovePos = movePos;
        return TextCommandResult.Success(successMessage);
    }

    internal TextCommandResult CmdActivate(TextCommandCallingArgs args)
    {
        var player = args.Caller.Player as IServerPlayer;
        if (player == null) return TextCommandResult.Error("Server player required");
        if (!TryGetSelectedBot(player, out var bot, out var error)) return error;

        var pos = ((Vec3d)args.Parsers[0].GetValue()).AsBlockPos;
        var block = sapi.World.BlockAccessor.GetBlock(pos);
        if (block == null || block.Id == 0) return TextCommandResult.Error("No block at target position");

        ITreeAttribute attrs = null;
        if (!args.Parsers[1].IsMissing)
        {
            var json = (string)args.Parsers[1].GetValue();
            if (!string.IsNullOrWhiteSpace(json))
            {
                try
                {
                    attrs = TreeAttribute.FromJson(json) as ITreeAttribute;
                }
                catch (Exception ex)
                {
                    return TextCommandResult.Error("Invalid JSON args: " + ex.Message);
                }
            }
        }

        var selection = ResolveSelection(player, pos, BlockFacing.NORTH);
        if (!TryValidateBlockTarget(
            player,
            bot,
            selection,
            pos,
            EnumBlockAccessFlags.Use,
            debugEnabled ? msg => LogDebug(player, msg) : null,
            out var movePos,
            out var validationError))
        {
            return validationError;
        }
        var gotoAction = new PolisGotoAction(
            bot.Activity,
            movePos,
            true,
            "walk",
            0.02f,
            1f,
            debugEnabled ? msg => LogDebug(player, msg) : null,
            debugEnabled ? path => HighlightPath(player, path) : null,
            debugEnabled,
            false
        );
        var action = new PolisActivateBlockAction(
            pos,
            selection.Face,
            selection.HitPosition,
            attrs,
            player,
            PolisConstants.DefaultActionRange,
            debugEnabled ? msg => LogDebug(player, msg) : null,
            null
        );
        StartActionSequence(bot, "activate", gotoAction, action);

        Highlight(player, pos, ColorUtil.ToRgba(200, 255, 200, 0));
        LogDebug(player, $"Activated block at {pos}");
        return TextCommandResult.Success("Block activated");
    }

    internal TextCommandResult CmdIgnite(TextCommandCallingArgs args)
    {
        var player = args.Caller.Player as IServerPlayer;
        if (player == null) return TextCommandResult.Error("Server player required");
        if (!TryGetSelectedBot(player, out var bot, out var error)) return error;

        var pos = ((Vec3d)args.Parsers[0].GetValue()).AsBlockPos;
        var block = sapi.World.BlockAccessor.GetBlock(pos);
        if (block == null || block.Id == 0) return TextCommandResult.Error("No block at target position");

        // Check if block implements IIgnitable
        var ignitable = block.GetInterface<IIgnitable>(sapi.World, pos);
        if (ignitable == null)
        {
            return TextCommandResult.Error($"Block {block.Code} does not implement IIgnitable");
        }

        var selection = ResolveSelection(player, pos, BlockFacing.NORTH);
        if (!TryValidateBlockTarget(
            player,
            bot,
            selection,
            pos,
            EnumBlockAccessFlags.Use,
            debugEnabled ? msg => LogDebug(player, msg) : null,
            out var movePos,
            out var validationError))
        {
            return validationError;
        }
        var gotoAction = new PolisGotoAction(
            bot.Activity,
            movePos,
            true,
            "walk",
            0.02f,
            1f,
            debugEnabled ? msg => LogDebug(player, msg) : null,
            debugEnabled ? path => HighlightPath(player, path) : null,
            debugEnabled,
            false
        );
        var action = new PolisIgniteBlockAction(
            pos,
            selection.Face,
            bot.Entity,
            PolisConstants.DefaultActionRange,
            debugEnabled ? msg => LogDebug(player, msg) : null,
            null
        );
        StartActionSequence(bot, "ignite", gotoAction, action);

        Highlight(player, pos, ColorUtil.ToRgba(200, 255, 128, 0));
        LogDebug(player, $"Igniting block at {pos}");
        return TextCommandResult.Success("Igniting block");
    }

    internal TextCommandResult CmdBreak(TextCommandCallingArgs args)
    {
        var player = args.Caller.Player as IServerPlayer;
        if (player == null) return TextCommandResult.Error("Server player required");
        if (!TryGetSelectedBot(player, out var bot, out var error)) return error;

        var pos = ((Vec3d)args.Parsers[0].GetValue()).AsBlockPos;
        float dropMult = !args.Parsers[1].IsMissing ? (float)args.Parsers[1].GetValue() : 1f;

        var selection = ResolveSelection(player, pos, BlockFacing.NORTH);
        if (!TryValidateBlockTarget(
            player,
            bot,
            selection,
            pos,
            EnumBlockAccessFlags.BuildOrBreak,
            debugEnabled ? msg => LogDebug(player, msg) : null,
            out var movePos,
            out var validationError))
        {
            return validationError;
        }
        var gotoAction = new PolisGotoAction(
            bot.Activity,
            movePos,
            true,
            "walk",
            0.02f,
            1f,
            debugEnabled ? msg => LogDebug(player, msg) : null,
            debugEnabled ? path => HighlightPath(player, path) : null,
            debugEnabled,
            false
        );
        var action = new PolisBreakBlockAction(pos, player, dropMult, PolisConstants.DefaultActionRange, debugEnabled ? msg => LogDebug(player, msg) : null, (ok, msg) => bot.RecordActionResult("break", ok, msg, sapi.World.ElapsedMilliseconds));
        StartActionSequence(bot, "break", gotoAction, action);

        Highlight(player, pos, ColorUtil.ToRgba(200, 255, 80, 80));
        LogDebug(player, $"Broke block at {pos} (dropmult {dropMult})");
        return TextCommandResult.Success("Block broken");
    }

    internal TextCommandResult CmdMine(TextCommandCallingArgs args)
    {
        var player = args.Caller.Player as IServerPlayer;
        if (player == null) return TextCommandResult.Error("Server player required");
        if (!TryGetSelectedBot(player, out var bot, out var error)) return error;

        var pos = ((Vec3d)args.Parsers[0].GetValue()).AsBlockPos;
        bool autoCollect = !args.Parsers[1].IsMissing && (bool)args.Parsers[1].GetValue();

        var selection = ResolveSelection(player, pos, BlockFacing.NORTH);
        if (!TryValidateBlockTarget(
            player,
            bot,
            selection,
            pos,
            EnumBlockAccessFlags.BuildOrBreak,
            debugEnabled ? msg => LogDebug(player, msg) : null,
            out var movePos,
            out var validationError))
        {
            return validationError;
        }

        // Resolve owner player for block drops
        string ownerUid = bot.Entity.WatchedAttributes.GetString("polisOwnerUid");
        IServerPlayer ownerPlayer = sapi.World.PlayerByUid(ownerUid) as IServerPlayer ?? player;

        var gotoAction = new PolisGotoAction(
            bot.Activity,
            movePos,
            true,
            "walk",
            0.02f,
            1f,
            debugEnabled ? msg => LogDebug(player, msg) : null,
            debugEnabled ? path => HighlightPath(player, path) : null,
            debugEnabled,
            false
        );

        var action = new PolisMineBlockAction(
            pos,
            ownerPlayer,
            maxRange: PolisConstants.DefaultActionRange,
            autoCollectDrops: autoCollect,
            debugLog: debugEnabled ? msg => LogDebug(player, msg) : null,
            onResult: (ok, msg) =>
            {
                if (ok)
                {
                    LogDebug(player, $"[mine] result: {msg}");
                }
                else
                {
                    LogDebug(player, $"[mine] failed: {msg}");
                }
            }
        );

        StartActionSequence(bot, "mine", gotoAction, action);

        Highlight(player, pos, ColorUtil.ToRgba(200, 100, 150, 255));
        LogDebug(player, $"Mining block at {pos}" + (autoCollect ? " (autocollect)" : ""));
        return TextCommandResult.Success("Mining started");
    }

    internal TextCommandResult CmdHarvest(TextCommandCallingArgs args)
    {
        var player = args.Caller.Player as IServerPlayer;
        if (player == null) return TextCommandResult.Error("Server player required");
        if (!TryGetSelectedBot(player, out var bot, out var error)) return error;

        var pos = ((Vec3d)args.Parsers[0].GetValue()).AsBlockPos;
        bool autoCollect = !args.Parsers[1].IsMissing ? ((bool)args.Parsers[1].GetValue()) : false;
        bool validateRipe = !args.Parsers[2].IsMissing ? ((bool)args.Parsers[2].GetValue()) : true;

        var block = sapi.World.BlockAccessor.GetBlock(pos);
        if (block == null || block.Id == 0)
            return TextCommandResult.Error($"No block at {pos}");

        var action = new PolisHarvestBlockAction(
            pos,
            player,
            maxRange: PolisConstants.DefaultActionRange,
            autoCollectDrops: autoCollect,
            collectRadius: 3f,
            validateRipe: validateRipe,
            debugLog: debugEnabled ? msg => LogDebug(player, msg) : null
        );

        StartSingleAction(bot, "harvest", action);

        Highlight(player, pos, ColorUtil.ToRgba(100, 200, 100, 255));
        LogDebug(player, $"Harvesting block at {pos}" + (autoCollect ? " (autocollect)" : "") + (validateRipe ? " (ripe check)" : ""));
        return TextCommandResult.Success("Harvest started");
    }

    internal TextCommandResult CmdPlace(TextCommandCallingArgs args)
    {
        var player = args.Caller.Player as IServerPlayer;
        if (player == null) return TextCommandResult.Error("Server player required");
        if (!TryGetSelectedBot(player, out var bot, out var error)) return error;

        string code = (string)args.Parsers[0].GetValue();
        var targetPos = ((Vec3d)args.Parsers[1].GetValue()).AsBlockPos;  // Position where block will be placed

        string faceCode = !args.Parsers[2].IsMissing ? ((string)args.Parsers[2].GetValue()).ToLowerInvariant() : "up";
        var face = BlockFacing.FromCode(faceCode) ?? BlockFacing.UP;
        var clickedPos = targetPos.AddCopy(face.Opposite);  // Surface block that was "clicked"

        var block = sapi.World.GetBlock(new AssetLocation(code));
        if (block == null) return TextCommandResult.Error("Unknown block code: " + code);

        var itemstack = new ItemStack(block);
        var selection = ResolveSelection(player, clickedPos, face);
        if (!TryValidateBlockTarget(
            player,
            bot,
            selection,
            targetPos,
            EnumBlockAccessFlags.BuildOrBreak,
            debugEnabled ? msg => LogDebug(player, msg) : null,
            out var movePos,
            out var validationError))
        {
            return validationError;
        }
        var gotoAction = new PolisGotoAction(
            bot.Activity,
            movePos,
            true,
            "walk",
            0.02f,
            1f,
            debugEnabled ? msg => LogDebug(player, msg) : null,
            debugEnabled ? path => HighlightPath(player, path) : null,
            debugEnabled,
            false
        );
        var action = new PolisPlaceBlockAction(targetPos, face, selection.HitPosition, block, itemstack, player, PolisConstants.DefaultActionRange, debugEnabled ? msg => LogDebug(player, msg) : null);
        StartActionSequence(bot, "place", gotoAction, action);

        Highlight(player, targetPos, ColorUtil.ToRgba(200, 80, 200, 80));
        LogDebug(player, $"Placed {code} at {targetPos} (face {face.Code})");
        return TextCommandResult.Success("Block placed");
    }

    internal TextCommandResult CmdPlaceOn(TextCommandCallingArgs args)
    {
        var player = args.Caller.Player as IServerPlayer;
        if (player == null) return TextCommandResult.Error("Server player required");
        if (!TryGetSelectedBot(player, out var bot, out var error)) return error;

        var sel = player.CurrentBlockSelection;
        if (sel == null || sel.Position == null) return TextCommandResult.Error("No block selected.");

        string code = (string)args.Parsers[0].GetValue();
        string faceCode = !args.Parsers[1].IsMissing ? ((string)args.Parsers[1].GetValue()).ToLowerInvariant() : null;
        var face = faceCode != null ? BlockFacing.FromCode(faceCode) : sel.Face;
        if (face == null) face = BlockFacing.UP;

        var block = sapi.World.GetBlock(new AssetLocation(code));
        if (block == null) return TextCommandResult.Error("Unknown block code: " + code);

        var itemstack = new ItemStack(block);
        var clickedPos = sel.Position.Copy();  // Surface block that was clicked
        var selection = ResolveSelection(player, clickedPos, face);
        var targetPos = clickedPos.AddCopy(face);  // Position where block will be placed
        if (!TryValidateBlockTarget(
            player,
            bot,
            selection,
            targetPos,
            EnumBlockAccessFlags.BuildOrBreak,
            debugEnabled ? msg => LogDebug(player, msg) : null,
            out var movePos,
            out var validationError))
        {
            return validationError;
        }
        var gotoAction = new PolisGotoAction(
            bot.Activity,
            movePos,
            true,
            "walk",
            0.02f,
            1f,
            debugEnabled ? msg => LogDebug(player, msg) : null,
            debugEnabled ? path => HighlightPath(player, path) : null,
            debugEnabled,
            false
        );
        var action = new PolisPlaceBlockAction(targetPos, face, selection.HitPosition, block, itemstack, player, PolisConstants.DefaultActionRange, debugEnabled ? msg => LogDebug(player, msg) : null);
        StartActionSequence(bot, "placeon", gotoAction, action);

        Highlight(player, targetPos, ColorUtil.ToRgba(200, 80, 200, 80));
        LogDebug(player, $"Placed {code} on {clickedPos} (face {face.Code})");
        return TextCommandResult.Success("Block placed");
    }

    internal TextCommandResult CmdPlaceHeld(TextCommandCallingArgs args)
    {
        var player = args.Caller.Player as IServerPlayer;
        if (player == null) return TextCommandResult.Error("Server player required");
        if (!TryGetSelectedBot(player, out var bot, out var error)) return error;

        var sel = player.CurrentBlockSelection;
        if (sel == null || sel.Position == null) return TextCommandResult.Error("No block selected.");

        Block block = null;
        ItemStack stack = null;

        var slot = player.InventoryManager?.ActiveHotbarSlot;
        if (slot?.Itemstack?.Collectible is Block playerBlock)
        {
            block = playerBlock;
            stack = slot.Itemstack.Clone();
        }
        else if (bot.Entity.RightHandItemSlot?.Itemstack?.Collectible is Block botBlock)
        {
            block = botBlock;
            stack = bot.Entity.RightHandItemSlot.Itemstack.Clone();
        }

        if (block == null || stack == null)
        {
            return TextCommandResult.Error("No block available. Put a block in your active hotbar or equip the bot's right hand.");
        }
        string faceCode = !args.Parsers[0].IsMissing ? ((string)args.Parsers[0].GetValue()).ToLowerInvariant() : null;
        var face = faceCode != null ? BlockFacing.FromCode(faceCode) : sel.Face;
        if (face == null) face = BlockFacing.UP;

        var clickedPos = sel.Position.Copy();  // Surface block that was clicked
        var selection = ResolveSelection(player, clickedPos, face);
        var targetPos = clickedPos.AddCopy(face);  // Position where block will be placed
        if (!TryValidateBlockTarget(
            player,
            bot,
            selection,
            targetPos,
            EnumBlockAccessFlags.BuildOrBreak,
            debugEnabled ? msg => LogDebug(player, msg) : null,
            out var movePos,
            out var validationError))
        {
            return validationError;
        }
        var gotoAction = new PolisGotoAction(
            bot.Activity,
            movePos,
            true,
            "walk",
            0.02f,
            1f,
            debugEnabled ? msg => LogDebug(player, msg) : null,
            debugEnabled ? path => HighlightPath(player, path) : null,
            debugEnabled,
            false
        );
        var action = new PolisPlaceBlockAction(targetPos, face, selection.HitPosition, block, stack, player, PolisConstants.DefaultActionRange, debugEnabled ? msg => LogDebug(player, msg) : null);
        StartActionSequence(bot, "placeheld", gotoAction, action);

        Highlight(player, targetPos, ColorUtil.ToRgba(200, 80, 200, 80));
        LogDebug(player, $"Placed {block.Code} on {clickedPos} (face {face.Code})");
        return TextCommandResult.Success("Block placed");
    }

    internal TextCommandResult CmdEquip(TextCommandCallingArgs args)
    {
        var player = args.Caller.Player as IServerPlayer;
        if (player == null) return TextCommandResult.Error("Server player required");
        if (!TryGetSelectedBot(player, out var bot, out var error)) return error;

        string slotName = (string)args.Parsers[0].GetValue();
        string code = (string)args.Parsers[1].GetValue();
        int qty = !args.Parsers[2].IsMissing ? (int)args.Parsers[2].GetValue() : 1;
        if (qty < 1) qty = 1;

        if (!TryResolveStack(code, qty, out var stack, out var errorText))
        {
            return TextCommandResult.Error(errorText);
        }

        ItemSlot slot;
        switch (slotName)
        {
            case "righthand":
                slot = bot.Entity.RightHandItemSlot;
                break;
            case "lefthand":
                slot = bot.Entity.LeftHandItemSlot;
                break;
            case "backpack0":
            case "backpack1":
                slot = PolisInventoryHelpers.BackpackSlot(bot.Entity, slotName == "backpack0" ? 0 : 1);
                if (slot == null)
                {
                    return TextCommandResult.Error("Bot has no seraph inventory");
                }
                break;
            default:
                return TextCommandResult.Error($"Unknown slot: {slotName}");
        }

        slot.Itemstack = stack;
        slot.MarkDirty();
        PolisInventoryHelpers.StoreSeraphInventory(bot.Entity);

        LogDebug(player, $"Equipped {code} x{qty} on {slotName}");
        return TextCommandResult.Success("Equipped " + code + " on " + slotName);
    }

    internal TextCommandResult CmdGive(TextCommandCallingArgs args)
    {
        var player = args.Caller.Player as IServerPlayer;
        if (player == null) return TextCommandResult.Error("Server player required");
        if (!TryGetSelectedBot(player, out var bot, out var error)) return error;

        string code = (string)args.Parsers[0].GetValue();
        int qty = !args.Parsers[1].IsMissing ? (int)args.Parsers[1].GetValue() : 1;
        if (qty < 1) qty = 1;

        if (!TryResolveStack(code, qty, out var stack, out var errorText))
        {
            return TextCommandResult.Error(errorText);
        }

        if (!PolisInventoryHelpers.TryInsertIntoBotInventory(bot.Entity, stack, out int moved, out string insertError, debugEnabled ? msg => LogDebug(player, msg) : null))
        {
            return TextCommandResult.Error(insertError ?? "Bot inventory full or not available");
        }

        int remaining = qty - moved;
        string result = remaining > 0
            ? $"Gave {moved}x {code} (partial, {remaining} left)"
            : $"Gave {code} x{qty}";

        LogDebug(player, $"Gave {moved}x {code} to bot");
        return TextCommandResult.Success(result);
    }

    internal TextCommandResult CmdInteract(TextCommandCallingArgs args)
    {
        var player = args.Caller.Player as IServerPlayer;
        if (player == null) return TextCommandResult.Error("Server player required");
        if (!TryGetSelectedBot(player, out var bot, out var error)) return error;

        string modeText = args.Parsers[0].IsMissing ? "interact" : ((string)args.Parsers[0].GetValue() ?? "interact");
        if (!TryParseInteractMode(modeText, out var mode, out var modeError))
        {
            return TextCommandResult.Error(modeError);
        }

        float range = !args.Parsers[1].IsMissing ? (float)args.Parsers[1].GetValue() : PolisConstants.DefaultActionRange;
        range = GameMath.Clamp(range, 1f, PolisConstants.MaxGotoLookRange);

        if (player.Entity == null) return TextCommandResult.Error("Player entity is null.");

        var eyePos = player.Entity.ServerPos.XYZ.AddCopy(player.Entity.LocalEyePos);
        BlockSelection blockSel = null;
        EntitySelection entSel = null;
        sapi.World.RayTraceForSelection(
            eyePos,
            player.Entity.ServerPos.Pitch,
            player.Entity.ServerPos.Yaw,
            range,
            ref blockSel,
            ref entSel
        );

        if (entSel?.Entity == null)
        {
            return TextCommandResult.Error("No entity selected.");
        }

        var target = entSel.Entity;
        var movePos = target.ServerPos.XYZ.Clone();
        var gotoAction = new PolisGotoAction(
            bot.Activity,
            movePos,
            true,
            "walk",
            0.02f,
            1f,
            debugEnabled ? msg => LogDebug(player, msg) : null,
            debugEnabled ? path => HighlightPath(player, path) : null,
            debugEnabled,
            false
        );
        var action = new PolisInteractEntityAction(
            bot.Activity,
            target.EntityId,
            entSel.HitPosition?.Clone(),
            mode,
            range,
            debugEnabled ? msg => LogDebug(player, msg) : null,
            (ok, msg) => bot.RecordActionResult("interact", ok, msg, sapi.World.ElapsedMilliseconds)
        );
        StartActionSequence(bot, "interact", gotoAction, action);

        LogDebug(player, $"Interact entity {target.EntityId} mode={mode} range={range:0.00}");
        return TextCommandResult.Success("Interact started");
    }

    internal TextCommandResult CmdPickup(TextCommandCallingArgs args)
    {
        var player = args.Caller.Player as IServerPlayer;
        if (player == null) return TextCommandResult.Error("Server player required");
        if (!TryGetSelectedBot(player, out var bot, out var error)) return error;

        float range = !args.Parsers[1].IsMissing ? (float)args.Parsers[1].GetValue() : PolisConstants.DefaultActionRange;
        range = GameMath.Clamp(range, 1f, PolisConstants.MaxGotoLookRange);

        EntityItem targetItem = null;

        // If entity id provided, use that
        if (!args.Parsers[0].IsMissing)
        {
            long entityId = (long)args.Parsers[0].GetValue();
            var entity = sapi.World.GetEntityById(entityId);
            if (entity == null)
            {
                return TextCommandResult.Error($"Entity {entityId} not found");
            }
            targetItem = entity as EntityItem;
            if (targetItem == null)
            {
                return TextCommandResult.Error($"Entity {entityId} is not an item entity");
            }
        }
        else
        {
            // Find nearest item entity to player's look target or bot position
            var searchPos = bot.Entity.ServerPos.XYZ;
            double nearestDist = double.MaxValue;

            foreach (var entity in sapi.World.LoadedEntities.Values)
            {
                var item = entity as EntityItem;
                if (item == null || !item.Alive) continue;

                var dist = item.ServerPos.XYZ.DistanceTo(searchPos);
                if (dist < nearestDist && dist <= range * 2)
                {
                    nearestDist = dist;
                    targetItem = item;
                }
            }

            if (targetItem == null)
            {
                return TextCommandResult.Error("No item entity found nearby");
            }
        }

        var itemCode = targetItem.Itemstack?.Collectible?.Code?.ToString() ?? "unknown";
        var movePos = targetItem.ServerPos.XYZ.Clone();

        var gotoAction = new PolisGotoAction(
            bot.Activity,
            movePos,
            true,
            "walk",
            0.02f,
            1.5f,
            debugEnabled ? msg => LogDebug(player, msg) : null,
            debugEnabled ? path => HighlightPath(player, path) : null,
            debugEnabled,
            false
        );
        var pickupAction = new PolisPickupItemAction(
            bot.Activity,
            targetItem.EntityId,
            range,
            debugEnabled ? msg => LogDebug(player, msg) : null,
            (ok, msg) => bot.RecordActionResult("pickup", ok, msg, sapi.World.ElapsedMilliseconds)
        );
        StartActionSequence(bot, "pickup", gotoAction, pickupAction);

        LogDebug(player, $"Pickup started: {itemCode} entity={targetItem.EntityId}");
        return TextCommandResult.Success($"Picking up {itemCode}");
    }

    internal TextCommandResult CmdDrop(TextCommandCallingArgs args)
    {
        var player = args.Caller.Player as IServerPlayer;
        if (player == null) return TextCommandResult.Error("Server player required");
        if (!TryGetSelectedBot(player, out var bot, out var error)) return error;

        int slotIndex = !args.Parsers[0].IsMissing ? (int)args.Parsers[0].GetValue() : -1;
        int qty = !args.Parsers[1].IsMissing ? (int)args.Parsers[1].GetValue() : 0;

        var dropAction = new PolisDropItemAction(
            bot.Activity,
            slotIndex,
            qty,
            debugEnabled ? msg => LogDebug(player, msg) : null,
            (ok, msg) => bot.RecordActionResult("drop", ok, msg, sapi.World.ElapsedMilliseconds)
        );
        StartSingleAction(bot, "drop", dropAction);

        LogDebug(player, $"Drop started: slot={slotIndex} qty={qty}");
        return TextCommandResult.Success("Drop started");
    }

    internal TextCommandResult CmdTakeFrom(TextCommandCallingArgs args)
    {
        var player = args.Caller.Player as IServerPlayer;
        if (player == null) return TextCommandResult.Error("Server player required");
        if (!TryGetSelectedBot(player, out var bot, out var error)) return error;

        var pos = ((Vec3d)args.Parsers[0].GetValue()).AsBlockPos;
        int slotIndex = (int)args.Parsers[1].GetValue();
        int qty = args.Parsers[2].IsMissing ? 0 : (int)args.Parsers[2].GetValue();

        // Resolve bot owner player for claims check
        BotRecord botRecord = globalData.Bots[bot.Entity.EntityId];
        IServerPlayer ownerPlayer = sapi.World.PlayerByUid(botRecord.OwnerUid) as IServerPlayer;
        if (ownerPlayer == null)
        {
            return TextCommandResult.Error("Bot owner is offline or unknown");
        }

        var action = new PolisContainerTakeAction(
            bot.Activity,
            pos,
            slotIndex,
            qty,
            ownerPlayer,
            PolisConstants.DefaultActionRange,
            debugEnabled ? msg => LogDebug(player, msg) : null,
            (ok, msg) => bot.RecordActionResult("takefrom", ok, msg, sapi.World.ElapsedMilliseconds)
        );

        StartSingleAction(bot, "takefrom", action);
        LogDebug(player, $"takefrom queued: pos={FormatBlockPos(pos)} slot={slotIndex} qty={qty}");
        return TextCommandResult.Success("takefrom started");
    }

    internal TextCommandResult CmdPutInto(TextCommandCallingArgs args)
    {
        var player = args.Caller.Player as IServerPlayer;
        if (player == null) return TextCommandResult.Error("Server player required");
        if (!TryGetSelectedBot(player, out var bot, out var error)) return error;

        var pos = ((Vec3d)args.Parsers[0].GetValue()).AsBlockPos;
        int slotIndex = (int)args.Parsers[1].GetValue();
        int qty = args.Parsers[2].IsMissing ? 0 : (int)args.Parsers[2].GetValue();

        // Resolve bot owner player for claims check
        BotRecord botRecord = globalData.Bots[bot.Entity.EntityId];
        IServerPlayer ownerPlayer = sapi.World.PlayerByUid(botRecord.OwnerUid) as IServerPlayer;
        if (ownerPlayer == null)
        {
            return TextCommandResult.Error("Bot owner is offline or unknown");
        }

        var action = new PolisContainerPutAction(
            bot.Activity,
            pos,
            0, // bot source slot: always right hand
            qty,
            ownerPlayer,
            slotIndex, // container slot index
            PolisConstants.DefaultActionRange,
            debugEnabled ? msg => LogDebug(player, msg) : null,
            (ok, msg) => bot.RecordActionResult("putinto", ok, msg, sapi.World.ElapsedMilliseconds)
        );

        StartSingleAction(bot, "putinto", action);
        LogDebug(player, $"putinto queued: pos={FormatBlockPos(pos)} containerSlot={slotIndex} qty={qty}");
        return TextCommandResult.Success("putinto started");
    }

    internal TextCommandResult CmdValidate(TextCommandCallingArgs args)
    {
        var player = args.Caller.Player as IServerPlayer;
        if (player == null) return TextCommandResult.Error("Server player required");
        if (!TryGetSelectedBot(player, out var bot, out var error)) return error;

        var pos = ((Vec3d)args.Parsers[0].GetValue()).AsBlockPos;
        string accessText = args.Parsers[1].IsMissing ? "use" : ((string)args.Parsers[1].GetValue() ?? "use");
        if (!TryParseAccessFlag(accessText, out var accessFlag, out var accessError))
        {
            return TextCommandResult.Error(accessError);
        }

        var selectionSource = TryGetSelection(player, pos, out _) ? "player" : "fallback";
        var selection = ResolveSelection(player, pos, BlockFacing.NORTH);
        var losOk = HasLineOfSightToBlock(player.Entity, selection, out var hitSel);
        var claimResponse = sapi.World.Claims?.TestAccess(player, pos, accessFlag) ?? EnumWorldAccessResponse.Granted;
        var targetCenter = new Vec3d(pos.X + 0.5, pos.Y + 0.5, pos.Z + 0.5);
        var dist = bot.Entity?.ServerPos?.XYZ.DistanceTo(targetCenter) ?? -1;

        var lines = new List<string>
        {
            $"validate target={FormatBlockPos(pos)} access={accessFlag}",
            $"selection source={selectionSource} face={selection.Face?.Code ?? "?"} hitLocal={FormatPos(selection.HitPosition)} hitWorld={FormatPos(GetSelectionWorldPos(selection))}",
            $"los={(losOk ? "ok" : "blocked")} hit={FormatBlockPos(hitSel?.Position)}",
            $"claims={claimResponse}",
            $"range={dist:0.00} (<= {PolisConstants.DefaultActionRange:0.00}? {(dist >= 0 && dist <= PolisConstants.DefaultActionRange ? "yes" : "no")})"
        };

        return TextCommandResult.Success(string.Join("\n", lines));
    }

    internal TextCommandResult CmdDebug(TextCommandCallingArgs args)
    {
        bool enabled;
        if (args.Parsers[0].IsMissing)
        {
            enabled = !debugEnabled;
        }
        else
        {
            string mode = (string)args.Parsers[0].GetValue();
            enabled = mode.Equals("on", StringComparison.OrdinalIgnoreCase) || mode.Equals("true", StringComparison.OrdinalIgnoreCase);
        }

        debugEnabled = enabled;
        foreach (var bot in bots.Values)
        {
            bot.Activity.Debug = debugEnabled;
            TrySetTraverserDebug(bot.Activity?.wppathTraverser, false, null);
        }

        foreach (var player in sapi.World.AllOnlinePlayers)
        {
            serverChannel.SendPacket(new PolisDebugStatePacket { DebugEnabled = debugEnabled }, player as IServerPlayer);
        }

        if (!debugEnabled)
        {
            foreach (var entry in selectedByPlayer)
            {
                var player = sapi.World.PlayerByUid(entry.Key) as IServerPlayer;
                if (player == null) continue;
                sapi.World.HighlightBlocks(player, PolisConstants.HighlightSlotId, new List<BlockPos>());
                sapi.World.HighlightBlocks(player, PolisConstants.PathHighlightSlotId, new List<BlockPos>());
                sapi.World.HighlightBlocks(player, PolisConstants.BotHighlightSlotId, new List<BlockPos>());
            }
            highlightClearAtMs.Clear();
            pathHighlightClearAtMs.Clear();
        }
        ClearEnginePathDebugHighlight();

        // Emit debug_toggled event
        testHarness?.Broadcaster?.QueueEvent("debug_toggled", PolisLogLevel.Normal, new
        {
            enabled = debugEnabled
        });

        return TextCommandResult.Success("Debug " + (debugEnabled ? "on" : "off"));
    }

    internal TextCommandResult CmdPathDump(TextCommandCallingArgs args)
    {
        var player = args.Caller.Player as IServerPlayer;
        if (player == null) return TextCommandResult.Error("Server player required");
        if (!TryGetSelectedBot(player, out var bot, out var error)) return error;

        var traverser = bot.Activity?.wppathTraverser;
        if (traverser == null) return TextCommandResult.Error("Bot has no waypoint traverser");

        LogDebug(player, "[pathdump] traverser: " + traverser.GetType().FullName);
        LogDebug(player, "[pathdump] members: " + DescribeTraverserMembers(traverser));

        if (TryExtractPathFromTraverser(traverser, out var blocks, out var rawCount, out var source))
        {
            LogDebug(player, $"[pathdump] path source={source} nodes={rawCount}");
            HighlightPath(player, blocks);
            return TextCommandResult.Success("Path dumped: " + rawCount + " nodes");
        }

        return TextCommandResult.Success("Path dump: no path nodes found");
    }

    internal TextCommandResult CmdEntityTypes(TextCommandCallingArgs args)
    {
        string filter = args.Parsers[0].IsMissing ? null : (string)args.Parsers[0].GetValue();

        var matches = sapi.World.EntityTypes
            .Select(t => t?.Code?.ToShortString())
            .Where(code => !string.IsNullOrWhiteSpace(code))
            .Where(code => filter == null || code.IndexOf(filter, StringComparison.OrdinalIgnoreCase) >= 0)
            .ToList();

        if (matches.Count == 0)
        {
            return TextCommandResult.Success(filter == null ? "No entity types found." : "No entity types match: " + filter);
        }

        const int maxList = 40;
        var shown = matches.Take(maxList).ToList();
        string suffix = matches.Count > maxList ? $" (showing {maxList} of {matches.Count})" : "";

        return TextCommandResult.Success(string.Join(", ", shown) + suffix);
    }

    bool TryGetSelectedBot(IServerPlayer player, out BotState bot, out TextCommandResult error)
    {
        bot = null;
        error = null;

        if (!selectedByPlayer.TryGetValue(player.PlayerUID, out var id))
        {
            if (bots.Count == 1)
            {
                foreach (var entry in bots)
                {
                    id = entry.Key;
                    selectedByPlayer[player.PlayerUID] = id;
                    break;
                }
            }
            else
            {
                error = TextCommandResult.Error("No bot selected. Use /polis spawn or /polis select <id>.");
                return false;
            }
        }

        if (!bots.TryGetValue(id, out bot) || bot.Entity == null || !bot.Entity.Alive)
        {
            selectedByPlayer.Remove(player.PlayerUID);
            error = TextCommandResult.Error("Selected bot not found.");
            return false;
        }

        return true;
    }

    void StartSingleAction(BotState bot, string name, IEntityAction action)
    {
        StartActionSequence(bot, name, action);
    }

    void StartActionSequence(BotState bot, string name, params IEntityAction[] actions)
    {
        // The forage/feed guard: while a bot is in a forage episode, no
        // new job action may displace it — the mission layer (r2) sees
        // the refusal in LastAction and simply waits out the meal.
        // The forage controller itself bypasses this (its own phases).
        if (!forageBypassGuard && forageEpisodes.ContainsKey(bot.Entity.EntityId))
        {
            bot.RecordActionResult(name, false, "refused:foraging (food-pressure episode in progress; retry after it ends)", sapi.World.ElapsedMilliseconds);
            return;
        }
        // The action name doubles as the safe-point key for the food-
        // pressure interrupt: the policy's `preempt.waitTypes` lists the
        // job names with side effects (harvest/mine/place/...) that are
        // only preempted at their finish.
        bot.LastActionType = name;
        if (!name.StartsWith("forage-"))
        {
            bot.JobRunning = true;
            foragePendingStart.Remove(bot.Entity.EntityId);   // a new job displaces any deferred start
        }
        bot.Activity.CancelAll();

        var activity = new EntityActivity(bot.Activity)
        {
            Name = name,
            Code = name,
            Slot = 0,
            Priority = 9999,
            Actions = actions
        };
        activity.OnLoaded(bot.Activity);

        bot.Activity.ActiveActivitiesBySlot[activity.Slot] = activity;
        bot.Activity.ClearNextActionDelay();
        activity.Start();
    }

    bool TryGetSelection(IServerPlayer player, BlockPos targetPos, out BlockSelection selection)
    {
        selection = player?.CurrentBlockSelection;
        if (selection?.Position == null) return false;

        return selection.Position.X == targetPos.X
            && selection.Position.Y == targetPos.Y
            && selection.Position.Z == targetPos.Z;
    }

    BlockSelection ResolveSelection(IServerPlayer player, BlockPos targetPos, BlockFacing fallbackFace)
    {
        if (!TryGetSelection(player, targetPos, out var selection))
        {
            return new BlockSelection
            {
                Position = targetPos,
                Face = fallbackFace,
                HitPosition = new Vec3d(0.5, 0.5, 0.5),
                Block = sapi.World.BlockAccessor.GetBlock(targetPos)
            };
        }

        return new BlockSelection
        {
            Position = targetPos,
            Face = selection.Face ?? fallbackFace,
            HitPosition = selection.HitPosition ?? new Vec3d(0.5, 0.5, 0.5),
            Block = sapi.World.BlockAccessor.GetBlock(targetPos)
        };
    }

    /// <summary>
    /// Test-world escape hatch: POLIS_SKIP_CLAIMS=1 disables all claim
    /// access checks. Only for dedicated single-player test worlds where
    /// the harness drives every block operation.
    /// </summary>
    internal static bool SkipClaims =>
        Environment.GetEnvironmentVariable("POLIS_SKIP_CLAIMS") == "1";

    bool TryValidateBlockTarget(
        IServerPlayer player,
        BotState bot,
        BlockSelection selection,
        BlockPos accessPos,
        EnumBlockAccessFlags access,
        Action<string> debugLog,
        out Vec3d movePos,
        out TextCommandResult error,
        EntityAgent losEntity = null
    )
    {
        movePos = null;
        error = null;

        if (player == null)
        {
            error = TextCommandResult.Error("Server player required");
            return false;
        }

        if (bot?.Entity == null)
        {
            error = TextCommandResult.Error("Bot not found");
            return false;
        }

        if (selection?.Position == null)
        {
            error = TextCommandResult.Error("No block selected.");
            return false;
        }

        var targetPos = selection.Position;
        var claimPos = accessPos ?? targetPos;
        if (!SkipClaims && sapi.World.Claims != null && !sapi.World.Claims.TryAccess(player, claimPos, access))
        {
            debugLog?.Invoke($"[validate] failed: claims access={access} pos={claimPos}");
            error = TextCommandResult.Error("Access denied.");
            return false;
        }

        var viewer = losEntity ?? player?.Entity;
        if (viewer == null)
        {
            error = TextCommandResult.Error("Line of sight requires a viewer entity.");
            return false;
        }

        if (!HasLineOfSightToBlock(viewer, selection, out var hitSel))
        {
            if (hitSel?.Position != null)
            {
                debugLog?.Invoke($"[validate] failed: LOS blocked by {hitSel.Position}");
            }
            else
            {
                debugLog?.Invoke("[validate] failed: no line of sight");
            }
            error = TextCommandResult.Error("No line of sight to target.");
            return false;
        }

        if (hitSel != null)
        {
            selection.Face = hitSel.Face ?? selection.Face;
            selection.HitPosition = hitSel.HitPosition ?? selection.HitPosition;
            selection.SelectionBoxIndex = hitSel.SelectionBoxIndex;
            selection.Block ??= hitSel.Block;
        }

        movePos = GetApproachPosition(selection, targetPos.ToVec3d());
        return true;
    }

    IEnumerable<Vec3d> GetSelectionRayTargets(BlockSelection selection)
    {
        if (selection?.Position == null) yield break;

        var pos = selection.Position;
        var block = selection.Block ?? sapi.World.BlockAccessor.GetBlock(pos);
        var boxes = block?.GetSelectionBoxes(sapi.World.BlockAccessor, pos);

        if (boxes != null && boxes.Length > 0)
        {
            foreach (var box in boxes)
            {
                // 1. Box center (best for full blocks)
                yield return new Vec3d(
                    pos.X + (box.X1 + box.X2) / 2.0,
                    pos.Y + (box.Y1 + box.Y2) / 2.0,
                    pos.Z + (box.Z1 + box.Z2) / 2.0
                );

                // 2. All 8 corners (critical for narrow boxes)
                // Inset slightly (0.01) to ensure ray endpoints are inside the box
                double inset = 0.01;
                double x1 = pos.X + box.X1 + inset;
                double y1 = pos.Y + box.Y1 + inset;
                double z1 = pos.Z + box.Z1 + inset;
                double x2 = pos.X + box.X2 - inset;
                double y2 = pos.Y + box.Y2 - inset;
                double z2 = pos.Z + box.Z2 - inset;

                yield return new Vec3d(x1, y1, z1);
                yield return new Vec3d(x1, y1, z2);
                yield return new Vec3d(x1, y2, z1);
                yield return new Vec3d(x1, y2, z2);
                yield return new Vec3d(x2, y1, z1);
                yield return new Vec3d(x2, y1, z2);
                yield return new Vec3d(x2, y2, z1);
                yield return new Vec3d(x2, y2, z2);

                // 3. Face centers (6 points - for oblique angles)
                double midX = (x1 + x2) / 2.0;
                double midY = (y1 + y2) / 2.0;
                double midZ = (z1 + z2) / 2.0;

                yield return new Vec3d(x1, midY, midZ);   // -X face
                yield return new Vec3d(x2, midY, midZ);   // +X face
                yield return new Vec3d(midX, y1, midZ);   // -Y face (bottom)
                yield return new Vec3d(midX, y2, midZ);   // +Y face (top)
                yield return new Vec3d(midX, midY, z1);   // -Z face
                yield return new Vec3d(midX, midY, z2);   // +Z face
            }
        }

        // Fallback: block center or provided hit position
        var fallback = GetSelectionWorldPos(selection);
        if (fallback != null)
        {
            yield return fallback;
        }
    }

    bool HasLineOfSightToBlock(Entity viewer, BlockSelection selection, out BlockSelection hitSelection)
    {
        hitSelection = null;
        if (viewer?.ServerPos == null || selection?.Position == null) return false;

        var fromPos = viewer.ServerPos.XYZ.AddCopy(viewer.LocalEyePos);

        foreach (var targetPos in GetSelectionRayTargets(selection))
        {
            EntitySelection entSel = null;
            BlockSelection hitSel = null;
            sapi.World.RayTraceForSelection(fromPos, targetPos, ref hitSel, ref entSel);
            if (IsSameBlockPos(hitSel?.Position, selection.Position))
            {
                hitSelection = hitSel;
                return true;
            }
        }

        return false;
    }

    Vec3d GetSelectionWorldPos(BlockSelection selection)
    {
        if (selection?.Position == null) return null;
        var basePos = selection.Position.ToVec3d();
        var hit = selection.HitPosition ?? new Vec3d(0.5, 0.5, 0.5);
        return basePos.AddCopy(hit);
    }

    static bool IsSameBlockPos(BlockPos a, BlockPos b)
    {
        if (a == null || b == null) return false;
        return a.X == b.X && a.Y == b.Y && a.Z == b.Z;
    }

    Vec3d GetApproachPosition(IServerPlayer player, Vec3d requestedPos)
    {
        var targetPos = requestedPos.AsBlockPos;
        if (TryGetSelection(player, targetPos, out var selection))
        {
            return GetApproachPosition(selection, requestedPos);
        }

        return requestedPos;
    }

    Vec3d GetApproachPosition(BlockSelection selection, Vec3d fallbackPos)
    {
        if (selection?.Face == null || selection.Position == null) return fallbackPos;

        var approach = selection.Position.AddCopy(selection.Face);
        return new Vec3d(approach.X + 0.5, approach.Y, approach.Z + 0.5);
    }

    bool ResolveGotoLookTarget(
        IServerPlayer player,
        float range,
        out BlockSelection blockSel,
        out Vec3d targetPos,
        out Vec3d movePos,
        out bool usedTallGrassFallback,
        out bool snappedToGround
    )
    {
        blockSel = null;
        targetPos = null;
        movePos = null;
        usedTallGrassFallback = false;
        snappedToGround = false;

        if (player?.Entity == null) return false;

        range = GameMath.Clamp(range, 2f, PolisConstants.MaxGotoLookRange);

        var eyePos = player.Entity.ServerPos.XYZ.AddCopy(player.Entity.LocalEyePos);
        BlockSelection filteredSel = null;
        EntitySelection filteredEntSel = null;
        BlockSelection rawBlockSel = null;
        EntitySelection rawEntSel = null;
        BlockFilter ignoreTallGrass = (pos, block) => !IsTallGrassBlock(block);

        sapi.World.RayTraceForSelection(
            eyePos,
            player.Entity.ServerPos.Pitch,
            player.Entity.ServerPos.Yaw,
            range,
            ref filteredSel,
            ref filteredEntSel,
            ignoreTallGrass
        );

        if (filteredSel == null)
        {
            sapi.World.RayTraceForSelection(
                eyePos,
                player.Entity.ServerPos.Pitch,
                player.Entity.ServerPos.Yaw,
                range,
                ref rawBlockSel,
                ref rawEntSel
            );
        }

        targetPos = filteredSel?.Position?.ToVec3d();
        if (targetPos == null && rawBlockSel != null && IsTallGrassBlock(rawBlockSel.Block))
        {
            targetPos = rawBlockSel.Position.ToVec3d();
            usedTallGrassFallback = true;

            // Snap to ground below tall grass
            if (TryFindStandPos(targetPos, out var grassStandPos))
            {
                targetPos = grassStandPos;
                snappedToGround = true;
            }
        }

        if (targetPos == null)
        {
            blockSel = rawBlockSel;
            targetPos = blockSel?.Position?.ToVec3d()
                ?? eyePos.AheadCopy(range, player.Entity.ServerPos.Pitch, player.Entity.ServerPos.Yaw);
        }
        else
        {
            blockSel = filteredSel;
        }

        if (blockSel == null && TryFindStandPos(targetPos, out var standPos))
        {
            targetPos = standPos;
            snappedToGround = true;
        }

        movePos = GetApproachPosition(blockSel, targetPos);
        return true;
    }

    bool IsTallGrassBlock(Block block)
    {
        if (block == null) return false;

        var path = block.Code?.Path;
        if (path == null) return false;

        return path.StartsWith("tallgrass", StringComparison.Ordinal)
            || path.StartsWith("frostedtallgrass", StringComparison.Ordinal);
    }

    bool TryFindStandPos(Vec3d targetPos, out Vec3d standPos)
    {
        standPos = null;
        var blockAccessor = sapi.World.BlockAccessor;
        var basePos = targetPos.AsBlockPos;

        const int maxDown = 40;
        for (int dy = 0; dy <= maxDown; dy++)
        {
            var checkPos = new BlockPos(basePos.X, basePos.Y - dy, basePos.Z);
            var block = blockAccessor.GetBlock(checkPos);
            if (block == null || block.Id == 0) continue;
            if (!block.SideSolid[BlockFacing.UP.Index]) continue;

            var above = checkPos.UpCopy();
            var blockAbove = blockAccessor.GetBlock(above);
            if (blockAbove != null && blockAbove.Id != 0 && blockAbove.SideSolid[BlockFacing.DOWN.Index]) continue;

            standPos = new Vec3d(above.X + 0.5, above.Y, above.Z + 0.5);
            return true;
        }

        return false;
    }

    void UpdateHighlights()
    {
        if (highlightClearAtMs.Count == 0) return;

        long now = sapi.World.ElapsedMilliseconds;
        var expired = new List<string>();

        foreach (var entry in highlightClearAtMs)
        {
            if (now < entry.Value) continue;

            var player = sapi.World.PlayerByUid(entry.Key) as IServerPlayer;
            if (player != null)
            {
                sapi.World.HighlightBlocks(player, PolisConstants.HighlightSlotId, new List<BlockPos>());
            }

            expired.Add(entry.Key);
        }

        for (int i = 0; i < expired.Count; i++)
        {
            highlightClearAtMs.Remove(expired[i]);
        }
    }

    void Highlight(IServerPlayer player, BlockPos pos, int color)
    {
        if (!debugEnabled) return;

        sapi.World.HighlightBlocks(
            player,
            PolisConstants.HighlightSlotId,
            new List<BlockPos> { pos },
            new List<int> { color },
            EnumHighlightBlocksMode.Absolute,
            EnumHighlightShape.Cube
        );

        highlightClearAtMs[player.PlayerUID] = sapi.World.ElapsedMilliseconds + 2000;
    }

    void HighlightPath(IServerPlayer player, List<BlockPos> path)
    {
        if (player == null) return;

        if (path == null || path.Count == 0)
        {
            sapi.World.HighlightBlocks(player, PolisConstants.PathHighlightSlotId, new List<BlockPos>());
            if (!string.IsNullOrEmpty(player.PlayerUID))
            {
                pathHighlightClearAtMs.Remove(player.PlayerUID);
            }
            return;
        }

        if (!debugEnabled) return;

        var colors = new List<int>(path.Count);
        int pathColor = ColorUtil.ToRgba(180, 50, 120, 255);
        for (int i = 0; i < path.Count; i++)
        {
            colors.Add(pathColor);
        }

        sapi.World.HighlightBlocks(
            player,
            PolisConstants.PathHighlightSlotId,
            path,
            colors,
            EnumHighlightBlocksMode.Absolute,
            EnumHighlightShape.Arbitrary
        );

        pathHighlightClearAtMs[player.PlayerUID] = sapi.World.ElapsedMilliseconds + 6000;
    }

    void UpdatePathHighlights()
    {
        if (pathHighlightClearAtMs.Count == 0) return;

        long now = sapi.World.ElapsedMilliseconds;
        var expired = new List<string>();

        foreach (var entry in pathHighlightClearAtMs)
        {
            if (now < entry.Value) continue;

            var player = sapi.World.PlayerByUid(entry.Key) as IServerPlayer;
            if (player != null)
            {
                sapi.World.HighlightBlocks(player, PolisConstants.PathHighlightSlotId, new List<BlockPos>());
            }

            expired.Add(entry.Key);
        }

        for (int i = 0; i < expired.Count; i++)
        {
            pathHighlightClearAtMs.Remove(expired[i]);
        }
    }

    void HighlightZone(IServerPlayer player, Cuboidi bounds, int durationMs = 300000)
    {
        // Collect all edge/corner blocks of the AABB (wireframe outline)
        var positions = new List<BlockPos>();

        // Bottom and top face edges (perimeter only, not filled)
        for (int x = bounds.X1; x <= bounds.X2; x++)
        {
            positions.Add(new BlockPos(x, bounds.Y1, bounds.Z1));
            positions.Add(new BlockPos(x, bounds.Y1, bounds.Z2));
            positions.Add(new BlockPos(x, bounds.Y2, bounds.Z1));
            positions.Add(new BlockPos(x, bounds.Y2, bounds.Z2));
        }
        for (int z = bounds.Z1 + 1; z < bounds.Z2; z++)
        {
            positions.Add(new BlockPos(bounds.X1, bounds.Y1, z));
            positions.Add(new BlockPos(bounds.X2, bounds.Y1, z));
            positions.Add(new BlockPos(bounds.X1, bounds.Y2, z));
            positions.Add(new BlockPos(bounds.X2, bounds.Y2, z));
        }
        // Vertical edges
        for (int y = bounds.Y1 + 1; y < bounds.Y2; y++)
        {
            positions.Add(new BlockPos(bounds.X1, y, bounds.Z1));
            positions.Add(new BlockPos(bounds.X2, y, bounds.Z1));
            positions.Add(new BlockPos(bounds.X1, y, bounds.Z2));
            positions.Add(new BlockPos(bounds.X2, y, bounds.Z2));
        }

        var colors = new List<int>(positions.Count);
        int zoneColor = ColorUtil.ToRgba(160, 100, 200, 255); // Purple
        for (int i = 0; i < positions.Count; i++)
        {
            colors.Add(zoneColor);
        }

        sapi.World.HighlightBlocks(player, PolisConstants.ZoneHighlightSlotId, positions, colors,
            EnumHighlightBlocksMode.Absolute, EnumHighlightShape.Cube);

        zoneHighlightClearAtMs[player.PlayerUID] = sapi.World.ElapsedMilliseconds + durationMs;
    }

    void UpdateZoneHighlights()
    {
        if (zoneHighlightClearAtMs.Count == 0) return;

        long now = sapi.World.ElapsedMilliseconds;
        var expired = new List<string>();

        foreach (var entry in zoneHighlightClearAtMs)
        {
            if (now < entry.Value) continue;

            var player = sapi.World.PlayerByUid(entry.Key) as IServerPlayer;
            if (player != null)
            {
                sapi.World.HighlightBlocks(player, PolisConstants.ZoneHighlightSlotId, new List<BlockPos>());
            }

            expired.Add(entry.Key);
        }

        for (int i = 0; i < expired.Count; i++)
        {
            zoneHighlightClearAtMs.Remove(expired[i]);
        }
    }

    void UpdatePreviewPaths()
    {
        if (previewByPlayer.Count == 0) return;

        long now = sapi.World.ElapsedMilliseconds;
        var toRemove = new List<string>();

        foreach (var entry in previewByPlayer)
        {
            var state = entry.Value;
            if (!state.Enabled && !state.Locked) continue;
            if (now < state.NextUpdateAtMs) continue;

            var player = sapi.World.PlayerByUid(entry.Key) as IServerPlayer;
            if (player == null)
            {
                toRemove.Add(entry.Key);
                continue;
            }

            if (!TryGetSelectedBot(player, out var bot, out _))
            {
                ClearPreviewHighlight(player);
                state.NextUpdateAtMs = now + PolisConstants.PreviewPathIntervalMs;
                continue;
            }

            Vec3d movePos;
            if (state.Locked)
            {
                movePos = state.LockedTarget;
                if (movePos == null)
                {
                    state.Locked = false;
                    if (!state.Enabled) ClearPreviewHighlight(player);
                    state.NextUpdateAtMs = now + PolisConstants.PreviewPathIntervalMs;
                    continue;
                }

                var dist = bot.Entity?.ServerPos?.XYZ?.DistanceTo(movePos) ?? double.MaxValue;
                if (dist <= 0.75)
                {
                    state.Locked = false;
                    if (!state.Enabled) ClearPreviewHighlight(player);
                    state.NextUpdateAtMs = now + PolisConstants.PreviewPathIntervalMs;
                    continue;
                }
            }
            else
            {
                if (!ResolveGotoLookTarget(player, state.Range, out _, out _, out movePos, out _, out _))
                {
                    ClearPreviewHighlight(player);
                    state.NextUpdateAtMs = now + PolisConstants.PreviewPathIntervalMs;
                    continue;
                }
            }

            var psys = sapi.ModLoader.GetModSystem<PathfindSystem>();
            if (psys == null)
            {
                ClearPreviewHighlight(player);
                state.NextUpdateAtMs = now + PolisConstants.PreviewPathIntervalMs;
                continue;
            }

            var startPos = bot.Entity.ServerPos.AsBlockPos;
            var targetBlockPos = movePos.AsBlockPos;
            var bh = bot.Entity.GetBehavior<EntityBehaviorControlledPhysics>();
            float stepHeight = bh == null ? 0.6f : bh.StepHeight;
            bool avoidFall = bot.Entity.Properties.FallDamage && bot.Entity.Properties.Attributes?["reckless"].AsBool(false) != true;
            int maxFallHeight = avoidFall ? 4 : 12;
            EnumAICreatureType creatureType = ResolveCreatureType(bot.Entity);

            List<Vec3d> waypoints = psys.FindPathAsWaypoints(
                startPos,
                targetBlockPos,
                -1f,
                maxFallHeight,
                stepHeight,
                bot.Entity.CollisionBox,
                PolisConstants.PreviewPathSearchDepth,
                0,
                creatureType
            );

            if (waypoints == null || waypoints.Count == 0)
            {
                ClearPreviewHighlight(player);
                if (state.Locked)
                {
                    state.Locked = false;
                }
                state.NextUpdateAtMs = now + PolisConstants.PreviewPathIntervalMs;
                continue;
            }

            var path = new List<BlockPos>(Math.Min(waypoints.Count, PolisConstants.MaxPathHighlights));
            for (int i = 0; i < waypoints.Count && path.Count < PolisConstants.MaxPathHighlights; i++)
            {
                path.Add(waypoints[i].AsBlockPos);
            }

            HighlightPreviewPath(player, path);
            state.NextUpdateAtMs = now + PolisConstants.PreviewPathIntervalMs;
        }

        for (int i = 0; i < toRemove.Count; i++)
        {
            previewByPlayer.Remove(toRemove[i]);
        }
    }

    void HighlightPreviewPath(IServerPlayer player, List<BlockPos> path)
    {
        if (player == null) return;

        if (path == null || path.Count == 0)
        {
            sapi.World.HighlightBlocks(player, PolisConstants.PreviewPathHighlightSlotId, new List<BlockPos>());
            return;
        }

        var colors = new List<int>(path.Count);
        int pathColor = ColorUtil.ToRgba(140, 40, 200, 200);
        for (int i = 0; i < path.Count; i++)
        {
            colors.Add(pathColor);
        }

        sapi.World.HighlightBlocks(
            player,
            PolisConstants.PreviewPathHighlightSlotId,
            path,
            colors,
            EnumHighlightBlocksMode.Absolute,
            EnumHighlightShape.Arbitrary
        );
    }

    void ClearPreviewHighlight(IServerPlayer player)
    {
        if (player == null) return;
        sapi.World.HighlightBlocks(player, PolisConstants.PreviewPathHighlightSlotId, new List<BlockPos>());
    }

    static EnumAICreatureType ResolveCreatureType(EntityAgent entity)
    {
        var serverAttrs = entity?.Properties?.Server?.Attributes;
        if (serverAttrs != null)
        {
            var aicreaturetype = serverAttrs.GetString("aiCreatureType", "Humanoid");
            if (Enum.TryParse(aicreaturetype, out EnumAICreatureType ect)) return ect;
        }
        else if (entity is EntityHumanoid)
        {
            return EnumAICreatureType.Humanoid;
        }

        return EnumAICreatureType.Default;
    }

    void UpdateBotHighlights()
    {
        if (!debugEnabled) return;
        if (selectedByPlayer.Count == 0) return;

        long now = sapi.World.ElapsedMilliseconds;
        if (now < nextBotHighlightAtMs) return;
        nextBotHighlightAtMs = now + 200;

        foreach (var entry in selectedByPlayer)
        {
            if (!bots.TryGetValue(entry.Value, out var bot) || bot.Entity == null || !bot.Entity.Alive)
            {
                continue;
            }

            var player = sapi.World.PlayerByUid(entry.Key) as IServerPlayer;
            if (player == null) continue;

            var botPos = bot.Entity.ServerPos.XYZ.AsBlockPos;
            sapi.World.HighlightBlocks(
                player,
                PolisConstants.BotHighlightSlotId,
                new List<BlockPos> { botPos },
                new List<int> { ColorUtil.ToRgba(180, 80, 140, 255) },
                EnumHighlightBlocksMode.Absolute,
                EnumHighlightShape.Cube
            );
        }
    }

    bool TryResolveStack(string code, int qty, out ItemStack stack, out string error)
    {
        stack = null;
        error = null;

        var loc = new AssetLocation(code);
        var item = sapi.World.GetItem(loc);
        if (item != null)
        {
            stack = new ItemStack(item, qty);
            return true;
        }

        var block = sapi.World.GetBlock(loc);
        if (block != null)
        {
            stack = new ItemStack(block, qty);
            return true;
        }

        error = "Unknown item or block code: " + code;
        return false;
    }

    bool TryResolveEntityType(string requestedCode, out EntityProperties type, out string resolvedCode, out string error)
    {
        type = null;
        resolvedCode = null;
        error = null;

        if (!string.IsNullOrWhiteSpace(requestedCode))
        {
            type = sapi.World.GetEntityType(new AssetLocation(requestedCode));
            if (type != null)
            {
                resolvedCode = type.Code.ToShortString();
                return true;
            }

            error = "Unknown entity type: " + requestedCode;
            return false;
        }

        type = sapi.World.GetEntityType(new AssetLocation(PolisConstants.DefaultBotCode));
        if (type != null)
        {
            resolvedCode = type.Code.ToShortString();
            return true;
        }

        error = "Unknown entity type: " + PolisConstants.DefaultBotCode + ". Use /polis spawn <entitycode> (try /polis entitytypes player).";
        return false;
    }

    void LogDebug(IServerPlayer player, string message)
    {
        if (!debugEnabled) return;
        sapi.World.Logger.Notification("[polis] " + message);
        player.SendMessage(GlobalConstants.GeneralChatGroup, message, EnumChatType.Notification);
    }

    internal static string FormatPos(Vec3d pos)
    {
        if (pos == null) return "(null)";
        return string.Format(CultureInfo.InvariantCulture, "{0:0.00},{1:0.00},{2:0.00}", pos.X, pos.Y, pos.Z);
    }

    static string FormatBlockPos(BlockPos pos)
    {
        if (pos == null) return "(null)";
        return string.Format(CultureInfo.InvariantCulture, "{0},{1},{2}", pos.X, pos.Y, pos.Z);
    }

    static bool TryParseAccessFlag(string raw, out EnumBlockAccessFlags flag, out string error)
    {
        error = null;
        flag = EnumBlockAccessFlags.Use;

        if (string.IsNullOrWhiteSpace(raw)) return true;

        switch (raw.Trim().ToLowerInvariant())
        {
            case "use":
                flag = EnumBlockAccessFlags.Use;
                return true;
            case "break":
            case "build":
            case "place":
                flag = EnumBlockAccessFlags.BuildOrBreak;
                return true;
            case "traverse":
                flag = EnumBlockAccessFlags.Traverse;
                return true;
            default:
                error = "Unknown access flag. Use: use, break, build, place, traverse.";
                return false;
        }
    }

    static bool TryParseInteractMode(string raw, out EnumInteractMode mode, out string error)
    {
        error = null;
        mode = EnumInteractMode.Interact;

        if (string.IsNullOrWhiteSpace(raw)) return true;

        switch (raw.Trim().ToLowerInvariant())
        {
            case "interact":
            case "use":
            case "rightclick":
                mode = EnumInteractMode.Interact;
                return true;
            case "attack":
            case "hit":
                mode = EnumInteractMode.Attack;
                return true;
            default:
                error = "Unknown mode. Use: interact, use, rightclick, attack, hit.";
                return false;
        }
    }

    // PolisGotoAction extracted to src/Actions/Navigation/PolisGotoAction.cs

    // Block actions extracted to src/Actions/Blocks/

    // Harvest actions extracted to src/Actions/Harvesting/

    // Butcher action extracted to src/Actions/Entities/PolisButcherEntityAction.cs

    // Workstation actions extracted to src/Actions/Workstations/

    internal class BotState
    {
        /// <summary>
        /// Back-reference to the owning system (nested-class access to
        /// the outer instance methods, e.g. BeginEpisodeWhenIdle).
        /// </summary>
        public PolisSystem Owner;
        public EntityAgent Entity { get; }
        public EntityActivitySystem Activity { get; }

        // Action result tracking for testing/diagnostics
        public string LastActionName { get; private set; }
        public string LastActionType { get; set; }
        /// <summary>
        /// True while a (non-forage) job action is running — the safe-point
        /// contract of the food-pressure interrupt (PolisForageController):
        /// side-effect jobs are only preempted at their finish, which is
        /// where this flag clears (RecordActionResult).
        /// </summary>
        public bool JobRunning { get; set; }
        public bool LastActionOk { get; private set; }
        public string LastActionMsg { get; private set; }
        public long LastActionMs { get; private set; }
        public long LastActionId { get; private set; }

        /// <summary>
        /// Callback invoked when an action result is recorded.
        /// Parameters: botId, actionName, ok, msg, elapsedMs, actionId
        /// </summary>
        public Action<long, string, bool, string, long, long> OnActionRecorded { get; set; }

        /// <summary>
        /// Tracks animations started with the "loop" flag for cleanup.
        /// </summary>
        public HashSet<string> LoopingAnimations;

        public BotState(EntityAgent entity)
        {
            Entity = entity;
            Activity = new EntityActivitySystem(entity);
        }

        public void RecordActionResult(string actionName, bool ok, string msg, long elapsedMs)
        {
            LastActionName = actionName;
            LastActionOk = ok;
            LastActionMsg = msg;
            LastActionMs = elapsedMs;
            LastActionId++;

            // A "refused:foraging" record is a rejected RETRY of a job
            // that is still running — it must not clear JobRunning
            // (that would break the safe-point contract: the episode
            // would start and cancel the side-effect job).
            bool isRefusal = msg != null && msg.StartsWith("refused:foraging");
            if (!actionName.StartsWith("forage-") && !isRefusal)
            {
                JobRunning = false;
                // A side-effect job that ran to its finish is the safe
                // point where a deferred forage start proceeds.
                Owner?.BeginEpisodeWhenIdle(this, "finish");
            }

            // Notify listeners (e.g., WebSocket broadcaster)
            OnActionRecorded?.Invoke(Entity.EntityId, actionName, ok, msg, elapsedMs, LastActionId);
        }
    }

    class PreviewState
    {
        public bool Enabled;
        public bool Locked;
        public float Range;
        public Vec3d LockedTarget;
        public long NextUpdateAtMs;
    }

    internal static string DescribeTraverserMembers(object root)
    {
        if (root == null) return "(no traverser)";

        var type = root.GetType();
        var members = type.GetMembers(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)
            .Select(m => m.Name)
            .Where(n =>
                n.IndexOf("path", StringComparison.OrdinalIgnoreCase) >= 0
                || n.IndexOf("waypoint", StringComparison.OrdinalIgnoreCase) >= 0
                || n.IndexOf("node", StringComparison.OrdinalIgnoreCase) >= 0)
            .Distinct()
            .Take(30)
            .ToArray();

        if (members.Length == 0) return type.FullName + " (no path-related members found)";
        return type.FullName + " members: " + string.Join(", ", members);
    }

    internal static void TrySetTraverserDebug(object traverser, bool enabled, Action<string> debugLog)
    {
        if (traverser == null) return;

        if (TrySetBoolMember(traverser, "PathFindDebug", enabled)
            || TrySetBoolMember(traverser, "pathFindDebug", enabled)
            || TrySetBoolMember(traverser, "PathfindDebug", enabled)
            || TrySetBoolMember(traverser, "pathfindDebug", enabled))
        {
            debugLog?.Invoke("[goto] PathFindDebug " + (enabled ? "on" : "off"));
        }
    }

    static bool TrySetBoolMember(object obj, string name, bool value)
    {
        var type = obj.GetType();
        var prop = type.GetProperty(name, BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
        if (prop != null && prop.CanWrite && prop.PropertyType == typeof(bool))
        {
            prop.SetValue(obj, value);
            return true;
        }

        var field = type.GetField(name, BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
        if (field != null && field.FieldType == typeof(bool))
        {
            field.SetValue(obj, value);
            return true;
        }

        return false;
    }

    void ClearEnginePathDebugHighlight()
    {
        if (sapi?.World?.AllOnlinePlayers == null) return;

        foreach (var player in sapi.World.AllOnlinePlayers)
        {
            sapi.World.HighlightBlocks(player, PolisConstants.EnginePathDebugHighlightSlotId, new List<BlockPos>());
        }
    }

    internal static bool TryExtractPathFromTraverser(object traverser, out List<BlockPos> blocks, out int rawCount, out string source)
    {
        blocks = null;
        rawCount = 0;
        source = null;
        if (traverser == null) return false;

        if (TryGetPathEnumerable(traverser, out var enumerable, out source))
        {
            if (TryCollectPath(enumerable, out blocks, out rawCount)) return true;
        }

        return TryScanForPath(traverser, out blocks, out rawCount, out source);
    }

    static bool TryCollectPath(IEnumerable enumerable, out List<BlockPos> blocks, out int rawCount)
    {
        blocks = null;
        rawCount = 0;
        if (enumerable == null) return false;

        var collected = new List<BlockPos>();
        int iter = 0;
        const int maxScan = 5000;

        foreach (var node in enumerable)
        {
            if (iter++ > maxScan) break;
            if (TryGetNodePos(node, out var pos))
            {
                collected.Add(pos);
            }
        }

        rawCount = collected.Count;
        if (collected.Count == 0) return false;

        if (collected.Count > PolisConstants.MaxPathHighlights)
        {
            var step = Math.Max(1, collected.Count / PolisConstants.MaxPathHighlights);
            var reduced = new List<BlockPos>();
            for (int i = 0; i < collected.Count; i += step)
            {
                reduced.Add(collected[i]);
            }
            collected = reduced;
        }

        blocks = collected;
        return true;
    }

    static bool TryGetPathEnumerable(object root, out IEnumerable enumerable, out string source)
    {
        enumerable = null;
        source = null;
        if (root == null) return false;

        if (root is IEnumerable direct && root is not string)
        {
            enumerable = direct;
            source = root.GetType().Name;
            return true;
        }

        object pathObj = GetMemberValue(root, "Path")
            ?? GetMemberValue(root, "path")
            ?? GetMemberValue(root, "PathNodes")
            ?? GetMemberValue(root, "pathNodes")
            ?? GetMemberValue(root, "DataPath")
            ?? GetMemberValue(root, "dataPath")
            ?? GetMemberValue(root, "CurrentPath")
            ?? GetMemberValue(root, "currentPath")
            ?? GetMemberValue(root, "Waypoints")
            ?? GetMemberValue(root, "waypoints")
            ?? GetMemberValue(root, "WaypointPath")
            ?? GetMemberValue(root, "waypointPath")
            ?? GetMemberValue(root, "PathWaypoints")
            ?? GetMemberValue(root, "pathWaypoints");

        if (pathObj is IEnumerable pathEnumerable && pathObj is not string)
        {
            enumerable = pathEnumerable;
            source = "direct:" + root.GetType().Name;
            return true;
        }

        object nested = GetMemberValue(root, "pathTraverser")
            ?? GetMemberValue(root, "PathTraverser")
            ?? GetMemberValue(root, "pathfinder")
            ?? GetMemberValue(root, "pathFinder")
            ?? GetMemberValue(root, "Pathfinder")
            ?? GetMemberValue(root, "pathfindSystem")
            ?? GetMemberValue(root, "PathfindSystem");

        if (nested != null)
        {
            if (TryGetPathEnumerable(nested, out enumerable, out var nestedSource))
            {
                source = root.GetType().Name + "->" + nestedSource;
                return true;
            }
        }

        return false;
    }

    static bool TryScanForPath(object root, out List<BlockPos> blocks, out int rawCount, out string source)
    {
        blocks = null;
        rawCount = 0;
        source = null;
        if (root == null) return false;

        var visited = new HashSet<object>(ReferenceEqualityComparer.Instance);
        var queue = new Queue<(object obj, string path, int depth)>();
        queue.Enqueue((root, root.GetType().Name, 0));
        visited.Add(root);

        List<BlockPos> bestBlocks = null;
        int bestScore = int.MinValue;
        int bestRawCount = 0;
        string bestSource = null;

        const int maxDepth = 3;

        while (queue.Count > 0)
        {
            var (obj, path, depth) = queue.Dequeue();
            foreach (var member in GetMemberValues(obj))
            {
                if (member.Value == null || member.Value is string) continue;

                if (member.Value is IEnumerable enumerable && member.Value is not string)
                {
                    if (TryCollectPath(enumerable, out var candidate, out var count))
                    {
                        int score = count;
                        if (member.Name.IndexOf("path", StringComparison.OrdinalIgnoreCase) >= 0) score += 10000;
                        if (member.Name.IndexOf("waypoint", StringComparison.OrdinalIgnoreCase) >= 0) score += 10000;
                        if (score > bestScore)
                        {
                            bestScore = score;
                            bestRawCount = count;
                            bestBlocks = candidate;
                            bestSource = path + "." + member.Name + ":" + member.Value.GetType().Name;
                        }
                    }
                }

                if (depth >= maxDepth) continue;
                if (member.Value is IEnumerable) continue;

                if (IsSkippableType(member.Value.GetType())) continue;
                if (!visited.Add(member.Value)) continue;

                queue.Enqueue((member.Value, path + "." + member.Name, depth + 1));
            }
        }

        if (bestBlocks == null || bestBlocks.Count == 0) return false;

        blocks = bestBlocks;
        rawCount = bestRawCount;
        source = bestSource ?? "scan";
        return true;
    }

    static IEnumerable<(string Name, object Value)> GetMemberValues(object obj)
    {
        if (obj == null) yield break;
        var type = obj.GetType();
        var flags = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;

        foreach (var field in type.GetFields(flags))
        {
            object value = null;
            try { value = field.GetValue(obj); }
            catch { }
            yield return (field.Name, value);
        }

        foreach (var prop in type.GetProperties(flags))
        {
            if (!prop.CanRead) continue;
            if (prop.GetIndexParameters().Length > 0) continue;
            object value = null;
            try { value = prop.GetValue(obj); }
            catch { }
            yield return (prop.Name, value);
        }
    }

    static bool IsSkippableType(Type type)
    {
        if (type == null) return true;
        if (type.IsPrimitive || type.IsEnum) return true;
        if (type == typeof(string)) return true;
        if (type == typeof(decimal)) return true;
        return false;
    }

    static object GetMemberValue(object obj, string name)
    {
        if (obj == null) return null;
        var type = obj.GetType();

        var prop = type.GetProperty(name, BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
        if (prop != null && prop.CanRead)
        {
            try { return prop.GetValue(obj); } catch { }
        }

        var field = type.GetField(name, BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
        if (field != null)
        {
            try { return field.GetValue(obj); } catch { }
        }

        return null;
    }

    static bool TryGetNodePos(object node, out BlockPos pos)
    {
        pos = null;
        if (node == null) return false;

        if (node is BlockPos bp)
        {
            pos = bp.Copy();
            return true;
        }

        if (node is Vec3d v3d)
        {
            pos = v3d.AsBlockPos;
            return true;
        }

        if (node is Vec3f v3f)
        {
            pos = new BlockPos((int)v3f.X, (int)v3f.Y, (int)v3f.Z);
            return true;
        }

        if (node is Vec3i v3i)
        {
            pos = new BlockPos(v3i.X, v3i.Y, v3i.Z);
            return true;
        }

        object candidate = GetMemberValue(node, "Pos") ?? GetMemberValue(node, "Position") ?? GetMemberValue(node, "pos") ?? GetMemberValue(node, "position");
        if (candidate is BlockPos bp2)
        {
            pos = bp2.Copy();
            return true;
        }
        if (candidate is Vec3d v3d2)
        {
            pos = v3d2.AsBlockPos;
            return true;
        }
        if (candidate is Vec3f v3f2)
        {
            pos = new BlockPos((int)v3f2.X, (int)v3f2.Y, (int)v3f2.Z);
            return true;
        }
        if (candidate is Vec3i v3i2)
        {
            pos = new BlockPos(v3i2.X, v3i2.Y, v3i2.Z);
            return true;
        }

        if (TryGetNumeric(node, "x", out var x) && TryGetNumeric(node, "y", out var y) && TryGetNumeric(node, "z", out var z))
        {
            pos = new BlockPos((int)Math.Round(x), (int)Math.Round(y), (int)Math.Round(z));
            return true;
        }
        if (TryGetNumeric(node, "X", out x) && TryGetNumeric(node, "Y", out y) && TryGetNumeric(node, "Z", out z))
        {
            pos = new BlockPos((int)Math.Round(x), (int)Math.Round(y), (int)Math.Round(z));
            return true;
        }

        return false;
    }

    static bool TryGetNumeric(object obj, string name, out double value)
    {
        value = 0;
        if (obj == null) return false;

        var type = obj.GetType();
        var prop = type.GetProperty(name, BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
        if (prop != null)
        {
            object propVal = null;
            try { propVal = prop.GetValue(obj); } catch { }
            if (propVal != null && TryConvertNumber(propVal, out value)) return true;
        }

        var field = type.GetField(name, BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
        if (field != null)
        {
            object fieldVal = null;
            try { fieldVal = field.GetValue(obj); } catch { }
            if (fieldVal != null && TryConvertNumber(fieldVal, out value)) return true;
        }

        return false;
    }

    static bool TryConvertNumber(object value, out double result)
    {
        result = 0;
        switch (value)
        {
            case int i: result = i; return true;
            case float f: result = f; return true;
            case double d: result = d; return true;
            case long l: result = l; return true;
            case short s: result = s; return true;
            case byte b: result = b; return true;
            default:
                return false;
        }
    }

    sealed class ReferenceEqualityComparer : IEqualityComparer<object>
    {
        public static readonly ReferenceEqualityComparer Instance = new ReferenceEqualityComparer();

        public new bool Equals(object x, object y) => ReferenceEquals(x, y);
        public int GetHashCode(object obj) => System.Runtime.CompilerServices.RuntimeHelpers.GetHashCode(obj);
    }
}
