using System;
using Vintagestory.API.Common;
using Vintagestory.API.Common.Entities;
using Vintagestory.API.Datastructures;
using Vintagestory.API.MathTools;
using Vintagestory.API.Server;
using Vintagestory.Essentials;
using Vintagestory.GameContent;

namespace Polis.Actions.Blocks;

/// <summary>
/// Action that activates a block (doors, containers, levers, etc.) at a target position.
/// </summary>
class PolisActivateBlockAction : EntityActionBase
{
    readonly BlockPos targetPos;
    readonly BlockFacing face;
    readonly Vec3d hitPos;
    readonly ITreeAttribute args;
    readonly IServerPlayer player;
    readonly float range;
    readonly Action<string> debugLog;
    readonly Action<bool, string> onResult;
    readonly bool shift;
    bool done;
    bool resultSent;

    public override string Type => "polis-activateblock";

    public PolisActivateBlockAction(BlockPos targetPos, BlockFacing face, Vec3d hitPos, ITreeAttribute args, IServerPlayer player, float range, Action<string> debugLog, Action<bool, string> onResult, bool shift = false)
    {
        this.targetPos = targetPos;
        this.face = face;
        this.hitPos = hitPos;
        this.args = args;
        this.player = player;
        this.range = range;
        this.debugLog = debugLog;
        this.onResult = onResult;
        this.shift = shift;
    }

    public override void Start(EntityActivity entityActivity)
    {
        done = true;

        var center = new Vec3d(targetPos.X + 0.5, targetPos.Y + 0.5, targetPos.Z + 0.5);
        var dist = vas.Entity.ServerPos.XYZ.DistanceTo(center);
        if (dist > range)
        {
            var msg = $"out of range dist={dist:0.00} range={range:0.00}";
            debugLog?.Invoke($"[activate] failed: {msg}");
            ExecutionHasFailed = true;
            ReportResult(false, msg);
            return;
        }

        var block = vas.Entity.Api.World.BlockAccessor.GetBlock(targetPos);
        if (block == null || block.Id == 0)
        {
            var msg = "missing block";
            debugLog?.Invoke("[activate] failed: missing block");
            ExecutionHasFailed = true;
            ReportResult(false, msg);
            return;
        }

        var blockSel = new BlockSelection
        {
            Block = block,
            Position = targetPos,
            HitPosition = hitPos ?? new Vec3d(0.5, 0.5, 0.5),
            Face = face ?? BlockFacing.NORTH
        };

        // Check if block has any activatable behaviors before attempting activation
        // This prevents false-positive success reports for non-interactive blocks
        bool hasActivatableBehavior = false;

        // Check for known activatable behaviors
        if (block.HasBehavior<BlockBehaviorDoor>() ||
            block.HasBehavior<BlockBehaviorLadder>())
        {
            hasActivatableBehavior = true;
        }

        // Check if block has an associated block entity (containers, machines, etc.)
        var blockEntity = vas.Entity.Api.World.BlockAccessor.GetBlockEntity(targetPos);
        if (blockEntity != null)
        {
            hasActivatableBehavior = true;
        }

        // Also check for common activatable block codes
        var blockCode = block.Code?.Path ?? "";
        if (blockCode.Contains("door") || blockCode.Contains("gate") || blockCode.Contains("trapdoor") ||
            blockCode.Contains("chest") || blockCode.Contains("barrel") || blockCode.Contains("crate") ||
            blockCode.Contains("lever") || blockCode.Contains("button") || blockCode.Contains("anvil") ||
            blockCode.Contains("forge") || blockCode.Contains("quern") || blockCode.Contains("press"))
        {
            hasActivatableBehavior = true;
        }

        bool handled = false;
        if (player != null)
        {
            if (shift) player.Entity.Controls.ShiftKey = true;
            try
            {
                handled = block.OnBlockInteractStart(vas.Entity.World, player, blockSel);
            }
            finally
            {
                if (shift) player.Entity.Controls.ShiftKey = false;
            }
            debugLog?.Invoke($"[activate] interactstart handled={handled} shift={shift}");
        }

        if (!handled)
        {
            // If block has no activatable behaviors and OnBlockInteractStart didn't handle it,
            // this activation will have no effect - report failure
            if (!hasActivatableBehavior)
            {
                var msg = $"block {block.Code} has no activation behavior";
                debugLog?.Invoke($"[activate] failed: {msg}");
                ExecutionHasFailed = true;
                ReportResult(false, msg);
                return;
            }

            var caller = new Caller
            {
                Entity = vas.Entity,
                Pos = vas.Entity.Pos.XYZ
            };
            if (player != null)
            {
                caller.Type = EnumCallerType.Player;
                caller.Player = player;
            }
            else
            {
                caller.Type = EnumCallerType.Entity;
            }

            block.Activate(vas.Entity.World, caller, blockSel, args ?? new TreeAttribute());
        }
        debugLog?.Invoke("[activate] ok");
        ReportResult(true, handled ? "handled" : "activated");
    }

    public override bool IsFinished() => done;

    public override IEntityAction Clone()
    {
        return new PolisActivateBlockAction(targetPos, face, hitPos?.Clone(), args, player, range, debugLog, onResult, shift);
    }

    void ReportResult(bool ok, string msg)
    {
        if (resultSent) return;
        resultSent = true;
        onResult?.Invoke(ok, msg);
    }
}
