using System;
using System.IO;
using Vintagestory.API.Common;
using Vintagestory.API.Common.Entities;
using Vintagestory.API.Server;
using Vintagestory.GameContent;

/// <summary>
/// Polis variant of the engine's EntityBehaviorHunger (1.22 VSEssentials).
/// Inherits the WHOLE engine behavior (movement-coupled drain, five
/// nutrition levels and delays, clamping, starvation damage, sync, the
/// intoxication/psychedelic detox) and gates only the drain tick:
///
///   (1) parked gate — EntityPolisBot.HungerSuspended: a bot with no
///       active mission does not starve (bots are otherwise drained to
///       death in ~4 in-game hours of idling). The policy engine /
///       mission system owns this flag; the harness can toggle it
///       (`hungerpause`) for debugging.
///
///   (2) world gate — <DataBasePath>/Saves/<world>/polis/hunger.json
///       {"hungerMode": "off"} suspends the drain for the whole world
///       (dev/creative/debug worlds). Missing file or "full" = the
///       engine runs unmodified. The pilot (survival) worlds stay full.
///
/// Note: while suspended the inherited detox (intoxication/psychedelic
/// decay) also pauses — it lives in the same tick; acceptable, it
/// resumes when the gate clears.
/// </summary>
public class EntityBehaviorPolisHunger : EntityBehaviorHunger
{
    public EntityBehaviorPolisHunger(Entity entity) : base(entity)
    {
    }

    public override void OnGameTick(float deltaTime)
    {
        if (PolisWorldConfig.HungerSuspended(base.entity))
        {
            return;
        }
        base.OnGameTick(deltaTime);
    }
}

/// <summary>
/// Per-world polis configuration: <DataBasePath>/Saves/<world>/polis/hunger.json
/// {"hungerMode": "full" | "off"}. Read on file-change only (mtime cache);
/// a missing file means "full" (engine behavior unmodified).
/// </summary>
internal static class PolisWorldConfig
{
    static string cachedWorld;
    static DateTime cachedMtime = DateTime.MinValue;
    static bool cachedDisabled;

    public static bool HungerSuspended(Entity e)
    {
        // (1) parked bot: no active mission
        var bot = e as EntityPolisBot;
        if (bot != null && bot.HungerSuspended)
        {
            return true;
        }

        // (2) per-world switch (dev/creative worlds)
        var world = e.World as IServerWorldAccessor;
        string worldName = world?.WorldName;
        if (worldName == null)
        {
            return false;
        }

        string path;
        try
        {
            path = Path.Combine(e.Api.DataBasePath, "Saves", worldName, "polis", "hunger.json");
        }
        catch
        {
            return false;
        }

        if (File.Exists(path))
        {
            var mtime = File.GetLastWriteTimeUtc(path);
            if (worldName != cachedWorld || mtime != cachedMtime)
            {
                cachedWorld = worldName;
                cachedMtime = mtime;
                cachedDisabled = false;
                try
                {
                    using var fs = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite);
                    using var rd = new StreamReader(fs);
                    string json = rd.ReadToEnd();
                    // Keep parsing dependency-free: we only look for the
                    // single key the file format defines.
                    cachedDisabled = json.Contains("\"hungerMode\"") && json.Contains("\"off\"");
                }
                catch
                {
                    cachedDisabled = false;
                }
            }
            return cachedDisabled;
        }

        // file absent for this world: clear the cache if it was cached
        if (cachedWorld == worldName)
        {
            cachedWorld = null;
            cachedMtime = DateTime.MinValue;
            cachedDisabled = false;
        }
        return false;
    }
}
