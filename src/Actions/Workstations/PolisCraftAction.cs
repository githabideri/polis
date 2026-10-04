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
/// in the output code) are usable; shaped (non-shapeless) recipes are
/// reported as a limitation - the headless path has no grid geometry.
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
            Fail($"recipe '{recipe.Name}' is shaped (pattern {recipe.IngredientPattern}) - headless crafting supports shapeless recipes only");
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
