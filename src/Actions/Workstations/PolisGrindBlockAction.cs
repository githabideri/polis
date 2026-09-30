using System;
using Vintagestory.API.Common;
using Vintagestory.API.MathTools;
using Vintagestory.API.Server;
using Vintagestory.Essentials;
using Vintagestory.GameContent;

namespace Polis.Actions.Workstations;

/// <summary>
/// Timed action to grind items in a quern.
/// Uses BlockQuern's OnBlockInteractStart/Step/Stop pattern with SelectionBoxIndex=1 to trigger grinding.
/// Grinding converts input items (grains) to output (flour) over time.
/// </summary>
class PolisGrindBlockAction : EntityActionBase
{
    // === Constructor Parameters ===
    readonly BlockPos targetPos;
    readonly IServerPlayer player;
    readonly float maxRange;
    readonly int maxCount; // Max items to grind (0 = unlimited)
    readonly float maxDuration; // Max grinding time in seconds (0 = unlimited)
    readonly Action<string> debugLog;
    readonly Action<bool, string> onResult;

    // === Runtime State ===
    Block block;
    BlockEntityQuern quernEntity;
    float elapsedTime;
    BlockSelection blockSel;
    bool interactionStarted;
    bool validated;
    bool done;
    string activeAnimation;
    int itemsGroundAtStart;
    int itemsGround;

    // === Constants ===
    const float DEFAULT_MAX_RANGE = 4.5f;
    const float GRIND_TIME_PER_ITEM = 4.0f; // Default quern grind time per item
    const float TICK_INTERVAL = 0.1f; // Match quern's 100ms tick

    public override string Type => "polis-grind";

    public PolisGrindBlockAction(
        BlockPos targetPos,
        IServerPlayer player,
        float maxRange = DEFAULT_MAX_RANGE,
        int maxCount = 0,
        float maxDuration = 0,
        Action<string> debugLog = null,
        Action<bool, string> onResult = null
    )
    {
        this.targetPos = targetPos;
        this.player = player;
        this.maxRange = maxRange;
        this.maxCount = maxCount;
        this.maxDuration = maxDuration;
        this.debugLog = debugLog;
        this.onResult = onResult;
    }

    public override void Start(EntityActivity entityActivity)
    {
        done = false;
        itemsGround = 0;
        var world = vas.Entity.Api.World;

        // --- Range Check ---
        var center = new Vec3d(targetPos.X + 0.5, targetPos.Y + 0.5, targetPos.Z + 0.5);
        double dist = vas.Entity.ServerPos.XYZ.DistanceTo(center);
        if (dist > maxRange)
        {
            debugLog?.Invoke($"[grind] failed: out of range dist={dist:F1} > {maxRange}");
            ReportResult(false, $"out of range: {dist:F1} > {maxRange}");
            ExecutionHasFailed = true;
            done = true;
            return;
        }

        // --- Player Validation ---
        if (player == null)
        {
            debugLog?.Invoke("[grind] failed: missing player");
            ReportResult(false, "missing player");
            ExecutionHasFailed = true;
            done = true;
            return;
        }

        // --- Block Validation ---
        block = world.BlockAccessor.GetBlock(targetPos);
        if (block == null || block.Id == 0)
        {
            debugLog?.Invoke("[grind] failed: no block at target");
            ReportResult(false, "no block at target");
            ExecutionHasFailed = true;
            done = true;
            return;
        }

        // --- Check for BlockQuern ---
        if (!(block is BlockQuern))
        {
            debugLog?.Invoke($"[grind] failed: block {block.Code} is not a quern");
            ReportResult(false, $"block {block.Code} is not a quern");
            ExecutionHasFailed = true;
            done = true;
            return;
        }

        // --- Get BlockEntityQuern ---
        quernEntity = world.BlockAccessor.GetBlockEntity(targetPos) as BlockEntityQuern;
        if (quernEntity == null)
        {
            debugLog?.Invoke("[grind] failed: no quern block entity");
            ReportResult(false, "no quern block entity");
            ExecutionHasFailed = true;
            done = true;
            return;
        }

        // --- Check CanGrind ---
        if (!quernEntity.CanGrind())
        {
            debugLog?.Invoke("[grind] failed: quern cannot grind (no input or not grindable)");
            ReportResult(false, "quern cannot grind (no input or not grindable)");
            ExecutionHasFailed = true;
            done = true;
            return;
        }

        // --- Prepare Block Selection with SelectionBoxIndex=1 for grinding ---
        blockSel = new BlockSelection
        {
            Position = targetPos,
            Face = BlockFacing.UP,
            HitPosition = new Vec3d(0.5, 1.0, 0.5), // Top of quern
            Block = block,
            SelectionBoxIndex = 1 // Index 1 = grinding action (not opening GUI)
        };

        // --- Start interaction ---
        bool canStart = block.OnBlockInteractStart(world, player, blockSel);
        if (!canStart)
        {
            debugLog?.Invoke("[grind] failed: interaction blocked (claims or block state)");
            ReportResult(false, "interaction blocked (claims or block state)");
            ExecutionHasFailed = true;
            done = true;
            return;
        }

        interactionStarted = true;
        elapsedTime = 0f;
        validated = true;
        itemsGroundAtStart = GetOutputSlotCount();

        // Start grind animation
        StartGrindAnimation();

        debugLog?.Invoke($"[grind] started: quern at {targetPos}, maxCount={maxCount}, maxDuration={maxDuration}");
        ReportResult(true, "grinding started");
    }

    void StartGrindAnimation()
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

    void StopGrindAnimation()
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

        // Restart animation if it finished but grinding still in progress
        if (activeAnimation != null && !vas.Entity.AnimManager.IsAnimationActive(activeAnimation))
        {
            StartGrindAnimation();
        }

        var world = vas.Entity.Api.World;

        // --- Check block still exists and is same type ---
        Block currentBlock = world.BlockAccessor.GetBlock(targetPos);
        if (currentBlock == null || currentBlock.Id != block.Id)
        {
            StopGrindAnimation();
            debugLog?.Invoke("[grind] block changed during grinding");
            ReportResult(true, $"block changed during grinding, ground {itemsGround} item(s)");
            done = true;
            return;
        }

        // --- Refresh quern entity reference ---
        quernEntity = world.BlockAccessor.GetBlockEntity(targetPos) as BlockEntityQuern;
        if (quernEntity == null)
        {
            StopGrindAnimation();
            debugLog?.Invoke("[grind] quern entity gone");
            ReportResult(true, $"quern entity gone, ground {itemsGround} item(s)");
            done = true;
            return;
        }

        // --- Accumulate time ---
        elapsedTime += dt;

        // --- Call interaction step to continue grinding ---
        bool continueInteraction = block.OnBlockInteractStep(elapsedTime, world, player, blockSel);

        // --- Track items ground (output slot changes) ---
        int currentOutputCount = GetOutputSlotCount();
        int newItemsGround = currentOutputCount - itemsGroundAtStart;
        if (newItemsGround > itemsGround)
        {
            itemsGround = newItemsGround;
            debugLog?.Invoke($"[grind] progress: {itemsGround} item(s) ground");
        }

        // --- Check completion conditions ---
        bool shouldStop = false;
        string stopReason = "";

        // Check if can no longer grind (input exhausted)
        if (!quernEntity.CanGrind())
        {
            shouldStop = true;
            stopReason = "input exhausted";
        }

        // Check count limit
        if (maxCount > 0 && itemsGround >= maxCount)
        {
            shouldStop = true;
            stopReason = $"reached count limit ({maxCount})";
        }

        // Check duration limit
        if (maxDuration > 0 && elapsedTime >= maxDuration)
        {
            shouldStop = true;
            stopReason = $"reached duration limit ({maxDuration:F1}s)";
        }

        // Check if interaction says to stop
        if (!continueInteraction)
        {
            shouldStop = true;
            stopReason = "interaction complete";
        }

        if (shouldStop)
        {
            StopGrindAnimation();

            // Stop the interaction
            if (interactionStarted)
            {
                block.OnBlockInteractStop(elapsedTime, world, player, blockSel);
            }

            debugLog?.Invoke($"[grind] completed: {stopReason}, ground {itemsGround} item(s) in {elapsedTime:F2}s");
            ReportResult(true, $"ground {itemsGround} item(s): {stopReason}");
            done = true;
        }
    }

    public override void Cancel()
    {
        StopGrindAnimation();
        if (interactionStarted && block != null && player != null)
        {
            var world = vas.Entity.Api.World;
            block.OnBlockInteractStop(elapsedTime, world, player, blockSel);
            debugLog?.Invoke($"[grind] cancelled at {elapsedTime:F2}s, ground {itemsGround} item(s)");
        }
        ReportResult(false, $"cancelled after grinding {itemsGround} item(s)");
        done = true;
        base.Cancel();
    }

    public override bool IsFinished() => done;

    public override IEntityAction Clone()
    {
        return new PolisGrindBlockAction(targetPos, player, maxRange, maxCount, maxDuration, debugLog, onResult);
    }

    void ReportResult(bool ok, string msg)
    {
        onResult?.Invoke(ok, msg);
    }

    int GetOutputSlotCount()
    {
        if (quernEntity?.Inventory == null) return 0;
        // Output slot is index 1 in InventoryQuern
        var outputSlot = quernEntity.Inventory[1];
        if (outputSlot?.Itemstack == null) return 0;
        return outputSlot.Itemstack.StackSize;
    }
}
