using System;
using Vintagestory.API.Common;
using Vintagestory.API.Common.Entities;
using Vintagestory.API.MathTools;
using Vintagestory.GameContent;
using PolisBuilderNpc.Helpers;

namespace PolisBuilderNpc.Actions.Inventory;

public class PolisPickupItemAction : EntityActionBase
{
    private long targetEntityId;
    private float range;
    private bool done;
    private Action<string> debugLog;
    private Action<bool, string> resultCallback;

    // CanCollect retry state (VS spawn protection is ~1s)
    private EntityAgent agent;
    private bool awaitingCanCollect;
    private float canCollectWaitTime;
    private const float CAN_COLLECT_TIMEOUT = 1.5f;

    public override string Type => "polis-pickupitem";

    public PolisPickupItemAction(EntityActivitySystem vas, long targetEntityId, float range, Action<string> debugLog = null, Action<bool, string> resultCallback = null)
    {
        this.vas = vas;
        this.targetEntityId = targetEntityId;
        this.range = range;
        this.debugLog = debugLog;
        this.resultCallback = resultCallback;
    }

    public override void Start(EntityActivity activity)
    {
        agent = vas?.Entity as EntityAgent;
        if (agent == null)
        {
            Fail("actor is not an agent");
            return;
        }

        var target = vas?.Entity?.World?.GetEntityById(targetEntityId);
        if (target == null)
        {
            Fail($"target entity {targetEntityId} not found");
            return;
        }

        var itemEntity = target as EntityItem;
        if (itemEntity == null)
        {
            Fail($"target {targetEntityId} is not an EntityItem (is {target.GetType().Name})");
            return;
        }

        var targetPos = target.ServerPos?.XYZ;
        if (targetPos == null)
        {
            Fail("target position missing");
            return;
        }

        var dist = agent.ServerPos.XYZ.DistanceTo(targetPos);
        if (dist > range)
        {
            Fail($"out of range dist={dist:0.00} range={range:0.00}");
            return;
        }

        // Check if item can be collected (VS spawn protection ~1s)
        if (!itemEntity.CanCollect(agent))
        {
            // Item not yet collectible - wait and retry in OnTick
            awaitingCanCollect = true;
            canCollectWaitTime = 0f;
            debugLog?.Invoke($"[pickup] waiting for CanCollect on entity {targetEntityId}");
            return;  // Don't set done=true, let OnTick handle it
        }

        // Item is collectible - perform pickup immediately
        PerformPickup(itemEntity);
    }

    void PerformPickup(EntityItem itemEntity)
    {
        var stack = itemEntity.Itemstack;
        if (stack == null || stack.StackSize <= 0)
        {
            Fail("item has no stack");
            return;
        }

        int originalSize = stack.StackSize;
        string itemCode = stack.Collectible?.Code?.ToString() ?? "unknown";

        debugLog?.Invoke($"[pickup] attempting: {itemCode} x{originalSize} from entity {targetEntityId}");

        if (!PolisInventoryHelpers.TryInsertIntoBotInventory(agent, stack, out int pickedUp, out string insertError, debugLog))
        {
            Fail(insertError ?? "inventory full, nothing transferred");
            return;
        }

        int remaining = originalSize - pickedUp;

        if (remaining <= 0)
        {
            // Fully picked up - despawn the item entity
            debugLog?.Invoke($"[pickup] success: picked up {pickedUp}x {itemCode}, despawning entity");
            itemEntity.Die(EnumDespawnReason.PickedUp, null);
            Succeed($"picked {pickedUp}x {itemCode} from #{targetEntityId}");
        }
        else
        {
            // Partial pickup - update the item entity's stack
            debugLog?.Invoke($"[pickup] partial: picked up {pickedUp}x {itemCode}, {remaining} remaining");
            itemEntity.Itemstack.StackSize = remaining;
            itemEntity.WatchedAttributes.MarkPathDirty("itemstack");
            Succeed($"picked {pickedUp}x {itemCode} (partial, {remaining} left) from #{targetEntityId}");
        }
    }

    void Fail(string reason)
    {
        debugLog?.Invoke($"[pickup] failed: {reason}");
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

    public override void OnTick(float dt)
    {
        if (done) return;

        if (awaitingCanCollect)
        {
            canCollectWaitTime += dt;

            // Timeout check
            if (canCollectWaitTime >= CAN_COLLECT_TIMEOUT)
            {
                Fail($"CanCollect timeout after {CAN_COLLECT_TIMEOUT:F1}s for entity {targetEntityId}");
                return;
            }

            // Re-check CanCollect
            var itemEntity = agent.World.GetEntityById(targetEntityId) as EntityItem;
            if (itemEntity == null || !itemEntity.Alive)
            {
                Fail($"Item entity {targetEntityId} no longer exists");
                return;
            }

            if (itemEntity.CanCollect(agent))
            {
                debugLog?.Invoke($"[pickup] CanCollect now true after {canCollectWaitTime:F2}s");
                awaitingCanCollect = false;
                PerformPickup(itemEntity);
            }
        }
    }

    public override void Cancel()
    {
        done = true;
    }

    public override IEntityAction Clone()
    {
        return new PolisPickupItemAction(vas, targetEntityId, range, debugLog, resultCallback);
    }
}
