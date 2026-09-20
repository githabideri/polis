# Mount vs Player Movement Research Findings

**Date:** 2026-01-06
**Researcher:** Codex
**Task:** TASK-mount-movement-research.md

---

## Summary

Player movement in Vintage Story is driven by physics modules that consume `EntityControls.WalkVector` and apply acceleration/drag differently per state (ground/air/liquid), yielding responsive start/stop. Mount movement in rideable systems (as seen in Jaunt) is gait-driven with smooth interpolation and yaw-based turning; this produces the vehicular feel and tilt when turning. Because possession uses the mounting system, control inputs are routed through rideable behavior (or seat motion), and you end up with mount-style smoothing and rotation rather than player physics.

The practical path to player-like movement is to bypass or override rideable movement: use player physics modules on the NPC and apply `WalkVector` via standard `EntityAgent` controls, while avoiding gait/seat motion logic and mount angle modes that introduce smoothing/tilt.

---

## btca Query 1: Player Movement Mechanics

### Query
```
btca ask "How does player movement work in Vintage Story? I need to understand:
1. The physics/movement system for player entities (acceleration, deceleration, friction)
2. How player movement differs from entity movement
3. Whether players use EntityControls.CalcMovementVectors() or a different system
4. What gives player movement its responsive, discrete feel (vs smooth vehicular movement)
5. How movement start/stop is handled (does it use animation-driven movement?)

Context: Building NPC possession system where possessed NPC should move exactly like the player does, not like riding a horse.

Please provide code references, class names, and specific mechanisms."
```

### Results
```
Based on my analysis of the Vintage Story API code, here's how player movement works:

## 1. Physics/Movement System for Player Entities

Player movement uses a modular physics system with different physics modules (PModule classes) that handle different states:

Key Modules:
- PModuleOnGround - Handles ground movement with acceleration/deceleration
- PModulePlayerInAir - Air movement with reduced control
- PModulePlayerInLiquid - Swimming physics
- PModuleMotionDrag - Applies drag forces

Ground Movement Physics (PModuleOnGround.cs):

motionDeltaX += (walkX - motionDeltaX) * belowBlockDragMultiplier;
motionDeltaZ += (walkZ - motionDeltaZ) * belowBlockDragMultiplier;
motion.Add(motionDeltaX, 0, motionDeltaZ);

motion.X *= groundDrag; // groundDrag = 1 - groundDragFactor (typically 0.7)
motion.Z *= groundDrag;

## 2. Player vs Regular Entity Movement Differences

Player-Specific Features:
- PModulePlayerInAir reduces air control by 75% (airMovingStrengthFalling = AirMovingStrength / 4)
- Enhanced liquid physics with swimming push system
- Walk speed modifiers from stats/armor: entity.Stats.GetBlended("walkspeed")
- Sneak/sprint multipliers

Regular Entities use PModuleInAir with full air control.

## 3. EntityControls.CalcMovementVectors() Usage

YES - players use EntityControls.CalcMovementVectors():

public virtual void CalcMovementVectors(EntityPos pos, float dt)
{
    double moveSpeed = dt * GlobalConstants.BaseMoveSpeed * MovespeedMultiplier * GlobalConstants.OverallSpeedMultiplier;
    double dz = (Forward ? moveSpeed : 0) + (Backward ? -moveSpeed : 0);
    double dx = (Right ? -moveSpeed : 0) + (Left ? moveSpeed : 0);
    WalkVector.Set(dx * cosYaw - dz * sinYaw, 0, dx * sinYaw + dz * cosYaw);
    double normalization = (Forward || Backward) && (Right || Left) ? 1 / Math.Sqrt(2) : 1;
    WalkVector.Mul(normalization);
}

## 4. Responsive, Discrete Feel Sources

What creates player responsiveness:
- Frame-based physics accumulation (1/60s timesteps)
- Immediate response: motionDeltaX/Z accelerates toward target speed
- Block drag multipliers (ice vs stone)
- State-based modules (ground/air/liquid)
- Coyote time 0.15s

## 5. Movement Start/Stop Handling

NOT animation-driven, physics-driven. Animations follow movement state.
```

### Key Findings
- Player movement is handled by physics modules (`PModuleOnGround`, `PModulePlayerInAir`, `PModulePlayerInLiquid`) that consume `EntityControls.WalkVector` and apply drag/acceleration per tick.
- `EntityControls.CalcMovementVectors()` is used by players; responsiveness comes from physics modules and drag/accel values rather than from the input vector itself.
- Movement start/stop is physics-based; animation is triggered by control state, not vice versa.

---

## btca Query 2: Mount/Animal Movement Mechanics

### Query
```
btca ask "How does mount/rideable entity movement work in Vintage Story (e.g., horses)? I need to understand:
1. The movement physics for rideable entities
2. Why mounts have smooth, vehicular movement (vs bipedal player movement)
3. What causes the tilting behavior when turning in curves
4. How EntityBehaviorRideable controls mounted entity movement
5. The relationship between rider controls and mount motion

Context: NPC possession uses mounting system (IMountableSeat) but we're getting horse-like movement instead of player-like movement.

Please provide code references and examples from vanilla rideable entities."
```

### Results
```
Based on my analysis of the Jaunt mod's rideable system, I can now explain how mount/rideable entity movement works in Vintage Story and why you're getting horse-like movement instead of player-like movement for NPC possession:

## 1. Movement Physics for Rideable Entities

Mount movement uses a gait-based system rather than direct player control:

public override Vec2d SeatsToMotion(float dt)
{
    double linearMotion = 0;
    double angularMotion = 0;

    if (ebg.IsForward || ebg.IsBackward)
    {
        float dir = ebg.IsForward ? 1 : -1;
        linearMotion += str * dir * dt * 2f;
    }

    return new Vec2d(linearMotion, angularMotion);
}

## 2. Why Mounts Have Smooth, Vehicular Movement

Mounts use predefined gaits with fixed speed multipliers:

public record JauntGaitMeta : GaitMeta
{
    public double MoveSpeed { get; set; }
    public double? DragFactor { get; set; }
    public float YawMultiplier { get; set; }
}

## 3. Tilting Behavior When Turning

Tilting comes from yaw/angle update and angular velocity:

entity.SidedPos.Yaw += (float)motion.Y * dt * 30f;
AngularVelocity = ebg.CurrentJauntGait.YawMultiplier * motion.Y * 1.5;

## 4. EntityBehaviorRideable Controls Movement

Control flow is SeatsToMotion -> updateAngleAndMotion -> Move.

## 5. Rider Controls to Mount Motion Relationship

Rider controls are mapped through seat system, but motion derives from gait system.
```

### Key Findings
- Rideable movement uses gait/seat motion, not player physics modules.
- Smooth feel is from fixed gait speeds plus drag and yaw smoothing.
- Turning/tilt comes from yaw rotation and angular velocity in rideable behavior.
- Even with the same controls, seat-based motion yields mount-like movement.

---

## btca Query 3: EntityControls and Movement Vectors

### Query
```
btca ask -r vsapi -q "How does EntityControls.CalcMovementVectors() work in Vintage Story? I need to understand:
1. What this method does (how it calculates WalkVector from control inputs)
2. Whether it behaves differently for players vs other entities
3. Whether it produces continuous smooth motion or discrete movement
4. If there are alternative movement APIs for bipedal entities
5. How to achieve player-like movement instead of mount-like movement

Context: Using CalcMovementVectors in client prediction for possessed NPC, but getting smooth vehicular motion instead of responsive bipedal motion.

Please provide specific API details and alternatives."
```

### Results
```
Based on my search of the vsapi repository, I can now provide you with comprehensive answers about EntityControls.CalcMovementVectors() and related movement APIs:

## 1. What CalcMovementVectors() Does

public virtual void CalcMovementVectors(EntityPos pos, float dt)
{
    double moveSpeed = dt * GlobalConstants.BaseMoveSpeed * MovespeedMultiplier * GlobalConstants.OverallSpeedMultiplier;
    double dz = (Forward ? moveSpeed : 0) + (Backward ? -moveSpeed : 0);
    double dx = (Right ? -moveSpeed : 0) + (Left ? moveSpeed : 0);
    double cosPitch = Math.Cos(pos.Pitch);
    double sinPitch = Math.Sin(pos.Pitch);
    double cosYaw = Math.Cos(-pos.Yaw);
    double sinYaw = Math.Sin(-pos.Yaw);

    WalkVector.Set(dx * cosYaw - dz * sinYaw, 0, dx * sinYaw + dz * cosYaw);

    double normalization = (Forward || Backward) && (Right || Left) ? 1 / Math.Sqrt(2) : 1;
    WalkVector.Mul(normalization);
}

## 2. Player vs Other Entity Behavior

CalcMovementVectors is generic; differences come from physics modules that consume WalkVector:

public override void ApplyFreeFall(float dt, Entity entity, EntityPos pos, EntityControls controls)
{
    float strength = AirMovingStrength * Math.Min(1, ((EntityPlayer)entity).walkSpeed) * dt * 60;
    if (!controls.Jump)
    {
        strength = airMovingStrengthFalling; // /= 4
        pos.Motion.X *= (float)Math.Pow(0.98f, dt * 33);
        pos.Motion.Z *= (float)Math.Pow(0.98f, dt * 33);
    }
    pos.Motion.Add(controls.WalkVector.X * strength, controls.WalkVector.Y * strength, controls.WalkVector.Z * strength);
}

## 3. Continuous vs Discrete Movement

CalcMovementVectors produces continuous motion using dt. Feel is from ground physics:

motionDeltaX += (walkX - motionDeltaX) * belowBlockDragMultiplier;
motionDeltaZ += (walkZ - motionDeltaZ) * belowBlockDragMultiplier;
motion.Add(motionDeltaX, 0, motionDeltaZ);
motion.X *= groundDrag;
motion.Z *= groundDrag;

## 4. Alternative Movement APIs

- Direct manipulation of pos.Motion
- Player physics modules
- Server-side authoritative position updates

## 5. Achieving Player-like Movement

- Call CalcMovementVectors each frame
- Apply WalkVector to pos.Motion directly
- Use player physics modules and proper drag/interpolation

Walk speed multipliers from EntityAgent.GetWalkSpeedMultiplier.
```

### Key Findings
- `CalcMovementVectors()` just computes the input vector; it is not responsible for smoothing.
- Player feel is created by downstream physics modules and drag/acceleration tuning.
- If mounted movement feels smooth, the issue is likely the rideable motion pipeline, not `CalcMovementVectors()` itself.

---

## btca Query 4: Movement Modes/Systems

### Query
```
btca ask "Are there different movement modes or physics systems in Vintage Story for different entity types? Looking for:
1. Whether there's a 'player movement mode' vs 'mount movement mode'
2. How to switch or select movement behavior
3. Any flags, properties, or configurations that control movement physics
4. EntityBehavior classes that affect movement (besides BehaviorRideable)

Context: Need to make mounted NPC move like player, not like horse.

Please provide code references and configuration options."
```

### Results
```
Based on my analysis of the Vintage Story API code, here are the key findings about movement modes and physics systems:

## 1. Movement Modes vs Entity Types

No distinct "player vs mount" movement modes. Movement is controlled by EntityBehaviors and EntityControls.

public class EntityBehaviorPassivePhysics : PhysicsBehaviorBase, IPhysicsTickable, IRemotePhysics
{
    private double waterDragValue = GlobalConstants.WaterDrag;
    private double airDragValue = GlobalConstants.AirDragAlways;
    private double groundDragValue = 0.7f;
    private double gravityPerSecond = GlobalConstants.GravityPerSecond;
}

## 2. Movement Control Switching

EntityControls can be transferred between entities when mounting:

public virtual bool TryMount(IMountableSeat onmount)
{
    onmount.Controls.FromInt(Controls.ToInt());
}

protected virtual void doMount(IMountableSeat mountable)
{
    this.MountedOn = mountable;
    controls.StopAllMovement();
}

## 3. Physics Configuration Flags

public virtual void SetProperties(JsonObject attributes)
{
    waterDragValue = 1 - (1 - waterDragValue) * attributes["waterDragFactor"].AsDouble(1);
    airDragValue = 1 - (1 - airDragValue) * attributes["airDragFactor"].AsDouble(1);
    groundDragValue = 0.3 * attributes["groundDragFactor"].AsDouble(1);
    gravityPerSecond *= attributes["gravityFactor"].AsDouble(1);
}

## 4. Key EntityBehavior Classes for Movement

- PhysicsBehaviorBase
- EntityBehaviorPassivePhysics

Mount angle modes are configured on seat:

public enum EnumMountAngleMode { Unaffected, PushYaw, Push, FixateYaw, Fixate }

public class SeatConfig
{
    public bool Controllable;
    public EnumMountAngleMode AngleMode = EnumMountAngleMode.FixateYaw;
}
```

### Key Findings
- Movement behavior is defined by physics behaviors and attributes, not by entity type.
- Mounting transfers controls and can clear movement, but does not change physics modules automatically.
- Seat angle modes and physics attribute factors (drag, gravity) are key knobs.

---

## Analysis

### Player Movement System
Player movement is input-to-`WalkVector` followed by physics modules that apply acceleration and drag on ground, reduced control in air, and specialized liquid behavior. The responsive feel comes from the physics modules and their drag/accel values, not from `CalcMovementVectors()` alone.

### Mount Movement System
Rideable movement (as seen in Jaunt) uses gait-based motion (fixed speed per gait) and angular velocity for turning. This decouples raw input from instantaneous acceleration and introduces smoothing. Yaw updates and angular velocity produce visible tilting during turns.

### Why They Feel Different
Player movement uses physics modules with immediate acceleration and drag tied to block properties, while mounts use gait motion and yaw smoothing. Mounts therefore feel like vehicles: continuous, smoothed, and tilted in turns.

### What Causes Our Issue
Using the mounting system routes movement through rideable/seat motion logic (or equivalent), which applies gait/seat smoothing and angular motion. Even when `CalcMovementVectors()` is used for prediction, the mount pipeline is still in control, producing mount-like feel.

---

## Solutions

### Option 1: Bypass Mounting for Movement (Direct Player Physics)
**Description:** Keep possession for camera/ownership, but do not use mount movement. Feed controls directly into NPC `EntityAgent.Controls` and let standard physics modules handle motion.
**Pros:** Closest to player feel; reuses existing player physics; avoids gait/seat smoothing.
**Cons:** Must re-implement dismount/seat logic for camera or interaction; may need custom networking for control sync.
**Feasibility:** High
**Implementation complexity:** Medium

### Option 2: Custom Rideable Behavior That Mimics Player Physics
**Description:** Replace or override rideable behavior so `SeatsToMotion` and movement step apply player-like acceleration/drag rather than gaits; disable angular velocity tilt and reduce smoothing.
**Pros:** Retains mounting system; integrates with existing seat flow.
**Cons:** More invasive; risk of conflicts with other rideable logic; requires careful tuning.
**Feasibility:** Medium
**Implementation complexity:** High

### Option 3: Tune Physics Attributes + Seat Angle Mode
**Description:** Keep mount system but adjust drag/gravity attributes on NPC to match player, and set `SeatConfig.AngleMode` to `Unaffected` or `PushYaw` to reduce forced yaw/tilt.
**Pros:** Minimal change; quick test.
**Cons:** Likely insufficient alone; does not remove gait smoothing.
**Feasibility:** Medium
**Implementation complexity:** Low

### Recommended Approach
Option 1 is most reliable for player-like movement: it keeps player physics intact and avoids rideable smoothing entirely. If you must keep the mounting system, Option 2 is viable but higher effort; Option 3 is a quick diagnostic step but unlikely to fix the feel completely.

---

## Code References

- `Common/Entity/EntityControls.cs` (`CalcMovementVectors`)
- `Common/Entity/EntityAgent.cs` (`TryMount`, `doMount`, `GetWalkSpeedMultiplier`)
- `Common/Entity/Physics/Normal/PModuleOnGround.cs`
- `Common/Entity/Physics/Player/PModulePlayerInAir.cs`
- `Common/EntityBehavior/BehaviorPassivePhysics.cs`
- `Common/IMountableSeat.cs` (`SeatConfig`, `EnumMountAngleMode`)
- `jaunt/EntityBehaviorJauntRideable.cs`
- `jaunt/EntityBehaviorJauntGait.cs`
- `jaunt/EntityJauntRideableSeat.cs`

---

## Implementation Notes

- If you bypass mounting for movement, keep the mount seat for camera/possession but do not route controls into seat motion. Apply controls directly to the NPC's `EntityAgent.Controls` and let physics modules update motion.
- If you keep rideable behavior, override seat motion to use player-like acceleration and remove yaw/tilt effects (angular velocity).
- If you use attribute tuning, align `groundDragFactor`, `airDragFactor`, `waterDragFactor`, and `gravityFactor` with player defaults and set `SeatConfig.AngleMode` to avoid forced rotation.
- Testing: compare motion start/stop curves and turn response against a player in identical terrain; log `WalkVector`, `pos.Motion`, and drag factors per tick.

---

## Open Questions

- How much of the horse-like feel comes from mount animation blending rather than physics? (Need engine-side confirmation.)
- Are there vanilla rideable entities (outside Jaunt) whose behavior can be inspected for closer-to-player movement? (If yes, check vssurvivalmod or engine code.)
- Does the server-side possession routing introduce additional smoothing beyond client prediction?
