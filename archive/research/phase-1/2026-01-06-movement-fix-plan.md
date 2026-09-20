# Movement Fix Implementation Plan

**Date:** 2026-01-06
**Status:** Ready to implement
**Based on:** Phase B investigation results (2026-01-06-npc-physics-investigation.md)

---

## Investigation Summary

### Key Findings from Parallel Agent

**Entity Type:**
- `EntityPlayerBot` (survival:playerbot)
- Has `EntityBehaviorControlledPhysics` (server + client)
- Has `EntityBehaviorInterpolatePosition` (client only)
- **Does NOT have `EntityBehaviorRideable`** ← No mount/gait system!

**Server-Side Physics (CORRECT):**
```
UpdatePossessions() → npc.ServerControls → CalcMovementVectors() →
EntityBehaviorControlledPhysics.OnPhysicsTick() → PModules (drag/accel) →
ServerPos.Motion (proper player-like movement)
```

**Client-Side Prediction (WRONG):**
```csharp
// PolisClientPossessionHandler.cs:118
possessedNpc.Pos.Motion.Set(predictControls.WalkVector);  // ❌ BYPASSES PHYSICS!
```

### Root Cause Identified

**The "horse-like" movement is caused by our own client prediction code:**

1. **Direct motion assignment** bypasses `EntityBehaviorControlledPhysics`
2. No drag or acceleration applied (just raw input vector)
3. Creates smooth continuous motion (vehicular feel)
4. Fights with `EntityBehaviorInterpolatePosition` causing conflicts
5. Server has proper physics, client doesn't = desync feel

**Original Theory (WRONG):** Mount/rideable behavior causing horse movement
**Actual Reality:** There's no rideable behavior - WE caused it ourselves!

---

## Solution: Remove Bad Prediction (Option 1)

### Approach

**Remove the direct motion assignment** and let the proper physics pipeline work:

**Current Code (PolisClientPossessionHandler.cs:85-122):**
```csharp
private void PredictNpcMovement(float dt, PolisPossessableSeat seat)
{
    // ... diagnostic logging ...

    // COPY: Controls from seat
    predictControls.Forward = seatControls.Forward;
    // ... (other controls)

    // PREDICT: Use CalcMovementVectors
    predictControls.CalcMovementVectors(possessedNpc.Pos, dt);

    // APPLY: Direct motion set (❌ PROBLEM!)
    possessedNpc.Pos.Motion.Set(predictControls.WalkVector);  // Line 118

    // TRACK: Save predicted position
    predictedPos = possessedNpc.Pos.XYZ.Clone();
}
```

**Fixed Approach:**
```csharp
private void PredictNpcMovement(float dt, PolisPossessableSeat seat)
{
    // REMOVED: All prediction logic
    // Let EntityBehaviorControlledPhysics handle motion on client
    // Let EntityBehaviorInterpolatePosition smooth server updates

    // Keep diagnostics for now (can remove later)
    // [Optional: Log that prediction is disabled]
}
```

### Why This Works

**Server (already correct):**
- Controls → Physics modules → Proper drag/acceleration → Player-like movement

**Client (after fix):**
- Server updates → `EntityBehaviorInterpolatePosition` → Smooth interpolation
- `EntityBehaviorControlledPhysics` also active client-side (reads same controls)
- No direct motion writes fighting the system

**Expected Result:**
- Responsive bipedal movement (matches server physics)
- No more smooth vehicular feel
- No tilting during turns (was from prediction conflict, not mount behavior)

---

## Implementation Steps

### Step 1: Disable Client Prediction

**File:** `PolisClientPossessionHandler.cs`

**Change:** Comment out or remove the problematic motion assignment

**Option A: Minimal change (comment out line 118):**
```csharp
// possessedNpc.Pos.Motion.Set(predictControls.WalkVector);  // DISABLED: Was bypassing physics
```

**Option B: Remove entire prediction function body:**
```csharp
private void PredictNpcMovement(float dt, PolisPossessableSeat seat)
{
    // DISABLED: Client prediction bypassed physics, causing smooth vehicular feel
    // Server-side EntityBehaviorControlledPhysics provides correct player-like movement
    // EntityBehaviorInterpolatePosition handles client smoothing
    return;
}
```

**Option C: Remove prediction entirely and reconciliation:**
```csharp
public void OnRenderFrame(float dt, EnumRenderStage stage)
{
    // ... FPS diagnostics ...

    if (!(player.MountedOn is PolisPossessableSeat seat)) return;

    possessedNpc = seat.Entity as EntityAgent;
    possessionSeat = seat;

    if (possessedNpc == null || !possessedNpc.Alive) return;

    // REMOVED: PredictNpcMovement(dt, seat);
    // REMOVED: ReconcileWithServer(dt);

    // Let EntityBehaviorInterpolatePosition handle all smoothing
}
```

**Recommended:** Option B (clear disable with comment explaining why)

### Step 2: Build and Test

**Build:**
```bash
VINTAGE_STORY="..." dotnet build -c Release && cp -r bin/Release/Mods/polis-builder-npc ../vsdata/Mods/
```

**Test Scenarios:**
1. **Outdoor movement:** Walk, strafe, diagonal - feel responsive?
2. **Movement start/stop:** Does acceleration/deceleration feel natural?
3. **Turning:** No sideways tilting?
4. **Indoor movement:** Works same as outdoor?
5. **Network lag:** Any visible stuttering/teleporting?

**Success Criteria:**
- ✅ Movement feels responsive (like controlling player directly)
- ✅ No smooth vehicular feel
- ✅ No tilting during turns
- ✅ Acceleration/deceleration feels natural
- ✅ No obvious stuttering (interpolation working)

### Step 3: Document Results

**If successful:**
- Update findings document with test results
- Note that server physics was correct all along
- Remove or clean up unused prediction code

**If needs improvement:**
- Document what feels wrong (lag? stuttering?)
- Consider Option 2: Proper physics-based prediction
- May need to replicate PModule drag/accel client-side

---

## Fallback: Option 2 (Proper Physics Prediction)

### If Option 1 Feels Too Laggy

**Instead of removing prediction, apply proper physics:**

```csharp
private void PredictNpcMovement(float dt, PolisPossessableSeat seat)
{
    // ... (control copying same as before)

    predictControls.CalcMovementVectors(possessedNpc.Pos, dt);

    // Apply drag and acceleration (mimic PModuleOnGround)
    double groundDrag = 0.7;  // From research
    double walkX = predictControls.WalkVector.X;
    double walkZ = predictControls.WalkVector.Z;

    // Acceleration toward target
    double motionDeltaX = walkX - possessedNpc.Pos.Motion.X;
    double motionDeltaZ = walkZ - possessedNpc.Pos.Motion.Z;

    possessedNpc.Pos.Motion.X += motionDeltaX * groundDrag;
    possessedNpc.Pos.Motion.Z += motionDeltaZ * groundDrag;

    // Apply drag
    possessedNpc.Pos.Motion.X *= (1 - groundDrag);
    possessedNpc.Pos.Motion.Z *= (1 - groundDrag);

    predictedPos = possessedNpc.Pos.XYZ.Clone();
}
```

**Pros:** Matches server physics, keeps responsiveness
**Cons:** More complex, need to match PModule math exactly

---

## Expected Outcomes

### Best Case (Option 1 Works)

**Movement Feel:**
- Responsive start/stop (not smooth)
- Natural acceleration/deceleration
- Bipedal walking feel (not vehicular)
- No tilting in turns

**Performance:**
- Smooth enough via interpolation
- No visible stuttering
- Matches server state

**Result:** Ship it, clean up code

### Acceptable Case (Option 1 Needs Refinement)

**Movement Feel:**
- Correct physics feel but slightly laggy
- Occasional position snaps on high latency
- Still better than vehicular feel

**Next Step:**
- Implement Option 2 (proper physics prediction)
- Test again

**Result:** More work but achievable

### Worst Case (Unexpected Issues)

**If neither option works:**
- May need to investigate `EntityBehaviorControlledPhysics` configuration
- Check if playerbot has different physics settings
- Verify controls are being consumed correctly

**Unlikely** based on investigation evidence.

---

## Comparison to Original Plan

### What We Thought (WRONG)

**Original Analysis:**
- Mount/rideable behavior causing horse movement
- Need to bypass mounting system
- Apply player physics manually
- Disable gait/seat motion

**Would have been:**
- Complex manual physics implementation
- Bypassing mount system
- Fighting with existing systems
- High complexity, uncertain success

### What We Discovered (CORRECT)

**Actual Problem:**
- Our own client prediction bypassing physics
- Server physics already correct
- No rideable behavior to fight
- Simple one-line fix

**Actual Solution:**
- Remove one problematic line of code
- Let existing systems work properly
- Low complexity, high confidence

**Time Saved:** Hours of complex implementation avoided by proper investigation!

---

## Risk Assessment

### Option 1: Remove Prediction

**Risk Level:** Low

**Risks:**
- May feel laggy on high-latency connections
- Interpolation might not be smooth enough

**Mitigations:**
- Test on local/LAN first (low latency baseline)
- Option 2 available as fallback
- Can always restore prediction with proper physics

### Option 2: Proper Physics Prediction

**Risk Level:** Medium

**Risks:**
- Math might not match server exactly (drift)
- Missing edge cases (jumping, falling, etc.)
- More code to maintain

**Mitigations:**
- Use known values from research (groundDrag = 0.7)
- Test thoroughly
- Keep server as authority (reconciliation)

---

## Success Metrics

**Movement Quality:**
- [ ] Feels responsive (not smooth/floaty)
- [ ] Natural acceleration/deceleration
- [ ] No tilting during turns
- [ ] Matches player movement feel

**Technical Correctness:**
- [ ] No direct `Pos.Motion` writes (respects physics)
- [ ] Interpolation working smoothly
- [ ] Server remains authoritative

**User Experience:**
- [ ] No visual stuttering
- [ ] No geometry clipping issues
- [ ] Indoor and outdoor movement consistent

---

## Next Steps After Implementation

1. **Test thoroughly** (scenarios above)
2. **Document results** in findings doc
3. **Clean up code:**
   - Remove unused prediction code if Option 1 works
   - Remove diagnostic logging (or make conditional)
   - Update comments to reflect actual behavior
4. **Commit changes** with clear message
5. **Move to Phase 2** (task system) if successful

---

## Lessons Learned (Pre-Implementation)

1. **Investigation pays off** - Parallel agent saved hours of wrong implementation
2. **Don't assume** - "Horse-like" wasn't from mounts, was from our code
3. **Server was right** - Physics pipeline working correctly all along
4. **Client prediction is tricky** - Bypassing systems causes unexpected behavior
5. **Simple solutions exist** - One line removal vs hours of complex physics code

**The best code is the code you delete.**
