# HANDOFF: Movement Fix Implementation

**Date:** 2026-01-06
**For:** Next agent to implement movement fix
**Context:** Phase 1 polish - Fix horse-like movement in possessed NPCs

---

## Quick Summary

**Problem:** Possessed NPCs move like horses (smooth, tilting) instead of players (responsive, bipedal)

**Root Cause:** Client prediction code bypasses physics by directly setting `Pos.Motion`

**Solution:** Remove the problematic line - let existing physics systems work

**Complexity:** LOW (one function to disable, ~10 lines change)

---

## What You Need to Know

### Investigation Complete ✅

**Already done:**
- Parallel agent investigated NPC physics (see `docs/journal/2026-01-06-npc-physics-investigation.md`)
- Found NO rideable behavior on playerbot (mount system not causing issue)
- Server physics is CORRECT (uses EntityBehaviorControlledPhysics properly)
- Client prediction is WRONG (bypasses physics, creates smooth motion)

**Key Discovery:**
```csharp
// PolisClientPossessionHandler.cs:118
possessedNpc.Pos.Motion.Set(predictControls.WalkVector);  // ❌ THIS LINE IS THE PROBLEM
```

This line:
- Bypasses `EntityBehaviorControlledPhysics` (no drag/acceleration)
- Fights with `EntityBehaviorInterpolatePosition` (interpolation conflict)
- Creates smooth continuous motion (vehicular feel)
- Server has proper physics, client doesn't = feels weird

### Documentation Already Created ✅

**All context in these files:**
1. `docs/research/phase-1/2026-01-06-movement-fix-plan.md` - Full implementation plan
2. `docs/journal/2026-01-06-npc-physics-investigation.md` - Investigation results
3. `docs/research/phase-1/2026-01-06-phase-1-polish-findings.md` - Overall findings

---

## Implementation Instructions

### File to Edit

**File:** `PolisClientPossessionHandler.cs`
**Location:** `/home/mf/Code/polis-builder/polis-builder-npc/PolisClientPossessionHandler.cs`

### Code Change (Option B - Recommended)

**Find this function (starts around line 85):**
```csharp
private void PredictNpcMovement(float dt, PolisPossessableSeat seat)
{
    // DIAGNOSTIC: Verify we reached prediction code
    capi.Logger.Notification("[polis] PredictNpcMovement: Called");

    // ... (diagnostic logging and control copying) ...

    // PREDICT: Use engine's CalcMovementVectors (same as server)
    predictControls.CalcMovementVectors(possessedNpc.Pos, dt);

    // DIAGNOSTIC: Log calculated WalkVector
    capi.Logger.Notification($"[polis] WalkVec: X={predictControls.WalkVector.X:F3} Z={predictControls.WalkVector.Z:F3}");

    // APPLY: Set motion vector for smooth movement
    possessedNpc.Pos.Motion.Set(predictControls.WalkVector);  // ❌ PROBLEM LINE

    // TRACK: Save predicted position for reconciliation
    predictedPos = possessedNpc.Pos.XYZ.Clone();
}
```

**Replace entire function body with:**
```csharp
private void PredictNpcMovement(float dt, PolisPossessableSeat seat)
{
    // DISABLED: Client prediction was bypassing EntityBehaviorControlledPhysics
    // This caused smooth vehicular movement instead of responsive bipedal movement
    //
    // Root cause: Direct Pos.Motion writes bypassed physics modules (drag/acceleration)
    // and fought with EntityBehaviorInterpolatePosition causing conflicts
    //
    // Solution: Let server-side EntityBehaviorControlledPhysics provide correct movement
    // and EntityBehaviorInterpolatePosition handle client smoothing
    //
    // See: docs/journal/2026-01-06-npc-physics-investigation.md
    // See: docs/research/phase-1/2026-01-06-movement-fix-plan.md

    return;
}
```

**Alternative (if you want to keep some diagnostics):**
```csharp
private void PredictNpcMovement(float dt, PolisPossessableSeat seat)
{
    // DISABLED: Was bypassing physics, see investigation results
    if (debugEnabled)  // If there's a debug flag
    {
        capi.Logger.Notification("[polis] PredictNpcMovement: DISABLED (letting physics work)");
    }
    return;
}
```

### Don't Change ReconcileWithServer

**Leave this function as-is** (or comment out the call to it in OnRenderFrame if prediction is fully disabled).

The reconciliation was fighting the interpolation system, but it's safer to test first with just prediction disabled.

---

## Build & Deploy

**Commands:**
```bash
cd /home/mf/Code/polis-builder/polis-builder-npc

VINTAGE_STORY="/home/mf/.local/share/flatpak/app/at.vintagestory.VintageStory/x86_64/stable/active/files/extra/vintagestory" \
dotnet build -c Release && \
cp -r bin/Release/Mods/polis-builder-npc ../vsdata/Mods/
```

**Expected output:**
- Build succeeded
- 0 Warning(s)
- 0 Error(s)

---

## Testing Instructions

### Test Scenarios

**1. Outdoor Movement (Baseline)**
- Possess bot in open area
- Walk forward (W), back (S), strafe (A/D)
- Try diagonal movement (W+A, W+D, etc.)
- **Check:** Does it feel responsive? Natural acceleration/deceleration?

**2. Movement Start/Stop (Critical)**
- Press W briefly, release
- Press A briefly, release
- **Check:** Does movement start/stop feel snappy? Or laggy/smooth?

**3. Turning and Strafing**
- Walk in circles
- Strafe while turning camera
- **Check:** No sideways tilting? Feels like controlling player?

**4. Indoor Movement**
- Test in house/building
- Same movement tests
- **Check:** Works same as outdoor? No issues with tight spaces?

**5. Network Lag Test (if applicable)**
- If testing on server with latency
- **Check:** Any visible stuttering? Teleporting? Position snaps?

### Success Criteria

**Must Have:**
- ✅ Movement feels responsive (not smooth/floaty)
- ✅ Natural acceleration/deceleration (not continuous)
- ✅ No tilting during turns
- ✅ Matches player movement feel

**Nice to Have:**
- ✅ No visible stuttering
- ✅ Smooth enough via interpolation
- ✅ Indoor/outdoor work same

### Expected Results

**Best Case:** Movement feels responsive and player-like immediately
- Ship it!
- Clean up diagnostic code
- Commit changes

**Acceptable Case:** Slightly laggy but correct physics feel
- May need Option 2 (proper physics prediction)
- But still better than vehicular feel

**Unexpected Case:** Doesn't work or feels worse
- Check logs for errors
- Verify EntityBehaviorControlledPhysics is active
- May need deeper investigation

---

## Where to Document Results

### Update This File

**File:** `docs/research/phase-1/2026-01-06-phase-1-polish-findings.md`

**Add section at end:**
```markdown
## Movement Fix Implementation Results (2026-01-06)

### Change Made
- Disabled client prediction in PolisClientPossessionHandler.cs
- Removed direct Pos.Motion write that bypassed physics

### Test Results

**Outdoor Movement:**
[Your observations]

**Movement Start/Stop:**
[Your observations]

**Turning/Strafing:**
[Your observations]

**Indoor Movement:**
[Your observations]

### Conclusion
[Success? Need refinement? Next steps?]
```

---

## Git Commit

**After successful testing:**

```bash
git add PolisClientPossessionHandler.cs
git commit -m "fix(movement): Remove client prediction that bypassed physics

Client prediction was directly setting Pos.Motion to WalkVector, bypassing
EntityBehaviorControlledPhysics and creating smooth vehicular movement.

Changes:
- Disable PredictNpcMovement() function body
- Let server EntityBehaviorControlledPhysics provide correct movement
- Let client EntityBehaviorInterpolatePosition handle smoothing

Result: Responsive bipedal movement instead of smooth horse-like movement

Investigation: docs/journal/2026-01-06-npc-physics-investigation.md
Root cause: Client prediction bypassed physics modules (no drag/acceleration)
Solution: Let existing physics pipeline work (it was correct all along)"
```

---

## Fallback Plan

### If Option 1 Doesn't Work Well

**Option 2: Proper Physics Prediction** is documented in:
- `docs/research/phase-1/2026-01-06-movement-fix-plan.md` (section: "Fallback: Option 2")

**Summary:** Instead of removing prediction, apply proper drag/acceleration math:
```csharp
// Apply drag and acceleration (mimic PModuleOnGround)
double groundDrag = 0.7;
possessedNpc.Pos.Motion.X += (walkX - possessedNpc.Pos.Motion.X) * groundDrag;
possessedNpc.Pos.Motion.Z += (walkZ - possessedNpc.Pos.Motion.Z) * groundDrag;
possessedNpc.Pos.Motion.X *= (1 - groundDrag);
possessedNpc.Pos.Motion.Z *= (1 - groundDrag);
```

**Only implement if Option 1 feels too laggy.**

---

## Context Files (For Reference)

### Must Read
- `docs/research/phase-1/2026-01-06-movement-fix-plan.md` - Full plan with all options
- `docs/journal/2026-01-06-npc-physics-investigation.md` - Investigation results

### Background (Optional)
- `docs/research/phase-1/2026-01-06-phase-1-polish-findings.md` - Overall findings (camera + movement)
- `docs/journal/2026-01-06-mount-movement-findings.md` - Mount vs player physics research

### Current State
- **Camera issue:** DEFERRED (manual F5 workaround)
- **Movement issue:** Ready to fix (this task)
- **Server movement:** Already correct
- **Client movement:** Needs fixing (this task)

---

## Key Points for Implementation

1. **This is a SIMPLE fix** - just disable one function
2. **Server physics is correct** - don't change server code
3. **Investigation was thorough** - high confidence in solution
4. **No rideable behavior** - mount system not involved
5. **Test thoroughly** - but expect it to work
6. **Document results** - update findings file

---

## Questions? Check These First

**Q: Why not just fix the prediction instead of removing it?**
A: Option 1 tests if interpolation alone is good enough. Option 2 (proper prediction) is fallback if needed.

**Q: What if it still feels like a horse?**
A: Unlikely - investigation proved no rideable behavior exists. If it happens, check logs for errors.

**Q: Should I change ReconcileWithServer too?**
A: Start with just disabling prediction. Can disable reconciliation in second iteration if needed.

**Q: What about the camera issue?**
A: That's DEFERRED. Focus only on movement. Camera workaround is manual F5.

**Q: How do I know if it worked?**
A: Movement should feel snappy/responsive (like player) instead of smooth/floaty (like vehicle).

---

## Good Luck!

This should be straightforward - the hard work (investigation) is done. Just remove the problematic code and let the correct systems work.

Expected time: 15-30 minutes (implement + test + commit)
