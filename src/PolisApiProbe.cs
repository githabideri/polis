using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text;
using Vintagestory.API.Common;
using Vintagestory.API.Server;

namespace Polis;

/// <summary>
/// Opt-in API probe (2026-10-04, POLIS_API_PROBE=1): dumps the
/// crafting/smelting API surface of the running game (reflection) to
/// /tmp/polis-api-probe.txt so new actions can be written against the
/// real game-version API instead of guesses. Off unless the env var is
/// set in the launch environment.
/// </summary>
public static class PolisApiProbe
{
    const string OutPath = "/tmp/polis-api-probe.txt";
    static readonly StringBuilder sb = new();
    static bool typesDumped;

    public static void DumpTypes()
    {
        if (typesDumped) return;
        typesDumped = true;
        sb.AppendLine("=== TYPES (reflection, game runtime) ===");
        var seen = new HashSet<string>();
        int shown = 0;
        foreach (var asm in AppDomain.CurrentDomain.GetAssemblies())
        {
            Type[] types;
            try { types = asm.GetTypes(); }
            catch (ReflectionTypeLoadException e)
            { types = e.Types.Where(t => t != null).ToArray(); }
            foreach (var t in types)
            {
                if (t == null || t.FullName == null) continue;
                if (seen.Contains(t.FullName)) continue;
                seen.Add(t.FullName);
                string n = t.Name;
                bool hit = n.Contains("Smelt") || n.Contains("Furnace")
                    || n.Contains("Workbench") || n.Contains("CraftingStation")
                    || n.Contains("Station") || n.Contains("Anvil")
                    || n.Contains("Quern") || n.Contains("Crucible")
                    || n.Contains("Bloomery") || n.Contains("DoSmelt")
                    || n == "EnumSmeltType" || n.Contains("Recipe");
                if (!hit) continue;
                if (++shown > 80) { sb.AppendLine("... (80-type cap)"); Write(); return; }
                DumpType(t);
            }
        }
        Write();
    }

    static void DumpType(Type t)
    {
        sb.AppendLine();
        sb.AppendLine("== " + t.FullName + "  [" + t.Assembly.GetName().Name + "]");
        if (t.BaseType != null) sb.AppendLine("   base: " + t.BaseType.FullName);
        foreach (var i in t.GetInterfaces())
            sb.AppendLine("   impl: " + i.FullName);
        if (t.IsEnum)
        {
            foreach (var v in Enum.GetNames(t))
                sb.AppendLine("   enum: " + v + " = " + (int)Enum.Parse(t, v));
            return;
        }
        var flags = BindingFlags.Public | BindingFlags.Instance
                    | BindingFlags.Static | BindingFlags.DeclaredOnly;
        foreach (var p in t.GetProperties(flags).Where(p => p.GetIndexParameters().Length == 0))
            sb.AppendLine("   prop: " + p.PropertyType.Name + " " + p.Name);
        foreach (var f in t.GetFields(flags))
            sb.AppendLine("   field: " + f.FieldType.Name + " " + f.Name);
        foreach (var m in t.GetMethods(flags).Where(m => !m.IsSpecialName
                    && m.Name != "get_" && m.Name != "set_"))
            sb.AppendLine("   method: " + m.ToString());
    }

    public static void DumpWorld(ICoreServerAPI api)
    {
        sb.AppendLine();
        sb.AppendLine("=== WORLD: recipe registries ===");
        try
        {
            var w = api.World;
            var m = w.GetType().GetMethod("GetRecipeRegistry",
                new[] { typeof(string) });
            if (m == null)
            {
                // interface method?
                m = typeof(IWorldAccessor).GetMethod("GetRecipeRegistry");
            }
            if (m == null)
            {
                sb.AppendLine("   (no GetRecipeRegistry found)");
                return;
            }
            sb.AppendLine("   GetRecipeRegistry return type: " + m.ReturnType.FullName);
            foreach (string name in new[] { "crafting", "smelting", "cooking", "alloy", "grid" })
            {
                object reg = null;
                try { reg = m.Invoke(w, new object[] { name }); }
                catch (Exception e) { sb.AppendLine("   " + name + ": invoke failed: " + e.InnerException?.Message); continue; }
                if (reg == null) { sb.AppendLine("   " + name + ": null"); continue; }
                sb.AppendLine("   registry '" + name + "' -> " + reg.GetType().FullName);
                // dump the registry type once
                bool fresh = !sb.ToString().Contains(reg.GetType().FullName + "  [registry]");
                if (fresh) DumpType(reg.GetType());
                // try to enumerate recipe ids
                var ids = TryGetIds(reg);
                if (ids != null)
                {
                    sb.AppendLine("   '" + name + "' recipe count: " + ids.Count);
                    sb.AppendLine("   sample: " + string.Join(", ", ids.Take(12)));
                }
            }
        }
        catch (Exception e)
        {
            sb.AppendLine("   registry dump failed: " + e);
        }
        // grid recipes: the 1.22 stationless crafting list
        sb.AppendLine();
        sb.AppendLine("=== WORLD: GridRecipes ===");
        try
        {
            var gr = api.World.GridRecipes;
            sb.AppendLine("   count: " + (gr == null ? "null" : gr.Count));
            if (gr != null)
            {
                int n = 0;
                foreach (var r in gr)
                {
                    if (n++ >= 40)
                    {
                        sb.AppendLine("   ... (40 shown of " + gr.Count + ")");
                        break;
                    }
                    string outc = "?";
                    try
                    {
                        var ro = r.RecipeOutput;
                        if (ro == null) outc = "null";
                        else
                        {
                            var p = ro.GetType().GetProperty("Code");
                            outc = p == null ? (ro.GetType().GetProperty("Name")?.GetValue(ro) as string ?? "?")
                                : (p.GetValue(ro) as string ?? "?");
                        }
                    }
                    catch { }
                    sb.AppendLine("   rec: id=" + r.RecipeId + " name=" + (r.Name?.Path ?? "?")
                        + " out=" + outc
                        + (r.Shapeless ? " [shapeless]" : " [" + r.IngredientPattern + "]")
                        + " in=" + IngredientSummary(r));
                }
            }
        }
        catch (Exception e)
        {
            sb.AppendLine("   GridRecipes failed: " + e.Message);
        }
        // can-smelt probe: the game's own per-item smelt logic
        sb.AppendLine();
        sb.AppendLine("=== WORLD: CanSmelt probe ===");
        foreach (string code in new[] { "stone", "granite", "iron-ore", "coal",
            "charcoal", "wood", "copper-ore", "tin-ore", "salt", "flint",
            "clay", "ore-iron", "ore-copper", "sugar", "sugarcane" })
        {
            try
            {
                var item = api.World.GetItem(new AssetLocation("survival:" + code));
                if (item == null) { sb.AppendLine("   " + code + ": (no item)"); continue; }
                var stack = new ItemStack(item);
                bool can = item.CanSmelt(api.World, null, stack, null);
                sb.AppendLine("   " + code + ": CanSmelt=" + can);
            }
            catch (Exception e)
            {
                sb.AppendLine("   " + code + ": err " + e.Message);
            }
        }
        Write();
    }

    static string IngredientSummary(IRecipeBase r)
    {
        try
        {
            var list = new List<string>();
            foreach (var i in r.RecipeIngredients)
            {
                if (i == null) continue;
                string c = "?";
                int q = -1;
                try { c = (string)i.GetType().GetProperty("Code").GetValue(i); } catch { }
                try { q = (int)i.GetType().GetProperty("Quantity").GetValue(i); } catch { }
                list.Add((c ?? "?") + "x" + q);
            }
            return string.Join(",", list);
        }
        catch { return "?"; }
    }

    static List<string> TryGetIds(object reg)
    {
        try
        {
            var t = reg.GetType();
            // common shapes: Items dict/Enumerable, ById, All
            foreach (var prop in t.GetProperties())
            {
                if (prop.GetIndexParameters().Length > 0) continue;
                object v;
                try { v = prop.GetValue(reg); } catch { continue; }
                if (v == null) continue;
                var vt = v.GetType();
                if (vt.IsGenericType && vt.GetGenericTypeDefinition() == typeof(Dictionary<,>)
                    || vt.GetInterfaces().Any(i => i.IsGenericType && i.GetGenericTypeDefinition() == typeof(IReadOnlyDictionary<,>))
                    || (vt.IsGenericType && vt.GetGenericTypeDefinition() == typeof(Dictionary<,>)))
                {
                    var md = vt.GetMethod("Keys") ?? vt.GetInterfaces()
                        .SelectMany(i => i.GetMethods()).FirstOrDefault(x => x.Name == "Keys");
                    if (md != null)
                    {
                        object keys = md.Invoke(v, null);
                        if (keys is System.Collections.IEnumerable en)
                        {
                            var list = new List<string>();
                            foreach (var k in en) list.Add(Convert.ToString(k));
                            if (list.Count > 0) return list;
                        }
                    }
                }
            }
            var e = t.GetMethod("GetRecipeIds") ?? t.GetMethod("Ids")
                ?? t.GetInterfaces().SelectMany(i => i.GetMethods())
                    .FirstOrDefault(x => x.Name is "GetRecipeIds" or "Ids");
            if (e != null)
            {
                object v = e.Invoke(reg, null);
                if (v is System.Collections.IEnumerable en)
                {
                    var list = new List<string>();
                    foreach (var k in en) list.Add(Convert.ToString(k));
                    return list;
                }
            }
        }
        catch { }
        return null;
    }

    static void Write()
    {
        try
        {
            File.WriteAllText(OutPath, sb.ToString());
            Console.WriteLine("[PolisApiProbe] wrote " + OutPath +
                " (" + sb.Length + " chars)");
        }
        catch (Exception e)
        {
            Console.WriteLine("[PolisApiProbe] write failed: " + e.Message);
        }
    }
}
