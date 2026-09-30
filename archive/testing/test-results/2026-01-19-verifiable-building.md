# Verifiable Building System - Test Report

**Date:** 2026-01-19
**Tester:** Claude (automated testing with human oversight)
**Feature:** Scan, Verify, and Build commands for blueprint-driven construction

---

## Test Summary

| Test | Description | Result |
|------|-------------|--------|
| 1 | Scan command returns blocks | **PASS** |
| 2 | Scan saves to file | **PASS** (after fix) |
| 3 | Verify detects matches/mismatches | **PASS** |
| 4 | Verify with origin offset | **PASS** |
| 5 | Build dry-run | **PASS** |
| 6 | Build full execution | **PASS** (after fix) |
| 7 | Build resumability | **PASS** |
| 8 | Build error handling | **PASS** |

**Overall: 8/8 PASS** (with fixes applied during testing)

---

## Bugs Found and Fixed

### 1. Scan `--relative` Flag Not Affecting Saved File
**Symptom:** `--relative` converted coordinates in stdout but saved absolute coords to file.
**Root Cause:** Relative conversion happened AFTER file save.
**Fix Applied:** Moved relative conversion BEFORE file save in `cmd_scan()`.
**File:** `scripts/poliscli.py` lines 907-919

### 2. Scan `--output` Still Printing Full Result to Stdout
**Symptom:** When using `--output`, full YAML result still printed to stdout, causing issues with piping.
**Fix Applied:** Only print full output if `--output` not specified.
**File:** `scripts/poliscli.py` lines 914-922

### 3. Build Command Insufficient Wait Time
**Symptom:** Build reported "9 placed" but only 1 block actually placed. Per-block verification failed.
**Root Cause:** `time.sleep(0.1)` insufficient for placement to complete; place command returns acknowledgment before block is actually placed.
**Fix Applied:** Increased to `time.sleep(0.8)`.
**TODO:** Implement proper `wait_for_action` polling instead of fixed sleep.
**File:** `scripts/poliscli.py` line 1097

### 4. Debug Logging Added for Build Command
**Addition:** Added `fmt.debug()` call to log each place response.
**Usage:** Run with `-v` flag to see per-placement responses.
**File:** `scripts/poliscli.py` line 1084

---

## Issues Found (Not Fixed)

### 1. Teleport Yaw/Pitch: HUD/Minimap Desync Causing Agent Confusion

**Symptom:** After teleport with `--yaw` and `--pitch`, the view IS correctly positioned (screenshots show correct orientation), BUT the HUD and minimap do not update to reflect the new orientation.

**Impact:** Agent/LLM sees a screenshot where:
- The actual view is facing South (e.g., sun visible, cobblestone structure ahead)
- But HUD text displays "North"

The agent trusts the written HUD text over visual evidence, leading to confusion about:
- Where structures are located relative to the player
- Which direction the camera is actually facing
- Correlation between API coordinates and visual scene

**Debugging observation:** When the user manually moves the mouse, the view snaps back to match the stale HUD/minimap orientation. This reveals the underlying mechanism: the teleport sets server-side orientation but the client-side HUD/minimap retain the old state, and mouse input causes resync to that stale state.

**Suggested Fix:** Investigate client-side sync for player yaw/pitch after teleport. The HUD/minimap should update to reflect the teleported orientation, or the teleport should force a client-side orientation update.

### 2. Coordinate System Discrepancy
**Observation:** In-game HUD shows spawn-relative coordinates (e.g., "24, 3, 57"), while API uses absolute world coordinates (e.g., "251, 3, 319").
**Impact:** Confusion when correlating visual HUD with API commands.
**Suggested Fix:** Document clearly; consider adding absolute coords option to HUD or API option for spawn-relative.

### 3. Wide Scan Returns Excessive Data

**Observation:** Scanning large areas returns thousands of blocks (mostly soil), overwhelming output.
**Example:** 30x10x30 area returned 9933 blocks, ~650KB output.

**Workflow Analysis:**
- **Small area scan** (e.g., 3x3 build site): Agent needs full detail with positions - this works fine.
- **Large area survey** (e.g., "find cobblestone in 50x50 area"): Agent doesn't need 9000 soil block positions, just wants to know what's there and where specific blocks are.

**Current problem:** Agent runs scan on large area, receives 10000+ blocks of mostly terrain, wastes tokens, doesn't get useful info efficiently.

**Suggested Solutions (consider workflow):**

1. **Smart default behavior:** Auto-detect large result sets and summarize:
   ```
   Found 9933 blocks in area:
     9865x soil (various types)
       34x game:cobblestone-granite
        5x game:farmland-*
       ... (other non-terrain)
   Use --full for complete block list, or --filter <pattern> to narrow results.
   ```

2. **Built-in filtering:** Add `--filter` or `--type` to scan:
   ```bash
   ./scripts/poliscli.py scan 200 1 300 280 10 340 --filter cobblestone
   # Returns only matching blocks with positions
   ```

3. **Exclude terrain by default for large scans:** Add `--include-terrain` flag, exclude soil/rock/gravel by default when result > N blocks.

The key insight: for large areas, the typical task is "find something specific" not "enumerate everything." The tool should optimize for that workflow.

---

## Orientation Reference (Confirmed)

| Setting | Result |
|---------|--------|
| `pitch = 0` | Looking at horizon |
| `pitch > 0` | Looking UP (sky) |
| `pitch < 0` | Looking DOWN (ground) |
| `yaw = 0` | Facing North (+Z direction in VS = South geographically) |
| `yaw = π/2 (1.57)` | Facing East |
| `yaw = π (3.14)` | Facing South |
| `yaw = 3π/2 (4.71)` | Facing West |

**Note:** Vintage Story coordinate system: +Z is South. Yaw accumulates with mouse movement rather than normalizing to 0-2π range.

---

## Suggested Improvements

### 1. Verification HUD Panel
Add an optional debug HUD panel showing:
- Absolute server position (X, Y, Z)
- Current yaw/pitch values (actual, not stale)
- Human-readable orientation ("Looking down 30°, facing South")
- This would provide reliable orientation info that agents can trust

### 2. Build Command Action Polling
Replace fixed `time.sleep(0.8)` with proper action completion polling:
```python
# Instead of fixed sleep, poll for completion like wait_for_action()
while not action_complete(client, bot_id, "place"):
    time.sleep(0.2)
```

### 3. Bot Range Pre-Check
Build command should verify bot is within placement range BEFORE attempting placements, and either:
- Warn and abort with clear message
- Auto-navigate bot to suitable position

Currently failures appear as silent verification failures, requiring investigation to discover range was the issue.

---

## Test Protocol Established

During testing, we established a proper verification protocol:

1. **Pre-test cleanup:**
   - Despawn old bots
   - Scan area to find/remove existing test blocks
   - Verify area clear via scan

2. **Before any build/placement test:**
   - Verify bot position via API (not visual)
   - Scan target area to confirm state
   - Position camera and screenshot
   - Cross-reference scan data with visual (don't trust HUD orientation text)

3. **For orientation verification:**
   - Use scan/verify commands as ground truth
   - Visual elements (sun position, known structures) more reliable than HUD text
   - Note: HUD orientation may be stale after teleport

---

## Files Modified

1. `scripts/poliscli.py`:
   - Line 907-922: Fixed `--relative` and `--output` interaction for scan
   - Line 1084: Added debug logging for place responses
   - Line 1097: Increased placement wait time (0.1s → 0.8s)

---

## Cleanup Performed

- Removed test blocks at:
  - (250-252, 3, 320-322) - Test 1 area
  - (260-262, 3, 330-332) - Test 6 area
  - (270-272, 3, 340) - Test 8 area
- Despawned test bot #549
- Removed temp blueprint files from /tmp/
