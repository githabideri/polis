# Mounting System Approaches: Custom IMountableSeat vs EntityBehaviorRideable

**Date:** 2026-01-05
**Status:** Research Complete - Custom Approach Chosen
**Related:** `2026-01-04-vintage-story-mounting-analysis.md`, `2026-01-02-possession-implementation-plan.md`

## Executive Summary

We investigated two approaches for implementing NPC possession in Vintage Story:
1. **Custom `IMountableSeat` implementation** (our current approach)
2. **Extending vanilla `EntityBehaviorRideable`** (Jaunt mod approach)

**Decision:** Stick with custom `IMountableSeat` approach and fix `WalkVector` routing.

**Reason:** Possession is fundamentally different from riding a mount. The custom approach is simpler, more flexible, and avoids unnecessary complexity from the rideable system's gait/saddle/control scheme features we don't need.

---

## Research Methodology

### Sources
- **btca queries** against vsapi, vssurvivalmod, Jaunt mod repositories
- **Manual code review** of vanilla mounting system
- **ChatGPT research** on VS mounting architecture and networking

### Key Files Analyzed
- `vssurvivalmod/Entity/Behavior/BehaviorRideable.cs` - Vanilla rideable system
- `vssurvivalmod/Entity/Behavior/EntityRideableSeat.cs` - Vanilla seat implementation
- `jaunt/Jaunt/Behaviors/EntityBehaviorJauntRideable.cs` - Jaunt's extension
- `jaunt/Jaunt/Behaviors/EntityJauntRideableSeat.cs` - Jaunt's custom seat
- `vsapi/Common/IMountableSeat.cs` - Mounting interface
- `vsessentialsmod/Entity/Behavior/BehaviorControlledPhysics.cs` - NPC physics
- `vsessentialsmod/Entity/Behavior/BehaviorPlayerPhysics.cs` - Player physics

---

## Approach 1: Custom IMountableSeat (Our Current Approach)

### Architecture

```
Player (EntityPlayer)
  └─ TryMount(seat)
       └─ PolisPossessableSeat (IMountableSeat)
            ├─ Entity: The NPC being possessed
            ├─ Passenger: The player possessing
            ├─ Controls: Receives player input from mounting system
            ├─ LocalEyePos: Camera position (at NPC eye level)
            └─ MountSupplier: PolisPossessionMountable (IMountable wrapper)

NPC (EntityAgent with playerbot behavior)
  └─ ServerControls: We route seat.Controls → npc.ServerControls
  └─ EntityBehaviorControlledPhysics: Processes ServerControls for movement
```

### How It Works

1. **Mounting:**
   ```csharp
   // Command handler
   var seat = new PolisPossessableSeat(npc);
   seat.OnPossessionStart += (passenger) => {
       activePossessions[playerUid] = seat;
   };

   player.TryMount(seat); // Vanilla mounting system
   ```

2. **Camera Positioning:**
   ```csharp
   // In PolisPossessableSeat.cs
   public Vec3f LocalEyePos => new Vec3f(0, (float)(npcEntity?.LocalEyePos?.Y ?? 1.6), 0);

   public EntityPos SeatPosition {
       get {
           UpdateSeatPosition(); // Follow NPC position
           return seatPos;
       }
   }
   ```

   VS mounting system automatically:
   - Sets player's `LocalEyePos` from seat
   - Positions player at `SeatPosition`
   - Syncs to client via `WatchedAttributes["mountedOn"]`

3. **Control Routing (CURRENT - BROKEN):**
   ```csharp
   // In UpdatePossessions() - this doesn't work!
   var controls = player.Controls;
   npc.ServerControls.Forward = controls.Forward;
   npc.ServerControls.Left = controls.Left;
   // ... etc

   // Problem: WalkVector stays (0,0,0)!
   // Physics uses WalkVector, not boolean flags
   ```

4. **Control Routing (FIXED):**
   ```csharp
   // In UpdatePossessions() - the WalkVector fix
   void UpdatePossessions(float dt)
   {
       foreach (var kvp in activePossessions)
       {
           var seat = kvp.Value;
           var npc = seat.Entity as EntityAgent;
           var player = sapi.World.PlayerByUid(kvp.Key)?.Entity;

           seat.UpdateSeatPosition(); // Keep seat following NPC

           var seatControls = seat.Controls; // Player input (from mounting system)
           var npcControls = npc.ServerControls;

           // Copy boolean inputs
           npcControls.Forward = seatControls.Forward;
           npcControls.Backward = seatControls.Backward;
           npcControls.Left = seatControls.Left;
           npcControls.Right = seatControls.Right;
           npcControls.Jump = seatControls.Jump;
           npcControls.Sneak = seatControls.Sneak;
           npcControls.Sprint = seatControls.Sprint;

           // CRITICAL: Directly calculate WalkVector like Jaunt does
           double dx = (seatControls.Left ? -1 : 0) + (seatControls.Right ? 1 : 0);
           double dz = (seatControls.Forward ? 1 : 0) + (seatControls.Backward ? -1 : 0);

           double moveSpeed = dt * GlobalConstants.BaseMoveSpeed * npcControls.MovespeedMultiplier;
           double cosYaw = Math.Cos(npc.ServerPos.Yaw);
           double sinYaw = Math.Sin(npc.ServerPos.Yaw);

           // Set WalkVector directly (bypasses CalcMovementVectors)
           npcControls.WalkVector.Set(
               (dx * cosYaw - dz * sinYaw) * moveSpeed,
               0,
               (dx * sinYaw + dz * cosYaw) * moveSpeed
           );

           // Route camera orientation to NPC
           npc.ServerPos.Yaw = player.ServerPos.Yaw;
           npc.ServerPos.HeadYaw = player.ServerPos.HeadYaw;
           npc.ServerPos.HeadPitch = player.ServerPos.HeadPitch;
       }
   }
   ```

5. **Animation Triggers:**
   ```csharp
   // Animations triggered by EntityAgent.CurrentControls (in EntityAgent.OnGameTick)
   CurrentControls =
       (servercontrols.TriesToMove ? EnumEntityActivity.Move : EnumEntityActivity.Idle) |
       (servercontrols.Jump && OnGround ? EnumEntityActivity.Jump : 0) |
       // ... etc

   // TriesToMove = Forward || Backward || Left || Right
   // So our boolean routing + WalkVector should trigger animations
   ```

6. **Physics Processing:**
   ```csharp
   // EntityBehaviorControlledPhysics.OnPhysicsTick() runs on server
   // Reads npc.ServerControls.WalkVector
   // Applies to entity position via physics modules:
   //   - PModuleOnGround uses WalkVector for ground movement
   //   - PModuleInAir uses WalkVector for air control
   //   - etc.
   ```

### Implementation Files

- **Core:** `PolisPossessableSeat.cs` (~245 lines)
- **Integration:** `PolisBuilderNpcSystem.cs` - possession commands, `UpdatePossessions()`
- **Hotkeys:** `PolisBuilderNpcHotkeys.cs` - Alt+U, Alt+Shift+U
- **Registration:** `StartServerSide()` - `api.RegisterMountable(PolisPossessableSeat.CreateFromTree)`

### Pros

✅ **Simple** - ~300 total lines, all code is ours
✅ **Flexible** - Not constrained by rideable assumptions
✅ **Focused** - Only does possession, no extra features
✅ **Understandable** - We control every aspect
✅ **Lightweight** - No gait system, stamina, accessories
✅ **Working camera** - `LocalEyePos` auto-syncs
✅ **Working networking** - `MountableToTreeAttributes` handles it

### Cons

❌ **Manual control routing** - We write `UpdatePossessions()` ourselves
❌ **No built-in gaits** - NPCs move at one speed
❌ **No fancy animations** - Basic walk/idle only
❌ **WalkVector fix needed** - Must calculate directly

---

## Approach 2: Extending EntityBehaviorRideable (Jaunt Approach)

### Architecture

```
EntityBehaviorRideable (vanilla base class)
  ├─ IMountable interface
  ├─ SeatsToMotion() - converts seat controls to linear/angular motion
  ├─ Move() - applies motion to entity WalkVector
  ├─ UpdateRidingState() - updates entity controls, animations
  ├─ Gait system (walk, trot, gallop, fly, etc.)
  ├─ Control schemes (Hold vs Press)
  ├─ Saddle breaking for wild animals
  └─ EntityRideableSeat (vanilla seat implementation)
       ├─ LocalEyePos - calculated from attachment points
       ├─ SeatPosition - from attachment point transforms
       └─ RenderTransform - complex matrix math

EntityBehaviorJauntRideable (Jaunt's extension)
  └─ Overrides SeatsToMotion, Move, UpdateRidingState
  └─ Adds stamina integration, flight controls
  └─ EntityJauntRideableSeat (custom seat)
       └─ Sets HeadYawLimits/BodyYawLimits on mount
```

### How It Works (Jaunt Example)

1. **Entity Setup:**
   ```json
   // In entity JSON
   {
     "behaviors": [
       {
         "code": "jaunt:rideable",
         "controls": {
           "forward": { "trigger": "forward" },
           "backward": { "trigger": "backward" }
         },
         "gaits": {
           "walk": { "speed": 0.02, "code": "walk" },
           "trot": { "speed": 0.04, "code": "trot" }
         }
       }
     ]
   }
   ```

2. **Mounting:**
   ```csharp
   // Vanilla mounting - player right-clicks entity
   // EntityBehaviorRideable handles it via OnInteract()

   public override void OnInteract(EntityAgent byEntity, ItemSlot itemslot,
                                    Vec3d hitPosition, EnumInteractMode mode,
                                    ref EnumHandling handled)
   {
       if (GetOrCreateSeats().Count > 0)
       {
           var seat = GetOrCreateSeats()[0];
           if (seat.CanMount(byEntity))
           {
               byEntity.TryMount(seat);
               handled = EnumHandling.PreventDefault;
           }
       }
   }
   ```

3. **Control Processing:**
   ```csharp
   // EntityBehaviorJauntRideable.SeatsToMotion()
   public override Vec2d SeatsToMotion(float dt)
   {
       foreach (var seat in Seats)
       {
           if (seat.Passenger == null) continue;

           var controls = seat.Controls; // Player input here

           // Process gait changes
           if (controls.Forward && !prevForwardKey) SpeedUp();
           if (controls.Backward && !prevBackwardKey) SlowDown();

           // Calculate motion
           if (controls.Left || controls.Right)
           {
               float dir = controls.Left ? 1 : -1;
               angularMotion += CurrentGait.YawMultiplier * dir * dt;
           }

           if (IsMovingForward)
           {
               linearMotion += CurrentGait.Speed * dt * 2f;
           }
       }

       return new Vec2d(linearMotion, angularMotion);
   }
   ```

4. **Movement Application:**
   ```csharp
   // EntityBehaviorJauntRideable.Move()
   private void Move(float dt, EntityControls controls, float nowMoveSpeed)
   {
       double cosYaw = Math.Cos(entity.Pos.Yaw);
       double sinYaw = Math.Sin(entity.Pos.Yaw);

       // Directly set WalkVector
       controls.WalkVector.Set(sinYaw, 0, cosYaw);
       controls.WalkVector.Mul(nowMoveSpeed * GlobalConstants.OverallSpeedMultiplier * ForwardSpeed);

       if (controls.IsFlying)
       {
           controls.FlyVector.Set(controls.WalkVector);
           eagent.Pos.Motion.Y = VerticalSpeed;
       }
   }
   ```

5. **Camera Constraints:**
   ```csharp
   // EntityJauntRideableSeat.DidMount()
   if (Passenger is EntityPlayer eplr)
   {
       // Limit how far player can look left/right
       eplr.HeadYawLimits = new AngleConstraint(
           Entity.Pos.Yaw + Config.MountRotation.Y * GameMath.DEG2RAD,
           GameMath.PIHALF  // ±90 degrees
       );
       eplr.BodyYawLimits = new AngleConstraint(
           Entity.Pos.Yaw + Config.MountRotation.Y * GameMath.DEG2RAD,
           GameMath.PIHALF
       );

       // On client, sync mouse to mount yaw
       if (capi != null)
       {
           capi.Input.MouseYaw = Entity.Pos.Yaw;
       }
   }
   ```

### Implementation Requirements

To use this approach, you would need to:

1. **Create entity behavior:**
   ```csharp
   public class EntityBehaviorPolisPossessable : EntityBehaviorRideable
   {
       // Override SeatsToMotion() - convert controls to motion
       // Override Move() - apply motion to WalkVector
       // Override UpdateRidingState() - update animations
       // Override CreateSeat() - return custom seat
   }
   ```

2. **Create custom seat:**
   ```csharp
   public class PolisPossessionSeat : EntityRideableSeat
   {
       // Override DidMount() - no camera constraints for possession
       // Override CanMount() - check possession requirements
   }
   ```

3. **Register behavior:**
   ```csharp
   api.RegisterEntityBehaviorClass("polis:possessable",
                                    typeof(EntityBehaviorPolisPossessable));
   ```

4. **Add to entity JSON:**
   ```json
   {
     "behaviors": [
       { "code": "polis:possessable" }
     ]
   }
   ```

5. **Configure in code** (no more commands) - relies on right-click interaction

### Pros

✅ **Robust** - Vanilla battle-tested code
✅ **Feature-rich** - Gaits, animations, stamina hooks
✅ **Less manual work** - Control routing built-in
✅ **Polished** - Attachment points, proper camera math
✅ **Extensible** - Can add walk/trot/gallop easily

### Cons

❌ **Complex** - ~1500+ lines of base class logic to understand
❌ **Mount-oriented** - Designed for riding, not possession
❌ **Over-engineered** - Brings features we don't need (saddle breaking, etc.)
❌ **Less flexible** - Constrained by base class assumptions
❌ **Harder to debug** - More indirection, inheritance
❌ **JSON config** - Requires entity JSON changes
❌ **No commands** - Would need to rework our command-based possession

---

## Comparison Matrix

| Criterion | Custom IMountableSeat | EntityBehaviorRideable |
|-----------|----------------------|------------------------|
| **Lines of Code** | ~300 | ~1500+ (base) + overrides |
| **Complexity** | 🟢 Low | 🔴 High |
| **Flexibility** | 🟢 High | 🟡 Medium |
| **Camera Control** | 🟢 Free 360° | 🟡 Constrained ±90° (or override) |
| **Command-based** | 🟢 Yes | 🔴 No (entity interaction) |
| **Learning Curve** | 🟢 Low | 🔴 High |
| **Maintenance** | 🟢 Simple | 🟡 Moderate |
| **Features** | 🔴 Minimal | 🟢 Rich (gaits, etc.) |
| **Debug Difficulty** | 🟢 Easy | 🟡 Moderate |
| **Initial Setup** | 🟢 Done | 🔴 Major refactor |

---

## Critical Research Findings

### 1. Mounts Keep Ticking Physics

**Discovery:** When a player mounts an entity, the mount's physics continues to tick normally. Only the PLAYER's physics stops.

**Evidence:**
```csharp
// From BehaviorControlledPhysics.cs:503-507
EntityAgent agent = entity as EntityAgent;
if (agent?.MountedOn != null)  // Player has MountedOn set
{
    AdjustMountedPositionFor(agent);
    return;  // Player physics exits early
}
// Mount continues past this point - physics runs normally
```

**Implication:** Our NPC can move while possessed - we just need to route controls correctly.

### 2. WalkVector is The Key

**Discovery:** VS physics doesn't use `ServerControls.Forward/Left/etc` directly. It uses `ServerControls.WalkVector`.

**Evidence:**
```csharp
// From PModuleOnGround.cs:76-77
double walkX = controls.WalkVector.X * multiplier;
double walkZ = controls.WalkVector.Z * multiplier;
```

**Implication:** Setting boolean flags isn't enough - we must calculate `WalkVector`.

### 3. CalcMovementVectors Not Called for NPCs

**Discovery:** `EntityControls.CalcMovementVectors()` is called by player physics but NOT by NPC physics.

**Evidence:**
```csharp
// BehaviorPlayerPhysics.cs:304,310,354
controls.CalcMovementVectors(pos, dt); // Player calls this

// BehaviorControlledPhysics.cs - NEVER calls CalcMovementVectors
// NPCs rely on AI or manual vector setting
```

**Implication:** We can either call `CalcMovementVectors()` ourselves OR directly set `WalkVector` like Jaunt.

### 4. Jaunt Doesn't Use CalcMovementVectors

**Discovery:** Jaunt's rideable system directly sets `WalkVector` instead of calling `CalcMovementVectors()`.

**Evidence:**
```csharp
// From EntityBehaviorJauntRideable.Move()
controls.WalkVector.Set(sinYaw, 0, cosYaw);
controls.WalkVector.Mul(nowMoveSpeed * ForwardSpeed);
```

**Implication:** Direct vector calculation is the proven pattern for controlled NPCs.

### 5. Camera Auto-Syncs

**Discovery:** Camera positioning via `LocalEyePos` is automatically synchronized by the engine.

**Evidence:** No manual networking code in Jaunt or vanilla mounting system for camera.

**Implication:** Our `LocalEyePos` should "just work" once mounting succeeds.

---

## Decision Rationale

### Why Custom Approach Wins

1. **Possession ≠ Riding**
   - Riding: Player wants to go somewhere, mount takes them there
   - Possession: Player IS the NPC, controls it directly
   - The rideable system is optimized for the former, not the latter

2. **Simplicity Matters**
   - We understand every line of our code
   - Easier to debug when things break
   - Less cognitive overhead

3. **No Unnecessary Features**
   - Don't need: gaits, saddle breaking, control schemes, accessories
   - Only need: control routing, camera, basic movement

4. **Already 90% There**
   - Mounting works ✓
   - Camera positioning works ✓
   - Networking works ✓
   - Just need WalkVector fix

5. **Future Flexibility**
   - Can add features incrementally as needed
   - Not locked into rideable architecture
   - Easier to experiment

---

## Implementation Plan

### Step 1: Apply WalkVector Fix

**File:** `PolisBuilderNpcSystem.cs`

**Change `UpdatePossessions()` from:**
```csharp
// Current (broken)
var controls = player.Controls;
npc.ServerControls.Forward = controls.Forward;
// ... WalkVector stays (0,0,0)
```

**To:**
```csharp
// Fixed
var seatControls = seat.Controls;
var npcControls = npc.ServerControls;

// Copy boolean inputs
npcControls.Forward = seatControls.Forward;
npcControls.Backward = seatControls.Backward;
npcControls.Left = seatControls.Left;
npcControls.Right = seatControls.Right;
npcControls.Jump = seatControls.Jump;
npcControls.Sneak = seatControls.Sneak;
npcControls.Sprint = seatControls.Sprint;

// Calculate WalkVector directly
double dx = (seatControls.Left ? -1 : 0) + (seatControls.Right ? 1 : 0);
double dz = (seatControls.Forward ? 1 : 0) + (seatControls.Backward ? -1 : 0);
double moveSpeed = dt * GlobalConstants.BaseMoveSpeed * npcControls.MovespeedMultiplier;
double cosYaw = Math.Cos(npc.ServerPos.Yaw);
double sinYaw = Math.Sin(npc.ServerPos.Yaw);

npcControls.WalkVector.Set(
    (dx * cosYaw - dz * sinYaw) * moveSpeed,
    0,
    (dx * sinYaw + dz * cosYaw) * moveSpeed
);

// Route camera
npc.ServerPos.Yaw = player.ServerPos.Yaw;
npc.ServerPos.HeadYaw = player.ServerPos.HeadYaw;
npc.ServerPos.HeadPitch = player.ServerPos.HeadPitch;
```

### Step 2: Test

```bash
# Build and deploy
cd /home/mf/Code/polis-builder/polis-builder-npc && \
VINTAGE_STORY="/home/mf/.local/share/flatpak/app/at.vintagestory.VintageStory/x86_64/stable/active/files/extra/vintagestory" \
dotnet build -c Release && \
cp -r bin/Release/Mods/polis-builder-npc ../vsdata/Mods/

# In-game test
/polis spawn
/polis possess
# Press WASD - NPC should move!
# Move mouse - NPC should rotate!
```

### Step 3: Debug if Needed

Check logs for:
```bash
tail -f ../vsdata/Logs/server-main.log | grep -i "polis\|possess"
```

Expected behavior:
- ✅ Camera follows NPC
- ✅ WASD moves NPC
- ✅ Mouse rotates NPC
- ✅ Walking animation plays
- ✅ Jumping works

### Step 4: Refine (if needed)

Potential issues to address:
- **Movement speed** - adjust `MovespeedMultiplier`
- **Sprint** - may need special handling
- **Jump height** - NPC vs player jump differences
- **Collision** - ensure NPC physics handles it

---

## Future Enhancements (Optional)

If we need more features later:

1. **Variable Speed:**
   ```csharp
   float speedMultiplier = seatControls.Sprint ? 1.5f :
                           seatControls.Sneak ? 0.5f : 1.0f;
   npcControls.WalkVector.Mul(speedMultiplier);
   ```

2. **Flight Control:**
   ```csharp
   if (npc.Controls.IsFlying)
   {
       npcControls.FlyVector.Set(npcControls.WalkVector);
       if (seatControls.Jump) npc.Pos.Motion.Y = 0.05;
       if (seatControls.Sneak) npc.Pos.Motion.Y = -0.05;
   }
   ```

3. **Smooth Camera:**
   ```csharp
   // Lerp NPC yaw to player yaw for smooth turning
   float targetYaw = player.ServerPos.Yaw;
   float yawDiff = GameMath.AngleRadDistance(npc.ServerPos.Yaw, targetYaw);
   npc.ServerPos.Yaw += yawDiff * 0.3f; // 30% lerp
   ```

---

## References

### Code Locations

**Vanilla (vssurvivalmod):**
- `Entity/Behavior/BehaviorRideable.cs` - Base rideable system
- `Entity/Behavior/EntityRideableSeat.cs` - Vanilla seat
- `Entity/Behavior/BehaviorRideableAccessories.cs` - Saddle/accessories

**Essentials (vsessentialsmod):**
- `Entity/Behavior/BehaviorControlledPhysics.cs` - NPC physics (lines 493-511 = OnPhysicsTick)
- `Entity/Behavior/BehaviorPlayerPhysics.cs` - Player physics (lines 281-357 = SetPlayerControls)

**Jaunt Mod:**
- `Jaunt/Behaviors/EntityBehaviorJauntRideable.cs` - Extended rideable
- `Jaunt/Behaviors/EntityJauntRideableSeat.cs` - Custom seat

**Our Implementation:**
- `PolisPossessableSeat.cs` - Custom seat (245 lines)
- `PolisBuilderNpcSystem.cs` - Possession commands, UpdatePossessions()
- `PolisBuilderNpcHotkeys.cs` - Alt+U, Alt+Shift+U

### Research Documents

- `docs/research/phase-1/2026-01-04-vintage-story-mounting-analysis.md`
- `docs/research/phase-1/2026-01-04-btca-possession-mounting-details.md`
- `docs/research/phase-1/2026-01-02-possession-implementation-plan.md`

### External Resources

- [VS API: IMountableSeat](https://apidocs.vintagestory.at/api/Vintagestory.API.Common.IMountableSeat.html)
- [VS API: EntityAgent](https://apidocs.vintagestory.at/api/Vintagestory.API.Common.EntityAgent.html)
- [VS API: EntityControls](https://apidocs.vintagestory.at/api/Vintagestory.API.Common.EntityControls.html)

---

## Conclusion

The custom `IMountableSeat` approach is the right choice for our possession system because:

1. **It's simpler** - 300 lines vs 1500+
2. **It's more appropriate** - Possession isn't riding
3. **It's almost working** - Just needs WalkVector fix
4. **It's maintainable** - We understand every line

The WalkVector fix is proven by Jaunt's implementation and follows the same pattern used by vanilla rideable mounts. Once applied, our possession system should be fully functional.

If we later need advanced features (gaits, fancy animations, etc.), we can either:
- Add them incrementally to our custom system
- Reconsider extending EntityBehaviorRideable with this research as a guide

For now: **Fix WalkVector routing and test.**
