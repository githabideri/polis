using System;
using Vintagestory.API.Common;
using Vintagestory.API.Common.Entities;
using Vintagestory.API.MathTools;
using Vintagestory.GameContent;
using Polis.Helpers;

namespace Polis.Actions.Inventory;

public class PolisDropItemAction : EntityActionBase
{
    private int slotIndex;
    private int quantity;
    private bool done;
    private Action<string> debugLog;
    private Action<bool, string> resultCallback;

    public override string Type => "polis-dropitem";

    /// <summary>
    /// Creates a drop action.
    /// </summary>
    /// <param name="vas">The activity system</param>
    /// <param name="slotIndex">Inventory slot index to drop from (-1 for active hand)</param>
    /// <param name="quantity">Number of items to drop (0 for entire stack)</param>
    /// <param name="debugLog">Optional debug logger</param>
    /// <param name="resultCallback">Optional callback for action result (ok, message)</param>
    public PolisDropItemAction(EntityActivitySystem vas, int slotIndex, int quantity, Action<string> debugLog = null, Action<bool, string> resultCallback = null)
    {
        this.vas = vas;
        this.slotIndex = slotIndex;
        this.quantity = quantity;
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

        // Get the slot to drop from
        // For now, only support hand slots: -1 or 0 = right hand, 1 = left hand
        ItemSlot slot;
        string slotName;
        if (slotIndex <= 0)
        {
            // Right hand (default)
            slot = agent.RightHandItemSlot;
            slotName = "right hand";
            if ((slot == null || slot.Empty) && slotIndex < 0)
            {
                // If -1 (auto) and right hand empty, try left hand
                slot = agent.LeftHandItemSlot;
                slotName = "left hand";
            }
        }
        else if (slotIndex == 1)
        {
            // Left hand
            slot = agent.LeftHandItemSlot;
            slotName = "left hand";
        }
        else
        {
            // Future: support backpack slots via GearInventory
            Fail($"slot index {slotIndex} not supported (use 0=right, 1=left, or -1=auto)");
            return;
        }

        if (slot == null || slot.Empty)
        {
            Fail($"{slotName} is empty");
            return;
        }

        var stack = slot.Itemstack;
        string itemCode = stack.Collectible?.Code?.ToString() ?? "unknown";
        int available = stack.StackSize;

        // Determine how many to drop
        int toDrop = (quantity <= 0 || quantity > available) ? available : quantity;

        debugLog?.Invoke($"[drop] dropping {toDrop}x {itemCode} from {slotName}");

        // Create the stack to spawn
        var dropStack = stack.Clone();
        dropStack.StackSize = toDrop;

        // Remove from inventory
        if (toDrop >= available)
        {
            slot.Itemstack = null;
        }
        else
        {
            slot.Itemstack.StackSize -= toDrop;
        }
        slot.MarkDirty();
        PolisInventoryHelpers.StoreSeraphInventory(agent);

        // Spawn the item entity at bot's position with slight upward velocity
        var dropPos = agent.ServerPos.XYZ.AddCopy(0, 0.5, 0);
        var velocity = new Vec3d(
            (world.Rand.NextDouble() - 0.5) * 0.1,
            0.2,
            (world.Rand.NextDouble() - 0.5) * 0.1
        );

        var spawnedEntity = world.SpawnItemEntity(dropStack, dropPos, velocity);

        if (spawnedEntity == null)
        {
            // Spawn failed - this is rare but can happen
            // Note: inventory was already modified, so item is lost - this is a known edge case
            debugLog?.Invoke($"[drop] warning: SpawnItemEntity returned null, item may be lost");
            Fail($"failed to spawn {toDrop}x {itemCode} (item removed from inventory but not spawned)");
            return;
        }

        debugLog?.Invoke($"[drop] success: spawned {toDrop}x {itemCode} at {FormatVec(dropPos)} entityId={spawnedEntity.EntityId}");
        Succeed($"dropped {toDrop}x {itemCode}");
    }

    void Fail(string reason)
    {
        debugLog?.Invoke($"[drop] failed: {reason}");
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
        return new PolisDropItemAction(vas, slotIndex, quantity, debugLog, resultCallback);
    }

    static string FormatVec(Vec3d vec)
    {
        if (vec == null) return "null";
        return string.Format(System.Globalization.CultureInfo.InvariantCulture, "{0:0.00},{1:0.00},{2:0.00}", vec.X, vec.Y, vec.Z);
    }
}
