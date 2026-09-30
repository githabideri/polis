using System;
using System.Linq;
using System.Reflection;
using Vintagestory.API.Common;
using Vintagestory.API.Common.Entities;
using Vintagestory.API.MathTools;
using Vintagestory.API.Server;
using Vintagestory.Essentials;
using Vintagestory.GameContent;
using Polis.Helpers;

namespace Polis.Actions.Workstations;

/// <summary>
/// Action to form clay into a recipe shape. Places voxels progressively with animation.
/// Bot must have clay in inventory to provide material. The action places a clayform block
/// if one doesn't exist, then adds voxels according to the recipe pattern over time.
///
/// Key timing feature: Uses elapsed time tracking to throttle voxel placement,
/// ensuring visible progressive animation rather than instant completion.
/// </summary>
class PolisClayFormAction : EntityActionBase
{
    // === Constructor Parameters ===
    readonly BlockPos targetPos;
    readonly IServerPlayer player;
    readonly string recipeName;
    readonly int voxelsPerTick;
    readonly float maxRange;
    readonly Action<string> debugLog;
    readonly Action<bool, string> onResult;

    // === Runtime State ===
    Block block;
    BlockEntityClayForm clayFormEntity;
    ClayFormingRecipe recipe;
    float elapsedTime;
    float lastVoxelTime;
    bool validated;
    bool done;
    string activeAnimation;
    int voxelsPlaced;
    int totalRecipeVoxels;
    int currentLayer;
    int currentX;
    int currentZ;
    bool[,,] recipeVoxels;

    // === Constants ===
    const float DEFAULT_MAX_RANGE = 4.5f;
    const int DEFAULT_VOXELS_PER_TICK = 4;
    const float TICK_INTERVAL = 0.1f; // 100ms between voxel placements
    const float SOUND_INTERVAL = 0.25f; // 250ms between sound effects

    public override string Type => "polis-clayform";

    public PolisClayFormAction(
        BlockPos targetPos,
        IServerPlayer player,
        string recipeName,
        int voxelsPerTick = DEFAULT_VOXELS_PER_TICK,
        float maxRange = DEFAULT_MAX_RANGE,
        Action<string> debugLog = null,
        Action<bool, string> onResult = null
    )
    {
        this.targetPos = targetPos;
        this.player = player;
        this.recipeName = recipeName;
        this.voxelsPerTick = Math.Max(1, voxelsPerTick);
        this.maxRange = maxRange;
        this.debugLog = debugLog;
        this.onResult = onResult;
    }

    public override void Start(EntityActivity entityActivity)
    {
        done = false;
        voxelsPlaced = 0;
        currentLayer = 0;
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
            debugLog?.Invoke($"[clayform] failed: out of range dist={dist:F1} > {maxRange}");
            ReportResult(false, $"out of range: {dist:F1} > {maxRange}");
            ExecutionHasFailed = true;
            done = true;
            return;
        }

        // --- Player Validation ---
        if (player == null)
        {
            debugLog?.Invoke("[clayform] failed: missing player");
            ReportResult(false, "missing player");
            ExecutionHasFailed = true;
            done = true;
            return;
        }

        // --- Find Recipe ---
        var recipes = world.Api.GetClayformingRecipes();
        if (recipes == null || recipes.Count == 0)
        {
            debugLog?.Invoke("[clayform] failed: no clay forming recipes found");
            ReportResult(false, "no clay forming recipes found");
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
            debugLog?.Invoke($"[clayform] failed: recipe '{recipeName}' not found");
            ReportResult(false, $"recipe '{recipeName}' not found");
            ExecutionHasFailed = true;
            done = true;
            return;
        }

        recipeVoxels = recipe.Voxels;
        totalRecipeVoxels = recipeVoxels.Cast<bool>().Count(v => v);
        debugLog?.Invoke($"[clayform] found recipe '{recipe.Name}' with {totalRecipeVoxels} voxels");

        // --- Check for clay in bot inventory ---
        var claySlot = FindClaySlot(agent);
        if (claySlot == null || claySlot.Empty)
        {
            debugLog?.Invoke("[clayform] failed: bot has no clay in inventory");
            ReportResult(false, "bot has no clay in inventory");
            ExecutionHasFailed = true;
            done = true;
            return;
        }

        // --- Check/Create ClayForm Block ---
        block = world.BlockAccessor.GetBlock(targetPos);

        if (block is BlockClayForm)
        {
            // Block already exists
            clayFormEntity = world.BlockAccessor.GetBlockEntity(targetPos) as BlockEntityClayForm;
            if (clayFormEntity == null)
            {
                debugLog?.Invoke("[clayform] failed: clayform block has no entity");
                ReportResult(false, "clayform block has no entity");
                ExecutionHasFailed = true;
                done = true;
                return;
            }
        }
        else
        {
            // Need to place a new clayform block
            var clayformBlock = world.GetBlock(new AssetLocation("clayform"));
            if (clayformBlock == null)
            {
                debugLog?.Invoke("[clayform] failed: clayform block not found");
                ReportResult(false, "clayform block not found");
                ExecutionHasFailed = true;
                done = true;
                return;
            }

            // Check if target position is valid for placement
            Block existingBlock = world.BlockAccessor.GetBlock(targetPos);
            if (existingBlock != null && existingBlock.Id != 0 && !existingBlock.IsReplacableBy(clayformBlock))
            {
                debugLog?.Invoke($"[clayform] failed: cannot place at {targetPos}, blocked by {existingBlock.Code}");
                ReportResult(false, $"cannot place at {targetPos}, blocked by {existingBlock.Code}");
                ExecutionHasFailed = true;
                done = true;
                return;
            }

            // Place the block
            world.BlockAccessor.SetBlock(clayformBlock.BlockId, targetPos);
            clayFormEntity = world.BlockAccessor.GetBlockEntity(targetPos) as BlockEntityClayForm;

            if (clayFormEntity == null)
            {
                debugLog?.Invoke("[clayform] failed: could not create clayform entity");
                ReportResult(false, "could not create clayform entity");
                ExecutionHasFailed = true;
                done = true;
                return;
            }

            // Initialize with clay - consume one clay from bot inventory
            clayFormEntity.PutClay(claySlot);
            claySlot.MarkDirty();
        }

        // --- Set Recipe on ClayForm ---
        // Use reflection to set the selected recipe since there's no public setter
        try
        {
            var recipeField = typeof(BlockEntityClayForm).GetField("selectedRecipeId", BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public);
            if (recipeField != null)
            {
                recipeField.SetValue(clayFormEntity, recipe.RecipeId);
            }

            var selectedRecipeProp = typeof(BlockEntityClayForm).GetProperty("SelectedRecipe", BindingFlags.Instance | BindingFlags.Public);
            if (selectedRecipeProp != null && selectedRecipeProp.CanWrite)
            {
                selectedRecipeProp.SetValue(clayFormEntity, recipe);
            }
            else
            {
                // Try field directly
                var recipeFieldDirect = typeof(BlockEntityClayForm).GetField("selectedRecipe", BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public);
                if (recipeFieldDirect != null)
                {
                    recipeFieldDirect.SetValue(clayFormEntity, recipe);
                }
            }
        }
        catch (Exception ex)
        {
            debugLog?.Invoke($"[clayform] warning: could not set recipe via reflection: {ex.Message}");
        }

        validated = true;

        // Start forming animation
        StartFormAnimation();

        debugLog?.Invoke($"[clayform] started: forming {recipe.Name} at {targetPos}, speed={voxelsPerTick} voxels/tick");
        ReportResult(true, $"forming started: {recipe.Name}");
    }

    ItemSlot FindClaySlot(EntityAgent agent)
    {
        if (agent == null) return null;

        // Check hands first
        if (agent.RightHandItemSlot?.Itemstack?.Collectible?.Code?.Path?.StartsWith("clay-") == true)
        {
            return agent.RightHandItemSlot;
        }
        if (agent.LeftHandItemSlot?.Itemstack?.Collectible?.Code?.Path?.StartsWith("clay-") == true)
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
                if (slot?.Itemstack?.Collectible?.Code?.Path?.StartsWith("clay-") == true)
                {
                    return slot;
                }
            }
        }

        return null;
    }

    void StartFormAnimation()
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

    void StopFormAnimation()
    {
        if (activeAnimation != null)
        {
            vas.Entity.AnimManager.StopAnimation(activeAnimation);
            activeAnimation = null;
        }
    }

    public override void OnTick(float dt)
    {
        if (!validated || done) return;

        // Restart animation if it finished but forming still in progress
        if (activeAnimation != null && !vas.Entity.AnimManager.IsAnimationActive(activeAnimation))
        {
            StartFormAnimation();
        }

        var world = vas.Entity.Api.World;

        // --- Check block still exists ---
        Block currentBlock = world.BlockAccessor.GetBlock(targetPos);
        if (!(currentBlock is BlockClayForm))
        {
            StopFormAnimation();
            debugLog?.Invoke("[clayform] block changed during forming");
            ReportResult(true, $"block changed during forming, placed {voxelsPlaced} voxel(s)");
            done = true;
            return;
        }

        // --- Refresh entity reference ---
        clayFormEntity = world.BlockAccessor.GetBlockEntity(targetPos) as BlockEntityClayForm;
        if (clayFormEntity == null)
        {
            StopFormAnimation();
            debugLog?.Invoke("[clayform] clayform entity gone");
            ReportResult(true, $"clayform entity gone, placed {voxelsPlaced} voxel(s)");
            done = true;
            return;
        }

        // --- Accumulate time ---
        elapsedTime += dt;

        // --- Time-based throttling: only place voxels at TICK_INTERVAL ---
        if (elapsedTime - lastVoxelTime < TICK_INTERVAL)
        {
            return; // Wait for next tick interval
        }
        lastVoxelTime = elapsedTime;

        // --- Place voxels for this tick ---
        int voxelsThisTick = 0;
        bool foundVoxel = true;

        while (voxelsThisTick < voxelsPerTick && foundVoxel && currentLayer < 16)
        {
            foundVoxel = false;

            // Find next voxel position that needs to be filled
            while (currentLayer < 16)
            {
                while (currentX < 16)
                {
                    while (currentZ < 16)
                    {
                        // Check if recipe has voxel here and clayform doesn't yet
                        if (recipeVoxels[currentX, currentLayer, currentZ] &&
                            !clayFormEntity.Voxels[currentX, currentLayer, currentZ])
                        {
                            // Place this voxel
                            clayFormEntity.Voxels[currentX, currentLayer, currentZ] = true;
                            voxelsPlaced++;
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

                if (foundVoxel) break;
                currentX = 0;
                currentZ = 0;
                currentLayer++;
            }
        }

        // --- Mark dirty to sync visuals ---
        if (voxelsThisTick > 0)
        {
            clayFormEntity.MarkDirty(true);

            // Play sound periodically
            if (elapsedTime - Math.Floor(elapsedTime / SOUND_INTERVAL) * SOUND_INTERVAL < dt * 2)
            {
                // Note: Sound playing would require the world's sound API
                // This is a simplified version - full implementation would call world.PlaySoundAt
            }
        }

        // --- Log progress ---
        if (voxelsThisTick > 0)
        {
            debugLog?.Invoke($"[clayform] progress: {voxelsPlaced}/{totalRecipeVoxels} voxels placed ({(float)voxelsPlaced / totalRecipeVoxels * 100:F0}%)");
        }

        // --- Check if complete ---
        if (currentLayer >= 16 || voxelsPlaced >= totalRecipeVoxels || !foundVoxel)
        {
            StopFormAnimation();

            // Call CheckIfFinished to trigger output
            try
            {
                clayFormEntity.CheckIfFinished(player, currentLayer > 0 ? currentLayer - 1 : 0);
            }
            catch (Exception ex)
            {
                debugLog?.Invoke($"[clayform] warning during CheckIfFinished: {ex.Message}");
            }

            debugLog?.Invoke($"[clayform] completed: placed {voxelsPlaced} voxel(s) in {elapsedTime:F2}s");
            ReportResult(true, $"completed: placed {voxelsPlaced} voxel(s) for {recipe.Name}");
            done = true;
        }
    }

    public override void Cancel()
    {
        StopFormAnimation();
        debugLog?.Invoke($"[clayform] cancelled at {elapsedTime:F2}s, placed {voxelsPlaced} voxel(s)");
        ReportResult(false, $"cancelled after placing {voxelsPlaced} voxel(s)");
        done = true;
        base.Cancel();
    }

    public override bool IsFinished() => done;

    public override IEntityAction Clone()
    {
        return new PolisClayFormAction(targetPos, player, recipeName, voxelsPerTick, maxRange, debugLog, onResult);
    }

    void ReportResult(bool ok, string msg)
    {
        onResult?.Invoke(ok, msg);
    }
}
