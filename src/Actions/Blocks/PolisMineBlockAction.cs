using System;
using System.Collections.Generic;
using Vintagestory.API.Common;
using Vintagestory.API.Common.Entities;
using Vintagestory.API.Config;
using Vintagestory.API.MathTools;
using Vintagestory.API.Server;
using Vintagestory.Essentials;
using Vintagestory.GameContent;
using PolisBuilderNpc.Helpers;

namespace PolisBuilderNpc.Actions.Blocks;

/// <summary>
/// Action that mines a block over time with animation and tool requirements.
/// </summary>
class PolisMineBlockAction : EntityActionBase
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
    Block block;
    float resistance;
    float miningSpeed;
    float progress;
    ItemSlot toolSlot;
    bool validated;
    bool done;
    string activeAnimation;

    // === Autocollect Tracking ===
    int lastCollectTotal;
    int lastCollectPicked;
    List<string> lastCollectOverflow = new List<string>();

    // === Delayed Autocollect ===
    bool awaitingCollection;
    float collectWaitTime;
    const float COLLECT_DELAY = 1.2f;

    // === Constants ===
    const float DEFAULT_MAX_RANGE = 4.5f;
    const float DEFAULT_COLLECT_RADIUS = 3f;
    const float MIN_MINING_SPEED = 0.1f;

    public override string Type => "polis-mineblock";

    public PolisMineBlockAction(
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
        var agent = vas.Entity as EntityAgent;
        var world = vas.Entity.Api.World;

        // --- Range Check ---
        double dist = vas.Entity.ServerPos.DistanceTo(targetPos.ToVec3d().Add(0.5, 0.5, 0.5));
        if (dist > maxRange)
        {
            Fail($"Target too far: {dist:F1} > {maxRange}");
            return;
        }

        // --- Block Validation ---
        block = world.BlockAccessor.GetBlock(targetPos);
        if (block == null || block.Id == 0)
        {
            Fail("No block at target position");
            return;
        }

        resistance = block.Resistance;
        if (resistance <= 0)
        {
            // Instant break (air, water, etc.) - just break it
            world.BlockAccessor.BreakBlock(targetPos, player, 1.0f);
            debugLog?.Invoke($"[mine] instant break: {block.Code} (resistance=0)");
            if (autoCollectDrops)
            {
                awaitingCollection = true;
                collectWaitTime = 0f;
                validated = true;  // Enable OnTick processing
                return;
            }
            Succeed("instant break");
            return;
        }

        // --- Tool Validation ---
        var invbh = agent?.GetBehavior<EntityBehaviorSeraphInventory>();
        if (invbh == null)
        {
            Fail("Bot has no inventory behavior");
            return;
        }

        toolSlot = invbh.Inventory[15]; // Right hand
        if (toolSlot?.Itemstack?.Collectible == null)
        {
            // No tool - use bare hands (ToolTier = 0, slow speed)
            miningSpeed = 1.0f * GlobalConstants.ToolMiningSpeedModifier;
            int requiredTier = block.RequiredMiningTier;
            if (requiredTier > 0)
            {
                Fail($"Tool required: block needs tier {requiredTier}");
                return;
            }
        }
        else
        {
            var tool = toolSlot.Itemstack.Collectible;
            int toolTier = tool.ToolTier;
            int requiredTier = block.RequiredMiningTier;

            // --- Tier Check ---
            if (toolTier < requiredTier)
            {
                Fail($"Tool tier insufficient: {toolTier} < {requiredTier}");
                return;
            }

            // --- Mining Speed Calculation ---
            EnumBlockMaterial material = block.BlockMaterial;
            float baseMiningSpeed = 1.0f;

            if (tool.MiningSpeed != null && tool.MiningSpeed.TryGetValue(material, out float speedMult))
            {
                baseMiningSpeed = speedMult;
            }

            miningSpeed = baseMiningSpeed * GlobalConstants.ToolMiningSpeedModifier;
        }

        // Clamp to minimum
        if (miningSpeed < MIN_MINING_SPEED)
        {
            miningSpeed = MIN_MINING_SPEED;
        }

        progress = 0f;
        validated = true;

        // Start mining animation
        StartMiningAnimation();

        float estimatedTime = resistance / miningSpeed;
        debugLog?.Invoke($"[mine] start: {block.Code} resistance={resistance:F2} speed={miningSpeed:F2} est={estimatedTime:F2}s");
        ReportResult(true, "mining started");
    }

    public override void OnTick(float dt)
    {
        if (!validated || done) return;

        // Restart animation if it finished but mining still in progress
        if (activeAnimation != null && !vas.Entity.AnimManager.IsAnimationActive(activeAnimation))
        {
            StartMiningAnimation();
        }

        var world = vas.Entity.Api.World;

        // Handle delayed autocollect
        if (awaitingCollection)
        {
            collectWaitTime += dt;
            if (collectWaitTime >= COLLECT_DELAY)
            {
                CollectDrops(world);
                if (lastCollectOverflow.Count > 0)
                    Succeed($"mined, collected {lastCollectPicked}/{lastCollectTotal}, overflow: {string.Join(", ", lastCollectOverflow)}");
                else if (lastCollectPicked > 0)
                    Succeed($"mined, collected {lastCollectPicked}");
                else
                    Succeed("mined");
            }
            return;
        }

        // --- Check block still exists ---
        Block currentBlock = world.BlockAccessor.GetBlock(targetPos);
        if (currentBlock == null || currentBlock.Id == 0 || currentBlock.Id != block.Id)
        {
            // Block changed/removed by something else
            debugLog?.Invoke("[mine] block changed during mining");
            Succeed("block changed");
            return;
        }

        // --- Accumulate progress ---
        progress += miningSpeed * dt;

        // --- Check completion ---
        if (progress >= resistance)
        {
            // Break the block
            world.BlockAccessor.BreakBlock(targetPos, player, 1.0f);

            // Tool durability (TODO: implement in later step)
            // if (toolSlot?.Itemstack != null)
            // {
            //     toolSlot.Itemstack.Collectible.DamageItem(world, vas.Entity, toolSlot, 1);
            //     PolisInventoryHelpers.StoreSeraphInventory(vas.Entity as EntityAgent);
            // }

            float actualTime = progress / miningSpeed;
            debugLog?.Invoke($"[mine] complete: {block.Code} in {actualTime:F2}s");

            // Handle auto-collect with delay
            if (autoCollectDrops)
            {
                awaitingCollection = true;
                collectWaitTime = 0f;
                debugLog?.Invoke("[mine] awaiting collection delay");
                return; // Continue in OnTick
            }

            Succeed("mined");
            return;
        }
    }

    public override bool IsFinished() => done;

    public override IEntityAction Clone()
    {
        return new PolisMineBlockAction(targetPos, player, maxRange, autoCollectDrops, collectRadius, debugLog, onResult);
    }

    void StartMiningAnimation()
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

    void StopMiningAnimation()
    {
        if (activeAnimation != null)
        {
            vas.Entity.AnimManager.StopAnimation(activeAnimation);
            activeAnimation = null;
        }
    }

    void CollectDrops(IWorldAccessor world)
    {
        var botPos = vas.Entity.ServerPos.XYZ;
        var entities = world.GetEntitiesAround(botPos, collectRadius, collectRadius, e => e is EntityItem);

        int totalItems = 0;
        int pickedItems = 0;
        var overflow = new List<string>();

        var agent = vas.Entity as EntityAgent;
        if (agent == null) return;

        foreach (var entity in entities)
        {
            if (entity is EntityItem itemEntity && itemEntity.Itemstack != null)
            {
                var stack = itemEntity.Itemstack;
                int originalSize = stack.StackSize;
                string itemCode = stack.Collectible?.Code?.ToString() ?? "unknown";
                totalItems += originalSize;

                if (PolisInventoryHelpers.TryInsertIntoBotInventory(agent, stack, out int pickedUp, out string _, debugLog))
                {
                    pickedItems += pickedUp;

                    if (pickedUp >= originalSize)
                    {
                        // Fully collected
                        itemEntity.Die(EnumDespawnReason.PickedUp, null);
                    }
                    else
                    {
                        // Partial pickup - track overflow
                        int notPicked = originalSize - pickedUp;
                        overflow.Add($"{notPicked}x {itemCode}");
                        itemEntity.Itemstack.StackSize = notPicked;
                        itemEntity.WatchedAttributes.MarkPathDirty("itemstack");
                    }
                }
                else
                {
                    // Full overflow - nothing picked
                    overflow.Add($"{originalSize}x {itemCode}");
                }
            }
        }

        // Store for action result reporting
        lastCollectTotal = totalItems;
        lastCollectPicked = pickedItems;
        lastCollectOverflow = overflow;

        if (overflow.Count > 0)
            debugLog?.Invoke($"[mine] collected {pickedItems}/{totalItems}, overflow: {string.Join(", ", overflow)}");
        else if (pickedItems > 0)
            debugLog?.Invoke($"[mine] collected {pickedItems} item(s)");
    }

    void Fail(string reason)
    {
        StopMiningAnimation();
        debugLog?.Invoke($"[mine] failed: {reason}");
        ReportResult(false, reason);
        ExecutionHasFailed = true;
        done = true;
    }

    void Succeed(string msg)
    {
        StopMiningAnimation();
        ReportResult(true, msg);
        done = true;
    }

    void ReportResult(bool ok, string msg)
    {
        onResult?.Invoke(ok, msg);
    }
}
