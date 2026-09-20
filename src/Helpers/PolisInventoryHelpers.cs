using System;
using Vintagestory.API.Common;
using Vintagestory.API.Common.Entities;
using Vintagestory.GameContent;
using PolisBuilderNpc.Core;

namespace PolisBuilderNpc.Helpers;

internal static class PolisInventoryHelpers
{

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

        var invbh = agent.GetBehavior<EntityBehaviorSeraphInventory>();
        if (invbh?.Inventory == null)
        {
            reason = "seraph inventory missing";
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
            moved += TryPutIntoBackpacks(agent.World, invbh.Inventory, dummy);
        }

        if (moved > 0)
        {
            invbh.storeInv();
            debugLog?.Invoke($"[inventory] inserted {moved}x {stack.Collectible?.Code?.ToString() ?? "item"} into bot inventory");
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
    /// Searches RightHand, LeftHand, then backpack contents.
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

        // Check backpacks
        var invbh = agent.GetBehavior<EntityBehaviorSeraphInventory>();
        if (invbh?.Inventory == null || invbh.Inventory.Count <= PolisConstants.BackpackSlotId1)
        {
            return null;
        }

        ItemSlot[] bagSlots = { invbh.Inventory[PolisConstants.BackpackSlotId0], invbh.Inventory[PolisConstants.BackpackSlotId1] };
        for (int bagIndex = 0; bagIndex < bagSlots.Length; bagIndex++)
        {
            var bagSlot = bagSlots[bagIndex];
            if (bagSlot?.Itemstack == null)
            {
                continue;
            }

            var bag = bagSlot.Itemstack.Collectible?.GetCollectibleInterface<IHeldBag>();
            if (bag == null)
            {
                continue;
            }

            var contents = bag.GetOrCreateSlots(bagSlot.Itemstack, invbh.Inventory, bagIndex, agent.World);
            if (contents == null)
            {
                continue;
            }

            foreach (var contentSlot in contents)
            {
                if (contentSlot?.Itemstack?.Collectible is Block bagBlock && bagBlock.Code.Equals(block.Code))
                {
                    debugLog?.Invoke($"[inventory] found {block.Code} in backpack {bagIndex}");
                    return contentSlot;
                }
            }
        }

        return null;
    }

    private static int TryPutIntoBackpacks(IWorldAccessor world, InventoryBase inv, ItemSlot sourceSlot)
    {
        if (world == null || inv == null || sourceSlot == null || sourceSlot.Empty)
        {
            return 0;
        }

        if (inv.Count <= PolisConstants.BackpackSlotId1)
        {
            return 0;
        }

        var backpack0 = inv[PolisConstants.BackpackSlotId0];
        var backpack1 = inv[PolisConstants.BackpackSlotId1];
        int moved = 0;

        bool isBagItem = sourceSlot.Itemstack?.Collectible?.GetCollectibleInterface<IHeldBag>() != null;

        if (isBagItem)
        {
            moved += TryPutIntoSlot(world, sourceSlot, backpack0, true);
            if (!sourceSlot.Empty)
            {
                moved += TryPutIntoSlot(world, sourceSlot, backpack1, true);
            }
        }

        if (sourceSlot.Empty)
        {
            return moved;
        }

        ItemSlot[] bagSlots = { backpack0, backpack1 };
        for (int bagIndex = 0; bagIndex < bagSlots.Length; bagIndex++)
        {
            if (sourceSlot.Empty)
            {
                break;
            }

            var bagSlot = bagSlots[bagIndex];
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
