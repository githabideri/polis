using System;
using Vintagestory.API.Common;
using Vintagestory.API.Common.Entities;
using Vintagestory.API.MathTools;
using Vintagestory.Essentials;
using Vintagestory.GameContent;

namespace PolisBuilderNpc.Actions.Blocks;

/// <summary>
/// Action that ignites a block (forges, firewood piles, etc.) at a target position.
/// </summary>
class PolisIgniteBlockAction : EntityActionBase
{
    readonly BlockPos targetPos;
    readonly BlockFacing face;
    readonly Entity botEntity;
    readonly float range;
    readonly Action<string> debugLog;
    readonly Action<bool, string> onResult;
    bool done;
    bool resultSent;

    public override string Type => "polis-igniteblock";

    public PolisIgniteBlockAction(BlockPos targetPos, BlockFacing face, Entity botEntity, float range, Action<string> debugLog, Action<bool, string> onResult)
    {
        this.targetPos = targetPos;
        this.face = face;
        this.botEntity = botEntity;
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
            debugLog?.Invoke($"[ignite] failed: {msg}");
            ExecutionHasFailed = true;
            ReportResult(false, msg);
            return;
        }

        var block = vas.Entity.Api.World.BlockAccessor.GetBlock(targetPos);
        if (block == null || block.Id == 0)
        {
            var msg = "missing block";
            debugLog?.Invoke("[ignite] failed: missing block");
            ExecutionHasFailed = true;
            ReportResult(false, msg);
            return;
        }

        // Get IIgnitable interface
        var ignitable = block.GetInterface<IIgnitable>(vas.Entity.World, targetPos);
        if (ignitable == null)
        {
            var msg = $"block {block.Code} not ignitable";
            debugLog?.Invoke($"[ignite] failed: {msg}");
            ExecutionHasFailed = true;
            ReportResult(false, msg);
            return;
        }

        // Check current ignitable state with 0 seconds (initial check)
        var state = ignitable.OnTryIgniteBlock(botEntity as EntityAgent, targetPos, 0);
        debugLog?.Invoke($"[ignite] initial state={state}");

        if (state == EnumIgniteState.NotIgnitable || state == EnumIgniteState.NotIgnitablePreventDefault)
        {
            var msg = $"not ignitable (state={state})";
            debugLog?.Invoke($"[ignite] failed: {msg}");
            ExecutionHasFailed = true;
            ReportResult(false, msg);
            return;
        }

        // Simulate holding for sufficient time (3+ seconds) to ignite
        // Pass enough time to trigger IgniteNow state
        state = ignitable.OnTryIgniteBlock(botEntity as EntityAgent, targetPos, 3.5f);
        debugLog?.Invoke($"[ignite] after 3.5s state={state}");

        if (state == EnumIgniteState.IgniteNow)
        {
            // Call OnTryIgniteBlockOver to complete the ignition
            var handling = EnumHandling.PassThrough;
            ignitable.OnTryIgniteBlockOver(botEntity as EntityAgent, targetPos, 3.5f, ref handling);
            debugLog?.Invoke($"[ignite] OnTryIgniteBlockOver called, handling={handling}");
            ReportResult(true, "ignited");
        }
        else
        {
            var msg = $"ignition failed (state={state})";
            debugLog?.Invoke($"[ignite] failed: {msg}");
            ExecutionHasFailed = true;
            ReportResult(false, msg);
        }
    }

    public override bool IsFinished() => done;

    public override IEntityAction Clone()
    {
        return new PolisIgniteBlockAction(targetPos, face, botEntity, range, debugLog, onResult);
    }

    void ReportResult(bool ok, string msg)
    {
        if (resultSent) return;
        resultSent = true;
        onResult?.Invoke(ok, msg);
    }
}
