using System;
using Vintagestory.API.Common;
using Vintagestory.API.Common.Entities;
using Vintagestory.API.MathTools;
using Vintagestory.GameContent;
using Polis.Actions.Navigation;
using Polis.Helpers;

namespace Polis.Actions.Inventory;

/// <summary>
/// Pick up a loose ground item. Self-approach (2026-11-03): when the
/// item is out of range the action does not hard-fail anymore - it
/// walks to the item first (a nested PolisGotoAction, loop-level
/// form: walk-to-item, then pick) and re-resolves the item's
/// position on arrival, because loose items roll while you walk to
/// them. Bounded: MAX_APPROACH_ATTEMPTS re-targets, and each attempt
/// is the goto's own bounded ladder (15 s phases, stuck repaths,
/// watchdog - it cannot hang).
///
/// The nested goto is a helper object, not a second registered
/// action: the 1.22 EntityActivitySystem ticks the entity's
/// traversers in its own OnTick (decompiled: linepath/wppath
/// OnGameTick run before the active activity is ticked), so the
/// child only needs its Start (to issue the navigation) and its
/// OnTick (watchdog + stuck ladder), both driven by this action.
/// </summary>
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

    // Self-approach state.
    private PolisGotoAction approach;
    private bool inApproach;
    private int approachAttempts;
    private const int MAX_APPROACH_ATTEMPTS = 2;
    private string approachResult = "";

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
            // Durable path: walk to it, then pick (was a hard Fail).
            StartApproach(itemEntity, (float)dist);
            return;
        }

        BeginCollect(itemEntity);
    }

    /// <summary>
    /// Kick off one approach attempt: a nested goto to the item's cell.
    /// The goto resolves the cell to a standable feet level itself
    /// (PolisAStar GetTargetPos) and runs its full bounded ladder.
    /// </summary>
    void StartApproach(EntityItem itemEntity, float dist)
    {
        if (approachAttempts >= MAX_APPROACH_ATTEMPTS)
        {
            Fail($"out of range after {approachAttempts} approaches (dist={dist:0.00} range={range:0.00})");
            return;
        }
        approachAttempts++;
        approachResult = "";

        var p = itemEntity.ServerPos.XYZ;
        var cell = new Vec3d(p.X, p.Y, p.Z); // the item's cell; the goto walks there
        approach = new PolisGotoAction(
            vas,
            cell,
            true,                       // A*
            "walk",
            0.02f,                      // walk speed (same as the harness goto)
            1.5f,                       // anim speed
            debugLog,
            null,                       // no path highlight
            false,                      // debug off
            true,                       // allowFallback: a straight-line walk still lands in range
            (ok, msg) => approachResult = (ok ? "ok:" : "fail:") + msg,
            true,                       // usePolisAStar (fence/door aware)
            true,                       // openDoors
            false                       // closeDoors
        );
        approach.Start(null); // helper object: this action drives its OnTick
        inApproach = true;
        debugLog?.Invoke($"[pickup] out of range (dist={dist:0.00} range={range:0.00}) - self-approach {approachAttempts}/{MAX_APPROACH_ATTEMPTS} to {PolisSystem.FormatPos(cell)}");
    }

    /// <summary>
    /// In range: the collect sequence (CanCollect wait + pickup).
    /// </summary>
    void BeginCollect(EntityItem itemEntity)
    {
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
        if (done) return;
        StopMovement();
        debugLog?.Invoke($"[pickup] failed: {reason}");
        resultCallback?.Invoke(false, reason);
        ExecutionHasFailed = true;
        done = true;
    }

    void Succeed(string msg)
    {
        if (done) return;
        StopMovement();
        resultCallback?.Invoke(true, msg);
        done = true;
    }

    /// <summary>
    /// Belt and braces: whatever phase ended the action, the entity's
    /// traversers and controls are left stopped (the goto already does
    /// this on its own paths; a parent-level stop covers the rest).
    /// </summary>
    void StopMovement()
    {
        approach?.Finish();
        inApproach = false;
        vas?.linepathTraverser?.Stop();
        vas?.wppathTraverser?.Stop();
        agent?.Controls?.StopAllMovement();
    }

    public override bool IsFinished()
    {
        return done;
    }

    public override void OnTick(float dt)
    {
        if (done) return;

        if (inApproach)
        {
            // Drive the nested goto's watchdog + stuck ladder. The
            // actual walking is the entity's traverser, which the
            // activity system ticks independently of actions.
            approach.OnTick(dt);
            if (!approach.IsFinished()) return;
            inApproach = false;

            // Re-resolve: loose items roll while we walked to them.
            var item = vas?.Entity?.World?.GetEntityById(targetEntityId) as EntityItem;
            if (item == null || !item.Alive)
            {
                Fail($"item {targetEntityId} gone after approach ({approachResult})");
                return;
            }
            var pos = item.ServerPos?.XYZ;
            if (pos == null)
            {
                Fail($"target position missing after approach ({approachResult})");
                return;
            }
            var dist = agent.ServerPos.XYZ.DistanceTo(pos);
            if (dist <= range)
            {
                debugLog?.Invoke($"[pickup] arrived, dist={dist:0.00} - collecting ({approachResult})");
                BeginCollect(item);
                return;
            }
            // Still short (the item rolled during the walk): one more
            // approach to the new position, then an honest fail.
            debugLog?.Invoke($"[pickup] item moved, dist={dist:0.00} after approach ({approachResult}) - re-approach");
            StartApproach(item, (float)dist);
        }

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
        StopMovement();
    }

    public override IEntityAction Clone()
    {
        return new PolisPickupItemAction(vas, targetEntityId, range, debugLog, resultCallback);
    }
}
