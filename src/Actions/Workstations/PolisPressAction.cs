using System;
using System.Reflection;
using Vintagestory.API.Common;
using Vintagestory.API.MathTools;
using Vintagestory.API.Server;
using Vintagestory.Essentials;
using Vintagestory.GameContent;

namespace Polis.Actions.Workstations;

/// <summary>
/// Timed action to press fruit in a fruit press.
/// Uses BlockFruitPress's OnReceivedClientPacket to trigger screw animation and juice extraction.
/// Pressing extracts juice from fruit mash into a bucket container.
/// </summary>
class PolisPressAction : EntityActionBase
{
    // === Constructor Parameters ===
    readonly BlockPos targetPos;
    readonly IServerPlayer player;
    readonly float maxRange;
    readonly float maxDuration; // Max pressing time in seconds (0 = unlimited)
    readonly bool autoUnscrew; // Whether to unscrew when complete
    readonly Action<string> debugLog;
    readonly Action<bool, string> onResult;

    // === Runtime State ===
    Block block;
    BlockEntity fruitPressEntity;
    float elapsedTime;
    bool interactionStarted;
    bool validated;
    bool done;
    string activeAnimation;
    double initialJuiceLitres;
    double juiceExtracted;

    // === Constants ===
    const float DEFAULT_MAX_RANGE = 4.5f;
    const float TICK_INTERVAL = 0.1f;
    // Packet IDs from BlockEntityFruitPress
    const int PacketIdScrewStart = 1002;
    const int PacketIdUnscrew = 1003;

    public override string Type => "polis-press";

    public PolisPressAction(
        BlockPos targetPos,
        IServerPlayer player,
        float maxRange = DEFAULT_MAX_RANGE,
        float maxDuration = 0,
        bool autoUnscrew = true,
        Action<string> debugLog = null,
        Action<bool, string> onResult = null
    )
    {
        this.targetPos = targetPos;
        this.player = player;
        this.maxRange = maxRange;
        this.maxDuration = maxDuration;
        this.autoUnscrew = autoUnscrew;
        this.debugLog = debugLog;
        this.onResult = onResult;
    }

    public override void Start(EntityActivity entityActivity)
    {
        done = false;
        juiceExtracted = 0;
        var world = vas.Entity.Api.World;

        // --- Range Check ---
        var center = new Vec3d(targetPos.X + 0.5, targetPos.Y + 0.5, targetPos.Z + 0.5);
        double dist = vas.Entity.ServerPos.XYZ.DistanceTo(center);
        if (dist > maxRange)
        {
            debugLog?.Invoke($"[press] failed: out of range dist={dist:F1} > {maxRange}");
            ReportResult(false, $"out of range: {dist:F1} > {maxRange}");
            ExecutionHasFailed = true;
            done = true;
            return;
        }

        // --- Player Validation ---
        if (player == null)
        {
            debugLog?.Invoke("[press] failed: missing player");
            ReportResult(false, "missing player");
            ExecutionHasFailed = true;
            done = true;
            return;
        }

        // --- Block Validation ---
        block = world.BlockAccessor.GetBlock(targetPos);
        if (block == null || block.Id == 0)
        {
            debugLog?.Invoke("[press] failed: no block at target");
            ReportResult(false, "no block at target");
            ExecutionHasFailed = true;
            done = true;
            return;
        }

        // --- Check for BlockFruitPress ---
        if (block.GetType().Name != "BlockFruitPress")
        {
            debugLog?.Invoke($"[press] failed: block {block.Code} is not a fruit press");
            ReportResult(false, $"block {block.Code} is not a fruit press");
            ExecutionHasFailed = true;
            done = true;
            return;
        }

        // --- Get BlockEntityFruitPress ---
        fruitPressEntity = world.BlockAccessor.GetBlockEntity(targetPos);
        if (fruitPressEntity == null || fruitPressEntity.GetType().Name != "BlockEntityFruitPress")
        {
            debugLog?.Invoke("[press] failed: no fruit press block entity");
            ReportResult(false, "no fruit press block entity");
            ExecutionHasFailed = true;
            done = true;
            return;
        }

        // --- Check if can screw (via reflection since we don't have direct access to the type) ---
        var canScrewProp = fruitPressEntity.GetType().GetProperty("CanScrew");
        if (canScrewProp != null)
        {
            bool canScrew = (bool)canScrewProp.GetValue(fruitPressEntity);
            if (!canScrew)
            {
                debugLog?.Invoke("[press] failed: fruit press cannot screw (already fully compressed or empty)");
                ReportResult(false, "fruit press cannot screw (already fully compressed or empty)");
                ExecutionHasFailed = true;
                done = true;
                return;
            }
        }

        // --- Check if has mash content ---
        var mashSlotProp = fruitPressEntity.GetType().GetProperty("MashSlot");
        if (mashSlotProp != null)
        {
            var mashSlot = mashSlotProp.GetValue(fruitPressEntity) as ItemSlot;
            if (mashSlot == null || mashSlot.Empty)
            {
                debugLog?.Invoke("[press] failed: fruit press has no mash to press");
                ReportResult(false, "fruit press has no mash to press");
                ExecutionHasFailed = true;
                done = true;
                return;
            }
        }

        // --- Record initial juice level ---
        initialJuiceLitres = GetCurrentJuiceLitres();

        // --- Start the screw animation by simulating client packet ---
        // Call OnReceivedClientPacket with PacketIdScrewStart
        fruitPressEntity.OnReceivedClientPacket(player, PacketIdScrewStart, null);

        interactionStarted = true;
        elapsedTime = 0f;
        validated = true;

        // Start press animation on bot
        StartPressAnimation();

        debugLog?.Invoke($"[press] started: fruit press at {targetPos}, maxDuration={maxDuration}, autoUnscrew={autoUnscrew}");
        ReportResult(true, "pressing started");
    }

    void StartPressAnimation()
    {
        var animMeta = new AnimationMetaData
        {
            Code = "hit",
            Animation = "hit",
            AnimationSpeed = 0.8f,
            BlendMode = EnumAnimationBlendMode.Average
        };
        animMeta.EaseInSpeed = 1f;
        animMeta.EaseOutSpeed = 1f;
        vas.Entity.AnimManager.StartAnimation(animMeta.Init());
        activeAnimation = "hit";
    }

    void StopPressAnimation()
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

        // Restart animation if it finished but pressing still in progress
        if (activeAnimation != null && !vas.Entity.AnimManager.IsAnimationActive(activeAnimation))
        {
            StartPressAnimation();
        }

        var world = vas.Entity.Api.World;

        // --- Check block still exists and is same type ---
        Block currentBlock = world.BlockAccessor.GetBlock(targetPos);
        if (currentBlock == null || currentBlock.Id != block.Id)
        {
            StopPressAnimation();
            debugLog?.Invoke("[press] block changed during pressing");
            ReportResult(true, $"block changed during pressing, extracted {juiceExtracted:F2}L juice");
            done = true;
            return;
        }

        // --- Refresh block entity reference ---
        fruitPressEntity = world.BlockAccessor.GetBlockEntity(targetPos);
        if (fruitPressEntity == null)
        {
            StopPressAnimation();
            debugLog?.Invoke("[press] fruit press entity gone");
            ReportResult(true, $"fruit press entity gone, extracted {juiceExtracted:F2}L juice");
            done = true;
            return;
        }

        // --- Accumulate time ---
        elapsedTime += dt;

        // --- Track juice extracted ---
        double currentJuice = GetCurrentJuiceLitres();
        double newExtracted = currentJuice - initialJuiceLitres;
        if (newExtracted > juiceExtracted)
        {
            juiceExtracted = newExtracted;
            debugLog?.Invoke($"[press] progress: {juiceExtracted:F2}L juice extracted");
        }

        // --- Check completion conditions ---
        bool shouldStop = false;
        string stopReason = "";

        // Check if animation is finished (fully compressed)
        var compressAnimFinishedProp = fruitPressEntity.GetType().GetProperty("CompressAnimFinished");
        bool compressFinished = false;
        if (compressAnimFinishedProp != null)
        {
            compressFinished = (bool)compressAnimFinishedProp.GetValue(fruitPressEntity);
        }

        // Check if compress animation is still active
        var compressAnimActiveProp = fruitPressEntity.GetType().GetProperty("CompressAnimActive");
        bool compressActive = false;
        if (compressAnimActiveProp != null)
        {
            compressActive = (bool)compressAnimActiveProp.GetValue(fruitPressEntity);
        }

        // Check juiceable litres left
        double juiceableLitresLeft = GetJuiceableLitresLeft();

        // Complete when:
        // 1. Animation finished and no more juice to extract
        // 2. Animation stopped (not active) and was started
        // 3. Duration limit reached
        if (compressFinished && juiceableLitresLeft <= 0)
        {
            shouldStop = true;
            stopReason = "pressing complete (fully compressed)";
        }
        else if (!compressActive && elapsedTime > 1.0f)
        {
            // Animation stopped but not via our control - might be blocked
            shouldStop = true;
            stopReason = "animation stopped";
        }

        // Check duration limit
        if (maxDuration > 0 && elapsedTime >= maxDuration)
        {
            shouldStop = true;
            stopReason = $"reached duration limit ({maxDuration:F1}s)";
        }

        if (shouldStop)
        {
            StopPressAnimation();

            // Optionally unscrew to release the press
            if (autoUnscrew && compressFinished)
            {
                fruitPressEntity.OnReceivedClientPacket(player, PacketIdUnscrew, null);
                debugLog?.Invoke("[press] auto-unscrewed fruit press");
            }

            debugLog?.Invoke($"[press] completed: {stopReason}, extracted {juiceExtracted:F2}L juice in {elapsedTime:F2}s");
            ReportResult(true, $"extracted {juiceExtracted:F2}L juice: {stopReason}");
            done = true;
        }
    }

    public override void Cancel()
    {
        StopPressAnimation();
        if (interactionStarted && fruitPressEntity != null && player != null)
        {
            // Send unscrew to stop the animation
            fruitPressEntity.OnReceivedClientPacket(player, PacketIdUnscrew, null);
            debugLog?.Invoke($"[press] cancelled at {elapsedTime:F2}s, extracted {juiceExtracted:F2}L juice");
        }
        ReportResult(false, $"cancelled after extracting {juiceExtracted:F2}L juice");
        done = true;
        base.Cancel();
    }

    public override bool IsFinished() => done;

    public override IEntityAction Clone()
    {
        return new PolisPressAction(targetPos, player, maxRange, maxDuration, autoUnscrew, debugLog, onResult);
    }

    void ReportResult(bool ok, string msg)
    {
        onResult?.Invoke(ok, msg);
    }

    double GetCurrentJuiceLitres()
    {
        if (fruitPressEntity == null) return 0;

        // Get bucket slot and check liquid content
        var bucketSlotProp = fruitPressEntity.GetType().GetProperty("BucketSlot");
        if (bucketSlotProp == null) return 0;

        var bucketSlot = bucketSlotProp.GetValue(fruitPressEntity) as ItemSlot;
        if (bucketSlot?.Itemstack == null) return 0;

        // Try to get the liquid container and its current litres
        var collectible = bucketSlot.Itemstack.Collectible;
        if (collectible == null) return 0;

        // Use reflection to call GetCurrentLitres if it's a BlockLiquidContainerBase
        var getCurrentLitresMethod = collectible.GetType().GetMethod("GetCurrentLitres", new Type[] { typeof(ItemStack) });
        if (getCurrentLitresMethod != null)
        {
            return (float)getCurrentLitresMethod.Invoke(collectible, new object[] { bucketSlot.Itemstack });
        }

        return 0;
    }

    double GetJuiceableLitresLeft()
    {
        if (fruitPressEntity == null) return 0;

        // Access the juiceableLitresLeft field via reflection
        var field = fruitPressEntity.GetType().GetField("juiceableLitresLeft",
            BindingFlags.Instance | BindingFlags.NonPublic);
        if (field != null)
        {
            return (double)field.GetValue(fruitPressEntity);
        }

        return 0;
    }
}
