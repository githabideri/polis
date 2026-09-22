using Vintagestory.API.Common;
using Vintagestory.GameContent;
using PolisBuilderNpc.Core;

namespace PolisBuilderNpc.Helpers;

internal static class PolisProfessionHelper
{
    /// <summary>
    /// Applies a profession loadout to an entity. Best-effort: logs warnings for
    /// items that fail to resolve but does not abort the spawn.
    /// </summary>
    /// <param name="entity">The entity to equip.</param>
    /// <param name="loadout">Profession loadout to apply.</param>
    /// <param name="resolveStack">Delegate that resolves (itemCode, qty) → (ItemStack, errorMsg).
    /// Returns null stack and an error string on failure.</param>
    /// <param name="debugLog">Optional debug logger.</param>
    /// <param name="errorMsg">Set if ALL items failed (partial success still returns true).</param>
    /// <returns>True if at least one item was equipped.</returns>
    internal static bool ApplyLoadout(
        EntityAgent entity,
        ProfessionLoadout loadout,
        System.Func<string, int, (ItemStack stack, string error)> resolveStack,
        System.Action<string> debugLog,
        out string errorMsg)
    {
        errorMsg = null;
        int equipped = 0;
        int failed = 0;

        foreach (var (slotName, itemCode, qty) in loadout.Items)
        {
            var (stack, resolveError) = resolveStack(itemCode, qty);
            if (stack == null)
            {
                debugLog?.Invoke($"[polis] profession: failed to resolve {itemCode}: {resolveError}");
                failed++;
                continue;
            }

            ItemSlot slot = ResolveSlot(entity, slotName, debugLog);
            if (slot == null)
            {
                debugLog?.Invoke($"[polis] profession: failed to resolve slot {slotName}");
                failed++;
                continue;
            }

            slot.Itemstack = stack;
            slot.MarkDirty();
            equipped++;
            debugLog?.Invoke($"[polis] profession: equipped {itemCode} x{qty} in {slotName}");
        }

        PolisInventoryHelpers.StoreSeraphInventory(entity);

        if (equipped == 0 && failed > 0)
        {
            errorMsg = $"Failed to equip any items for profession {loadout.Name}";
            return false;
        }

        return true;
    }

    static ItemSlot ResolveSlot(EntityAgent entity, string slotName, System.Action<string> debugLog)
    {
        switch (slotName)
        {
            case "righthand":
                return entity.RightHandItemSlot;
            case "lefthand":
                return entity.LeftHandItemSlot;
            case "backpack0":
            case "backpack1":
                return PolisInventoryHelpers.BackpackSlot(entity, slotName == "backpack0" ? 0 : 1);
            default:
                return null;
        }
    }
}
