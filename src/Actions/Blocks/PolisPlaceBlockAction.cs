using System;
using Vintagestory.API.Common;
using Vintagestory.API.Common.Entities;
using Vintagestory.API.MathTools;
using Vintagestory.API.Server;
using Vintagestory.Essentials;
using Vintagestory.GameContent;
using Polis.Helpers;

namespace Polis.Actions.Blocks;

/// <summary>
/// Action that places a block at a target position.
/// </summary>
class PolisPlaceBlockAction : EntityActionBase
{
    readonly BlockPos targetPos;  // Position where block will be placed (typically air)
    readonly BlockFacing face;
    readonly Vec3d hitPos;
    readonly Block block;
    readonly ItemStack stack;
    readonly IServerPlayer player;
    readonly float range;
    readonly Action<string> debugLog;
    readonly ItemSlot sourceSlot;
    readonly Action<bool, string> onResult;
    bool done;

    public override string Type => "polis-placeblock";

    public PolisPlaceBlockAction(BlockPos targetPos, BlockFacing face, Vec3d hitPos, Block block, ItemStack stack, IServerPlayer player, float range, Action<string> debugLog, ItemSlot sourceSlot = null, Action<bool, string> onResult = null)
    {
        this.targetPos = targetPos;
        this.face = face;
        this.hitPos = hitPos;
        this.block = block;
        this.stack = stack?.Clone();
        this.player = player;
        this.range = range;
        this.debugLog = debugLog;
        this.sourceSlot = sourceSlot;
        this.onResult = onResult;
    }

    public override void Start(EntityActivity entityActivity)
    {
        done = true;

        var center = new Vec3d(targetPos.X + 0.5, targetPos.Y + 0.5, targetPos.Z + 0.5);
        var dist = vas.Entity.ServerPos.XYZ.DistanceTo(center);
        if (dist > range)
        {
            debugLog?.Invoke($"[place] failed: out of range dist={dist:0.00} range={range:0.00}");
            onResult?.Invoke(false, $"out of range: {dist:0.00} > {range:0.00}");
            ExecutionHasFailed = true;
            return;
        }

        if (block == null || stack == null || player == null)
        {
            debugLog?.Invoke("[place] failed: missing block/stack/player");
            onResult?.Invoke(false, "missing block/stack/player");
            ExecutionHasFailed = true;
            return;
        }

        // BlockSelection.Position must be the target (air) position, not the clicked surface
        // VS's TryPlaceBlock checks if the block at Position is replaceable
        var blockSel = new BlockSelection
        {
            Position = targetPos,
            Face = face ?? BlockFacing.NORTH,
            HitPosition = hitPos ?? new Vec3d(0.5, 0.5, 0.5),
            DidOffset = true,  // Indicates position was pre-offset to target
            Block = vas.Entity.Api.World.BlockAccessor.GetBlock(targetPos.AddCopy(face?.Opposite ?? BlockFacing.DOWN))
        };

        string failureCode = null;
        bool ok = block.TryPlaceBlock(vas.Entity.World, player, stack, blockSel, ref failureCode);
        if (!ok)
        {
            debugLog?.Invoke("[place] failed" + (failureCode != null ? ": " + failureCode : ""));
            onResult?.Invoke(false, failureCode ?? "placement failed");
            ExecutionHasFailed = true;
        }
        else
        {
            // Consume item from source slot if provided
            // Use direct stack modification instead of TakeOut() for reliable entity inventory updates
            if (sourceSlot != null && !sourceSlot.Empty && sourceSlot.Itemstack != null)
            {
                if (sourceSlot.Itemstack.StackSize <= 1)
                {
                    sourceSlot.Itemstack = null;
                }
                else
                {
                    sourceSlot.Itemstack.StackSize -= 1;
                }
                sourceSlot.MarkDirty();
                PolisInventoryHelpers.StoreSeraphInventory(vas.Entity as EntityAgent);
                debugLog?.Invoke($"[place] consumed 1 block from inventory, remaining: {sourceSlot.Itemstack?.StackSize ?? 0}");
            }
            debugLog?.Invoke("[place] ok");
            onResult?.Invoke(true, "placed");
        }
    }

    public override bool IsFinished() => done;

    public override IEntityAction Clone()
    {
        return new PolisPlaceBlockAction(targetPos, face, hitPos?.Clone(), block, stack, player, range, debugLog, sourceSlot, onResult);
    }
}
