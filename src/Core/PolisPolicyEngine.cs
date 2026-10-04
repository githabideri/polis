using System;
using System.IO;
using System.Text.Json;

namespace Polis.Core
{
    /// <summary>
    /// The polis interaction-rules layer (design:
    /// docs/design/food-hunger-skills-policies.md, section B). One
    /// evaluator for all domains:
    ///
    ///     PolisPolicyEngine.Instance.Evaluate("food", itemCode, foodCategory)
    ///     PolisPolicyEngine.Instance.Evaluate(player, "food", itemCode, foodCategory)
    ///         → (allow, reason)
    ///
    /// Rules come from the committed, versioned <mod>/assets/polis/
    /// polis-policies.json (hot-reloaded on file change, so a dev can
    /// iterate without a restart):
    ///
    ///   v1 (top level):   { "version": 1, "domains": { ... } }
    ///   v2 (profiles):    { "version": 2, "profiles": {
    ///                          "default": { "domains": { ... } },
    ///                          "<playerUid>": { "domains": { ... } } } }
    ///
    /// v2 exists because the rules layer must work on multiplayer servers:
    /// policies are PER PLAYER (2026-10-04 decision; per-settlement is a
    /// future layer beyond current scope). A profile's domain table is
    /// resolved per call: exact player key → "default" → v1 top level →
    /// deny. Matching within a domain: `category` is a case-insensitive
    /// name of the item's FoodNutritionProperties.FoodCategory (Fruit /
    /// Vegetable / Protein / Grain / Dairy / Unknown / NoNutrition);
    /// `code` is the full item code with `*` wildcards (`game:raw-*`).
    /// Both set → both must match. The highest-priority matching rule
    /// wins (ties: the later rule); no match → the domain default. Denials
    /// carry a reason string — call sites log them (rejection data, not
    /// noise).
    ///
    /// The food domain additionally carries the decision parameters of the
    /// food-pressure interrupt and the forage skill (data, not code):
    /// pressure { trigger, rearm } — fractions of max saturation; forage
    /// { maxRadius, ringWidth, blocksPerTick, maxTargets, blockPatterns };
    /// preempt { mode, waitTypes } — how a forage interrupt preempts the
    /// current job. All have sane defaults (see the classes below) so a
    /// file may omit them.
    ///
    /// Call sites (the eat action, the forage/feed sequences, later the
    /// planner filter and any use-check) only ever call Evaluate /
    /// GetProfile — a future per-settlement layer replaces the profile
    /// keying, not the call sites.
    /// </summary>
    public class PolisPolicyEngine
    {
        public static PolisPolicyEngine Instance { get; } = new PolisPolicyEngine();

        string filePath;
        DateTime lastMtime = DateTime.MinValue;
        string lastError;

        // Normalized view: every profile (v1 → single "default") keyed by
        // player key ("default" is the fallback profile).
        System.Collections.Generic.Dictionary<string, PolicyProfile> profiles =
            new System.Collections.Generic.Dictionary<string, PolicyProfile>();

        void Init(string path)
        {
            filePath = path;
        }

        /// <summary>
        /// Resolve the policy file from the deployed mod directory
        /// (<assembly dir>/assets/polis/polis-policies.json) and remember
        /// it. Returns the path, or null if the mod directory cannot be
        /// found.
        /// </summary>
        public string AutoInit()
        {
            if (filePath != null) return filePath;
            try
            {
                var asm = System.Reflection.Assembly.GetExecutingAssembly().Location;
                if (string.IsNullOrEmpty(asm)) return null;
                var dir = Path.GetDirectoryName(asm);
                if (dir == null) return null;
                filePath = Path.Combine(dir, "assets", "polis", "polis-policies.json");
            }
            catch
            {
                return null;
            }
            return filePath;
        }

        /// <summary>
        /// The last load/parse error (null when the file is good).
        /// </summary>
        public string LastError => lastError;

        /// <summary>
        /// Evaluate an item/action against a policy domain using the
        /// default profile. Unknown domain → deny (safe default for a
        /// rules layer).
        /// </summary>
        public (bool Allow, string Reason) Evaluate(string domain, string code, string foodCategory)
        {
            return Evaluate(null, domain, code, foodCategory);
        }

        /// <summary>
        /// Evaluate per player: resolves the profile by player key
        /// (uid in multiplayer, "default" as the fallback).
        /// </summary>
        public (bool Allow, string Reason) Evaluate(string player, string domain, string code, string foodCategory)
        {
            ReloadIfChanged();

            var profile = ResolveProfile(player);
            if (profile == null || !profile.domains.TryGetValue(domain, out var d))
            {
                return (false, $"no policy domain '{domain}' (profile: {(player ?? "default")}, file: {lastError ?? "missing"})");
            }

            return EvaluateDomain(d, code, foodCategory);
        }

        static (bool, string) EvaluateDomain(DomainPolicy d, string code, string foodCategory)
        {
            int bestPriority = int.MinValue;
            bool bestAllow = d.defaultAllow;
            string bestReason = $"domain default: {d.@default}";

            foreach (var rule in d.rules)
            {
                if (rule.match != null
                    && rule.match.category != null
                    && (foodCategory == null
                        || !string.Equals(rule.match.category, foodCategory, StringComparison.OrdinalIgnoreCase)))
                {
                    continue;
                }
                if (rule.match != null
                    && rule.match.code != null
                    && !WildcardMatch(rule.match.code, code))
                {
                    continue;
                }
                // a rule with no match fields matches everything in the domain
                if (rule.priority > bestPriority)
                {
                    bestPriority = rule.priority;
                    bestAllow = rule.allow;
                    bestReason = rule.id ?? (rule.match?.category ?? rule.match?.code) ?? "rule";
                }
            }

            return (bestAllow, bestReason);
        }

        static bool WildcardMatch(string pattern, string value)
        {
            return WildcardMatchPublic(pattern, value);
        }

        /// <summary>Public wildcard match ('*' patterns) — shared with the
        /// forage controller's block-pattern scan.</summary>
        public static bool WildcardMatchPublic(string pattern, string value)
        {
            if (pattern == null || value == null) return pattern == value;
            if (!pattern.Contains('*'))
                return string.Equals(pattern, value, StringComparison.OrdinalIgnoreCase);
            // split on '*' and require each fragment in order
            int pos = 0;
            foreach (var frag in pattern.Split('*'))
            {
                if (frag.Length == 0) continue;
                int idx = value.IndexOf(frag, pos, StringComparison.OrdinalIgnoreCase);
                if (idx < 0) return false;
                pos = idx + frag.Length;
            }
            return true;
        }

        // --- Profile resolution (v2) ---

        /// <summary>
        /// The resolved profile for a player: exact key → "default" →
        /// null (no policy data at all).
        /// </summary>
        public PolicyProfile ResolveProfile(string player)
        {
            ReloadIfChanged();
            if (profiles.Count == 0) return null;
            if (!string.IsNullOrEmpty(player) && profiles.TryGetValue(player, out var p)) return p;
            return profiles.TryGetValue("default", out var d) ? d : null;
        }

        /// <summary>
        /// The food-pressure parameters for a player: (trigger, rearm) as
        /// fractions of max saturation. The interrupt fires below
        /// `trigger`; it re-arms only above `rearm` (hysteresis, so a
        /// small eat cannot oscillate the interrupt on and off).
        /// Defaults: trigger 0.25, rearm 0.40.
        /// </summary>
        public (float Trigger, float Rearm) GetFoodPressure(string player)
        {
            var p = ResolveProfile(player)?.domains?.TryGetValue("food", out var f) == true ? f.pressure : null;
            float trigger = p?.trigger > 0f && p?.trigger < 1f ? p.trigger : 0.25f;
            float rearm = p?.rearm > trigger ? p.rearm : trigger + 0.15f;
            return (trigger, rearm);
        }

        /// <summary>
        /// The forage discovery parameters for a player (see the class
        /// defaults; a missing section → all defaults).
        /// </summary>
        public ForageParams GetForageConfig(string player)
        {
            var f = ResolveProfile(player)?.domains?.TryGetValue("food", out var d) == true ? d.forage : null;
            return f ?? new ForageParams();
        }

        /// <summary>
        /// The preemption parameters for a player: how a forage interrupt
        /// treats the job the bot is currently executing. mode:
        ///   immediate  — cancel the current job action right away
        ///   finish     — let the current action finish, then forage
        ///   safe-point — immediate for navigation-type actions, finish
        ///                for actions with side effects (waitTypes)
        /// Defaults: safe-point; waitTypes = the harvest/mine actions.
        /// </summary>
        public PreemptParams GetPreemptConfig(string player)
        {
            var f = ResolveProfile(player)?.domains?.TryGetValue("food", out var d) == true ? d.preempt : null;
            return f ?? new PreemptParams();
        }

        void ReloadIfChanged()
        {
            if (filePath == null) filePath = AutoInit();
            if (filePath == null || !File.Exists(filePath))
            {
                lastError = filePath == null ? "mod directory not found" : "file missing";
                if (lastError != null && profiles.Count == 0) return;
                return;
            }

            var mtime = File.GetLastWriteTimeUtc(filePath);
            if (mtime == lastMtime && profiles.Count > 0) return;

            try
            {
                string json = File.ReadAllText(filePath);
                var raw = JsonSerializer.Deserialize<PolicyFile>(json,
                    new JsonSerializerOptions { PropertyNameCaseInsensitive = true });

                var next = new System.Collections.Generic.Dictionary<string, PolicyProfile>();
                if (raw?.profiles != null && raw.profiles.Count > 0)
                {
                    // v2: per-player profiles; ensure a default exists
                    if (!raw.profiles.ContainsKey("default"))
                        raw.profiles["default"] = new PolicyProfile();
                    foreach (var kv in raw.profiles)
                    {
                        if (kv.Value == null) continue;
                        kv.Value.domains ??= new System.Collections.Generic.Dictionary<string, DomainPolicy>();
                        next[kv.Key] = kv.Value;
                    }
                }
                else if (raw?.domains != null && raw.domains.Count > 0)
                {
                    // v1: a single top-level domain table = the default profile
                    next["default"] = new PolicyProfile { domains = raw.domains };
                }

                if (next.Count > 0)
                {
                    profiles = next;
                    lastMtime = mtime;
                    lastError = null;
                }
            }
            catch (Exception ex)
            {
                lastError = $"parse error: {ex.Message}";
                // keep the last good table (or none) on a bad file
            }
        }
    }

    // --- File schema (mirrors assets/polis/polis-policies.json) ---

    internal class PolicyFile
    {
        public int version { get; set; }
        public System.Collections.Generic.Dictionary<string, DomainPolicy> domains { get; set; }
        public System.Collections.Generic.Dictionary<string, PolicyProfile> profiles { get; set; }
    }

    internal class PolicyProfile
    {
        public System.Collections.Generic.Dictionary<string, DomainPolicy> domains { get; set; }
    }

    internal class DomainPolicy
    {
        public string @default { get; set; } = "deny";
        public bool defaultAllow => string.Equals(@default, "allow", StringComparison.OrdinalIgnoreCase);
        public System.Collections.Generic.List<PolicyRule> rules { get; set; } = new();

        // food-domain decision parameters (data, not code)
        public FoodPressure pressure { get; set; }
        public ForageParams forage { get; set; }
        public PreemptParams preempt { get; set; }
    }

    internal class PolicyRule
    {
        public string id { get; set; }
        public PolicyMatch match { get; set; }
        public bool allow { get; set; }
        public int priority { get; set; }
    }

    internal class PolicyMatch
    {
        public string category { get; set; }
        public string code { get; set; }
    }

    /// <summary>
    /// Food-pressure interrupt thresholds, fractions of max saturation.
    /// trigger: below this the interrupt fires; rearm: the interrupt
    /// re-arms only above this (hysteresis).
    /// </summary>
    internal class FoodPressure
    {
        public float trigger { get; set; } = 0.25f;
        public float rearm { get; set; } = 0.40f;
    }

    /// <summary>
    /// Forage discovery: expanding square rings from the bot, up to
    /// maxRadius blocks, ringWidth blocks thick per ring; at most
    /// blocksPerTick block queries per game tick (chunked, no hitch);
    /// at most maxTargets bushes per forage episode. blockPatterns:
    /// '*' wildcards on the full block code (wild fruiting bushes by
    /// default — the forage skill targets nature, not planted crops).
    /// </summary>
    internal class ForageParams
    {
        public int maxRadius { get; set; } = 192;
        public int ringWidth { get; set; } = 32;
        public int blocksPerTick { get; set; } = 1024;
        public int maxTargets { get; set; } = 3;
        public System.Collections.Generic.List<string> blockPatterns { get; set; } =
            new() { "*fruitingbush-wild-*" };
    }

    /// <summary>
    /// Preemption mode for the food-pressure interrupt (see
    /// PolisPolicyEngine.GetPreemptConfig). waitTypes: the NAMES of job
    /// actions (as started through StartActionSequence — "mine",
    /// "harvest", "place", ...) that carry side effects and are
    /// therefore only preempted at their finish (safe-point mode).
    /// </summary>
    internal class PreemptParams
    {
        public string mode { get; set; } = "safe-point";
        public System.Collections.Generic.List<string> waitTypes { get; set; } =
            new() { "harvest", "harvestcrop", "mine", "place", "break", "craft" };
    }
}
