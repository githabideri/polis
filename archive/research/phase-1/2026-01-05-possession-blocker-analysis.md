# Possession System Blocker Analysis

**Date:** 2026-01-05
**Status:** BLOCKED - Mount succeeds server-side but doesn't sync to client
**Related:** `2026-01-05-mounting-approaches-comparison.md`, `2026-01-04-vintage-story-mounting-analysis.md`

## Executive Summary

The possession system has **partial functionality**:
- ✅ WalkVector fix works - NPC moves correctly
- ✅ Control routing works - Bot mimics player input
- ✅ TryMount succeeds server-side
- ❌ **BLOCKER:** Mount state doesn't sync to client
- ❌ Player physics keeps running (both entities move)
- ❌ Camera stays with player (doesn't switch to NPC view)

**Root Issue:** The mounting system works on the server but the client never receives/processes the mount state, so `player.MountedOn` stays `null` on the client side.

---

## Current Behavior (After All Fixes)

### What Works ✅

1. **Server-Side Mounting:**
   ```
   [polis] CmdPossess called
   [polis] CmdPossess: Player player
   [polis] CmdPossess: Bot 103 selected
   [polis] CmdPossess: Creating seat
   [polis] CmdPossess: Attempting TryMount
   [polis] OnPossessionStart: Player player -> Bot 103
   [polis] CmdPossess: TryMount SUCCESS
   ```

2. **Control Routing:**
   ```
   [polis] Possession: controls=(True,False,False,False) walkVec=(0.024,0.000,-0.101)
   [polis] Possession: controls=(False,False,False,True) walkVec=(-0.023,0.000,0.098)
   ```
   - Player input → seat.Controls → NPC.ServerControls ✅
   - WalkVector calculated correctly ✅
   - NPC moves in response to WASD ✅

3. **NPC Movement:**
   - Bot faces same direction as player ✅
   - Bot moves when WASD pressed ✅
   - Bot jumps when space pressed ✅
   - Walking animations play ✅

### What's Broken ❌

1. **Player Physics Still Active:**
   - Player entity continues to move with WASD
   - BOTH player and bot walk around simultaneously
   - Player is NOT frozen at seat position

2. **Camera Stays With Player:**
   - Camera does NOT switch to NPC view
   - Player sees from their own character's eyes
   - LocalEyePos from seat is NOT being used

3. **No Client-Side Mount State:**
   - No mount-related logs on client side
   - No errors in client logs
   - Silent failure to sync mount state

---

## Code Changes Applied (Session History)

### 1. WalkVector Fix (✅ WORKING)

**File:** `PolisBuilderNpcSystem.cs` - `UpdatePossessions()`

```csharp
// Calculate WalkVector directly (Jaunt pattern)
double dx = (seatControls.Left ? -1 : 0) + (seatControls.Right ? 1 : 0);
double dz = (seatControls.Forward ? 1 : 0) + (seatControls.Backward ? -1 : 0);

double moveSpeed = dt * GlobalConstants.BaseMoveSpeed * npcControls.MovespeedMultiplier;
double cosYaw = Math.Cos(npc.ServerPos.Yaw);
double sinYaw = Math.Sin(npc.ServerPos.Yaw);

// Set WalkVector directly - this is what physics uses!
npcControls.WalkVector.Set(
    (dx * cosYaw - dz * sinYaw) * moveSpeed,
    0,
    (dx * sinYaw + dz * cosYaw) * moveSpeed
);
```

**Result:** NPC moves correctly ✅

### 2. RegisterMountable Call (❓ UNKNOWN EFFECT)

**File:** `PolisBuilderNpcSystem.cs` - `StartServerSide()`

```csharp
// Register the possession mountable so clients can reconstruct the seat
api.RegisterMountable(PolisPossessableSeat.MountableClassName, PolisPossessableSeat.CreateFromTree);
```

**Expected:** Client should be able to deserialize the seat from `MountableToTreeAttributes`

**Observed:** No change in behavior - still no client-side mount

### 3. Control Routing Source (✅ WORKING)

Changed from reading `player.Controls` to `seat.Controls`:

```csharp
// OLD (broken):
var controls = player.Controls;  // Player's controls are null when mounted

// NEW (working):
var seatControls = seat.Controls;  // Seat receives player input from mounting system
```

**Result:** Controls route correctly ✅

---

## Implementation Status

### Files Modified

1. **`PolisPossessableSeat.cs`** - Custom IMountableSeat implementation
   - Implements all required interface methods
   - `LocalEyePos` - camera position at NPC eye level
   - `SeatPosition` - follows NPC position
   - `MountableToTreeAttributes` - serializes for network sync
   - `CreateFromTree` - deserializes on client
   - `DidMount/DidUnmount` - lifecycle callbacks

2. **`PolisBuilderNpcSystem.cs`** - Possession commands and update loop
   - `CmdPossess` - creates seat, calls TryMount
   - `CmdUnpossess` - calls TryUnmount
   - `UpdatePossessions(float dt)` - routes controls, calculates WalkVector
   - `RegisterMountable` call in StartServerSide

3. **`PolisBuilderNpcHotkeys.cs`** - Hotkey bindings
   - Alt+U - possess
   - Alt+Shift+U - unpossess

---

## Diagnosis: Why Mount Doesn't Sync to Client

### Expected Flow (How Mounting Should Work)

```
Server                                    Client
------                                    ------
1. player.TryMount(seat)
   → Sets player.MountedOn = seat
   → Calls seat.DidMount(player)
   → Serializes seat via MountableToTreeAttributes

2. WatchedAttributes sync →               Receives player entity update
                                          → Sees "mountedOn" attribute
                                          → Looks up mount factory by className
                                          → Calls CreateFromTree(tree)
                                          → Sets player.MountedOn = newSeat

3. Client physics tick                    → Checks player.MountedOn
                                          → If not null, skip player physics
                                          → Position player at seat.SeatPosition

4. Client camera render                   → Check player.MountedOn
                                          → If not null, use seat.LocalEyePos
                                          → Render from NPC position
```

### Actual Flow (What's Happening)

```
Server                                    Client
------                                    ------
1. player.TryMount(seat) ✅
   → Sets player.MountedOn = seat ✅
   → Calls seat.DidMount(player) ✅
   → Serializes seat via MountableToTreeAttributes ✅

2. WatchedAttributes sync →               ❌ Something fails here
                                          ❌ player.MountedOn stays null

3. Client physics tick                    → player.MountedOn == null
                                          → Runs normal player physics
                                          → Player keeps moving

4. Client camera render                   → player.MountedOn == null
                                          → Uses player.LocalEyePos
                                          → Camera stays with player
```

### Possible Failure Points

1. **`TryMount()` doesn't set WatchedAttributes?**
   - Need to verify: Does TryMount call something like `WatchedAttributes.SetBytes("mountedOn", ...)`?
   - If not, we may need to manually trigger the sync

2. **`CreateFromTree` fails silently on client?**
   - Returns null if NPC entity not found
   - Client may not have the NPC entity loaded yet?
   - No error logging in CreateFromTree

3. **Client doesn't have the mountable factory registered?**
   - RegisterMountable only called server-side
   - Client might need its own registration?

4. **Seat serialization missing data?**
   - `MountableToTreeAttributes` only serializes: className, npcEntityId, seatId
   - Missing something the client needs?

---

## Research Findings (Resolved via btca)

### 1. The `TryMount` Sync Loop
**Finding:** `EntityAgent.TryMount()` is server-authoritative but relies on client-side reconstruction.
- **Server:** Serializes seat to `WatchedAttributes["mountedOn"]` and calls `MarkPathDirty`.
- **Client:** `EntityAgent` has a registered listener: `WatchedAttributes.RegisterModifiedListener("mountedOn", updateMountedState)`.
- **Logic:** `updateMountedState` calls `World.ClassRegistry.GetMountable(tree)`, which searches for a factory matching the `className` attribute.

### 2. Root Cause of Sync Failure
**Finding:** Standalone `IMountable` classes (like our `PolisPossessableSeat`) are not automatically known to the client's `ClassRegistry`.
- **Conclusion:** Unlike `EntityBehavior`, which is often registered in a common `Start()` method, `RegisterMountable` must be called explicitly on **both** sides. Because we only registered it on the server, `GetMountable` returned `null` on the client, leaving the player in a "half-mounted" state (mounted on server, free on client).

### 3. Physics & Camera Dependencies
**Finding:** Both systems are hardcoded to check the `MountedOn` property.
- **Physics:** `BehaviorPlayerPhysics.SimPhysics()` checks `if (eagent.MountedOn != null)` to skip movement and velocity calculations.
- **Camera:** `EntityPlayer.updateEyeHeight()` sets the camera position to `MountedOn.LocalEyePos` if it exists.
- **Preliminary Conclusion:** The "player walking" and "camera not switching" bugs were symptoms of the same cause: the client-side `MountedOn` property was never populated.

### 4. Comparison with Vanilla (Behavior-based)
**Finding:** Vanilla `EntityBehaviorRideable` uses a `seatdata` attribute on the **NPC entity** rather than `mountedOn` on the **Player entity** for its internal seat management.
- **Preliminary Conclusion:** Our standalone `TryMount(seat)` approach is valid and "lighter," but it places the synchronization burden entirely on the `mountedOn` attribute and the `ClassRegistry`, making dual-side registration non-negotiable.

---

## Current Status (Post-Fix)

**Status:** Client Sync RESOLVED via `api.RegisterMountable` on client side.
- Player entity now correctly freezes physics.
- Camera snaps to NPC position.
- Log confirms: `[polis] CreateFromTree: Reconstructing seat for NPC ...`

### New Issues Identified
1.  **Control Misalignment:** WASD inputs are inconsistent and drift relative to the camera view.
    *   *Observation:* Moving the mouse changes which key does what (e.g., Forward sometimes moves sideways or backward). The control vector is rotating differently than the camera view.
    *   *Suspected Cause:* Coordinate system mismatch between player view (Camera Yaw) and physics calculation, possibly involving incorrect Yaw sign or rotation origin.
2.  **Choppy Movement:** NPC movement feels laggy/stuttery.
    *   *Cause:* Lack of client-side prediction for the possessed entity.

### Resolved Since
1.  **Player Visibility:** Confirmed player model is hidden during possession (RenderTransform scale works).

### Open Questions (Next Steps)
1.  **WalkVector Math:** We need to verify the *exact* engine formula for `CalcMovementVectors` and how it relates to `ServerPos.Yaw`. The current implementation is clearly desynchronized from the view.
2.  **Client-Side Prediction:** Can we enable `EntityBehaviorControlledPhysics` on the client to predict movement, or do we need a custom solution?

---

## Follow-up Findings (2026-01-06)

### Engine WalkVector math (CalcMovementVectors)
Deep research confirmed the canonical movement conversion lives in `EntityControls.CalcMovementVectors(EntityPos pos, float dt)` and uses:
- `moveSpeed = dt * BaseMoveSpeed * MovespeedMultiplier * OverallSpeedMultiplier`
- local inputs: `dz` uses **Forward as negative**, `dx` uses **Right as positive**
- yaw rotation uses **pi/2 - yaw**, not a plain cos(yaw)/sin(yaw)
- diagonal normalization (1/sqrt(2)) when both x and z inputs are pressed
- yaw is in **radians**

Implication: our manual WalkVector calculation does not match engine math and can drift if yaw basis differs.

### Misalignment root cause
The possession code currently computes WalkVector using `npc.ServerPos.Yaw` while the camera yaw is based on the possessor. If NPC yaw lags or diverges, movement becomes misaligned (W changes with mouse).

Expected behavior: the yaw used in movement math should match the **camera/possessor yaw** while possessed.

Clarify design choice: if freelook is allowed (camera yaw != NPC body yaw), movement should still use **camera yaw** or explicitly use **body yaw** and document that W is "body-forward", not "camera-forward".

### Suggested correction (server-side)
Use engine math instead of custom math:
- Copy seat controls to `npc.ServerControls`
- Set `npc.ServerPos.Yaw = player.ServerPos.Yaw` each tick (lock yaw while possessed)
- Call `npcControls.CalcMovementVectors(npc.ServerPos, dt)`

This mirrors vanilla and should eliminate drift.

### Choppy movement cause
Possessed NPC is still a server-authoritative remote entity on the client. Camera rides a server-updated entity without client prediction, so motion appears stuttery.

### Suggested smoothing (client-side)
Vanilla rideables update motion in client render ticks (`OnRenderFrame` / `SeatsToMotion`). For possession:
- When local player is mounted on `PolisPossessableSeat`, run a client-side update loop that mirrors the control routing + `CalcMovementVectors` for the NPC on the client.
- Reconcile to server snapshots instead of hard snapping.

Target placement: client-side render tick or high-frequency client tick, scoped to the local player’s possessed NPC only.

### References (from deep research)
- `Vintagestory.API.Common.EntityControls.CalcMovementVectors(...)` (movement math)
- `Vintagestory.GameContent.EntityBehaviorRideable.OnRenderFrame()` (client-side smoothing pattern)

### Test Checklist (after changes)
- W moves forward relative to camera (no drift when rotating mouse)
- Diagonal movement speed is normalized (no faster diagonal strafe)
- NPC yaw matches camera yaw while possessed (if using yaw lock)
- Possession movement feels smooth (no visible server tick stutter)

---

## Resolution Plan

### 1. Register Mountable on Client (DONE)
Add the registration call to `StartClientSide` in `PolisBuilderNpcSystem.cs`. This ensures the `ClassRegistry` on the client knows how to deserialize `"polispossession"` seats.

```csharp
public override void StartClientSide(ICoreClientAPI api)
{
    // ... existing channel registration ...
    
    // FIX: Register the factory so client can reconstruct the seat from WatchedAttributes
    api.RegisterMountable(PolisPossessableSeat.MountableClassName, PolisPossessableSeat.CreateFromTree);
}
```

### 2. Verify with Logging (DONE)
Add debug logging to `PolisPossessableSeat.CreateFromTree` to confirm it is actually being called on the client side during the sync process.

### 3. Build & Verify (DONE)
- Rebuild and deploy.
- Test `/polis possess` command.
- Expectation:
  - Player view snaps to NPC.
  - Player entity freezes (physics disabled).
  - WASD moves NPC (already working via WalkVector fix).

---

## Git Commit Recommendation

### Commit Message

```
fix(possession): register mountable on client to enable sync

The possession system was failing to sync the mount state to the client because
the custom seat factory was only registered on the server.

- Added `api.RegisterMountable` to `StartClientSide`
- Added debug logging to `CreateFromTree` for verification

Fixes:
- Client physics not stopping (player walking alongside bot)
- Camera not switching to bot view
```
