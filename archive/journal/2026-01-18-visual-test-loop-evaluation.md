# Visual Test Loop Evaluation

**Date:** 2026-01-18
**Purpose:** Evaluate the visual debugging/development loop using poliscli + screenshots for automated testing

## Summary

Tested the capability to run bot actions and visually verify results through screenshots. This enables a full visual test/debug/dev loop where an agent can:
1. Issue commands to bots
2. Position camera to observe
3. Capture screenshots for verification
4. Iterate based on visual feedback

The core capability works well. Several usability improvements would make the workflow smoother.

## What Works Well

- **Screenshot capture:** `/polis/screenshot` + `--save` reliably captures the player's view
- **Camera positioning:** `teleport --face-bot` automatically calculates yaw to face the bot
- **Bot state inspection:** `state` command shows position, inventory, last action result
- **Action verification:** LastAction field confirms success/failure with message

## Visual Test Workflow

```bash
# Position camera to observe bot
./scripts/poliscli.py teleport X Y Z --face-bot --player UID

# Take screenshot before action
./scripts/poliscli.py screenshot --player UID --save

# Perform action
./scripts/poliscli.py mine X Y Z --player UID

# Take screenshot after action
./scripts/poliscli.py screenshot --player UID --save
```

## Issues Affecting Visual Test Loop

### 1. Player UID Required Everywhere

**Problem:** Every command needs `--player 'UID'` passed explicitly, adding friction to test scripts.

**Impact:** Test scripts become verbose and error-prone.

**Suggestion:** Auto-detect single online player as default. For dev/debug scenarios this is almost always the case.

### 2. Camera Not Auto-Positioned After Unpossess

**Problem:** After `unpossess`, the player camera stays where it was (often inside the bot or facing wrong direction). Must manually teleport to get a useful view.

**Impact:** Easy to forget this step and capture useless screenshots.

**Suggestion:** Document as standard practice: always `teleport --face-bot` before capturing verification screenshots.

### 3. Targets Output Flooded with Soil

**Problem:** When looking for specific objects (doors, chests) to test interactions, the `targets` command returns mostly soil blocks.

**Impact:** Hard to discover what's available to interact with in the area.

**Suggestions:**
- Add `--filter` option (e.g., `--filter door`)
- Add `--exclude-natural` to hide soil/stone/dirt
- Prioritize "interesting" blocks (doors, containers, machines) in output

### 4. Bot Ownership Must Be Set at Spawn

**Problem:** Spawning without `--player` creates an ownerless bot. Many actions (mine, activate) then fail with "Bot owner is offline or unknown".

**Impact:** Confusing failure mode - spawn succeeds but subsequent actions fail.

**Suggestion:** Auto-assign owner to single online player, or fail spawn early with clear error.

### 5. Drop Uses RightHand Automatically

**Behavior:** `drop` drops from RightHand, not LeftHand, regardless of what's in each.

**Impact:** Need to be aware of hand contents when testing drop sequences.

### 6. Minor: Python Error in Mine Output

**Observation:** `mine` command shows a Python error (`'NoneType' object has no attribute 'get'`) but the action succeeds. Display issue only.

## Screenshots from This Session

| Screenshot | Description |
|------------|-------------|
| `17-44-56` | Initial area overview |
| `17-45-33` | First-person view while possessing (door in crosshair) |
| `17-49-01` | Bot after mining, hole visible in ground |
| `17-49-38` | After drop command |
| `17-51-15` | Bot positioned near door |
| `17-51-36` | Door closed after activate toggle |
| `17-52-51` | After wave animation |

## Recommended Standard Test Sequence

```bash
# 1. Start game with window positioning
./scripts/vsctl.py start --wait --window

# 2. Spawn bot with ownership
./scripts/poliscli.py spawn --player UID
./scripts/poliscli.py select BOT_ID

# 3. Setup bot
./scripts/poliscli.py give game:pickaxe-copper
./scripts/poliscli.py goto X Y Z
sleep 2  # wait for movement

# 4. ALWAYS position camera before screenshots
./scripts/poliscli.py teleport X Y Z --face-bot --player UID

# 5. Capture before state
./scripts/poliscli.py screenshot --player UID --save

# 6. Perform action
./scripts/poliscli.py mine X Y Z --player UID
sleep 3  # wait for completion

# 7. Capture after state
./scripts/poliscli.py screenshot --player UID --save

# 8. Verify programmatically
./scripts/poliscli.py state  # check LastAction.Ok

# 9. Cleanup
./scripts/poliscli.py despawn
./scripts/vsctl.py stop
```

## Conclusion

The visual test loop is functional and valuable for debugging bot behavior. The main friction points are:
1. Verbose player UID requirement
2. Need to manually position camera after actions
3. Difficulty finding specific interactables in targets output

These are quality-of-life improvements that would make automated visual testing more ergonomic.
