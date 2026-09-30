using System;
using System.Linq;
using System.Reflection;
using Vintagestory.API.Common;
using Vintagestory.API.MathTools;
using Vintagestory.API.Server;
using Vintagestory.Essentials;
using Vintagestory.GameContent;
using Polis.Core;
using Polis.Helpers;

namespace Polis.Actions.Workstations;

/// <summary>
/// Action: Smith a work item on an anvil using direct voxel manipulation.
///
/// This bypasses the normal hammer hit mechanics and directly sets voxels to match
/// the recipe pattern. This is necessary because helve hammer only works for
/// iron bloom and literal "plate"/"blistersteel" recipes - all other recipes
/// (tools, weapons, etc.) require this direct voxel approach.
///
/// Algorithm:
/// 1. Each tick, compare current voxels with recipe voxels
/// 2. For voxels where current=metal but recipe=empty: remove (set to 0)
/// 3. For voxels where current=empty but recipe=metal: this shouldn't happen
///    (we can only remove excess metal, not add)
/// 4. Call RegenMeshAndSelectionBoxes() after changes
/// 5. Play sound and spawn particles for hot metal
/// 6. When voxels match recipe, call CheckIfFinished to complete
/// </summary>
class PolisAnvilSmithAction : EntityActionBase
{
    // === Constructor Parameters ===
    readonly BlockPos targetPos;
    readonly int targetRecipeId;
    readonly IServerPlayer player;
    readonly int voxelsPerTick;
    readonly float maxRange;
    readonly Action<string> debugLog;
    readonly Action<bool, string> onResult;

    // === Runtime State ===
    BlockEntityAnvil anvilEntity;
    SmithingRecipe recipe;
    float tickAccumulator;
    bool done;
    bool validated;
    int totalVoxelsModified;
    int ticksSinceLastProgress;
    PolisAnimationHelpers.LoopingAnimationState animState;

    // === Constants ===
    const float DEFAULT_MAX_RANGE = 4.5f;
    const float TICK_INTERVAL = 0.1f; // Process every 100ms
    const int DEFAULT_VOXELS_PER_TICK = 4;
    const int MAX_STALL_TICKS = 30; // ~3 seconds at 100ms tick interval

    public override string Type => "polis-anvilsmith";

    public PolisAnvilSmithAction(
        BlockPos targetPos,
        int targetRecipeId,
        IServerPlayer player,
        int voxelsPerTick = DEFAULT_VOXELS_PER_TICK,
        float maxRange = DEFAULT_MAX_RANGE,
        Action<string> debugLog = null,
        Action<bool, string> onResult = null
    )
    {
        this.targetPos = targetPos;
        this.targetRecipeId = targetRecipeId;
        this.player = player;
        this.voxelsPerTick = voxelsPerTick;
        this.maxRange = maxRange;
        this.debugLog = debugLog;
        this.onResult = onResult;
    }

    public override void Start(EntityActivity entityActivity)
    {
        done = false;
        totalVoxelsModified = 0;
        tickAccumulator = 0f;
        var world = vas.Entity.Api.World;

        // --- Range Check ---
        var center = new Vec3d(targetPos.X + 0.5, targetPos.Y + 0.5, targetPos.Z + 0.5);
        double dist = vas.Entity.ServerPos.XYZ.DistanceTo(center);
        if (dist > maxRange)
        {
            debugLog?.Invoke($"[anvil-smith] failed: out of range dist={dist:F1} > {maxRange}");
            ReportResult(false, $"out of range: {dist:F1} > {maxRange}");
            ExecutionHasFailed = true;
            done = true;
            return;
        }

        // --- Player Validation ---
        if (player == null)
        {
            debugLog?.Invoke("[anvil-smith] failed: missing player");
            ReportResult(false, "missing player");
            ExecutionHasFailed = true;
            done = true;
            return;
        }

        // --- Block Validation ---
        var block = world.BlockAccessor.GetBlock(targetPos);
        if (block == null || !(block is BlockAnvil))
        {
            debugLog?.Invoke($"[anvil-smith] failed: block {block?.Code} is not an anvil");
            ReportResult(false, $"block {block?.Code} is not an anvil");
            ExecutionHasFailed = true;
            done = true;
            return;
        }

        // --- Get BlockEntityAnvil ---
        anvilEntity = world.BlockAccessor.GetBlockEntity(targetPos) as BlockEntityAnvil;
        if (anvilEntity == null)
        {
            debugLog?.Invoke("[anvil-smith] failed: no anvil block entity");
            ReportResult(false, "no anvil block entity");
            ExecutionHasFailed = true;
            done = true;
            return;
        }

        // --- Check work item ---
        if (anvilEntity.WorkItemStack == null)
        {
            debugLog?.Invoke("[anvil-smith] failed: no work item on anvil");
            ReportResult(false, "no work item on anvil");
            ExecutionHasFailed = true;
            done = true;
            return;
        }

        // --- Check temperature ---
        float temp = anvilEntity.WorkItemStack.Collectible.GetTemperature(world, anvilEntity.WorkItemStack);
        if (temp <= 20)
        {
            debugLog?.Invoke($"[anvil-smith] failed: work item too cold ({temp:F0}C)");
            ReportResult(false, $"work item too cold ({temp:F0}C)");
            ExecutionHasFailed = true;
            done = true;
            return;
        }

        // --- Set recipe on anvil ---
        recipe = world.Api.GetSmithingRecipes().FirstOrDefault(r => r.RecipeId == targetRecipeId);
        if (recipe == null)
        {
            debugLog?.Invoke($"[anvil-smith] failed: recipe {targetRecipeId} not found");
            ReportResult(false, $"recipe {targetRecipeId} not found");
            ExecutionHasFailed = true;
            done = true;
            return;
        }

        anvilEntity.SelectedRecipeId = targetRecipeId;

        // Pre-validate: warn if recipe requires metal where work item has none
        bool[,,] preCheckVoxels = GetRecipeVoxels();
        if (preCheckVoxels != null)
        {
            int ymax = Math.Min(6, recipe.QuantityLayers);
            int missingMetal = 0;
            for (int vy = 0; vy < ymax; vy++)
                for (int vx = 0; vx < 16; vx++)
                    for (int vz = 0; vz < 16; vz++)
                        if (preCheckVoxels[vx, vy, vz] && anvilEntity.Voxels[vx, vy, vz] == 0)
                            missingMetal++;
            if (missingMetal > 0)
            {
                debugLog?.Invoke($"[anvil-smith] warning: {missingMetal} recipe voxels have no metal — recipe may not complete");
            }
        }

        // Start looping hit animation
        animState = new PolisAnimationHelpers.LoopingAnimationState("hit", animSpeed: 1.5f, minRetriggerInterval: 0.4f);
        PolisAnimationHelpers.StartLoopingAnimation(vas.Entity, animState, debugLog);

        validated = true;
        debugLog?.Invoke($"[anvil-smith] started: smithing {recipe.Output.ResolvedItemstack.Collectible.Code} at {targetPos}");
    }

    public override void OnTick(float dt)
    {
        if (!validated || done) return;

        // Update looping animation
        PolisAnimationHelpers.UpdateLoopingAnimation(vas.Entity, animState, dt, debugLog);

        tickAccumulator += dt;
        if (tickAccumulator < TICK_INTERVAL) return;
        tickAccumulator = 0f;

        var world = vas.Entity.Api.World;

        // --- Refresh block entity reference ---
        anvilEntity = world.BlockAccessor.GetBlockEntity(targetPos) as BlockEntityAnvil;
        if (anvilEntity == null || anvilEntity.WorkItemStack == null)
        {
            PolisAnimationHelpers.StopLoopingAnimation(vas.Entity, animState, debugLog);
            debugLog?.Invoke("[anvil-smith] anvil or work item gone");
            ReportResult(true, $"completed (anvil state changed), modified {totalVoxelsModified} voxels");
            done = true;
            return;
        }

        // --- Check temperature (item may cool mid-smith) ---
        float currentTemp = anvilEntity.WorkItemStack.Collectible.GetTemperature(world, anvilEntity.WorkItemStack);
        if (currentTemp <= 20)
        {
            PolisAnimationHelpers.StopLoopingAnimation(vas.Entity, animState, debugLog);
            debugLog?.Invoke($"[anvil-smith] work item cooled to {currentTemp:F0}°C, stopping");
            ReportResult(false, $"work item cooled ({currentTemp:F0}°C), needs reheating");
            ExecutionHasFailed = true;
            done = true;
            return;
        }

        // --- Check if recipe still matches ---
        if (anvilEntity.SelectedRecipeId != targetRecipeId)
        {
            // Re-set it in case it was cleared
            anvilEntity.SelectedRecipeId = targetRecipeId;
        }

        // --- Get recipe voxels (handles rotation) ---
        bool[,,] recipeVoxels = GetRecipeVoxels();
        if (recipeVoxels == null)
        {
            PolisAnimationHelpers.StopLoopingAnimation(vas.Entity, animState, debugLog);
            debugLog?.Invoke("[anvil-smith] failed: could not get recipe voxels");
            ReportResult(false, "could not get recipe voxels");
            ExecutionHasFailed = true;
            done = true;
            return;
        }

        // --- Modify voxels to match recipe ---
        int voxelsModifiedThisTick = 0;
        int ymax = Math.Min(6, recipe.QuantityLayers);
        bool allMatch = true;

        for (int vy = 0; vy < ymax && voxelsModifiedThisTick < voxelsPerTick; vy++)
        {
            for (int vx = 0; vx < 16 && voxelsModifiedThisTick < voxelsPerTick; vx++)
            {
                for (int vz = 0; vz < 16 && voxelsModifiedThisTick < voxelsPerTick; vz++)
                {
                    byte currentVoxel = anvilEntity.Voxels[vx, vy, vz];
                    bool recipeMetal = recipeVoxels[vx, vy, vz];
                    byte desiredVoxel = (byte)(recipeMetal ? 1 : 0); // 1 = Metal, 0 = Empty

                    if (currentVoxel != desiredVoxel)
                    {
                        allMatch = false;
                        // We can only remove metal (set to 0), not add it
                        if (currentVoxel == 1 && !recipeMetal)
                        {
                            anvilEntity.Voxels[vx, vy, vz] = 0;
                            voxelsModifiedThisTick++;
                            totalVoxelsModified++;
                        }
                        // If currentVoxel is slag (2), also remove it
                        else if (currentVoxel == 2)
                        {
                            anvilEntity.Voxels[vx, vy, vz] = 0;
                            voxelsModifiedThisTick++;
                            totalVoxelsModified++;
                        }
                    }
                }
            }
        }

        // --- Track stall ---
        if (voxelsModifiedThisTick > 0)
        {
            ticksSinceLastProgress = 0;
        }
        else
        {
            ticksSinceLastProgress++;
        }

        // --- Regenerate mesh if we modified voxels ---
        if (voxelsModifiedThisTick > 0)
        {
            // Call private RegenMeshAndSelectionBoxes via reflection or mark dirty
            anvilEntity.MarkDirty(true);
            world.BlockAccessor.MarkBlockDirty(targetPos);

            // Play anvil hit sound
            float temp = anvilEntity.WorkItemStack.Collectible.GetTemperature(world, anvilEntity.WorkItemStack);
            bool isHot = temp > 800;
            world.PlaySoundAt(
                new AssetLocation(isHot ? "sounds/effect/anvilmergehit" : "sounds/effect/anvilhit"),
                targetPos.X + 0.5, targetPos.Y + 0.5, targetPos.Z + 0.5,
                null, true, 16f
            );

            // Spawn particles for hot metal
            if (isHot && world is IServerWorldAccessor sworld)
            {
                SpawnSmithingParticles(sworld, targetPos);
            }

            debugLog?.Invoke($"[anvil-smith] tick: modified {voxelsModifiedThisTick} voxels, total={totalVoxelsModified}");
        }

        // --- Stall detection ---
        if (ticksSinceLastProgress >= MAX_STALL_TICKS)
        {
            PolisAnimationHelpers.StopLoopingAnimation(vas.Entity, animState, debugLog);
            debugLog?.Invoke($"[anvil-smith] stalled: no progress for {MAX_STALL_TICKS} ticks, modified {totalVoxelsModified} voxels total");
            ReportResult(false, $"stalled: work item cannot match recipe (modified {totalVoxelsModified} voxels, then no further progress)");
            ExecutionHasFailed = true;
            done = true;
            return;
        }

        // --- Check if complete ---
        if (allMatch || CheckIfMatchesRecipe())
        {
            PolisAnimationHelpers.StopLoopingAnimation(vas.Entity, animState, debugLog);

            // Call CheckIfFinished to complete the recipe and give output
            anvilEntity.CheckIfFinished(player);

            debugLog?.Invoke($"[anvil-smith] complete: smithed {recipe.Output.ResolvedItemstack.Collectible.Code}, modified {totalVoxelsModified} voxels");
            ReportResult(true, $"smithed {recipe.Output.ResolvedItemstack.Collectible.Code}");
            done = true;
        }
    }

    bool[,,] GetRecipeVoxels()
    {
        // The recipeVoxels property handles rotation internally
        // We need to access it via reflection since it's a property on BlockEntityAnvil
        var prop = anvilEntity.GetType().GetProperty("recipeVoxels", BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
        if (prop != null)
        {
            return prop.GetValue(anvilEntity) as bool[,,];
        }

        // Fallback: use recipe voxels directly (without rotation)
        return recipe?.Voxels;
    }

    bool CheckIfMatchesRecipe()
    {
        if (recipe == null || anvilEntity == null) return false;

        bool[,,] recipeVoxels = GetRecipeVoxels();
        if (recipeVoxels == null) return false;

        int ymax = Math.Min(6, recipe.QuantityLayers);

        for (int x = 0; x < 16; x++)
        {
            for (int y = 0; y < ymax; y++)
            {
                for (int z = 0; z < 16; z++)
                {
                    byte desiredMat = (byte)(recipeVoxels[x, y, z] ? 1 : 0);
                    if (anvilEntity.Voxels[x, y, z] != desiredMat)
                    {
                        return false;
                    }
                }
            }
        }

        return true;
    }

    void SpawnSmithingParticles(IServerWorldAccessor world, BlockPos pos)
    {
        // Particle spawning deferred - BlockEntityAnvil handles its own particles
        // when the mesh is regenerated and the block is marked dirty
    }

    public override bool IsFinished() => done;

    public override void Cancel()
    {
        if (animState != null)
        {
            PolisAnimationHelpers.StopLoopingAnimation(vas.Entity, animState, debugLog);
        }
        done = true;
        base.Cancel();
    }

    public override IEntityAction Clone()
    {
        return new PolisAnvilSmithAction(targetPos, targetRecipeId, player, voxelsPerTick, maxRange, debugLog, onResult);
    }

    void ReportResult(bool ok, string msg)
    {
        onResult?.Invoke(ok, msg);
    }
}
