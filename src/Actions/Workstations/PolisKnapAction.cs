using System;
using System.Linq;
using System.Reflection;
using Vintagestory.API.Common;
using Vintagestory.API.Common.Entities;
using Vintagestory.API.Datastructures;
using Vintagestory.API.MathTools;
using Vintagestory.Essentials;
using Vintagestory.GameContent;
using Polis.Core;
using Polis.Helpers;

namespace Polis.Actions.Workstations;

/// <summary>
/// Action to knap flint/stone into tools. Removes voxels progressively with animation.
/// Bot must have knapping material (flint, stone, etc.) in inventory. The action works on
/// an existing knapping surface block, sets the recipe, then chips away voxels according
/// to the recipe pattern over time.
///
/// Key difference from clay forming: knapping REMOVES voxels (chips away material) rather
/// than adding them. The recipe pattern indicates which voxels should REMAIN.
/// </summary>
class PolisKnapAction : EntityActionBase
{
    // === Constructor Parameters ===
    readonly BlockPos targetPos;
    readonly string recipeName;
    readonly int voxelsPerTick;
    readonly float maxRange;
    readonly Action<string> debugLog;
    readonly Action<bool, string> onResult;

    // === Runtime State ===
    Block block;
    BlockEntityKnappingSurface knapEntity;
    KnappingRecipe recipe;
    float elapsedTime;
    float lastVoxelTime;
    bool validated;
    bool done;
    string activeAnimation;
    int voxelsRemoved;
    int totalVoxelsToRemove;
    int currentX;
    int currentZ;
    bool[,,] recipeVoxels;

    // === Constants ===
    const float DEFAULT_MAX_RANGE = 4.5f;
    const int DEFAULT_VOXELS_PER_TICK = 4;
    const float TICK_INTERVAL = 0.1f; // 100ms between voxel removals
    const float SOUND_INTERVAL = 0.25f; // 250ms between sound effects

    public override string Type => "polis-knap";

    public PolisKnapAction(
        BlockPos targetPos,
        string recipeName,
        int voxelsPerTick = DEFAULT_VOXELS_PER_TICK,
        float maxRange = DEFAULT_MAX_RANGE,
        Action<string> debugLog = null,
        Action<bool, string> onResult = null
    )
    {
        this.targetPos = targetPos;
        this.recipeName = recipeName;
        this.voxelsPerTick = Math.Max(1, voxelsPerTick);
        this.maxRange = maxRange;
        this.debugLog = debugLog;
        this.onResult = onResult;
    }

    public override void Start(EntityActivity entityActivity)
    {
        done = false;
        voxelsRemoved = 0;
        currentX = 0;
        currentZ = 0;
        elapsedTime = 0f;
        lastVoxelTime = 0f;
        var world = vas.Entity.Api.World;
        var agent = vas.Entity as EntityAgent;

        // --- Range Check ---
        var center = new Vec3d(targetPos.X + 0.5, targetPos.Y + 0.5, targetPos.Z + 0.5);
        double dist = vas.Entity.ServerPos.XYZ.DistanceTo(center);
        if (dist > maxRange)
        {
            debugLog?.Invoke($"[knap] failed: out of range dist={dist:F1} > {maxRange}");
            ReportResult(false, $"out of range: {dist:F1} > {maxRange}");
            ExecutionHasFailed = true;
            done = true;
            return;
        }

        // --- Find Recipe ---
        var recipes = world.Api.GetKnappingRecipes();
        if (recipes == null || recipes.Count == 0)
        {
            debugLog?.Invoke("[knap] failed: no knapping recipes found");
            ReportResult(false, "no knapping recipes found");
            ExecutionHasFailed = true;
            done = true;
            return;
        }

        // Find recipe by output code or name
        recipe = recipes.FirstOrDefault(r =>
            r.Output?.ResolvedItemstack?.Collectible?.Code?.Path == recipeName ||
            r.Output?.ResolvedItemstack?.Collectible?.Code?.ToString() == recipeName ||
            r.Name == recipeName);

        if (recipe == null)
        {
            debugLog?.Invoke($"[knap] failed: recipe '{recipeName}' not found");
            ReportResult(false, $"recipe '{recipeName}' not found");
            ExecutionHasFailed = true;
            done = true;
            return;
        }

        recipeVoxels = recipe.Voxels;

        // Count how many voxels need to be removed (those NOT in the recipe pattern)
        // Knapping starts with a full 16x16 grid and we chip away what's not needed
        int recipeVoxelCount = 0;
        for (int x = 0; x < 16; x++)
        {
            for (int z = 0; z < 16; z++)
            {
                if (recipeVoxels[x, 0, z])
                {
                    recipeVoxelCount++;
                }
            }
        }
        totalVoxelsToRemove = 256 - recipeVoxelCount; // 16x16 = 256 total

        debugLog?.Invoke($"[knap] found recipe '{recipe.Name}' - need to remove {totalVoxelsToRemove} voxels (keeping {recipeVoxelCount})");

        // --- Check block is a knapping surface ---
        block = world.BlockAccessor.GetBlock(targetPos);

        if (!(block is BlockKnappingSurface))
        {
            debugLog?.Invoke($"[knap] failed: block at {targetPos} is not a knapping surface (got {block?.Code?.Path ?? "null"})");
            ReportResult(false, $"block at position is not a knapping surface");
            ExecutionHasFailed = true;
            done = true;
            return;
        }

        knapEntity = world.BlockAccessor.GetBlockEntity(targetPos) as BlockEntityKnappingSurface;
        if (knapEntity == null)
        {
            debugLog?.Invoke("[knap] failed: knapping surface has no entity");
            ReportResult(false, "knapping surface has no entity");
            ExecutionHasFailed = true;
            done = true;
            return;
        }

        // Check if surface has material - if not, try to initialize from bot inventory
        if (knapEntity.BaseMaterial == null || knapEntity.BaseMaterial.StackSize <= 0)
        {
            // Try to find matching material in bot inventory
            var materialSlot = FindKnappingMaterialSlot(agent, recipe.Ingredient);
            if (materialSlot == null || materialSlot.Empty)
            {
                debugLog?.Invoke("[knap] failed: knapping surface has no material and bot has no matching material");
                ReportResult(false, "knapping surface has no material and bot has no matching material");
                ExecutionHasFailed = true;
                done = true;
                return;
            }

            // Initialize the surface with material from bot's inventory
            knapEntity.BaseMaterial = materialSlot.Itemstack.Clone();
            knapEntity.BaseMaterial.StackSize = 1;
            materialSlot.TakeOut(1);
            materialSlot.MarkDirty();

            // Initialize the 16x16 voxel grid to all true (full material)
            for (int x = 0; x < 16; x++)
            {
                for (int z = 0; z < 16; z++)
                {
                    knapEntity.Voxels[x, z] = true;
                }
            }

            knapEntity.MarkDirty(true);
            debugLog?.Invoke($"[knap] initialized surface with {knapEntity.BaseMaterial.Collectible?.Code?.Path ?? "material"}");
        }

        // Verify the material matches the recipe ingredient
        if (!recipe.Ingredient.SatisfiesAsIngredient(knapEntity.BaseMaterial))
        {
            var materialCode = knapEntity.BaseMaterial?.Collectible?.Code?.Path ?? "unknown";
            var ingredientCode = recipe.Ingredient?.Code?.Path ?? "unknown";
            debugLog?.Invoke($"[knap] failed: material '{materialCode}' doesn't match recipe ingredient '{ingredientCode}'");
            ReportResult(false, $"material doesn't match recipe ingredient");
            ExecutionHasFailed = true;
            done = true;
            return;
        }

        // --- Set Recipe on KnappingSurface ---
        // Use reflection to set the selected recipe since there's no public setter
        try
        {
            var recipeField = typeof(BlockEntityKnappingSurface).GetField("selectedRecipeId", BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public);
            if (recipeField != null)
            {
                recipeField.SetValue(knapEntity, recipe.RecipeId);
            }

            var selectedRecipeProp = typeof(BlockEntityKnappingSurface).GetProperty("SelectedRecipe", BindingFlags.Instance | BindingFlags.Public);
            if (selectedRecipeProp != null && selectedRecipeProp.CanWrite)
            {
                selectedRecipeProp.SetValue(knapEntity, recipe);
            }
        }
        catch (Exception ex)
        {
            debugLog?.Invoke($"[knap] warning: could not set recipe via reflection: {ex.Message}");
        }

        validated = true;

        // Start knapping animation
        StartKnapAnimation();

        debugLog?.Invoke($"[knap] started: knapping {recipe.Name} at {targetPos}, speed={voxelsPerTick} voxels/tick");
        ReportResult(true, $"knapping started: {recipe.Name}");
    }

    void StartKnapAnimation()
    {
        var animMeta = new AnimationMetaData
        {
            Code = "hit",
            Animation = "hit",
            AnimationSpeed = 1.0f,
            BlendMode = EnumAnimationBlendMode.Average
        };
        animMeta.EaseInSpeed = 1f;
        animMeta.EaseOutSpeed = 1f;
        vas.Entity.AnimManager.StartAnimation(animMeta.Init());
        activeAnimation = "hit";
    }

    void StopKnapAnimation()
    {
        if (activeAnimation != null)
        {
            vas.Entity.AnimManager.StopAnimation(activeAnimation);
            activeAnimation = null;
        }
    }

    ItemSlot FindKnappingMaterialSlot(EntityAgent agent, CraftingRecipeIngredient ingredient)
    {
        if (agent == null || ingredient == null) return null;

        // Check hands first
        if (agent.RightHandItemSlot?.Itemstack != null && ingredient.SatisfiesAsIngredient(agent.RightHandItemSlot.Itemstack))
        {
            return agent.RightHandItemSlot;
        }
        if (agent.LeftHandItemSlot?.Itemstack != null && ingredient.SatisfiesAsIngredient(agent.LeftHandItemSlot.Itemstack))
        {
            return agent.LeftHandItemSlot;
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
                    return slot;
                }
            }
        }

        return null;
    }

    /// <summary>
    /// Custom knapping completion that puts items directly into bot inventory.
    /// Replaces vanilla CheckIfFinished which gives items to the player.
    /// </summary>
    void CompleteKnapToBot(IWorldAccessor world)
    {
        if (recipe == null || knapEntity == null) return;

        var agent = vas.Entity as EntityAgent;
        if (agent == null)
        {
            debugLog?.Invoke("[knap] CompleteKnapToBot: no agent");
            return;
        }

        // Get output item from recipe
        ItemStack outstack = recipe.Output.ResolvedItemstack?.Clone();
        if (outstack == null)
        {
            debugLog?.Invoke("[knap] CompleteKnapToBot: no output itemstack");
            return;
        }

        // Fire the onitemknapped event (for mod compatibility)
        TreeAttribute tree = new TreeAttribute();
        tree["itemstack"] = new ItemstackAttribute(outstack);
        tree["byentityid"] = new LongAttribute(vas.Entity.EntityId);
        world.Api.Event.PushEvent("onitemknapped", tree);

        // Give items to bot inventory
        int totalCollected = 0;
        while (outstack.StackSize > 0)
        {
            ItemStack giveStack = outstack.Clone();
            giveStack.StackSize = Math.Min(outstack.StackSize, outstack.Collectible.MaxStackSize);
            outstack.StackSize -= giveStack.StackSize;

            int originalSize = giveStack.StackSize;
            if (PolisInventoryHelpers.TryInsertIntoBotInventory(agent, giveStack, out int pickedUp, out string _, debugLog))
            {
                totalCollected += pickedUp;
                debugLog?.Invoke($"[knap] gave {pickedUp}x {giveStack.Collectible?.Code} to bot");

                // If bot inventory couldn't hold everything, drop the remainder
                if (pickedUp < originalSize)
                {
                    giveStack.StackSize = originalSize - pickedUp;
                    world.SpawnItemEntity(giveStack, targetPos);
                    debugLog?.Invoke($"[knap] dropped overflow {giveStack.StackSize}x {giveStack.Collectible?.Code}");
                }
            }
            else
            {
                // Bot inventory full, drop on ground
                world.SpawnItemEntity(giveStack, targetPos);
                debugLog?.Invoke($"[knap] bot inventory full, dropped {giveStack.StackSize}x {giveStack.Collectible?.Code}");
            }
        }

        // Clear the knapping surface block
        world.BlockAccessor.SetBlock(0, targetPos);

        debugLog?.Invoke($"[knap] CompleteKnapToBot: collected {totalCollected} items");
    }

    public override void OnTick(float dt)
    {
        if (!validated || done) return;

        // Restart animation if it finished but knapping still in progress
        if (activeAnimation != null && !vas.Entity.AnimManager.IsAnimationActive(activeAnimation))
        {
            StartKnapAnimation();
        }

        var world = vas.Entity.Api.World;

        // --- Check block still exists ---
        Block currentBlock = world.BlockAccessor.GetBlock(targetPos);
        if (!(currentBlock is BlockKnappingSurface))
        {
            StopKnapAnimation();
            debugLog?.Invoke("[knap] block changed during knapping");
            ReportResult(true, $"block changed during knapping, removed {voxelsRemoved} voxel(s)");
            done = true;
            return;
        }

        // --- Refresh entity reference ---
        knapEntity = world.BlockAccessor.GetBlockEntity(targetPos) as BlockEntityKnappingSurface;
        if (knapEntity == null)
        {
            StopKnapAnimation();
            debugLog?.Invoke("[knap] knapping entity gone");
            ReportResult(true, $"knapping entity gone, removed {voxelsRemoved} voxel(s)");
            done = true;
            return;
        }

        // --- Accumulate time ---
        elapsedTime += dt;

        // --- Time-based throttling: only remove voxels at TICK_INTERVAL ---
        if (elapsedTime - lastVoxelTime < TICK_INTERVAL)
        {
            return; // Wait for next tick interval
        }
        lastVoxelTime = elapsedTime;

        // --- Remove voxels for this tick ---
        int voxelsThisTick = 0;
        bool foundVoxel = true;

        while (voxelsThisTick < voxelsPerTick && foundVoxel)
        {
            foundVoxel = false;

            // Find next voxel position that needs to be removed
            // (voxels that exist in the surface but are NOT in the recipe pattern)
            while (currentX < 16)
            {
                while (currentZ < 16)
                {
                    // Check if surface has a voxel here but recipe doesn't need it
                    if (knapEntity.Voxels[currentX, currentZ] && !recipeVoxels[currentX, 0, currentZ])
                    {
                        // Remove this voxel
                        knapEntity.Voxels[currentX, currentZ] = false;
                        voxelsRemoved++;
                        voxelsThisTick++;
                        foundVoxel = true;

                        // Move to next position
                        currentZ++;
                        break;
                    }
                    currentZ++;
                }

                if (foundVoxel) break;
                currentZ = 0;
                currentX++;
            }
        }

        // --- Mark dirty to sync visuals ---
        if (voxelsThisTick > 0)
        {
            // Call RegenMeshAndSelectionBoxes via reflection to update visuals
            try
            {
                var regenMethod = typeof(BlockEntityKnappingSurface).GetMethod("RegenMeshAndSelectionBoxes",
                    BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public);
                regenMethod?.Invoke(knapEntity, null);
            }
            catch { }

            knapEntity.MarkDirty(true);
        }

        // --- Log progress ---
        if (voxelsThisTick > 0)
        {
            debugLog?.Invoke($"[knap] progress: {voxelsRemoved}/{totalVoxelsToRemove} voxels removed ({(float)voxelsRemoved / Math.Max(1, totalVoxelsToRemove) * 100:F0}%)");
        }

        // --- Check if complete ---
        if (currentX >= 16 || voxelsRemoved >= totalVoxelsToRemove || !foundVoxel)
        {
            StopKnapAnimation();

            // Complete knapping and give output to bot (not player)
            CompleteKnapToBot(world);

            debugLog?.Invoke($"[knap] completed: removed {voxelsRemoved} voxel(s) in {elapsedTime:F2}s");
            ReportResult(true, $"completed: knapped {recipe.Name}");
            done = true;
        }
    }

    public override void Cancel()
    {
        StopKnapAnimation();
        debugLog?.Invoke($"[knap] cancelled at {elapsedTime:F2}s, removed {voxelsRemoved} voxel(s)");
        ReportResult(false, $"cancelled after removing {voxelsRemoved} voxel(s)");
        done = true;
        base.Cancel();
    }

    public override bool IsFinished() => done;

    public override IEntityAction Clone()
    {
        return new PolisKnapAction(targetPos, recipeName, voxelsPerTick, maxRange, debugLog, onResult);
    }

    void ReportResult(bool ok, string msg)
    {
        onResult?.Invoke(ok, msg);
    }
}
