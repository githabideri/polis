# Vintage Story IMountable and IMountableSeat Interface Analysis

## Overview
Complete analysis of the mounting system interfaces and RenderTransform usage patterns found in Vintage Story modding repositories.

## IMountable Interface

**Location**: `vsapi/Common/IMountableSeat.cs` (lines 109-143)

```csharp
/// <summary>
/// Represents something the player can mount. Usually a block or an entity.
/// </summary>
public interface IMountable
{
    /// <summary>
    /// The seats of this mountable
    /// </summary>
    IMountableSeat[] Seats { get; }

    /// <summary>
    /// Position of this mountable
    /// </summary>
    EntityPos Position { get; }

    /// <summary>
    /// StepPitch (pitching when stepping up or down a block) of this mountable - valid client-side only, taken from EntityShapeRenderer
    /// </summary>
    double StepPitch { get; }

    bool AnyMounted();

    /// <summary>
    /// The entity that controls this mountable - there can only be one
    /// </summary>
    Entity Controller { get; }

    /// <summary>
    /// The entity which this mountable really is (for example raft, boat or elk) - may be null if the IMountable is a bed or other block
    /// </summary>
    Entity OnEntity { get; }

    /// <summary>
    /// The controls of the controlling seat (if any)
    /// </summary>
    EntityControls ControllingControls { get; }
}
```

## IMountableSeat Interface

**Location**: `vsapi/Common/IMountableSeat.cs` (lines 149-241)

```csharp
/// <summary>
/// Represents a seat of a mountable object.
/// </summary>
public interface IMountableSeat
{
    SeatConfig Config { get; set; }
    string SeatId { get; set; }
    long PassengerEntityIdForInit { get; set; }
    bool DoTeleportOnUnmount { get; set; }

    /// <summary>
    /// The entity behind this mountable supplier, if any
    /// </summary>
    Entity Entity { get; }

    /// <summary>
    /// The entity sitting on this seat
    /// </summary>
    Entity Passenger { get; }

    /// <summary>
    /// The supplier of this mount provider. e.g. the raft entity for the 2 raft seats
    /// </summary>
    IMountable MountSupplier { get; }

    /// <summary>
    /// If this "mountable seat" is the one that controls the mountable entity/block
    /// </summary>
    bool CanControl { get; }

    /// <summary>
    /// How the mounted entity should rotate
    /// </summary>
    EnumMountAngleMode AngleMode { get; }

    /// <summary>
    /// What animation the mounted entity should play
    /// </summary>
    AnimationMetaData SuggestedAnimation { get; }

    /// <summary>
    /// Whether or not the mount should play the idle anim
    /// </summary>
    bool SkipIdleAnimation { get; }

    float FpHandPitchFollow { get; }

    /// <summary>
    /// Where to place the first person camera
    /// </summary>
    Vec3f LocalEyePos { get; }

    /// <summary>
    /// Exact position of this seat
    /// </summary>
    EntityPos SeatPosition { get; }

    /// <summary>
    /// Transformation matrix that can be used to render the mounted entity at the right position. The transform is relative to the SeatPosition. May be null.
    /// </summary>
    Matrixf RenderTransform { get; }

    /// <summary>
    /// The control scheme of this seat
    /// </summary>
    EntityControls Controls { get; }

    void MountableToTreeAttributes(TreeAttribute tree);
    void DidUnmount(EntityAgent entityAgent);
    void DidMount(EntityAgent entityAgent);
    bool CanUnmount(EntityAgent entityAgent);
    bool CanMount(EntityAgent entityAgent);
}
```

## RenderTransform Property and Matrixf API

### Property Definition
- **Type**: `Matrixf` (4x4 transformation matrix)
- **Purpose**: Positions mounted entities relative to seat position for rendering
- **Relation**: Transform is relative to `SeatPosition`
- **Nullability**: May be `null`

### Matrixf Class API (from vsapi btca search)

#### Core Properties
- `Values`: `float[]` - 16 float values of 4x4 matrix
- `ValuesAsDouble`: `double[]` - Read-only matrix values as doubles

#### Transformation Methods (Chainable)
**Translation:**
```csharp
Matrixf Translate(double x, double y, double z)
Matrixf Translate(Vec3f vec)  
Matrixf Translate(float x, float y, float z)
```

**Scaling:**
```csharp
Matrixf Scale(float x, float y, float z)
```

**Rotation (Radians):**
```csharp
Matrixf Rotate(float radX, float radY, float radZ)
Matrixf Rotate(Vec3f radians)
Matrixf RotateX(float radX)
Matrixf RotateY(float radY) 
Matrixf RotateZ(float radZ)
```

**Rotation (Degrees):**
```csharp
Matrixf RotateDeg(Vec3f degrees)
Matrixf RotateXDeg(float degX)
Matrixf RotateYDeg(float degY)
Matrixf RotateZDeg(float degZ)
```

**Matrix Operations:**
```csharp
Matrixf Mul(float[] matrix)
Matrixf Mul(Matrixf matrix)
Matrixf ReverseMul(float[] matrix)
Matrixf Invert()
Matrixf Identity()
Matrixf Clone()
```

### Usage Pattern
```csharp
Matrixf renderTransform = new Matrixf()
    .Identity()
    .Translate(offsetX, offsetY, offsetZ)
    .RotateDeg(rotX, rotY, rotZ)
    .Scale(scaleX, scaleY, scaleZ);
```

## Known Implementations

### Abstract Base Class
**Location**: `vssurvivalmod/Systems/Boats/EntitySeat.cs`
```csharp
public abstract class EntitySeat : IMountableSeat
{
    public abstract Matrixf RenderTransform { get; }
    // ... other IMountableSeat implementations ...
}
```

## Concrete Implementations Found

### Implementation Hierarchy
```
EntitySeat (Abstract Base)
    ↓
EntityRideableSeat (Intermediate) 
    ↓
EntityBoatSeat (Boat-Specific Concrete)
```

### 1. EntitySeat (Abstract Base Class)
**Location**: `vssurvivalmod/Systems/Boats/EntitySeat.cs`
```csharp
public abstract class EntitySeat : IMountableSeat
{
    public abstract Matrixf RenderTransform { get; }
    // Implements basic seat functionality:
    // - mounting/unmounting logic
    // - passenger management
    // - control schemes
    // - DidMount()/DidUnmount() lifecycle methods
}
```

### 2. EntityRideableSeat (Intermediate)
**Location**: `vssurvivalmod/Entity/Behavior/EntityRideableSeat.cs`
- Extends `EntitySeat` for rideable entities
- **Key feature**: Handles `RenderTransform` via attachment point transforms
- Manages safe teleportation for unmounting
- Ownership checking for controllable seats

### 3. EntityBoatSeat (Boat-Specific Concrete)
**Location**: `vssurvivalmod/Systems/Boats/BoatSeat.cs`
```csharp
public class EntityBoatSeat : EntityRideableSeat
{
    public EntityBoatSeat(Entity entity, SeatConfig config) : base(entity, config) 
    {
        RideableClassName = "boat";
    }
    
    // Boat-specific features:
    // - Supports rope-tieable creatures
    // - Boat-specific animations
    // - Custom teleportation logic for water-safe unmounting
}
```

### 4. EntityBoat (IMountable Implementation)
**Location**: `vssurvivalmod/Systems/Boats/EntityBoat.cs`
**Key Interfaces Implemented**:
- `ISeatInstSupplier` - Creates seat instances via `CreateSeat()`
- `IMountableListener` - Handles mount/unmount events
- `IMountable` - Boat-level mounting functionality

```csharp
public class Entity : Entity, IRenderer, ISeatInstSupplier, IMountableListener
{
    // Creates EntityBoatSeat instances
    public IMountableSeat CreateSeat(SeatConfig config)
    {
        return new EntityBoatSeat(this, config);
    }
    
    // Converts passenger controls to boat movement
    protected void SeatsToMotion(float dt)
    
    // IMountableListener implementation
    public void DidMount(EntityAgent entityAgent)
    public void DidUnmount(EntityAgent entityAgent)
}
```

### 5. EntityBehaviorSeatable (Seat Management)
**Location**: `vssurvivalmod/Systems/Boats/EntityBehaviorSeatable.cs`
- Manages multiple seats on entities
- Handles seat registration and interaction
- Supports selection box-based seat selection
- Integrates with attachment points and animations

## RenderTransform Implementation Pattern

Based on the implementation hierarchy, the `RenderTransform` property is:

1. **Defined** in `IMountableSeat` interface
2. **Made abstract** in `EntitySeat` base class  
3. **Implemented concretely** in `EntityRideableSeat` using attachment point transforms
4. **Inherited** by `EntityBoatSeat` and other seat types

### Concrete RenderTransform Implementation
**Location**: `vssurvivalmod/Entity/Behavior/EntityRideableSeat.cs` (lines 61-74)

```csharp
public override Matrixf RenderTransform
{
    get
    {
        loadAttachPointTransform();
        var rotvec = modelmat.TransformVector(new Vec4f(0, 0, 0, 1));
        return
            new Matrixf()
            .Translate(-rotvec.X, -rotvec.Y, -rotvec.Z) // Relative to SeatPosition, so let's subtract that offset
            .Mul(modelmat)
            .RotateDeg(config.MountRotation)
        ;
    }
}
```

### Key Components

**Helper Method**: `loadAttachPointTransform()` (lines 78-103)
```csharp
private void loadAttachPointTransform()
{
    var anim = entity.AnimationsManager;
    if (anim == null) return;
    
    AttachmentPointAndPose apap = anim.GetAttachmentPointPose(APName);
    if (apap == null) return;

    var r = entity.Properties.Client.Renderer;
    
    // Get entity rotation
    float degX = r.SwivelYaw * GameMath.DEG2RAD * r.BodyYawRollFactor;
    float degY = r.BodyYaw;
    float degZ = r.Pitch;
    
    // Create transformation matrix
    modelmat.Identity()
        .Translate(0, r.OffY, 0)
        .RotateX(degX)
        .RotateY(degY)
        .RotateZ(degZ)
        .Translate(-r.LocalOrigin.X, -r.LocalOrigin.Y, -r.LocalOrigin.Z)
        .Mul(apap.Matrixf)
        .Translate(config.MountOffset);
}
```

**Transformation Process**:
1. **Load Attachment Point** - Gets pose from entity animator at attachment point
2. **Apply Entity Rotation** - Handles swivel, body yaw, pitch from renderer
3. **Adjust Origin** - Accounts for local origin offset  
4. **Multiply with Attachment Matrix** - Combines entity transform with attach point
5. **Apply Mount Offset** - Adds seat-specific offset from config
6. **Final Relative Transform** - Makes relative to SeatPosition by subtracting rotation vector

**Variables Used**:
- `modelmat`: Transformation matrix from attachment point
- `APName`: Attachment point name from `config.APName`
- `config.MountRotation`: Additional rotation from seat configuration
- `config.MountOffset`: Position offset from seat configuration

This implementation ensures passengers are positioned correctly relative to:
- Entity animations and attachment points
- Entity rotation and orientation  
- Seat-specific offsets and rotations
- Relative positioning from seat center

## Source
All findings derived from btca searches of vsapi and vssurvivalmod repositories as per AGENTS.md instructions.