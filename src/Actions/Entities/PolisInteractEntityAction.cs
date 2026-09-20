using System;
using Vintagestory.API.Common;
using Vintagestory.API.Common.Entities;
using Vintagestory.API.MathTools;
using Vintagestory.GameContent;

namespace PolisBuilderNpc.Actions.Entities;

public class PolisInteractEntityAction : EntityActionBase
{
    private long targetEntityId;
    private Vec3d hitPos;
    private EnumInteractMode mode;
    private float range;
    private bool done;
    private Action<string> debugLog;
    private Action<bool, string> resultCallback;

    public override string Type => "polis-interactentity";

    public PolisInteractEntityAction(EntityActivitySystem vas, long targetEntityId, Vec3d hitPos, EnumInteractMode mode, float range, Action<string> debugLog = null, Action<bool, string> resultCallback = null)
    {
        this.vas = vas;
        this.targetEntityId = targetEntityId;
        this.hitPos = hitPos?.Clone();
        this.mode = mode;
        this.range = range;
        this.debugLog = debugLog;
        this.resultCallback = resultCallback;
    }

    public override void Start(EntityActivity activity)
    {
        // Safety check: ensure the actor is an agent
        var agent = vas?.Entity as EntityAgent;
        if (agent == null)
        {
            Fail("actor is not an agent");
            return;
        }

        // Find the target entity
        var target = vas?.Entity?.World?.GetEntityById(targetEntityId);
        if (target == null)
        {
            Fail($"target entity {targetEntityId} not found (loaded?)");
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

        var useHitPos = NormalizeHitPos(target, hitPos, debugLog) ?? GetDefaultRelativeHitPos(target);

        var slot = agent.ActiveHandItemSlot;
        if (slot == null)
        {
            Fail("ActiveHandItemSlot is null");
            return;
        }

        int beforeHurt = mode == EnumInteractMode.Attack ? target.WatchedAttributes.GetInt("onHurtCounter") : 0;
        float? beforeHealth = mode == EnumInteractMode.Attack ? target.GetBehavior<EntityBehaviorHealth>()?.Health : null;

        debugLog?.Invoke($"[interact] target={target.Code} id={targetEntityId} mode={mode} item={slot.Itemstack?.Collectible?.Code} hitRel={FormatVec(useHitPos)}");

        // Perform the interaction
        target.OnInteract(agent, slot, useHitPos, mode);

        if (mode == EnumInteractMode.Attack)
        {
            int afterHurt = target.WatchedAttributes.GetInt("onHurtCounter");
            float? afterHealth = target.GetBehavior<EntityBehaviorHealth>()?.Health;
            debugLog?.Invoke($"[interact] attack result hurt={beforeHurt}->{afterHurt} health={FormatNum(beforeHealth)}->{FormatNum(afterHealth)}");

            // Verify attack had an effect by checking if hurtCounter or health changed
            bool hurtCounterChanged = afterHurt != beforeHurt;
            bool healthChanged = beforeHealth.HasValue && afterHealth.HasValue && Math.Abs(afterHealth.Value - beforeHealth.Value) > 0.001f;
            bool entityDied = !target.Alive;

            if (!hurtCounterChanged && !healthChanged && !entityDied)
            {
                // Attack had no observable effect
                Fail($"attack on {target.Code} had no effect (invulnerable, out of reach, or already dead)");
            }
            else
            {
                Succeed($"attacked {target.Code} (hurt={beforeHurt}->{afterHurt})");
            }
        }
        else
        {
            // For non-attack interactions, we can't easily verify success
            // Report success but with indication that effect is unverified
            Succeed($"interacted with {target.Code}");
        }
    }

    void Fail(string reason)
    {
        debugLog?.Invoke($"[interact] failed: {reason}");
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
        return new PolisInteractEntityAction(vas, targetEntityId, hitPos?.Clone(), mode, range, debugLog, resultCallback);
    }

    static Vec3d NormalizeHitPos(Entity target, Vec3d hitPos, Action<string> debugLog)
    {
        if (hitPos == null || target == null) return hitPos?.Clone();

        var targetPos = target.ServerPos?.XYZ ?? target.Pos?.XYZ;
        if (targetPos == null) return hitPos.Clone();

        var dist = hitPos.DistanceTo(targetPos);
        if (dist <= 2.5)
        {
            // HitPosition likely in world space, convert to relative.
            var rel = hitPos.SubCopy(targetPos.X, targetPos.Y, targetPos.Z);
            debugLog?.Invoke($"[interact] hitpos world->rel dist={dist:0.00} rel={FormatVec(rel)}");
            return rel;
        }

        return hitPos.Clone();
    }

    static Vec3d GetDefaultRelativeHitPos(Entity target)
    {
        var selBox = target?.SelectionBox;
        if (selBox == null) return new Vec3d(0, 0.5, 0);

        return new Vec3d(
            (selBox.X1 + selBox.X2) / 2.0,
            (selBox.Y1 + selBox.Y2) / 2.0,
            (selBox.Z1 + selBox.Z2) / 2.0
        );
    }

    static string FormatVec(Vec3d vec)
    {
        if (vec == null) return "null";
        return string.Format(System.Globalization.CultureInfo.InvariantCulture, "{0:0.00},{1:0.00},{2:0.00}", vec.X, vec.Y, vec.Z);
    }

    static string FormatNum(float? value)
    {
        if (value == null) return "?";
        return value.Value.ToString("0.00", System.Globalization.CultureInfo.InvariantCulture);
    }
}
