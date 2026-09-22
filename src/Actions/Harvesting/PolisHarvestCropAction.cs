using System;
using System.Collections.Generic;
using Vintagestory.API.Common;
using Vintagestory.API.Common.Entities;
using Vintagestory.API.MathTools;
using Vintagestory.API.Server;
using Vintagestory.Essentials;
using Vintagestory.GameContent;
using PolisBuilderNpc.Helpers;

namespace PolisBuilderNpc.Actions.Harvesting;

/// <summary>
/// Harvests mature crops planted on farmland blocks.
/// Unlike PolisHarvestBlockAction (for berry bushes/resin with BlockBehaviorHarvestable),
/// farmland crops are harvested via instant BreakBlock() when mature.
/// </summary>
class PolisHarvestCropAction : EntityActionBase
{
    // === Constructor Parameters ===
    readonly BlockPos targetPos;
    readonly IServerPlayer player;
    readonly float maxRange;
    readonly bool autoCollectDrops;
    readonly float collectRadius;
    readonly Action<string> debugLog;
    readonly Action<bool, string> onResult;

    // === Runtime State ===
    BlockPos farmlandPos;
    BlockPos cropPos;
    bool done;

    // === Runtime State (for delayed result) ===
    string harvestedCropCode;

    // === Delayed Autocollect ===
    bool awaitingCollection;
    float collectWaitTime;
    const float COLLECT_DELAY = 1.2f;

    // === Constants ===
    const float DEFAULT_MAX_RANGE = 4.5f;
    const float DEFAULT_COLLECT_RADIUS = 3f;

    public override string Type => "polis-harvestcrop";

    public PolisHarvestCropAction(
        BlockPos targetPos,
        IServerPlayer player,
        float maxRange = DEFAULT_MAX_RANGE,
        bool autoCollectDrops = false,
        float collectRadius = DEFAULT_COLLECT_RADIUS,
        Action<string> debugLog = null,
        Action<bool, string> onResult = null
    )
    {
        this.targetPos = targetPos;
        this.player = player;
        this.maxRange = maxRange;
        this.autoCollectDrops = autoCollectDrops;
        this.collectRadius = collectRadius;
        this.debugLog = debugLog;
        this.onResult = onResult;
    }

    public override void Start(EntityActivity entityActivity)
    {
        done = false;
        var world = vas.Entity.Api.World;

        // --- Range Check ---
        var center = new Vec3d(targetPos.X + 0.5, targetPos.Y + 0.5, targetPos.Z + 0.5);
        double dist = vas.Entity.ServerPos.XYZ.DistanceTo(center);
        if (dist > maxRange)
        {
            debugLog?.Invoke($"[harvestcrop] failed: out of range dist={dist:F1} > {maxRange}");
            ReportResult(false, $"out of range: {dist:F1} > {maxRange}");
            ExecutionHasFailed = true;
            done = true;
            return;
        }

        // --- Player Validation ---
        if (player == null)
        {
            debugLog?.Invoke("[harvestcrop] failed: missing player");
            ReportResult(false, "missing player");
            ExecutionHasFailed = true;
            done = true;
            return;
        }

        // --- Resolve Farmland and Crop Positions ---
        // Target could be the crop block (above farmland) or the farmland itself
        BlockEntityFarmland farmland = world.BlockAccessor.GetBlockEntity(targetPos) as BlockEntityFarmland;
        if (farmland != null)
        {
            // Target is farmland, crop is above
            farmlandPos = targetPos.Copy();
            cropPos = targetPos.UpCopy();
        }
        else
        {
            // Target might be the crop block, check below for farmland
            farmland = world.BlockAccessor.GetBlockEntity(targetPos.DownCopy()) as BlockEntityFarmland;
            if (farmland != null)
            {
                farmlandPos = targetPos.DownCopy();
                cropPos = targetPos.Copy();
            }
        }

        if (farmland == null)
        {
            debugLog?.Invoke("[harvestcrop] failed: no farmland found at or below target");
            ReportResult(false, "no farmland found at or below target");
            ExecutionHasFailed = true;
            done = true;
            return;
        }

        // --- Check for Crop ---
        Block cropBlock = world.BlockAccessor.GetBlock(cropPos);
        if (cropBlock == null || cropBlock.Id == 0 || cropBlock.CropProps == null)
        {
            debugLog?.Invoke("[harvestcrop] failed: no crop on this farmland");
            ReportResult(false, "no crop on this farmland");
            ExecutionHasFailed = true;
            done = true;
            return;
        }

        // --- Check Maturity via HasRipeCrop() ---
        if (!farmland.HasRipeCrop())
        {
            // Get current stage for informative message
            int currentStage = GetCropStage(cropBlock);
            int maxStages = cropBlock.CropProps.GrowthStages;
            debugLog?.Invoke($"[harvestcrop] failed: crop not mature: stage {currentStage}/{maxStages}");
            ReportResult(false, $"crop not mature: stage {currentStage}/{maxStages}");
            ExecutionHasFailed = true;
            done = true;
            return;
        }

        // --- Claims Check (POLIS_SKIP_CLAIMS bypass for the test world) ---
        bool skipClaims = Environment.GetEnvironmentVariable("POLIS_SKIP_CLAIMS") == "1";
        if (!skipClaims
            && world.Claims != null
            && world.Claims.TestAccess(player, cropPos, EnumBlockAccessFlags.BuildOrBreak)
                != EnumWorldAccessResponse.Granted)
        {
            debugLog?.Invoke($"[harvestcrop] failed: no permission to break block (claims)");
            ReportResult(false, "no permission to break block (claims)");
            ExecutionHasFailed = true;
            done = true;
            return;
        }

        // --- Execute Harvest (break as the bot) ---
        // 1.22: BreakBlock() only has a player overload and its loot routes
        // to the player's inventory manager. Break the crop directly and
        // route GetDrops() into the bot's cargo (overflow -> ground).
        harvestedCropCode = cropBlock.Code?.ToString() ?? "unknown";
        var drops = cropBlock.GetDrops(world, cropPos, null, 1.0f) ?? Array.Empty<ItemStack>();
        world.BlockAccessor.SetBlock(0, cropPos); // air
        var agent = vas.Entity as EntityAgent;
        int collected = 0;
        var overflow = new List<ItemStack>();
        foreach (var stack in drops)
        {
            if (agent != null
                && PolisInventoryHelpers.TryInsertIntoBotInventory(agent, stack, out _, out _, debugLog))
            {
                collected += stack.StackSize;
            }
            else
            {
                overflow.Add(stack);
                world.SpawnItemEntity(stack, cropPos.ToVec3d().AddCopy(0.5f, 0.2f, 0.5f), null);
            }
        }
        debugLog?.Invoke($"[harvestcrop] harvested: {harvestedCropCode}, collected {collected}, overflow {overflow.Count}");

        // --- Auto-collect Drops (with delay) ---
        if (autoCollectDrops)
        {
            awaitingCollection = true;
            collectWaitTime = 0f;
            debugLog?.Invoke("[harvestcrop] awaiting collection delay");
            return; // Don't mark done, use OnTick
        }

        ReportResult(true, $"harvested {harvestedCropCode}, collected {collected}");
        done = true;
    }

    public override void OnTick(float dt)
    {
        // Handle delayed autocollect
        if (awaitingCollection)
        {
            collectWaitTime += dt;
            if (collectWaitTime >= COLLECT_DELAY)
            {
                var world = vas.Entity.Api.World;
                CollectDrops(world);
                debugLog?.Invoke("[harvestcrop] collection complete");
                ReportResult(true, $"harvested {harvestedCropCode} with collection");
                done = true;
            }
            return;
        }
    }

    public override void Cancel()
    {
        ReportResult(false, "cancelled");
        done = true;
        base.Cancel();
    }

    public override bool IsFinished() => done;

    public override IEntityAction Clone()
    {
        return new PolisHarvestCropAction(targetPos, player, maxRange, autoCollectDrops, collectRadius, debugLog, onResult);
    }

    void ReportResult(bool ok, string msg)
    {
        onResult?.Invoke(ok, msg);
    }

    // === Helper Methods ===

    int GetCropStage(Block block)
    {
        // Crop stage is encoded in the last code part (e.g., "grain-wheat-3" -> 3)
        if (int.TryParse(block.LastCodePart(), out int stage))
        {
            return stage;
        }
        return 0;
    }

    void CollectDrops(IWorldAccessor world)
    {
        // Collect nearby EntityItems that spawned from the harvest
        var botPos = vas.Entity.ServerPos.XYZ;
        var entities = world.GetEntitiesAround(botPos, collectRadius, collectRadius, e => e is EntityItem);

        int collected = 0;
        var agent = vas.Entity as EntityAgent;
        if (agent == null) return;

        foreach (var entity in entities)
        {
            if (entity is EntityItem itemEntity && itemEntity.Itemstack != null)
            {
                var stack = itemEntity.Itemstack;
                int originalSize = stack.StackSize;

                if (PolisInventoryHelpers.TryInsertIntoBotInventory(agent, stack, out int pickedUp, out string _, debugLog))
                {
                    if (pickedUp >= originalSize)
                    {
                        // Fully collected
                        itemEntity.Die(EnumDespawnReason.PickedUp, null);
                    }
                    else
                    {
                        // Partial pickup - update remaining
                        itemEntity.Itemstack.StackSize = originalSize - pickedUp;
                        itemEntity.WatchedAttributes.MarkPathDirty("itemstack");
                    }
                    collected++;
                }
            }
        }

        if (collected > 0)
        {
            debugLog?.Invoke($"[harvestcrop] collected {collected} item(s)");
        }
    }
}
