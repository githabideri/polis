using System;
using System.Reflection;
using Vintagestory.API.Common;
using Vintagestory.API.Common.Entities;
using Vintagestory.API.MathTools;
using Vintagestory.API.Server;
using Vintagestory.Essentials;
using Vintagestory.GameContent;
using Polis.Helpers;

namespace Polis.Actions.Harvesting;

/// <summary>
/// Action that harvests blocks with BlockBehaviorHarvestable (berry bushes, resin, etc.).
/// </summary>
class PolisHarvestBlockAction : EntityActionBase
{
    // === Constructor Parameters ===
    readonly BlockPos targetPos;
    readonly IServerPlayer player;
    readonly float maxRange;
    readonly bool autoCollectDrops;
    readonly float collectRadius;
    readonly bool validateRipe;
    readonly Action<string> debugLog;
    readonly Action<bool, string> onResult;

    // === Runtime State ===
    Block block;
    BlockBehaviorHarvestable harvestBehavior;
    float harvestTime;
    float elapsedTime;
    BlockSelection blockSel;
    bool interactionStarted;
    bool validated;
    bool done;
    string activeAnimation;

    // === Constants ===
    const float DEFAULT_MAX_RANGE = 4.5f;
    const float DEFAULT_COLLECT_RADIUS = 3f;
    const float DEFAULT_HARVEST_TIME = 1.0f;

    public override string Type => "polis-harvestblock";

    public PolisHarvestBlockAction(
        BlockPos targetPos,
        IServerPlayer player,
        float maxRange = DEFAULT_MAX_RANGE,
        bool autoCollectDrops = false,
        float collectRadius = DEFAULT_COLLECT_RADIUS,
        bool validateRipe = true,
        Action<string> debugLog = null,
        Action<bool, string> onResult = null
    )
    {
        this.targetPos = targetPos;
        this.player = player;
        this.maxRange = maxRange;
        this.autoCollectDrops = autoCollectDrops;
        this.collectRadius = collectRadius;
        this.validateRipe = validateRipe;
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
            debugLog?.Invoke($"[harvest] failed: out of range dist={dist:F1} > {maxRange}");
            ReportResult(false, $"out of range: {dist:F1} > {maxRange}");
            ExecutionHasFailed = true;
            done = true;
            return;
        }

        // --- Player Validation ---
        if (player == null)
        {
            debugLog?.Invoke("[harvest] failed: missing player");
            ReportResult(false, "missing player");
            ExecutionHasFailed = true;
            done = true;
            return;
        }

        // --- Block Validation ---
        block = world.BlockAccessor.GetBlock(targetPos);
        if (block == null || block.Id == 0)
        {
            debugLog?.Invoke("[harvest] failed: no block at target");
            ReportResult(false, "no block at target");
            ExecutionHasFailed = true;
            done = true;
            return;
        }

        // --- Check for Harvestable Behavior ---
        harvestBehavior = block.GetBehavior<BlockBehaviorHarvestable>();
        if (harvestBehavior == null)
        {
            debugLog?.Invoke($"[harvest] failed: block {block.Code} is not harvestable");
            ReportResult(false, $"block {block.Code} is not harvestable");
            ExecutionHasFailed = true;
            done = true;
            return;
        }

        // --- Validate Ripe State ---
        if (validateRipe && !IsRipe(block))
        {
            debugLog?.Invoke($"[harvest] failed: block {block.Code} is not ripe");
            ReportResult(false, $"block {block.Code} is not ripe");
            ExecutionHasFailed = true;
            done = true;
            return;
        }

        // --- Get Harvest Time via Reflection ---
        harvestTime = GetHarvestTime(harvestBehavior);
        if (harvestTime <= 0)
        {
            harvestTime = DEFAULT_HARVEST_TIME;
        }

        // --- Prepare Block Selection ---
        blockSel = new BlockSelection
        {
            Position = targetPos,
            Face = BlockFacing.UP,
            HitPosition = new Vec3d(0.5, 0.5, 0.5),
            Block = block
        };

        // --- Claims Check via OnBlockInteractStart ---
        bool canStart = block.OnBlockInteractStart(world, player, blockSel);
        if (!canStart)
        {
            debugLog?.Invoke("[harvest] failed: interaction blocked (claims or block state)");
            ReportResult(false, "interaction blocked (claims or block state)");
            ExecutionHasFailed = true;
            done = true;
            return;
        }

        interactionStarted = true;
        elapsedTime = 0f;
        validated = true;

        // Start harvest animation
        StartHarvestAnimation();

        debugLog?.Invoke($"[harvest] started: {block.Code} harvestTime={harvestTime:F2}s");
        ReportResult(true, "harvest started");
    }

    void StartHarvestAnimation()
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

    void StopHarvestAnimation()
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

        // Restart animation if it finished but harvest still in progress
        if (activeAnimation != null && !vas.Entity.AnimManager.IsAnimationActive(activeAnimation))
        {
            StartHarvestAnimation();
        }

        var world = vas.Entity.Api.World;

        // --- Check block still exists and is same type ---
        Block currentBlock = world.BlockAccessor.GetBlock(targetPos);
        if (currentBlock == null || currentBlock.Id != block.Id)
        {
            // Block changed (maybe already harvested by someone else)
            StopHarvestAnimation();
            debugLog?.Invoke("[harvest] block changed during harvest");
            ReportResult(true, "block changed during harvest");
            done = true;
            return;
        }

        // --- Accumulate time ---
        elapsedTime += dt;

        // --- Call interaction step (for animations/sounds) ---
        bool continueInteraction = block.OnBlockInteractStep(elapsedTime, world, player, blockSel);

        // --- Check completion (step returns false when elapsed >= harvestTime) ---
        if (!continueInteraction || elapsedTime >= harvestTime)
        {
            // Stop animation and complete the harvest
            StopHarvestAnimation();

            // When autocollect is enabled, bypass vanilla OnBlockInteractStop (which gives items to player)
            // and use our own method that puts items directly into bot inventory
            if (autoCollectDrops)
            {
                bool harvestSuccess = CompleteHarvestToBot(world);
                if (!harvestSuccess)
                {
                    // Fall back to vanilla behavior
                    block.OnBlockInteractStop(elapsedTime, world, player, blockSel);
                }
            }
            else
            {
                // Vanilla behavior: items go to player or drop if inventory full
                block.OnBlockInteractStop(elapsedTime, world, player, blockSel);
            }

            debugLog?.Invoke($"[harvest] completed: {block.Code} in {elapsedTime:F2}s");
            ReportResult(true, "harvested");
            done = true;
            return;
        }
    }

    public override void Cancel()
    {
        StopHarvestAnimation();
        if (interactionStarted && block != null && player != null)
        {
            var world = vas.Entity.Api.World;
            // Call stop with current elapsed time (incomplete harvest)
            block.OnBlockInteractStop(elapsedTime, world, player, blockSel);
            debugLog?.Invoke($"[harvest] cancelled at {elapsedTime:F2}s");
        }
        ReportResult(false, "cancelled");
        done = true;
        base.Cancel();
    }

    public override bool IsFinished() => done;

    public override IEntityAction Clone()
    {
        return new PolisHarvestBlockAction(targetPos, player, maxRange, autoCollectDrops, collectRadius, validateRipe, debugLog, onResult);
    }

    void ReportResult(bool ok, string msg)
    {
        onResult?.Invoke(ok, msg);
    }

    // === Helper Methods ===

    bool IsRipe(Block b)
    {
        // Check variant state for berry bushes and similar
        if (b.Variant != null && b.Variant.TryGetValue("state", out string state))
        {
            return state == "ripe";
        }

        // For farmland crops, check if crop is ripe
        // (Note: This is a simplified check - actual farmland harvest uses different mechanics)
        // Most harvestable blocks will use variant state

        return true; // Default: assume harvestable if behavior exists
    }

    float GetHarvestTime(BlockBehaviorHarvestable behavior)
    {
        // harvestTime is private, so we use reflection
        try
        {
            var field = typeof(BlockBehaviorHarvestable).GetField("harvestTime",
                BindingFlags.NonPublic | BindingFlags.Instance);
            if (field != null)
            {
                return (float)field.GetValue(behavior);
            }
        }
        catch (Exception ex)
        {
            debugLog?.Invoke($"[harvest] warning: failed to get harvestTime via reflection: {ex.Message}");
        }

        return DEFAULT_HARVEST_TIME;
    }

    /// <summary>
    /// Custom harvest completion that puts items directly into bot inventory.
    /// Replaces vanilla OnBlockInteractStop which gives items to the controlling player.
    /// </summary>
    bool CompleteHarvestToBot(IWorldAccessor world)
    {
        if (harvestBehavior == null) return false;

        var agent = vas.Entity as EntityAgent;
        if (agent == null)
        {
            debugLog?.Invoke("[harvest] CompleteHarvestToBot: no agent");
            return false;
        }

        // Get harvestedStacks (public field)
        var harvestedStacks = harvestBehavior.harvestedStacks;
        if (harvestedStacks == null || harvestedStacks.Length == 0)
        {
            debugLog?.Invoke("[harvest] CompleteHarvestToBot: no harvestedStacks");
            return false;
        }

        // Calculate drop rate (bots don't have forageDropRate stat, so use 1.0)
        float dropRate = 1f;

        // Give items to bot inventory
        int totalCollected = 0;
        foreach (var harvestedStack in harvestedStacks)
        {
            if (harvestedStack == null) continue;

            ItemStack stack = harvestedStack.GetNextItemStack(dropRate);
            if (stack == null) continue;

            int originalSize = stack.StackSize;
            if (PolisInventoryHelpers.TryInsertIntoBotInventory(agent, stack, out int pickedUp, out string _, debugLog))
            {
                totalCollected += pickedUp;
                debugLog?.Invoke($"[harvest] gave {pickedUp}x {stack.Collectible?.Code} to bot");

                // If bot inventory couldn't hold everything, drop the remainder
                if (pickedUp < originalSize)
                {
                    stack.StackSize = originalSize - pickedUp;
                    world.SpawnItemEntity(stack, blockSel.Position);
                    debugLog?.Invoke($"[harvest] dropped overflow {stack.StackSize}x {stack.Collectible?.Code}");
                }
            }
            else
            {
                // Bot inventory full, drop on ground
                world.SpawnItemEntity(stack, blockSel.Position);
                debugLog?.Invoke($"[harvest] bot inventory full, dropped {stack.StackSize}x {stack.Collectible?.Code}");
            }
        }

        // Get harvestedBlock via reflection (private field)
        Block harvestedBlock = GetHarvestedBlock(harvestBehavior, world);
        bool exchangeBlock = GetExchangeBlock(harvestBehavior);

        // Replace the block
        if (harvestedBlock != null)
        {
            if (!exchangeBlock)
            {
                world.BlockAccessor.SetBlock(harvestedBlock.BlockId, blockSel.Position);
            }
            else
            {
                world.BlockAccessor.ExchangeBlock(harvestedBlock.BlockId, blockSel.Position);
            }
            debugLog?.Invoke($"[harvest] replaced block with {harvestedBlock.Code}");
        }

        // Play harvest sound (public field)
        if (harvestBehavior.harvestingSound != null && player != null)
        {
            world.PlaySoundAt(harvestBehavior.harvestingSound, blockSel.Position, 0, player);
        }

        debugLog?.Invoke($"[harvest] CompleteHarvestToBot: collected {totalCollected} items");
        return true;
    }

    Block GetHarvestedBlock(BlockBehaviorHarvestable behavior, IWorldAccessor world)
    {
        try
        {
            // Try getting the resolved harvestedBlock field first
            var blockField = typeof(BlockBehaviorHarvestable).GetField("harvestedBlock",
                BindingFlags.NonPublic | BindingFlags.Instance);
            if (blockField != null)
            {
                var result = blockField.GetValue(behavior) as Block;
                if (result != null) return result;
            }

            // Fall back to harvestedBlockCode
            var codeField = typeof(BlockBehaviorHarvestable).GetField("harvestedBlockCode",
                BindingFlags.NonPublic | BindingFlags.Instance);
            if (codeField != null)
            {
                var code = codeField.GetValue(behavior) as AssetLocation;
                if (code != null)
                {
                    return world.GetBlock(code);
                }
            }
        }
        catch (Exception ex)
        {
            debugLog?.Invoke($"[harvest] warning: failed to get harvestedBlock via reflection: {ex.Message}");
        }
        return null;
    }

    bool GetExchangeBlock(BlockBehaviorHarvestable behavior)
    {
        try
        {
            var field = typeof(BlockBehaviorHarvestable).GetField("exchangeBlock",
                BindingFlags.NonPublic | BindingFlags.Instance);
            if (field != null)
            {
                return (bool)field.GetValue(behavior);
            }
        }
        catch (Exception ex)
        {
            debugLog?.Invoke($"[harvest] warning: failed to get exchangeBlock via reflection: {ex.Message}");
        }
        return false;
    }
}
