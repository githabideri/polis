# Animate Command Visual Test Results

**Date:** 2026-01-18
**Tester:** Claude (automated via poliscli)
**Branch:** main (commit a5e4dd5)

## Environment

- Harness: http://localhost:8585 - READY
- Player UID: REDACTED-UID
- Bot ID: 519
- Game started via vsctl

## Test Summary

| Test | Animation | Mode | Speed | API Result | Visual Result | Stop Count |
|------|-----------|------|-------|------------|---------------|------------|
| 1 | `hit` | one-shot | 1.0 | PASS | PASS | N/A |
| 2 | `hit` | one-shot | 0.3 | PASS | PASS (slower) | N/A |
| 3 | `hit` | one-shot | 2.0 | PASS | PASS (faster) | N/A |
| 4 | `walk` | looping | 1.0 | PASS | PASS | 1 |
| 5 | `interact` | looping | 0.5 | PASS | **FAIL** | 0 |
| 6 | `sit` | looping | 1.0 | PASS | **FAIL** | 0 |
| 7 | `run` | looping | 1.0 | PASS | **FAIL** | 0 |
| 8 | `nonexistent_xyz` | one-shot | 1.0 | PASS (bug) | FAIL | 0 |
| 9 | `stop` (all) | - | - | PASS | PASS | correct |

## Detailed Findings

### Working Animations

1. **`hit` (one-shot)** - Bot raises arm in hitting motion, returns to idle after completion
   - Speed modifier works: 0.3x visibly slower, 2.0x visibly faster
   - Screenshot evidence: `screenshot-2026-01-18_16-52-44-919.png` shows arm extended

2. **`walk` (looping)** - Bot legs move in walking animation, pose changes between frames
   - Consistently works across multiple tests
   - Stop command correctly reports "Stopped 1 animation(s)"
   - Screenshot evidence: `screenshot-2026-01-18_16-53-48-240.png`, `screenshot-2026-01-18_16-54-11-911.png`, `screenshot-2026-01-18_16-54-37-558.png` show different leg positions

### Not Working Animations (API Success, No Visual)

These animations report success but don't visually play and `stop` returns 0:

1. **`interact`** - No visual change, stop returns 0
2. **`sit`** - No visual change, stop returns 0
3. **`run`** - No visual change, stop returns 0

**Root cause hypothesis:** These animation codes may not exist in the bot's shape file, or require specific conditions (e.g., movement state) to play.

### Bug: Invalid Animation Codes Return Success

- `animate nonexistent_animation_xyz` returns `Ok: true`
- Should return `Ok: false` with error message
- Bot stays idle (correct behavior), but API response is misleading

## Stop Command Verification

| Scenario | Expected | Actual | Result |
|----------|----------|--------|--------|
| Stop after `walk` loop | "Stopped 1" | "Stopped 1" | PASS |
| Stop after `interact` loop | "Stopped 1" | "Stopped 0" | FAIL* |
| Stop after `sit` loop | "Stopped 1" | "Stopped 0" | FAIL* |
| Stop with no animations | "Stopped 0" | "Stopped 0" | PASS |

*These "failures" indicate the animation never actually started, not a stop command bug.

## Screenshots Captured

All screenshots saved to `~/Pictures/Vintagestory/polis/`:

| Screenshot | Description |
|------------|-------------|
| `screenshot-2026-01-18_16-47-26-195.png` | Bot idle, facing camera |
| `screenshot-2026-01-18_16-52-44-919.png` | Bot mid-hit animation (arm extended) |
| `screenshot-2026-01-18_16-53-13-042.png` | Bot returned to idle after hit |
| `screenshot-2026-01-18_16-53-48-240.png` | Walk animation frame 1 |
| `screenshot-2026-01-18_16-54-11-911.png` | Walk animation frame 2 (different pose) |
| `screenshot-2026-01-18_16-54-37-558.png` | Walk animation frame 3 (different pose) |
| `screenshot-2026-01-18_16-54-57-016.png` | Bot idle after stop command |

## Comparison with Previous Test (2026-01-18-animate-and-actions.md)

Previous test reported:
- One-shot animations work - **CONFIRMED**
- Looping animations don't work - **PARTIALLY CORRECTED**: `walk` loops work, `interact` doesn't

The difference may be due to:
1. Previous test used `interact` which doesn't work
2. This test found `walk` works correctly as looping animation

## Bugs Found

### Bug 1: Some animation codes silently fail
- **Severity:** Medium
- **Animations affected:** `interact`, `sit`, `run`
- **Behavior:** API returns success, animation doesn't play, stop returns 0
- **Expected:** API should return failure for animations not in shape file

### Bug 2: Invalid animation codes return success
- **Severity:** Low
- **Behavior:** `animate nonexistent_code` returns `Ok: true`
- **Expected:** Should return `Ok: false` with "animation not found" message

## Recommendations

1. **Add animation validation** - Check if animation code exists in entity's AnimationManager before returning success
2. **Document valid animations** - List animation codes that actually work for polisbot entity
3. **Consider fallback** - If `run` doesn't exist, could fall back to `walk` with speed modifier

## Conclusion

The animate command core functionality works:
- ✅ One-shot animations play and complete
- ✅ Speed modifiers affect animation speed
- ✅ `walk` looping animation works correctly
- ✅ Stop command correctly stops running animations
- ⚠️ Some animation codes don't work (entity shape limitation)
- ⚠️ Error reporting needs improvement for invalid/missing animations
