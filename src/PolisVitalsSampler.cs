using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using Vintagestory.API.Common;
using Vintagestory.API.Common.Entities;
using Vintagestory.API.Server;
using Vintagestory.API.Util;
using Vintagestory.GameContent;

// ---------------------------------------------------------------------
// Vitals sampler (A1 of the survival lane, 2026-10-07): one per-second
// tick (the PolisForageController OnTick/accumulator pattern) that
// samples every loaded bot and every online player:
//
//   * the synced "hunger" tree (currentsaturation / maxsaturation)
//   * the "health" tree (currenthealth / maxhealth)
//   * position
//   * the behavior levels the entity exposes. The mod has no
//     skill/XP system yet (EntityPolisBot carries only a "stub for a
//     future skill system"), so `skills` is the set of present
//     behaviors, each at level 1 - when the skill system lands, this
//     is the place its levels plug in.
//
// The latest snapshot is held in memory and served by GET
// /polis/vitals (JSON: { world:{time,day}, entities:[{uid,code,name,
// sat,satMax,hp,hpMax,pos,skills}] }) and the `vitals` harness command
// (`vitals [uid]`).
//
// The running per-world record is persisted with the bot registry
// (PolisGlobalData.Vitals, same StoreData("polis-bots") path as the
// zone records the forage lane asked to mirror): the series is
// downsampled to at most one sample per persistence interval per
// entity (default: 1 in-game hour) and capped per entity, so the
// world-save stays bounded. In addition to the hourly tick, the whole
// record is written again on world save (OnGameWorldSave serializes
// globalData, Vitals included) and on load (OnSaveGameLoaded null-
// guards it).
//
// Configuration: <mod dir>/assets/polis/polis-vitals.json - the same
// load path and hot-reload pattern as polis-policies.json (the contract
// said "world directory, same load path as polis-policies.json"; the
// policies file lives in the mod's assets directory, so vitals do the
// same). Shape (all fields optional, defaults as in this file):
//
//   { "note": "...",
//     "sampleHz": 1.0,
//     "persistHz": 0.000277,   // in-game Hz; 1/3600 = one per in-game hour
//     "fields": ["sat","satMax","hp","hpMax","pos","skills"] }
// ---------------------------------------------------------------------

internal class PolisVitalsConfig
{
    public float sampleHz { get; set; } = 1.0f;
    public float persistHz { get; set; } = 1f / 3600f;
    public List<string> fields { get; set; } = new() { "sat", "satMax", "hp", "hpMax", "pos", "skills" };

    public float SampleIntervalSec => sampleHz > 0.01f ? 1f / sampleHz : 1f;
    public float PersistIntervalGameSec => persistHz > 1e-7f ? 1f / persistHz : 3600f;

    public bool HasField(string field)
        => fields == null || fields.Count == 0 || fields.Contains(field, StringComparer.OrdinalIgnoreCase);
}

public partial class PolisSystem
{
    // ----- vitals sampler (1 Hz; called from OnTick like ForageOnTick) -----

    readonly PolisVitalsConfig vitalsConfig = new PolisVitalsConfig();
    string vitalsConfigPath;
    DateTime vitalsConfigMtime = DateTime.MinValue;
    readonly Dictionary<long, VitalsSample> vitalsLatest = new();
    long lastVitalsPersistGameSec = -1;
    long lastVitalsPersistMs;
    float vitalsSampleAccum;

    // Real-time throttle for the StoreData write: under the daylock
    // fast-forward (6000x) an in-game hour passes every few ms, so
    // "one sample per in-game hour" alone would serialize the world
    // save every tick. At most one persist per 30 real seconds.
    const float VitalsPersistMinIntervalMs = 30000f;

    void VitalsReloadConfig()
    {
        if (vitalsConfigPath == null)
        {
            try
            {
                string asm = Assembly.GetExecutingAssembly().Location;
                if (string.IsNullOrEmpty(asm)) return;
                string dir = Path.GetDirectoryName(asm);
                if (dir == null) return;
                vitalsConfigPath = Path.Combine(dir, "assets", "polis", "polis-vitals.json");
            }
            catch
            {
                return;
            }
        }
        if (!File.Exists(vitalsConfigPath)) return;

        var mtime = File.GetLastWriteTimeUtc(vitalsConfigPath);
        if (mtime == vitalsConfigMtime) return;
        vitalsConfigMtime = mtime;

        try
        {
            var parsed = JsonSerializer.Deserialize<PolisVitalsConfig>(File.ReadAllText(vitalsConfigPath),
                new JsonSerializerOptions { PropertyNameCaseInsensitive = true });
            if (parsed != null)
            {
                vitalsConfig = parsed;
                sapi?.Logger?.Notification(
                    $"[polis] vitals config loaded: sample={vitalsConfig.sampleHz}Hz persist={vitalsConfig.persistHz}Hz (1/{vitalsConfig.PersistIntervalGameSec:F0} game-s) fields={string.Join(",", vitalsConfig.fields ?? new List<string>())}");
            }
        }
        catch (Exception ex)
        {
            // keep the last good config (or the defaults) on a bad file
            sapi?.Logger?.Warning($"[polis] vitals config parse error (keeping previous): {ex.Message}");
        }
    }

    /// <summary>
    /// The latest vitals snapshot for the endpoint / command:
    /// { world:{time,day}, entities:[ ... ] }, optional uid filter
    /// (numeric EntityId or case-insensitive name).
    /// </summary>
    internal object GetVitalsEndpointPayload(string uid)
    {
        if (sapi?.World == null)
            return new { ok = false, error = "no world" };

        VitalsReloadConfig();

        var cal = sapi.World.Calendar;
        long nowGameSec = (long)(cal.TotalDays * 86400 + cal.HourOfDay * 3600);

        List<object> rows;
        if (string.IsNullOrWhiteSpace(uid))
        {
            rows = new List<object>();
            foreach (var kv in vitalsLatest)
                rows.Add(VitalsToJson(kv.Value));
            rows = rows.OrderBy(r => (r as Dictionary<string, object>)["uid"].ToString()).ToList();
        }
        else
        {
            VitalsSample found = null;
            if (long.TryParse(uid, out var lid) && vitalsLatest.TryGetValue(lid, out var byId))
            {
                found = byId;
            }
            else
            {
                foreach (var kv in vitalsLatest)
                {
                    if (kv.Value.Name != null && kv.Value.Name.Equals(uid, StringComparison.OrdinalIgnoreCase))
                    {
                        found = kv.Value;
                        break;
                    }
                }
            }

            if (found == null)
                return new { ok = false, error = $"no vitals for uid '{uid}'" };

            rows = new List<object> { VitalsToJson(found) };
        }

        return new
        {
            ok = true,
            world = new { time = nowGameSec, day = (long)cal.TotalDays },
            entities = rows
        };
    }

    object VitalsToJson(VitalsSample s)
    {
        var o = new Dictionary<string, object>
        {
            ["uid"] = s.EntityId,
            ["code"] = s.Code,
            ["name"] = s.Name
        };
        if (vitalsConfig.HasField("sat")) o["sat"] = s.Sat;
        if (vitalsConfig.HasField("satMax")) o["satMax"] = s.SatMax;
        if (vitalsConfig.HasField("hp")) o["hp"] = s.Hp;
        if (vitalsConfig.HasField("hpMax")) o["hpMax"] = s.HpMax;
        if (vitalsConfig.HasField("pos")) o["pos"] = new { x = s.X, y = s.Y, z = s.Z };
        if (vitalsConfig.HasField("skills")) o["skills"] = s.Skills ?? new Dictionary<string, int>();
        return o;
    }

    static VitalsSample VitalsSampleEntity(Vintagestory.API.Common.Entities.Entity e)
    {
        var cal = e.World.Calendar;
        long gameTimeSec = (long)(cal.TotalDays * 86400 + cal.HourOfDay * 3600);

        // Name is set by the caller (registry name for bots, PlayerName
        // for players) - the Entity base has no reliable public name.
        var sample = new VitalsSample
        {
            EntityId = e.EntityId,
            Code = e.Code?.ToString(),
            X = e.ServerPos.X,
            Y = e.ServerPos.Y,
            Z = e.ServerPos.Z,
            GameTimeSec = gameTimeSec,
            GameDay = (long)cal.TotalDays,
            Skills = VitalsBehaviorLevels(e)
        };

        var hunger = e.WatchedAttributes.GetTreeAttribute("hunger");
        if (hunger != null)
        {
            sample.Sat = hunger.GetFloat("currentsaturation", 0f);
            sample.SatMax = hunger.GetFloat("maxsaturation", 0f);
        }

        var health = e.WatchedAttributes.GetTreeAttribute("health");
        if (health != null)
        {
            sample.Hp = health.GetFloat("currenthealth", 0f);
            sample.HpMax = health.GetFloat("maxhealth", 0f);
        }

        return sample;
    }

    /// <summary>
    /// Behavior levels the entity exposes: each present survival
    /// behavior at level 1. The mod has no skill/XP state yet, so this
    /// is the "skills" of a bot or player as of 2026-10-07.
    /// </summary>
    static Dictionary<string, int> VitalsBehaviorLevels(Vintagestory.API.Common.Entities.Entity e)
    {
        var skills = new Dictionary<string, int>();
        if (e.GetBehavior<EntityBehaviorHunger>() != null) skills["hunger"] = 1;
        if (e.GetBehavior<EntityBehaviorHealth>() != null) skills["health"] = 1;
        if (e.GetBehavior<EntityBehaviorSeraphInventory>() != null) skills["seraphInventory"] = 1;
        return skills;
    }

    void VitalsOnTick(float dt)
    {
        if (sapi?.World == null || sapi.WorldManager?.SaveGame == null) return;
        VitalsReloadConfig();

        vitalsSampleAccum += dt;
        if (vitalsSampleAccum < vitalsConfig.SampleIntervalSec) return;
        vitalsSampleAccum = 0f;

        // --- sample: every loaded bot ---
        foreach (var bot in bots.Values)
        {
            var e = bot?.Entity;
            if (e == null || !e.Alive) continue;

            string name = null;
            if (globalData.Bots.TryGetValue(e.EntityId, out var rec) && !string.IsNullOrWhiteSpace(rec.Name))
            {
                name = rec.Name;
            }
            if (name == null)
            {
                // fallback: the name written on spawn (polisName), else the id
                name = "";
                if (e.WatchedAttributes is Vintagestory.API.Datastructures.TreeAttribute wt)
                    name = wt.GetString("polisName", "");
                if (string.IsNullOrWhiteSpace(name)) name = "Bot " + e.EntityId;
            }

            var sample = VitalsSampleEntity(e);
            sample.Name = name;
            vitalsLatest[e.EntityId] = sample;
        }

        // --- sample: every online player ---
        var players = sapi.World.AllOnlinePlayers;
        if (players != null)
        {
            foreach (var p in players)
            {
                var e = p?.Entity;
                if (e == null || !e.Alive) continue;
                var sample = VitalsSampleEntity(e);
                sample.Name = p.PlayerName;
                vitalsLatest[e.EntityId] = sample;
            }
        }

        // --- drop entities that are gone (bots already cleaned in OnTick) ---
        if (vitalsLatest.Count > 0)
        {
            var gone = new List<long>();
            foreach (var kv in vitalsLatest)
            {
                if (!bots.ContainsKey(kv.Key) && sapi.World.GetEntityById(kv.Key) == null)
                    gone.Add(kv.Key);
            }
            foreach (var id in gone)
                vitalsLatest.Remove(id);
        }

        // --- persist: downsample to <=1 sample per interval, real-time throttled ---
        long nowGameSec = (long)(sapi.World.Calendar.TotalDays * 86400 + sapi.World.Calendar.HourOfDay * 3600);
        long intervalSec = (long)Math.Max(1, vitalsConfig.PersistIntervalGameSec);
        long nowMs = sapi.World.ElapsedMilliseconds;

        if (vitalsLatest.Count > 0 && globalData.Vitals != null
            && (lastVitalsPersistGameSec < 0 || nowGameSec - lastVitalsPersistGameSec >= intervalSec)
            && nowMs - lastVitalsPersistMs >= VitalsPersistMinIntervalMs)
        {
            int maxSamples = globalData.Vitals.MaxSeriesSamples > 0 ? globalData.Vitals.MaxSeriesSamples : 336;
            if (globalData.Vitals.Series == null)
                globalData.Vitals.Series = new Dictionary<long, List<VitalsSample>>();

            foreach (var kv in vitalsLatest)
            {
                if (!globalData.Vitals.Series.TryGetValue(kv.Key, out var series))
                {
                    series = new List<VitalsSample>();
                    globalData.Vitals.Series[kv.Key] = series;
                }

                if (series.Count > 0 && nowGameSec - series[series.Count - 1].GameTimeSec < intervalSec)
                {
                    // same persistence interval: replace the last sample
                    series[series.Count - 1] = kv.Value;
                }
                else
                {
                    series.Add(kv.Value);
                }

                while (series.Count > maxSamples)
                    series.RemoveAt(0);
            }

            lastVitalsPersistGameSec = nowGameSec;
            lastVitalsPersistMs = nowMs;
            sapi.WorldManager.SaveGame.StoreData("polis-bots", SerializerUtil.Serialize(globalData));
        }
    }

    /// <summary>
    /// True if <paramref name="uid"/> (numeric EntityId or name, case-
    /// insensitive; null/blank matches everything) has a current vitals
    /// sample. Used by the `vitals` command to reject unknown uids.
    /// </summary>
    bool VitalsHasEntity(string uid)
    {
        if (string.IsNullOrWhiteSpace(uid)) return true;
        if (long.TryParse(uid, out var lid) && vitalsLatest.ContainsKey(lid)) return true;
        return vitalsLatest.Values.Any(s => s.Name != null && s.Name.Equals(uid, StringComparison.OrdinalIgnoreCase));
    }
}
