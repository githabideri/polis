using System;
using System.Collections.Generic;
using System.Linq;
using Vintagestory.API.Common;
using Vintagestory.API.Common.Entities;
using Vintagestory.API.MathTools;
using Vintagestory.Essentials;
using Vintagestory.GameContent;
using Polis.Helpers;

namespace Polis.Actions.Workstations;

/// <summary>
/// Headless grid crafting - 1.22.7 removed the workbench block (its
/// definition is enabled:false) and registers 12.9k stationless grid
/// recipes in world.GridRecipes. The player crafting GUI drives
/// GridRecipe.Matches + ConsumeInput; this action runs that exact
/// engine logic against the bot's cargo inventory, so what the game
/// would let a player craft, the bot can craft (and nothing else).
///
/// Instant action (like place/ignite): no movement, one tick.
/// The bot's cargo slots are the slot array handed to the game
/// (in-place consumption), then the resolved output is inserted back
/// into cargo and the inventory is persisted.
///
/// Only recipes whose output is fully resolvable (no open {placeholder}
/// in the output code) are usable. Shapeless recipes match bag-style
/// against the first 9 cargo slots; shaped (grid-pattern) recipes are
/// matched at their own grid dimensions against a grid built by
/// placing one cargo slot per pattern cell (hands first, then
/// backpack slots in order; one slot fills at most one cell; empty
/// cells stay empty), then run through the engine's Matches +
/// ConsumeInput - the engine does not consume tool ingredients, they
/// only lose durability.
/// </summary>
class PolisCraftAction : EntityActionBase
{
    readonly string outputCode;
    readonly IPlayer ownerPlayer;
    readonly Action<string> debugLog;
    readonly Action<bool, string> onResult;
    bool done;

    public override string Type => "polis-craft";

    public PolisCraftAction(string outputCode, IPlayer ownerPlayer, Action<string> debugLog = null, Action<bool, string> onResult = null)
    {
        this.outputCode = outputCode?.ToLowerInvariant();
        this.ownerPlayer = ownerPlayer;
        this.debugLog = debugLog;
        this.onResult = onResult;
    }

    public override void Start(EntityActivity entityActivity)
    {
        var agent = vas.Entity as EntityPolisBot;
        if (agent == null || agent.Cargo == null)
        {
            Fail("bot has no cargo inventory");
            return;
        }
        var world = vas.Entity.Api.World;

        // The GridRecipe engine's first parameter is an IPlayer; 1.22
        // EntityAgents do NOT implement it (playerCast=False finding),
        // so the bot's OWNER player is the engine's actor. The slots
        // passed below are the bot's own cargo - the player is only the
        // identity/tool reference, not the ingredient source.
        IPlayer player = ownerPlayer ?? (vas.Entity as IPlayer);
        if (player == null)
        {
            Fail("no IPlayer available (bot has no owner) - the GridRecipe engine needs one");
            return;
        }

        // --- 1. find a recipe producing the requested output ---
        GridRecipe recipe = null;
        int recipeCount = 0;
        foreach (var r in world.GridRecipes)
        {
            recipeCount++;
            if (r == null || r.RecipeOutput == null) continue;
            string outCode = OutputCode(r, world);
            if (string.IsNullOrEmpty(outCode)) continue;
            string norm = outCode.ToLowerInvariant();
            if (norm == outputCode
                || norm.EndsWith(":" + outputCode)
                || (r.Name != null && r.Name.Path != null
                    && r.Name.Path.Contains(outputCode)))
            {
                recipe = r;
                break;
            }
        }
        if (recipe == null)
        {
            Fail($"no grid recipe produces '{outputCode}' (searched {recipeCount})");
            return;
        }

        if (!recipe.Shapeless)
        {
            // Shaped path: build a width*height grid from cargo slots and
            // run the engine's own pattern matching. Output handling and
            // failure reporting are shared with the shapeless path.
            CraftShaped(recipe, player, world, agent);
            return;
        }

        // --- 2. the bot's cargo slots are the crafting grid (3x3 = 9) ---
        var slots = new List<ItemSlot>(agent.Cargo.Count);
        foreach (var s in agent.Cargo)
            if (s != null) slots.Add(s);
        slots = slots.Take(9).ToList();

        bool matched;
        try
        {
            matched = recipe.Matches(player, world, slots.ToArray(), 3);
        }
        catch (Exception e)
        {
            // diagnostic: include the top frames - the 1.22 GridRecipe
            // engine NPEs on several argument shapes and the message
            // alone ("Object reference not set...") does not say which.
            var st = e.StackTrace ?? "";
            var frames = st.Split(new[] { "\n   at " }, StringSplitOptions.None)
                .Take(3).Select(f => f.Trim().Split('\n')[0]);
            Fail($"Matches threw: {e.GetType().Name}: {e.Message} | inner={e.InnerException?.Message} | frames=[{string.Join("; ", frames)}] | playerCast={(agent as IPlayer) != null}");
            return;
        }
        if (!matched)
        {
            debugLog?.Invoke("[craft] inventory does not satisfy " + recipe.Name);
            Fail($"inventory does not satisfy recipe '{recipe.Name}' (need: {IngredientList(recipe)})");
            return;
        }

        // --- 3. consume inputs via the game's own logic ---
        try
        {
            recipe.ConsumeInput(player, slots.ToArray(), 3);
        }
        catch (Exception e)
        {
            Fail($"ConsumeInput threw: {e.Message}");
            return;
        }
        foreach (var s in slots) s?.MarkDirty();

        // --- 4. resolve and insert the output ---
        InsertOutput(recipe, world, agent);
    }

    bool CraftShaped(GridRecipe recipe, IPlayer player, IWorldAccessor world, EntityPolisBot agent)
    {
        // ResolvedIngredients is the per-cell ingredient array the
        // engine itself uses: length Width*Height, row-major, null =
        // empty pattern cell. On the server the original pattern
        // string is freed after recipe resolve, so the grid is driven
        // from this array instead.
        var cells = recipe.ResolvedIngredients;
        int w = Math.Max(1, recipe.Width);
        int h = Math.Max(1, recipe.Height);
        if (cells == null || cells.Length != w * h)
        {
            Fail($"shaped recipe '{recipe.Name}' has no usable resolved ingredient grid ({w}x{h})");
            return false;
        }

        // Grid slots must be real cargo slots: the engine's ConsumeInput
        // consumes the grid slots themselves, so the grid can only be
        // filled from actual inventory slots (a GUI player arranges
        // stacks the same way). A pattern cell may demand less than the
        // quantity of a satisfying stack (e.g. the crude door's three
        // stick cells from one 3-stack): split the stack first - TakeOut
        // the demanded quantity into an empty cargo slot. Exactly what
        // the engine does when a player splits a stack into the grid.
        var cargo = PolisInventoryHelpers.BotCargo(agent);
        var grid = new ItemSlot[w * h];
        int nslots = cargo?.Count ?? 0;
        var used = new bool[nslots];
        var missing = new List<string>();
        ICoreAPI api = vas.Entity.Api;
        for (int i = 0; i < grid.Length; i++)
        {
            var cell = cells[i];
            if (cell == null) continue; // empty pattern cell stays empty
            int need = Math.Max(1, cell.Quantity);
            int pick = -1;
            if (cell.IsTool)
            {
                // Tools are not consumed (Consume=false): the slot must
                // stay in place; only its durability decreases.
                for (int c = 0; c < nslots; c++)
                {
                    if (used[c]) continue;
                    var s = cargo[c];
                    if (s == null || s.Empty) continue;
                    if (!StackSatisfies(recipe, cell, s.Itemstack)) continue;
                    pick = c;
                    break;
                }
                if (pick < 0)
                {
                    missing.Add(CellLabel(i, w, cell, api));
                    continue;
                }
                used[pick] = true;
                grid[i] = cargo[pick];
                continue;
            }
            // 1) a slot holding exactly the demanded quantity
            for (int c = 0; c < nslots; c++)
            {
                if (used[c]) continue;
                var s = cargo[c];
                if (s == null || s.Empty) continue;
                if (s.Itemstack.StackSize != need) continue;
                if (!StackSatisfies(recipe, cell, s.Itemstack)) continue;
                pick = c;
                break;
            }
            // 2) otherwise split the demanded quantity off a larger
            //    satisfying stack into a free cargo slot
            if (pick < 0)
            {
                for (int c = 0; c < nslots; c++)
                {
                    if (used[c]) continue;
                    var s = cargo[c];
                    if (s == null || s.Empty) continue;
                    if (s.Itemstack.StackSize < need) continue;
                    if (!StackSatisfies(recipe, cell, s.Itemstack)) continue;
                    int free = -1;
                    for (int f = 0; f < nslots; f++)
                    {
                        if (used[f]) continue;
                        if (cargo[f] == null || !cargo[f].Empty) continue;
                        free = f;
                        break;
                    }
                    if (free < 0) continue;
                    var sub = s.TakeOut(need);
                    if (sub == null || sub.StackSize < need) continue;
                    cargo[free].Itemstack = sub;
                    cargo[free].MarkDirty();
                    s.MarkDirty();
                    pick = free;
                    break;
                }
            }
            if (pick < 0)
            {
                missing.Add(CellLabel(i, w, cell, api));
                continue;
            }
            used[pick] = true;
            grid[i] = cargo[pick];
        }
        if (missing.Count > 0)
        {
            Fail($"shaped recipe '{recipe.Name}' inventory missing: {string.Join(", ", missing)} (need: {IngredientList(recipe)})");
            return false;
        }

        bool matched;
        try
        {
            // gridWidth = the recipe's own width: the grid has exactly
            // Height rows, so the pattern can only match at the origin.
            matched = recipe.Matches(player, world, grid, w);
        }
        catch (Exception e)
        {
            var st = e.StackTrace ?? "";
            var frames = st.Split(new[] { "\n   at " }, StringSplitOptions.None)
                .Take(3).Select(f => f.Trim().Split('\n')[0]);
            Fail($"Matches threw: {e.GetType().Name}: {e.Message} | inner={e.InnerException?.Message} | frames=[{string.Join("; ", frames)}]");
            return false;
        }
        if (!matched)
        {
            debugLog?.Invoke("[craft] shaped grid does not match " + recipe.Name);
            Fail($"shaped grid does not match recipe '{recipe.Name}' (pattern {PatternString(recipe, cells)}) (need: {IngredientList(recipe)})");
            return false;
        }

        try
        {
            // the engine does not consume tool ingredients
            // (Consume=false); the tool slot stays in the grid and only
            // loses durability
            recipe.ConsumeInput(player, grid, w);
        }
        catch (Exception e)
        {
            Fail($"ConsumeInput threw: {e.Message}");
            return false;
        }
        foreach (var s in grid) s?.MarkDirty();

        InsertOutput(recipe, world, agent);
        return true;
    }

    // Same acceptance test the engine's per-cell matching applies:
    // SatisfiesAsIngredient (code/wildcard/tags + stack size) and the
    // collectible's crafting hook (rejects a tool whose remaining
    // durability is below the tool cost).
    static bool StackSatisfies(IRecipeBase recipe, CraftingRecipeIngredient cell, ItemStack stack)
    {
        if (stack == null || stack.Collectible == null) return false;
        if (!cell.SatisfiesAsIngredient(stack)) return false;
        try
        {
            return stack.Collectible.MatchesForCrafting(stack, recipe, cell);
        }
        catch
        {
            return false;
        }
    }

    // "A row1 col1 (any:tool-axe)" style label for failure messages
    static string CellLabel(int index, int width, CraftingRecipeIngredient cell, ICoreAPI api)
    {
        int row = index / width + 1;
        int col = index % width + 1;
        string id = string.IsNullOrEmpty(cell.Id) ? "?" : cell.Id;
        string code = cell.Code?.ToString();
        string what = !string.IsNullOrEmpty(code) && code != "*:*" ? code : TagNames(api, cell);
        return $"{id} row{row} col{col} ({what})";
    }

    // Tag names of a tags-only ingredient (code "*:*"), e.g.
    // "tool-axe" - resolved through the collectible tag registry.
    static string TagNames(ICoreAPI api, CraftingRecipeIngredient cell)
    {
        var parts = new List<string>();
        try
        {
            var registry = api?.CollectibleTagRegistry;
            var conds = cell.Tags.conditions;
            if (conds != null && registry != null)
            {
                foreach (var c in conds)
                {
                    var names = registry.SlowEnumerateTagNames(c.RequiredTags).ToList();
                    if (names.Count > 0) parts.Add(string.Join("|", names));
                }
            }
        }
        catch { }
        return parts.Count > 0 ? "any:" + string.Join(",", parts) : "any tag";
    }

    // The pattern string reconstructed from the resolved grid
    // (row-major, rows of Width chars joined by commas; '_' = empty
    // cell). The server frees the original string after resolve, so
    // this is the runtime view of the pattern.
    static string PatternString(GridRecipe recipe, CraftingRecipeIngredient?[] cells)
    {
        int w = Math.Max(1, recipe.Width);
        var sb = new System.Text.StringBuilder();
        for (int i = 0; i < cells.Length; i++)
        {
            if (i > 0 && i % w == 0) sb.Append(',');
            var cell = cells[i];
            sb.Append(cell != null && !string.IsNullOrEmpty(cell.Id) ? cell.Id : '_');
        }
        return sb.ToString();
    }

    // Resolve the recipe output and hand it back to the bot's cargo -
    // shared by the shapeless and shaped paths.
    void InsertOutput(GridRecipe recipe, IWorldAccessor world, EntityPolisBot agent)
    {
        try
        {
            recipe.RecipeOutput.Resolve(world, "polis-craft");
        }
        catch (Exception e)
        {
            Fail($"output resolve threw: {e.Message}");
            return;
        }
        var outStack = recipe.RecipeOutput.ResolvedItemStack;
        if (outStack == null || outStack.StackSize <= 0)
        {
            Fail($"recipe '{recipe.Name}' resolved no output stack");
            return;
        }
        int moved = 0;
        string reason = null;
        bool ok = PolisInventoryHelpers.TryInsertIntoBotInventory(agent, outStack, out moved, out reason);
        PolisInventoryHelpers.StoreSeraphInventory(agent);

        if (!ok || moved <= 0)
        {
            Fail($"consumed inputs but could not store output: {reason}");
            return;
        }

        string code = outStack.Collectible?.Code?.ToString() ?? outputCode;
        debugLog?.Invoke($"[craft] crafted {moved}x {code} via {recipe.Name}");
        onResult?.Invoke(true, $"crafted {moved}x {code} via {recipe.Name}");
        done = true;
    }

    static string OutputCode(GridRecipe r, IWorldAccessor world)
    {
        try
        {
            var rs = r.RecipeOutput.ResolvedItemStack;
            if (rs != null && rs.Collectible != null)
                return rs.Collectible.Code.ToString();
            r.RecipeOutput.Resolve(world, "probe");
            rs = r.RecipeOutput.ResolvedItemStack;
            if (rs != null && rs.Collectible != null)
                return rs.Collectible.Code.ToString();
            // fallback: the recipe name path minus the folder
            var n = r.Name;
            if (n != null && n.Path != null)
            {
                var idx = n.Path.LastIndexOf('/');
                if (idx >= 0) return n.Path.Substring(idx + 1);
            }
        }
        catch { }
        return null;
    }

    static string IngredientList(GridRecipe r)
    {
        var parts = new List<string>();
        foreach (var ing in r.ResolvedIngredients ?? Array.Empty<CraftingRecipeIngredient>())
        {
            if (ing == null) continue;
            string c = ing.Code?.ToString() ?? "?";
            parts.Add(c + "x" + ing.Quantity);
        }
        return string.Join(", ", parts.Count > 0 ? parts : (r.Ingredients != null ? new[] { r.IngredientPattern } : Array.Empty<string>()));
    }

    void Fail(string msg)
    {
        debugLog?.Invoke("[craft] failed: " + msg);
        onResult?.Invoke(false, msg);
        ExecutionHasFailed = true;
        done = true;
    }

    public override bool IsFinished() => done;

    public override IEntityAction Clone()
        => new PolisCraftAction(outputCode, ownerPlayer, debugLog, onResult);
}
