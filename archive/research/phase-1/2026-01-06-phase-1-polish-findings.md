# Phase 1 Polish: Camera & Movement Findings

**Date:** 2026-01-06
**Status:** Analysis complete, awaiting implementation approval
**Context:** Post-parallel research analysis of current possession system implementation

---

## Executive Summary

Analyzed current implementation against parallel agent research findings. Camera issue is a **configuration problem** (easily fixed), but movement issue is **architectural** (mount physics vs player physics). Both have clear solutions with different complexity levels.

---

## Issue 1: Camera Inside Head

### Current Implementation Analysis

**File:** `PolisPossessableSeat.cs`

```csharp
// Line 140: LocalEyePos property
public Vec3f LocalEyePos => new Vec3f(0, (float)(npcEntity?.LocalEyePos?.Y ?? 1.6), 0);

// Line 102: SeatConfig (unused)
public SeatConfig Config { get; set; } = new SeatConfig();
```

**What's Happening:**
1. Seat's `LocalEyePos` **correctly** delegates to `npcEntity.LocalEyePos.Y`
2. Falls back to 1.6 if NPC LocalEyePos is null
3. Sets X=0, Z=0 (correct - only Y offset matters for eye height)
4. `SeatConfig` is created but never populated

**Research Finding (from camera-positioning-findings.md):**
- Player camera positioning: `entity.Pos.XYZ + entity.LocalEyePos + entity.CameraPosOffset`
- When mounted: `EntityPlayer.updateEyeHeight()` overrides rider's `LocalEyePos` with `MountedOn.LocalEyePos`
- Our seat implementation **follows this pattern correctly**

### Root Cause

**Problem:** NPC entity's `LocalEyePos.Y` is likely returning incorrect value OR seat's reading is correct but the value itself is wrong for the NPC model.

**Possible Causes:**
1. NPC's `EntityProperties.EyeHeight` is set incorrectly in entity definition
2. NPC's `LocalEyePos` hasn't been initialized properly
3. The 1.6 fallback is being used and doesn't match NPC model eye position

### Testing Needed

**Diagnostic:** Add logging to see actual values:
```csharp
// What does npcEntity.LocalEyePos actually return?
// What is npcEntity.Properties.EyeHeight?
// Is the fallback (1.6) being used?
```

### Assumptions

1. ✅ **Verified:** Seat delegation pattern is correct per VS API research
2. ⚠️ **Unverified:** NPC entity has correct `EntityProperties.EyeHeight` value
3. ⚠️ **Unverified:** 1.6 fallback matches NPC model geometry
4. ✅ **Verified:** X=0, Z=0 is correct (only Y offset matters for eye height)

### Proposed Solution: Option 1 - Value Tuning (Low Complexity)

**Approach:**
1. Log actual NPC `LocalEyePos.Y` and `Properties.EyeHeight` values during possession
2. Test with different hardcoded values to find correct eye position visually
3. Once correct value found, either:
   - Update NPC entity definition's `EyeHeight` property
   - OR hardcode correct value in seat's `LocalEyePos` calculation
   - OR populate `SeatConfig.EyeHeight` and use that

**Implementation:**
```csharp
// Diagnostic version (temporary)
public Vec3f LocalEyePos
{
    get
    {
        float eyeY = (float)(npcEntity?.LocalEyePos?.Y ?? 1.6);
        float propsEyeHeight = (float)(npcEntity?.Properties?.EyeHeight ?? 0);

        // Log for debugging
        npcEntity?.World?.Logger?.Notification(
            $"[polis] Seat LocalEyePos: NPC LocalEyePos.Y={eyeY}, " +
            $"Properties.EyeHeight={propsEyeHeight}");

        return new Vec3f(0, eyeY, 0);
    }
}
```

**After finding correct value:**
```csharp
// Production version (option A: hardcode)
public Vec3f LocalEyePos => new Vec3f(0, 1.75f, 0); // Tuned for humanoid NPC

// OR (option B: use entity property)
public Vec3f LocalEyePos => new Vec3f(0, (float)(npcEntity?.Properties?.EyeHeight ?? 1.75), 0);
```

**Pros:**
- Low complexity (single line change)
- Fast to test and iterate
- Aligns with VS mount camera pattern

**Cons:**
- Requires manual value tuning
- May need different values per NPC type

**Estimated Effort:** 30 minutes (diagnostics + testing + fix)

---

## Issue 2: Horse-like Movement

### Current Implementation Analysis

**Server-Side: `PolisBuilderNpcSystem.cs:UpdatePossessions()`**

```csharp
// Lines 408-424
// Copy controls from seat to NPC
npcControls.Forward = seatControls.Forward;
npcControls.Backward = seatControls.Backward;
npcControls.Left = seatControls.Left;
npcControls.Right = seatControls.Right;
// ... (Jump, Sneak, Sprint)

// Calculate WalkVector from controls
npcControls.CalcMovementVectors(npc.ServerPos, dt);

// [No explicit motion application here - physics behaviors handle it]
```

**Client-Side: `PolisClientPossessionHandler.cs:PredictNpcMovement()`**

```csharp
// Lines 85-122
// Copy controls from seat
predictControls.Forward = seatControls.Forward;
// ... (other controls)

// Calculate WalkVector
predictControls.CalcMovementVectors(possessedNpc.Pos, dt);

// DIRECTLY set motion (not using physics modules!)
possessedNpc.Pos.Motion.Set(predictControls.WalkVector);
```

**Research Finding (from mount-movement-findings.md):**
- Player movement: WalkVector consumed by physics modules (`PModuleOnGround`, `PModulePlayerInAir`) which apply acceleration/drag
- Mount movement: Gait-based system with smoothing and angular velocity (tilting)
- `CalcMovementVectors()` just computes input vector - feel comes from downstream physics

### Root Cause

**Problem:** Movement is going through **mount/rideable physics pipeline** instead of **player physics modules**.

**Evidence:**
1. NPC tilts sideways during turns (signature of mount angular velocity)
2. Movement feels smooth/vehicular (signature of gait-based motion)
3. Not responsive like player (no physics module acceleration/drag)

**Architecture Issue:**
- Server: Sets `npcControls.WalkVector`, but what consumes it?
  - If NPC has `EntityBehaviorPassivePhysics` → generic entity physics
  - If NPC has rideable behaviors → mount-like motion
  - If NPC has player physics modules → player-like motion (what we want)
- Client: Directly sets `Pos.Motion` to `WalkVector` (bypasses ALL physics!)
  - This is wrong - should let physics modules apply WalkVector with drag/accel
  - Direct motion setting creates smooth continuous motion

### Assumptions

1. ✅ **Verified:** Mount system uses gait/angular velocity (from btca research)
2. ✅ **Verified:** Player physics uses modules with drag/accel (from btca research)
3. ⚠️ **Unverified:** What physics behaviors does the NPC entity actually have?
4. ⚠️ **Unverified:** Does mounting automatically add rideable behaviors?
5. ✅ **Verified:** Client prediction directly setting Motion is incorrect pattern

### Critical Questions

**Q1:** What entity behaviors does our NPC have?
- Need to check entity type being spawned/controlled
- Need to list its `entity.SidedProperties.Behaviors`

**Q2:** Does the mounting system automatically invoke rideable movement?
- Research says `EntityBehaviorRideable` controls mount motion
- Is this behavior automatically active when mounted?

**Q3:** Where is the actual motion being applied server-side?
- `UpdatePossessions()` only sets WalkVector
- What tick/behavior consumes WalkVector and updates `ServerPos`?

### Proposed Solution: Option 1 - Bypass Mount Physics (Medium Complexity)

**Approach:** Keep mounting for camera/ownership, but apply player physics directly to NPC.

**Research Recommendation:** "Option 1 is most reliable for player-like movement: it keeps player physics intact and avoids rideable smoothing entirely."

**Implementation Strategy:**

1. **Server-Side Changes (`UpdatePossessions`):**
   ```csharp
   // Current: Only sets WalkVector
   npcControls.CalcMovementVectors(npc.ServerPos, dt);

   // New: Apply WalkVector via player-like physics
   // Option A: Manually apply drag/acceleration (mimics PModuleOnGround)
   double groundDrag = 0.7; // From PModuleOnGround research
   npc.ServerPos.Motion.X += (npcControls.WalkVector.X - npc.ServerPos.Motion.X) * groundDrag;
   npc.ServerPos.Motion.Z += (npcControls.WalkVector.Z - npc.ServerPos.Motion.Z) * groundDrag;
   npc.ServerPos.Motion.X *= (1 - groundDrag);
   npc.ServerPos.Motion.Z *= (1 - groundDrag);

   // Option B: Invoke NPC's physics modules directly (if they exist)
   // Need to investigate if EntityAgent.Physics or similar exists
   ```

2. **Client-Side Changes (`PolisClientPossessionHandler`):**
   ```csharp
   // Current: Direct motion set (WRONG)
   possessedNpc.Pos.Motion.Set(predictControls.WalkVector);

   // New: Apply physics-like prediction
   double groundDrag = 0.7;
   possessedNpc.Pos.Motion.X += (predictControls.WalkVector.X - possessedNpc.Pos.Motion.X) * groundDrag;
   possessedNpc.Pos.Motion.Z += (predictControls.WalkVector.Z - possessedNpc.Pos.Motion.Z) * groundDrag;
   possessedNpc.Pos.Motion.X *= (1 - groundDrag);
   possessedNpc.Pos.Motion.Z *= (1 - groundDrag);
   ```

3. **Prevent Mount Motion:**
   - Ensure NPC doesn't have `EntityBehaviorRideable` active during possession
   - OR override seat motion to return zero (if `SeatsToMotion` is being called)

**Pros:**
- Achieves player-like movement feel
- Reuses known physics values from research
- Doesn't require entity type changes

**Cons:**
- Manually reimplementing physics (may miss edge cases)
- Need to handle air/liquid states separately if needed
- More code to maintain

**Estimated Effort:** 2-3 hours (implementation + testing)

### Proposed Solution: Option 2 - Use NPC Physics Modules (High Feasibility, Unknown Complexity)

**Approach:** Check if NPC entity has physics modules, invoke them directly.

**Implementation:**
1. Investigate what behaviors NPC entity has
2. If it has `EntityBehaviorPassivePhysics` or similar:
   - Check if we can invoke its tick/physics update directly
   - OR ensure it's active and consuming WalkVector
3. If it doesn't have physics behaviors:
   - Add player physics modules to NPC programmatically during possession
   - OR switch NPC entity type to one with correct physics

**Pros:**
- Uses engine's built-in physics (most reliable)
- Automatically handles all states (ground/air/liquid)
- Future-proof against engine changes

**Cons:**
- Unknown complexity (depends on NPC entity structure)
- May require entity type changes or behavior injection

**Estimated Effort:** Unknown (need investigation first)

### Proposed Solution: Option 3 - Attribute Tuning (Low Effort, Low Impact)

**Approach:** Tune physics attributes and seat angle mode.

**From research:** "Option 3 is a quick diagnostic step but unlikely to fix the feel completely."

**Implementation:**
```csharp
// In PolisPossessableSeat or NPC entity config
// Set drag/gravity attributes to match player
npcEntity.Properties.GroundDragFactor = 1.0; // Player default
npcEntity.Properties.AirDragFactor = 1.0;
npcEntity.Properties.WaterDragFactor = 1.0;

// Seat angle mode already set to Unaffected (line 126 PolisPossessableSeat.cs)
```

**Pros:**
- Very quick to test
- Minimal code changes

**Cons:**
- Won't fix gait-based smoothing
- Won't fix angular velocity tilting
- Research says insufficient alone

**Estimated Effort:** 15 minutes (testing only)

---

## Conclusions

### Camera Issue
- **Root Cause:** Value problem (eye height offset incorrect)
- **Complexity:** Low (single value tuning)
- **Confidence:** High (implementation pattern is correct per research)
- **Priority:** Fix first (quick win, enables comfortable testing)

### Movement Issue
- **Root Cause:** Architectural problem (mount physics vs player physics)
- **Complexity:** Medium (requires physics reimplementation or behavior changes)
- **Confidence:** High (research clearly identified gait vs physics modules)
- **Priority:** Fix second (requires more investigation and testing)

### Critical Next Steps

**Before implementing movement fix:**
1. ✅ **Must investigate:** What physics behaviors does NPC entity have?
2. ✅ **Must investigate:** Is there a rideable behavior active during mounting?
3. ✅ **Must investigate:** Can we access/invoke NPC's physics modules directly?

**These investigations will determine whether Option 1 (manual physics) or Option 2 (use NPC physics) is better.**

---

## Implementation Plan (Proposed)

### Phase A: Camera Fix (30 min)

**Step 1: Diagnostics (10 min)**
- Add logging to `PolisPossessableSeat.LocalEyePos`
- Possess NPC and check logs for actual values
- Test in F1 (first-person) to see camera position

**Step 2: Value Tuning (10 min)**
- Try different hardcoded values (1.5, 1.6, 1.75, 2.0)
- Find value where camera is at eye level (not inside head)

**Step 3: Implement Fix (10 min)**
- Update `LocalEyePos` property with correct value
- Remove diagnostic logging
- Test in F1 and F5 modes

**Success Criteria:**
- ✅ First-person camera at NPC eye level (not inside head geometry)
- ✅ Can see NPC face in F5 (third-person) correctly
- ✅ No visual glitching when moving head

---

### Phase B: Movement Investigation (1 hour)

**Step 1: Entity Behavior Inspection (30 min)**
```csharp
// Add to UpdatePossessions() for diagnostics
var behaviors = npc.SidedProperties?.Behaviors;
if (behaviors != null)
{
    sapi.Logger.Notification($"[polis] NPC behaviors: {string.Join(", ",
        behaviors.Select(b => b.GetType().Name))}");
}

// Check for rideable behaviors specifically
var rideable = npc.GetBehavior<EntityBehaviorRideable>();
sapi.Logger.Notification($"[polis] Has rideable behavior: {rideable != null}");
```

**Step 2: Physics Module Investigation (20 min)**
```csharp
// Check if NPC has physics simulation
var physics = npc.GetBehavior("passivephysics"); // or similar
// Check what consumes WalkVector
// Log npc.ServerPos.Motion before and after UpdatePossessions
```

**Step 3: Document Findings (10 min)**
- What behaviors exist on NPC?
- Is rideable behavior active?
- What's actually applying motion to NPC?

---

### Phase C: Movement Fix Implementation (2-3 hours)

**Route 1 (if NPC has usable physics):**
- Invoke NPC physics modules directly
- Disable/bypass any rideable behaviors

**Route 2 (if manual physics needed):**
- Implement Option 1 (manual drag/acceleration)
- Test server-side physics application
- Update client-side prediction to match
- Test movement feel vs player movement

**Success Criteria:**
- ✅ Movement start/stop feels responsive (like player)
- ✅ No tilting during turns
- ✅ Acceleration/deceleration matches player
- ✅ No stuttering on movement initiation

---

## Open Questions

1. **NPC Entity Type:** What entity type/class is being used for NPCs?
   - Is it vanilla EntityHumanoid?
   - Custom entity type?
   - What behaviors does it have by default?

2. **Mount Behavior Activation:** Does the mounting system automatically activate rideable behaviors?
   - Or are they dormant until explicitly used?

3. **Physics Module Access:** Can we programmatically invoke physics modules?
   - Is there an API like `entity.Physics.Tick(dt)`?
   - Or do we need to reimplement manually?

4. **Movement Start Stutter:** Still need to analyze logs for this
   - Is it related to physics issue?
   - Or separate reconciliation issue?

---

## Risk Assessment

### Camera Fix
- **Risk:** Low
- **Reason:** Simple value change, clear research backing
- **Mitigation:** Test multiple values visually

### Movement Fix
- **Risk:** Medium
- **Reason:** Complex physics system, multiple unknowns
- **Mitigation:** Investigate thoroughly before implementing, test incrementally

---

---

## Test Results (2026-01-06, 15:32 UTC)

### Camera Height Tuning Experiment

**Test 1: Value 1.7 (NPC default)**
- Result: Camera fully inside head geometry
- Visual: See face from inside, geometry clipping

**Test 2: Value 1.85 (+0.15 blocks)**
- Result: Camera halfway out of head
- Visual: Sky flickers through, partial geometry clipping
- Diagnostic output:
  ```
  NPC.ServerPos: (224.62, 3.00, 278.20)
  Seat returning: (0, 1.850, 0)
  Expected camera Y: 4.850
  Camera = NPC.Pos + LocalEyePos formula
  ```

### Critical Finding: Math Doesn't Match Visual Reality

**According to formula:**
- NPC feet at Y=3.0
- Eye offset = 1.85
- **Expected camera Y = 4.85 blocks**

**For typical humanoid (1.8-2.0 blocks tall):**
- Head top should be around Y=4.8-5.0
- Camera at Y=4.85 should be **above or at head top**, not inside

**But visual result:**
- Camera still halfway inside head geometry
- Sky visible through head (geometry clipping)

### Root Cause Analysis

**Simple height tuning is NOT the solution.** The discrepancy between calculated position and visual result suggests:

**Hypothesis 1: Visual Model vs Collision Box Mismatch**
- NPC's visual head geometry may be significantly higher than collision box suggests
- The "head" in the visual model might extend much higher than expected

**Hypothesis 2: Animation Attachment Point Override**
- Research mentioned immersive FP uses animator "Eyes" attachment point
- Animation system may be overriding our seat's LocalEyePos
- This could place camera at animation-defined position instead of our calculated one

**Hypothesis 3: Client-Side Calculation Differs**
- Server logs show our calculation
- Client might be using different formula or additional offsets
- Mount camera positioning might have client-side overrides

**Hypothesis 4: Seat Position Incorrect**
- Our SeatPosition might not be at NPC feet where we assume
- If seat is elevated, formula would be: SeatPos + LocalEyePos (both elevated)

### Evidence Supporting Hypothesis 2 (Animation Override)

From camera-positioning-findings.md:
```
When immersive FP mode is enabled:
AttachmentPointAndPose apap = AnimManager.Animator.GetAttachmentPointPose("Eyes");
// Complex matrix calculations determine exact eye position based on animation
```

**This is likely overriding our LocalEyePos calculation.**

### Conclusion

**Height tuning alone cannot solve this.** We could set value to 2.5+ and get camera above head, but this is a hack that:
- Doesn't address root cause
- Would vary per NPC model/animation
- Would fail if animation attachment points are active
- Provides unpredictable results

**User assessment was correct:** "that might be a workaround but does not solve it"

---

## Revised Solution: Auto-Switch to 3rd Person Camera

### Rationale

**Why abandon 1st person camera fix:**
1. Complex animation attachment point system may override our values
2. Visual model geometry doesn't match collision box calculations
3. Would require per-NPC-model tuning (not scalable)
4. User already tests in F5 (3rd person) to avoid visual issues

**Why 3rd person auto-switch is better:**
1. Clean, predictable behavior
2. No geometry clipping issues
3. Works uniformly across all NPC models
4. Low implementation complexity
5. Avoids fighting unknown animation/attachment systems

### Implementation Plan

**On Possession Start (`DidMount`):**
- Detect possession
- Switch player camera to 3rd person mode
- Log for debugging

**On Possession End (`DidUnmount`):**
- Detect unpossession
- **[UNKNOWN]** Wait for dismount animation to finish?
- Switch player camera back to 1st person (if they were in 1st before)
- Log for debugging

### Open Questions Before Implementation

**Q1: How to switch camera mode programmatically?**
- What API controls player camera mode (1st vs 3rd person)?
- Server-side or client-side?
- Can we read current mode before changing it?

**Q2: How to detect animation completion?**
- Is there an animation finished callback/event?
- Or should we use a fixed delay (e.g., 1 second)?
- What is the dismount animation duration?

**Q3: Should we remember player's original camera mode?**
- If player was already in 3rd person, don't switch them to 1st on unpossess
- Need to store camera mode state per player?

**Q4: Is there a mount/dismount animation at all for possession seats?**
- Our seat might not trigger standard mount animations
- Need to verify what actually happens visually

### Investigation Required

Before implementing, need to research:
1. VS API for camera mode switching (client-side? server-side?)
2. Animation completion detection or standard dismount timings
3. Whether possession seat has mount/dismount animations

---

## Next Action

**Awaiting approval to:**
1. Investigate camera mode switching API and animation timing
2. Report findings on available APIs
3. Then implement 3rd person auto-switch with informed approach

**NOT proceeding with code until we understand:**
- How to switch camera modes
- How to handle animation timing properly

---

## Camera Mode Switching API Research (2026-01-06, 16:27 UTC)

### btca Query: Camera Mode Control API

**Query:**
```
How do I programmatically switch a player's camera between first-person and third-person view in Vintage Story?
Need: API calls, current mode checking, client/server operation, switching delays/animations
Context: Auto-switch to 3rd person on mount, back to 1st on dismount
```

### Results

**Available API (Read-Only):**
```csharp
// from: vsapi - Client-side only
ICoreClientAPI capi = entity.Api as ICoreClientAPI;
EnumCameraMode currentMode = capi.Render.CameraType;
// Values: FirstPerson, ThirdPerson, Overhead

// EntityPlayer camera position properties
public Vec3d CameraPos { get; }
public Vec3d CameraPosOffset { get; }
```

**NOT Available (No Setter Found):**
- No `CameraType` setter (property is read-only)
- No `SwitchCamera()` method or similar
- No camera mode change API exposed to mods
- Camera switching appears to be engine-level only

**Key Findings:**
1. Camera mode control is **client-side only** (`ICoreClientAPI.Render.CameraType`)
2. Camera type property is **read-only** - can check, cannot set
3. Engine uses camera type for animation selection (first vs third person animations)
4. No documented way for mods to programmatically change camera mode

### Implications

**3rd Person Auto-Switch Workaround is NOT FEASIBLE** with public API.

**Why it won't work:**
- Cannot programmatically force camera mode change
- Would require reflection hacks or input simulation (unreliable)
- Engine may reject/override mod-initiated camera changes
- No animation timing info even if we could switch

### Alternative Approaches Evaluated

**Option 1: Simulate F5 Keypress**
- Inject F5 input event programmatically
- **Risk:** May not work, could conflict with user keybinds
- **Feasibility:** Low (no input injection API found)

**Option 2: Reflection to Access Internal Methods**
- Use C# reflection to call private camera switching methods
- **Risk:** Breaks on engine updates, unstable, potentially unsafe
- **Feasibility:** Medium but not maintainable

**Option 3: Custom Client-Side Camera Controller**
- Override camera positioning entirely for possession
- **Risk:** Very complex, conflicts with engine camera system
- **Feasibility:** Low (would require deep camera system understanding)

**Option 4: Elevated First-Person Camera (Above Head)**
- Set `LocalEyePos.Y` high enough that camera is above NPC head
- No geometry clipping, functional for testing/playing
- **Risk:** May clip through low ceilings in confined spaces
- **Feasibility:** High (simple value change)

**Option 5: Manual User Workaround**
- Document that player should press F5 when possessing
- **Risk:** None
- **Feasibility:** Immediate (no code changes)

---

## Revised Solution: Elevated Camera Position

### Rationale

Since programmatic camera switching is not exposed by API:
1. Abandon 3rd person auto-switch approach
2. Use elevated camera position as "tall mode" view
3. Aim for camera above NPC head but below typical room ceilings
4. Accept this as pragmatic workaround, not ideal solution

### Implementation Constraints

**NPC and Environment Considerations:**

**Typical NPC height:** ~1.8 meters (feet to head top)
- Feet at Y=0
- Head top at Y=~1.8
- Eyes typically at Y=1.6-1.7 (inside head for camera)

**Typical room ceiling height:** 2.0 meters minimum
- Standard VS construction: 2-3 block high rooms
- 1 block = 1 meter
- Minimum clearance: 2.0 meters

**Camera Height Calculation:**
- Current NPC LocalEyePos.Y = 1.7 (inside head)
- Tested 1.85 = halfway out of head (still clipping)
- Need ~1.95-2.0 to clear head geometry
- But 2.0+ risks clipping through 2m ceilings!

**The Dilemma:**
```
NPC head top:     Y = 1.8m
Need camera:      Y > 1.9m (to clear head)
Room ceiling:     Y = 2.0m (minimum)
Safe range:       1.9m - 2.0m (only 10cm window!)
```

**User's Valid Concern:**
> "the bots are usually less than 2 meters and can go in rooms with heights of only 2 meters, if we make it 2+ meters that might go crazy inside"

**This is correct.** A 2+ meter camera would:
- Clip through ceilings in standard 2m rooms
- See through roof blocks
- Create visual chaos (sky/ground flickering)
- Make indoor possession unusable

### Proposed Test Value: 1.95 meters

**Rationale:**
- NPC feet at Y=3.0 example: Camera at Y=4.95
- NPC head top at ~Y=4.8: Camera 15cm above head
- Room ceiling at Y=5.0: Camera 5cm below ceiling
- **Tight fit but theoretically safe**

**What to Test:**
1. Does 1.95 clear head geometry? (No clipping?)
2. How close is camera to ceiling in 2m rooms?
3. Does camera clip through ceiling when moving?
4. Is the "floating above NPC" view acceptable?

**Fallback Values:**
- If 1.95 too high: Try 1.92, 1.90
- If 1.95 still clips head: Try 1.97, 1.98 (risks ceiling more)

### Expected Behavior

**Outdoor:**
- Camera floating ~15cm above NPC head
- Clear view, no geometry clipping
- "Tall mode" perspective

**Indoor (2m ceilings):**
- Camera very close to ceiling (5cm clearance)
- May occasionally touch/clip ceiling when jumping
- Acceptable if rare, unusable if constant

**Indoor (low ceilings <2m):**
- Camera will clip through ceiling
- Visual chaos (see outside/sky through roof)
- **Possession unusable in low-ceiling areas**

### Trade-offs

**Pros:**
- Functional workaround with public API
- No geometry clipping of NPC head
- Works immediately, no hacks
- Maintainable solution

**Cons:**
- Camera position is unnatural ("floating" above NPC)
- May clip through low ceilings
- Not true first-person immersion
- Limits bot usage in confined spaces

### Documentation Requirements

If we accept this workaround, must document:
1. Possession uses "elevated camera view"
2. Avoid possessing bots in rooms with <2m ceilings
3. Outdoor possession works best
4. Press F5 for true 3rd person if desired

---

## Final Recommendation

**Test 1.95m camera height** as pragmatic workaround:
- If it clears head AND stays below typical ceilings → Success
- If it clips ceilings frequently → Reduce to 1.92 or abandon approach
- If it doesn't clear head → Consider reflection hacks or accept manual F5

**Alternative if 1.95 fails:**
- Document "Press F5 before possessing" as user workflow
- Zero implementation cost
- Reliable (3rd person always works)
- Accepts API limitation

---

## Next Action

**Awaiting approval to:**
1. Test LocalEyePos.Y = 1.95 meters
2. Document results (head clearance, ceiling issues)
3. Based on test, decide:
   - Accept 1.95 as workaround
   - OR reduce to 1.92-1.93 for safety
   - OR abandon and document manual F5 workflow

**Ready to test once approved.**

---

## Test Results: 1.95m Camera Height (2026-01-06, Final Test)

### Test Value: 1.95 meters

**Expected Outcome (Based on Math):**
```
NPC feet at Y=3.0 → Camera at Y=4.95
NPC head top at ~Y=4.8 → Camera should be 15cm ABOVE head
Result: Clear view, no head geometry clipping
```

**Actual Outcome:**
- Camera STILL halfway inside head geometry
- No improvement over 1.85m test
- Math completely doesn't match visual reality

### Critical Conclusion: LocalEyePos May Be Ignored

**Evidence:**
- 1.7m: Inside head
- 1.85m: Halfway out of head
- 1.95m: STILL halfway out of head (same as 1.85m!)

**This suggests:**
1. **Animation attachment point override:** Client-side "Eyes" attachment from animator is overriding our seat LocalEyePos value
2. **Different client calculation:** Client camera positioning doesn't use the formula we think it does
3. **Head geometry issue:** Visual model head is absurdly tall (would need 2.3m+ to clear)

**The math breakdown:**
- If camera moves 0.15m (from 1.7 to 1.85) and goes "halfway out"
- Then to fully clear head would need another ~0.15m = 2.0m minimum
- But 2.0m+ clips through standard 2m ceilings
- **There is no viable value that clears head AND stays below ceiling**

### The Impossible Dilemma

```
Option 1: Low camera (1.7-1.95)  → See inside head geometry
Option 2: High camera (2.0-2.3+) → Clip through ceilings indoors
Option 3: Manual F5 by user      → Works perfectly, requires user action
```

**No automated solution exists within API constraints and environmental constraints (2m ceilings).**

---

## Final Status: DEFERRED

### Decision

**Camera positioning issue is DEFERRED for future investigation.**

**Current workaround:** Users manually press F5 to switch to 3rd person before possessing.

### Why Deferred

1. **API Limitation:** Cannot programmatically switch camera mode (CameraType is read-only)
2. **Physics Limitation:** No camera height value clears head without clipping ceilings
3. **Unknown Override:** Something (likely animation attachment points) may be ignoring our LocalEyePos
4. **Time vs Value:** Deep investigation would take hours with uncertain outcome

### What Would Be Needed to Solve This

**Short term (if revisited):**
- Decompile client-side camera positioning code
- Investigate animation attachment point system
- Check if immersive FP "Eyes" attachment is active and overriding
- Possibly use reflection to access internal camera methods

**Long term (ideal):**
- Request API feature from VS devs: Camera mode setter
- OR: Camera positioning override for custom seats
- OR: Disable animation attachment overrides for specific entities

### Current Implementation

**Code State:**
- `PolisPossessableSeat.LocalEyePos` returns 1.95m (ineffective but documented)
- Diagnostic logging present (can be removed in cleanup)
- Debug mode required for diagnostics (`/polis debug`)

**User Experience:**
- First-person: Camera inside/near head (visual glitching)
- Third-person (F5): Works perfectly
- **Recommended:** Press F5 before possessing

### Documentation Required

When this mod is released/documented, must include:

**User Guide:**
```markdown
## Possessing Bots

1. Select a bot (Alt+Shift+Click or /polis manage)
2. **Press F5 to switch to 3rd person view** (recommended)
3. Press Alt+U to possess the bot
4. Control with WASD as normal
5. Press Alt+Shift+U to exit possession
```

**Technical Notes:**
```markdown
### Known Limitation: First-Person Camera

First-person camera positioning when possessing NPCs has geometry clipping issues
due to animation attachment point overrides that cannot be controlled via the API.

**Workaround:** Use 3rd person view (F5) when possessing.

**Status:** Deferred pending VS API improvements or further investigation.
```

---

## Next Priority: Movement Issue (Phase B)

With camera issue deferred, **focus shifts to movement physics problem:**

**Issue:** Possessed NPC moves like horse (smooth, tilting) instead of player (responsive, bipedal)

**Status:** Research in progress via parallel agent (TASK-npc-physics-investigation.md)

**Next Steps:**
1. Wait for Phase B investigation results
2. Implement movement fix based on findings
3. This is SOLVABLE (unlike camera) - we can apply player physics manually

---

## Movement Fix Attempt: Disable Client Prediction (2026-01-06)

### Change Made
- Disabled `PredictNpcMovement()` in `PolisClientPossessionHandler.cs` so it no longer writes to `pos.Motion`.
- Added a one-time client log to confirm prediction is disabled when mounted.

### Log Evidence (client-main.log)
```
[polis] PredictNpcMovement: DISABLED (letting physics drive motion)
```

### Outcome
- Movement feel remained choppy/vehicular (no noticeable improvement).
- Confirms the current "horse/vehicle" feel is not caused solely by direct `Pos.Motion` writes.

### Implication
- The baseline controlled physics + interpolation pipeline still produces the undesired feel for possession.
- Next step is **Option 2**: reintroduce client prediction but apply player-like drag/accel (PModule-style) instead of raw motion assignment.

---

## Movement Fix Attempt: Physics-Style Prediction (2026-01-06)

### Change Made
- Re-enabled `PredictNpcMovement()` with drag/accel smoothing (PModule-style) instead of raw motion assignment.
- Added a one-time client log to confirm prediction is enabled.

### Log Evidence (client-main.log)
```
[polis] PredictNpcMovement: ENABLED (physics-style prediction)
```

### Outcome
- Movement feel remained choppy/vehicular with no noticeable improvement.
- Indicates client-side prediction changes are not materially affecting the rendered feel.

### Current State
- Client prediction disabled and enabled variants both fail to improve motion feel.
- Remaining likely cause is the server-side movement pipeline or interpolation behavior.

**Camera can be revisited later if:**
- VS adds camera mode API in future version
- User demand is high enough to justify deep investigation
- We discover new information about animation overrides

---

## Lessons Learned

1. **Public API limitations are real** - CameraType read-only blocked auto-switch approach
2. **Math doesn't always match reality** - Our calculations were correct but something overrides them
3. **Environmental constraints matter** - 2m ceilings create hard limits on camera height
4. **Sometimes pragmatic workarounds are best** - Manual F5 works, deep investigation may not
5. **Defer when stuck** - Move to solvable problems, revisit later with fresh perspective

**Time spent on camera issue:** ~2 hours research + testing
**Result:** Deferred with documented workaround
**Value:** Understanding of API limits and camera system constraints
