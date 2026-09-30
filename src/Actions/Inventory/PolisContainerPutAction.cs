using System;
using Vintagestory.API.Common;
using Vintagestory.API.Common.Entities;
using Vintagestory.API.MathTools;
using Vintagestory.API.Server;
using Vintagestory.GameContent;
using Polis.Helpers;

namespace Polis.Actions.Inventory;

/// <summary>
/// Action: Deposit items from bot inventory into a container (IBlockEntityContainer).
///
/// Validation flow:
/// 1. Actor is EntityAgent
/// 2. Range check: distance to container center ≤ range
/// 3. Block exists and has IBlockEntityContainer interface
/// 4. Claims check: owner player has Use access (via land claims system)
/// 5. Bot has EntityBehaviorSeraphInventory
/// 6. Bot slot is valid (0=right, 1=left) and not empty
/// 7. Transfer execution via ItemSlot.TryPutInto with iteration
/// 8. Mark dirty and invoke result callback
/// </summary>
public class PolisContainerPutAction : EntityActionBase
{
    private BlockPos containerPos;
    private int botSlotIndex;
    private int quantity;
    private int containerSlotIndex;
    private IServerPlayer ownerPlayer;
    private float range;
    private bool done;
    private Action<string> debugLog;
    private Action<bool, string> resultCallback;

    public override string Type => "polis-containerput";

    public PolisContainerPutAction(
        EntityActivitySystem vas,
        BlockPos targetPos,
        int botSlotIndex,
        int qty,
        IServerPlayer ownerPlayer,
        int containerSlotIndex = -1,
        float range = 4.5f,
        Action<string> debugLog = null,
        Action<bool, string> resultCallback = null)
    {
        this.vas = vas;
        this.containerPos = targetPos;
        this.botSlotIndex = botSlotIndex;
        this.quantity = qty;
        this.containerSlotIndex = containerSlotIndex;
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

        // Resolve bot slot (0=right hand, 1=left hand; backpack support deferred)
        ItemSlot sourceSlot;
        string slotName;

        if (botSlotIndex == 0)
        {
            sourceSlot = agent.RightHandItemSlot;
            slotName = "right hand";
        }
        else if (botSlotIndex == 1)
        {
            sourceSlot = agent.LeftHandItemSlot;
            slotName = "left hand";
        }
        else
        {
            Fail($"slot index {botSlotIndex} not supported (use 0=right, 1=left)");
            return;
        }

        // Slot validation
        if (sourceSlot == null || sourceSlot.Empty)
        {
            Fail($"{slotName} is empty");
            return;
        }

        var sourceStack = sourceSlot.Itemstack;
        if (sourceStack == null || sourceStack.StackSize <= 0)
        {
            Fail($"{slotName} is empty");
            return;
        }

        string itemCode = sourceStack.Collectible?.Code?.ToString() ?? "unknown";
        int available = sourceStack.StackSize;

        // Determine quantity to transfer (0 = all)
        int qtyToTransfer = (quantity <= 0 || quantity > available) ? available : quantity;

        debugLog?.Invoke($"[containerput] attempting: {itemCode} x{qtyToTransfer} from {slotName} to container");

        // Transfer items into container slots
        int totalMoved = 0;

        if (containerSlotIndex >= 0)
        {
            // Target a specific container slot
            if (containerSlotIndex >= container.Inventory.Count)
            {
                Fail($"container slot {containerSlotIndex} out of range (container has {container.Inventory.Count} slots)");
                return;
            }

            var destSlot = container.Inventory[containerSlotIndex];
            if (destSlot != null)
            {
                var op = new ItemStackMoveOperation(world, EnumMouseButton.Left, 0, EnumMergePriority.AutoMerge, qtyToTransfer);
                sourceSlot.TryPutInto(destSlot, ref op);
                if (op.MovedQuantity > 0)
                {
                    totalMoved = op.MovedQuantity;
                    destSlot.MarkDirty();
                }
            }
        }
        else
        {
            // Auto-place: iterate all slots
            for (int i = 0; i < container.Inventory.Count && !sourceSlot.Empty; i++)
            {
                var destSlot = container.Inventory[i];
                if (destSlot == null)
                {
                    continue;
                }

                var op = new ItemStackMoveOperation(world, EnumMouseButton.Left, 0, EnumMergePriority.AutoMerge, qtyToTransfer - totalMoved);
                sourceSlot.TryPutInto(destSlot, ref op);

                if (op.MovedQuantity > 0)
                {
                    totalMoved += op.MovedQuantity;
                    destSlot.MarkDirty();
                }
            }
        }

        if (totalMoved <= 0)
        {
            Fail("could not transfer any items");
            return;
        }

        // Mark block entity dirty to sync to clients
        if (blockEntity is BlockEntity be)
        {
            be.MarkDirty(true);
        }

        // Mark bot inventory dirty
        sourceSlot.MarkDirty();
        PolisInventoryHelpers.StoreSeraphInventory(agent);

        debugLog?.Invoke($"[containerput] success: transferred {totalMoved}x {itemCode} from bot to container");
        Succeed($"transferred {totalMoved} items from bot to container");
    }

    void Fail(string reason)
    {
        debugLog?.Invoke($"[containerput] failed: {reason}");
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
        return new PolisContainerPutAction(vas, containerPos, botSlotIndex, quantity, ownerPlayer, containerSlotIndex, range, debugLog, resultCallback);
    }
}
