# Possession Mounting Details (btca research)

**Date:** 2026-01-04
**Source:** Local copies of vsapi and vssurvivalmod

---

## Key Findings

### 1. Programmatic Mounting - `EntityAgent.TryMount()`

**Location:** `vsapi/Common/Entity/EntityAgent.cs:185-216`

```csharp
public virtual bool TryMount(IMountableSeat onmount)
{
    if (!onmount.CanMount(this)) return false;

    // Copy current controls to mount
    onmount.Controls.FromInt(Controls.ToInt());

    // Handle existing mount
    if (MountedOn != null && MountedOn != onmount)
    {
        if (!TryUnmount()) return false;
    }

    doMount(onmount);

    // Store for network sync
    var mountableTree = new TreeAttribute();
    onmount.MountableToTreeAttributes(mountableTree);
    WatchedAttributes["mountedOn"] = mountableTree;

    // Server marks dirty for sync
    if (World.Side == EnumAppSide.Server)
    {
        WatchedAttributes.MarkPathDirty("mountedOn");
    }
    return true;
}
```

**Usage:** Simply call `playerEntity.TryMount(ourCustomSeat)` - no special interaction needed!

---

### 2. doMount() Internal Flow

**Location:** `vsapi/Common/Entity/EntityAgent.cs:245-266`

```csharp
protected virtual void doMount(IMountableSeat mountable)
{
    this.MountedOn = mountable;
    controls.StopAllMovement();  // ← Important: clears existing movement

    if (mountable == null) return;

    mountable.Entity?.AnimManager?.StopAllAnimations();

    // Start suggested animation (our seat can return null to skip)
    if (MountedOn?.SuggestedAnimation != null)
    {
        curMountedAnim = MountedOn.SuggestedAnimation;
        AnimManager?.StopAllAnimations();
        AnimManager?.StartAnimation(curMountedAnim);
    }

    mountable.DidMount(this);  // ← Our hook to capture brain state!
}
```

---

### 3. SeatsToMotion() - Control Routing Pattern

**Location:** `vssurvivalmod/Systems/Boats/EntityBoat.cs:534-655`

```csharp
public virtual Vec2d SeatsToMotion(float dt)
{
    double linearMotion = 0;
    double angularMotion = 0;

    var bh = GetBehavior<EntityBehaviorSeatable>();

    foreach (var sseat in bh.Seats)
    {
        var seat = sseat as EntityBoatSeat;
        if (seat.Passenger == null) continue;
        if (!seat.Config.Controllable) continue;

        var controls = seat.controls;  // ← EntityControls from the passenger

        // Convert controls to motion
        if (controls.Left || controls.Right)
        {
            float dir = controls.Left ? 1 : -1;
            angularMotion += dir * dt;
        }

        if (controls.Forward || controls.Backward)
        {
            float dir = controls.Forward ? 1 : -1;
            linearMotion += dir * dt;
        }
    }

    return new Vec2d(linearMotion, angularMotion);
}
```

**Key Insight:** The seat's `controls` property reflects the passenger's input. For possession, we route these to NPC locomotion instead of boat motion.

---

### 4. Network Sync for Mounting

Mounting is synced via `WatchedAttributes["mountedOn"]`:

```csharp
// Server side after mount
WatchedAttributes.MarkPathDirty("mountedOn");

// Client side restoration
if (WatchedAttributes.HasAttribute("mountedOn"))
{
    var mountable = World.ClassRegistry.GetMountable(WatchedAttributes["mountedOn"] as TreeAttribute);
    doMount(mountable);
}
```

---

## Implementation Plan for Possession

### Step 1: Create `PolisPossessableSeat : IMountableSeat`

```csharp
public class PolisPossessableSeat : IMountableSeat
{
    private Entity npcEntity;
    private EntityAgent passenger;

    // Camera at NPC eye level
    public Vec3f LocalEyePos => new Vec3f(0, npcEntity.EyeHeight, 0);

    // Hide player model
    public Matrixf RenderTransform => new Matrixf().Scale(0, 0, 0);

    // No animation override - let NPC keep its current animation
    public AnimationMetaData SuggestedAnimation => null;

    // Input routing
    public EntityControls Controls { get; } = new EntityControls();

    // Lifecycle hooks
    public void DidMount(EntityAgent entityAgent)
    {
        passenger = entityAgent;
        // Snapshot NPC brain state here
        // Start routing controls to NPC
    }

    public void DidUnmount(EntityAgent entityAgent)
    {
        // Restore NPC brain state
        // Enter reentry state
    }
}
```

### Step 2: Route Controls in NPC Update

```csharp
// In NPC's OnGameTick or behavior
void OnGameTick(float dt)
{
    if (possessionSeat?.Passenger != null)
    {
        // Player is possessing - route their controls to our movement
        var controls = possessionSeat.Controls;

        // Same pattern as SeatsToMotion but for walking
        if (controls.Forward) MoveForward(dt);
        if (controls.Backward) MoveBackward(dt);
        if (controls.Left) TurnLeft(dt);
        if (controls.Right) TurnRight(dt);
        if (controls.Jump) TryJump();
        // etc.
    }
    else
    {
        // Normal AI behavior
    }
}
```

### Step 3: Trigger Possession

```csharp
// Command handler for /polis possess
void OnPossessCommand(EntityPlayer player, Entity npcBot)
{
    var seat = new PolisPossessableSeat(npcBot);
    player.TryMount(seat);  // That's it!
}
```

---

## Key Properties Summary

| Property | Purpose | Our Value |
|----------|---------|-----------|
| `LocalEyePos` | First-person camera position | `(0, npcEyeHeight, 0)` |
| `RenderTransform` | Position/hide passenger | `Scale(0,0,0)` to hide |
| `SeatPosition` | Seat world position | NPC's position |
| `Controls` | Input from passenger | Route to NPC movement |
| `SuggestedAnimation` | Animation for passenger | `null` (keep NPC's) |
| `CanControl` | Can this seat control mount | `true` |
| `AngleMode` | Rotation mode | `Unaffected` |

---

## Reference Files

- `docs/vsapi/Common/Entity/EntityAgent.cs` - TryMount, TryUnmount, doMount
- `docs/vssurvivalmod/Systems/Boats/EntityBoat.cs` - SeatsToMotion pattern
- `docs/vssurvivalmod/Systems/Boats/EntitySeat.cs` - Base seat implementation
- `docs/vssurvivalmod/Systems/Boats/EntityBehaviorSeatable.cs` - Multi-seat management
