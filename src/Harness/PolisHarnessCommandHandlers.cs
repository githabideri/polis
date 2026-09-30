using System;
using System.Collections.Generic;
using System.Linq;
using System.Globalization;
using System.Reflection;
using System.Text.Json;
using Vintagestory.API.Common;
using Vintagestory.API.Common.Entities;
using Vintagestory.API.Config;
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
                case "takefrom":
                    return ExecuteTakeFromCommand(args, context);
                case "putinto":
                    return ExecutePutIntoCommand(args, context);
                case "mine":
                    return ExecuteMineCommand(args, context);
                case "break":
                    return ExecuteBreakCommand(args, context);
                case "harvest":
                    return ExecuteHarvestCommand(args, context);
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
                case "animate":
                    return ExecuteAnimateCommand(args, context);
                case "teleport":
                    return ExecuteTeleportCommand(args, context);
                case "place":
                    return ExecutePlaceCommand(args, context);
                case "setblock":
                    return ExecuteSetBlockCommand(args, context);
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
                    result.Message = "Unknown command: " + cmd + ". Available: spawn, select, selectlook, autonomy, despawn, stop, give, drop, pickup, goto, gotolook, look, activate, ignite, interact, teststate, bots, takefrom, putinto, mine, break, harvest, harvestcrop, grind, press, butcher, clayform, knap, seal, possess, unpossess, setcontrols, spawnentity, killentity, animate, teleport, place, setblock, equip, scan, verify, container-register, container-list, container-remove, container-contents, zone-define, zone-remove, zone-list, zone-check, zone-show, viewpoint-define, viewpoint-list, viewpoint-remove, observer-screenshot, viewpoint-screenshot";
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

        // Add to persistent registry - use context player as owner if available
        var ownerUid = contextPlayer?.PlayerUID ?? "harness";
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

        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = $"Spawned bot #{entity.EntityId} ({resolvedCode}{profLabel})",
            Data = new { id = entity.EntityId, code = resolvedCode, pos = new[] { x, y, z }, profession = professionName }
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

    PolisTestHarness.CommandResult ExecuteDespawnCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        if (!TryGetHarnessBot(context, out var bot, out var err))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = err };
        }

        bot.Entity.Die(EnumDespawnReason.Removed);
        return new PolisTestHarness.CommandResult { Ok = true, Message = $"Despawned bot #{bot.Entity.EntityId}" };
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

    PolisTestHarness.CommandResult ExecuteMineCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        // Usage: mine <x> <y> <z> [autocollect]
        if (args.Length < 3)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Usage: mine <x> <y> <z> [true|false]" };
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
                bot.RecordActionResult("mine", false, $"goto failed: {msg}", sapi.World.ElapsedMilliseconds);
            }
        }

        void OnMineResult(bool ok, string msg)
        {
            bot.RecordActionResult("mine", ok, msg, sapi.World.ElapsedMilliseconds);
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

        StartActionSequence(bot, "mine", gotoAction, mineAction);

        float estTime = block.Resistance / 1.0f; // Rough estimate with default speed
        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = $"Bot #{bot.Entity.EntityId} mining {block.Code} at ({pos.X}, {pos.Y}, {pos.Z}), est {estTime:F1}s" + (autoCollect ? " (autocollect)" : ""),
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
        // Usage: teleport <playerUid> <x> <y> <z> [yaw] [pitch]
        // Teleports a player to the specified position with optional view direction
        if (args.Length < 4)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Usage: teleport <playerUid> <x> <y> <z> [yaw] [pitch]" };
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

        // Find the player
        var player = sapi.World.PlayerByUid(playerUid) as IServerPlayer;
        if (player == null)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"Player not found: {playerUid}" };
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

    // --- End HTTP Test Harness Callbacks ---
}
