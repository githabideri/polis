# Camera Positioning Research Findings

**Date:** 2026-01-06
**Researcher:** Codex CLI
**Task:** TASK-camera-positioning-research.md

---

## Summary

The Vintage Story API positions first-person camera by combining the entity world position with a local eye offset and an optional camera offset. For player entities, eye height derives from `EntityProperties.EyeHeight` and is adjusted for crouch/sit/death state; when mounted, the rider's `LocalEyePos` is overridden with the mount seat's `LocalEyePos`. The `IMountableSeat` interface exposes `LocalEyePos`, and `SeatConfig` provides `EyeHeight`/`EyeOffsetX` parameters to drive that value. There are no separate high-level camera utilities beyond these properties, but `EntityPlayer.CameraPos` and `CameraPosOffset` are used client-side for special effects.

The immediate implication for NPC possession via mounting is that the seat's `LocalEyePos` (and/or `SeatConfig.EyeHeight`) should be tuned to the NPC's eye position, or the NPC's `EntityProperties.EyeHeight` should be updated if the mount is delegating to entity properties. For immersive FP, the player uses the animation attachment point "Eyes" which may be a separate advanced path.

---

## btca Query 1: Player Camera Positioning

### Query
```
btca ask -r vsapi -q "In the Vintage Story API and game code, how is the first-person camera positioned for player entities? I need to understand:
1. The exact attachment point (entity position, head offset, eye position)
2. Any offset calculations used for first-person view
3. How camera positioning differs between first-person and third-person
4. Any relevant classes, methods, or properties that control camera position

Context: Building a mod where player can possess NPC entities (via mounting), and need the camera positioned correctly at NPC eye level for first-person view. Currently camera is centered inside head geometry.

Please provide specific code references, class names, and method signatures."
```

### Results
```
Based on my analysis of the Vintage Story API code, here's how the first-person camera positioning works for player entities:

## First-Person Camera Positioning in Vintage Story

### 1. Exact Attachment Point

The camera position is calculated using this formula:

```csharp
// Final camera position for first-person view
Vec3d cameraPosition = entity.Pos.XYZ.Add(entity.LocalEyePos).Add(entity.CameraPosOffset);
```

**Key Components:**
- **Entity Position (`entity.Pos.XYZ`)**: Base world position of the entity
- **Local Eye Position (`entity.LocalEyePos`)**: Local offset from entity center to eye position
- **Camera Position Offset (`entity.CameraPosOffset`)**: Additional offset for special effects

### 2. LocalEyePos Calculation

From `EntityPlayer.cs` lines 496-507 and 505-508:

```csharp
// from: vsapi
// For unmounted entities
LocalEyePos.X = 0;
LocalEyePos.Z = 0;

// For mounted entities - uses mount's eye position
if (MountedOn != null && MountedOn.LocalEyePos != null)
{
    LocalEyePos.Set(MountedOn.LocalEyePos);
}

// Base eye height comes from entity properties
double newEyeheight = Properties.EyeHeight; // EntityProperties.EyeHeight
```

### 3. Eye Height Modifications

The eye height is dynamically adjusted based on state:

```csharp
// from: vsapi (EntityPlayer.cs lines 471-485)
if (controls.FloorSitting)
{
    newEyeheight *= 0.5f;
}
else if ((controls.Sneak || !PrevFrameCanStandUp) && !controls.IsClimbing && !controls.IsFlying)
{
    newEyeheight *= 0.8f;
}
else if (!Alive)
{
    newEyeheight *= 0.25f;
}
```

### 4. Mount-Based Camera Positioning

For mounted entities, the camera uses the mount's `LocalEyePos` property:

```csharp
// from: vsapi (IMountableSeat.cs line 194-196)
/// <summary>
/// Where to place the first person camera
/// </summary>
Vec3f LocalEyePos { get; }
```

And from `SeatConfig.cs` lines 84-86:
```csharp
public float EyeHeight = 1.5f;
public float EyeOffsetX = 0f;
```

### 5. First-Person vs Third-Person Differences

**First-Person:**
- Uses `entity.LocalEyePos` for camera positioning
- In immersive mode (`player.ImmersiveFpMode`), uses attachment point "Eyes" from animation system
- Camera positioned at: `entity.Pos.XYZ + LocalEyePos`

**Third-Person:**
- Camera positioned behind/above the entity using different calculations
- Not affected by `LocalEyePos` in the same way

### 6. Immersive First-Person Mode

When immersive FP mode is enabled:

```csharp
// from: vsapi (EntityPlayer.cs lines 742-762)
AttachmentPointAndPose apap = AnimManager.Animator.GetAttachmentPointPose("Eyes");
// Complex matrix calculations determine exact eye position based on animation
```

## For Your NPC Possession Mod

To fix camera positioning when possessing NPCs:

1. **Set the mount's LocalEyePos correctly** on your `IMountableSeat` implementation:

```csharp
public Vec3f LocalEyePos => new Vec3f(0f, npcEyeHeight, 0f);
```

2. **Configure SeatConfig** with appropriate eye height:
```csharp
var seatConfig = new SeatConfig {
    EyeHeight = yourNpcEyeHeight,  // Set this to match NPC's actual eye level
    EyeOffsetX = 0f
};
```

3. **Optionally override Entity.LocalEyePos** on your NPC entity if needed:
```csharp
public override Vec3d LocalEyePos { 
    get { return new Vec3d(0, yourCustomEyeHeight, 0); }
    set { base.LocalEyePos = value; }
}
```

The key is ensuring the `LocalEyePos` property returns the correct offset from the entity's center to where you want the camera positioned for first-person view.
```

### Key Findings
- Camera position is computed as `entity.Pos.XYZ + entity.LocalEyePos + entity.CameraPosOffset`.
- `EntityPlayer.updateEyeHeight()` adjusts `LocalEyePos` based on crouch/sit/death and mounts.
- Mounts override the rider `LocalEyePos` via `IMountableSeat.LocalEyePos`.
- `SeatConfig.EyeHeight` and `EyeOffsetX` are the seat-level inputs.
- Immersive FP uses attachment point `Eyes` from the animator.

---

## btca Query 2: Mount Camera Positioning

### Query
```
btca ask -r vsapi -q "In Vintage Story, how is the rider camera positioned when mounted on an entity (like a horse)? I need to understand:
1. How IMountableSeat controls camera position
2. The calculation for rider eye position on mounted entities
3. Any differences between first-person and third-person camera when mounted
4. Relevant properties or methods in IMountableSeat/IMountable

Context: Implementing NPC possession via mounting system, need to understand how mounts position rider camera.

Please provide code references and examples from vanilla rideable entities."
```

### Results
```
Based on my search through the Vintage Story API, I found the core information about how rider camera positioning works when mounted. Here's what I discovered:

## 1. IMountableSeat Camera Position Control

The `IMountableSeat` interface controls camera position through its properties:

```csharp
// from: vsapi/Common/IMountableSeat.cs
public interface IMountableSeat
{
    /// <summary>
    /// Where to place first person camera
    /// </summary>
    Vec3f LocalEyePos { get; }

    /// <summary>
    /// Exact position of this seat
    /// </summary>
    EntityPos SeatPosition { get; }
}
```

The `LocalEyePos` property is the key for positioning the rider's camera.

## 2. Seat Configuration for Eye Height

The `SeatConfig` class defines the eye positioning parameters:

```csharp
// from: vsapi/Common/IMountableSeat.cs
public class SeatConfig
{
    public float EyeHeight = 1.5f;
    public float EyeOffsetX = 0f;
    public Vec3f MountOffset;
    public Vec3f MountRotation = new Vec3f();
}
```

## 3. Rider Eye Position Calculation

In `EntityPlayer.updateEyeHeight()`, when a player is mounted:

```csharp
// from: vsapi/Common/Entity/EntityPlayer.cs
if (MountedOn != null)
{
    var anim = MountedOn.SuggestedAnimation;
    skipIfpEyePos = anim?.Code == "sleep";
    if (MountedOn.LocalEyePos != null)
    {
        LocalEyePos.Set(MountedOn.LocalEyePos);
    }
}
```

The rider's `LocalEyePos` is overridden by the mount's `LocalEyePos` when mounted.

## 4. Base Entity Eye Position

In the base `Entity` class, eye position is set from entity properties:

```csharp
// from: vsapi/Common/Entity/Entity.cs  
LocalEyePos.Y = Properties.EyeHeight;
```

## 5. Camera Mode Differences

From the camera enum found:

```csharp
// from: vsapi/Client/EnumCameraType.cs
public enum EnumCameraMode
{
    FirstPerson,
    ThirdPerson,
    Overhead
}
```

The camera positioning logic applies to all modes, but first-person uses `LocalEyePos` directly while third-person uses the entity's position + offsets.

## Key Properties for Your NPC Possession System

For implementing NPC possession via mounting, you'll need to configure:

1. **IMountableSeat.LocalEyePos** - Vector3f for exact camera position
2. **SeatConfig.EyeHeight** - Base eye height (default 1.5f)  
3. **SeatConfig.EyeOffsetX** - Horizontal eye offset
4. **SeatConfig.MountOffset** - Overall mount positioning offset
5. **SeatConfig.MountRotation** - Mount rotation angles

The system works by having the mountable entity provide its own `LocalEyePos` that overrides the rider's normal eye position calculation, allowing precise camera control for different mount types like horses, carts, or possessed NPCs.
```

### Key Findings
- `IMountableSeat.LocalEyePos` is the primary camera placement control for riders.
- `SeatConfig` provides `EyeHeight`/`EyeOffsetX` and mount offsets/rotations that feed the seat position and eye point.
- `EntityPlayer.updateEyeHeight()` swaps to mount `LocalEyePos` when mounted.

---

## btca Query 3: Camera Utilities

### Query
```
btca ask -r vsapi -q "Are there any camera positioning utilities, helpers, or standard patterns in the Vintage Story API for calculating eye-level or view position for entities? Looking for:
1. Standard offset calculations for entity eye position
2. Any EntityPos properties related to camera/view
3. Helpers for first-person view positioning
4. How different entity types (player, humanoid, animal) handle camera attachment

Please provide specific API references."
```

### Results
```
Based on my search through the vsapi repository, I found the key camera positioning and eye-level utilities in the Vintage Story API. Here's what I found:

## Camera Positioning API References

### 1. Standard Eye Position Properties

**EntityProperties.EyeHeight** (`// from: vsapi`)
```csharp
/// <summary>
/// How high the camera should be placed if this entity were to be controlled by the player
/// </summary>
public double EyeHeight;
```

**EntityProperties.SwimmingEyeHeight** (`// from: vsapi`)
```csharp
public double SwimmingEyeHeight;
```

**Entity.LocalEyePos** (`// from: vsapi`)
```csharp
/// <summary>
/// The height of the eyes for the given entity.
/// </summary>
public virtual Vec3d LocalEyePos { get; set; } = new Vec3d();
```

### 2. Entity Position Properties for Camera

**EntityPlayer.CameraPos** (`// from: vsapi`)
```csharp
/// <summary>
/// The camera position of player's view. Set only by the game client.
/// </summary>
public Vec3d CameraPos = new Vec3d();
```

**EntityPlayer.CameraPosOffset** (`// from: vsapi`)
```csharp
/// <summary>
/// An offset which can be applied to the camera position to achieve certain special effects or special features, for example Timeswitch feature. Set only by the game client.
/// </summary>
public Vec3d CameraPosOffset = new Vec3d();
```

### 3. Eye Submersion Detection

**EntityAgent.IsEyesSubmerged()** (`// from: vsapi`)
```csharp
/// <summary>
/// Are eyes of this entity submerged in liquid?
/// </summary>
/// <returns></returns>
public bool IsEyesSubmerged()
{
    BlockPos pos = SidedPos.AsBlockPos.Add(0, (float)(Swimming ? Properties.SwimmingEyeHeight : Properties.EyeHeight), 0);
    return World.BlockAccessor.GetBlock(pos).MatterState == EnumMatterState.Liquid;
}
```

### 4. Eye Position Calculation Pattern

From `EntityPlayer.Initialize()` in vsapi:
```csharp
LocalEyePos.Y = Properties.EyeHeight;
```

From `EntityAgent.IsEyesSubmerged()`:
```csharp
BlockPos pos = SidedPos.AsBlockPos.Add(0, (float)(Swimming ? Properties.SwimmingEyeHeight : Properties.EyeHeight), 0);
```

### 5. Dynamic Eye Height Adjustment

**EntityPlayer.updateEyeHeight()** (`// from: vsapi`) shows dynamic eye height calculations:
```csharp
double newEyeheight = Properties.EyeHeight;
double newModelHeight = Properties.CollisionBoxSize.Y;

if (controls.FloorSitting)
{
    newEyeheight *= 0.5f;
    newModelHeight *= 0.55f;
}
else if ((controls.Sneak || !PrevFrameCanStandUp) && !controls.IsClimbing && !controls.IsFlying)
{
    newEyeheight *= 0.8f;
    newModelHeight *= 0.8f;
}
else if (!Alive)
{
    newEyeheight *= 0.25f;
    newModelHeight *= 0.25f;
}
```

## Key Patterns for Different Entity Types

1. **Base Entity**: Uses `Properties.EyeHeight` for standard eye positioning
2. **Player Entity**: Has additional `CameraPos` and `CameraPosOffset` for camera control
3. **Agent Entities**: Can detect eye submersion state using both `EyeHeight` and `SwimmingEyeHeight`
4. **Humanoid Entities**: Inherit eye height behavior from base properties

## Usage Examples

To get eye position for any entity:
```csharp
Vec3d eyePosition = entity.Pos.XYZ.Add(entity.LocalEyePos);
```

To check if eyes are submerged:
```csharp
bool eyesUnderwater = entityAgent.IsEyesSubmerged();
```

For player camera positioning:
```csharp
Vec3d cameraPos = player.CameraPos.Add(player.CameraPosOffset);
```

The API provides these core utilities but does not include higher-level camera helpers - you typically work with the eye height properties directly or use the player's camera position/offset for first-person view calculations.
```

### Key Findings
- Standard eye positioning uses `EntityProperties.EyeHeight` and `Entity.LocalEyePos`.
- Player camera has client-side `CameraPos` and `CameraPosOffset` for special effects.
- `EntityAgent.IsEyesSubmerged()` demonstrates standard eye position calculation.
- No dedicated high-level camera helper API exists beyond these properties.

---

## Analysis

### How Player Camera Works
`EntityPlayer` computes eye height from `EntityProperties.EyeHeight`, adjusts it for crouch/sit/death, and stores it in `LocalEyePos`. First-person camera positioning uses `entity.Pos.XYZ + entity.LocalEyePos + entity.CameraPosOffset`. In immersive FP, the animator attachment point `Eyes` is used to compute a different eye position.

### How Mount Camera Works
When mounted, `EntityPlayer.updateEyeHeight()` checks `MountedOn.LocalEyePos` and copies it into the player's `LocalEyePos`. The mount seat defines `LocalEyePos` (camera placement) and `SeatPosition` (seat transform). `SeatConfig` provides `EyeHeight`, `EyeOffsetX`, and mount transform parameters used by mount implementations.

### Differences & Implications
First-person depends on `LocalEyePos` and thus is sensitive to the seat's eye height, while third-person uses separate offsets and should be unaffected. For possessed NPCs, incorrect eye placement likely means the seat's `LocalEyePos` or `SeatConfig.EyeHeight` doesn't match the NPC model's eye point. Immersive FP may need animator attachment points if the NPC model differs.

---

## Recommendations

### Option 1: Seat Eye Height Tuning
**Description:** Set `IMountableSeat.LocalEyePos` (or `SeatConfig.EyeHeight` + `EyeOffsetX`) to match the NPC model eye position. Keep player camera pipeline unchanged.
**Pros:** Minimal code changes; aligns with VS mount pipeline.
**Cons:** Requires reliable NPC model eye measurement and maintenance.
**Implementation complexity:** Low

### Option 2: Override NPC LocalEyePos
**Description:** Override the NPC entity's `LocalEyePos` (or `EntityProperties.EyeHeight`) for possession mode, then use mount to copy that value.
**Pros:** Centralizes eye calculation on the NPC entity; easier to reuse for other systems.
**Cons:** Requires careful sync with mount behavior and state transitions.
**Implementation complexity:** Medium

### Recommended Approach
Start with Option 1: tune the seat `LocalEyePos`/`SeatConfig.EyeHeight` to the NPC model eye position, since the mount pipeline is clearly designed to override rider `LocalEyePos` and should fix first-person head clipping with minimal changes.

---

## Code References

- `Common/Entity/EntityPlayer.cs` (`updateEyeHeight`, `LocalEyePos`, immersive FP attachment point)
- `Common/Entity/Entity.cs` (`LocalEyePos` default from `EntityProperties.EyeHeight`)
- `Common/IMountableSeat.cs` (`IMountableSeat.LocalEyePos`, `SeatPosition`, `SeatConfig`)
- `Client/EnumCameraType.cs` (`EnumCameraMode`)
- `Common/Entity/EntityAgent.cs` (`IsEyesSubmerged`)
- `Common/Entity/EntityProperties.cs` (`EyeHeight`, `SwimmingEyeHeight`)

---

## Open Questions

- Exact file/line references for camera positioning in the client render pipeline (beyond API surface) may be engine-side (not in vsapi).
- Whether immersive FP is active for possessed NPCs and how animator attachment points are resolved for NPC models.
