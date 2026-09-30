using System;
using Vintagestory.API.Common;
using Vintagestory.API.MathTools;
using Vintagestory.API.Server;
using Vintagestory.Essentials;
using Vintagestory.GameContent;

namespace Polis.Actions.Workstations;

/// <summary>
/// Action: Seal a barrel for fermentation/pickling.
///
/// Validation flow:
/// 1. Range check: distance to barrel center <= range
/// 2. Block exists and is a barrel
/// 3. Barrel has BlockEntityBarrel
/// 4. Barrel is not already sealed
/// 5. Barrel can be sealed (has valid sealing recipe with items + liquid)
/// 6. Call SealBarrel() to seal
/// </summary>
class PolisSealBarrelAction : EntityActionBase
{
    readonly BlockPos targetPos;
    readonly IServerPlayer player;
    readonly float maxRange;
    readonly Action<string> debugLog;
    readonly Action<bool, string> onResult;
    bool done;

    const float DEFAULT_MAX_RANGE = 4.5f;

    public override string Type => "polis-sealbarrel";

    public PolisSealBarrelAction(
        BlockPos targetPos,
        IServerPlayer player,
        float maxRange = DEFAULT_MAX_RANGE,
        Action<string> debugLog = null,
        Action<bool, string> onResult = null
    )
    {
        this.targetPos = targetPos;
        this.player = player;
        this.maxRange = maxRange;
        this.debugLog = debugLog;
        this.onResult = onResult;
    }

    public override void Start(EntityActivity entityActivity)
    {
        done = true; // Instant action
        var world = vas.Entity.Api.World;

        // --- Range Check ---
        var center = new Vec3d(targetPos.X + 0.5, targetPos.Y + 0.5, targetPos.Z + 0.5);
        double dist = vas.Entity.ServerPos.XYZ.DistanceTo(center);
        if (dist > maxRange)
        {
            debugLog?.Invoke($"[seal] failed: out of range dist={dist:F1} > {maxRange}");
            ReportResult(false, $"out of range: {dist:F1} > {maxRange}");
            ExecutionHasFailed = true;
            return;
        }

        // --- Player Validation ---
        if (player == null)
        {
            debugLog?.Invoke("[seal] failed: missing player");
            ReportResult(false, "missing player");
            ExecutionHasFailed = true;
            return;
        }

        // --- Block Validation ---
        var block = world.BlockAccessor.GetBlock(targetPos);
        if (block == null || block.Id == 0)
        {
            debugLog?.Invoke("[seal] failed: no block at target");
            ReportResult(false, "no block at target");
            ExecutionHasFailed = true;
            return;
        }

        // --- Check for barrel block ---
        if (!block.Code.Path.StartsWith("barrel"))
        {
            debugLog?.Invoke($"[seal] failed: block {block.Code} is not a barrel");
            ReportResult(false, $"block {block.Code} is not a barrel");
            ExecutionHasFailed = true;
            return;
        }

        // --- Get BlockEntityBarrel ---
        var barrelEntity = world.BlockAccessor.GetBlockEntity(targetPos) as BlockEntityBarrel;
        if (barrelEntity == null)
        {
            debugLog?.Invoke("[seal] failed: no barrel block entity");
            ReportResult(false, "no barrel block entity");
            ExecutionHasFailed = true;
            return;
        }

        // --- Check if already sealed ---
        if (barrelEntity.Sealed)
        {
            debugLog?.Invoke("[seal] failed: barrel already sealed");
            ReportResult(false, "barrel already sealed");
            ExecutionHasFailed = true;
            return;
        }

        // --- Check CanSeal ---
        if (!barrelEntity.CanSeal)
        {
            debugLog?.Invoke("[seal] failed: barrel cannot be sealed (no valid sealing recipe)");
            ReportResult(false, "barrel cannot be sealed (no valid sealing recipe - needs items + liquid for fermentation)");
            ExecutionHasFailed = true;
            return;
        }

        // --- Seal the barrel ---
        barrelEntity.SealBarrel();

        // Play seal sound
        world.PlaySoundAt(new AssetLocation("sounds/player/seal"), targetPos.X + 0.5, targetPos.Y + 0.5, targetPos.Z + 0.5, null, false, 16f);

        debugLog?.Invoke($"[seal] success: sealed barrel at {targetPos}");
        ReportResult(true, "sealed");
    }

    public override bool IsFinished() => done;

    public override void Cancel()
    {
        done = true;
        base.Cancel();
    }

    public override IEntityAction Clone()
    {
        return new PolisSealBarrelAction(targetPos, player, maxRange, debugLog, onResult);
    }

    void ReportResult(bool ok, string msg)
    {
        onResult?.Invoke(ok, msg);
    }
}
