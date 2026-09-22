using System;
using Vintagestory.API.Common;
using Vintagestory.API.Common.Entities;
using Vintagestory.API.MathTools;
using Vintagestory.API.Server;
using Vintagestory.GameContent;
using PolisBuilderNpc.Helpers;

namespace PolisBuilderNpc.Actions.Inventory;

/// <summary>
/// Action: Withdraw items from a container (IBlockEntityContainer) into bot inventory.
///
/// Validation flow:
/// 1. Actor is EntityAgent
/// 2. Range check: distance to container center ≤ range
/// 3. Block exists and has IBlockEntityContainer interface
/// 4. Claims check: owner player has Use access (via land claims system)
/// 5. Bot has EntityBehaviorSeraphInventory
/// 6. Container slot is not empty
/// 7. Transfer execution via PolisInventoryHelpers
/// 8. Mark dirty and invoke result callback
/// </summary>
public class PolisContainerTakeAction : EntityActionBase
{
    private BlockPos containerPos;
    private int containerSlotIndex;
    private int quantity;
    private IServerPlayer ownerPlayer;
    private float range;
    private bool done;
    private Action<string> debugLog;
    private Action<bool, string> resultCallback;

    public override string Type => "polis-containertake";

    public PolisContainerTakeAction(
        EntityActivitySystem vas,
        BlockPos targetPos,
        int containerSlotIndex,
        int qty,
        IServerPlayer ownerPlayer,
        float range = 4.5f,
        Action<string> debugLog = null,
        Action<bool, string> resultCallback = null)
    {
        this.vas = vas;
        this.containerPos = targetPos;
        this.containerSlotIndex = containerSlotIndex;
        this.quantity = qty;
        this.ownerPlayer = ownerPlayer;
        this.range = range;
        this.debugLog = debugLog;
        this.resultCallback = resultCallback;
    }

    public override void Start(EntityActivity activity)
    {
        var agent = vas?.Entity as EntityAgent;
        if (agent == null)
        {
            Fail("actor is not an agent");
            return;
        }

        var world = vas?.Entity?.World;
        if (world == null)
        {
            Fail("world is null");
            return;
        }

        // Range check: distance to container block center
        var agentPos = agent.ServerPos.XYZ;
        var containerCenter = new Vec3d(containerPos.X + 0.5, containerPos.Y + 0.5, containerPos.Z + 0.5);
        double dist = agentPos.DistanceTo(containerCenter);
        if (dist > range)
        {
            Fail($"out of range dist={dist:0.00} range={range:0.00}");
            return;
        }

        // Block existence check
        var block = world.BlockAccessor.GetBlock(containerPos);
        if (block.Id == 0)
        {
            Fail("no block at target position");
            return;
        }

        // Container interface check
        var blockEntity = world.BlockAccessor.GetBlockEntity(containerPos);
        var container = blockEntity as IBlockEntityContainer;
        if (container == null)
        {
            Fail($"block is not a container (is {block.Code})");
            return;
        }

        if (container.Inventory == null)
        {
            Fail("container has no inventory");
            return;
        }

        // Claims check (if claims system active)
        if (ownerPlayer != null && world.Claims != null)
        {
            var claimResponse = world.Claims.TestAccess(ownerPlayer, containerPos, EnumBlockAccessFlags.Use);
            if (claimResponse != EnumWorldAccessResponse.Granted)
            {
                Fail("access denied by land claim");
                return;
            }
        }

        // Bot inventory check
        if (PolisInventoryHelpers.BotCargo(agent) == null)
        {
            Fail("bot has no seraph inventory");
            return;
        }

        // Container slot validation
        if (containerSlotIndex < 0 || containerSlotIndex >= container.Inventory.Count)
        {
            Fail($"invalid slot index {containerSlotIndex}");
            return;
        }

        var sourceSlot = container.Inventory[containerSlotIndex];
        if (sourceSlot == null || sourceSlot.Empty)
        {
            Fail($"container slot {containerSlotIndex} is empty");
            return;
        }

        var sourceStack = sourceSlot.Itemstack;
        if (sourceStack == null || sourceStack.StackSize <= 0)
        {
            Fail($"container slot {containerSlotIndex} is empty");
            return;
        }

        string itemCode = sourceStack.Collectible?.Code?.ToString() ?? "unknown";
        int originalSize = sourceStack.StackSize;

        debugLog?.Invoke($"[containertake] attempting: {itemCode} x{originalSize} from container slot {containerSlotIndex}");

        // Determine quantity to transfer (0 = all)
        int qtyToTransfer = (quantity <= 0 || quantity > originalSize) ? originalSize : quantity;

        // Create a stack copy for transfer
        var transferStack = sourceStack.Clone();
        transferStack.StackSize = qtyToTransfer;

        // Try to insert into bot inventory
        if (!PolisInventoryHelpers.TryInsertIntoBotInventory(agent, transferStack, out int moved, out string insertError, debugLog))
        {
            Fail(insertError ?? "could not transfer any items");
            return;
        }

        if (moved <= 0)
        {
            Fail("could not transfer any items");
            return;
        }

        // Update container slot (decrement or clear)
        sourceSlot.Itemstack.StackSize -= moved;
        if (sourceSlot.Itemstack.StackSize <= 0)
        {
            sourceSlot.Itemstack = null;
        }

        // Mark dirty
        sourceSlot.MarkDirty();
        if (blockEntity is BlockEntity be)
        {
            be.MarkDirty(true);
        }

        debugLog?.Invoke($"[containertake] success: transferred {moved}x {itemCode} from container to bot");
        Succeed($"transferred {moved} items from container to bot");
    }

    void Fail(string reason)
    {
        debugLog?.Invoke($"[containertake] failed: {reason}");
        resultCallback?.Invoke(false, reason);
        ExecutionHasFailed = true;
        done = true;
    }

    void Succeed(string msg)
    {
        resultCallback?.Invoke(true, msg);
        done = true;
    }

    public override bool IsFinished()
    {
        return done;
    }

    public override void Cancel()
    {
        done = true;
    }

    public override IEntityAction Clone()
    {
        return new PolisContainerTakeAction(vas, containerPos, containerSlotIndex, quantity, ownerPlayer, range, debugLog, resultCallback);
    }
}
