using System;
using System.Collections.Generic;
using System.Linq;
using System.Globalization;
using System.Reflection;
using System.Text.Json;
using Vintagestory.API.Common;
using Vintagestory.API.Common.Entities;
using Vintagestory.API.Config;
using Vintagestory.API.Datastructures;
using Vintagestory.API.MathTools;
using Vintagestory.API.Server;
using Vintagestory.Essentials;
using Vintagestory.GameContent;
using Polis.Core;
using Polis.Actions.Navigation;
using Polis.Actions.Blocks;
using Polis.Actions.Harvesting;
using Polis.Actions.Entities;
using Polis.Actions.Workstations;
using Polis.Actions.Inventory;
using Polis.Helpers;

/// <summary>
/// Partial class containing all HTTP test harness command handlers.
/// These methods handle commands from the poliscli.py and test harness.
/// </summary>
public partial class PolisSystem
{
    // ---- god mode: keep flagged entities effectively invulnerable ----
    // (harness aid so test bots survive mobs over long unattended runs;
    //  not persisted -- the driver re-issues `godmode on` at boot)
    internal readonly HashSet<long> godModeEntities = new HashSet<long>();
    readonly Dictionary<long, float> godModeOrigMax = new Dictionary<long, float>();
    const float GodModeMaxHealth = 100000f;

    void GodModeOnTick(float dt)
    {
        if (godModeEntities.Count == 0) return;
        foreach (var id in godModeEntities)
        {
            Entity ent = null;
            if (bots.TryGetValue(id, out var bs) && bs?.Entity != null) ent = bs.Entity;
            if (ent == null) ent = sapi?.World?.GetEntityById(id);
            if (ent == null || !ent.Alive) continue;
            var h = ent.WatchedAttributes.GetTreeAttribute("health");
            if (h == null) continue;
            h.SetFloat("maxhealth", GodModeMaxHealth);
            h.SetFloat("currenthealth", GodModeMaxHealth);
        }
    }

    PolisTestHarness.CommandResult ExecuteGodModeCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        if (args.Length < 1)
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Usage: godmode <on|off> [entityId]" };
        bool on = args[0].Equals("on", StringComparison.OrdinalIgnoreCase);
        long? singleId = (args.Length > 1 && long.TryParse(args[1], out var bid)) ? (long?)bid : null;

        var targets = new List<(string Label, Entity E, long Id)>();
        if (singleId != null)
        {
            var e = (bots.TryGetValue(singleId.Value, out var bs1) && bs1?.Entity != null) ? bs1.Entity : sapi?.World?.GetEntityById(singleId.Value);
            if (e == null) return new PolisTestHarness.CommandResult { Ok = false, Message = "Entity " + singleId + " not found" };
            targets.Add(("entity#" + singleId, e, singleId.Value));
        }
        else
        {
            foreach (var kv in bots) if (kv.Value?.Entity != null) targets.Add(("bot#" + kv.Key, kv.Value.Entity, kv.Key));
            var lp = sapi?.Server?.Players?.FirstOrDefault(p => p?.Entity != null);
            if (lp != null) targets.Add((lp.PlayerName + " (player)", lp.Entity, lp.Entity.EntityId));
        }
        if (targets.Count == 0)
            return new PolisTestHarness.CommandResult { Ok = false, Message = "No bots and no local player found" };

        var msgs = new List<string>();
        foreach (var t in targets)
        {
            var h = t.E.WatchedAttributes.GetTreeAttribute("health");
            float origMax = h?.GetFloat("maxhealth", 10f) ?? 10f;
            if (on)
            {
                if (!godModeEntities.Contains(t.Id)) { godModeEntities.Add(t.Id); godModeOrigMax[t.Id] = origMax; }
                if (h != null) { h.SetFloat("maxhealth", GodModeMaxHealth); h.SetFloat("currenthealth", GodModeMaxHealth); }
                string revived = "";
                if (!t.E.Alive)
                {
                    // Dead entities are skipped by GodModeOnTick, so an already
                    // dead target (e.g. a starved player on the death screen)
                    // must be revived first: force Alive and call the engine's
                    // own Revive() so clients clear the death screen.
                    t.E.Alive = true;
                    if (t.E is Vintagestory.API.Common.Entities.Entity ce) ce.Revive();
                    revived = " (revived)";
                }
                msgs.Add(t.Label + ": ON (max " + origMax.ToString("F0") + "->" + GodModeMaxHealth.ToString("F0") + ")" + revived);
            }
            else
            {
                godModeEntities.Remove(t.Id);
                float om = godModeOrigMax.TryGetValue(t.Id, out var m) ? m : 10f;
                if (h != null) { h.SetFloat("maxhealth", om); h.SetFloat("currenthealth", om); }
                msgs.Add(t.Label + ": OFF (restored max " + om.ToString("F0") + ")");
            }
        }
        return new PolisTestHarness.CommandResult { Ok = true, Message = string.Join("; ", msgs) };
    }

    /// <summary>
    /// 2026-10-06: Set a connected player's game mode server-side, mirroring the
    /// engine's own /gamemode handler (1.22.7 CmdPlayer.SetGameMode): set the
    /// mode on the player's IWorldPlayerData, adjust FreeMove/NoClip the way the
    /// engine does, then BroadcastPlayerData so the client applies it (the
    /// IWorldPlayerData contract: "if you want modify any value, also broadcast
    /// the playerdata"). Creative (2) is the proper god-mode for the HUMAN
    /// player: no hunger, no death, F3 fly/noclip -- pin-health godmode can't
    /// fly, and bots can't be creative, so both mechanisms coexist.
    /// Args: [playerNameOrUid, 0|1|2|3 or guest|survival|creative|spectator].
    /// </summary>
    PolisTestHarness.CommandResult ExecuteGamemodeCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        if (args.Length < 1)
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Usage: gamemode <player> <0|1|2|3|guest|survival|creative|spectator>" };

        // NOTE: `context` is null unless the JSON body carries a "context"
        // field - never dereference it directly.
        string who = args[0];
        var all = sapi?.Server?.Players;
        IServerPlayer target = null;
        for (int i = 0; all != null && i < all.Length; i++)
        {
            var p = all[i];
            if (p == null) continue;
            if (p.PlayerUID == who || string.Equals(p.PlayerName, who, StringComparison.OrdinalIgnoreCase))
            {
                target = p;
                break;
            }
        }
        if (target == null)
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"gamemode: no online player '{who}'" };

        string step = "";
        System.Exception ex = null;
        IWorldPlayerData wd = null;
        var old = EnumGameMode.Survival;
        var newMode = old;
        try
        {
            step = "worlddata";
            wd = target.WorldData;
            if (wd == null)
                return new PolisTestHarness.CommandResult { Ok = false, Message = "gamemode: player has no world data (never connected?)" };

            step = "read-mode";
            old = wd.CurrentGameMode;
            newMode = old;

            step = "parse";
            if (args.Length > 1)
            {
                if (int.TryParse(args[1], out int n) && Enum.IsDefined(typeof(EnumGameMode), n))
                    newMode = (EnumGameMode)n;
                else
                {
                    switch (args[1].ToLowerInvariant())
                    {
                        case "g": case "guest": newMode = EnumGameMode.Guest; break;
                        case "s": case "survival": newMode = EnumGameMode.Survival; break;
                        case "c": case "creative": newMode = EnumGameMode.Creative; break;
                        case "sp": case "spectator": newMode = EnumGameMode.Spectator; break;
                        default: return new PolisTestHarness.CommandResult { Ok = false, Message = "gamemode: invalid mode '" + args[1] + "'" };
                    }
                }
            }

            if (newMode != old)
            {
                step = "set-mode";
                // Engine-mirrored side effects of a mode switch (read the old
                // FreeMove/NoClip BEFORE mutating, as the engine handler does):
                bool oldFreeMove = wd.FreeMove;
                bool oldNoClip = wd.NoClip;
                bool newIsCreativeLike = newMode == EnumGameMode.Creative || newMode == EnumGameMode.Spectator;
                wd.CurrentGameMode = newMode; // setter also re-partitions the entity
                wd.FreeMove = (oldFreeMove && newIsCreativeLike) || newMode == EnumGameMode.Spectator;
                wd.NoClip = (oldNoClip && newIsCreativeLike) || newMode == EnumGameMode.Spectator;
                if (newMode == EnumGameMode.Survival || newMode == EnumGameMode.Guest)
                {
                    wd.MoveSpeedMultiplier = 1f;
                    wd.PickingRange = GlobalConstants.DefaultPickingRange;
                }
            }

            // Notify all clients (incl. the player itself) of the modified data.
            step = "broadcast";
            target.BroadcastPlayerData(sendInventory: false);
            step = "repartition";
            target.Entity?.UpdatePartitioning();
        }
        catch (System.Exception e)
        {
            ex = e;
        }
        if (ex != null)
        {
            sapi?.Logger?.Error("[polis] gamemode failed at step '" + step + "' for " + target.PlayerName + ": " + ex);
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"gamemode: failed at '{step}': {ex.Message}" };
        }

        sapi?.Logger?.Notification($"[polis] gamemode {target.PlayerName}: {old} -> {newMode} (freeMove={wd.FreeMove}, noClip={wd.NoClip})");
        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = $"{target.PlayerName}: gamemode {old} -> {newMode} (freeMove={wd.FreeMove}, noClip={wd.NoClip})"
        };
    }

    /// <summary>
    /// Execute a command from HTTP API.
    /// </summary>
    PolisTestHarness.CommandResult ExecuteHarnessCommand(string cmd, string[] args, PolisTestHarness.CommandContext context)
    {
        var result = new PolisTestHarness.CommandResult();

        try
        {
            // Map commands to their implementations
            switch (cmd?.ToLowerInvariant())
            {
                case "spawn":
                    return ExecuteSpawnCommand(args, context);
                case "select":
                    return ExecuteSelectCommand(args, context);
                case "selectlook":
                    return ExecuteSelectLookCommand(args, context);
                case "despawn":
                    return ExecuteDespawnCommand(args, context);
                case "stop":
                    return ExecuteStopCommand(args, context);
                case "give":
                    return ExecuteGiveCommand(args, context);
                case "drop":
                    return ExecuteDropCommand(args, context);
                case "pickup":
                    return ExecutePickupCommand(args, context);
                case "goto":
                    return ExecuteGotoCommand(args, context);
                case "gotolook":
                    return ExecuteGotoLookCommand(args, context);
                case "look":
                    return ExecuteLookCommand(args, context);                case "settime":
                    return ExecuteSetTimeCommand(args, context);
                case "time":
                    return ExecuteTimeCommand(args, context);
                case "daylock":
                    return ExecuteDayLockCommand(args, context);
                case "sanity":
                case "stability":
                    return ExecuteSanityCommand(args, context);
                case "autonomy":
                    return ExecuteAutonomyCommand(args, context);
                case "activate":
                    return ExecuteActivateCommand(args, context);
                case "ignite":
                    return ExecuteIgniteCommand(args, context);
                case "interact":
                    return ExecuteInteractCommand(args, context);
                case "teststate":
                    return ExecuteTestStateCommand(args, context);
                case "bots":
                    return ExecuteBotsCommand(args, context);
                case "hunger":
                    return ExecuteHungerCommand(args, context);
                case "vitals":
                    return ExecuteVitalsCommand(args, context);
                case "eat":
                    return ExecuteEatCommand(args, context);
                case "hungerpause":
                    return ExecuteHungerPauseCommand(args, context);
                case "policy":
                    return ExecutePolicyCommand(args, context);
                case "forage":
                    return ExecuteForageCommand(args, context);
                case "feed":
                    return ExecuteFeedCommand(args, context);
                case "takefrom":
                    return ExecuteTakeFromCommand(args, context);
                case "putinto":
                    return ExecutePutIntoCommand(args, context);
                case "mine":
                    return ExecuteMineCommand(args, context);
                case "chop":
                    return ExecuteMineCommand(args, context, "chop");
                case "break":
                    return ExecuteBreakCommand(args, context);
                case "harvest":
                    return ExecuteHarvestCommand(args, context);
                case "pick":
                    return ExecutePickCommand(args, context);
                case "harvestcrop":
                    return ExecuteHarvestCropCommand(args, context);
                case "grind":
                    return ExecuteGrindCommand(args, context);
                case "press":
                    return ExecutePressCommand(args, context);
                case "butcher":
                    return ExecuteButcherCommand(args, context);
                case "clayform":
                    return ExecuteClayFormCommand(args, context);
                case "knap":
                    return ExecuteKnapCommand(args, context);
                case "craft":
                    return ExecuteCraftCommand(args, context);
                case "seal":
                    return ExecuteSealCommand(args, context);
                case "forge-heat":
                    return ExecuteForgeHeatCommand(args, context);
                case "anvil-smith":
                    return ExecuteAnvilSmithCommand(args, context);
                case "anvil-state":
                    return ExecuteAnvilStateCommand(args, context);
                case "loot":
                    return ExecuteLootCommand(args, context);
                case "possess":
                    return ExecutePossessCommand(args, context);
                case "unpossess":
                    return ExecuteUnpossessCommand(args, context);
                case "setcontrols":
                    return ExecuteSetControlsCommand(args, context);
                case "spawnentity":
                    return ExecuteSpawnEntityCommand(args, context);
                case "killentity":
                    return ExecuteKillEntityCommand(args, context);
                case "respawn":
                    return ExecuteRespawnCommand(args, context);
                case "godmode":
                    return ExecuteGodModeCommand(args, context);
                case "gamemode":
                    return ExecuteGamemodeCommand(args, context);
                case "animate":
                    return ExecuteAnimateCommand(args, context);
                case "teleport":
                    return ExecuteTeleportCommand(args, context);
                case "place":
                    return ExecutePlaceCommand(args, context);
                case "setblock":
                    return ExecuteSetBlockCommand(args, context);
                case "ripen":
                    return ExecuteRipenCommand(args, context);
                case "equip":
                    return ExecuteEquipCommand(args, context);
                case "scan":
                    return ExecuteScanCommand(args, context);
                case "verify":
                    return ExecuteVerifyCommand(args, context);
                case "container-register":
                    return ExecuteContainerRegisterCommand(args, context);
                case "container-list":
                    return ExecuteContainerListCommand(args, context);
                case "container-remove":
                    return ExecuteContainerRemoveCommand(args, context);
                case "container-contents":
                    return ExecuteContainerContentsCommand(args, context);
                case "container-set":
                    return ExecuteContainerSetCommand(args, context);
                case "zone-define":
                    return ExecuteZoneDefineCommand(args, context);
                case "zone-remove":
                    return ExecuteZoneRemoveCommand(args, context);
                case "zone-list":
                    return ExecuteZoneListCommand(args, context);
                case "zone-check":
                    return ExecuteZoneCheckCommand(args, context);
                case "zone-rename":
                    return ExecuteZoneRenameCommand(args, context);
                case "crucible-fire":
                    return ExecuteCrucibleFireCommand(args, context);
                case "crucible-insert":
                    return ExecuteCrucibleInsertCommand(args, context);
                case "crucible-fuel":
                    return ExecuteCrucibleFuelCommand(args, context);
                case "crucible-take":
                    return ExecuteCrucibleTakeCommand(args, context);
                case "crucible-pour":
                    return ExecuteCruciblePourCommand(args, context);
                case "zone-show":
                    return ExecuteZoneShowCommand(args, context);
                case "viewpoint-define":
                    return ExecuteViewpointDefineCommand(args, context);
                case "viewpoint-list":
                    return ExecuteViewpointListCommand(args, context);
                case "viewpoint-remove":
                    return ExecuteViewpointRemoveCommand(args, context);
                case "observer-screenshot":
                    return ExecuteObserverScreenshotCommand(args, context);
                case "viewpoint-screenshot":
                    return ExecuteViewpointScreenshotCommand(args, context);
                default:
                    result.Ok = false;
                    result.Message = "Unknown command: " + cmd + ". Available: spawn, select, selectlook, autonomy, despawn, stop, give, drop, pickup, goto, gotolook, look, activate, ignite, interact, teststate, bots, takefrom, putinto, mine, chop, break, harvest, pick, harvestcrop, grind, press, butcher, clayform, knap, seal, possess, unpossess, setcontrols, spawnentity, killentity, respawn, godmode, gamemode, animate, teleport, place, setblock, equip, scan, verify, ripen, container-register, container-list, container-remove, container-contents, zone-define, zone-remove, zone-list, zone-check, zone-rename, zone-show, viewpoint-define, viewpoint-list, viewpoint-remove, observer-screenshot, viewpoint-screenshot, vitals, crucible-fire, crucible-insert, crucible-fuel, crucible-take, crucible-pour";
                    break;
            }
        }
        catch (Exception ex)
        {
            result.Ok = false;
            result.Message = $"Command execution error: {ex.Message}";
        }

        return result;
    }

    PolisTestHarness.CommandResult ExecuteSpawnCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        // Spawn at world spawn or specified coords, optionally with explicit entity code
        var spawn = sapi.World.DefaultSpawnPosition.XYZ;
        double x = spawn.X, y = spawn.Y, z = spawn.Z;
        IServerPlayer contextPlayer = null;

        if (context != null && !string.IsNullOrWhiteSpace(context.PlayerUid))
        {
            if (!TryGetContextPlayer(context, out contextPlayer, out var ctxError))
            {
                return new PolisTestHarness.CommandResult { Ok = false, Message = ctxError };
            }

            var basePos = contextPlayer.Entity.ServerPos.XYZ;
            x = basePos.X;
            y = basePos.Y;
            z = basePos.Z;
        }

        if (context?.SpawnOffset != null)
        {
            if (contextPlayer == null)
            {
                return new PolisTestHarness.CommandResult { Ok = false, Message = "spawnOffset requires playerUid" };
            }

            if (!TryParseOffset(context.SpawnOffset, out var offset, out var offsetError))
            {
                return new PolisTestHarness.CommandResult { Ok = false, Message = offsetError };
            }

            x += offset.X;
            y += offset.Y;
            z += offset.Z;
        }

        // Determine profession: from args[0] if it matches a profession name, or from context
        string professionName = null;
        string requestedCode = null;

        if (args.Length == 1)
        {
            if (PolisProfessions.All.ContainsKey(args[0]))
                professionName = args[0];
            else
                requestedCode = args[0];
        }
        else if (args.Length == 3)
        {
            if (!double.TryParse(args[0], out x) || !double.TryParse(args[1], out y) || !double.TryParse(args[2], out z))
            {
                return new PolisTestHarness.CommandResult { Ok = false, Message = "Invalid coordinates" };
            }
        }
        else if (args.Length == 4)
        {
            if (PolisProfessions.All.ContainsKey(args[0]))
                professionName = args[0];
            else
                requestedCode = args[0];
            if (!double.TryParse(args[1], out x) || !double.TryParse(args[2], out y) || !double.TryParse(args[3], out z))
            {
                return new PolisTestHarness.CommandResult { Ok = false, Message = "Invalid coordinates" };
            }
        }
        else if (args.Length != 0)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Usage: spawn [profession|entityCode] [x y z]" };
        }

        // Context profession overrides if no profession from args
        if (professionName == null && requestedCode == null && !string.IsNullOrEmpty(context?.Profession))
        {
            if (PolisProfessions.All.ContainsKey(context.Profession))
                professionName = context.Profession;
        }

        // Default profession when no entity code specified
        if (professionName == null && requestedCode == null)
        {
            professionName = PolisProfessions.DefaultProfession;
        }

        if (!TryResolveEntityType(requestedCode, out var entityType, out var resolvedCode, out var errorText))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = errorText };
        }

        var entity = sapi.World.ClassRegistry.CreateEntity(entityType) as EntityAgent;
        if (entity == null)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Failed to create entity" };
        }

        entity.ServerPos.SetPos(x, y, z);
        if (contextPlayer != null)
        {
            entity.ServerPos.Dimension = contextPlayer.Entity.ServerPos.Dimension;
            entity.ServerPos.Yaw = contextPlayer.Entity.ServerPos.Yaw;
        }
        entity.Pos.SetFrom(entity.ServerPos);
        sapi.World.SpawnEntity(entity);

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

        // Add to persistent registry - use context player as owner if available;
        // else the single online player (a harness-spawned bot with owner
        // "harness" is unusable by every owner-scoped action: PlayerByUid
        // never resolves a harness pseudo-uid).
        var ownerUid = contextPlayer?.PlayerUID
            ?? sapi.Server?.Players?.FirstOrDefault(p => p?.Entity != null)?.PlayerUID
            ?? "harness";
        globalData.Bots[entity.EntityId] = new BotRecord
        {
            EntityId = entity.EntityId,
            OwnerUid = ownerUid,
            Name = $"Bot {entity.EntityId}",
            LastKnownPos = entity.ServerPos.XYZ.Clone(),
            IsLoaded = true,
            EntityCode = resolvedCode,
            Profession = professionName
        };

        entity.WatchedAttributes.SetString("polisOwnerUid", ownerUid);
        entity.WatchedAttributes.SetString("polisName", $"Bot {entity.EntityId}");

        // Emit bot_spawned event
        var profLabel = professionName != null ? $", profession={professionName}" : "";
        testHarness?.Broadcaster?.QueueEvent("bot_spawned", PolisLogLevel.Normal, new
        {
            botId = entity.EntityId,
            pos = new[] { x, y, z },
            type = resolvedCode,
            profession = professionName,
            source = "spawn_command"
        });

        // 2026-10-10: the spawn reply now carries the resulting headcount
        // - the 27B brain recruited ~18 laborers in one session because a
        // bare "Spawned bot #N" reply gave it no feedback on how big the
        // crew was getting. The number is the throttle signal.
        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = $"Spawned bot #{entity.EntityId} ({resolvedCode}{profLabel}) - roster now {globalData.Bots.Count} bots",
            Data = new { id = entity.EntityId, code = resolvedCode, pos = new[] { x, y, z }, profession = professionName, roster = globalData.Bots.Count }
        };
    }

    PolisTestHarness.CommandResult ExecuteSelectCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        if (args.Length < 1 || !long.TryParse(args[0], out var botId))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Usage: select <botId>" };
        }

        if (!bots.ContainsKey(botId))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"Bot {botId} not found" };
        }

        // Store selection under player UID if available, otherwise "harness" pseudo-player
        var key = !string.IsNullOrEmpty(context?.PlayerUid) ? context.PlayerUid : "harness";
        selectedByPlayer[key] = botId;
        return new PolisTestHarness.CommandResult { Ok = true, Message = $"Selected bot #{botId}" };
    }


    /// <summary>
    /// look: turn the player (or the selected/ given bot) to face a world position.
    /// Horizontal aim only (pitch preserved unless a 4th arg is given).
    /// Yaw convention verified 2026-09-21: forward = (sin(yaw), cos(yaw)), so
    /// yaw = atan2(dx, dz) faces +X at yaw=pi/2 (see tests/view/aim-verify).
    /// For players this sets the server pos AND sends PolisSetViewDirectionPacket
    /// (client camera follows); for bots the server pos IS the rendered state.
    /// </summary>
    // World-clock control for deterministic lighting (photography, vision experiments).
    // NOTE: IGameCalendar.SetTimeSpeedModifier sets the speed to the SUM of all modifiers
    // (an empty set would freeze the clock), so the polis-harness modifier is never removed;
    // restore vanilla with: settime 1.
    // NOTE2 (measured 2026-09-26): the world carries an inherent base of 60 that is added
    // to the named modifiers (ours=6000 observed SpeedOfTime 6060), and negative modifiers
    // clamp to 0 — so the speed knob alone cannot freeze the clock (sum can never be < 60
    // ... 60+0). factor 1 yields ~2x the vanilla 48-min day; factor 0 (ours=0, sum 60)
    // is the true vanilla. Daylock (PolisSystem.DaylockTick) therefore
    // fast-forwards with the modifier and then freezes via the concrete
    // Vintagestory.Common.GameCalendar: CalendarSpeedMul = 0 (true stop: no
    // time, no date). NEVER call GameCalendar.SetDayTime in a tick loop —
    // it corrupts the date counter (+years per minute, observed 2026-09-26).
    PolisTestHarness.CommandResult ExecuteSetTimeCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        const float baseSpeed = 60f; // vanilla default SpeedOfTime (48-min day with CalendarSpeedMul 0.5)
        if (args == null || args.Length < 1 || !double.TryParse(args[0], NumberStyles.Float, CultureInfo.InvariantCulture, out var factor))
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Usage: settime <factor>  (1 = vanilla 48-min day; 10 = ~5-min day)" };
        if (factor < 1)
            return new PolisTestHarness.CommandResult { Ok = false, Message = "factor must be >= 1 (a lower sum than the vanilla base would freeze the clock)" };
        var cal = sapi.World.Calendar;
        float prev = cal.SpeedOfTime;
        cal.SetTimeSpeedModifier("polis-harness", baseSpeed * (float)factor);
        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = $"time speed factor set to {factor} (speed {prev} -> {cal.SpeedOfTime})"
        };
    }

    PolisTestHarness.CommandResult ExecuteTimeCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        var cal = sapi.World.Calendar;
        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = cal.PrettyDate(),
            Data = new
            {
                date = cal.PrettyDate(),
                hourOfDay = cal.HourOfDay,
                fullHour = cal.FullHourOfDay,
                totalDays = cal.TotalDays,
                speedOfTime = cal.SpeedOfTime,
                seasonRel = cal.YearRel,
                moonPhase = (int)cal.MoonPhaseExact
            }
        };
    }

    PolisTestHarness.CommandResult ExecuteDayLockCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        var sub = (args != null && args.Length > 0 ? args[0] : "status").ToLowerInvariant();
        var cal = sapi?.World?.Calendar;
        float hour = cal != null ? (float)cal.HourOfDay : -1f;
        if (sub == "on")
        {
            if (cal == null) return new PolisTestHarness.CommandResult { Ok = false, Message = "no world loaded" };
            int s = 3333, e = 6667;
            if (args.Length >= 3 && int.TryParse(args[1], out var a) && int.TryParse(args[2], out var b))
            {
                s = Math.Max(0, Math.Min(9999, a));
                e = Math.Max(0, Math.Min(9999, b));
            }
            if (e <= s) e = (s + 1 <= 9999) ? s + 1 : 1;
            daylockWinStart = s; daylockWinEnd = e;
            daylockOn = true; daylockFrozen = false;
            cal.SetTimeSpeedModifier("polis-harness", 6000f);
            return new PolisTestHarness.CommandResult
            {
                Ok = true,
                Message = $"daylock: fast-forwarding; will freeze once the clock enters {s/10000f*24f:F1}-{e/10000f*24f:F1}h",
                Data = new { hourOfDay = (double)cal.HourOfDay, speedOfTime = (double)cal.SpeedOfTime, window = new { start = s, end = e } }
            };
        }
        if (sub == "off")
        {
            daylockOn = false; daylockFrozen = false;
            // base 60 is inherent (SpeedOfTime = 60 + named modifiers);
            // ours=0 restores the vanilla 48-min day, and the calendar
            // speed multiplier goes back to the vanilla 0.5 (daylock set 0).
            cal?.SetTimeSpeedModifier("polis-harness", 0f);
            if (cal is Vintagestory.Common.GameCalendar gcal)
                gcal.CalendarSpeedMul = 0.5f;
            return new PolisTestHarness.CommandResult { Ok = true, Message = "daylock off: vanilla 48-min day restored" };
        }
        double? so = cal != null ? (double)cal.SpeedOfTime : (double?)null;
        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = daylockOn ? $"daylock ACTIVE (frozen={daylockFrozen})" : "daylock inactive",
            Data = new
            {
                hourOfDay = (double)hour,
                speedOfTime = so,
                on = daylockOn, frozen = daylockFrozen,
                window = new { start = daylockWinStart, end = daylockWinEnd }
            }
        };
    }

    // ---- temporal stability (1.22's "sanity" meter) ---------------------
    // The engine's SystemTemporalStability (Vintagestory.GameContent) keeps a
    // per-player 0..1 value in the watched attribute "temporalStability"
    // (the blue gear above the hotbar). It drains in temporally-unstable
    // areas (~1%/7.5s), drains fast near temporal rifts (~3%/s), recovers in
    // stable areas (~1%/4s), and is clamped by an active temporal storm
    // (value <= 1 - glitchStrength). At 0 the player enters the "Rust
    // World" (unavoidable damage, glitch overlay, hallucination spawns).
    // Storms and rifts are scheduled on calendar days, so under a FROZEN
    // clock (daylock) an active storm never ends and spawned rifts never
    // expire (DieAtTotalHours is a calendar time that never arrives) — the
    // state our world fell into: meter at 0, glitch overlay, rifts piling
    // up. This command is the godmode/daylock-style lever: query the meter,
    // pin a value (re-asserted every second), and switch storms/rifts off
    // (persisted in the world config AND cleared live + broadcast, so no
    // restart is needed to see the screen clear).
    internal double sanityPin = -1;   // -1 = not pinned; else the value re-asserted below
    internal string sanityPinUid;
    float sanityAccum;

    internal void SanityOnTick(float dt)
    {
        if (sanityPin < 0 || sanityPinUid == null || sapi?.World == null) return;
        sanityAccum += dt;
        if (sanityAccum < 1f) return;
        sanityAccum = 0;
        var p = sapi.World.PlayerByUid(sanityPinUid);
        if (p?.Entity == null) return;
        SetStability(p.Entity, (float)sanityPin);
    }

    static double GetStability(Entity e)
    {
        if (e == null) return -1;
        if (e.WatchedAttributes is TreeAttribute t)
            return t.GetDouble("temporalStability", 1.0);
        return 1.0;
    }

    static void SetStability(Entity e, double v)
    {
        if (e == null) return;
        v = Math.Max(0, Math.Min(1, v));
        if (e.WatchedAttributes is TreeAttribute t)
            t.SetDouble("temporalStability", v);
    }

    static void SetPrivate(object o, string field, object value)
    {
        o.GetType().GetField(field, BindingFlags.NonPublic | BindingFlags.Instance)?.SetValue(o, value);
    }

    PolisTestHarness.CommandResult ExecuteSanityCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        var world = sapi?.World;
        if (world == null) return new PolisTestHarness.CommandResult { Ok = false, Message = "no world loaded" };

        string sub = (args != null && args.Length > 0 ? args[0] : "status").ToLowerInvariant();

        var sys = sapi.ModLoader.GetModSystem<SystemTemporalStability>(true);
        var riftSys = sapi.ModLoader.GetModSystem<ModSystemRifts>(true);
        if (sys == null) return new PolisTestHarness.CommandResult { Ok = false, Message = "temporal-stability system not available (is temporalStability enabled?)" };

        var storm = sys.StormData;
        string cfgStorms = world.Config.GetString("temporalStorms", (string)null);
        string cfgRifts = world.Config.GetString("temporalRifts", (string)null);
        bool cfgEnabled = world.Config.GetBool("temporalStability", true);

        if (sub == "status" || sub == "get")
        {
            var players = new List<object>();
            var playerLines = new List<string>();
            foreach (var p in world.AllOnlinePlayers)
            {
                players.Add(new
                {
                    name = p.PlayerName,
                    uid = p.PlayerUID,
                    stability = (double)GetStability(p.Entity),
                    gamemode = (int)p.WorldData.CurrentGameMode
                });
                playerLines.Add($"{p.PlayerName} {(double)GetStability(p.Entity):P0}");
            }
            var riftCount = riftSys?.riftsById.Count ?? -1;
            string msg = "temporal stability: " +
                (playerLines.Count == 0 ? "no players online" : string.Join(" | ", playerLines)) +
                $" | storm active={storm.nowStormActive} glitch={storm.stormGlitchStrength:F2} next@{storm.nextStormTotalDays:F1}d"
                + $" | rifts={riftCount} (config: storms={cfgStorms ?? "n/a"} rifts={cfgRifts ?? "n/a"} system={cfgEnabled})"
                + (sanityPin >= 0 ? $" | PIN on ({sanityPinUid} at {sanityPin:F2})" : "");
            return new PolisTestHarness.CommandResult
            {
                Ok = true,
                Message = msg,
                Data = new
                {
                    players,
                    storm = new { active = storm.nowStormActive, glitchStrength = (double)storm.stormGlitchStrength, nextStormTotalDays = storm.nextStormTotalDays, nextStorm = storm.nextStormStrength.ToString() },
                    rifts = new { count = (long)riftCount, mode = cfgRifts },
                    config = new { temporalStability = cfgEnabled, temporalStorms = cfgStorms, temporalRifts = cfgRifts },
                    pin = new { on = sanityPin >= 0, value = (double)sanityPin, uid = sanityPinUid }
                }
            };
        }

        if (sub == "off" || sub == "unpin")
        {
            sanityPin = -1; sanityPinUid = null;
            return new PolisTestHarness.CommandResult { Ok = true, Message = "stability pin released (the area/storm dynamics drive the meter again)" };
        }

        if (sub == "storms")
        {
            string preset = (args.Length > 1 ? args[1] : "").ToLowerInvariant();
            if (preset == "" || preset == "status")
                return new PolisTestHarness.CommandResult { Ok = false, Message = "Usage: sanity storms <off|veryrare|rare|sometimes|often>  (config is persisted; 'off' also clears the live storm immediately)" };
            // persist (survives restart) + runtime (affects the live system)
            sapi.WorldManager.SaveGame.WorldConfiguration.SetString("temporalStorms", preset);
            world.Config.SetString("temporalStorms", preset);
            SetPrivate(sys, "stormsEnabled", preset != "off");
            SetPrivate(sys, "worldConfigStorminess", preset);
            if (preset == "off")
            {
                // zero the live storm state, persist it, and push it to the
                // clients (their glitch overlay follows this packet)
                storm.nowStormActive = false;
                storm.stormGlitchStrength = 0f;
                storm.stormActiveTotalDays = 0;
                storm.stormDayNotify = 99;
                storm.nextStormTotalDays = world.Calendar.TotalDays + 3650;
                sys.modGlitchStrength = 0f;
                try
                {
                    sapi.WorldManager.SaveGame.StoreData("temporalStormData",
                        Vintagestory.API.Util.SerializerUtil.Serialize<TemporalStormRunTimeData>(storm));
                    sapi.Network.GetChannel("temporalstability").BroadcastPacket(storm, Array.Empty<IServerPlayer>());
                }
                catch (Exception ex)
                {
                    return new PolisTestHarness.CommandResult { Ok = false, Message = $"storms: config set, but live clear failed: {ex.Message}" };
                }
                return new PolisTestHarness.CommandResult
                {
                    Ok = true,
                    Message = "temporal storms OFF (persisted): live storm zeroed and broadcast; a frozen clock can no longer hold a storm open. Re-enable with 'sanity storms <veryrare|rare|sometimes|often>'"
                };
            }
            return new PolisTestHarness.CommandResult
            {
                Ok = true,
                Message = $"temporal storms preset '{preset}' (persisted; scheduler resumes with the saved state)"
            };
        }

        if (sub == "rifts")
        {
            string mode = (args.Length > 1 ? args[1] : "").ToLowerInvariant();
            if (mode != "off" && mode != "invisible" && mode != "visible")
                return new PolisTestHarness.CommandResult { Ok = false, Message = "Usage: sanity rifts <off|invisible|visible>  (config is persisted; 'off' also wipes the existing rifts now)" };
            sapi.WorldManager.SaveGame.WorldConfiguration.SetString("temporalRifts", mode);
            world.Config.SetString("temporalRifts", mode);
            if (riftSys != null)
            {
                SetPrivate(riftSys, "riftsEnabled", mode != "off");
                SetPrivate(riftSys, "riftMode", mode);
                if (mode == "off")
                {
                    WipeRifts(riftSys);
                    try
                    {
                        sapi.WorldManager.SaveGame.StoreData("rifts", riftSys.riftsById);
                        sapi.Network.GetChannel("rifts").BroadcastPacket(new RiftList(), Array.Empty<IServerPlayer>());
                        sapi.Network.GetChannel("rifts").BroadcastPacket(new RiftsStatus { Enabled = false }, Array.Empty<IServerPlayer>());
                    }
                    catch (Exception ex)
                    {
                        return new PolisTestHarness.CommandResult { Ok = false, Message = $"rifts: config set, but live wipe failed: {ex.Message}" };
                    }
                }
            }
            return new PolisTestHarness.CommandResult
            {
                Ok = true,
                Message = $"temporal rifts '{mode}' (persisted)" + (mode == "off" ? "; existing rifts wiped server-side and clients told" : "; takes effect fully on next world load")
            };
        }

        if (sub == "clear")
        {
            if (riftSys == null) return new PolisTestHarness.CommandResult { Ok = false, Message = "rift system not available" };
            int before = riftSys.riftsById.Count;
            WipeRifts(riftSys);
            try
            {
                sapi.Network.GetChannel("rifts").BroadcastPacket(new RiftList(), Array.Empty<IServerPlayer>());
            }
            catch (Exception ex) { /* cosmetic only */ }
            return new PolisTestHarness.CommandResult { Ok = true, Message = $"cleared {before} temporal rift(s) (config unchanged; they may respawn while rift activity is high)" };
        }

        // default: `sanity <value 0..1> [playerUid]` — set AND pin
        if (!double.TryParse(sub, NumberStyles.Float, CultureInfo.InvariantCulture, out double v))
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Usage: sanity | sanity <0-1> [playerUid] | sanity off | sanity storms <preset> | sanity rifts <off|invisible|visible> | sanity clear" };
        string uid = args.Length > 1 ? args[1] : null;
        IPlayer target = uid != null ? world.PlayerByUid(uid) : world.AllOnlinePlayers.FirstOrDefault();
        if (target == null) return new PolisTestHarness.CommandResult { Ok = false, Message = $"no such online player: {uid ?? "(none online)"}" };
        SetStability(target.Entity, v);
        sanityPin = v; sanityPinUid = target.PlayerUID; sanityAccum = 0;
        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = $"{target.PlayerName}: temporal stability set to {v:P0} and PINNED (re-asserted every second, godmode-style). 'sanity off' releases the pin.",
            Data = new { name = target.PlayerName, uid = target.PlayerUID, stability = (double)GetStability(target.Entity), pinned = true }
        };
    }

    static void WipeRifts(ModSystemRifts r)
    {
        r.riftsById.Clear();
        if (r.ServerRifts != null) r.ServerRifts.Clear();
    }

    PolisTestHarness.CommandResult ExecuteLookCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        if (args.Length < 3)
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Usage: look <x> <y> <z> [pitch]" };
        if (!double.TryParse(args[0], out var tx) || !double.TryParse(args[1], out var ty) || !double.TryParse(args[2], out var tz))
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Invalid coordinates" };
        float? pitchOverride = args.Length >= 4 && float.TryParse(args[3], out var po) ? po : (float?)null;

        // player target
        if (!string.IsNullOrEmpty(context.PlayerUid))
        {
            var player = sapi.World.PlayerByUid(context.PlayerUid) as IServerPlayer;
            if (player?.Entity == null)
                return new PolisTestHarness.CommandResult { Ok = false, Message = "Player not found or entity not loaded" };
            var pos = player.Entity.ServerPos;
            var dx = (float)tx - (float)pos.X;
            var dz = (float)tz - (float)pos.Z;
            var yaw = (float)Math.Atan2(dx, dz);
            var pitch = pitchOverride ?? (float)pos.Pitch;
            player.Entity.TeleportTo(new EntityPos((double)pos.X, (double)pos.Y, (double)pos.Z, yaw, pitch));
            serverChannel.SendPacket(new PolisSetViewDirectionPacket { Yaw = yaw, Pitch = pitch }, player);
            return new PolisTestHarness.CommandResult
            {
                Ok = true,
                Message = $"Looking at ({tx}, {ty}, {tz}): yaw={yaw:F4} pitch={pitch:F4}",
                Data = new { yaw, pitch, target = new { tx, ty, tz } }
            };
        }

        // bot target (explicit botId or the player's selected bot)
        if (TryGetHarnessBot(context, out var bot, out var berr))
        {
            var be = bot.Entity;
            var bpos = be.ServerPos;
            var bdx = (float)tx - (float)bpos.X;
            var bdz = (float)tz - (float)bpos.Z;
            var byaw = (float)Math.Atan2(bdx, bdz);
            var bpitch = pitchOverride ?? (float)bpos.Pitch;
            be.TeleportTo(new EntityPos((double)bpos.X, (double)bpos.Y, (double)bpos.Z, byaw, bpitch));
            return new PolisTestHarness.CommandResult
            {
                Ok = true,
                Message = $"Bot {bot.Entity.EntityId} looking at ({tx}, {ty}, {tz}): yaw={byaw:F4} pitch={bpitch:F4}",
                Data = new { yaw = byaw, pitch = bpitch, target = new { tx, ty, tz } }
            };
        }

        return new PolisTestHarness.CommandResult { Ok = false, Message = "No player or bot in context" };
    }

    PolisTestHarness.CommandResult ExecuteSelectLookCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        if (!TryGetContextPlayer(context, out var player, out var error))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = error };
        }

        float range = 48f;
        if (args.Length > 0 && !float.TryParse(args[0], out range))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Usage: selectlook [range]" };
        }
        range = GameMath.Clamp(range, 2f, PolisConstants.MaxGotoLookRange);

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
            return new PolisTestHarness.CommandResult { Ok = false, Message = "No entity selected" };
        }

        var id = entSel.Entity.EntityId;
        if (!bots.ContainsKey(id))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Selected entity is not a tracked bot" };
        }

        selectedByPlayer[player.PlayerUID] = id;
        return new PolisTestHarness.CommandResult { Ok = true, Message = $"Selected bot #{id}" };
    }

    /// <summary>
    /// 2026-10-10 fix: the old version ignored its argument entirely and
    /// killed the CONTEXT bot (the caller's own body). In a live Oikistes
    /// session the agent ordered "despawn all but two"; every call answered
    /// "Despawned bot #<a different id>", and the 27B model compensated by
    /// repeatedly SPAWNING new laborers - the roster never shrank (it even
    /// killed its own body first). Now: an explicit entity id is required
    /// and matched exactly - the engine exposes no world-wide entity
    /// enumeration, so a wide sweep is taken around the registry's last
    /// known position of the requested bot (falling back to the caller's
    /// position); unknown or non-bot ids fail with a precise message so
    /// the model can report instead of compensating.
    /// Args: [entityId].
    /// </summary>
    PolisTestHarness.CommandResult ExecuteDespawnCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        if (args.Length == 0)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "despawn: usage: despawn <entityId> (bot ids from the roster/state)" };
        }
        if (!long.TryParse(args[0], out var id))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "despawn: '" + args[0] + "' is not an entity id" };
        }

        // sweep center: the requested bot's last known position, else the
        // caller's, else the player's - bots live in the settlement, so a
        // 256m disc around any of these covers the field
        Vec3d center = new Vec3d();
        bool haveCenter = false;
        if (globalData != null && globalData.Bots.TryGetValue(id, out var rec)
            && Math.Abs(rec.LastKnownPos.X) + Math.Abs(rec.LastKnownPos.Y) + Math.Abs(rec.LastKnownPos.Z) > 0.001)
        {
            center = rec.LastKnownPos;
            haveCenter = true;
        }
        if (!haveCenter && TryGetHarnessBot(context, out var cbot, out _))
        {
            var bp = cbot.Entity.ServerPos;
            center = new Vec3d(bp.X, bp.Y, bp.Z);
            haveCenter = true;
        }
        if (!haveCenter && context != null && !string.IsNullOrEmpty(context.PlayerUid))
        {
            var p = sapi.World?.PlayerByUid(context.PlayerUid);
            if (p != null && p.Entity != null)
            {
                var pp = p.Entity.ServerPos;
                center = new Vec3d(pp.X, pp.Y, pp.Z);
                haveCenter = true;
            }
        }
        if (!haveCenter)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "despawn: no reference position for a sweep (no bot registry entry, no caller, no player)" };
        }

        var victim = sapi.World != null
            ? sapi.World.GetEntitiesAround(center, 256f, 256f, e => true).FirstOrDefault(e => e != null && e.EntityId == id)
            : null;
        if (victim == null)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "despawn: no entity with id " + id + " in the world (256m sweep from " + (int)center.X + "," + (int)center.Y + "," + (int)center.Z + ")" };
        }
        var vcode = victim.Code != null ? victim.Code.ToString() : "an entity without a code";
        if (vcode != "polis:polisbot")
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "despawn: entity " + id + " is not a polis bot (it is " + vcode + ")" };
        }

        victim.Die(EnumDespawnReason.Removed);
        return new PolisTestHarness.CommandResult { Ok = true, Message = "Despawned bot #" + id };
    }

    /// <summary>
    /// 2026-10-05: Revive a dead player entity in place. When a player's health
    /// hits 0 the VS client shows a death screen and the entity is marked dead
    /// (Alive=false). `teleport` does NOT un-kill a dead player (it repositions
    /// but the death state persists), which left the test player stuck on the
    /// death screen after an over-head vantage-point screenshot. This restores
    /// the health tree to max, forces Alive, and calls the engine's own
    /// Revive() so the client clears the death screen and the player is usable
    /// again. The reliable reset the episode harness (A/B game battery) needs:
    /// a player can die mid-run and must come back without a full reconnect.
    /// Args: [optional playerUid] (context player if omitted).
    /// </summary>
    PolisTestHarness.CommandResult ExecuteRespawnCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        var uid = args.Length > 0 ? args[0] : context?.PlayerUid;
        if (string.IsNullOrEmpty(uid))
            return new PolisTestHarness.CommandResult { Ok = false, Message = "respawn: no player (no uid arg and no context player)" };

        var player = sapi.World?.PlayerByUid(uid);
        if (player == null)
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"respawn: no player with uid {uid} (not connected?)" };

        var en = player.Entity;
        if (en == null)
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"respawn: player {uid} has no entity (disconnected/despawned) - reconnect the client first" };

        bool wasAlive = en.Alive;

        // 1. Restore the health tree to max (VS decides IsDead from this).
        var ht = en.WatchedAttributes.GetTreeAttribute("health");
        float cur = 0f, max = 0f;
        if (ht != null)
        {
            cur = ht.GetFloat("curhealth", 0f);
            max = ht.GetFloat("maxhealth", 10f);
            if (max <= 0f) max = 10f;
            ht.SetFloat("maxhealth", max);
            ht.SetFloat("curhealth", max);
        }

        // 2. Force alive + call the engine's own revive (drives client sync so
        //    the death screen clears).
        en.Alive = true;
        if (en is Vintagestory.API.Common.Entities.Entity ce) ce.Revive();

        sapi.Logger.Debug($"[polis] respawn {uid}: wasAlive={wasAlive} health {cur:F1}->{max:F1}");
        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = $"Respawned {uid}: health {cur:F1}->{max:F1}, alive={wasAlive}->true"
        };
    }

    /// <summary>
    /// Oikistes autonomy level (2026-09-27): mod-owned, world-config-persisted
    /// (key `polis_oikistes_autonomy`), agent-reads / UI-and-culture-write.
    /// The decision runtime injects the current level into its context each
    /// turn AND enforces it in the execution path — the LLM never carries
    /// the policy itself. Presets are global shortcuts over a per-domain map
    /// (free / guarded / strict) so a later cultural/tech-tree system can set
    /// per-domain levels without a migration.
    /// </summary>
    PolisTestHarness.CommandResult ExecuteAutonomyCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        const string KEY = "polis_oikistes_autonomy";
        string[] presets = { "free", "guarded", "strict" };
        if (sapi.World?.Config == null)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "No world loaded" };
        }

        string sub = args.Length > 0 ? args[0].ToLowerInvariant() : "get";
        if (sub == "get")
        {
            string preset = sapi.World.Config.GetString(KEY, "guarded");
            return new PolisTestHarness.CommandResult
            {
                Ok = true,
                Message = $"autonomy: {preset}",
                Data = new { preset, key = KEY, presets }
            };
        }
        if (sub == "set")
        {
            string preset = args.Length > 1 ? args[1].ToLowerInvariant() : "";
            if (!presets.Contains(preset))
            {
                return new PolisTestHarness.CommandResult { Ok = false, Message = $"Unknown preset '{preset}' — expected: {string.Join(", ", presets)}" };
            }
            sapi.World.Config.SetString(KEY, preset);
            return new PolisTestHarness.CommandResult
            {
                Ok = true,
                Message = $"autonomy set: {preset}",
                Data = new { preset, key = KEY }
            };
        }
        return new PolisTestHarness.CommandResult { Ok = false, Message = "Usage: autonomy get | autonomy set <free|guarded|strict>" };
    }

    PolisTestHarness.CommandResult ExecuteStopCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        if (!TryGetHarnessBot(context, out var bot, out var err))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = err };
        }

        bot.Activity.CancelAll();
        return new PolisTestHarness.CommandResult { Ok = true, Message = $"Stopped bot #{bot.Entity.EntityId}" };
    }

    PolisTestHarness.CommandResult ExecuteGiveCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        if (args.Length < 1)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Usage: give <itemCode> [quantity]" };
        }

        if (!TryGetHarnessBot(context, out var bot, out var err))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = err };
        }

        var itemCode = args[0];
        int qty = args.Length > 1 && int.TryParse(args[1], out var q) ? q : 1;

        var item = ResolveItemLenient(sapi.World, itemCode);
        var block = item == null ? ResolveBlockLenient(sapi.World, itemCode) : null;

        ItemStack stack = null;
        if (item != null)
        {
            stack = new ItemStack(item, qty);
        }
        else if (block != null)
        {
            stack = new ItemStack(block, qty);
        }

        if (stack == null)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"Item/block '{itemCode}' not found" };
        }

        if (!PolisInventoryHelpers.TryInsertIntoBotInventory(bot.Entity, stack, out int moved, out string insertError, debugEnabled ? msg => sapi.Logger.Debug($"[polis] {msg}") : null))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = insertError ?? "Bot inventory full or not available" };
        }

        int remaining = qty - moved;
        string message = remaining > 0
            ? $"Gave {moved}x {itemCode} (partial, {remaining} left) to bot #{bot.Entity.EntityId}"
            : $"Gave {qty}x {itemCode} to bot #{bot.Entity.EntityId}";

        return new PolisTestHarness.CommandResult { Ok = true, Message = message };
    }

    PolisTestHarness.CommandResult ExecuteDropCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        if (!TryGetHarnessBot(context, out var bot, out var err))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = err };
        }

        int slotIndex = args.Length > 0 && int.TryParse(args[0], out var s) ? s : -1;
        int quantity = args.Length > 1 && int.TryParse(args[1], out var q) ? q : 0;

        var result = new PolisTestHarness.CommandResult();
        var action = new PolisDropItemAction(
            bot.Activity,
            slotIndex,
            quantity,
            debugEnabled ? msg => sapi.Logger.Debug($"[polis] {msg}") : null,
            (ok, msg) =>
            {
                result.Ok = ok;
                result.Message = msg;
                bot.RecordActionResult("drop", ok, msg, sapi.World.ElapsedMilliseconds);
            }
        );

        StartSingleAction(bot, "drop", action);

        // Action executes immediately in Start()
        if (string.IsNullOrEmpty(result.Message))
        {
            result.Ok = false;
            result.Message = "Action did not complete synchronously";
        }

        return result;
    }

    PolisTestHarness.CommandResult ExecutePickupCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        if (!TryGetHarnessBot(context, out var bot, out var err))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = err };
        }

        float range = args.Length > 1 && float.TryParse(args[1], out var r) ? r : 3f;

        // Find target entity
        long targetId;
        if (args.Length > 0 && long.TryParse(args[0], out var t))
        {
            targetId = t;
        }
        else
        {
            // Find nearest item entity
            var searchPos = bot.Entity.ServerPos.XYZ;
            double nearestDist = double.MaxValue;
            EntityItem nearest = null;

            foreach (var entity in sapi.World.LoadedEntities.Values)
            {
                var item = entity as EntityItem;
                if (item == null || !item.Alive) continue;

                var dist = item.ServerPos.XYZ.DistanceTo(searchPos);
                if (dist < nearestDist && dist <= range * 2)
                {
                    nearestDist = dist;
                    nearest = item;
                }
            }

            if (nearest == null)
            {
                return new PolisTestHarness.CommandResult { Ok = false, Message = "No item entity found nearby" };
            }
            targetId = nearest.EntityId;
        }

        var result = new PolisTestHarness.CommandResult();
        var action = new PolisPickupItemAction(
            bot.Activity,
            targetId,
            range,
            debugEnabled ? msg => sapi.Logger.Debug($"[polis] {msg}") : null,
            (ok, msg) =>
            {
                result.Ok = ok;
                result.Message = msg;
                bot.RecordActionResult("pickup", ok, msg, sapi.World.ElapsedMilliseconds);
            }
        );

        StartSingleAction(bot, "pickup", action);

        if (string.IsNullOrEmpty(result.Message))
        {
            result.Ok = false;
            result.Message = "Action did not complete synchronously";
        }

        return result;
    }

    PolisTestHarness.CommandResult ExecuteGotoCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        if (!TryGetHarnessBot(context, out var bot, out var err))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = err };
        }

        Vec3d target = null;
        Vec3d offset = null;
        IServerPlayer contextPlayer = null;

        if (args.Length >= 3)
        {
            if (!double.TryParse(args[0], out var x) || !double.TryParse(args[1], out var y) || !double.TryParse(args[2], out var z))
            {
                return new PolisTestHarness.CommandResult { Ok = false, Message = "Invalid coordinates" };
            }
            target = new Vec3d(x, y, z);
        }
        else if (context != null && !string.IsNullOrWhiteSpace(context.PlayerUid))
        {
            if (!TryGetContextPlayer(context, out contextPlayer, out var ctxError))
            {
                return new PolisTestHarness.CommandResult { Ok = false, Message = ctxError };
            }

            if (context.UseLookTarget)
            {
                if (!ResolveGotoLookTarget(contextPlayer, 48f, out _, out _, out var movePos, out _, out _))
                {
                    return new PolisTestHarness.CommandResult { Ok = false, Message = "No look target found" };
                }
                target = movePos;
            }
            else if (context.GotoOffset != null)
            {
                if (!TryParseOffset(context.GotoOffset, out offset, out var offsetError))
                {
                    return new PolisTestHarness.CommandResult { Ok = false, Message = offsetError };
                }
                var basePos = contextPlayer.Entity.ServerPos.XYZ;
                target = basePos.AddCopy(offset);
            }
        }

        if (target == null)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Usage: goto <x> <y> <z> (or use context with playerUid + gotoOffset/useLookTarget)" };
        }

        if (context?.GotoOffset != null && offset == null)
        {
            if (!TryParseOffset(context.GotoOffset, out offset, out var offsetError))
            {
                return new PolisTestHarness.CommandResult { Ok = false, Message = offsetError };
            }
            target = target.AddCopy(offset);
        }

        void OnResult(bool ok, string msg)
        {
            bot.RecordActionResult("goto", ok, msg, sapi.World.ElapsedMilliseconds);
        }
        var action = new PolisGotoAction(
            bot.Activity,
            target,
            true, // useAstar
            "walk", // animCode
            0.02f, // walkSpeed
            1f, // animSpeed
            debugEnabled ? msg => sapi.Logger.Debug($"[polis] {msg}") : null,
            null, // debugPath callback
            debugEnabled,
            true, // allowFallback
            OnResult
        );

        StartSingleAction(bot, "goto", action);

        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = $"Bot #{bot.Entity.EntityId} moving to ({target.X:0.0}, {target.Y:0.0}, {target.Z:0.0})"
        };
    }

    PolisTestHarness.CommandResult ExecuteGotoLookCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        if (!TryGetContextPlayer(context, out var player, out var error))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = error };
        }

        if (!TryGetHarnessBot(context, out var bot, out var botError))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = botError };
        }

        float range = 48f;
        bool astar = true;
        float speed = 0.02f;
        bool fallback = false;

        if (args.Length > 0 && !float.TryParse(args[0], out range))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Usage: gotolook [range] [astar] [speed] [fallback]" };
        }
        if (args.Length > 1 && !bool.TryParse(args[1], out astar))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Usage: gotolook [range] [astar] [speed] [fallback]" };
        }
        if (args.Length > 2 && !float.TryParse(args[2], out speed))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Usage: gotolook [range] [astar] [speed] [fallback]" };
        }
        if (args.Length > 3 && !bool.TryParse(args[3], out fallback))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Usage: gotolook [range] [astar] [speed] [fallback]" };
        }

        Vec3d moveOffset = null;
        if (context?.GotoOffset != null)
        {
            if (!TryParseOffset(context.GotoOffset, out moveOffset, out var offsetError))
            {
                return new PolisTestHarness.CommandResult { Ok = false, Message = offsetError };
            }
        }

        void OnResult(bool ok, string msg)
        {
            bot.RecordActionResult("gotolook", ok, msg, sapi.World.ElapsedMilliseconds);
        }

        var result = StartGotoLookActionWithOffset(
            player,
            bot,
            range,
            astar,
            speed,
            fallback,
            "Goto look started",
            out var movePos,
            moveOffset,
            OnResult
        );

        if (result.Status == EnumCommandStatus.Success)
        {
            return new PolisTestHarness.CommandResult
            {
                Ok = true,
                Message = $"Bot #{bot.Entity.EntityId} moving to ({movePos.X:0.0}, {movePos.Y:0.0}, {movePos.Z:0.0})"
            };
        }

        return new PolisTestHarness.CommandResult { Ok = false, Message = result.StatusMessage };
    }

    PolisTestHarness.CommandResult ExecuteActivateCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        if (!TryGetContextPlayer(context, out var player, out var ctxError))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = ctxError };
        }

        if (!TryGetHarnessBot(context, out var bot, out var err))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = err };
        }

        bool shift = args.Contains("--shift");
        args = args.Where(a => a != "--shift").ToArray();

        BlockSelection selection = null;
        BlockPos targetPos = null;

        if (args.Length == 3)
        {
            if (!double.TryParse(args[0], out var x) || !double.TryParse(args[1], out var y) || !double.TryParse(args[2], out var z))
            {
                return new PolisTestHarness.CommandResult { Ok = false, Message = "Invalid coordinates" };
            }
            targetPos = new Vec3d(x, y, z).AsBlockPos;
        }
        else if (args.Length == 0 && context.UseLookTarget)
        {
            if (!ResolveGotoLookTarget(player, 48f, out var blockSel, out _, out _, out _, out _))
            {
                return new PolisTestHarness.CommandResult { Ok = false, Message = "No look target found" };
            }

            if (blockSel?.Position == null)
            {
                return new PolisTestHarness.CommandResult { Ok = false, Message = "No block selected" };
            }

            targetPos = blockSel.Position;
            selection = blockSel;
        }
        else
        {
            return new PolisTestHarness.CommandResult
            {
                Ok = false,
                Message = "Usage: activate <x> <y> <z> (requires context.playerUid) or activate with context.useLookTarget"
            };
        }

        var block = sapi.World.BlockAccessor.GetBlock(targetPos);
        if (block == null || block.Id == 0)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "No block at target position" };
        }

        selection ??= ResolveSelection(player, targetPos, BlockFacing.NORTH);
        selection.Block = block;

        if (!TryValidateBlockTarget(
            player,
            bot,
            selection,
            targetPos,
            EnumBlockAccessFlags.Use,
            debugEnabled ? msg => LogDebug(player, msg) : null,
            out var movePos,
            out var validationError,
            bot.Entity))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = validationError.StatusMessage };
        }

        void OnGotoResult(bool ok, string msg)
        {
            if (!ok)
            {
                bot.RecordActionResult("activate", false, $"goto failed: {msg}", sapi.World.ElapsedMilliseconds);
            }
        }

        void OnActivateResult(bool ok, string msg)
        {
            bot.RecordActionResult("activate", ok, msg, sapi.World.ElapsedMilliseconds);
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
            false,
            OnGotoResult
        );
        var action = new PolisActivateBlockAction(
            targetPos,
            selection.Face,
            selection.HitPosition,
            null,
            player,
            PolisConstants.DefaultActionRange,
            debugEnabled ? msg => LogDebug(player, msg) : null,
            OnActivateResult,
            shift
        );
        StartActionSequence(bot, "activate", gotoAction, action);

        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = $"Bot #{bot.Entity.EntityId} activating block at {targetPos}"
        };
    }

    PolisTestHarness.CommandResult ExecuteIgniteCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        if (!TryGetContextPlayer(context, out var player, out var ctxError))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = ctxError };
        }

        if (!TryGetHarnessBot(context, out var bot, out var err))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = err };
        }

        BlockSelection selection = null;
        BlockPos targetPos = null;

        if (args.Length == 3)
        {
            if (!double.TryParse(args[0], out var x) || !double.TryParse(args[1], out var y) || !double.TryParse(args[2], out var z))
            {
                return new PolisTestHarness.CommandResult { Ok = false, Message = "Invalid coordinates" };
            }
            targetPos = new Vec3d(x, y, z).AsBlockPos;
        }
        else if (args.Length == 0 && context.UseLookTarget)
        {
            if (!ResolveGotoLookTarget(player, 48f, out var blockSel, out _, out _, out _, out _))
            {
                return new PolisTestHarness.CommandResult { Ok = false, Message = "No look target found" };
            }

            if (blockSel?.Position == null)
            {
                return new PolisTestHarness.CommandResult { Ok = false, Message = "No block selected" };
            }

            targetPos = blockSel.Position;
            selection = blockSel;
        }
        else
        {
            return new PolisTestHarness.CommandResult
            {
                Ok = false,
                Message = "Usage: ignite <x> <y> <z> (requires context.playerUid) or ignite with context.useLookTarget"
            };
        }

        var block = sapi.World.BlockAccessor.GetBlock(targetPos);
        if (block == null || block.Id == 0)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "No block at target position" };
        }

        // Check if block implements IIgnitable
        var ignitable = block.GetInterface<IIgnitable>(sapi.World, targetPos);
        if (ignitable == null)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"Block {block.Code} does not implement IIgnitable" };
        }

        selection ??= ResolveSelection(player, targetPos, BlockFacing.NORTH);
        selection.Block = block;

        if (!TryValidateBlockTarget(
            player,
            bot,
            selection,
            targetPos,
            EnumBlockAccessFlags.Use,
            debugEnabled ? msg => LogDebug(player, msg) : null,
            out var movePos,
            out var validationError,
            bot.Entity))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = validationError.StatusMessage };
        }

        void OnGotoResult(bool ok, string msg)
        {
            if (!ok)
            {
                bot.RecordActionResult("ignite", false, $"goto failed: {msg}", sapi.World.ElapsedMilliseconds);
            }
        }

        void OnIgniteResult(bool ok, string msg)
        {
            bot.RecordActionResult("ignite", ok, msg, sapi.World.ElapsedMilliseconds);
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
            false,
            OnGotoResult
        );
        var action = new PolisIgniteBlockAction(
            targetPos,
            selection.Face,
            bot.Entity,
            PolisConstants.DefaultActionRange,
            debugEnabled ? msg => LogDebug(player, msg) : null,
            OnIgniteResult
        );
        StartActionSequence(bot, "ignite", gotoAction, action);

        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = $"Bot #{bot.Entity.EntityId} igniting block at {targetPos}"
        };
    }

    PolisTestHarness.CommandResult ExecuteInteractCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        if (!TryGetHarnessBot(context, out var bot, out var err))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = err };
        }

        if (args.Length == 0 || !long.TryParse(args[0], out var entityId))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Usage: interact <entityId> [mode] [range]" };
        }

        string modeText = args.Length > 1 ? args[1] : "interact";
        if (!TryParseInteractMode(modeText, out var mode, out var modeError))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = modeError };
        }

        float range = PolisConstants.DefaultActionRange;
        if (args.Length > 2 && !float.TryParse(args[2], out range))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Usage: interact <entityId> [mode] [range]" };
        }

        var target = sapi.World.GetEntityById(entityId);
        if (target == null)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"Entity {entityId} not found" };
        }

        var movePos = target.ServerPos?.XYZ?.Clone();
        if (movePos == null)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Target position missing" };
        }

        var gotoAction = new PolisGotoAction(
            bot.Activity,
            movePos,
            true,
            "walk",
            0.02f,
            1f,
            debugEnabled ? msg => sapi.Logger.Debug($"[polis] {msg}") : null,
            null,
            debugEnabled,
            false
        );
        var action = new PolisInteractEntityAction(
            bot.Activity,
            entityId,
            null,
            mode,
            range,
            debugEnabled ? msg => sapi.Logger.Debug($"[polis] {msg}") : null,
            (ok, msg) => bot.RecordActionResult("interact", ok, msg, sapi.World.ElapsedMilliseconds)
        );

        StartActionSequence(bot, "interact", gotoAction, action);

        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = $"Bot #{bot.Entity.EntityId} interacting with entity {entityId} (mode={mode})"
        };
    }

    PolisTestHarness.CommandResult ExecuteTakeFromCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        // Usage: takefrom <name|x> [y z] <slotIndex> [qty]
        // Can accept either a registered container name or x y z coordinates
        if (args.Length < 2)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Usage: takefrom <name|x> [y z] <slotIndex> [qty]" };
        }

        if (!TryGetContextPlayer(context, out var contextPlayer, out var ctxError))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = ctxError };
        }

        if (!TryGetHarnessBot(context, out var bot, out var err))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = err };
        }

        BlockPos pos;
        int slotIndex;
        int qty = 0;

        // Try to parse as coordinates first (4+ args: x y z slot [qty])
        if (args.Length >= 4 && double.TryParse(args[0], out var x) && double.TryParse(args[1], out var y) && double.TryParse(args[2], out var z))
        {
            pos = new Vec3d(x, y, z).AsBlockPos;
            if (!int.TryParse(args[3], out slotIndex))
            {
                return new PolisTestHarness.CommandResult { Ok = false, Message = "Invalid slot index" };
            }
            if (args.Length > 4 && !int.TryParse(args[4], out qty))
            {
                return new PolisTestHarness.CommandResult { Ok = false, Message = "Invalid quantity" };
            }
        }
        // Otherwise try as container name (2+ args: name slot [qty])
        else
        {
            string containerName = args[0];
            if (!TryResolveContainerName(containerName, out pos, out var resolveError))
            {
                return new PolisTestHarness.CommandResult { Ok = false, Message = resolveError };
            }
            if (!int.TryParse(args[1], out slotIndex))
            {
                return new PolisTestHarness.CommandResult { Ok = false, Message = "Invalid slot index" };
            }
            if (args.Length > 2 && !int.TryParse(args[2], out qty))
            {
                return new PolisTestHarness.CommandResult { Ok = false, Message = "Invalid quantity" };
            }
        }

        // Resolve bot owner player for claims check
        if (!globalData.Bots.TryGetValue(bot.Entity.EntityId, out var botRecord))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Bot not in registry" };
        }

        IServerPlayer ownerPlayer = sapi.World.PlayerByUid(botRecord.OwnerUid) as IServerPlayer;
        if (ownerPlayer == null)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Bot owner is offline or unknown" };
        }

        // Pre-validate range before starting action
        var botPos = bot.Entity.ServerPos.XYZ;
        var containerCenter = new Vec3d(pos.X + 0.5, pos.Y + 0.5, pos.Z + 0.5);
        double dist = botPos.DistanceTo(containerCenter);
        if (dist > PolisConstants.DefaultActionRange)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"Out of range: {dist:F1} > {PolisConstants.DefaultActionRange:F1}" };
        }

        var action = new PolisContainerTakeAction(
            bot.Activity,
            pos,
            slotIndex,
            qty,
            ownerPlayer,
            PolisConstants.DefaultActionRange,
            debugEnabled ? msg => sapi.Logger.Debug($"[polis] {msg}") : null,
            (ok, msg) => bot.RecordActionResult("takefrom", ok, msg, sapi.World.ElapsedMilliseconds)
        );

        StartSingleAction(bot, "takefrom", action);

        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = $"Bot #{bot.Entity.EntityId} taking from container at ({pos.X}, {pos.Y}, {pos.Z}) slot {slotIndex}"
        };
    }

    PolisTestHarness.CommandResult ExecutePutIntoCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        // Usage: putinto <name|x> [y z] <containerSlot> [qty]
        // Can accept either a registered container name or x y z coordinates
        // The slot arg is the target container slot index (e.g. firepit: 0=fuel, 1=input, 2=output)
        // Bot source is always right hand (equip righthand first)
        if (args.Length < 2)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Usage: putinto <name|x> [y z] <containerSlot> [qty]" };
        }

        if (!TryGetContextPlayer(context, out var contextPlayer, out var ctxError))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = ctxError };
        }

        if (!TryGetHarnessBot(context, out var bot, out var err))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = err };
        }

        BlockPos pos;
        int containerSlot;
        int qty = 0;

        // Try to parse as coordinates first (4+ args: x y z containerSlot [qty])
        if (args.Length >= 4 && double.TryParse(args[0], out var x) && double.TryParse(args[1], out var y) && double.TryParse(args[2], out var z))
        {
            pos = new Vec3d(x, y, z).AsBlockPos;
            if (!int.TryParse(args[3], out containerSlot))
            {
                return new PolisTestHarness.CommandResult { Ok = false, Message = "Invalid container slot index" };
            }
            if (args.Length > 4 && !int.TryParse(args[4], out qty))
            {
                return new PolisTestHarness.CommandResult { Ok = false, Message = "Invalid quantity" };
            }
        }
        // Otherwise try as container name (2+ args: name containerSlot [qty])
        else
        {
            string containerName = args[0];
            if (!TryResolveContainerName(containerName, out pos, out var resolveError))
            {
                return new PolisTestHarness.CommandResult { Ok = false, Message = resolveError };
            }
            if (!int.TryParse(args[1], out containerSlot))
            {
                return new PolisTestHarness.CommandResult { Ok = false, Message = "Invalid container slot index" };
            }
            if (args.Length > 2 && !int.TryParse(args[2], out qty))
            {
                return new PolisTestHarness.CommandResult { Ok = false, Message = "Invalid quantity" };
            }
        }

        // Resolve bot owner player for claims check
        if (!globalData.Bots.TryGetValue(bot.Entity.EntityId, out var botRecord))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Bot not in registry" };
        }

        IServerPlayer ownerPlayer = sapi.World.PlayerByUid(botRecord.OwnerUid) as IServerPlayer;
        if (ownerPlayer == null)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Bot owner is offline or unknown" };
        }

        // Pre-validate range before starting action
        var botPos = bot.Entity.ServerPos.XYZ;
        var containerCenter = new Vec3d(pos.X + 0.5, pos.Y + 0.5, pos.Z + 0.5);
        double dist = botPos.DistanceTo(containerCenter);
        if (dist > PolisConstants.DefaultActionRange)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"Out of range: {dist:F1} > {PolisConstants.DefaultActionRange:F1}" };
        }

        var action = new PolisContainerPutAction(
            bot.Activity,
            pos,
            0, // bot source slot: always right hand
            qty,
            ownerPlayer,
            containerSlot,
            PolisConstants.DefaultActionRange,
            debugEnabled ? msg => sapi.Logger.Debug($"[polis] {msg}") : null,
            (ok, msg) => bot.RecordActionResult("putinto", ok, msg, sapi.World.ElapsedMilliseconds)
        );

        StartSingleAction(bot, "putinto", action);

        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = $"Bot #{bot.Entity.EntityId} putting into container at ({pos.X}, {pos.Y}, {pos.Z}) target slot {containerSlot}"
        };
    }

    // <verb>: "mine" (generic block break) or "chop" (the campaign's own
    // verb - same break path, but recorded under the name "chop" so the
    // harness's LastAction state and action sequence report it as a chop).
    PolisTestHarness.CommandResult ExecuteMineCommand(string[] args, PolisTestHarness.CommandContext context, string verb = "mine")
    {
        // Usage: mine|chop <x> <y> <z> [autocollect]
        if (args.Length < 3)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"Usage: {verb} <x> <y> <z> [true|false]" };
        }

        if (!TryGetContextPlayer(context, out var contextPlayer, out var ctxError))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = ctxError };
        }

        if (!TryGetHarnessBot(context, out var bot, out var err))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = err };
        }

        if (!double.TryParse(args[0], out var x) || !double.TryParse(args[1], out var y) || !double.TryParse(args[2], out var z))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Invalid coordinates" };
        }

        bool autoCollect = false;
        if (args.Length > 3)
        {
            if (!bool.TryParse(args[3], out autoCollect))
            {
                return new PolisTestHarness.CommandResult { Ok = false, Message = "Invalid autocollect value (use true/false)" };
            }
        }

        var pos = new Vec3d(x, y, z).AsBlockPos;

        // Validate block exists
        var block = sapi.World.BlockAccessor.GetBlock(pos);
        if (block == null || block.Id == 0)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "No block at target position" };
        }

        // Resolve bot owner player for block drops and claims check
        if (!globalData.Bots.TryGetValue(bot.Entity.EntityId, out var botRecord))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Bot not in registry" };
        }

        IServerPlayer ownerPlayer = sapi.World.PlayerByUid(botRecord.OwnerUid) as IServerPlayer;
        if (ownerPlayer == null)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Bot owner is offline or unknown" };
        }

        var selection = ResolveSelection(contextPlayer, pos, BlockFacing.NORTH);
        if (!TryValidateBlockTarget(
            contextPlayer,
            bot,
            selection,
            pos,
            EnumBlockAccessFlags.BuildOrBreak,
            debugEnabled ? msg => sapi.Logger.Debug($"[polis] {msg}") : null,
            out var movePos,
            out var validationError,
            bot.Entity))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = validationError.StatusMessage };
        }

        void OnGotoResult(bool ok, string msg)
        {
            if (!ok)
            {
                bot.RecordActionResult(verb, false, $"goto failed: {msg}", sapi.World.ElapsedMilliseconds);
            }
        }

        void OnMineResult(bool ok, string msg)
        {
            bot.RecordActionResult(verb, ok, msg, sapi.World.ElapsedMilliseconds);
        }

        var gotoAction = new PolisGotoAction(
            bot.Activity,
            movePos,
            true,
            "walk",
            0.02f,
            1f,
            debugEnabled ? msg => sapi.Logger.Debug($"[polis] {msg}") : null,
            null,
            debugEnabled,
            false,
            OnGotoResult
        );

        var mineAction = new PolisMineBlockAction(
            pos,
            ownerPlayer,
            maxRange: PolisConstants.DefaultActionRange,
            autoCollectDrops: autoCollect,
            debugLog: debugEnabled ? msg => sapi.Logger.Debug($"[polis] {msg}") : null,
            onResult: OnMineResult
        );

        StartActionSequence(bot, verb, gotoAction, mineAction);

        float estTime = block.Resistance / 1.0f; // Rough estimate with default speed
        string doing = verb == "chop" ? "chopping" : "mining";
        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = $"Bot #{bot.Entity.EntityId} {doing} {block.Code} at ({pos.X}, {pos.Y}, {pos.Z}), est {estTime:F1}s" + (autoCollect ? " (autocollect)" : ""),
            Data = new { blockCode = block.Code.ToString(), pos = new[] { pos.X, pos.Y, pos.Z }, autoCollect, estimatedSeconds = estTime }
        };
    }

    PolisTestHarness.CommandResult ExecuteBreakCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        // Usage: break <x> <y> <z> [dropMult]
        if (args.Length < 3)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Usage: break <x> <y> <z> [dropMult]" };
        }

        if (!TryGetContextPlayer(context, out var contextPlayer, out var ctxError))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = ctxError };
        }

        if (!TryGetHarnessBot(context, out var bot, out var err))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = err };
        }

        if (!double.TryParse(args[0], out var x) || !double.TryParse(args[1], out var y) || !double.TryParse(args[2], out var z))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Invalid coordinates" };
        }

        float dropMult = 1.0f;
        if (args.Length > 3)
        {
            if (!float.TryParse(args[3], System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out dropMult))
            {
                return new PolisTestHarness.CommandResult { Ok = false, Message = "Invalid dropMult value" };
            }
        }

        var pos = new Vec3d(x, y, z).AsBlockPos;

        // Validate block exists
        var block = sapi.World.BlockAccessor.GetBlock(pos);
        if (block == null || block.Id == 0)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "No block at target position" };
        }

        // Resolve bot owner player for block drops
        if (!globalData.Bots.TryGetValue(bot.Entity.EntityId, out var botRecord))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Bot not in registry" };
        }

        IServerPlayer ownerPlayer = sapi.World.PlayerByUid(botRecord.OwnerUid) as IServerPlayer;
        if (ownerPlayer == null)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Bot owner is offline or unknown" };
        }

        var selection = ResolveSelection(contextPlayer, pos, BlockFacing.NORTH);
        if (!TryValidateBlockTarget(
            contextPlayer,
            bot,
            selection,
            pos,
            EnumBlockAccessFlags.BuildOrBreak,
            debugEnabled ? msg => sapi.Logger.Debug($"[polis] {msg}") : null,
            out var movePos,
            out var validationError,
            bot.Entity))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = validationError.StatusMessage };
        }

        void OnGotoResult(bool ok, string msg)
        {
            if (!ok)
            {
                bot.RecordActionResult("break", false, $"goto failed: {msg}", sapi.World.ElapsedMilliseconds);
            }
        }

        void OnBreakResult(bool ok, string msg)
        {
            bot.RecordActionResult("break", ok, msg, sapi.World.ElapsedMilliseconds);
        }

        var gotoAction = new PolisGotoAction(
            bot.Activity,
            movePos,
            true,
            "walk",
            0.02f,
            1f,
            debugEnabled ? msg => sapi.Logger.Debug($"[polis] {msg}") : null,
            null,
            debugEnabled,
            false,
            OnGotoResult
        );

        var breakAction = new PolisBreakBlockAction(
            pos,
            ownerPlayer,
            dropMult,
            PolisConstants.DefaultActionRange,
            debugEnabled ? msg => sapi.Logger.Debug($"[polis] {msg}") : null,
            OnBreakResult
        );

        StartActionSequence(bot, "break", gotoAction, breakAction);

        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = $"Bot #{bot.Entity.EntityId} breaking {block.Code} at ({pos.X}, {pos.Y}, {pos.Z})",
            Data = new { blockCode = block.Code.ToString(), pos = new[] { pos.X, pos.Y, pos.Z }, dropMult }
        };
    }

    PolisTestHarness.CommandResult ExecutePlaceCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        // Usage: place <blockcode> <x> <y> <z> [face]
        if (args.Length < 4)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Usage: place <blockcode> <x> <y> <z> [face]" };
        }

        if (!TryGetContextPlayer(context, out var contextPlayer, out var ctxError))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = ctxError };
        }

        if (!TryGetHarnessBot(context, out var bot, out var err))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = err };
        }

        string code = args[0];
        if (!double.TryParse(args[1], out var x) || !double.TryParse(args[2], out var y) || !double.TryParse(args[3], out var z))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Invalid coordinates" };
        }

        string faceCode = args.Length > 4 ? args[4].ToLowerInvariant() : "up";
        var face = BlockFacing.FromCode(faceCode) ?? BlockFacing.UP;

        // Resolve block
        var block = ResolveBlockLenient(sapi.World, code);
        if (block == null)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"Unknown block: {code}" };
        }

        // Search bot inventory for the block
        var sourceSlot = PolisInventoryHelpers.FindBlockInInventory(
            bot.Entity,
            block,
            debugEnabled ? msg => sapi.Logger.Debug($"[polis] {msg}") : null
        );

        if (sourceSlot == null)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"Bot doesn't have {code} in inventory" };
        }

        // Calculate positions - target pos is where block will be placed (air), clicked pos is the surface
        var targetPos = new Vec3d(x, y, z).AsBlockPos;
        var clickedPos = targetPos.AddCopy(face.Opposite);  // Surface block that was "clicked"

        // Resolve bot owner player for claims check
        if (!globalData.Bots.TryGetValue(bot.Entity.EntityId, out var botRecord))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Bot not in registry" };
        }

        IServerPlayer ownerPlayer = sapi.World.PlayerByUid(botRecord.OwnerUid) as IServerPlayer;
        if (ownerPlayer == null)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Bot owner is offline or unknown" };
        }

        var selection = ResolveSelection(contextPlayer, clickedPos, face);

        // Check claims on target position (where block will be placed)
        if (!SkipClaims && sapi.World.Claims != null && !sapi.World.Claims.TryAccess(contextPlayer, targetPos, EnumBlockAccessFlags.BuildOrBreak))
        {
            if (debugEnabled) sapi.Logger.Debug($"[polis] Place claims check failed at {targetPos}");
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Access denied." };
        }

        // Calculate approach position: bot should stand near the target but NOT overlapping it.
        // 2026-09-29 (the block-in-bot-cell incident): the old formula picked ONE offset
        // direction from the bot's side (with a |dx|>=|dz| tie-break) and sent the bot there
        // BLIND - a corner-arriving bot made the tie fire and the offset landed in an
        // already-placed block, where the pathfinder walked in and "finished". Now all four
        // horizontal neighbours at target level are candidates, nearest-first, and only an
        // OPEN (non-solid) cell is used. If none is open the place fails cleanly instead of
        // embedding the bot.
        Vec3d movePos;
        if (face == BlockFacing.UP || face == BlockFacing.DOWN)
        {
            var botPos = bot.Entity.ServerPos.XYZ;
            var opts = new System.Collections.Generic.List<(Vec3d pos, double dist)>
            {
                (new Vec3d(targetPos.X + 1.5, targetPos.Y, targetPos.Z + 0.5),
                 Math.Abs(botPos.X - (targetPos.X + 1.5)) + Math.Abs(botPos.Z - (targetPos.Z + 0.5))),
                (new Vec3d(targetPos.X - 0.5, targetPos.Y, targetPos.Z + 0.5),
                 Math.Abs(botPos.X - (targetPos.X - 0.5)) + Math.Abs(botPos.Z - (targetPos.Z + 0.5))),
                (new Vec3d(targetPos.X + 0.5, targetPos.Y, targetPos.Z + 1.5),
                 Math.Abs(botPos.X - (targetPos.X + 0.5)) + Math.Abs(botPos.Z - (targetPos.Z + 1.5))),
                (new Vec3d(targetPos.X + 0.5, targetPos.Y, targetPos.Z - 0.5),
                 Math.Abs(botPos.X - (targetPos.X + 0.5)) + Math.Abs(botPos.Z - (targetPos.Z - 0.5)))
            };
            opts.Sort((a, b) => a.dist.CompareTo(b.dist));
            movePos = null;
            foreach (var o in opts)
            {
                var cell = new BlockPos((int)o.pos.X, (int)o.pos.Y, (int)o.pos.Z);
                var cellBlock = sapi.World.BlockAccessor.GetBlock(cell);
                // an open standing cell is an EMPTY cell (BlockID 0 = air /
                // "none"). Anything else - a placed block, a wall, a crop -
                // is not a ledge: sending the bot there is how it got
                // embedded in the 09-29 hut runs.
                if (cellBlock == null || cellBlock.Id == 0)
                {
                    movePos = o.pos;
                    break;
                }
            }
            if (movePos == null)
            {
                return new PolisTestHarness.CommandResult
                {
                    Ok = false,
                    Message = $"no open standing cell around {targetPos} (all four neighbours are solid) - open a ledge first"
                };
            }
        }
        else
        {
            // For horizontal faces, stand at the surface block position (opposite to face direction)
            // This places the bot on the side away from the target
            movePos = new Vec3d(clickedPos.X + 0.5, clickedPos.Y, clickedPos.Z + 0.5);
        }

        void OnGotoResult(bool ok, string msg)
        {
            if (!ok)
            {
                bot.RecordActionResult("place", false, $"goto failed: {msg}", sapi.World.ElapsedMilliseconds);
            }
        }

        void OnPlaceResult(bool ok, string msg)
        {
            bot.RecordActionResult("place", ok, msg, sapi.World.ElapsedMilliseconds);
        }

        var gotoAction = new PolisGotoAction(
            bot.Activity,
            movePos,
            true,
            "walk",
            0.02f,
            1f,
            debugEnabled ? msg => sapi.Logger.Debug($"[polis] {msg}") : null,
            null,
            debugEnabled,
            false,
            OnGotoResult
        );

        var itemstack = sourceSlot.Itemstack.Clone();
        itemstack.StackSize = 1; // Only place one block

        var placeAction = new PolisPlaceBlockAction(
            targetPos,  // Pass target (air) position, not clicked surface
            face,
            selection.HitPosition,
            block,
            itemstack,
            ownerPlayer,
            PolisConstants.DefaultActionRange,
            debugEnabled ? msg => sapi.Logger.Debug($"[polis] {msg}") : null,
            sourceSlot,
            OnPlaceResult
        );

        StartActionSequence(bot, "place", gotoAction, placeAction);

        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = $"Bot #{bot.Entity.EntityId} placing {code} at ({targetPos.X}, {targetPos.Y}, {targetPos.Z}) face={face.Code}",
            Data = new { blockCode = code, pos = new[] { targetPos.X, targetPos.Y, targetPos.Z }, face = face.Code }
        };
    }

    /// <summary>
    /// 1.22: base-game content is registered under different mod ids than the
    /// asset folder names ("survival:..." stopped resolving; plain and "game:"
    /// codes work). Try the given code as-is, then common re-prefixings.
    /// </summary>
    private static Block ResolveBlockLenient(IWorldAccessor world, string code)
    {
        if (string.IsNullOrWhiteSpace(code) || code.Equals("air", StringComparison.OrdinalIgnoreCase)) return null;
        var tried = new System.Collections.Generic.List<string>();
        string[] candidates = code.Contains(':')
            ? new[] { code, code.Substring(code.IndexOf(':') + 1), "game:" + code.Substring(code.IndexOf(':') + 1), "survival:" + code.Substring(code.IndexOf(':') + 1) }
            : new[] { code, "game:" + code, "survival:" + code };
        foreach (var c in candidates)
        {
            if (tried.Contains(c)) continue;
            tried.Add(c);
            Block b = null;
            try { b = world.BlockAccessor.GetBlock(new AssetLocation(c)); } catch { }
            if (b == null) { try { b = world.GetBlock(new AssetLocation(c)); } catch { } }
            if (b != null) return b;
        }
        return null;
    }

    private static Item ResolveItemLenient(IWorldAccessor world, string code)
    {
        if (string.IsNullOrWhiteSpace(code)) return null;
        string[] candidates = code.Contains(':')
            ? new[] { code, code.Substring(code.IndexOf(':') + 1), "game:" + code.Substring(code.IndexOf(':') + 1), "survival:" + code.Substring(code.IndexOf(':') + 1) }
            : new[] { code, "game:" + code, "survival:" + code };
        foreach (var c in candidates)
        {
            Item it = null;
            try { it = world.GetItem(new AssetLocation(c)); } catch { }
            if (it != null) return it;
        }
        return null;
    }

    PolisTestHarness.CommandResult ExecuteSetBlockCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        // Usage: setblock <blockcode> <x> <y> <z>
        if (args.Length < 4)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Usage: setblock <blockcode> <x> <y> <z>" };
        }

        string code = args[0];
        if (!double.TryParse(args[1], out var x) || !double.TryParse(args[2], out var y) || !double.TryParse(args[3], out var z))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Invalid coordinates" };
        }

        var pos = new BlockPos((int)x, (int)y, (int)z);

        // Resolve block (handle "air" special case)
        Block block;
        if (code.ToLowerInvariant() == "air")
        {
            block = sapi.World.GetBlock(0); // Air block
        }
        else
        {
            block = ResolveBlockLenient(sapi.World, code);
        }

        if (block == null)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"Unknown block: {code}" };
        }

        // Set the block directly
        sapi.World.BlockAccessor.SetBlock(block.BlockId, pos);
        sapi.World.BlockAccessor.MarkBlockDirty(pos);

        if (debugEnabled)
        {
            sapi.Logger.Debug($"[polis] setblock: {code} at ({pos.X}, {pos.Y}, {pos.Z})");
        }

        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = $"Set {code} at ({pos.X}, {pos.Y}, {pos.Z})",
            Data = new { blockCode = code, pos = new[] { pos.X, pos.Y, pos.Z } }
        };
    }

    PolisTestHarness.CommandResult ExecuteRipenCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        // Usage: ripen <x> <y> <z>
        // Test lever: force a fruiting bush's block-entity growth state to
        // Ripe (it would otherwise take in-game months to ripen) so a
        // forage/pick cycle can be exercised without waiting for the
        // growth clock. Report the previous state.
        if (args.Length < 3)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Usage: ripen <x> <y> <z>" };
        }
        if (!int.TryParse(args[0], out var x) || !int.TryParse(args[1], out var y) || !int.TryParse(args[2], out var z))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Invalid coordinates" };
        }

        var pos = new BlockPos(x, y, z);
        var block = sapi.World.BlockAccessor.GetBlock(pos);
        if (block == null || block.Id == 0 || block.GetBehavior<BlockBehaviorFruitingBush>() == null)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"not a fruiting bush at ({x}, {y}, {z}): {block?.Code ?? "air"}" };
        }
        var bush = sapi.World.BlockAccessor.GetBlockEntity(pos)?.GetBehavior<BEBehaviorFruitingBush>();
        if (bush == null)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"bush at ({x}, {y}, {z}) has no block-entity state" };
        }

        var before = bush.BState.Growthstate;
        bush.BState.Growthstate = EnumFruitingBushGrowthState.Ripe;
        bush.BState.TransitionHoursLeft = bush.GetHoursForNextStage();
        bush.Blockentity.MarkDirty(true, null);

        sapi.Logger.Notification($"[polis] ripen: {block.Code} at ({x}, {y}, {z}) {before} -> Ripe");

        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = $"{block.Code} at ({x}, {y}, {z}) was {before}, now Ripe",
            Data = new { blockCode = block.Code.ToString(), pos = new[] { x, y, z }, before = before.ToString(), now = "Ripe" }
        };
    }

    PolisTestHarness.CommandResult ExecuteEquipCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        // Usage: equip <slot> <itemcode> [qty]
        // slot: lefthand, righthand, backpack0, backpack1
        if (args.Length < 2)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Usage: equip <slot> <itemcode> [qty]" };
        }

        if (!TryGetHarnessBot(context, out var bot, out var err))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = err };
        }

        string slotName = args[0].ToLowerInvariant();
        string code = args[1];
        int qty = 1;
        if (args.Length > 2 && int.TryParse(args[2], out var parsedQty) && parsedQty > 0)
        {
            qty = parsedQty;
        }

        if (!TryResolveStack(code, qty, out var stack, out var errorText))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = errorText };
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
                    return new PolisTestHarness.CommandResult { Ok = false, Message = "Bot has no seraph inventory" };
                }
                break;
            default:
                return new PolisTestHarness.CommandResult { Ok = false, Message = $"Unknown slot: {slotName}. Use: lefthand, righthand, backpack0, backpack1" };
        }

        slot.Itemstack = stack;
        slot.MarkDirty();
        PolisInventoryHelpers.StoreSeraphInventory(bot.Entity);

        if (debugEnabled)
        {
            sapi.Logger.Debug($"[polis] equip: {code} x{qty} on {slotName}");
        }

        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = $"Equipped {code} x{qty} on {slotName}",
            Data = new { slot = slotName, itemCode = code, qty }
        };
    }

    PolisTestHarness.CommandResult ExecuteScanCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        // Usage: scan <x1> <y1> <z1> <x2> <y2> <z2> [--include-air]
        // Scans a bounding box and returns all blocks
        if (args.Length < 6)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Usage: scan <x1> <y1> <z1> <x2> <y2> <z2> [--include-air]" };
        }

        if (!int.TryParse(args[0], out var x1) || !int.TryParse(args[1], out var y1) || !int.TryParse(args[2], out var z1))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Invalid from coordinates" };
        }
        if (!int.TryParse(args[3], out var x2) || !int.TryParse(args[4], out var y2) || !int.TryParse(args[5], out var z2))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Invalid to coordinates" };
        }

        bool includeAir = args.Length > 6 && args[6].ToLowerInvariant() == "--include-air";

        // Normalize bounds (ensure min/max ordering)
        int minX = Math.Min(x1, x2), maxX = Math.Max(x1, x2);
        int minY = Math.Min(y1, y2), maxY = Math.Max(y1, y2);
        int minZ = Math.Min(z1, z2), maxZ = Math.Max(z1, z2);

        // Safety limit: max 100x100x100 = 1M blocks
        int dx = maxX - minX + 1;
        int dy = maxY - minY + 1;
        int dz = maxZ - minZ + 1;
        long totalBlocks = (long)dx * dy * dz;
        if (totalBlocks > 1000000)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"Scan area too large: {totalBlocks} blocks (max 1M)" };
        }

        var blocks = new List<object>();
        var accessor = sapi.World.BlockAccessor;

        for (int x = minX; x <= maxX; x++)
        {
            for (int y = minY; y <= maxY; y++)
            {
                for (int z = minZ; z <= maxZ; z++)
                {
                    var pos = new BlockPos(x, y, z);
                    var block = accessor.GetBlock(pos);

                    // Skip air unless explicitly requested
                    if (block == null || block.Id == 0)
                    {
                        if (includeAir)
                        {
                            blocks.Add(new { pos = new[] { x, y, z }, code = "air" });
                        }
                        continue;
                    }

                    blocks.Add(new
                    {
                        pos = new[] { x, y, z },
                        code = block.Code?.ToString() ?? "unknown"
                    });
                }
            }
        }

        if (debugEnabled)
        {
            sapi.Logger.Debug($"[polis] scan: ({minX},{minY},{minZ}) to ({maxX},{maxY},{maxZ}) - {blocks.Count} blocks");
        }

        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = $"Scanned {blocks.Count} blocks",
            Data = new
            {
                from = new[] { minX, minY, minZ },
                to = new[] { maxX, maxY, maxZ },
                blockCount = blocks.Count,
                blocks
            }
        };
    }

    PolisTestHarness.CommandResult ExecuteVerifyCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        // Usage: verify <json_blueprint>
        // Blueprint format: [{"pos":[x,y,z],"code":"game:cobblestone"}, ...]
        if (args.Length < 1 || string.IsNullOrWhiteSpace(args[0]))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Usage: verify <json_blueprint>" };
        }

        string blueprintJson = args[0];

        // Parse blueprint JSON
        List<BlueprintBlock> blueprint;
        try
        {
            blueprint = System.Text.Json.JsonSerializer.Deserialize<List<BlueprintBlock>>(blueprintJson,
                new System.Text.Json.JsonSerializerOptions { PropertyNameCaseInsensitive = true });
        }
        catch (Exception ex)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"Invalid blueprint JSON: {ex.Message}" };
        }

        if (blueprint == null || blueprint.Count == 0)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Blueprint is empty" };
        }

        var accessor = sapi.World.BlockAccessor;
        var matched = new List<object>();
        var missing = new List<object>();
        var wrong = new List<object>();

        foreach (var entry in blueprint)
        {
            if (entry.Pos == null || entry.Pos.Length < 3)
            {
                continue;
            }

            var pos = new BlockPos(entry.Pos[0], entry.Pos[1], entry.Pos[2]);
            var actualBlock = accessor.GetBlock(pos);
            var actualCode = actualBlock?.Code?.ToString() ?? "air";
            var expectedCode = entry.Code ?? "air";

            // Normalize comparison (handle "air" specially)
            bool isActualAir = actualBlock == null || actualBlock.Id == 0;
            bool isExpectedAir = expectedCode.ToLowerInvariant() == "air";

            if (isActualAir && isExpectedAir)
            {
                matched.Add(new { pos = entry.Pos, code = "air" });
            }
            else if (isActualAir && !isExpectedAir)
            {
                missing.Add(new { pos = entry.Pos, expected = expectedCode, actual = "air" });
            }
            else if (!isActualAir && isExpectedAir)
            {
                wrong.Add(new { pos = entry.Pos, expected = "air", actual = actualCode });
            }
            else if (actualCode.Equals(expectedCode, StringComparison.OrdinalIgnoreCase))
            {
                matched.Add(new { pos = entry.Pos, code = actualCode });
            }
            else
            {
                // Different block - check if it's a variant match (e.g., cobblestone vs cobblestone-granite)
                // For now, exact match required
                wrong.Add(new { pos = entry.Pos, expected = expectedCode, actual = actualCode });
            }
        }

        int total = blueprint.Count;
        double completionPct = total > 0 ? Math.Round((matched.Count * 100.0) / total, 1) : 0;

        if (debugEnabled)
        {
            sapi.Logger.Debug($"[polis] verify: {matched.Count}/{total} matched, {missing.Count} missing, {wrong.Count} wrong");
        }

        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = $"Verified: {matched.Count}/{total} blocks correct ({completionPct}%)",
            Data = new
            {
                total,
                matched = matched.Count,
                missing = missing.Count,
                wrong = wrong.Count,
                completionPct,
                missingBlocks = missing,
                wrongBlocks = wrong
            }
        };
    }

    // Blueprint block entry for verify command
    private class BlueprintBlock
    {
        public int[] Pos { get; set; }
        public string Code { get; set; }
    }

    // ==================== Container Registry Commands ====================

    PolisTestHarness.CommandResult ExecuteContainerRegisterCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        // Usage: container-register <name> <x> <y> <z> [type] [description]
        if (args.Length < 4)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Usage: container-register <name> <x> <y> <z> [type] [description]" };
        }

        if (!TryGetContextPlayer(context, out var contextPlayer, out var ctxError))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = ctxError };
        }

        string name = args[0];
        if (string.IsNullOrWhiteSpace(name))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Container name cannot be empty" };
        }

        if (!int.TryParse(args[1], out var x) || !int.TryParse(args[2], out var y) || !int.TryParse(args[3], out var z))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Invalid coordinates" };
        }

        var pos = new BlockPos(x, y, z);
        var block = sapi.World.BlockAccessor.GetBlock(pos);
        if (block == null || block.Id == 0)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"No block at position ({x}, {y}, {z})" };
        }

        // Verify it's actually a container
        var blockEntity = sapi.World.BlockAccessor.GetBlockEntity(pos);
        if (blockEntity == null || !(blockEntity is IBlockEntityContainer))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"Block at ({x}, {y}, {z}) is not a container: {block.Code}" };
        }

        string blockCode = block.Code?.ToString() ?? "unknown";
        string containerType = args.Length > 4 && !string.IsNullOrWhiteSpace(args[4]) ? args[4] : InferContainerType(blockCode);
        string description = args.Length > 5 ? args[5] : null;

        var record = new ContainerRecord
        {
            Name = name,
            X = x,
            Y = y,
            Z = z,
            BlockCode = blockCode,
            OwnerUid = contextPlayer.PlayerUID,
            ContainerType = containerType,
            RegisteredAt = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(),
            Description = description
        };

        containerRegistry.Containers[name] = record;

        if (debugEnabled)
        {
            sapi.Logger.Debug($"[polis] container-register: '{name}' at ({x}, {y}, {z}) type={containerType}");
        }

        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = $"Registered container '{name}' at ({x}, {y}, {z}) type={containerType}",
            Data = new
            {
                name,
                pos = new[] { x, y, z },
                blockCode,
                containerType,
                description
            }
        };
    }

    PolisTestHarness.CommandResult ExecuteContainerListCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        // Usage: container-list [type]
        string filterType = args.Length > 0 && !string.IsNullOrWhiteSpace(args[0]) ? args[0] : null;

        var containers = new List<object>();
        foreach (var kvp in containerRegistry.Containers)
        {
            var record = kvp.Value;
            if (filterType != null && !record.ContainerType.Equals(filterType, StringComparison.OrdinalIgnoreCase))
            {
                continue;
            }

            // Validate container still exists
            var pos = new BlockPos(record.X, record.Y, record.Z);
            var block = sapi.World.BlockAccessor.GetBlock(pos);
            string currentCode = block?.Code?.ToString();
            bool valid = currentCode != null && currentCode.Equals(record.BlockCode, StringComparison.OrdinalIgnoreCase);

            containers.Add(new
            {
                name = record.Name,
                pos = new[] { record.X, record.Y, record.Z },
                blockCode = record.BlockCode,
                containerType = record.ContainerType,
                description = record.Description,
                ownerUid = record.OwnerUid,
                valid,
                currentBlockCode = valid ? null : currentCode
            });
        }

        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = $"Found {containers.Count} container(s)",
            Data = new { count = containers.Count, containers }
        };
    }

    PolisTestHarness.CommandResult ExecuteContainerRemoveCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        // Usage: container-remove <name>
        if (args.Length < 1 || string.IsNullOrWhiteSpace(args[0]))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Usage: container-remove <name>" };
        }

        string name = args[0];
        if (!containerRegistry.Containers.TryGetValue(name, out var record))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"Container '{name}' not found in registry" };
        }

        containerRegistry.Containers.Remove(name);

        if (debugEnabled)
        {
            sapi.Logger.Debug($"[polis] container-remove: '{name}'");
        }

        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = $"Removed container '{name}' from registry",
            Data = new { name, pos = new[] { record.X, record.Y, record.Z } }
        };
    }

    string InferContainerType(string blockCode)
    {
        if (string.IsNullOrWhiteSpace(blockCode)) return "generic";
        var lower = blockCode.ToLowerInvariant();
        if (lower.Contains("chest")) return "chest";
        if (lower.Contains("storagevessel") || lower.Contains("vessel")) return "vessel";
        if (lower.Contains("barrel")) return "barrel";
        if (lower.Contains("crate")) return "crate";
        return "generic";
    }

    /// <summary>
    /// Try to resolve a container name to BlockPos coordinates.
    /// Returns true if found and valid, false with error message otherwise.
    /// </summary>
    bool TryResolveContainerName(string name, out BlockPos pos, out string error)
    {
        pos = null;
        error = null;

        if (!containerRegistry.Containers.TryGetValue(name, out var record))
        {
            error = $"Container '{name}' not found in registry";
            return false;
        }

        pos = new BlockPos(record.X, record.Y, record.Z);

        // Validate container still exists at location
        var block = sapi.World.BlockAccessor.GetBlock(pos);
        string currentCode = block?.Code?.ToString();

        if (currentCode == null || !currentCode.Equals(record.BlockCode, StringComparison.OrdinalIgnoreCase))
        {
            error = $"Container '{name}' at ({record.X}, {record.Y}, {record.Z}) has been moved or replaced. " +
                    $"Expected: {record.BlockCode}, Found: {currentCode ?? "air"}";
            return false;
        }

        // Verify it's still a container
        var blockEntity = sapi.World.BlockAccessor.GetBlockEntity(pos);
        if (blockEntity == null || !(blockEntity is IBlockEntityContainer))
        {
            error = $"Block at ({record.X}, {record.Y}, {record.Z}) is no longer a container";
            return false;
        }

        return true;
    }

    PolisTestHarness.CommandResult ExecuteContainerContentsCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        // Usage: container-contents <name|x> [y z] [includeEmpty]
        // Can accept either a registered name or x y z coordinates
        if (args.Length < 1)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Usage: container-contents <name|x> [y z] [includeEmpty]" };
        }

        BlockPos pos;
        string containerName = null;
        bool includeEmpty = false;

        // Try to parse as coordinates first
        if (args.Length >= 3 && int.TryParse(args[0], out var x) && int.TryParse(args[1], out var y) && int.TryParse(args[2], out var z))
        {
            pos = new BlockPos(x, y, z);
            if (args.Length > 3 && bool.TryParse(args[3], out var ie))
            {
                includeEmpty = ie;
            }
        }
        else
        {
            // Try as container name
            containerName = args[0];
            if (!TryResolveContainerName(containerName, out pos, out var error))
            {
                return new PolisTestHarness.CommandResult { Ok = false, Message = error };
            }
            if (args.Length > 1 && bool.TryParse(args[1], out var ie))
            {
                includeEmpty = ie;
            }
        }

        var block = sapi.World.BlockAccessor.GetBlock(pos);
        if (block == null || block.Id == 0)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"No block at position ({pos.X}, {pos.Y}, {pos.Z})" };
        }

        var blockEntity = sapi.World.BlockAccessor.GetBlockEntity(pos);
        if (blockEntity == null || !(blockEntity is IBlockEntityContainer container))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"Block at ({pos.X}, {pos.Y}, {pos.Z}) is not a container" };
        }

        var inventory = container.Inventory;
        var slots = new List<object>();
        int occupiedCount = 0;

        for (int i = 0; i < inventory.Count; i++)
        {
            var slot = inventory[i];
            bool hasItem = slot?.Itemstack != null && slot.Itemstack.StackSize > 0;

            if (hasItem)
            {
                occupiedCount++;
                slots.Add(new
                {
                    slot = i,
                    code = slot.Itemstack.Collectible?.Code?.ToString(),
                    qty = slot.Itemstack.StackSize
                });
            }
            else if (includeEmpty)
            {
                slots.Add(new
                {
                    slot = i,
                    code = (string)null,
                    qty = 0
                });
            }
        }

        string blockCode = block.Code?.ToString();
        string inventoryType = InferContainerType(blockCode);

        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = occupiedCount > 0
                ? $"{occupiedCount}/{inventory.Count} slots used"
                : $"Empty ({inventory.Count} slots)",
            Data = new
            {
                pos = new[] { pos.X, pos.Y, pos.Z },
                blockCode,
                inventoryType,
                slotCount = inventory.Count,
                occupiedCount,
                isEmpty = occupiedCount == 0,
                name = containerName,
                slots
            }
        };
    }

    PolisTestHarness.CommandResult ExecuteContainerSetCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        // Usage: container-set <x> <y> <z> <slot> <itemCode> [qty]
        if (args.Length < 5)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Usage: container-set <x> <y> <z> <slot> <itemCode> [qty]" };
        }

        // Parse coordinates
        if (!int.TryParse(args[0], out int x) ||
            !int.TryParse(args[1], out int y) ||
            !int.TryParse(args[2], out int z))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Invalid coordinates" };
        }

        BlockPos pos = new BlockPos(x, y, z);

        // Parse slot
        if (!int.TryParse(args[3], out int slot))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Invalid slot number" };
        }

        string itemCode = args[4];
        int qty = args.Length > 5 && int.TryParse(args[5], out int q) ? q : 1;

        // Resolve item/block
        var item = sapi.World.GetItem(new AssetLocation(itemCode));
        var block = item == null ? sapi.World.GetBlock(new AssetLocation(itemCode)) : null;

        ItemStack stack = null;
        if (item != null) stack = new ItemStack(item, qty);
        else if (block != null) stack = new ItemStack(block, qty);

        if (stack == null)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"Item/block '{itemCode}' not found" };
        }

        // Get container
        var blockEntity = sapi.World.BlockAccessor.GetBlockEntity(pos);
        var container = blockEntity as IBlockEntityContainer;

        if (container == null)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"No container at {x},{y},{z}" };
        }

        // Validate slot
        if (slot < 0 || slot >= container.Inventory.Count)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"Slot {slot} out of range (0-{container.Inventory.Count - 1})" };
        }

        var destSlot = container.Inventory[slot];
        if (destSlot == null)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"Slot {slot} is null" };
        }

        // Set item and mark dirty
        destSlot.Itemstack = stack;
        destSlot.MarkDirty();

        if (blockEntity is BlockEntity be)
            be.MarkDirty(true);

        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = $"Set slot {slot} at {x},{y},{z} to {qty}x {itemCode}"
        };
    }

    PolisTestHarness.CommandResult ExecuteHarvestCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        // Usage: harvest <x> <y> <z> [autocollect] [validateripe]
        if (args.Length < 3)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Usage: harvest <x> <y> <z> [autocollect] [validateripe]" };
        }

        if (!TryGetContextPlayer(context, out var contextPlayer, out var ctxError))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = ctxError };
        }

        if (!TryGetHarnessBot(context, out var bot, out var err))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = err };
        }

        if (!double.TryParse(args[0], out var x) || !double.TryParse(args[1], out var y) || !double.TryParse(args[2], out var z))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Invalid coordinates" };
        }

        bool autoCollect = false;
        if (args.Length > 3 && bool.TryParse(args[3], out var ac))
        {
            autoCollect = ac;
        }

        bool validateRipe = true; // default true
        if (args.Length > 4 && bool.TryParse(args[4], out var vr))
        {
            validateRipe = vr;
        }

        var pos = new Vec3d(x, y, z).AsBlockPos;

        // Resolve bot owner player for claims check
        if (!globalData.Bots.TryGetValue(bot.Entity.EntityId, out var botRecord))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Bot not in registry" };
        }

        IServerPlayer ownerPlayer = sapi.World.PlayerByUid(botRecord.OwnerUid) as IServerPlayer;
        if (ownerPlayer == null)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Bot owner is offline or unknown" };
        }

        // Pre-validate range before starting action
        var botPos = bot.Entity.ServerPos.XYZ;
        var blockCenter = new Vec3d(pos.X + 0.5, pos.Y + 0.5, pos.Z + 0.5);
        double dist = botPos.DistanceTo(blockCenter);
        if (dist > PolisConstants.DefaultActionRange)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"Out of range: {dist:F1} > {PolisConstants.DefaultActionRange:F1}" };
        }

        void OnHarvestResult(bool ok, string msg)
        {
            bot.RecordActionResult("harvest", ok, msg, sapi.World.ElapsedMilliseconds);
        }

        var action = new PolisHarvestBlockAction(
            pos,
            ownerPlayer,
            maxRange: PolisConstants.DefaultActionRange,
            autoCollectDrops: autoCollect,
            collectRadius: 3f,
            validateRipe: validateRipe,
            debugLog: debugEnabled ? msg => sapi.Logger.Debug($"[polis] {msg}") : null,
            onResult: OnHarvestResult
        );

        StartSingleAction(bot, "harvest", action);

        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = $"Bot #{bot.Entity.EntityId} harvesting block at ({pos.X}, {pos.Y}, {pos.Z}) (autocollect={autoCollect}, validateripe={validateRipe})"
        };
    }

    PolisTestHarness.CommandResult ExecuteHarvestCropCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        // Usage: harvestcrop <x> <y> <z> [autocollect]
        if (args.Length < 3)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Usage: harvestcrop <x> <y> <z> [autocollect]" };
        }

        if (!TryGetContextPlayer(context, out var contextPlayer, out var ctxError))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = ctxError };
        }

        if (!TryGetHarnessBot(context, out var bot, out var err))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = err };
        }

        if (!double.TryParse(args[0], out var x) || !double.TryParse(args[1], out var y) || !double.TryParse(args[2], out var z))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Invalid coordinates" };
        }

        bool autoCollect = false;
        if (args.Length > 3 && bool.TryParse(args[3], out var ac))
        {
            autoCollect = ac;
        }

        var pos = new Vec3d(x, y, z).AsBlockPos;

        // Resolve bot owner player for claims check
        if (!globalData.Bots.TryGetValue(bot.Entity.EntityId, out var botRecord))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Bot not in registry" };
        }

        IServerPlayer ownerPlayer = sapi.World.PlayerByUid(botRecord.OwnerUid) as IServerPlayer;
        if (ownerPlayer == null)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Bot owner is offline or unknown" };
        }

        // Pre-validate range before starting action
        var botPos = bot.Entity.ServerPos.XYZ;
        var blockCenter = new Vec3d(pos.X + 0.5, pos.Y + 0.5, pos.Z + 0.5);
        double dist = botPos.DistanceTo(blockCenter);
        if (dist > PolisConstants.DefaultActionRange)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"Out of range: {dist:F1} > {PolisConstants.DefaultActionRange:F1}" };
        }

        void OnHarvestCropResult(bool ok, string msg)
        {
            bot.RecordActionResult("harvestcrop", ok, msg, sapi.World.ElapsedMilliseconds);
        }

        var action = new PolisHarvestCropAction(
            pos,
            ownerPlayer,
            maxRange: PolisConstants.DefaultActionRange,
            autoCollectDrops: autoCollect,
            collectRadius: 3f,
            debugLog: debugEnabled ? msg => sapi.Logger.Debug($"[polis] {msg}") : null,
            onResult: OnHarvestCropResult
        );

        StartSingleAction(bot, "harvestcrop", action);

        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = $"Bot #{bot.Entity.EntityId} harvesting crop at ({pos.X}, {pos.Y}, {pos.Z}) (autocollect={autoCollect})"
        };
    }

    PolisTestHarness.CommandResult ExecuteForgeHeatCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        // Usage: forge-heat <x> <y> <z> [duration]
        if (args.Length < 3)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Usage: forge-heat <x> <y> <z> [duration]" };
        }

        if (!TryGetContextPlayer(context, out var contextPlayer, out var ctxError))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = ctxError };
        }

        if (!TryGetHarnessBot(context, out var bot, out var err))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = err };
        }

        if (!double.TryParse(args[0], out var x) || !double.TryParse(args[1], out var y) || !double.TryParse(args[2], out var z))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Invalid coordinates" };
        }

        float maxDuration = 120f;
        if (args.Length > 3 && float.TryParse(args[3], out var md))
        {
            maxDuration = md;
        }

        var pos = new Vec3d(x, y, z).AsBlockPos;

        // Resolve bot owner player
        if (!globalData.Bots.TryGetValue(bot.Entity.EntityId, out var botRecord))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Bot not in registry" };
        }

        IServerPlayer ownerPlayer = sapi.World.PlayerByUid(botRecord.OwnerUid) as IServerPlayer;
        if (ownerPlayer == null)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Bot owner is offline or unknown" };
        }

        // Pre-validate range
        var botPos = bot.Entity.ServerPos.XYZ;
        var blockCenter = new Vec3d(pos.X + 0.5, pos.Y + 0.5, pos.Z + 0.5);
        double dist = botPos.DistanceTo(blockCenter);
        if (dist > PolisConstants.DefaultActionRange)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"Out of range: {dist:F1} > {PolisConstants.DefaultActionRange:F1}" };
        }

        // Pre-validate firepit
        var firepitEntity = sapi.World.BlockAccessor.GetBlockEntity(pos) as BlockEntityFirepit;
        if (firepitEntity == null)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"No firepit at ({pos.X}, {pos.Y}, {pos.Z})" };
        }

        if (firepitEntity.inputSlot.Empty)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Firepit input slot is empty" };
        }

        if (!firepitEntity.IsBurning)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Firepit is not burning" };
        }

        // Auto-calculate target temperature from input item
        var inputStack = firepitEntity.inputSlot.Itemstack;
        float meltingPoint = inputStack.Collectible.GetMeltingPoint(sapi.World, null, new DummySlot(inputStack));
        float targetTemp = meltingPoint / 2;
        if (inputStack.Collectible.Attributes?["workableTemperature"].Exists == true)
        {
            targetTemp = inputStack.Collectible.Attributes["workableTemperature"].AsFloat(targetTemp);
        }

        float currentTemp = firepitEntity.InputStackTemp;

        void OnForgeHeatResult(bool ok, string msg)
        {
            bot.RecordActionResult("forge-heat", ok, msg, sapi.World.ElapsedMilliseconds);
        }

        var action = new PolisForgeHeatAction(
            pos,
            ownerPlayer,
            targetTemp: targetTemp,
            maxDuration: maxDuration,
            maxRange: PolisConstants.DefaultActionRange,
            debugLog: debugEnabled ? msg => sapi.Logger.Debug($"[polis] {msg}") : null,
            onResult: OnForgeHeatResult
        );

        StartSingleAction(bot, "forge-heat", action);

        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = $"Bot #{bot.Entity.EntityId} waiting for heat at ({pos.X}, {pos.Y}, {pos.Z}): target={targetTemp:F0}°C, current={currentTemp:F0}°C, timeout={maxDuration:F0}s"
        };
    }

    PolisTestHarness.CommandResult ExecuteGrindCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        // Usage: grind <x> <y> <z> [count] [duration]
        // count: max items to grind (0 = unlimited)
        // duration: max grinding time in seconds (0 = unlimited)
        if (args.Length < 3)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Usage: grind <x> <y> <z> [count] [duration]" };
        }

        if (!TryGetContextPlayer(context, out var contextPlayer, out var ctxError))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = ctxError };
        }

        if (!TryGetHarnessBot(context, out var bot, out var err))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = err };
        }

        if (!double.TryParse(args[0], out var x) || !double.TryParse(args[1], out var y) || !double.TryParse(args[2], out var z))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Invalid coordinates" };
        }

        int maxCount = 0;
        if (args.Length > 3 && int.TryParse(args[3], out var mc))
        {
            maxCount = mc;
        }

        float maxDuration = 0;
        if (args.Length > 4 && float.TryParse(args[4], out var md))
        {
            maxDuration = md;
        }

        var pos = new Vec3d(x, y, z).AsBlockPos;

        // Resolve bot owner player for claims check
        if (!globalData.Bots.TryGetValue(bot.Entity.EntityId, out var botRecord))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Bot not in registry" };
        }

        IServerPlayer ownerPlayer = sapi.World.PlayerByUid(botRecord.OwnerUid) as IServerPlayer;
        if (ownerPlayer == null)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Bot owner is offline or unknown" };
        }

        // Pre-validate range before starting action
        var botPos = bot.Entity.ServerPos.XYZ;
        var blockCenter = new Vec3d(pos.X + 0.5, pos.Y + 0.5, pos.Z + 0.5);
        double dist = botPos.DistanceTo(blockCenter);
        if (dist > PolisConstants.DefaultActionRange)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"Out of range: {dist:F1} > {PolisConstants.DefaultActionRange:F1}" };
        }

        // Pre-validate quern block and CanGrind
        var block = sapi.World.BlockAccessor.GetBlock(pos);
        if (!(block is BlockQuern))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"Block at {pos} is not a quern (found: {block?.Code})" };
        }

        var quernEntity = sapi.World.BlockAccessor.GetBlockEntity(pos) as BlockEntityQuern;
        if (quernEntity == null)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "No quern block entity found" };
        }

        if (!quernEntity.CanGrind())
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Quern cannot grind (no grindable input)" };
        }

        void OnGrindResult(bool ok, string msg)
        {
            bot.RecordActionResult("grind", ok, msg, sapi.World.ElapsedMilliseconds);
        }

        var action = new PolisGrindBlockAction(
            pos,
            ownerPlayer,
            maxRange: PolisConstants.DefaultActionRange,
            maxCount: maxCount,
            maxDuration: maxDuration,
            debugLog: debugEnabled ? msg => sapi.Logger.Debug($"[polis] {msg}") : null,
            onResult: OnGrindResult
        );

        StartSingleAction(bot, "grind", action);

        string limits = "";
        if (maxCount > 0) limits += $" count={maxCount}";
        if (maxDuration > 0) limits += $" duration={maxDuration:F1}s";
        if (limits == "") limits = " unlimited";

        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = $"Bot #{bot.Entity.EntityId} grinding at ({pos.X}, {pos.Y}, {pos.Z}){limits}"
        };
    }

    PolisTestHarness.CommandResult ExecutePressCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        // Usage: press <x> <y> <z> [duration] [autounscrew]
        // duration: max pressing time in seconds (0 = unlimited)
        // autounscrew: whether to unscrew when complete (default: true)
        if (args.Length < 3)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Usage: press <x> <y> <z> [duration] [autounscrew]" };
        }

        if (!TryGetContextPlayer(context, out var contextPlayer, out var ctxError))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = ctxError };
        }

        if (!TryGetHarnessBot(context, out var bot, out var err))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = err };
        }

        if (!double.TryParse(args[0], out var x) || !double.TryParse(args[1], out var y) || !double.TryParse(args[2], out var z))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Invalid coordinates" };
        }

        float maxDuration = 0;
        if (args.Length > 3 && float.TryParse(args[3], out var md))
        {
            maxDuration = md;
        }

        bool autoUnscrew = true;
        if (args.Length > 4 && bool.TryParse(args[4], out var au))
        {
            autoUnscrew = au;
        }

        var pos = new Vec3d(x, y, z).AsBlockPos;

        // Resolve bot owner player for claims check
        if (!globalData.Bots.TryGetValue(bot.Entity.EntityId, out var botRecord))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Bot not in registry" };
        }

        IServerPlayer ownerPlayer = sapi.World.PlayerByUid(botRecord.OwnerUid) as IServerPlayer;
        if (ownerPlayer == null)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Bot owner is offline or unknown" };
        }

        // Pre-validate range before starting action
        var botPos = bot.Entity.ServerPos.XYZ;
        var blockCenter = new Vec3d(pos.X + 0.5, pos.Y + 0.5, pos.Z + 0.5);
        double dist = botPos.DistanceTo(blockCenter);
        if (dist > PolisConstants.DefaultActionRange)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"Out of range: {dist:F1} > {PolisConstants.DefaultActionRange:F1}" };
        }

        // Pre-validate fruit press block
        var block = sapi.World.BlockAccessor.GetBlock(pos);
        if (block.GetType().Name != "BlockFruitPress")
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"Block at {pos} is not a fruit press (found: {block?.Code})" };
        }

        var fruitPressEntity = sapi.World.BlockAccessor.GetBlockEntity(pos);
        if (fruitPressEntity == null || fruitPressEntity.GetType().Name != "BlockEntityFruitPress")
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "No fruit press block entity found" };
        }

        // Check CanScrew via reflection
        var canScrewProp = fruitPressEntity.GetType().GetProperty("CanScrew");
        if (canScrewProp != null)
        {
            bool canScrew = (bool)canScrewProp.GetValue(fruitPressEntity);
            if (!canScrew)
            {
                return new PolisTestHarness.CommandResult { Ok = false, Message = "Fruit press cannot screw (already fully compressed or animation active)" };
            }
        }

        // Check if has mash content
        var mashSlotProp = fruitPressEntity.GetType().GetProperty("MashSlot");
        if (mashSlotProp != null)
        {
            var mashSlot = mashSlotProp.GetValue(fruitPressEntity) as ItemSlot;
            if (mashSlot == null || mashSlot.Empty)
            {
                return new PolisTestHarness.CommandResult { Ok = false, Message = "Fruit press has no mash to press" };
            }
        }

        void OnPressResult(bool ok, string msg)
        {
            bot.RecordActionResult("press", ok, msg, sapi.World.ElapsedMilliseconds);
        }

        var action = new PolisPressAction(
            pos,
            ownerPlayer,
            maxRange: PolisConstants.DefaultActionRange,
            maxDuration: maxDuration,
            autoUnscrew: autoUnscrew,
            debugLog: debugEnabled ? msg => sapi.Logger.Debug($"[polis] {msg}") : null,
            onResult: OnPressResult
        );

        StartSingleAction(bot, "press", action);

        string options = "";
        if (maxDuration > 0) options += $" duration={maxDuration:F1}s";
        if (!autoUnscrew) options += " autounscrew=false";
        if (options == "") options = " unlimited";

        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = $"Bot #{bot.Entity.EntityId} pressing at ({pos.X}, {pos.Y}, {pos.Z}){options}"
        };
    }

    PolisTestHarness.CommandResult ExecuteButcherCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        // Usage: butcher <entityId> [autocollect]
        if (args.Length < 1)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Usage: butcher <entityId> [autocollect]" };
        }

        if (!TryGetContextPlayer(context, out var contextPlayer, out var ctxError))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = ctxError };
        }

        if (!TryGetHarnessBot(context, out var bot, out var err))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = err };
        }

        if (!long.TryParse(args[0], out var targetEntityId))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Invalid entity ID" };
        }

        bool autoCollect = true;
        if (args.Length > 1 && bool.TryParse(args[1], out var ac))
        {
            autoCollect = ac;
        }

        // Resolve bot owner player for claims/permission context
        if (!globalData.Bots.TryGetValue(bot.Entity.EntityId, out var botRecord))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Bot not in registry" };
        }

        IServerPlayer ownerPlayer = sapi.World.PlayerByUid(botRecord.OwnerUid) as IServerPlayer;
        if (ownerPlayer == null)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Bot owner is offline or unknown" };
        }

        void OnButcherResult(bool ok, string msg)
        {
            bot.RecordActionResult("butcher", ok, msg, sapi.World.ElapsedMilliseconds);
        }

        var action = new PolisButcherEntityAction(
            targetEntityId,
            ownerPlayer,
            maxRange: PolisConstants.DefaultActionRange,
            autoCollectDrops: autoCollect,
            dropQuantityMultiplier: 1.0f,
            debugLog: debugEnabled ? msg => sapi.Logger.Debug($"[polis] {msg}") : null,
            onResult: OnButcherResult
        );

        StartSingleAction(bot, "butcher", action);

        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = $"Bot #{bot.Entity.EntityId} butchering entity {targetEntityId} (autocollect={autoCollect})"
        };
    }

    PolisTestHarness.CommandResult ExecuteClayFormCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        // Usage: clayform <x> <y> <z> <recipe> [speed]
        // recipe: output code name (e.g., "bowl-raw", "toolmold-fire-raw-anvil")
        // speed: voxels per tick (default 4, higher = faster)
        if (args.Length < 4)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Usage: clayform <x> <y> <z> <recipe> [speed]" };
        }

        if (!TryGetContextPlayer(context, out var contextPlayer, out var ctxError))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = ctxError };
        }

        if (!TryGetHarnessBot(context, out var bot, out var err))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = err };
        }

        if (!double.TryParse(args[0], out var x) || !double.TryParse(args[1], out var y) || !double.TryParse(args[2], out var z))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Invalid coordinates" };
        }

        string recipeName = args[3];

        int speed = 4;
        if (args.Length > 4 && int.TryParse(args[4], out var s))
        {
            speed = Math.Max(1, s);
        }

        var pos = new Vec3d(x, y, z).AsBlockPos;

        // Resolve bot owner player for claims check
        if (!globalData.Bots.TryGetValue(bot.Entity.EntityId, out var botRecord))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Bot not in registry" };
        }

        IServerPlayer ownerPlayer = sapi.World.PlayerByUid(botRecord.OwnerUid) as IServerPlayer;
        if (ownerPlayer == null)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Bot owner is offline or unknown" };
        }

        // Pre-validate range before starting action
        var botPos = bot.Entity.ServerPos.XYZ;
        var blockCenter = new Vec3d(pos.X + 0.5, pos.Y + 0.5, pos.Z + 0.5);
        double dist = botPos.DistanceTo(blockCenter);
        if (dist > PolisConstants.DefaultActionRange)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"Out of range: {dist:F1} > {PolisConstants.DefaultActionRange:F1}" };
        }

        // Pre-validate recipe exists
        var recipes = sapi.World.Api.GetClayformingRecipes();
        if (recipes == null || recipes.Count == 0)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "No clay forming recipes available" };
        }

        var recipe = recipes.FirstOrDefault(r =>
            r.Output?.ResolvedItemstack?.Collectible?.Code?.Path == recipeName ||
            r.Output?.ResolvedItemstack?.Collectible?.Code?.ToString() == recipeName ||
            r.Name == recipeName);

        if (recipe == null)
        {
            // List some available recipes for debugging
            var sampleRecipes = recipes.Take(5).Select(r => r.Output?.ResolvedItemstack?.Collectible?.Code?.Path ?? r.Name).ToList();
            return new PolisTestHarness.CommandResult
            {
                Ok = false,
                Message = $"Recipe '{recipeName}' not found. Sample recipes: {string.Join(", ", sampleRecipes)}"
            };
        }

        // Check if bot has clay
        var agent = bot.Entity as EntityAgent;
        bool hasClayInHand = agent?.RightHandItemSlot?.Itemstack?.Collectible?.Code?.Path?.StartsWith("clay-") == true ||
                              agent?.LeftHandItemSlot?.Itemstack?.Collectible?.Code?.Path?.StartsWith("clay-") == true;

        if (!hasClayInHand)
        {
            // Check cargo
            bool hasClayInInventory = false;
            var inv = PolisInventoryHelpers.BotCargo(agent);
            if (inv != null)
            {
                for (int i = 0; i < inv.Count; i++)
                {
                    var slot = inv[i];
                    if (slot?.Itemstack?.Collectible?.Code?.Path?.StartsWith("clay-") == true)
                    {
                        hasClayInInventory = true;
                        break;
                    }
                }
            }

            if (!hasClayInInventory)
            {
                return new PolisTestHarness.CommandResult { Ok = false, Message = "Bot has no clay in inventory" };
            }
        }

        void OnClayFormResult(bool ok, string msg)
        {
            bot.RecordActionResult("clayform", ok, msg, sapi.World.ElapsedMilliseconds);
        }

        var action = new PolisClayFormAction(
            pos,
            ownerPlayer,
            recipeName,
            voxelsPerTick: speed,
            maxRange: PolisConstants.DefaultActionRange,
            debugLog: debugEnabled ? msg => sapi.Logger.Debug($"[polis] {msg}") : null,
            onResult: OnClayFormResult
        );

        StartSingleAction(bot, "clayform", action);

        int totalVoxels = recipe.Voxels.Cast<bool>().Count(v => v);
        float estimatedTime = (float)totalVoxels / speed * 0.1f; // 0.1s per tick

        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = $"Bot #{bot.Entity.EntityId} forming {recipe.Name} ({totalVoxels} voxels) at ({pos.X}, {pos.Y}, {pos.Z}), speed={speed}, ~{estimatedTime:F1}s"
        };
    }

    PolisTestHarness.CommandResult ExecuteKnapCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        // Usage: knap <x> <y> <z> <recipe> [speed]
        // recipe: output code name (e.g., "arrowhead-flint", "knife-blade-flint", "axehead-flint")
        // speed: voxels per tick (default 4, higher = faster)
        if (args.Length < 4)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Usage: knap <x> <y> <z> <recipe> [speed]" };
        }

        if (!TryGetContextPlayer(context, out var contextPlayer, out var ctxError))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = ctxError };
        }

        if (!TryGetHarnessBot(context, out var bot, out var err))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = err };
        }

        if (!double.TryParse(args[0], out var x) || !double.TryParse(args[1], out var y) || !double.TryParse(args[2], out var z))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Invalid coordinates" };
        }

        string recipeName = args[3];

        int speed = 4;
        if (args.Length > 4 && int.TryParse(args[4], out var s))
        {
            speed = Math.Max(1, s);
        }

        var pos = new Vec3d(x, y, z).AsBlockPos;

        // Pre-validate range before starting action
        var botPos = bot.Entity.ServerPos.XYZ;
        var blockCenter = new Vec3d(pos.X + 0.5, pos.Y + 0.5, pos.Z + 0.5);
        double dist = botPos.DistanceTo(blockCenter);
        if (dist > PolisConstants.DefaultActionRange)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"Out of range: {dist:F1} > {PolisConstants.DefaultActionRange:F1}" };
        }

        // Pre-validate recipe exists
        var recipes = sapi.World.Api.GetKnappingRecipes();
        if (recipes == null || recipes.Count == 0)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "No knapping recipes available" };
        }

        var recipe = recipes.FirstOrDefault(r =>
            r.Output?.ResolvedItemstack?.Collectible?.Code?.Path == recipeName ||
            r.Output?.ResolvedItemstack?.Collectible?.Code?.ToString() == recipeName ||
            r.Name == recipeName);

        if (recipe == null)
        {
            // List some available recipes for debugging
            var sampleRecipes = recipes.Take(5).Select(r => r.Output?.ResolvedItemstack?.Collectible?.Code?.Path ?? r.Name).ToList();
            return new PolisTestHarness.CommandResult
            {
                Ok = false,
                Message = $"Recipe '{recipeName}' not found. Sample recipes: {string.Join(", ", sampleRecipes)}"
            };
        }

        // Validate knapping surface exists at position
        var block = sapi.World.BlockAccessor.GetBlock(pos);
        if (!(block is BlockKnappingSurface))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"No knapping surface at position (got {block?.Code?.Path ?? "air"})" };
        }

        var knapEntity = sapi.World.BlockAccessor.GetBlockEntity(pos) as BlockEntityKnappingSurface;
        if (knapEntity == null)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Knapping surface has no entity" };
        }

        // Check surface has material OR bot has matching material to initialize it
        bool surfaceHasMaterial = knapEntity.BaseMaterial != null && knapEntity.BaseMaterial.StackSize > 0;
        bool botHasMaterial = false;
        var agent = bot.Entity as EntityAgent;

        if (!surfaceHasMaterial)
        {
            // Check if bot has matching material to initialize the surface
            botHasMaterial = CheckBotHasKnappingMaterial(agent, recipe.Ingredient);
            if (!botHasMaterial)
            {
                return new PolisTestHarness.CommandResult { Ok = false, Message = "Knapping surface has no material and bot has no matching material" };
            }
        }
        else
        {
            // Check material matches recipe
            if (!recipe.Ingredient.SatisfiesAsIngredient(knapEntity.BaseMaterial))
            {
                var materialCode = knapEntity.BaseMaterial?.Collectible?.Code?.Path ?? "unknown";
                return new PolisTestHarness.CommandResult { Ok = false, Message = $"Material '{materialCode}' doesn't match recipe ingredient" };
            }
        }

        void OnKnapResult(bool ok, string msg)
        {
            bot.RecordActionResult("knap", ok, msg, sapi.World.ElapsedMilliseconds);
        }

        var action = new PolisKnapAction(
            pos,
            recipeName,
            voxelsPerTick: speed,
            maxRange: PolisConstants.DefaultActionRange,
            debugLog: debugEnabled ? msg => sapi.Logger.Debug($"[polis] {msg}") : null,
            onResult: OnKnapResult
        );

        StartSingleAction(bot, "knap", action);

        // Calculate voxels to remove (256 - recipe voxels)
        int recipeVoxelCount = recipe.Voxels.Cast<bool>().Count(v => v);
        int totalVoxelsToRemove = 256 - recipeVoxelCount;
        float estimatedTime = (float)totalVoxelsToRemove / speed * 0.1f; // 0.1s per tick

        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = $"Bot #{bot.Entity.EntityId} knapping {recipe.Name} ({totalVoxelsToRemove} voxels to remove) at ({pos.X}, {pos.Y}, {pos.Z}), speed={speed}, ~{estimatedTime:F1}s"
        };
    }

    bool CheckBotHasKnappingMaterial(EntityAgent agent, CraftingRecipeIngredient ingredient)
    {
        if (agent == null || ingredient == null) return false;

        // Check hands first
        if (agent.RightHandItemSlot?.Itemstack != null && ingredient.SatisfiesAsIngredient(agent.RightHandItemSlot.Itemstack))
        {
            return true;
        }
        if (agent.LeftHandItemSlot?.Itemstack != null && ingredient.SatisfiesAsIngredient(agent.LeftHandItemSlot.Itemstack))
        {
            return true;
        }

        // Check cargo
        var inv = PolisInventoryHelpers.BotCargo(agent);
        if (inv != null)
        {
            for (int i = 0; i < inv.Count; i++)
            {
                var slot = inv[i];
                if (slot?.Itemstack != null && ingredient.SatisfiesAsIngredient(slot.Itemstack))
                {
                    return true;
                }
            }
        }

        return false;
    }

    PolisTestHarness.CommandResult ExecuteSealCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        // Usage: seal <x> <y> <z>
        // Seals a barrel that has contents matching a sealing recipe (fermentation/pickling)
        if (args.Length < 3)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Usage: seal <x> <y> <z>" };
        }

        if (!TryGetContextPlayer(context, out var contextPlayer, out var ctxError))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = ctxError };
        }

        if (!TryGetHarnessBot(context, out var bot, out var err))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = err };
        }

        if (!double.TryParse(args[0], out var x) || !double.TryParse(args[1], out var y) || !double.TryParse(args[2], out var z))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Invalid coordinates" };
        }

        var pos = new Vec3d(x, y, z).AsBlockPos;

        // Pre-validate range before starting action
        var botPos = bot.Entity.ServerPos.XYZ;
        var blockCenter = new Vec3d(pos.X + 0.5, pos.Y + 0.5, pos.Z + 0.5);
        double dist = botPos.DistanceTo(blockCenter);
        if (dist > PolisConstants.DefaultActionRange)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"Out of range: {dist:F1} > {PolisConstants.DefaultActionRange:F1}" };
        }

        // Pre-validate barrel block
        var block = sapi.World.BlockAccessor.GetBlock(pos);
        if (block == null || !block.Code.Path.StartsWith("barrel"))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"Block at {pos} is not a barrel (found: {block?.Code})" };
        }

        var barrelEntity = sapi.World.BlockAccessor.GetBlockEntity(pos) as BlockEntityBarrel;
        if (barrelEntity == null)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "No barrel block entity found" };
        }

        // Check if already sealed
        if (barrelEntity.Sealed)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Barrel is already sealed" };
        }

        // Check if barrel can be sealed (has valid sealing recipe)
        if (!barrelEntity.CanSeal)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Barrel cannot be sealed (no valid sealing recipe - needs items + liquid for fermentation)" };
        }

        void OnSealResult(bool ok, string msg)
        {
            bot.RecordActionResult("seal", ok, msg, sapi.World.ElapsedMilliseconds);
        }

        var action = new PolisSealBarrelAction(
            pos,
            contextPlayer,
            maxRange: PolisConstants.DefaultActionRange,
            debugLog: debugEnabled ? msg => sapi.Logger.Debug($"[polis] {msg}") : null,
            onResult: OnSealResult
        );

        StartSingleAction(bot, "seal", action);

        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = $"Bot #{bot.Entity.EntityId} sealing barrel at ({pos.X}, {pos.Y}, {pos.Z})"
        };
    }

    PolisTestHarness.CommandResult ExecuteAnvilSmithCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        // Usage: anvil-smith <x> <y> <z> <recipe> [speed]
        // recipe: output code (e.g., "pickaxehead-copper", "metalplate-iron")
        // speed: voxels per tick (default: 4)
        if (args.Length < 4)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Usage: anvil-smith <x> <y> <z> <recipe> [speed]" };
        }

        if (!TryGetContextPlayer(context, out var contextPlayer, out var ctxError))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = ctxError };
        }

        if (!TryGetHarnessBot(context, out var bot, out var err))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = err };
        }

        if (!double.TryParse(args[0], out var x) || !double.TryParse(args[1], out var y) || !double.TryParse(args[2], out var z))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Invalid coordinates" };
        }

        string recipeCode = args[3];

        int voxelsPerTick = 4;
        if (args.Length > 4 && int.TryParse(args[4], out var speed))
        {
            voxelsPerTick = speed;
        }

        var pos = new Vec3d(x, y, z).AsBlockPos;

        // Resolve bot owner player for claims check
        if (!globalData.Bots.TryGetValue(bot.Entity.EntityId, out var botRecord))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Bot not in registry" };
        }

        IServerPlayer ownerPlayer = sapi.World.PlayerByUid(botRecord.OwnerUid) as IServerPlayer;
        if (ownerPlayer == null)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Bot owner is offline or unknown" };
        }

        // Validate block target and compute move position
        var selection = ResolveSelection(ownerPlayer, pos, BlockFacing.NORTH);

        // Pre-validate anvil block
        var block = sapi.World.BlockAccessor.GetBlock(pos);
        if (block == null || !(block is BlockAnvil))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"Block at {pos} is not an anvil (found: {block?.Code})" };
        }

        selection.Block = block;

        if (!TryValidateBlockTarget(
            ownerPlayer,
            bot,
            selection,
            pos,
            EnumBlockAccessFlags.Use,
            debugEnabled ? msg => sapi.Logger.Debug($"[polis] {msg}") : null,
            out var movePos,
            out var validationError,
            bot.Entity))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = validationError.StatusMessage };
        }

        var anvilEntity = sapi.World.BlockAccessor.GetBlockEntity(pos) as BlockEntityAnvil;
        if (anvilEntity == null)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "No anvil block entity found" };
        }

        // Check if anvil has work item
        if (anvilEntity.WorkItemStack == null)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Anvil has no work item" };
        }

        // Check temperature - must be workable (>20°C)
        float temp = anvilEntity.WorkItemStack.Collectible.GetTemperature(sapi.World, anvilEntity.WorkItemStack);
        if (temp <= 20)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"Work item too cold: {temp:F0}°C (needs >20°C)" };
        }

        // Find the recipe by output code
        var recipes = sapi.GetSmithingRecipes();
        SmithingRecipe targetRecipe = null;

        // First check if anvil already has a selected recipe that matches
        if (anvilEntity.SelectedRecipeId >= 0)
        {
            foreach (var recipe in recipes)
            {
                if (recipe.RecipeId == anvilEntity.SelectedRecipeId)
                {
                    // Verify the output matches what was requested
                    if (recipe.Output?.ResolvedItemstack?.Collectible?.Code?.Path?.Contains(recipeCode) == true)
                    {
                        targetRecipe = recipe;
                        break;
                    }
                }
            }
        }

        // Fall back to searching all recipes by output code
        if (targetRecipe == null)
        {
            foreach (var recipe in recipes)
            {
                if (recipe.Output?.ResolvedItemstack?.Collectible?.Code?.Path?.Contains(recipeCode) == true)
                {
                    // Check if this recipe is valid for the current work item
                    if (recipe.Ingredient.SatisfiesAsIngredient(anvilEntity.WorkItemStack))
                    {
                        targetRecipe = recipe;
                        break;
                    }
                }
            }
        }

        if (targetRecipe == null)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"No matching smithing recipe found for '{recipeCode}'" };
        }

        void OnGotoResult(bool ok, string msg)
        {
            if (!ok)
            {
                bot.RecordActionResult("anvil-smith", false, $"goto failed: {msg}", sapi.World.ElapsedMilliseconds);
            }
        }

        void OnSmithResult(bool ok, string msg)
        {
            bot.RecordActionResult("anvil-smith", ok, msg, sapi.World.ElapsedMilliseconds);
        }

        var gotoAction = new PolisGotoAction(
            bot.Activity,
            movePos,
            true,
            "walk",
            0.02f,
            1f,
            debugEnabled ? msg => sapi.Logger.Debug($"[polis] {msg}") : null,
            debugEnabled ? path => HighlightPath(ownerPlayer, path) : null,
            debugEnabled,
            false,
            OnGotoResult
        );

        var action = new PolisAnvilSmithAction(
            pos,
            targetRecipe.RecipeId,
            ownerPlayer,
            voxelsPerTick: voxelsPerTick,
            maxRange: PolisConstants.DefaultActionRange,
            debugLog: debugEnabled ? msg => sapi.Logger.Debug($"[polis] {msg}") : null,
            onResult: OnSmithResult
        );

        StartActionSequence(bot, "anvil-smith", gotoAction, action);

        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = $"Bot #{bot.Entity.EntityId} smithing '{targetRecipe.Output.ResolvedItemstack.Collectible.Code}' at ({pos.X}, {pos.Y}, {pos.Z})"
        };
    }

    PolisTestHarness.CommandResult ExecuteAnvilStateCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        // Usage: anvil-state <x> <y> <z>
        // Returns the current state of an anvil (work item, temperature, recipe, voxel stats)
        if (args.Length < 3)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Usage: anvil-state <x> <y> <z>" };
        }

        if (!double.TryParse(args[0], out var x) || !double.TryParse(args[1], out var y) || !double.TryParse(args[2], out var z))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Invalid coordinates" };
        }

        var pos = new Vec3d(x, y, z).AsBlockPos;

        // Validate anvil block
        var block = sapi.World.BlockAccessor.GetBlock(pos);
        if (block == null || !(block is BlockAnvil))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"Block at {pos} is not an anvil (found: {block?.Code})" };
        }

        var anvilEntity = sapi.World.BlockAccessor.GetBlockEntity(pos) as BlockEntityAnvil;
        if (anvilEntity == null)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "No anvil block entity found" };
        }

        // Count voxels
        int metalVoxels = 0;
        int slagVoxels = 0;
        int emptyVoxels = 0;
        for (int vx = 0; vx < 16; vx++)
        {
            for (int vy = 0; vy < 6; vy++)
            {
                for (int vz = 0; vz < 16; vz++)
                {
                    byte v = anvilEntity.Voxels[vx, vy, vz];
                    if (v == 1) metalVoxels++;
                    else if (v == 2) slagVoxels++;
                    else emptyVoxels++;
                }
            }
        }

        // Build state data
        var stateData = new Dictionary<string, object>
        {
            ["hasWorkItem"] = anvilEntity.WorkItemStack != null,
            ["workItemCode"] = anvilEntity.WorkItemStack?.Collectible?.Code?.ToString(),
            ["temperature"] = anvilEntity.WorkItemStack != null ? anvilEntity.WorkItemStack.Collectible.GetTemperature(sapi.World, anvilEntity.WorkItemStack) : 0,
            ["selectedRecipeId"] = anvilEntity.SelectedRecipeId,
            ["selectedRecipeName"] = anvilEntity.SelectedRecipe?.Output?.ResolvedItemstack?.Collectible?.Code?.ToString(),
            ["metalVoxels"] = metalVoxels,
            ["slagVoxels"] = slagVoxels,
            ["emptyVoxels"] = emptyVoxels,
            ["canWork"] = anvilEntity.CanWorkCurrent
        };

        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = "Anvil state retrieved",
            Data = stateData
        };
    }

    PolisTestHarness.CommandResult ExecuteLootCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        // Usage: loot <entityId>
        // Transfers items from a dead entity's harvestable inventory to bot inventory
        // Differs from butcher: doesn't require Harvestable == true (works on already-butchered corpses)
        if (args.Length < 1)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Usage: loot <entityId>" };
        }

        if (!TryGetContextPlayer(context, out var contextPlayer, out var ctxError))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = ctxError };
        }

        if (!TryGetHarnessBot(context, out var bot, out var err))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = err };
        }

        if (!long.TryParse(args[0], out var targetEntityId))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Invalid entity ID" };
        }

        // Find target entity
        var targetEntity = sapi.World.GetEntityById(targetEntityId);
        if (targetEntity == null)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"Entity {targetEntityId} not found" };
        }

        // Check if dead
        if (targetEntity.Alive)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"Entity {targetEntityId} is still alive (must be dead to loot)" };
        }

        // Range check
        double dist = bot.Entity.ServerPos.XYZ.DistanceTo(targetEntity.ServerPos.XYZ);
        if (dist > PolisConstants.DefaultActionRange)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"Entity is out of range ({dist:F1} > {PolisConstants.DefaultActionRange})" };
        }

        // Get harvestable behavior
        var harvestBehavior = targetEntity.GetBehavior<EntityBehaviorHarvestable>();
        if (harvestBehavior?.Inventory == null)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Entity has no harvestable inventory" };
        }

        var harvestInv = harvestBehavior.Inventory;

        // Count items before transfer
        int itemsBefore = 0;
        for (int i = 0; i < harvestInv.Count; i++)
        {
            if (harvestInv[i]?.Itemstack?.StackSize > 0)
            {
                itemsBefore += harvestInv[i].Itemstack.StackSize;
            }
        }

        if (itemsBefore == 0)
        {
            // Even with no items, try to trigger carcass transformation if not already done
            // This handles cases where butcher already emptied the inventory
            bool emptyCarcassSpawned = false;
            string emptyCarcassBlockCode = null;

            var emptyDeadDecayBehavior = targetEntity.GetBehavior<EntityBehaviorDeadDecay>();
            if (emptyDeadDecayBehavior != null)
            {
                if (debugEnabled)
                {
                    sapi.Logger.Debug($"[polis] loot: inventory already empty, triggering carcass transformation via DecayNow()");
                }

                emptyDeadDecayBehavior.DecayNow();
                emptyCarcassSpawned = true;

                var emptyDecayedBlockAttr = targetEntity.Properties?.Attributes?["deaddecay"]?["decayedBlock"];
                if (emptyDecayedBlockAttr != null)
                {
                    emptyCarcassBlockCode = emptyDecayedBlockAttr.AsString();
                }
            }

            return new PolisTestHarness.CommandResult
            {
                Ok = true,
                Message = emptyCarcassSpawned
                    ? "No items to loot, corpse transformed to carcass"
                    : "No items to loot",
                Data = new
                {
                    transferred = 0,
                    inventoryEmpty = true,
                    carcassSpawned = emptyCarcassSpawned,
                    carcassBlockCode = emptyCarcassBlockCode
                }
            };
        }

        // Transfer items
        var agent = bot.Entity;
        int stacksTransferred = 0;
        int itemsTransferred = 0;
        var transferredItems = new List<object>();

        for (int i = 0; i < harvestInv.Count; i++)
        {
            var slot = harvestInv[i];
            if (slot?.Itemstack == null) continue;

            int stackSize = slot.Itemstack.StackSize;
            ItemStack stack = slot.Itemstack.Clone();
            string itemCode = stack.Collectible?.Code?.ToString() ?? "unknown";

            if (PolisInventoryHelpers.TryInsertIntoBotInventory(agent, stack, out int moved, out string _,
                    debugEnabled ? msg => sapi.Logger.Debug($"[polis] {msg}") : null))
            {
                stacksTransferred++;
                itemsTransferred += moved;
                transferredItems.Add(new { code = itemCode, qty = moved });

                if (debugEnabled)
                {
                    sapi.Logger.Debug($"[polis] loot: transferred {moved}x {itemCode}");
                }

                // Clear slot in harvest inventory
                if (moved >= stackSize)
                {
                    slot.Itemstack = null;
                }
                else
                {
                    slot.Itemstack.StackSize -= moved;
                }
                slot.MarkDirty();
            }
            else
            {
                if (debugEnabled)
                {
                    sapi.Logger.Debug($"[polis] loot: could not transfer {stack.StackSize}x {itemCode} (inventory full?)");
                }
            }
        }

        // Persist bot inventory
        PolisInventoryHelpers.StoreSeraphInventory(agent);

        // Check if inventory is now empty and trigger carcass transformation
        // This replicates the VS behavior when a player closes an empty corpse inventory dialog
        bool inventoryEmpty = harvestInv.Empty;
        bool carcassSpawned = false;
        string carcassBlockCode = null;

        if (inventoryEmpty)
        {
            var deadDecayBehavior = targetEntity.GetBehavior<EntityBehaviorDeadDecay>();
            if (deadDecayBehavior != null)
            {
                if (debugEnabled)
                {
                    sapi.Logger.Debug($"[polis] loot: inventory empty, triggering carcass transformation via DecayNow()");
                }

                deadDecayBehavior.DecayNow();
                carcassSpawned = true;

                // Try to get the decayed block code from entity type attributes for response
                var decayedBlockAttr = targetEntity.Properties?.Attributes?["deaddecay"]?["decayedBlock"];
                if (decayedBlockAttr != null)
                {
                    carcassBlockCode = decayedBlockAttr.AsString();
                }
            }
            else if (debugEnabled)
            {
                sapi.Logger.Debug($"[polis] loot: inventory empty but entity has no DeadDecay behavior");
            }
        }

        // Record action result
        bot.RecordActionResult("loot", true, $"Looted {itemsTransferred} items from entity {targetEntityId}", sapi.World.ElapsedMilliseconds);

        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = carcassSpawned
                ? $"Looted {itemsTransferred} items ({stacksTransferred} stacks) from entity {targetEntityId}, corpse transformed to carcass"
                : $"Looted {itemsTransferred} items ({stacksTransferred} stacks) from entity {targetEntityId}",
            Data = new
            {
                entityId = targetEntityId,
                transferred = itemsTransferred,
                stacks = stacksTransferred,
                items = transferredItems,
                remaining = itemsBefore - itemsTransferred,
                inventoryEmpty = inventoryEmpty,
                carcassSpawned = carcassSpawned,
                carcassBlockCode = carcassBlockCode
            }
        };
    }

    PolisTestHarness.CommandResult ExecuteSpawnEntityCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        // Usage: spawnentity <entityCode> [x y z]
        // Spawns any entity (not registered as a bot) - useful for testing butcher, interact, etc.
        if (args.Length < 1)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Usage: spawnentity <entityCode> [x y z]" };
        }

        string entityCode = args[0];
        double x = 0, y = 0, z = 0;
        bool hasCoords = false;

        if (args.Length >= 4)
        {
            if (!double.TryParse(args[1], out x) || !double.TryParse(args[2], out y) || !double.TryParse(args[3], out z))
            {
                return new PolisTestHarness.CommandResult { Ok = false, Message = "Invalid coordinates" };
            }
            hasCoords = true;
        }

        // Try context player for spawn position if no coords given
        if (!hasCoords)
        {
            if (TryGetContextPlayer(context, out var ctxPlayer, out _))
            {
                var playerPos = ctxPlayer.Entity.ServerPos;
                var yaw = playerPos.Yaw;
                x = playerPos.X + Math.Sin(yaw) * 2;
                y = playerPos.Y;
                z = playerPos.Z + Math.Cos(yaw) * 2;
            }
            else
            {
                // Fallback to world spawn
                x = sapi.World.DefaultSpawnPosition.X;
                y = sapi.World.DefaultSpawnPosition.Y;
                z = sapi.World.DefaultSpawnPosition.Z;
            }
        }

        // Resolve entity type
        var entityType = sapi.World.GetEntityType(new AssetLocation(entityCode));
        if (entityType == null)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"Unknown entity type: {entityCode}" };
        }

        // Create and spawn entity
        var entity = sapi.World.ClassRegistry.CreateEntity(entityType);
        if (entity == null)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"Failed to create entity: {entityCode}" };
        }

        entity.ServerPos.SetPos(x, y, z);
        if (TryGetContextPlayer(context, out var contextPlayer, out _))
        {
            entity.ServerPos.Dimension = contextPlayer.Entity.ServerPos.Dimension;
        }
        entity.Pos.SetFrom(entity.ServerPos);
        sapi.World.SpawnEntity(entity);

        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = $"Spawned entity #{entity.EntityId} ({entityType.Code.ToShortString()}) at ({x:F1}, {y:F1}, {z:F1})",
            Data = new { id = entity.EntityId, code = entityType.Code.ToShortString(), pos = new[] { x, y, z } }
        };
    }

    PolisTestHarness.CommandResult ExecuteKillEntityCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        // Usage: killentity <entityId>
        // Instantly kills an entity by setting health to 0 - useful for testing butcher action
        if (args.Length < 1 || !long.TryParse(args[0], out var entityId))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Usage: killentity <entityId>" };
        }

        var entity = sapi.World.GetEntityById(entityId);
        if (entity == null)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"Entity {entityId} not found" };
        }

        if (!entity.Alive)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"Entity {entityId} is already dead" };
        }

        // Kill the entity by dealing massive damage
        var damageSource = new DamageSource
        {
            Type = EnumDamageType.Gravity,  // Use gravity damage (fall damage) for natural death
            Source = EnumDamageSource.Fall
        };

        // Get current health and deal lethal damage
        var healthTree = entity.WatchedAttributes.GetTreeAttribute("health");
        float maxHealth = healthTree?.GetFloat("maxhealth", 10f) ?? 10f;
        entity.ReceiveDamage(damageSource, maxHealth * 2);

        // Verify death
        bool isDead = !entity.Alive;
        string entityCode = entity.Code?.ToShortString() ?? "unknown";

        return new PolisTestHarness.CommandResult
        {
            Ok = isDead,
            Message = isDead
                ? $"Killed entity #{entityId} ({entityCode})"
                : $"Entity #{entityId} ({entityCode}) survived damage (health may have been modified)"
        };
    }

    PolisTestHarness.CommandResult ExecuteTeleportCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        // Usage: teleport <playerUid or playerName> <x> <y> <z> [yaw] [pitch]
        // Teleports a player to the specified position with optional view
        // direction. A NAME as well as a uid is accepted: the agent brains
        // only ever know the display name, and a human types the name
        // (2026-10-10: 'the system doesn't recognize dingsdangser').
        if (args.Length < 4)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Usage: teleport <playerUid or playerName> <x> <y> <z> [yaw] [pitch]" };
        }

        var playerUid = args[0];
        if (!double.TryParse(args[1], NumberStyles.Float, CultureInfo.InvariantCulture, out var x) ||
            !double.TryParse(args[2], NumberStyles.Float, CultureInfo.InvariantCulture, out var y) ||
            !double.TryParse(args[3], NumberStyles.Float, CultureInfo.InvariantCulture, out var z))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Invalid coordinates. Expected numeric x, y, z values." };
        }

        // Optional yaw and pitch (in radians)
        float yaw = 0f;
        float pitch = 0f;
        bool hasOrientation = false;

        if (args.Length >= 5)
        {
            if (!float.TryParse(args[4], NumberStyles.Float, CultureInfo.InvariantCulture, out yaw))
            {
                return new PolisTestHarness.CommandResult { Ok = false, Message = "Invalid yaw. Expected numeric value in radians." };
            }
            hasOrientation = true;
        }

        if (args.Length >= 6)
        {
            if (!float.TryParse(args[5], NumberStyles.Float, CultureInfo.InvariantCulture, out pitch))
            {
                return new PolisTestHarness.CommandResult { Ok = false, Message = "Invalid pitch. Expected numeric value in radians." };
            }
        }

        // Find the player: uid first, then name (case-insensitive).
        // AllOnlinePlayers is IEnumerable<IPlayer> - filter to server
        // players (the players route does the same OfType).
        var player = sapi.World.PlayerByUid(playerUid) as IServerPlayer;
        if (player == null)
        {
            foreach (var p in sapi.World.AllOnlinePlayers)
            {
                var sp = p as IServerPlayer;
                if (sp != null &&
                    string.Equals(sp.PlayerName, playerUid, StringComparison.OrdinalIgnoreCase))
                {
                    player = sp;
                    break;
                }
            }
        }
        if (player == null)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"Player not found: {playerUid} (expected a player uid or name)" };
        }

        var entity = player.Entity;
        if (entity == null)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"Player entity not loaded: {playerUid}" };
        }

        // Teleport with or without orientation
        if (hasOrientation)
        {
            var targetPitch = NormalizeTeleportPitch(pitch);
            var newPos = new EntityPos(x, y, z, yaw, targetPitch);
            entity.TeleportTo(newPos);

            // Send packet to client to set camera direction
            serverChannel.SendPacket(new PolisSetViewDirectionPacket { Yaw = yaw, Pitch = targetPitch }, player);
        }
        else
        {
            entity.TeleportTo(new Vec3d(x, y, z));
        }

        var msg = hasOrientation
            ? $"Teleported {player.PlayerName} to ({x:F1}, {y:F1}, {z:F1}) facing yaw={yaw:F2} pitch={pitch:F2}"
            : $"Teleported {player.PlayerName} to ({x:F1}, {y:F1}, {z:F1})";

        return new PolisTestHarness.CommandResult { Ok = true, Message = msg };
    }

    /// <summary>
    /// Convert intuitive pitch (0=level, positive=up, negative=down) to VS internal pitch.
    /// VS uses: π/2 (up) to 3π/2 (down), with π = level.
    /// </summary>
    private static float NormalizeTeleportPitch(float inputPitch)
    {
        float vsPitch = (float)Math.PI - inputPitch;
        // ~3° short of the poles: AT exactly ±90° (π/2, 3π/2) the client's
        // view-direction math degenerates and the physics step produces NaN
        // (process crash 2026-09-26, rapid UI camera clicks). The UI clamps
        // the input to the same margin (app.js).
        const float MinPitch = 1.62f;  // π/2 + 0.05
        const float MaxPitch = 4.66f;  // 3π/2 - 0.05
        return Math.Clamp(vsPitch, MinPitch, MaxPitch);
    }

    PolisTestHarness.CommandResult ExecuteAnimateCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        // Get selected bot
        if (!TryGetHarnessBot(context, out var bot, out var err))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = err };
        }

        var entity = bot.Entity;
        if (entity == null)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Bot entity not loaded" };
        }

        // Handle stop command
        if (args.Length >= 1 && args[0].Equals("stop", StringComparison.OrdinalIgnoreCase))
        {
            return ExecuteAnimateStop(entity, bot, args.Length > 1 ? args[1] : null);
        }

        // Validate animation code
        if (args.Length < 1 || string.IsNullOrWhiteSpace(args[0]))
        {
            return new PolisTestHarness.CommandResult
            {
                Ok = false,
                Message = "Usage: animate <animCode> [speed] [loop] | animate stop [animCode]"
            };
        }

        string animCode = args[0].ToLowerInvariant();

        // Parse optional speed
        float speed = 1.0f;
        if (args.Length >= 2 && !args[1].Equals("loop", StringComparison.OrdinalIgnoreCase))
        {
            if (!float.TryParse(args[1], NumberStyles.Float, CultureInfo.InvariantCulture, out speed))
            {
                return new PolisTestHarness.CommandResult { Ok = false, Message = $"Invalid speed: {args[1]}" };
            }
            speed = GameMath.Clamp(speed, 0.1f, 10f);
        }

        // Parse optional loop flag
        bool loop = args.Any(a => a.Equals("loop", StringComparison.OrdinalIgnoreCase));

        // Apply per-bot speed modifier (stub for future skill system)
        float finalSpeed = ApplyBotAnimationSpeedModifiers(bot, animCode, speed);

        // Start animation
        var animMeta = new AnimationMetaData
        {
            Code = animCode,
            Animation = animCode,
            AnimationSpeed = finalSpeed,
            BlendMode = EnumAnimationBlendMode.Average
        }.Init();

        bool started = entity.AnimManager.StartAnimation(animMeta);

        if (!started)
        {
            return new PolisTestHarness.CommandResult
            {
                Ok = false,
                Message = $"Failed to start animation '{animCode}' (not found in shape?)"
            };
        }

        // Additional validation: VS AnimManager may return true even for invalid animations
        // Check if animation exists in the entity's shape definition
        var animator = entity.AnimManager.Animator;
        if (animator?.Animations != null)
        {
            bool animExists = animator.Animations.Any(a => a.Animation?.Code == animCode);
            if (!animExists)
            {
                // Stop the invalid animation that was added
                entity.AnimManager.StopAnimation(animCode);
                return new PolisTestHarness.CommandResult
                {
                    Ok = false,
                    Message = $"Animation '{animCode}' not found in entity shape"
                };
            }
        }

        // Track looping animations for cleanup
        if (loop)
        {
            TrackLoopingAnimation(bot, animCode);
        }
        else
        {
            // One-shot: schedule debug logging when animation finishes
            ScheduleOneShotAnimationStop(bot, animCode);
        }

        string loopNote = loop ? " (looping)" : " (one-shot)";
        string speedNote = Math.Abs(finalSpeed - speed) > 0.001f ? $" (modified from {speed:F2})" : "";
        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = $"Started animation '{animCode}' speed={finalSpeed:F2}{speedNote}{loopNote}"
        };
    }

    PolisTestHarness.CommandResult ExecuteAnimateStop(EntityAgent entity, BotState bot, string animCode)
    {
        if (string.IsNullOrWhiteSpace(animCode))
        {
            // Stop all - get active animations and stop each
            var active = entity.AnimManager.ActiveAnimationsByAnimCode;
            int count = active.Count;
            foreach (var code in active.Keys.ToList())
            {
                entity.AnimManager.StopAnimation(code);
            }
            // Clear tracked looping animations
            bot.LoopingAnimations?.Clear();
            return new PolisTestHarness.CommandResult
            {
                Ok = true,
                Message = $"Stopped {count} animation(s)"
            };
        }
        else
        {
            entity.AnimManager.StopAnimation(animCode);
            bot.LoopingAnimations?.Remove(animCode);
            return new PolisTestHarness.CommandResult
            {
                Ok = true,
                Message = $"Stopped animation '{animCode}'"
            };
        }
    }

    /// <summary>
    /// Stub for future skill system integration.
    /// Returns baseSpeed unchanged for now.
    /// </summary>
    float ApplyBotAnimationSpeedModifiers(BotState bot, string animCode, float baseSpeed)
    {
        // Future: multiply by bot.AnimSpeedModifiers.GlobalMultiplier, category multipliers, etc.
        return baseSpeed;
    }

    void TrackLoopingAnimation(BotState bot, string animCode)
    {
        bot.LoopingAnimations ??= new HashSet<string>();
        bot.LoopingAnimations.Add(animCode);
    }

    void ScheduleOneShotAnimationStop(BotState bot, string animCode)
    {
        // Check every 100ms if animation finished, log when done (debug mode only)
        long checkUntil = sapi.World.ElapsedMilliseconds + 10000; // 10s max

        void CheckAnimation(float dt)
        {
            if (bot.Entity == null) return;
            if (sapi.World.ElapsedMilliseconds > checkUntil) return;

            if (!bot.Entity.AnimManager.IsAnimationActive(animCode))
            {
                // Animation finished naturally
                if (debugEnabled)
                {
                    sapi.Logger.Debug($"[polis] Animation '{animCode}' finished on bot #{bot.Entity.EntityId}");
                }
                return;
            }

            // Still playing, check again
            sapi.Event.RegisterCallback(CheckAnimation, 100);
        }

        sapi.Event.RegisterCallback(CheckAnimation, 100);
    }

    PolisTestHarness.CommandResult ExecutePossessCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        // Require player context for possession
        if (!TryGetContextPlayer(context, out var player, out var ctxError))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = ctxError };
        }

        // Get selected bot
        if (!TryGetHarnessBot(context, out var bot, out var botError))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = botError };
        }

        // Check if player is already possessing
        if (activePossessions.ContainsKey(player.PlayerUID))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Already possessing a bot. Use unpossess first." };
        }

        // Check if bot is already possessed
        foreach (var kvp in activePossessions)
        {
            if (kvp.Value.Entity?.EntityId == bot.Entity.EntityId)
            {
                return new PolisTestHarness.CommandResult { Ok = false, Message = "This bot is already being possessed." };
            }
        }

        // Create the possession seat
        var seat = new PolisPossessableSeat(bot.Entity, debugEnabled);
        seat.OnPossessionStart = (passenger) =>
        {
            sapi.Logger.Notification($"[polis] HTTP Possess: Player {player.PlayerName} -> Bot {bot.Entity.EntityId}");
            bot.Activity?.CancelAll();
        };
        seat.OnPossessionEnd = (passenger) =>
        {
            sapi.Logger.Notification($"[polis] HTTP Unpossess: Player {player.PlayerName}");
            activePossessions.Remove(player.PlayerUID);
        };

        // Mount the player
        try
        {
            bool mounted = player.Entity.TryMount(seat);
            if (!mounted)
            {
                return new PolisTestHarness.CommandResult { Ok = false, Message = "Failed to mount for possession" };
            }
        }
        catch (Exception ex)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"Mount exception: {ex.Message}" };
        }

        activePossessions[player.PlayerUID] = seat;
        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = $"Player {player.PlayerName} now possessing bot {bot.Entity.EntityId}"
        };
    }

    PolisTestHarness.CommandResult ExecuteUnpossessCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        // Require player context
        if (!TryGetContextPlayer(context, out var player, out var ctxError))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = ctxError };
        }

        // Check if player is possessing
        if (!activePossessions.TryGetValue(player.PlayerUID, out var seat))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Not currently possessing a bot" };
        }

        // Unmount the player
        if (!player.Entity.TryUnmount())
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Failed to unmount from possession" };
        }

        // OnPossessionEnd callback will clean up activePossessions
        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = "Exited possession mode"
        };
    }

    PolisTestHarness.CommandResult ExecuteSetControlsCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        // Require player context
        if (!TryGetContextPlayer(context, out var player, out var ctxError))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = ctxError };
        }

        // Check if player is possessing
        if (!activePossessions.TryGetValue(player.PlayerUID, out var seat))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Not currently possessing a bot. Use possess first." };
        }

        // Parse control args: forward, backward, left, right, sprint, jump
        // Each is "true" or "false" (or missing = false)
        bool forward = args.Length > 0 && args[0].Equals("true", StringComparison.OrdinalIgnoreCase);
        bool backward = args.Length > 1 && args[1].Equals("true", StringComparison.OrdinalIgnoreCase);
        bool left = args.Length > 2 && args[2].Equals("true", StringComparison.OrdinalIgnoreCase);
        bool right = args.Length > 3 && args[3].Equals("true", StringComparison.OrdinalIgnoreCase);
        bool sprint = args.Length > 4 && args[4].Equals("true", StringComparison.OrdinalIgnoreCase);
        bool jump = args.Length > 5 && args[5].Equals("true", StringComparison.OrdinalIgnoreCase);

        // Set controls on the seat
        var controls = seat.Controls;
        controls.Forward = forward;
        controls.Backward = backward;
        controls.Left = left;
        controls.Right = right;
        controls.Sprint = sprint;
        controls.Jump = jump;
        controls.Sneak = false;

        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = $"Controls set: F={forward} B={backward} L={left} R={right} Sprint={sprint} Jump={jump}",
            Data = new { forward, backward, left, right, sprint, jump }
        };
    }

    PolisTestHarness.CommandResult ExecuteTestStateCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        long? botId = args.Length > 0 && long.TryParse(args[0], out var bid) ? bid : null;
        var state = GetTestStateResult(null, botId);

        return new PolisTestHarness.CommandResult
        {
            Ok = state.Error == null,
            Message = state.Error ?? "State retrieved",
            Data = state
        };
    }

    PolisTestHarness.CommandResult ExecuteBotsCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        var botList = bots.Values.Select(b => new
        {
            id = b.Entity.EntityId,
            code = b.Entity.Code?.ToString(),
            pos = new[] { b.Entity.ServerPos.X, b.Entity.ServerPos.Y, b.Entity.ServerPos.Z },
            lastAction = b.LastActionName != null ? new
            {
                name = b.LastActionName,
                ok = b.LastActionOk,
                msg = b.LastActionMsg,
                id = b.LastActionId,
                ms = b.LastActionMs
            } : null
        }).ToList();

        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = $"{botList.Count} bot(s) found",
            Data = new { bots = botList }
        };
    }

    // --- Hunger / Satiety introspection (the engine's EntityBehaviorHunger) ---
    //
    // Usage: hunger [botId]   (no arg: all bots + the local human player).
    // Reads the synced "hunger" tree attribute (currentsaturation/
    // maxsaturation, the five nutrition levels, the five delays) plus the
    // health tree. Pure read — no state changes.

    PolisTestHarness.CommandResult ExecuteHungerCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        var targets = new List<(string Label, Entity E)>();
        if (args.Length > 0 && long.TryParse(args[0], out var bid) && bots.TryGetValue(bid, out var singleBot))
        {
            targets.Add(("bot#" + bid, singleBot.Entity));
        }
        else
        {
            foreach (var b in bots.Values) targets.Add(("bot#" + b.Entity.EntityId, b.Entity));
            var lp = sapi.Server?.Players?.FirstOrDefault(p => p?.Entity != null);
            if (lp != null) targets.Add((lp.PlayerName + " (server player)", lp.Entity));
        }
        if (targets.Count == 0)
            return new PolisTestHarness.CommandResult { Ok = false, Message = "No bots and no local player found" };

        var rows = new List<object>();
        foreach (var (label, e) in targets)
        {
            var row = new Dictionary<string, object>
            {
                ["name"] = label,
                ["entityCode"] = e.Code?.ToString() ?? "?",
                ["hasHungerBehavior"] = e.GetBehavior<EntityBehaviorHunger>() != null,
            };

            var hunger = e.WatchedAttributes.GetTreeAttribute("hunger");
            if (hunger == null)
            {
                row["hunger"] = "ABSENT";
            }
            else
            {
                row["saturation"] = hunger.GetFloat("currentsaturation", 0f);
                row["maxSaturation"] = hunger.GetFloat("maxsaturation", 0f);
                row["levels"] = new Dictionary<string, float>
                {
                    ["fruit"] = hunger.GetFloat("fruitLevel", 0f),
                    ["vegetable"] = hunger.GetFloat("vegetableLevel", 0f),
                    ["protein"] = hunger.GetFloat("proteinLevel", 0f),
                    ["grain"] = hunger.GetFloat("grainLevel", 0f),
                    ["dairy"] = hunger.GetFloat("dairyLevel", 0f),
                };
                row["delays"] = new Dictionary<string, float>
                {
                    ["fruit"] = hunger.GetFloat("saturationlossdelayfruit", 0f),
                    ["vegetable"] = hunger.GetFloat("saturationlossdelayvegetable", 0f),
                    ["protein"] = hunger.GetFloat("saturationlossdelayprotein", 0f),
                    ["grain"] = hunger.GetFloat("saturationlossdelaygrain", 0f),
                    ["dairy"] = hunger.GetFloat("saturationlossdelaydairy", 0f),
                };
            }

            var health = e.WatchedAttributes.GetTreeAttribute("health");
            row["health"] = health?.GetFloat("currenthealth", 0f) ?? 0f;
            row["maxHealth"] = health?.GetFloat("maxhealth", 0f) ?? 0f;

            rows.Add(row);
        }

        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = $"{rows.Count} entity(ies)",
            Data = new { entities = rows },
        };
    }

    // --- Eat (the engine's own satiety path) ---
    //
    // Usage: eat <itemCode> [count=1]   [botId via select/POLIS_BOT_ID]
    // Gives the bot the item if it doesn't hold it, then per unit calls
    // Entity.ReceiveSaturation with the item's FoodNutritionProperties
    // (dispatches into EntityBehaviorHunger: clamping, nutrition levels,
    // delays, client sync — the same path a human's right-click-eat takes),
    // applies the item's Health field (negative = damage), consumes one
    // stack and hands back the EatenStack if the item defines one.

    PolisTestHarness.CommandResult ExecuteEatCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        if (args.Length < 1)
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Usage: eat <itemCode> [count=1]" };
        if (!TryGetHarnessBot(context, out var bot, out var selErr))
            return new PolisTestHarness.CommandResult { Ok = false, Message = selErr };

        string code = args[0];
        int count = 1;
        if (args.Length > 1) int.TryParse(args[1], out count);
        if (count < 1) count = 1;

        // The policy gate and the engine's satiety path live in the
        // shared eat core (PolisEatService) — the same code the forage
        // and feed skills run through. This command's only privilege on
        // top: it may hand the bot food it doesn't carry yet.
        string owner = null;
        if (globalData.Bots.TryGetValue(bot.Entity.EntityId, out var rec)) owner = rec.OwnerUid;

        var e = bot.Entity;
        int have = PolisInventoryHelpers.CountBotItems(e, code);
        if (have < count)
        {
            if (!TryResolveStack(code, count - have, out var toGive, out string giveErr2))
                return new PolisTestHarness.CommandResult { Ok = false, Message = giveErr2 };
            if (!PolisInventoryHelpers.TryInsertIntoBotInventory(e, toGive, out _, out string giveErr))
                return new PolisTestHarness.CommandResult { Ok = false, Message = $"Could not give {code}: {giveErr}" };
        }

        var (ok, reason, before, after, units) = PolisEatService.Eat(e, owner, code, count, sapi.Logger.Debug);

        string category = null;
        if (TryResolveStack(code, 1, out var unit2, out _))
        {
            var c2 = unit2.Collectible;
            var nut2 = c2?.GetNutritionProperties(sapi.World, unit2, e) ?? c2?.NutritionProps;
            category = nut2?.FoodCategory.ToString();
        }

        return new PolisTestHarness.CommandResult
        {
            Ok = ok,
            Message = ok
                ? $"Ate {units}x {code}{(category != null ? $" ({category})" : "")}: {before:F1} -> {after:F1} saturation"
                : $"eat failed: {reason}",
            Data = new
            {
                item = code,
                category,
                before,
                after,
                units,
            },
        };
    }

    // --- Hunger drain gate (parked bots / debug) ---
    // Usage: hungerpause [on|off]   (toggles the selected bot's
    // EntityPolisBot.HungerSuspended: the polis hunger behavior suspends
    // the engine drain while set; the policy engine will own this for
    // parked bots later).

    // --- Hunger drain gate (parked bots / debug) ---
    // Usage: hungerpause            → query (no state change)
    //        hungerpause on|off     → set the selected bot's
    //        EntityPolisBot.HungerSuspended (the polis hunger behavior
    //        suspends the engine drain while set).

    PolisTestHarness.CommandResult ExecuteHungerPauseCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        string mode = null;
        if (args.Length > 0 && (args[0] == "on" || args[0] == "off"))
        {
            mode = args[0];
        }
        if (!TryGetHarnessBot(context, out var bot, out var err))
            return new PolisTestHarness.CommandResult { Ok = false, Message = err };
        var pb = bot.Entity as EntityPolisBot;
        if (pb == null)
            return new PolisTestHarness.CommandResult { Ok = false, Message = "selected entity is not a polisbot" };

        float sat = pb.WatchedAttributes.GetTreeAttribute("hunger")?.GetFloat("currentsaturation", 0f) ?? 0f;
        if (mode == null)
        {
            // query — a no-arg call must not toggle state
            return new PolisTestHarness.CommandResult
            {
                Ok = true,
                Message = $"hunger drain {(pb.HungerSuspended ? "suspended" : "active")} (saturation {sat:F0}/1500)",
                Data = new { hungerSuspended = pb.HungerSuspended, saturation = sat, foraging = IsForaging(bot.Entity.EntityId) },
            };
        }
        pb.HungerSuspended = mode == "on";
        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = $"hunger drain {mode} (saturation {sat:F0}/1500)",
            Data = new { hungerSuspended = pb.HungerSuspended, saturation = sat, foraging = IsForaging(bot.Entity.EntityId) },
        };
    }

    // --- Forage / feed (the food-pressure skills, manual entry) ---
    // Usage: forage
    //   Start a forage episode on the selected bot NOW (manual entry to
    //   the machine the food-pressure interrupt uses): discover a wild
    //   fruiting bush (policy patterns), walk to it, harvest the fruit
    //   into its cargo, eat it (policy-gated). Preempts the current job
    //   at the policy's safe point. Thresholds come from the owner's
    //   policy profile; this command bypasses the saturation check but
    //   not the policy.
    //
    // Usage: feed <x> <y> <z> [itemCode] [count]
    //   Same machine with a known storage container (a storage vessel):
    //   walk to it, take a policy-allowed edible stack (itemCode when
    //   given), eat it. The pilot's survival story: the bot notices the
    //   pressure and feeds from its own storage before it starves.

    PolisTestHarness.CommandResult ExecuteForageCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        if (!TryGetHarnessBot(context, out var bot, out var selErr))
            return new PolisTestHarness.CommandResult { Ok = false, Message = selErr };
        if (IsForaging(bot.Entity.EntityId))
            return new PolisTestHarness.CommandResult { Ok = false, Message = "bot is already in a forage episode" };

        string owner = null;
        if (globalData.Bots.TryGetValue(bot.Entity.EntityId, out var rec)) owner = rec.OwnerUid;
        var (trigger, rearm) = PolisPolicyEngine.Instance.GetFoodPressure(owner);

        bool started = StartForageEpisode(bot, "wild", owner, trigger, rearm, "manual");
        return new PolisTestHarness.CommandResult
        {
            Ok = started,
            Message = started
                ? $"bot#{bot.Entity.EntityId}: forage episode started (manual; trigger={trigger:0.##}, rearm={rearm:0.##})"
                : "forage episode could not start (bot busy or no scan ring)",
            Data = new { bot = bot.Entity.EntityId, cause = "manual", trigger, rearm },
        };
    }

    PolisTestHarness.CommandResult ExecuteFeedCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        if (args.Length < 3)
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Usage: feed <x> <y> <z> [itemCode] [count]" };
        if (!TryGetHarnessBot(context, out var bot, out var selErr))
            return new PolisTestHarness.CommandResult { Ok = false, Message = selErr };
        if (IsForaging(bot.Entity.EntityId))
            return new PolisTestHarness.CommandResult { Ok = false, Message = "bot is already in a forage episode" };

        if (!int.TryParse(args[0], out int x) || !int.TryParse(args[1], out int y) || !int.TryParse(args[2], out int z))
            return new PolisTestHarness.CommandResult { Ok = false, Message = "invalid container coordinates" };
        string code = args.Length > 3 ? args[3] : null;
        int count = args.Length > 4 && int.TryParse(args[4], out int c) ? c : 0;

        var cpos = new BlockPos(x, y, z);
        if (!(sapi.World.BlockAccessor.GetBlockEntity(cpos) is IBlockEntityContainer))
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"no container at {x},{y},{z}" };

        string owner = null;
        if (globalData.Bots.TryGetValue(bot.Entity.EntityId, out var rec)) owner = rec.OwnerUid;
        var (trigger, rearm) = PolisPolicyEngine.Instance.GetFoodPressure(owner);

        bool started = StartForageEpisode(bot, "container", owner, trigger, rearm, "manual", cpos, code);
        if (started && count > 0)
            forageEpisodes[bot.Entity.EntityId].FeedCount = count;
        return new PolisTestHarness.CommandResult
        {
            Ok = started,
            Message = started
                ? $"bot#{bot.Entity.EntityId}: feed episode started (manual; container {x},{y},{z}{(code != null ? $", item {code}" : "")})"
                : "feed episode could not start (bot busy)",
            Data = new { bot = bot.Entity.EntityId, cause = "manual", container = new[] { x, y, z }, item = code, count },
        };
    }

    // --- Policy introspection (the interaction-rules layer) ---
    // Usage: policy                              → dump the policy file
    //        policy <domain> <itemCode>          → evaluate (default profile)
    //        policy <domain> <itemCode> <player> → evaluate for a player profile

    PolisTestHarness.CommandResult ExecutePolicyCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        if (args.Length == 0)
        {
            string path = PolisPolicyEngine.Instance.AutoInit();
            if (path == null || !System.IO.File.Exists(path))
                return new PolisTestHarness.CommandResult { Ok = false, Message = $"policy file not found: {path}" };
            return new PolisTestHarness.CommandResult
            {
                Ok = true,
                Message = "policy file",
                Data = new
                {
                    path,
                    mtime = System.IO.File.GetLastWriteTimeUtc(path).ToString("o"),
                    file = System.IO.File.ReadAllText(path),
                },
            };
        }
        if (args.Length < 2)
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Usage: policy [domain <itemCode>]" };

        string domain = args[0];
        string code = args[1];
        string player = args.Length > 2 ? args[2] : null;

        // Resolve the food category (needed for category-based rules)
        string category = null;
        if (TryResolveStack(code, 1, out var unit, out _))
        {
            var c = unit.Collectible;
            var nut = c?.GetNutritionProperties(sapi.World, unit, null) ?? c?.NutritionProps;
            category = nut?.FoodCategory.ToString();
        }

        var (allowed, reason) = PolisPolicyEngine.Instance.Evaluate(player, domain, code, category);
        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = $"{domain}/{code}{(player != null ? " [" + player + "]" : "")}: {(allowed ? "allow" : "deny")} ({reason})",
            Data = new { domain, item = code, player = player ?? "default", category, allow = allowed, reason },
        };
    }

    bool TryGetContextPlayer(PolisTestHarness.CommandContext context, out IServerPlayer player, out string error)
    {
        player = null;
        error = null;

        if (context == null || string.IsNullOrWhiteSpace(context.PlayerUid))
        {
            error = "playerUid required in context";
            return false;
        }

        player = sapi.World.PlayerByUid(context.PlayerUid) as IServerPlayer;
        if (player?.Entity == null)
        {
            error = "Player not found or missing entity";
            return false;
        }

        return true;
    }

    bool TryParseOffset(double[] raw, out Vec3d offset, out string error)
    {
        offset = null;
        error = null;

        if (raw == null) return false;
        if (raw.Length != 3)
        {
            error = "Offset must be [x, y, z]";
            return false;
        }

        offset = new Vec3d(raw[0], raw[1], raw[2]);
        return true;
    }

    bool TryGetHarnessBot(PolisTestHarness.CommandContext context, out BotState bot, out string error)
    {
        bot = null;
        error = null;

        // Check for explicit bot ID in context first
        if (context?.BotId != null && bots.TryGetValue(context.BotId.Value, out bot))
        {
            return true;
        }

        // Check if we have a selected bot for this player
        if (!string.IsNullOrEmpty(context?.PlayerUid) &&
            selectedByPlayer.TryGetValue(context.PlayerUid, out var playerSelectedId) &&
            bots.TryGetValue(playerSelectedId, out bot))
        {
            return true;
        }

        // Check if we have a selected bot for harness (no player context)
        if (selectedByPlayer.TryGetValue("harness", out var selectedId) && bots.TryGetValue(selectedId, out bot))
        {
            return true;
        }

        // Don't silently fall back - require explicit selection
        error = "No bot selected. Use 'select <botId>' first or set POLIS_BOT_ID.";
        return false;
    }

    // --- Zone Commands ---

    PolisTestHarness.CommandResult ExecuteZoneDefineCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        // Usage: zone-define <name> <x1> <y1> <z1> <x2> <y2> <z2>
        if (args.Length < 7)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Usage: zone-define <name> <x1> <y1> <z1> <x2> <y2> <z2>" };
        }

        string name = args[0];
        if (string.IsNullOrWhiteSpace(name))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Zone name cannot be empty" };
        }

        if (!int.TryParse(args[1], out var x1) || !int.TryParse(args[2], out var y1) || !int.TryParse(args[3], out var z1) ||
            !int.TryParse(args[4], out var x2) || !int.TryParse(args[5], out var y2) || !int.TryParse(args[6], out var z2))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Invalid coordinates" };
        }

        var bounds = new Cuboidi(
            Math.Min(x1, x2), Math.Min(y1, y2), Math.Min(z1, z2),
            Math.Max(x1, x2), Math.Max(y1, y2), Math.Max(z1, z2)
        );
        zoneRegistry.RegisterZone(name, bounds);

        if (debugEnabled)
        {
            sapi.Logger.Debug($"[polis] zone-define: '{name}' ({bounds.X1},{bounds.Y1},{bounds.Z1}) to ({bounds.X2},{bounds.Y2},{bounds.Z2})");
        }

        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = $"Zone '{name}' defined: ({bounds.X1},{bounds.Y1},{bounds.Z1}) to ({bounds.X2},{bounds.Y2},{bounds.Z2})",
            Data = new
            {
                name,
                bounds = new { x1 = bounds.X1, y1 = bounds.Y1, z1 = bounds.Z1, x2 = bounds.X2, y2 = bounds.Y2, z2 = bounds.Z2 }
            }
        };
    }

    PolisTestHarness.CommandResult ExecuteZoneRemoveCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        if (args.Length < 1 || string.IsNullOrWhiteSpace(args[0]))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Usage: zone-remove <name>" };
        }

        string name = args[0];
        if (!zoneRegistry.RemoveZone(name))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"Zone '{name}' not found" };
        }

        if (debugEnabled)
        {
            sapi.Logger.Debug($"[polis] zone-remove: '{name}'");
        }

        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = $"Zone '{name}' removed",
            Data = new { name }
        };
    }

    PolisTestHarness.CommandResult ExecuteZoneListCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        var allZones = zoneRegistry.GetAllZones();
        var zones = new List<object>();
        foreach (var kvp in allZones)
        {
            var b = kvp.Value.Bounds;
            zones.Add(new
            {
                name = kvp.Key,
                bounds = new { x1 = b.X1, y1 = b.Y1, z1 = b.Z1, x2 = b.X2, y2 = b.Y2, z2 = b.Z2 }
            });
        }

        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = $"Found {zones.Count} zone(s)",
            Data = new { count = zones.Count, zones }
        };
    }

    PolisTestHarness.CommandResult ExecuteZoneCheckCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        // Optional botId as first arg
        BotState bot;
        string error;
        long botId;

        if (args.Length > 0 && long.TryParse(args[0], out botId) && bots.TryGetValue(botId, out bot))
        {
            // Explicit bot ID
        }
        else if (TryGetHarnessBot(context, out bot, out error))
        {
            botId = bot.Entity.EntityId;
        }
        else
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = error };
        }

        var pos = bot.Entity.ServerPos.AsBlockPos;
        var zones = zoneRegistry.GetZonesAt(pos);

        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = zones.Count > 0 ? $"Bot {botId} is in: {string.Join(", ", zones)}" : $"Bot {botId} is not in any zone",
            Data = new { botId, zones, pos = new[] { pos.X, pos.Y, pos.Z } }
        };
    }

    PolisTestHarness.CommandResult ExecuteZoneShowCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        if (args.Length < 1 || string.IsNullOrWhiteSpace(args[0]))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Usage: zone-show <name>" };
        }

        string name = args[0];
        var zone = zoneRegistry.GetZone(name);
        if (zone == null)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"Zone '{name}' not found" };
        }

        // Get player to send highlight to
        IServerPlayer player = null;
        if (context != null && !string.IsNullOrWhiteSpace(context.PlayerUid))
        {
            player = sapi.World.PlayerByUid(context.PlayerUid) as IServerPlayer;
        }
        if (player == null)
        {
            // Fall back to first online player
            foreach (var p in sapi.World.AllOnlinePlayers)
            {
                player = p as IServerPlayer;
                if (player != null) break;
            }
        }
        if (player == null)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "No player available to show highlight" };
        }

        HighlightZone(player, zone.Bounds);

        if (debugEnabled)
        {
            sapi.Logger.Debug($"[polis] zone-show: '{name}' to player {player.PlayerName}");
        }

        var b = zone.Bounds;
        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = $"Highlighting zone '{name}'",
            Data = new
            {
                name,
                bounds = new { x1 = b.X1, y1 = b.Y1, z1 = b.Z1, x2 = b.X2, y2 = b.Y2, z2 = b.Z2 },
                player = player.PlayerName
            }
        };
    }

    // --- Viewpoint Commands ---

    PolisTestHarness.CommandResult ExecuteViewpointDefineCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        // Usage: viewpoint-define <name> <x> <y> <z> <yaw> <pitch> [station]
        if (args.Length < 6)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Usage: viewpoint-define <name> <x> <y> <z> <yaw> <pitch> [station]" };
        }

        string name = args[0];
        if (string.IsNullOrWhiteSpace(name))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Viewpoint name cannot be empty" };
        }

        if (!double.TryParse(args[1], NumberStyles.Float, CultureInfo.InvariantCulture, out var x) ||
            !double.TryParse(args[2], NumberStyles.Float, CultureInfo.InvariantCulture, out var y) ||
            !double.TryParse(args[3], NumberStyles.Float, CultureInfo.InvariantCulture, out var z))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Invalid coordinates. Expected numeric x, y, z values." };
        }

        if (!float.TryParse(args[4], NumberStyles.Float, CultureInfo.InvariantCulture, out var yaw) ||
            !float.TryParse(args[5], NumberStyles.Float, CultureInfo.InvariantCulture, out var pitch))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Invalid orientation. Expected numeric yaw, pitch values in radians." };
        }

        string station = args.Length > 6 ? args[6] : null;

        var viewpoint = new ViewpointRecord
        {
            Name = name,
            X = x,
            Y = y,
            Z = z,
            Yaw = yaw,
            Pitch = pitch,
            StationName = station
        };

        bool isUpdate = globalData.Viewpoints.ContainsKey(name);
        globalData.Viewpoints[name] = viewpoint;

        if (debugEnabled)
        {
            sapi.Logger.Debug($"[polis] viewpoint-define: '{name}' at ({x:F1}, {y:F1}, {z:F1}) yaw={yaw:F2} pitch={pitch:F2}");
        }

        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = isUpdate ? $"Updated viewpoint '{name}'" : $"Created viewpoint '{name}'",
            Data = new { name, x, y, z, yaw, pitch, station, isUpdate }
        };
    }

    PolisTestHarness.CommandResult ExecuteViewpointListCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        var viewpoints = globalData.Viewpoints.Values
            .Select(v => new
            {
                name = v.Name,
                x = v.X,
                y = v.Y,
                z = v.Z,
                yaw = v.Yaw,
                pitch = v.Pitch,
                station = v.StationName
            })
            .ToList();

        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = $"Found {viewpoints.Count} viewpoint(s)",
            Data = new { count = viewpoints.Count, viewpoints }
        };
    }

    PolisTestHarness.CommandResult ExecuteViewpointRemoveCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        if (args.Length < 1 || string.IsNullOrWhiteSpace(args[0]))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Usage: viewpoint-remove <name>" };
        }

        string name = args[0];
        if (!globalData.Viewpoints.ContainsKey(name))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"Viewpoint '{name}' not found" };
        }

        globalData.Viewpoints.Remove(name);

        if (debugEnabled)
        {
            sapi.Logger.Debug($"[polis] viewpoint-remove: '{name}'");
        }

        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = $"Removed viewpoint '{name}'"
        };
    }

    PolisTestHarness.CommandResult ExecuteObserverScreenshotCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        // This command requires async callback handling - use the HTTP endpoint instead
        // GET /polis/observer-screenshot?playerUid=&x=&y=&z=&yaw=&pitch=&save=false
        return new PolisTestHarness.CommandResult
        {
            Ok = false,
            Message = "Use GET /polis/observer-screenshot endpoint instead. The command handler cannot support async screenshot callbacks."
        };
    }

    PolisTestHarness.CommandResult ExecuteViewpointScreenshotCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        // This command requires async callback handling - use poliscli viewpoint-screenshot instead
        // which looks up the viewpoint and calls the HTTP endpoint
        return new PolisTestHarness.CommandResult
        {
            Ok = false,
            Message = "Use poliscli viewpoint-screenshot command or the /polis/observer-screenshot endpoint. The command handler cannot support async screenshot callbacks."
        };
    }

    // 1.22.7 headless grid crafting (no workbench block in this build):
    // runs the game's own GridRecipe engine (Matches + ConseeInput) against
    // the bot's cargo inventory and returns the resolved output to it.
    // Usage: craft <output-code>
    PolisTestHarness.CommandResult ExecuteCraftCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        if (args.Length < 1)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Usage: craft <output-code>" };
        }

        if (!TryGetHarnessBot(context, out var bot, out var err))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = err };
        }

        string code = args[0];

        // GridRecipe needs an IPlayer as its actor; the bot's owner is
        // the identity (the cargo slots are the ingredient source).
        // Fallback: the command-sending player (singleplayer: the local
        // player - a bot spawned before the current character session
        // has an unresolvable owner uid, which must not dead-end craft).
        IServerPlayer ownerPlayer = null;
        if (globalData.Bots.TryGetValue(bot.Entity.EntityId, out var botRecord))
        {
            ownerPlayer = sapi.World.PlayerByUid(botRecord.OwnerUid) as IServerPlayer;
        }
        if (ownerPlayer == null && TryGetContextPlayer(context, out var ctxPlayer, out var _))
        {
            ownerPlayer = ctxPlayer as IServerPlayer;
        }

        void OnResult(bool ok, string msg)
        {
            bot.RecordActionResult("craft", ok, msg, sapi.World.ElapsedMilliseconds);
        }

        var action = new PolisCraftAction(
            code,
            ownerPlayer,
            debugEnabled ? msg => sapi.Logger.Debug($"[polis] {msg}") : null,
            OnResult);

        StartActionSequence(bot, "craft", action);

        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = $"Bot #{bot.Entity.EntityId} crafting {code} (result lands in state action results)",
            Data = new { output = code }
        };
    }

    // --- A1: vitals ---

    PolisTestHarness.CommandResult ExecuteVitalsCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        // Usage: vitals [uid]   (uid = numeric EntityId or name; absent = all)
        string uid = args != null && args.Length > 0 ? args[0] : null;

        if (!VitalsHasEntity(uid))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"no vitals for uid '{uid}' (not sampled: offline bot or unknown name)" };
        }

        var payload = GetVitalsEndpointPayload(uid);
        string msg = string.IsNullOrWhiteSpace(uid)
            ? ("vitals for " + vitalsLatest.Count + (vitalsLatest.Count == 1 ? "y" : "ies"))
            : ("vitals for '" + uid + "'");
        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = msg,
            Data = payload
        };
    }

    // --- A3: zone-rename ---

    PolisTestHarness.CommandResult ExecuteZoneRenameCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        // Usage: zone-rename <old> <new>
        if (args.Length < 2 || string.IsNullOrWhiteSpace(args[0]) || string.IsNullOrWhiteSpace(args[1]))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Usage: zone-rename <old> <new>" };
        }

        if (zoneRegistry == null)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "zone registry not initialized (world not loaded?)" };
        }

        string oldName = args[0];
        string newName = args[1];

        if (!zoneRegistry.RenameZone(oldName, newName, out var err))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = err };
        }

        var bounds = zoneRegistry.GetZone(newName).Bounds;
        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = $"zone '{oldName}' renamed to '{newName}' (bounds preserved; persists with the world save)",
            Data = new
            {
                old = oldName,
                name = newName,
                bounds = new { x1 = bounds.X1, y1 = bounds.Y1, z1 = bounds.Z1, x2 = bounds.X2, y2 = bounds.Y2, z2 = bounds.Z2 }
            }
        };
    }

    // --- A3: pick ---

    PolisTestHarness.CommandResult ExecutePickCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        // Usage: pick <x> <y> <z> [count]
        if (args.Length < 3 ||
            !int.TryParse(args[0], out int x) ||
            !int.TryParse(args[1], out int y) ||
            !int.TryParse(args[2], out int z))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Usage: pick <x> <y> <z> [count]" };
        }

        int count = 1;
        if (args.Length >= 4 && int.TryParse(args[3], out int parsedCount))
        {
            count = Math.Max(1, Math.Min(16, parsedCount));
        }

        if (!TryGetHarnessBot(context, out var bot, out var err))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = err };
        }

        // The pick is attributed to a player (audit line, onitemcollected,
        // claims): the bot's owner, else the command-sending player.
        IServerPlayer ownerPlayer = null;
        if (globalData.Bots.TryGetValue(bot.Entity.EntityId, out var botRecord))
        {
            ownerPlayer = sapi.World.PlayerByUid(botRecord.OwnerUid) as IServerPlayer;
        }
        if (ownerPlayer == null && TryGetContextPlayer(context, out var ctxPlayer, out var _))
        {
            ownerPlayer = ctxPlayer as IServerPlayer;
        }
        if (ownerPlayer == null)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "no player to attribute the pick to (bot has no owner and no player in context)" };
        }

        var world = sapi.World;
        var pos = new BlockPos(x, y, z);

        // The pick happens in person: the bot has to be next to the bush.
        var center = new Vec3d(pos.X + 0.5, pos.Y + 0.5, pos.Z + 0.5);
        double dist = bot.Entity.ServerPos.XYZ.DistanceTo(center);
        if (dist > 3.0)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"bot not adjacent to the bush ({dist:F1} blocks away; walk it over first)" };
        }

        var block = world.BlockAccessor.GetBlock(pos);
        if (block == null || block.Id == 0)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"no block at {pos}" };
        }
        if (block.GetBehavior<BlockBehaviorFruitingBush>() == null)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"block {block.Code} is not a fruiting bush (use 'harvest' for harvestable crops)" };
        }

        var bush = world.BlockAccessor.GetBlockEntity(pos)?.GetBehavior<BEBehaviorFruitingBush>();
        if (bush == null)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"bush at {pos} has no block-entity state" };
        }
        if (bush.BState.Growthstate != EnumFruitingBushGrowthState.Ripe)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"bush not ripe (growth state: {bush.BState.Growthstate}; 'ripen' it first)" };
        }

        var blockSel = new BlockSelection
        {
            Position = pos,
            Face = BlockFacing.UP,
            HitPosition = new Vec3d(0.5, 0.5, 0.5),
            Block = block
        };

        var agent = bot.Entity as EntityAgent;
        var debug = debugEnabled ? (Action<string>)(msg => sapi.Logger.Debug($"[polis] {msg}")) : null;

        int totalPicked = 0;
        for (int round = 0; round < count; round++)
        {
            if (bush.BState.Growthstate != EnumFruitingBushGrowthState.Ripe)
            {
                break; // a pick advances the bush to Mature; it regrows to Ripe over time
            }

            // First round through the vanilla start gate (claims +
            // ripeness re-check + start sound), like the action's Start.
            if (round == 0)
            {
                EnumHandling handling = EnumHandling.PassThrough;
                if (!bush.OnBlockInteractStart(world, ownerPlayer, blockSel, ref handling))
                {
                    return new PolisTestHarness.CommandResult { Ok = false, Message = "interaction blocked (bush state or claims)" };
                }
            }

            totalPicked += PolisPickBushAction.CompletePickToBot(world, agent, bush, blockSel, ownerPlayer, debug);
        }

        bot.RecordActionResult("pick", totalPicked > 0, $"picked {totalPicked}x berries from {block.Code}", sapi.World.ElapsedMilliseconds);

        return new PolisTestHarness.CommandResult
        {
            Ok = totalPicked > 0,
            Message = totalPicked > 0
                ? $"picked {totalPicked}x from {block.Code} at {pos} (bush now {bush.BState.Growthstate})"
                : $"nothing picked from {block.Code} at {pos}",
            Data = new
            {
                code = block.Code.ToString(),
                pos = new { x, y, z },
                picked = totalPicked,
                bushState = (int)bush.BState.Growthstate,
                bot = bot.Entity.EntityId
            }
        };
    }

    // --- A2: crucible commands (firepit as the crucible station) ---
    //
    // Engine ground truth (VSSurvivalMod 1.22.7 decompiled): a crucible is
    // a BlockSmeltingContainer (raw/fired/smelted); there is NO dedicated
    // crucible block entity. Its "cooking" is a firepit: BlockEntityFirepit
    // holds it in the input slot, smelts raw->fired as ordinary smelting
    // (BlockSmeltingContainer smelting recipe) and - once the crucible is
    // fired - smelts container-requiring items placed in the firepit's four
    // cooking slots INTO the crucible (DoSmelt writes the smelted crucible,
    // carrying its metal as ItemStack attributes "output"+"units", into the
    // output slot). A smelted crucible pours into an ILiquidMetalSink
    // (BlockEntityIngotMold / BlockEntityToolMold) and reverts to the fired
    // block when empty. So the harness drives the whole chain against a
    // real firepit and a real mold:
    //
    //   crucible-fire    -> crucible into the firepit input + fuel + ignite
    //   crucible-insert  -> smeltable item(s) into the crucible's cooking slots
    //   crucible-fuel    -> add fuel / re-arm ignition
    //   crucible-take    -> take the smelted crucible from the output (tongs = advisory wear, engine has no hard gate)
    //   crucible-pour    -> empty the smelted crucible into a mold (ILiquidMetalSink)

    static bool CrucibleCodeMatch(string code, string crucibleType)
    {
        if (string.IsNullOrEmpty(code)) return false;
        string c = code;
        int colon = c.IndexOf(':');
        if (colon >= 0) c = c.Substring(colon + 1);
        return c.StartsWith("crucible-", StringComparison.Ordinal) && c.EndsWith("-" + crucibleType, StringComparison.Ordinal);
    }

    static bool CodeMatchesLenient(string actualCode, string wanted)
    {
        if (string.IsNullOrEmpty(actualCode) || string.IsNullOrEmpty(wanted)) return false;
        if (actualCode.Equals(wanted, StringComparison.OrdinalIgnoreCase)) return true;
        int colon = wanted.IndexOf(':');
        string bare = colon >= 0 ? wanted.Substring(colon + 1) : wanted;
        return actualCode.Equals(bare, StringComparison.OrdinalIgnoreCase)
            || actualCode.StartsWith("game:" + bare, StringComparison.OrdinalIgnoreCase)
            || actualCode.StartsWith("survival:" + bare, StringComparison.OrdinalIgnoreCase);
    }

    static ItemSlot FindBlockInCargoDirect(EntityAgent agent, Block block)
    {
        var cargo = PolisInventoryHelpers.BotCargo(agent);
        if (cargo == null || block == null) return null;
        for (int i = 0; i < cargo.Count; i++)
        {
            var it = cargo[i]?.Itemstack;
            if (it != null && it.Collectible is Block b && b.Code.Equals(block.Code))
            {
                return cargo[i];
            }
        }
        return null;
    }

    static ItemSlot FindItemInCargoDirect(EntityAgent agent, string code)
    {
        var cargo = PolisInventoryHelpers.BotCargo(agent);
        if (cargo == null) return null;
        for (int i = 0; i < cargo.Count; i++)
        {
            if (PolisInventoryHelpers.IsItem(cargo[i]?.Itemstack, code))
            {
                return cargo[i];
            }
        }
        return null;
    }

    /// <summary>
    /// Moves up to <paramref name="maxQty"/> of a bot-side stack into a
    /// destination slot (same merge rules as the inventory helpers):
    /// empty slot via CanHold, occupied via CanTakeFrom/AutoMerge.
    /// </summary>
    static int MoveStackToSlot(ItemSlot source, ItemSlot dest, int maxQty)
    {
        if (source == null || dest == null || source.Empty || maxQty <= 0) return 0;
        var stack = source.Itemstack;
        if (stack == null || stack.StackSize <= 0) return 0;

        int space;
        if (dest.Empty)
        {
            if (!dest.CanHold(source)) return 0;
            space = Math.Min(dest.GetRemainingSlotSpace(stack), stack.Collectible.MaxStackSize);
        }
        else
        {
            if (!dest.CanTakeFrom(source, EnumMergePriority.AutoMerge)) return 0;
            // engine merge cap (CollectibleObject.GetMergableQuantity)
            space = Math.Min(dest.GetRemainingSlotSpace(stack),
                stack.Collectible.GetMergableQuantity(dest.Itemstack, stack, EnumMergePriority.AutoMerge));
        }

        int moved = Math.Min(maxQty, Math.Min(stack.StackSize, space));
        if (moved <= 0) return 0;

        if (dest.Empty)
        {
            dest.Itemstack = stack.Clone();
            dest.Itemstack.StackSize = 0;
        }
        dest.Itemstack.StackSize += moved;
        stack.StackSize -= moved;
        if (stack.StackSize <= 0)
        {
            source.Itemstack = null;
        }
        source.MarkDirty();
        dest.MarkDirty();
        return moved;
    }

    static ItemSlot FindSmeltedCrucibleSlot(EntityAgent agent, out ItemStack smeltedStack)
    {
        smeltedStack = null;
        var cargo = PolisInventoryHelpers.BotCargo(agent);
        if (cargo == null) return null;
        for (int i = 0; i < cargo.Count; i++)
        {
            var it = cargo[i]?.Itemstack;
            if (it != null && CrucibleCodeMatch(it.Collectible?.Code?.ToString(), "smelted"))
            {
                smeltedStack = it;
                return cargo[i];
            }
        }
        return null;
    }

    IServerPlayer ResolveCommandOwner(BotState bot, PolisTestHarness.CommandContext context)
    {
        IServerPlayer owner = null;
        if (globalData.Bots.TryGetValue(bot.Entity.EntityId, out var botRecord))
        {
            owner = sapi.World.PlayerByUid(botRecord.OwnerUid) as IServerPlayer;
        }
        if (owner == null && TryGetContextPlayer(context, out var ctxPlayer, out var _))
        {
            owner = ctxPlayer as IServerPlayer;
        }
        return owner;
    }

    /// <summary>
    /// Explicit "x y z" (first three args, all int) or the nearest
    /// firepit to the bot (49x5x49 box scan around the bot, y -2..+1).
    /// </summary>
    bool TryResolveCrucibleFirepit(BotState bot, string[] args, out BlockPos pos, out string error)
    {
        pos = default;
        error = null;

        if (args.Length >= 3 &&
            int.TryParse(args[0], out int x) &&
            int.TryParse(args[1], out int y) &&
            int.TryParse(args[2], out int z))
        {
            pos = new BlockPos(x, y, z);
            if (sapi.World.BlockAccessor.GetBlockEntity(pos) is BlockEntityFirepit)
            {
                return true;
            }
            error = $"no firepit at ({x}, {y}, {z})";
            return false;
        }

        var botPos = bot.Entity.ServerPos.AsBlockPos;
        BlockPos nearest = default;
        int bestSq = int.MaxValue;
        for (int bx = botPos.X - 24; bx <= botPos.X + 24; bx++)
        {
            for (int by = Math.Max(0, botPos.Y - 2); by <= botPos.Y + 1; by++)
            {
                for (int bz = botPos.Z - 24; bz <= botPos.Z + 24; bz++)
                {
                    if (!(sapi.World.BlockAccessor.GetBlockEntity(new BlockPos(bx, by, bz)) is BlockEntityFirepit))
                    {
                        continue;
                    }
                    int dx = bx - botPos.X;
                    int dy = by - botPos.Y;
                    int dz = bz - botPos.Z;
                    int sq = dx * dx + dy * dy + dz * dz;
                    if (sq < bestSq)
                    {
                        bestSq = sq;
                        nearest = new BlockPos(bx, by, bz);
                    }
                }
            }
        }

        if (nearest == default)
        {
            error = "no firepit found within 24 blocks of the bot (pass x y z)";
            return false;
        }

        pos = nearest;
        return true;
    }

    bool CrucibleInRange(BotState bot, BlockPos pos, out double dist, out string error)
    {
        dist = 0;
        error = null;
        var center = new Vec3d(pos.X + 0.5, pos.Y + 0.5, pos.Z + 0.5);
        dist = bot.Entity.ServerPos.XYZ.DistanceTo(center);
        if (dist > PolisConstants.DefaultActionRange)
        {
            error = $"firepit out of range ({dist:F1} blocks)";
            return false;
        }
        return true;
    }

    PolisTestHarness.CommandResult ExecuteCrucibleFireCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        // Usage: crucible-fire [color] [x y z]
        //   color defaults to "fire". Raw crucibles exist for
        //   fire/blue/red; fired crucibles for fire, blue, red->(baked
        //   variants: black, brown, cream, earthyorange, gray, orange,
        //   tan). "fire" works for both.
        //   if the first arg is an integer it is the start of the coords.
        string color = "fire";
        int offset = 0;
        if (args.Length > 0 && !int.TryParse(args[0], out _))
        {
            color = args[0];
            offset = 1;
        }
        string[] coordArgs = args.Length > offset ? args.Skip(offset).ToArray() : Array.Empty<string>();

        if (!TryGetHarnessBot(context, out var bot, out var err))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = err };
        }
        if (!TryResolveCrucibleFirepit(bot, coordArgs, out var pos, out var resolveErr))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = resolveErr };
        }
        if (!CrucibleInRange(bot, pos, out _, out var rangeErr))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = rangeErr };
        }

        var world = sapi.World;
        var firepit = world.BlockAccessor.GetBlockEntity(pos) as BlockEntityFirepit;
        var owner = ResolveCommandOwner(bot, context);
        var agent = bot.Entity as EntityAgent;
        var debug = debugEnabled ? (Action<string>)(msg => sapi.Logger.Debug($"[polis] {msg}")) : null;

        // Fired first (it smelts directly), raw second (fires in place).
        var crucibleBlock = ResolveBlockLenient(world, $"crucible-{color}-fired")
            ?? ResolveBlockLenient(world, $"crucible-{color}-raw");
        if (crucibleBlock == null)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"no crucible-{color}-fired / crucible-{color}-raw in the block registry" };
        }

        string inputState;
        if (firepit.inputSlot != null && !firepit.inputSlot.Empty)
        {
            var inCode = firepit.inputSlot.Itemstack.Collectible?.Code?.ToString();
            if (inCode != null && inCode.Contains("crucible", StringComparison.OrdinalIgnoreCase))
            {
                inputState = inCode; // already loaded - that is the goal state
            }
            else
            {
                return new PolisTestHarness.CommandResult { Ok = false, Message = $"firepit input busy with {inCode} (crucible-take it first)" };
            }
        }
        else
        {
            var crucibleSlot = FindBlockInCargoDirect(agent, crucibleBlock);
            if (crucibleSlot == null)
            {
                return new PolisTestHarness.CommandResult { Ok = false, Message = $"bot carries no crucible-{color} (fired or raw); craft one first" };
            }
            var taken = crucibleSlot.TakeOut(1);
            if (taken == null || taken.StackSize <= 0)
            {
                return new PolisTestHarness.CommandResult { Ok = false, Message = "could not take the crucible out of the bot's cargo" };
            }
            if (firepit.inputSlot == null || firepit.inputSlot.Empty)
            {
                firepit.inputSlot.Itemstack = taken;
            }
            else
            {
                firepit.inputSlot.Itemstack.StackSize += taken.StackSize;
            }
            firepit.inputSlot.MarkDirty();
            inputState = taken.Collectible.Code.ToString();
        }

        // Fuel: if not burning yet and the fuel slot is empty, take
        // charcoal from the bot's cargo (one small stack).
        bool fueled = false;
        if (!firepit.IsBurning && (firepit.fuelSlot == null || firepit.fuelSlot.Empty))
        {
            var fuelSrc = FindItemInCargoDirect(agent, "charcoal");
            var takenFuel = fuelSrc?.TakeOut(Math.Min(8, fuelSrc.Itemstack.StackSize));
            if (takenFuel != null && takenFuel.StackSize > 0 && firepit.fuelSlot != null)
            {
                firepit.fuelSlot.Itemstack = takenFuel;
                firepit.fuelSlot.MarkDirty();
                fueled = true;
            }
        }

        // Arm ignition the way the GUI does; the firepit's own OnBurnTick
        // gate (canSmeltInput) decides when the burn actually starts.
        firepit.canIgniteFuel = true;
        firepit.MarkDirty(true, owner);

        bot.RecordActionResult("crucible-fire", true, $"firepit {pos}: input={inputState}", sapi.World.ElapsedMilliseconds);

        string fuelState = firepit.IsBurning ? "burning"
            : (fueled ? "loaded + armed"
                      : "none - run crucible-fuel or drop charcoal in");
        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = $"firepit at {pos}: crucible in input ({inputState}), fuel {fuelState}",
            Data = new
            {
                pos = new { x = pos.X, y = pos.Y, z = pos.Z },
                color,
                input = inputState,
                fuel = firepit.fuelStack?.Collectible?.Code?.ToString(),
                burning = firepit.IsBurning,
                canIgniteFuel = firepit.canIgniteFuel,
                canSmelt = firepit.canSmeltInput(),
                hasCookingContainer = firepit.otherCookingSlots != null && firepit.otherCookingSlots.Length > 0,
                temperature = firepit.furnaceTemperature,
                maxTemperature = firepit.maxTemperature,
                bot = bot.Entity.EntityId
            }
        };
    }

    PolisTestHarness.CommandResult ExecuteCrucibleInsertCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        // Usage: crucible-insert <itemCode> [count] [x y z]
        //   count 0/omitted = as much as fits in the empty cooking slots.
        if (args.Length < 1)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Usage: crucible-insert <itemCode> [count] [x y z]" };
        }

        string itemCode = args[0];
        int count = 0;
        int offset = 1;
        if (args.Length > 1 && int.TryParse(args[1], out int parsedCount))
        {
            count = Math.Max(0, Math.Min(64, parsedCount));
            offset = 2;
        }
        string[] coordArgs = args.Length > offset ? args.Skip(offset).ToArray() : Array.Empty<string>();

        if (!TryGetHarnessBot(context, out var bot, out var err))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = err };
        }
        if (!TryResolveCrucibleFirepit(bot, coordArgs, out var pos, out var resolveErr))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = resolveErr };
        }
        if (!CrucibleInRange(bot, pos, out _, out var rangeErr))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = rangeErr };
        }

        var world = sapi.World;
        var firepit = world.BlockAccessor.GetBlockEntity(pos) as BlockEntityFirepit;
        var owner = ResolveCommandOwner(bot, context);

        if (firepit.inputSlot == null || firepit.inputSlot.Empty)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"no crucible in the firepit input at {pos} (run crucible-fire first)" };
        }
        var cooking = firepit.otherCookingSlots;
        if (cooking == null || cooking.Length == 0)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"firepit at {pos} has a crucible-less input (no cooking container)" };
        }

        var agent = bot.Entity as EntityAgent;
        var cargo = PolisInventoryHelpers.BotCargo(agent);

        int remaining = count;
        int total = 0;
        if (cargo != null)
        {
            for (int i = 0; i < cargo.Count; i++)
            {
                var src = cargo[i];
                if (src == null || src.Empty || !CodeMatchesLenient(src.Itemstack?.Collectible?.Code?.ToString(), itemCode))
                {
                    continue;
                }
                for (int c = 0; c < cooking.Length; c++)
                {
                    int want = remaining > 0 ? remaining : 64;
                    int moved = MoveStackToSlot(src, cooking[c], want);
                    if (moved > 0)
                    {
                        total += moved;
                        if (remaining > 0) remaining -= moved;
                    }
                    if (remaining <= 0 && count > 0) break;
                }
                if (count > 0 && remaining <= 0) break;
            }
        }

        if (total == 0)
        {
            return new PolisTestHarness.CommandResult
            {
                Ok = false,
                Message = count > 0
                    ? $"bot carries no '{itemCode}' to insert (count {count} requested)"
                    : $"no empty cooking slot in the crucible at {pos} (or the bot carries no '{itemCode}')"
            };
        }

        firepit.MarkDirty(true, owner);
        bot.RecordActionResult("crucible-insert", true, $"inserted {total}x {itemCode}", sapi.World.ElapsedMilliseconds);

        var cookingNow = new List<object>();
        foreach (var c in cooking)
        {
            cookingNow.Add(c.Empty ? null : $"{c.Itemstack.StackSize}x{c.Itemstack.Collectible?.Code}");
        }

        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = $"inserted {total}x {itemCode} into the crucible at {pos}",
            Data = new
            {
                pos = new { x = pos.X, y = pos.Y, z = pos.Z },
                inserted = total,
                cookingSlots = cookingNow,
                canSmelt = firepit.canSmeltInput(),
                burning = firepit.IsBurning,
                temperature = firepit.furnaceTemperature,
                bot = bot.Entity.EntityId
            }
        };
    }

    PolisTestHarness.CommandResult ExecuteCrucibleFuelCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        // Usage: crucible-fuel [itemCode] [count] [x y z]
        //   defaults: charcoal x8, nearest firepit; if the first arg is an
        //   integer it is the start of the coords.
        string itemCode = "charcoal";
        int count = 8;
        string[] coordArgs = Array.Empty<string>();

        if (args.Length > 0 && int.TryParse(args[0], out _))
        {
            coordArgs = args;
        }
        else if (args.Length > 0)
        {
            itemCode = args[0];
            if (args.Length > 1)
            {
                if (args.Length - 1 >= 3 &&
                    int.TryParse(args[1], out int c2) &&
                    int.TryParse(args[2], out _) &&
                    int.TryParse(args[3], out _) &&
                    int.TryParse(args[4], out _))
                {
                    count = Math.Max(1, Math.Min(64, c2));
                    coordArgs = args.Skip(2).ToArray();
                }
                else if (int.TryParse(args[1], out int parsedCount))
                {
                    count = Math.Max(1, Math.Min(64, parsedCount));
                }
            }
        }

        if (!TryGetHarnessBot(context, out var bot, out var err))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = err };
        }
        if (!TryResolveCrucibleFirepit(bot, coordArgs, out var pos, out var resolveErr))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = resolveErr };
        }
        if (!CrucibleInRange(bot, pos, out _, out var rangeErr))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = rangeErr };
        }

        var firepit = sapi.World.BlockAccessor.GetBlockEntity(pos) as BlockEntityFirepit;
        var owner = ResolveCommandOwner(bot, context);
        var agent = bot.Entity as EntityAgent;

        var fuelSrc = FindItemInCargoDirect(agent, itemCode);
        if (fuelSrc == null)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"bot carries no '{itemCode}'" };
        }

        if (firepit.fuelSlot == null || firepit.fuelSlot.Empty)
        {
            var taken = fuelSrc.TakeOut(Math.Min(count, fuelSrc.Itemstack.StackSize));
            if (taken == null || taken.StackSize <= 0)
            {
                return new PolisTestHarness.CommandResult { Ok = false, Message = "could not take fuel out of the bot's cargo" };
            }
            firepit.fuelSlot.Itemstack = taken;
            firepit.fuelSlot.MarkDirty();
        }
        else if (CodeMatchesLenient(firepit.fuelSlot.Itemstack.Collectible?.Code?.ToString(), itemCode))
        {
            MoveStackToSlot(fuelSrc, firepit.fuelSlot, count);
        }
        else
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"firepit fuel slot holds {firepit.fuelSlot.Itemstack.Collectible?.Code}; clear it first" };
        }

        if (!firepit.IsBurning)
        {
            firepit.canIgniteFuel = true;
        }
        firepit.MarkDirty(true, owner);

        bot.RecordActionResult("crucible-fuel", true, $"+{count}x {itemCode} to firepit {pos}", sapi.World.ElapsedMilliseconds);

        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = $"fuel {firepit.fuelStack?.Collectible?.Code} in firepit at {pos}; burning={firepit.IsBurning}",
            Data = new
            {
                pos = new { x = pos.X, y = pos.Y, z = pos.Z },
                fuel = firepit.fuelStack?.Collectible?.Code?.ToString(),
                fuelStackSize = firepit.fuelStack?.StackSize,
                burnTime = firepit.fuelBurnTime,
                maxBurnTime = firepit.maxFuelBurnTime,
                burning = firepit.IsBurning,
                canIgniteFuel = firepit.canIgniteFuel,
                bot = bot.Entity.EntityId
            }
        };
    }

    PolisTestHarness.CommandResult ExecuteCrucibleTakeCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        // Usage: crucible-take [x y z]
        if (!TryGetHarnessBot(context, out var bot, out var err))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = err };
        }
        if (!TryResolveCrucibleFirepit(bot, args, out var pos, out var resolveErr))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = resolveErr };
        }
        if (!CrucibleInRange(bot, pos, out _, out var rangeErr))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = rangeErr };
        }

        var world = sapi.World;
        var firepit = world.BlockAccessor.GetBlockEntity(pos) as BlockEntityFirepit;
        var owner = ResolveCommandOwner(bot, context);
        var agent = bot.Entity as EntityAgent;

        var outStack = firepit.outputSlot?.Itemstack;
        if (outStack == null || outStack.StackSize <= 0)
        {
            return new PolisTestHarness.CommandResult
            {
                Ok = false,
                Message = $"nothing in the output slot yet (progress {firepit.inputStackCookingTime:F1}/{firepit.maxCookingTime():F1}s, burning={firepit.IsBurning}, {firepit.furnaceTemperature:F0}C)"
            };
        }

        // Engine 1.22.7 ground truth: there is NO hard tongs gate for
        // taking a hot crucible. The tongs mechanic is ModSystemSubTongsDurability
        // (onitemcollected): picking up a stack hotter than
        // TooHotToTouchTemperature while the tongs (EnumTool.Tongs == 31)
        // are the OFFHAND tool damages the tongs by 1. The take always
        // proceeds; heat + tongs facts are reported for the caller.
        float outTemp = outStack.Collectible.GetTemperature(world, outStack);
        bool hot = outTemp > GlobalConstants.TooHotToTouchTemperature;
        var leftItem = agent?.LeftHandItemSlot?.Itemstack;
        bool hasTongs = leftItem != null
            && (leftItem.Collectible is ItemTongs || CodeMatchesLenient(leftItem.Collectible?.Code?.ToString(), "tongs"));

        var taken = firepit.outputSlot.TakeOut(outStack.StackSize);
        firepit.outputSlot.MarkDirty();
        firepit.MarkDirty(true, owner);

        int moved = 0;
        if (PolisInventoryHelpers.TryInsertIntoBotInventory(agent, taken, out moved, out string reason, debugEnabled ? msg => sapi.Logger.Debug($"[polis] {msg}") : null))
        {
            if (moved < taken.StackSize)
            {
                var overflow = taken.Clone();
                overflow.StackSize = taken.StackSize - moved;
                world.SpawnItemEntity(overflow, pos);
            }
        }
        else
        {
            world.SpawnItemEntity(taken, pos);
        }

        bot.RecordActionResult("crucible-take", true, $"took {taken.StackSize}x {taken.Collectible.Code}", sapi.World.ElapsedMilliseconds);

        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = $"took {taken.StackSize}x {taken.Collectible.Code} ({outTemp:F0}C, tongs={hasTongs}{(hot ? " - carrying it hot wears the tongs (engine onitemcollected rule)" : "")}) from firepit at {pos}",
            Data = new
            {
                pos = new { x = pos.X, y = pos.Y, z = pos.Z },
                code = taken.Collectible.Code.ToString(),
                units = taken.Attributes.GetInt("units", 0),
                temperature = outTemp,
                hot,
                hasTongs,
                bot = bot.Entity.EntityId
            }
        };
    }

    PolisTestHarness.CommandResult ExecuteCruciblePourCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        // Usage: crucible-pour <x y z> [units]   (units omitted = all)
        if (args.Length < 3 ||
            !int.TryParse(args[0], out int x) ||
            !int.TryParse(args[1], out int y) ||
            !int.TryParse(args[2], out int z))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Usage: crucible-pour <x y z> [units]" };
        }

        int units = 0;
        if (args.Length >= 4 && int.TryParse(args[3], out int parsedUnits))
        {
            units = Math.Max(0, Math.Min(999, parsedUnits));
        }

        if (!TryGetHarnessBot(context, out var bot, out var err))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = err };
        }

        var world = sapi.World;
        var pos = new BlockPos(x, y, z);
        var center = new Vec3d(pos.X + 0.5, pos.Y + 0.5, pos.Z + 0.5);
        double dist = bot.Entity.ServerPos.XYZ.DistanceTo(center);
        if (dist > PolisConstants.DefaultActionRange)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"mold out of range ({dist:F1} blocks)" };
        }

        var sink = world.BlockAccessor.GetBlockEntity(pos) as ILiquidMetalSink;
        if (sink == null)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"no liquid-metal mold (ingotmold / toolmold) at {pos}" };
        }

        var agent = bot.Entity as EntityAgent;
        var smeltedSlot = FindSmeltedCrucibleSlot(agent, out var crucibleStack);
        if (smeltedSlot == null)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "bot carries no smelted crucible (crucible-take it from the firepit first)" };
        }

        // Contents live as attributes on the smelted crucible stack
        // (BlockSmeltedContainer.SetContents / GetContents).
        var content = crucibleStack.Attributes.GetItemstack("output", null);
        int unitsAvail = crucibleStack.Attributes.GetInt("units", 0);
        if (content == null || content.StackSize <= 0 || unitsAvail <= 0)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "the smelted crucible is empty (no metal contents)" };
        }
        content.ResolveBlockOrItem(world);

        // The metal must still be liquid: engine HasSolidifed gate
        // (crucible stack temperature vs 0.9x the metal's melting point).
        float crucibleTemp = crucibleStack.Collectible.GetTemperature(world, crucibleStack);
        float meltingPoint = content.Collectible.GetMeltingPoint(world, null, new DummySlot(content));
        if (crucibleTemp < 0.9f * meltingPoint)
        {
            return new PolisTestHarness.CommandResult
            {
                Ok = false,
                Message = $"the metal has solidified (crucible {crucibleTemp:F0}C < 0.9x melting point {0.9f * meltingPoint:F0}C); heat it again (forge-heat)"
            };
        }

        // Engine pour gate: the mold must be able to receive this metal.
        sink.BeginFill(center);
        if (sink is BlockEntityIngotMold ingotMold && ingotMold.QuantityMolds > 1)
        {
            // A two-mold block: if the currently selected side cannot
            // receive but the other can, switch sides (like a player
            // clicking the free half).
            bool selectedOk = !ingotMold.SelectedIsFull && !ingotMold.SelectedShattered;
            if (!selectedOk)
            {
                bool leftOk = !ingotMold.IsFullLeft && !ingotMold.ShatteredLeft;
                bool rightOk = !ingotMold.IsFullRight && !ingotMold.ShatteredRight;
                if ((ingotMold.IsRightSideSelected && rightOk) || (!ingotMold.IsRightSideSelected && leftOk))
                {
                    ingotMold.IsRightSideSelected = !ingotMold.IsRightSideSelected;
                    ingotMold.MarkDirty(true, null);
                }
            }
        }
        if (!sink.CanReceiveAny)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"mold at {pos} cannot receive (full or shattered)" };
        }
        if (!sink.CanReceive(content))
        {
            string heldCode = sink is BlockEntityIngotMold im ? im.SelectedContents?.Collectible?.Code?.ToString()
                : sink is BlockEntityToolMold tm ? tm.MetalContent?.Collectible?.Code?.ToString()
                : null;
            return new PolisTestHarness.CommandResult
            {
                Ok = false,
                Message = $"mold at {pos} cannot receive {content.Collectible.Code} (it already holds {heldCode ?? "other metal"})"
            };
        }

        // Engine 1.22.7: the pour has a HasSolidifed gate (above) but NO
        // tongs gate - the tongs mechanic is the same durability wear as
        // for take (ModSystemSubTongsDurability, onitemcollected: hot
        // stack + tongs as offhand tool -> tongs -1). Advisory facts only.
        float contentTemp = content.Collectible.GetTemperature(world, content);
        var leftItem = agent?.LeftHandItemSlot?.Itemstack;
        bool hasTongs = leftItem != null
            && (leftItem.Collectible is ItemTongs || CodeMatchesLenient(leftItem.Collectible?.Code?.ToString(), "tongs"));

        int toPour = units > 0 ? Math.Min(units, unitsAvail) : unitsAvail;
        int transferred = toPour;
        sink.ReceiveLiquidMetal(content, ref transferred, crucibleTemp);

        // Mirror the engine's OnHeldInteractStep bookkeeping: the crucible
        // loses what arrived in the mold, and at zero units it reverts to
        // its emptiedBlockCode (the fired crucible block).
        int left = Math.Max(0, unitsAvail - (toPour - transferred));
        crucibleStack.Attributes.SetInt("units", left);
        if (left <= 0 && world is IServerWorldAccessor)
        {
            // BlockSmeltedContainer.OnHeldInteractStart does the same:
            // the empty smelted crucible reverts to its emptiedBlockCode.
            string emptiedCode = null;
            var emTok = crucibleStack.Collectible is Block emBlock ? emBlock.Attributes?["emptiedBlockCode"] : null;
            if (emTok != null) emptiedCode = emTok.AsString();
            var emptiedBlock = emTok != null && emptiedCode != null
                ? world.GetBlock(AssetLocation.Create(emptiedCode, ((Block)crucibleStack.Collectible).Code.Domain))
                : null;
            smeltedSlot.Itemstack = emptiedBlock != null ? new ItemStack(emptiedBlock, 1) : null;
            smeltedSlot.MarkDirty();
        }
        sink.OnPourOver();

        bot.RecordActionResult("crucible-pour", transferred > 0, $"poured {transferred} units of {content.Collectible.Code}", sapi.World.ElapsedMilliseconds);

        object moldData = sink switch
        {
            BlockEntityIngotMold m => new
            {
                type = "ingotmold",
                fillLevel = m.SelectedFillLevel,
                requiredUnits = m.RequiredUnits,
                isFull = m.SelectedIsFull,
                isHardened = m.SelectedIsHardened,
                shattered = m.SelectedShattered,
                temperature = m.SelectedTemperature
            },
            BlockEntityToolMold m2 => new
            {
                type = "toolmold",
                fillLevel = m2.FillLevel,
                isHardened = m2.IsHardened,
                shattered = m2.Shattered,
                temperature = m2.Temperature,
                metal = m2.MetalContent?.Collectible?.Code?.ToString()
            },
            _ => new { type = "liquidmetalsink" }
        };

        return new PolisTestHarness.CommandResult
        {
            Ok = transferred > 0,
            Message = transferred > 0
                ? $"poured {transferred} of {unitsAvail} units of {content.Collectible.Code} into the mold at {pos} ({left} left in the crucible)"
                : $"the mold at {pos} accepted nothing (fill guard)",
            Data = new
            {
                pos = new { x, y, z },
                metal = content.Collectible.Code.ToString(),
                poured = transferred,
                unitsInCrucible = left,
                crucibleTemperature = crucibleTemp,
                mold = moldData,
                bot = bot.Entity.EntityId
            }
        };
    }

    // --- End HTTP Test Harness Callbacks ---
}
