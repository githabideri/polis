using System;
using System.IO;
using System.Text.Json;

namespace Polis.Core
{
    /// <summary>
    /// The polis interaction-rules layer (design: docs/design/food-hunger-skills-policies.md,
    /// section B). One evaluator for all domains:
    ///
    ///     PolisPolicyEngine.Instance.Evaluate("food", itemCode, foodCategory)
    ///         → (allow, reason)
    ///
    /// Rules come from the committed, versioned <mod>/assets/polis/polis-policies.json
    /// (hot-reloaded on file change, so a dev can iterate without a restart):
    ///
    ///   { "version": 1,
    ///     "domains": {
    ///       "food": { "default": "deny",
    ///                 "rules": [
    ///                   { "match": { "category": "Fruit" }, "allow": true, "priority": 10 },
    ///                   { "match": { "code": "game:bushmeat-cooked" }, "allow": true, "priority": 20 } ] },
    ///       "wear": { "default": "deny", "rules": [] },
    ///       "behavior": { "default": "allow", "rules": [] } } }
    ///
    /// Matching: `category` is a case-insensitive name of the item's
    /// FoodNutritionProperties.FoodCategory (Fruit / Vegetable / Protein /
    /// Grain / Dairy / Unknown / NoNutrition); `code` is the full item code
    /// with `*` wildcards (`game:raw-*`). Both set → both must match. The
    /// highest-priority matching rule wins (ties: the later rule); no match
    /// → the domain default. Denials carry a reason string — call sites log
    /// them (they are rejection data, not noise).
    ///
    /// The call sites (the `eat` action, later the planner filter and any
    /// use-check) only ever call Evaluate — a future per-pawn profile layer
    /// replaces the file schema and the internals, not the call sites.
    /// </summary>
    public class PolisPolicyEngine
    {
        public static PolisPolicyEngine Instance { get; } = new PolisPolicyEngine();

        string filePath;
        DateTime lastMtime = DateTime.MinValue;
        string lastError;
        DomainPolicyTable table;

        void Init(string path)
        {
            filePath = path;
        }

        /// <summary>
        /// Resolve the policy file from the deployed mod directory
        /// (<assembly dir>/assets/polis/polis-policies.json) and remember it.
        /// Returns the path, or null if the mod directory cannot be found.
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
        /// Evaluate an item/action against a policy domain.
        /// foodCategory: the item's FoodNutritionProperties.FoodCategory as a
        /// string (or null when the item has no nutrition props).
        /// Unknown domain → deny (safe default for a rules layer).
        /// </summary>
        public (bool Allow, string Reason) Evaluate(string domain, string code, string foodCategory)
        {
            ReloadIfChanged();

            if (table == null || !table.domains.TryGetValue(domain, out var d))
            {
                return (false, $"no policy domain '{domain}' (file: {lastError ?? "missing"})");
            }

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

        void ReloadIfChanged()
        {
            if (filePath == null) filePath = AutoInit();
            if (filePath == null || !File.Exists(filePath))
            {
                lastError = filePath == null ? "mod directory not found" : "file missing";
                return;
            }

            var mtime = File.GetLastWriteTimeUtc(filePath);
            if (mtime == lastMtime && table != null) return;

            try
            {
                string json = File.ReadAllText(filePath);
                table = JsonSerializer.Deserialize<DomainPolicyTable>(json,
                    new JsonSerializerOptions { PropertyNameCaseInsensitive = true });
                lastMtime = mtime;
                lastError = null;
            }
            catch (Exception ex)
            {
                lastError = $"parse error: {ex.Message}";
                // keep the last good table (or none) on a bad file
            }
        }
    }

    // --- File schema (mirrors assets/polis-policies.json) ---

    internal class DomainPolicyTable
    {
        public int version { get; set; }
        public System.Collections.Generic.Dictionary<string, DomainPolicy> domains { get; set; }
    }

    internal class DomainPolicy
    {
        public string @default { get; set; } = "deny";
        public bool defaultAllow => string.Equals(@default, "allow", StringComparison.OrdinalIgnoreCase);
        public System.Collections.Generic.List<PolicyRule> rules { get; set; } = new();
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
}
