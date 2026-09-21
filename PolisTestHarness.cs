using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.WebSockets;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Vintagestory.API.Common;
using Vintagestory.API.Common.Entities;
using Vintagestory.API.MathTools;
using Vintagestory.API.Server;
using PolisBuilderNpc.Core;

/// <summary>
/// HTTP test harness for external control of polis-builder-npc.
/// Enables agents, web UIs, and CLI tools to send commands and query state.
/// </summary>
public class PolisTestHarness : IDisposable
{
    public class TestStateResult
    {
        public BotInfo Bot { get; set; }
        // ... (rest of struct)
        public List<ItemInfo> Items { get; set; }
        public ActionInfo LastAction { get; set; }
        public long LastActionMs { get; set; }
        public long LastActionId { get; set; }
        public string Error { get; set; }

        public class BotInfo
        {
            public long Id { get; set; }
            public double[] Pos { get; set; }
            public float? CurrentHealth { get; set; }
            public float? MaxHealth { get; set; }
            public SlotInfo RightHand { get; set; }
            public SlotInfo LeftHand { get; set; }
            public SlotInfo[] Backpack { get; set; }
            public SlotInfo[][] BackpackContents { get; set; }
        }

        public class SlotInfo
        {
            public string Code { get; set; }
            public int Qty { get; set; }
        }

        public class ItemInfo
        {
            public long Id { get; set; }
            public string Code { get; set; }
            public int Qty { get; set; }
            public double Dist { get; set; }
        }

        public class ActionInfo
        {
            public string Name { get; set; }
            public bool Ok { get; set; }
            public string Msg { get; set; }
        }
    }
    const string LogPrefix = "[polis-harness]";

    private readonly ICoreServerAPI sapi;
    private readonly System.Func<string, long?, TestStateResult> getTestStateFunc;
    private readonly System.Func<string, string[], CommandContext, CommandResult> executeCommandFunc;
    private readonly System.Func<string, bool, System.Action<PolisScreenshotResponsePacket>, string> requestScreenshotFunc;

    private HttpListener listener;
    private CancellationTokenSource cts;
    private Thread listenerThread;
    private bool isRunning;
    private int port;
    private PolisEventBroadcaster broadcaster;
    private string modDirectory;

    public bool IsRunning => isRunning;
    public int Port => port;
    public PolisEventBroadcaster Broadcaster => broadcaster;

    public PolisTestHarness(
        ICoreServerAPI sapi,
        System.Func<string, long?, TestStateResult> getTestStateFunc,
        System.Func<string, string[], CommandContext, CommandResult> executeCommandFunc,
        System.Func<string, bool, System.Action<PolisScreenshotResponsePacket>, string> requestScreenshotFunc = null,
        int port = PolisConstants.DefaultPort)
    {
        this.sapi = sapi;
        this.getTestStateFunc = getTestStateFunc;
        this.executeCommandFunc = executeCommandFunc;
        this.requestScreenshotFunc = requestScreenshotFunc;
        this.port = port;
    }

    public bool Start()
    {
        if (isRunning) return true;

        try
        {
            // Find mod directory for serving static files
            modDirectory = FindModDirectory();

            listener = new HttpListener();
            listener.Prefixes.Add($"http://localhost:{port}/");
            listener.Prefixes.Add($"http://127.0.0.1:{port}/");
            listener.Start();

            cts = new CancellationTokenSource();
            broadcaster = new PolisEventBroadcaster(msg => sapi.Logger.Debug(msg));
            listenerThread = new Thread(ListenLoop) { IsBackground = true, Name = "PolisTestHarness" };
            listenerThread.Start();

            isRunning = true;
            sapi.Logger.Notification($"{LogPrefix} HTTP/WebSocket server started on port {port}");
            if (modDirectory != null)
                sapi.Logger.Notification($"{LogPrefix} UI available at http://localhost:{port}/polis/ui");
            return true;
        }
        catch (Exception ex)
        {
            sapi.Logger.Error($"{LogPrefix} Failed to start HTTP server: {ex.Message}");
            return false;
        }
    }

    public void Stop()
    {
        if (!isRunning) return;

        try
        {
            cts?.Cancel();
            broadcaster?.Dispose();
            broadcaster = null;
            listener?.Stop();
            listener?.Close();
            listenerThread?.Join(2000);
            isRunning = false;
            sapi.Logger.Notification($"{LogPrefix} HTTP/WebSocket server stopped");
        }
        catch (Exception ex)
        {
            sapi.Logger.Warning($"{LogPrefix} Error stopping HTTP server: {ex.Message}");
        }
    }

    public void Dispose()
    {
        Stop();
        cts?.Dispose();
    }

    private void ListenLoop()
    {
        while (!cts.Token.IsCancellationRequested)
        {
            try
            {
                var context = listener.GetContext();
                ThreadPool.QueueUserWorkItem(_ => HandleRequest(context));
            }
            catch (HttpListenerException) when (cts.Token.IsCancellationRequested)
            {
                // Expected when stopping
                break;
            }
            catch (Exception ex)
            {
                if (!cts.Token.IsCancellationRequested)
                {
                    sapi.Logger.Warning($"{LogPrefix} Listener error: {ex.Message}");
                }
            }
        }
    }

    private void HandleRequest(HttpListenerContext context)
    {
        var request = context.Request;
        var response = context.Response;
        var path = request.Url?.AbsolutePath ?? "/";

        // Handle WebSocket upgrade requests
        if (request.IsWebSocketRequest && path == "/polis/ws")
        {
            _ = HandleWebSocketUpgradeAsync(context);
            return;
        }

        // CORS headers for browser access
        response.Headers.Add("Access-Control-Allow-Origin", "*");
        response.Headers.Add("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
        response.Headers.Add("Access-Control-Allow-Headers", "Content-Type");

        if (request.HttpMethod == "OPTIONS")
        {
            response.StatusCode = 204;
            response.Close();
            return;
        }

        try
        {
            sapi.Logger.Debug($"{LogPrefix} {request.HttpMethod} {path}");

            object result = null;
            var tcs = new TaskCompletionSource<object>();

            // Route request
            if (path == "/polis/state" && request.HttpMethod == "GET")
            {
                var botIdParam = request.QueryString["botId"];
                long? botId = long.TryParse(botIdParam, out var bid) ? bid : null;
                var radiusParam = request.QueryString["radius"];
                float radius = float.TryParse(radiusParam, out var r) ? r : 10f;

                sapi.Event.EnqueueMainThreadTask(() =>
                {
                    try
                    {
                        var state = getTestStateFunc(null, botId);
                        tcs.SetResult(state);
                    }
                    catch (Exception ex)
                    {
                        tcs.SetResult(new { error = ex.Message });
                    }
                }, "polis-harness-state");
            }
            else if (path == "/polis/status" && request.HttpMethod == "GET")
            {
                var runPhase = sapi.Server?.CurrentRunPhase ?? EnumServerRunPhase.Standby;
                var worldReady = (int)runPhase >= (int)EnumServerRunPhase.WorldReady;
                var modInfo = sapi.ModLoader?.GetMod("polis-builder-npc")?.Info;

                tcs.SetResult(new
                {
                    ok = true,
                    harness = new { running = isRunning, port },
                    server = new { runPhase = runPhase.ToString(), worldReady },
                    websocket = new { connections = broadcaster?.ConnectionCount ?? 0 },
                    timeMs = sapi.World?.ElapsedMilliseconds ?? 0,
                    modVersion = modInfo?.Version ?? ""
                });
            }
            else if (path == "/polis/players" && request.HttpMethod == "GET")
            {
                sapi.Event.EnqueueMainThreadTask(() =>
                {
                    try
                    {
                        var players = sapi.World.AllOnlinePlayers
                            .OfType<IServerPlayer>()
                            .Select(BuildPlayerInfo)
                            .Where(p => p != null)
                            .ToList();
                        tcs.SetResult(new { ok = true, players });
                    }
                    catch (Exception ex)
                    {
                        tcs.SetResult(new { error = ex.Message });
                    }
                }, "polis-harness-players");
            }
            else if (path == "/polis/player" && request.HttpMethod == "GET")
            {
                var uid = request.QueryString["uid"];
                if (string.IsNullOrWhiteSpace(uid))
                {
                    tcs.SetResult(new { error = "Missing uid" });
                }
                else
                {
                    sapi.Event.EnqueueMainThreadTask(() =>
                    {
                        try
                        {
                            var player = sapi.World.PlayerByUid(uid) as IServerPlayer;
                            var info = BuildPlayerInfo(player);
                            tcs.SetResult(info ?? new { error = "Player not found" });
                        }
                        catch (Exception ex)
                        {
                            tcs.SetResult(new { error = ex.Message });
                        }
                    }, "polis-harness-player");
                }
            }
            else if (path == "/polis/look" && request.HttpMethod == "GET")
            {
                var uid = request.QueryString["uid"];
                float range = 48f;
                if (float.TryParse(request.QueryString["range"], out var parsedRange))
                {
                    range = parsedRange;
                }

                if (string.IsNullOrWhiteSpace(uid))
                {
                    tcs.SetResult(new { error = "Missing uid" });
                }
                else
                {
                    sapi.Event.EnqueueMainThreadTask(() =>
                    {
                        try
                        {
                            var player = sapi.World.PlayerByUid(uid) as IServerPlayer;
                            if (player?.Entity == null)
                            {
                                tcs.SetResult(new { error = "Player not found or missing entity" });
                                return;
                            }

                            tcs.SetResult(BuildLookInfo(player, range));
                        }
                        catch (Exception ex)
                        {
                            tcs.SetResult(new { error = ex.Message });
                        }
                    }, "polis-harness-look");
                }
            }
            else if (path == "/polis/targets" && request.HttpMethod == "GET")
            {
                var uid = request.QueryString["playerUid"] ?? request.QueryString["uid"];
                float radius = 6f;
                int limit = 20;
                var mode = (request.QueryString["mode"] ?? "blocks").ToLowerInvariant();
                var query = request.QueryString["q"];
                var codeFilters = ParseFilterTokens(request.QueryString["codeContains"]);
                bool requireEntityClass = bool.TryParse(request.QueryString["requireEntityClass"], out var requireClass) && requireClass;
                long? botId = long.TryParse(request.QueryString["botId"], out var parsedBotId) ? parsedBotId : (long?)null;
                bool includeDead = bool.TryParse(request.QueryString["includeDead"], out var incDead) && incDead;

                if (float.TryParse(request.QueryString["radius"], out var parsedRadius))
                {
                    radius = parsedRadius;
                }
                if (int.TryParse(request.QueryString["limit"], out var parsedLimit))
                {
                    limit = parsedLimit;
                }

                radius = GameMath.Clamp(radius, 1f, 32f);
                limit = GameMath.Clamp(limit, 1, 200);

                if (botId == null && string.IsNullOrWhiteSpace(uid))
                {
                    tcs.SetResult(new { error = "Missing playerUid or botId" });
                }
                else
                {
                    sapi.Event.EnqueueMainThreadTask(() =>
                    {
                        try
                        {
                            Vec3d center;
                            if (botId != null)
                            {
                                var state = getTestStateFunc(null, botId);
                                if (state?.Bot?.Pos == null || state.Bot.Pos.Length < 3)
                                {
                                    tcs.SetResult(new { error = "Bot not found or missing position" });
                                    return;
                                }
                                center = new Vec3d(state.Bot.Pos[0], state.Bot.Pos[1], state.Bot.Pos[2]);
                            }
                            else
                            {
                                var player = sapi.World.PlayerByUid(uid) as IServerPlayer;
                                if (player?.Entity == null)
                                {
                                    tcs.SetResult(new { error = "Player not found or missing entity" });
                                    return;
                                }
                                center = player.Entity.ServerPos.XYZ;
                            }
                            var centerBlock = center.AsBlockPos;
                            var result = new TargetsResult
                            {
                                Ok = true,
                                Center = new[] { center.X, center.Y, center.Z },
                                Radius = radius
                            };

                            bool includeBlocks = mode == "blocks" || mode == "all";
                            bool includeEntities = mode == "entities" || mode == "all";

                            if (includeBlocks)
                            {
                                int r = (int)Math.Ceiling(radius);
                                for (int dx = -r; dx <= r; dx++)
                                {
                                    for (int dy = -r; dy <= r; dy++)
                                    {
                                        for (int dz = -r; dz <= r; dz++)
                                        {
                                            var pos = new BlockPos(centerBlock.X + dx, centerBlock.Y + dy, centerBlock.Z + dz);
                                            var block = sapi.World.BlockAccessor.GetBlock(pos);
                                            if (block == null || block.Id == 0) continue;

                                            if (requireEntityClass && string.IsNullOrWhiteSpace(block.EntityClass)) continue;

                                            var reasons = new List<string>(3);
                                            if (!string.IsNullOrWhiteSpace(block.EntityClass)) reasons.Add("EntityClass");
                                            if (block.BlockBehaviors != null && block.BlockBehaviors.Length > 0) reasons.Add("BlockBehaviors");
                                            if (block.PlacedPriorityInteract) reasons.Add("PlacedPriorityInteract");

                                            if (reasons.Count == 0) continue;

                                            var blockCenter = new Vec3d(pos.X + 0.5, pos.Y + 0.5, pos.Z + 0.5);
                                            var dist = blockCenter.DistanceTo(center);
                                            if (dist > radius) continue;

                                            var behaviors = block.BlockBehaviors?
                                                .Select(b => b?.GetType().Name)
                                                .Where(name => !string.IsNullOrWhiteSpace(name))
                                                .Distinct()
                                                .ToList();

                                            var code = block.Code?.ToString();
                                            var queryValues = new List<string>(2);
                                            if (!string.IsNullOrWhiteSpace(code)) queryValues.Add(code);
                                            if (!string.IsNullOrWhiteSpace(block.EntityClass)) queryValues.Add(block.EntityClass);
                                            if (behaviors != null) queryValues.AddRange(behaviors);

                                            if (!MatchesQuery(query, queryValues)) continue;
                                            if (!MatchesAnyFilter(codeFilters, code)) continue;

                                            result.Blocks.Add(new TargetsResult.TargetBlockInfo
                                            {
                                                Pos = new[] { pos.X, pos.Y, pos.Z },
                                                Code = code,
                                                Dist = Math.Round(dist, 2),
                                                EntityClass = block.EntityClass,
                                                PlacedPriorityInteract = block.PlacedPriorityInteract,
                                                Behaviors = behaviors,
                                                Reasons = reasons
                                            });
                                        }
                                    }
                                }

                                result.Blocks = result.Blocks
                                    .OrderBy(b => b.Dist)
                                    .Take(limit)
                                    .ToList();
                            }

                            if (includeEntities)
                            {
                                var entities = sapi.World.GetEntitiesAround(center, radius, radius, e => includeDead || e.Alive);
                                foreach (var entity in entities)
                                {
                                    if (entity is EntityPlayer) continue;

                                    var dist = entity.ServerPos.XYZ.DistanceTo(center);
                                    if (dist > radius) continue;

                                    string itemCode = null;
                                    int? itemQty = null;
                                    if (entity is EntityItem item)
                                    {
                                        itemCode = item.Itemstack?.Collectible?.Code?.ToString();
                                        itemQty = item.Itemstack?.StackSize;
                                    }

                                    var entityCode = entity.Code?.ToString();
                                    var entityClass = entity.GetType().Name;
                                    var entityQueryValues = new List<string>(3);
                                    if (!string.IsNullOrWhiteSpace(entityCode)) entityQueryValues.Add(entityCode);
                                    if (!string.IsNullOrWhiteSpace(entityClass)) entityQueryValues.Add(entityClass);
                                    if (!string.IsNullOrWhiteSpace(itemCode)) entityQueryValues.Add(itemCode);

                                    if (!MatchesQuery(query, entityQueryValues)) continue;
                                    if (!MatchesAnyFilter(codeFilters, entityCode, itemCode)) continue;

                                    result.Entities.Add(new TargetsResult.TargetEntityInfo
                                    {
                                        Id = entity.EntityId,
                                        Code = entityCode,
                                        Class = entityClass,
                                        Pos = new[] { entity.ServerPos.X, entity.ServerPos.Y, entity.ServerPos.Z },
                                        Dist = Math.Round(dist, 2),
                                        ItemCode = itemCode,
                                        ItemQty = itemQty,
                                        Alive = entity.Alive
                                    });
                                }

                                result.Entities = result.Entities
                                    .OrderBy(e => e.Dist)
                                    .Take(limit)
                                    .ToList();
                            }

                            tcs.SetResult(result);
                        }
                        catch (Exception ex)
                        {
                            tcs.SetResult(new { error = ex.Message });
                        }
                    }, "polis-harness-targets");
                }
            }
            else if (path == "/polis/zones" && request.HttpMethod == "GET")
            {
                sapi.Event.EnqueueMainThreadTask(() =>
                {
                    try
                    {
                        var cmdResult = executeCommandFunc("zone-list", Array.Empty<string>(), null);
                        tcs.SetResult(cmdResult);
                    }
                    catch (Exception ex)
                    {
                        tcs.SetResult(new { error = ex.Message });
                    }
                }, "polis-harness-zones");
            }
            else if (path == "/polis/zone-check" && request.HttpMethod == "GET")
            {
                var botIdParam = request.QueryString["botId"];
                var cmdArgs = !string.IsNullOrWhiteSpace(botIdParam) ? new[] { botIdParam } : Array.Empty<string>();

                sapi.Event.EnqueueMainThreadTask(() =>
                {
                    try
                    {
                        var cmdResult = executeCommandFunc("zone-check", cmdArgs, null);
                        tcs.SetResult(cmdResult);
                    }
                    catch (Exception ex)
                    {
                        tcs.SetResult(new { error = ex.Message });
                    }
                }, "polis-harness-zone-check");
            }
            else if (path == "/polis/events" && request.HttpMethod == "GET")
            {
                // Return recent event history for debugging
                var limitParam = request.QueryString["limit"];
                int limit = int.TryParse(limitParam, out var l) ? Math.Min(l, 100) : 20;

                var history = broadcaster?.GetEventHistory();
                var events = history != null
                    ? history.Take(limit).Select(e => new
                    {
                        type = e.Type,
                        level = (int)e.Level,
                        data = e.Data,
                        ts = e.Timestamp
                    }).ToArray()
                    : Array.Empty<object>();

                tcs.SetResult(new
                {
                    ok = true,
                    count = events.Length,
                    wsConnections = broadcaster?.ConnectionCount ?? 0,
                    events
                });
            }
            else if (path == "/polis/bots" && request.HttpMethod == "GET")
            {
                // Use the command system to list bots
                sapi.Event.EnqueueMainThreadTask(() =>
                {
                    try
                    {
                        var cmdResult = executeCommandFunc("bots", Array.Empty<string>(), null);
                        tcs.SetResult(cmdResult);
                    }
                    catch (Exception ex)
                    {
                        tcs.SetResult(new { error = ex.Message });
                    }
                }, "polis-harness-bots");
            }
            else if (path == "/polis/container-contents" && request.HttpMethod == "GET")
            {
                // Get container contents by name or coordinates
                var name = request.QueryString["name"];
                var xStr = request.QueryString["x"];
                var yStr = request.QueryString["y"];
                var zStr = request.QueryString["z"];
                var includeEmpty = request.QueryString["includeEmpty"] == "true";

                var containerArgs = new List<string>();
                bool hasValidParams = false;

                if (!string.IsNullOrWhiteSpace(name))
                {
                    containerArgs.Add(name);
                    if (includeEmpty) containerArgs.Add("true");
                    hasValidParams = true;
                }
                else if (!string.IsNullOrWhiteSpace(xStr) && !string.IsNullOrWhiteSpace(yStr) && !string.IsNullOrWhiteSpace(zStr))
                {
                    containerArgs.Add(xStr);
                    containerArgs.Add(yStr);
                    containerArgs.Add(zStr);
                    if (includeEmpty) containerArgs.Add("true");
                    hasValidParams = true;
                }

                if (!hasValidParams)
                {
                    tcs.SetResult(new { error = "Missing required parameters: either 'name' or 'x', 'y', 'z'" });
                }
                else
                {
                    sapi.Event.EnqueueMainThreadTask(() =>
                    {
                        try
                        {
                            var cmdResult = executeCommandFunc("container-contents", containerArgs.ToArray(), null);
                            tcs.SetResult(cmdResult);
                        }
                        catch (Exception ex)
                        {
                            tcs.SetResult(new { error = ex.Message });
                        }
                    }, "polis-harness-container-contents");
                }
            }
            else if (path == "/polis/screenshot" && request.HttpMethod == "GET")
            {
                // Screenshot capture from player's client
                var playerUid = request.QueryString["playerUid"] ?? request.QueryString["uid"];
                var saveToFile = request.QueryString["save"] == "true";

                if (requestScreenshotFunc == null)
                {
                    tcs.SetResult(new { error = "Screenshot functionality not available" });
                }
                else if (string.IsNullOrWhiteSpace(playerUid))
                {
                    tcs.SetResult(new { error = "Missing playerUid parameter" });
                }
                else
                {
                    sapi.Event.EnqueueMainThreadTask(() =>
                    {
                        try
                        {
                            var player = sapi.World.PlayerByUid(playerUid) as IServerPlayer;
                            if (player == null)
                            {
                                tcs.SetResult(new { error = "Player not found" });
                                return;
                            }

                            // Request screenshot with callback
                            requestScreenshotFunc(playerUid, saveToFile, result =>
                            {
                                if (result == null)
                                {
                                    tcs.SetResult(new { error = "Screenshot response timeout" });
                                }
                                else if (!result.Success)
                                {
                                    tcs.SetResult(new { ok = false, error = result.Error ?? "Screenshot capture failed" });
                                }
                                else
                                {
                                    tcs.SetResult(new
                                    {
                                        ok = true,
                                        width = result.Width,
                                        height = result.Height,
                                        base64 = result.Base64Png,
                                        filePath = result.FilePath,
                                        captureTimeMs = result.CaptureTimeMs
                                    });
                                }
                            });
                        }
                        catch (Exception ex)
                        {
                            tcs.SetResult(new { error = ex.Message });
                        }
                    }, "polis-harness-screenshot");
                }
            }
            else if (path == "/polis/observer-screenshot" && request.HttpMethod == "GET")
            {
                // Observer screenshot: teleport player to viewpoint, capture, restore position
                var playerUid = request.QueryString["playerUid"] ?? request.QueryString["uid"];
                var saveToFile = request.QueryString["save"] == "true";

                // Parse position/orientation
                if (!double.TryParse(request.QueryString["x"], NumberStyles.Float, CultureInfo.InvariantCulture, out var x) ||
                    !double.TryParse(request.QueryString["y"], NumberStyles.Float, CultureInfo.InvariantCulture, out var y) ||
                    !double.TryParse(request.QueryString["z"], NumberStyles.Float, CultureInfo.InvariantCulture, out var z))
                {
                    tcs.SetResult(new { error = "Invalid or missing x, y, z coordinates" });
                }
                else if (!float.TryParse(request.QueryString["yaw"], NumberStyles.Float, CultureInfo.InvariantCulture, out var yaw) ||
                         !float.TryParse(request.QueryString["pitch"], NumberStyles.Float, CultureInfo.InvariantCulture, out var pitch))
                {
                    tcs.SetResult(new { error = "Invalid or missing yaw, pitch values" });
                }
                else if (requestScreenshotFunc == null)
                {
                    tcs.SetResult(new { error = "Screenshot functionality not available" });
                }
                else if (string.IsNullOrWhiteSpace(playerUid))
                {
                    tcs.SetResult(new { error = "Missing playerUid parameter" });
                }
                else
                {
                    sapi.Event.EnqueueMainThreadTask(() =>
                    {
                        try
                        {
                            var player = sapi.World.PlayerByUid(playerUid) as IServerPlayer;
                            if (player?.Entity == null)
                            {
                                tcs.SetResult(new { error = "Player not found or entity not loaded" });
                                return;
                            }

                            var entity = player.Entity;

                            // Store original position
                            var originalX = entity.ServerPos.X;
                            var originalY = entity.ServerPos.Y;
                            var originalZ = entity.ServerPos.Z;
                            var originalYaw = entity.ServerPos.Yaw;
                            var originalPitch = entity.ServerPos.Pitch;

                            // Teleport to observer position
                            var observerPos = new EntityPos(x, y, z, yaw, pitch);
                            entity.TeleportTo(observerPos);

                            // Get server channel to send view direction packet
                            var modSystem = sapi.ModLoader.GetModSystem<PolisBuilderNpcSystem>();
                            modSystem?.serverChannel?.SendPacket(new PolisSetViewDirectionPacket { Yaw = yaw, Pitch = pitch }, player);

                            // Small delay for render to settle, then take screenshot
                            sapi.Event.RegisterCallback((dt) =>
                            {
                                requestScreenshotFunc(playerUid, saveToFile, result =>
                                {
                                    // Restore position (on main thread)
                                    sapi.Event.EnqueueMainThreadTask(() =>
                                    {
                                        var restorePos = new EntityPos(originalX, originalY, originalZ, originalYaw, originalPitch);
                                        entity.TeleportTo(restorePos);
                                        modSystem?.serverChannel?.SendPacket(new PolisSetViewDirectionPacket { Yaw = originalYaw, Pitch = originalPitch }, player);

                                        if (result == null)
                                        {
                                            tcs.SetResult(new { error = "Screenshot response timeout" });
                                        }
                                        else if (!result.Success)
                                        {
                                            tcs.SetResult(new { ok = false, error = result.Error ?? "Screenshot capture failed" });
                                        }
                                        else
                                        {
                                            tcs.SetResult(new
                                            {
                                                ok = true,
                                                width = result.Width,
                                                height = result.Height,
                                                base64Png = result.Base64Png,
                                                filePath = result.FilePath,
                                                captureTimeMs = result.CaptureTimeMs,
                                                viewpoint = new { x, y, z, yaw, pitch }
                                            });
                                        }
                                    }, "polis-observer-restore");
                                });
                            }, 100); // 100ms delay for render
                        }
                        catch (Exception ex)
                        {
                            tcs.SetResult(new { error = ex.Message });
                        }
                    }, "polis-observer-screenshot");
                }
            }
            else if (path == "/polis/servercmd" && request.HttpMethod == "POST")
            {
                if (!IsLoopbackRequest(request))
                {
                    tcs.SetResult(new { error = "Remote access not allowed" });
                }
                else
                {
                    string body;
                    using (var reader = new StreamReader(request.InputStream, request.ContentEncoding))
                    {
                        body = reader.ReadToEnd();
                    }

                    ServerCommandRequest cmdReq;
                    try
                    {
                        cmdReq = JsonSerializer.Deserialize<ServerCommandRequest>(body, new JsonSerializerOptions
                        {
                            PropertyNameCaseInsensitive = true
                        });
                    }
                    catch
                    {
                        tcs.SetResult(new { error = "Invalid JSON body. Expected: {\"cmd\":\"/time set 0\", \"playerUid\":\"...\"}" });
                        cmdReq = null;
                    }

                    if (cmdReq != null)
                    {
                        sapi.Event.EnqueueMainThreadTask(() =>
                        {
                            try
                            {
                                if (string.IsNullOrWhiteSpace(cmdReq.Cmd))
                                {
                                    tcs.SetResult(new { error = "Missing cmd" });
                                    return;
                                }

                                var caller = new Caller();
                                if (!string.IsNullOrWhiteSpace(cmdReq.PlayerUid))
                                {
                                    var player = sapi.World.PlayerByUid(cmdReq.PlayerUid) as IServerPlayer;
                                    if (player == null)
                                    {
                                        tcs.SetResult(new { error = "Player not found" });
                                        return;
                                    }
                                    caller.Player = player;
                                }
                                else
                                {
                                    caller.Type = EnumCallerType.Console;
                                }

                                caller.CallerPrivileges = new[] { "*" };
                                var args = new TextCommandCallingArgs { Caller = caller };

                                sapi.ChatCommands.ExecuteUnparsed(cmdReq.Cmd, args, result =>
                                {
                                    tcs.SetResult(BuildChatCommandResult(result));
                                });
                            }
                            catch (Exception ex)
                            {
                                tcs.SetResult(new { error = ex.Message });
                            }
                        }, "polis-harness-servercmd");
                    }
                }
            }
            else if (path == "/polis/command" && request.HttpMethod == "POST")
            {
                string body;
                using (var reader = new StreamReader(request.InputStream, request.ContentEncoding))
                {
                    body = reader.ReadToEnd();
                }

                CommandRequest cmdReq;
                try
                {
                    cmdReq = JsonSerializer.Deserialize<CommandRequest>(body, new JsonSerializerOptions
                    {
                        PropertyNameCaseInsensitive = true
                    });
                }
                catch
                {
                    tcs.SetResult(new { error = "Invalid JSON body. Expected: {\"cmd\":\"...\", \"args\":[...]}" });
                    cmdReq = null;
                }

                if (cmdReq != null)
                {
                    sapi.Event.EnqueueMainThreadTask(() =>
                    {
                        try
                        {
                            var cmdResult = executeCommandFunc(cmdReq.Cmd, cmdReq.Args ?? Array.Empty<string>(), cmdReq.Context);
                            tcs.SetResult(cmdResult);
                        }
                        catch (Exception ex)
                        {
                            tcs.SetResult(new CommandResult { Ok = false, Message = ex.Message });
                        }
                    }, "polis-harness-cmd");
                }
            }
            else if (path == "/" || path == "/polis")
            {
                // Health check / info endpoint
                tcs.SetResult(new
                {
                    service = "polis-test-harness",
                    version = "1.2",
                    endpoints = new[]
                    {
                        "GET /polis/ui - Web test UI",
                        "GET /polis/ui2 - Web UI v2",
                        "GET /polis/ui2/* - Web UI v2 static files",
                        "GET /polis/state?botId=&radius=10",
                        "GET /polis/status",
                        "GET /polis/players",
                        "GET /polis/player?uid=",
                        "GET /polis/look?uid=&range=48",
                        "GET /polis/targets?playerUid=&botId=&radius=6&limit=20&mode=blocks|entities|all&q=&codeContains=&requireEntityClass=&includeDead=",
                        "GET /polis/bots",
                        "GET /polis/container-contents?name=|x=&y=&z= - Get container inventory",
                        "GET /polis/zones - List all named zones",
                        "GET /polis/zone-check?botId= - Check which zones a bot is in",
                        "GET /polis/screenshot?playerUid=&save=false - Capture screenshot from player's client",
                        "GET /polis/observer-screenshot?playerUid=&x=&y=&z=&yaw=&pitch=&save=false - Screenshot from arbitrary position (player restored after)",
                        "GET /polis/events?limit=20 - Recent WebSocket event history",
                        "POST /polis/command {\"cmd\":\"...\",\"args\":[...]}",
                        "POST /polis/servercmd {\"cmd\":\"/time set 0\",\"playerUid\":\"optional\"}",
                        "WS ws://localhost:8585/polis/ws - Subscribe: {\"subscribe\":{\"level\":\"normal|info|debug\"}}"
                    },
                    websocket = new
                    {
                        url = $"ws://localhost:{port}/polis/ws",
                        subscriptionLevels = new[] { "normal", "info", "debug" },
                        eventTypes = new[] { "action_complete", "bot_spawned", "bot_died", "bot_unloaded", "debug_toggled", "log" }
                    }
                });
            }
            else if (path.StartsWith("/polis/ui2/") && request.HttpMethod == "GET")
            {
                var subPath = path.Substring("/polis/ui2/".Length);
                var relativePath = string.IsNullOrEmpty(subPath) ? "tools/webui-v2/index.html" : "tools/webui-v2/" + subPath;
                var ext = Path.GetExtension(relativePath).ToLower();
                var contentType = ext switch {
                    ".html" => "text/html",
                    ".css" => "text/css",
                    ".js" => "application/javascript",
                    ".json" => "application/json",
                    ".png" => "image/png",
                    ".svg" => "image/svg+xml",
                    _ => "application/octet-stream"
                };
                ServeStaticFile(response, relativePath, contentType);
                return;
            }
            else if (path == "/polis/ui2" && request.HttpMethod == "GET")
            {
                // Redirect to trailing slash so relative URLs resolve correctly
                response.StatusCode = 301;
                response.Headers.Set("Location", "/polis/ui2/");
                response.Close();
                return;
            }
            else if (path == "/polis/ui" && request.HttpMethod == "GET")
            {
                // Serve test UI HTML file
                ServeStaticFile(response, "tools/test-ui.html", "text/html");
                return; // Already handled response
            }
            else
            {
                response.StatusCode = 404;
                tcs.SetResult(new { error = "Not found", path });
            }

            // Wait for main thread task to complete (with timeout)
            if (tcs.Task.Wait(TimeSpan.FromSeconds(10)))
            {
                result = tcs.Task.Result;
            }
            else
            {
                result = new { error = "Timeout waiting for game thread" };
            }

            // Send response
            response.ContentType = "application/json";
            var json = JsonSerializer.Serialize(result, new JsonSerializerOptions { WriteIndented = true });
            var buffer = Encoding.UTF8.GetBytes(json);
            response.ContentLength64 = buffer.Length;
            response.OutputStream.Write(buffer, 0, buffer.Length);
        }
        catch (Exception ex)
        {
            sapi.Logger.Warning($"{LogPrefix} Request error: {ex.Message}");
            try
            {
                response.StatusCode = 500;
                var error = JsonSerializer.Serialize(new { error = ex.Message });
                var buffer = Encoding.UTF8.GetBytes(error);
                response.ContentLength64 = buffer.Length;
                response.OutputStream.Write(buffer, 0, buffer.Length);
            }
            catch { }
        }
        finally
        {
            try { response.Close(); } catch { }
        }
    }

    private string FindModDirectory()
    {
        // Try to find the mod directory from the assembly location
        try
        {
            var assemblyPath = System.Reflection.Assembly.GetExecutingAssembly().Location;
            if (!string.IsNullOrEmpty(assemblyPath))
            {
                var dir = Path.GetDirectoryName(assemblyPath);
                if (dir != null && Directory.Exists(dir))
                {
                    sapi.Logger.Debug($"{LogPrefix} Mod directory: {dir}");
                    return dir;
                }
            }
        }
        catch (Exception ex)
        {
            sapi.Logger.Warning($"{LogPrefix} Could not determine mod directory: {ex.Message}");
        }
        return null;
    }

    private void ServeStaticFile(HttpListenerResponse response, string relativePath, string contentType)
    {
        try
        {
            if (modDirectory == null)
            {
                response.StatusCode = 500;
                var error = Encoding.UTF8.GetBytes("{\"error\":\"Mod directory not found\"}");
                response.ContentType = "application/json";
                response.ContentLength64 = error.Length;
                response.OutputStream.Write(error, 0, error.Length);
                response.Close();
                return;
            }

            var fullPath = Path.Combine(modDirectory, relativePath);
            if (!File.Exists(fullPath))
            {
                response.StatusCode = 404;
                var error = Encoding.UTF8.GetBytes($"{{\"error\":\"File not found: {relativePath}\"}}");
                response.ContentType = "application/json";
                response.ContentLength64 = error.Length;
                response.OutputStream.Write(error, 0, error.Length);
                response.Close();
                return;
            }

            var content = File.ReadAllBytes(fullPath);
            response.StatusCode = 200;
            response.ContentType = contentType;
            response.Headers.Add("Access-Control-Allow-Origin", "*");
            response.ContentLength64 = content.Length;
            response.OutputStream.Write(content, 0, content.Length);
            response.Close();
        }
        catch (Exception ex)
        {
            sapi.Logger.Warning($"{LogPrefix} Error serving file {relativePath}: {ex.Message}");
            try
            {
                response.StatusCode = 500;
                var error = Encoding.UTF8.GetBytes($"{{\"error\":\"{ex.Message}\"}}");
                response.ContentType = "application/json";
                response.ContentLength64 = error.Length;
                response.OutputStream.Write(error, 0, error.Length);
                response.Close();
            }
            catch { }
        }
    }

    private async Task HandleWebSocketUpgradeAsync(HttpListenerContext context)
    {
        WebSocketContext wsContext = null;
        string connId = null;
        try
        {
            wsContext = await context.AcceptWebSocketAsync(null);
            connId = broadcaster.AddConnection(wsContext.WebSocket);
            sapi.Logger.Debug($"{LogPrefix} WebSocket connected: {connId}");

            await HandleWebSocketConnectionAsync(connId, wsContext.WebSocket);
        }
        catch (WebSocketException ex)
        {
            sapi.Logger.Warning($"{LogPrefix} WebSocket error: {ex.Message}");
        }
        catch (Exception ex)
        {
            sapi.Logger.Warning($"{LogPrefix} WebSocket handler error: {ex.Message}");
        }
        finally
        {
            if (connId != null)
            {
                broadcaster?.RemoveConnection(connId);
            }
        }
    }

    private async Task HandleWebSocketConnectionAsync(string connId, WebSocket socket)
    {
        var buffer = new byte[4096];
        var lastPing = DateTime.UtcNow;

        while (socket.State == WebSocketState.Open && !cts.Token.IsCancellationRequested)
        {
            try
            {
                // Use a timeout so we can send periodic pings
                using var timeoutCts = new CancellationTokenSource(PolisConstants.WsPingIntervalMs);
                using var linkedCts = CancellationTokenSource.CreateLinkedTokenSource(cts.Token, timeoutCts.Token);

                try
                {
                    var result = await socket.ReceiveAsync(new ArraySegment<byte>(buffer), linkedCts.Token);

                    if (result.MessageType == WebSocketMessageType.Close)
                    {
                        await socket.CloseAsync(WebSocketCloseStatus.NormalClosure, "Client requested close", CancellationToken.None);
                        break;
                    }

                    if (result.MessageType == WebSocketMessageType.Text)
                    {
                        var message = Encoding.UTF8.GetString(buffer, 0, result.Count);
                        HandleWebSocketMessage(connId, message);
                    }
                }
                catch (OperationCanceledException) when (timeoutCts.IsCancellationRequested && !cts.Token.IsCancellationRequested)
                {
                    // Timeout - send a ping to keep connection alive
                    if (socket.State == WebSocketState.Open)
                    {
                        try
                        {
                            // Send a ping frame (empty payload)
                            var pingData = new ArraySegment<byte>(Array.Empty<byte>());
                            await socket.SendAsync(pingData, WebSocketMessageType.Binary, true, CancellationToken.None);
                            lastPing = DateTime.UtcNow;
                        }
                        catch (WebSocketException)
                        {
                            // Connection likely closed, exit loop
                            break;
                        }
                    }
                }
            }
            catch (OperationCanceledException) when (cts.Token.IsCancellationRequested)
            {
                break;
            }
            catch (WebSocketException)
            {
                break;
            }
        }
    }

    private void HandleWebSocketMessage(string connId, string message)
    {
        try
        {
            var msg = JsonSerializer.Deserialize<WsClientMessage>(message, new JsonSerializerOptions
            {
                PropertyNameCaseInsensitive = true
            });

            if (msg?.Subscribe != null)
            {
                var level = msg.Subscribe.GetLevel();
                broadcaster.UpdateSubscription(connId, level);
            }
        }
        catch (JsonException ex)
        {
            sapi.Logger.Debug($"{LogPrefix} Invalid WebSocket message from {connId}: {ex.Message}");
        }
    }

    public class CommandRequest
    {
        public string Cmd { get; set; }
        public string[] Args { get; set; }
        public CommandContext Context { get; set; }
    }

    public class ServerCommandRequest
    {
        public string Cmd { get; set; }
        public string PlayerUid { get; set; }
    }


    // Accepts a JSON number or a numeric string (clients are inconsistent).
    public class FlexibleLongConverter : System.Text.Json.Serialization.JsonConverter<long?>
    {
        public override long? Read(ref System.Text.Json.Utf8JsonReader reader, Type typeToConvert, System.Text.Json.JsonSerializerOptions options)
        {
            if (reader.TokenType == System.Text.Json.JsonTokenType.String)
            {
                var sv = reader.GetString();
                return long.TryParse(sv, out var v) ? v : (long?)null;
            }
            if (reader.TokenType == System.Text.Json.JsonTokenType.Number)
            {
                return reader.GetInt64();
            }
            reader.Skip();
            return null;
        }

        public override void Write(System.Text.Json.Utf8JsonWriter writer, long? value, System.Text.Json.JsonSerializerOptions options)
        {
            if (value.HasValue) writer.WriteNumberValue(value.Value);
            else writer.WriteNullValue();
        }
    }

    public class CommandContext
    {
        public string PlayerUid { get; set; }
        [System.Text.Json.Serialization.JsonConverter(typeof(FlexibleLongConverter))]
        public long? BotId { get; set; }
        public bool UseLookTarget { get; set; }
        public double[] SpawnOffset { get; set; }
        public double[] GotoOffset { get; set; }
        public string Profession { get; set; }
    }

    public class CommandResult
    {
        public bool Ok { get; set; }
        public string Message { get; set; }
        public object Data { get; set; }
    }



    public class TargetsResult
    {
        public bool Ok { get; set; }
        public double[] Center { get; set; }
        public float Radius { get; set; }
        public List<TargetBlockInfo> Blocks { get; set; } = new List<TargetBlockInfo>();
        public List<TargetEntityInfo> Entities { get; set; } = new List<TargetEntityInfo>();

        public class TargetBlockInfo
        {
            public int[] Pos { get; set; }
            public string Code { get; set; }
            public double Dist { get; set; }
            public string EntityClass { get; set; }
            public bool PlacedPriorityInteract { get; set; }
            public List<string> Behaviors { get; set; }
            public List<string> Reasons { get; set; }
        }

        public class TargetEntityInfo
        {
            public long Id { get; set; }
            public string Code { get; set; }
            public string Class { get; set; }
            public double[] Pos { get; set; }
            public double Dist { get; set; }
            public string ItemCode { get; set; }
            public int? ItemQty { get; set; }
            public bool Alive { get; set; }
        }
    }

    static string[] ParseFilterTokens(string raw)
    {
        if (string.IsNullOrWhiteSpace(raw)) return Array.Empty<string>();
        return raw
            .Split(',')
            .Select(token => token.Trim())
            .Where(token => token.Length > 0)
            .ToArray();
    }

    static bool MatchesQuery(string query, IEnumerable<string> values)
    {
        if (string.IsNullOrWhiteSpace(query)) return true;
        foreach (var value in values)
        {
            if (!string.IsNullOrWhiteSpace(value) && value.IndexOf(query, StringComparison.OrdinalIgnoreCase) >= 0)
            {
                return true;
            }
        }
        return false;
    }

    static bool MatchesAnyFilter(string[] filters, params string[] values)
    {
        if (filters == null || filters.Length == 0) return true;
        foreach (var filter in filters)
        {
            foreach (var value in values)
            {
                if (!string.IsNullOrWhiteSpace(value) && value.IndexOf(filter, StringComparison.OrdinalIgnoreCase) >= 0)
                {
                    return true;
                }
            }
        }
        return false;
    }

    object BuildPlayerInfo(IServerPlayer player)
    {
        if (player?.Entity == null) return null;

        var pos = player.Entity.ServerPos.XYZ;
        var eyePos = pos.AddCopy(player.Entity.LocalEyePos);

        return new
        {
            uid = player.PlayerUID,
            name = player.PlayerName,
            pos = new[] { pos.X, pos.Y, pos.Z },
            yaw = player.Entity.ServerPos.Yaw,
            pitch = player.Entity.ServerPos.Pitch,
            eyePos = new[] { eyePos.X, eyePos.Y, eyePos.Z },
            dimension = player.Entity.ServerPos.Dimension
        };
    }

    object BuildLookInfo(IServerPlayer player, float range)
    {
        var entity = player.Entity;
        var eyePos = entity.ServerPos.XYZ.AddCopy(entity.LocalEyePos);

        BlockSelection blockSel = null;
        EntitySelection entSel = null;
        sapi.World.RayTraceForSelection(
            eyePos,
            entity.ServerPos.Pitch,
            entity.ServerPos.Yaw,
            range,
            ref blockSel,
            ref entSel
        );

        var lookVec = EntityPos.GetViewVector(entity.ServerPos.Pitch, entity.ServerPos.Yaw);

        object blockInfo = null;
        if (blockSel?.Position != null)
        {
            var hitPos = blockSel.HitPosition ?? new Vec3d(0.5, 0.5, 0.5);
            var fullPos = blockSel.Position.ToVec3d().AddCopy(hitPos);
            blockInfo = new
            {
                pos = new[] { blockSel.Position.X, blockSel.Position.Y, blockSel.Position.Z },
                face = blockSel.Face?.Code,
                hit = new[] { fullPos.X, fullPos.Y, fullPos.Z },
                code = blockSel.Block?.Code?.ToString()
            };
        }

        object entityInfo = null;
        if (entSel?.Entity != null)
        {
            var entPos = entSel.Entity.ServerPos.XYZ;
            entityInfo = new
            {
                id = entSel.Entity.EntityId,
                code = entSel.Entity.Code?.ToString(),
                pos = new[] { entPos.X, entPos.Y, entPos.Z },
                face = entSel.Face?.Code,
                hit = entSel.HitPosition != null
                    ? new[] { entSel.HitPosition.X, entSel.HitPosition.Y, entSel.HitPosition.Z }
                    : null
            };
        }

        return new
        {
            ok = true,
            lookVec = new[] { lookVec.X, lookVec.Y, lookVec.Z },
            blockSelection = blockInfo,
            entitySelection = entityInfo
        };
    }

    bool IsLoopbackRequest(HttpListenerRequest request)
    {
        var address = request?.RemoteEndPoint?.Address;
        return address != null && IPAddress.IsLoopback(address);
    }

    object BuildChatCommandResult(TextCommandResult result)
    {
        if (result == null)
        {
            return new { ok = false, status = EnumCommandStatus.UnknownLegacy.ToString(), message = "No result returned" };
        }

        return new
        {
            ok = result.Status == EnumCommandStatus.Success,
            status = result.Status.ToString(),
            message = result.StatusMessage,
            errorCode = result.ErrorCode,
            data = result.Data
        };
    }
}
