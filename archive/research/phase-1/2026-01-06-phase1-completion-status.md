# Phase 1 Completion Status: Possession Core Mechanics

**Date:** 2026-01-06
**Status:** ✅ COMPLETE - All critical blockers resolved
**Commits:**
- `00cc17a` - fix(possession): resolve client mount sync blocker
- `18742af` - fix(possession): use engine CalcMovementVectors for proper movement alignment

---

## What Was Phase 1?

Implement foundational possession system where:
1. Player mounts NPC entity (mounting system integration)
2. Camera switches to NPC perspective
3. Player controls route to NPC movement
4. Movement aligns with camera direction (no drift)

---

## Blockers Resolved ✅

### 1. Client Mount Sync (Commit: 00cc17a)
**Problem:** Mount succeeded on server but client never received state. Player physics kept running, camera stayed with player.

**Root Cause:** `RegisterMountable()` only called server-side. Client's `ClassRegistry` couldn't deserialize the custom `PolisPossessableSeat`.

**Solution:** Added `api.RegisterMountable()` to `StartClientSide()`.

**Verification:**
- ✅ Player entity freezes (MountedOn property set)
- ✅ Camera snaps to NPC position
- ✅ Log: `[polis] CreateFromTree: Reconstructing seat for NPC ...`

---

### 2. Control Misalignment (Commit: 18742af)
**Problem:** WASD inputs drifted relative to camera. W would change direction when rotating mouse.

**Root Cause:** Manual WalkVector calculation used plain `cos(yaw)/sin(yaw)` and `npc.ServerPos.Yaw`, but player camera yaw diverged during possession.

**Solution:**
- Lock NPC yaw to possessor's camera yaw FIRST
- Replace manual math with engine's `CalcMovementVectors()` (which uses correct pi/2 - yaw formula)
- Let engine handle diagonal normalization and input inversion

**Verification:**
- ✅ W always moves forward relative to camera (tested with mouse rotation)
- ✅ Diagonal speed normalized (1/sqrt(2))
- ✅ A/D strafe correctly
- ✅ S moves backward relative to camera
- ✅ No drift when rotating camera 90°/180°

---

## Current Capabilities ✅

| Feature | Status | Notes |
|---------|--------|-------|
| Mount player on NPC | ✅ | TryMount succeeds, sync works |
| Camera positioning | ✅ | Snaps to NPC eye level |
| Control routing | ✅ | Seat.Controls → NPC.ServerControls |
| Movement calculation | ✅ | Uses engine CalcMovementVectors |
| Yaw tracking | ✅ | NPC body follows camera |
| Head tracking | ✅ | Head yaw/pitch sync to camera |
| Block interaction | ✅ | Can dig/place blocks while possessed |
| Animations | ✅ | Walk, jump, fall working |
| Physics | ✅ | Jump, fall, collision all work |

---

## Known Issues (for Phase 2)

### 1. Movement Speed (Non-blocking)
- NPC walks noticeably faster than player
- Sprint is extremely fast
- **Cause:** Mount system speed scaling vs bipedal character speed
- **Priority:** Low - doesn't break functionality
- **Resolution:** Phase 2 tuning + client-side smoothing may help

### 2. Choppy Movement (Blocking Experience)
- Motion feels stuttery, like riding a mount
- **Cause:** No client-side prediction; NPC is remote server entity
- **Impact:** Breaks immersion, feels "vehicular"
- **Solution:** Phase 2 - Client-side render prediction + reconciliation
- **Priority:** HIGH - critical for "feel"

---

## Phase 1 Summary

✅ **All critical path items complete:**
- Mounting works end-to-end (server + client)
- Camera positioning correct
- Control routing functional
- **Movement alignment fixed** (primary blocker resolved)

⏳ **Deferred to Phase 2:**
- Client-side movement smoothing (handles choppiness)
- Speed multiplier tuning (handles "vehicle" feel)

---

## Next: Phase 2 - Client-Side Smoothing

See `docs/research/phase-1/2026-01-05-possession-blocker-analysis.md` lines 295-310 for:
- Exact smoothing strategy
- Implementation pattern (EntityBehaviorRideable.OnRenderFrame)
- Reconciliation approach (not hard-snap)

**Entry Point:** `PolisBuilderNpcHotkeys.cs` StartClientSide or create new `PolisClientPossessionHandler`

---

## Test Results

### In-Game Testing (2026-01-06)
```
Command: /polis spawn && /polis possess
Status: SUCCESS

✅ W = forward (camera-relative)
✅ A = strafe left (camera-relative)
✅ D = strafe right (camera-relative)
✅ S = backward (camera-relative)
✅ Mouse rotation = NPC body follows
✅ Crouch/Sprint modifiers work
✅ Space = jump
✅ Fall animation plays
✅ Block digging works

⚠️  Movement speed > player walk speed
⚠️  Choppy motion (server snapshots)
```

---

## Commits This Session

```
bf1fa91 docs: add deep analysis of possession control misalignment and smoothing strategy
18742af fix(possession): use engine CalcMovementVectors for proper movement alignment
00cc17a fix(possession): resolve client mount sync blocker [previous session]
```

---

## Files Modified

- `PolisBuilderNpcSystem.cs` - UpdatePossessions(): replaced manual WalkVector with CalcMovementVectors()
- Existing: `PolisPossessableSeat.cs`, `PolisBuilderNpcHotkeys.cs` (no changes needed)

---

## Code Patterns Established

1. **Yaw Locking:** Lock NPC yaw to possessor before calculating movement
2. **Engine Math Delegation:** Use CalcMovementVectors() instead of custom rotation
3. **Control Routing:** seat.Controls → npcControls via boolean flags
4. **Debug Logging:** [polis] prefix, checks debugEnabled flag

