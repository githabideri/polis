using System;
using Vintagestory.API.Common;
using Vintagestory.API.MathTools;
using Vintagestory.API.Server;
using Vintagestory.Essentials;
using Vintagestory.GameContent;

namespace PolisBuilderNpc.Actions.Blocks;

/// <summary>
/// Action that instantly breaks a block at a target position (without mining animation).
/// </summary>
class PolisBreakBlockAction : EntityActionBase
{
    readonly BlockPos targetPos;
    readonly IServerPlayer player;
    readonly float dropMult;
    readonly float range;
    readonly Action<string> debugLog;
    readonly Action<bool, string> onResult;
    bool done;

    public override string Type => "polis-breakblock";

    public PolisBreakBlockAction(BlockPos targetPos, IServerPlayer player, float dropMult, float range, Action<string> debugLog, Action<bool, string> onResult = null)
    {
        this.targetPos = targetPos;
        this.player = player;
        this.dropMult = dropMult;
        this.range = range;
        this.debugLog = debugLog;
        this.onResult = onResult;
    }

    public override void Start(EntityActivity entityActivity)
    {
        done = true;

        var center = new Vec3d(targetPos.X + 0.5, targetPos.Y + 0.5, targetPos.Z + 0.5);
        var dist = vas.Entity.ServerPos.XYZ.DistanceTo(center);
        if (dist > range)
        {
            var msg = $"out of range dist={dist:0.00} range={range:0.00}";
            debugLog?.Invoke($"[break] failed: {msg}");
            ExecutionHasFailed = true;
            onResult?.Invoke(false, msg);
            return;
        }

        if (player == null)
        {
            debugLog?.Invoke("[break] failed: missing player");
            ExecutionHasFailed = true;
            onResult?.Invoke(false, "missing player");
            return;
        }

        // Capture block state before breaking to verify success
        var blockBefore = vas.Entity.Api.World.BlockAccessor.GetBlock(targetPos);
        int blockIdBefore = blockBefore?.Id ?? 0;
        string blockCodeBefore = blockBefore?.Code?.Path ?? "air";

        if (blockIdBefore == 0)
        {
            debugLog?.Invoke("[break] failed: no block at position");
            ExecutionHasFailed = true;
            onResult?.Invoke(false, "no block at position");
            return;
        }

        vas.Entity.Api.World.BlockAccessor.BreakBlock(targetPos, player, dropMult);

        // Verify the block was actually broken by checking if it changed
        var blockAfter = vas.Entity.Api.World.BlockAccessor.GetBlock(targetPos);
        int blockIdAfter = blockAfter?.Id ?? 0;

        if (blockIdAfter == blockIdBefore)
        {
            // Block didn't change - break failed (likely due to claims or unbreakable)
            var msg = $"block {blockCodeBefore} was not broken (claims or unbreakable)";
            debugLog?.Invoke($"[break] failed: {msg}");
            ExecutionHasFailed = true;
            onResult?.Invoke(false, msg);
            return;
        }

        debugLog?.Invoke($"[break] ok: {blockCodeBefore} -> {blockAfter?.Code?.Path ?? "air"}");
        onResult?.Invoke(true, $"broke {blockCodeBefore}");
    }

    public override bool IsFinished() => done;

    public override IEntityAction Clone()
    {
        return new PolisBreakBlockAction(targetPos, player, dropMult, range, debugLog, onResult);
    }
}
