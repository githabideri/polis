using System;
using Vintagestory.API.Common;
using Vintagestory.API.Common.Entities;
using Vintagestory.GameContent;
using PolisBuilderNpc.Core;

namespace PolisBuilderNpc.Helpers;

internal static class PolisInventoryHelpers
{
    /// <summary>
    /// The bot's cargo inventory: 16 generic slots created on EntityPolisBot
    /// ([0]=right hand, [1]=left hand, [2..15]=grid). 1.22 turned the seraph
    /// behavior into an equipment-only inventory, so all bot cargo goes
    /// through this seam.
    /// </summary>
    internal static InventoryBase BotCargo(EntityAgent agent)
        => (agent as EntityPolisBot)?.Cargo;

    internal static ItemSlot BackpackSlot(EntityAgent agent, int which)
    {
        var inv = BotCargo(agent);
        int idx = which == 0 ? PolisConstants.CargoBackpackSlot0 : PolisConstants.CargoBackpackSlot1;
        return inv != null && idx < inv.Count ? inv[idx] : null;
    }

    internal static bool TryInsertIntoBotInventory(EntityAgent agent, ItemStack stack, out int moved, out string reason, Action<string> debugLog = null)
    {
        moved = 0;
        reason = null;

        if (agent == null)
        {
            reason = "actor is null";
            return false;
        }

        if (stack == null || stack.StackSize <= 0)
        {
            reason = "stack is empty";
            return false;
        }

        var cargo = BotCargo(agent);
        if (cargo == null || cargo.Count == 0)
        {
            reason = "cargo inventory missing";
            return false;
        }

        var dummy = new DummySlot(null) { Itemstack = stack.Clone() };

        moved += TryPutIntoSlot(agent.World, dummy, agent.RightHandItemSlot, true);
        if (!dummy.Empty)
        {
            moved += TryPutIntoSlot(agent.World, dummy, agent.LeftHandItemSlot, true);
        }

        if (!dummy.Empty)
        {
            moved += TryPutIntoCargoGrid(agent.World, cargo, dummy);
        }

        if (moved > 0)
        {
            debugLog?.Invoke($"[inventory] inserted {moved}x {stack.Collectible?.Code?.ToString() ?? "item"} into bot cargo");
            return true;
        }

        reason = "inventory full or no valid slots";
        return false;
    }

    internal static void StoreSeraphInventory(EntityAgent agent)
    {
        var invbh = agent?.GetBehavior<EntityBehaviorSeraphInventory>();
        invbh?.storeInv();
    }

    /// <summary>
    /// Finds the first inventory slot containing the specified block.
    /// Searches RightHand, LeftHand, cargo grid slots, then carried-bag contents.
    /// </summary>
    internal static ItemSlot FindBlockInInventory(EntityAgent agent, Block block, Action<string> debugLog = null)
    {
        if (agent == null || block == null)
        {
            return null;
        }

        // Check RightHand
        if (agent.RightHandItemSlot?.Itemstack?.Collectible is Block rightBlock && rightBlock.Code.Equals(block.Code))
        {
            debugLog?.Invoke($"[inventory] found {block.Code} in RightHand");
            return agent.RightHandItemSlot;
        }

        // Check LeftHand
        if (agent.LeftHandItemSlot?.Itemstack?.Collectible is Block leftBlock && leftBlock.Code.Equals(block.Code))
        {
            debugLog?.Invoke($"[inventory] found {block.Code} in LeftHand");
            return agent.LeftHandItemSlot;
        }

        var cargo = BotCargo(agent);
        if (cargo == null)
        {
            return null;
        }

        // Check cargo grid slots
        for (int i = 0; i < cargo.Count; i++)
        {
            var slot = cargo[i];
            if (slot?.Itemstack?.Collectible is Block gridBlock && gridBlock.Code.Equals(block.Code))
            {
                debugLog?.Invoke($"[inventory] found {block.Code} in cargo slot {i}");
                return slot;
            }
        }

        // Check carried bags
        for (int bagIndex = 0; bagIndex < cargo.Count; bagIndex++)
        {
            var bagSlot = cargo[bagIndex];
            if (bagSlot?.Itemstack == null)
            {
                continue;
            }

            var bag = bagSlot.Itemstack.Collectible?.GetCollectibleInterface<IHeldBag>();
            if (bag == null)
            {
                continue;
            }

            var contents = bag.GetOrCreateSlots(bagSlot.Itemstack, cargo, bagIndex, agent.World);
            if (contents == null)
            {
                continue;
            }

            foreach (var contentSlot in contents)
            {
                if (contentSlot?.Itemstack?.Collectible is Block bagBlock && bagBlock.Code.Equals(block.Code))
                {
                    debugLog?.Invoke($"[inventory] found {block.Code} in bag slot {bagIndex}");
                    return contentSlot;
                }
            }
        }

        return null;
    }

    /// <summary>
    /// Pushes a stack into free cargo grid slots, then into carried-bag
    /// contents if still remaining.
    /// </summary>
    private static int TryPutIntoCargoGrid(IWorldAccessor world, InventoryBase inv, ItemSlot sourceSlot)
    {
        if (world == null || inv == null || sourceSlot == null || sourceSlot.Empty)
        {
            return 0;
        }

        int moved = 0;

        // 1) direct grid slots (skip the hand slots, handled by the caller)
        for (int i = 0; i < inv.Count && !sourceSlot.Empty; i++)
        {
            if (i <= 1)
            {
                continue;
            }
            moved += TryPutIntoSlot(world, sourceSlot, inv[i], true);
        }

        if (sourceSlot.Empty)
        {
            return moved;
        }

        // 2) carried bags
        for (int bagIndex = 0; bagIndex < inv.Count && !sourceSlot.Empty; bagIndex++)
        {
            var bagSlot = inv[bagIndex];
            if (bagSlot?.Itemstack == null)
            {
                continue;
            }

            var bag = bagSlot.Itemstack.Collectible?.GetCollectibleInterface<IHeldBag>();
            if (bag == null)
            {
                continue;
            }

            var contents = bag.GetOrCreateSlots(bagSlot.Itemstack, inv, bagIndex, world);
            if (contents == null)
            {
                continue;
            }

            foreach (var contentSlot in contents)
            {
                if (sourceSlot.Empty)
                {
                    break;
                }

                int movedInto = TryPutIntoBagContent(sourceSlot, contentSlot);
                if (movedInto > 0)
                {
                    moved += movedInto;
                    bag.Store(bagSlot.Itemstack, contentSlot);
                    bagSlot.MarkDirty();
                }
            }
        }

        return moved;
    }

    private static int TryPutIntoBagContent(ItemSlot sourceSlot, ItemSlot destSlot)
    {
        if (sourceSlot == null || destSlot == null || sourceSlot.Empty)
        {
            return 0;
        }

        var sourceStack = sourceSlot.Itemstack;
        if (sourceStack == null || sourceStack.StackSize <= 0)
        {
            return 0;
        }

        if (destSlot.Empty)
        {
            if (!destSlot.CanHold(sourceSlot))
            {
                return 0;
            }

            int moved = Math.Min(sourceStack.StackSize, destSlot.GetRemainingSlotSpace(sourceStack));
            if (moved <= 0)
            {
                return 0;
            }

            destSlot.Itemstack = sourceStack.Clone();
            destSlot.Itemstack.StackSize = moved;

            sourceStack.StackSize -= moved;
            if (sourceStack.StackSize <= 0)
            {
                sourceSlot.Itemstack = null;
            }

            return moved;
        }

        if (!destSlot.CanTakeFrom(sourceSlot, EnumMergePriority.AutoMerge))
        {
            return 0;
        }

        int movedInto = Math.Min(sourceStack.StackSize, destSlot.GetRemainingSlotSpace(sourceStack));
        if (movedInto <= 0)
        {
            return 0;
        }

        destSlot.Itemstack.StackSize += movedInto;
        sourceStack.StackSize -= movedInto;
        if (sourceStack.StackSize <= 0)
        {
            sourceSlot.Itemstack = null;
        }

        return movedInto;
    }

    private static int TryPutIntoSlot(IWorldAccessor world, ItemSlot sourceSlot, ItemSlot destSlot, bool markDestDirty)
    {
        if (world == null || sourceSlot == null || destSlot == null || sourceSlot.Empty)
        {
            return 0;
        }

        var sourceStack = sourceSlot.Itemstack;
        if (sourceStack == null || sourceStack.StackSize <= 0)
        {
            return 0;
        }

        var op = new ItemStackMoveOperation(world, EnumMouseButton.Left, 0, EnumMergePriority.AutoMerge, sourceStack.StackSize);
        sourceSlot.TryPutInto(destSlot, ref op);

        if (op.MovedQuantity > 0 && markDestDirty)
        {
            destSlot.MarkDirty();
        }

        return op.MovedQuantity;
    }
}
