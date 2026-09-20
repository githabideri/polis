# Verifiable Building System - Test Plan

**Date:** 2026-01-19
**Feature:** Scan, Verify, and Build commands for blueprint-driven construction
**Status:** Ready for testing

## Overview

This test plan validates the new verifiable building system which includes:
- `scan` - Capture world blocks as blueprints
- `verify` - Compare blueprints against world state
- `build` - Construct from blueprints with per-block verification

## Prerequisites

1. **Build and deploy the mod:**
   ```bash
   source .env && dotnet build -c Release && cp -r bin/Release/Mods/polis-builder-npc "$VSDATA/Mods/"
   ```

2. **Start the game:**
   ```bash
   ./scripts/vsctl.py start --wait --window
   ```

3. **Verify harness is running:**
   ```bash
   ./scripts/poliscli.py status
   # Expected: worldReady=true
   ```

---

## Test 1: Scan Command (Harness)

**Goal:** Verify the scan endpoint correctly captures blocks in a region.

### Steps

1. **Find a known structure** (or place some blocks manually):
   ```bash
   # Place a 3x1x3 test pattern using setblock
   ./scripts/poliscli.py setblock game:cobblestone-granite 250 3 320
   ./scripts/poliscli.py setblock game:cobblestone-granite 251 3 320
   ./scripts/poliscli.py setblock game:cobblestone-granite 252 3 320
   ./scripts/poliscli.py setblock game:cobblestone-granite 250 3 321
   ./scripts/poliscli.py setblock game:cobblestone-granite 251 3 321
   ./scripts/poliscli.py setblock game:cobblestone-granite 252 3 321
   ./scripts/poliscli.py setblock game:cobblestone-granite 250 3 322
   ./scripts/poliscli.py setblock game:cobblestone-granite 251 3 322
   ./scripts/poliscli.py setblock game:cobblestone-granite 252 3 322
   ```

2. **Run scan command:**
   ```bash
   ./scripts/poliscli.py scan 250 3 320 252 3 322
   ```

3. **Expected output:**
   ```json
   {
     "Ok": true,
     "Message": "Scanned 9 blocks",
     "Data": {
       "blockCount": 9,
       "blocks": [...]
     }
   }
   ```

### Success Criteria
- [x] Returns `Ok: true`
- [x] `blockCount` matches expected (9 blocks)
- [x] Each block has correct `pos` and `code`

---

## Test 2: Scan with File Output

**Goal:** Verify scan can save blueprints to file.

### Steps

1. **Scan and save:**
   ```bash
   ./scripts/poliscli.py scan 250 3 320 252 3 322 --output /tmp/test-blueprint.json
   ```

2. **Verify file contents:**
   ```bash
   cat /tmp/test-blueprint.json | jq '.blocks | length'
   # Expected: 9
   ```

3. **Test relative coordinates:**
   ```bash
   ./scripts/poliscli.py scan 250 3 320 252 3 322 --output /tmp/test-relative.json --relative
   cat /tmp/test-relative.json | jq '.blocks[0].pos'
   # Expected: [0, 0, 0] (not absolute coords)
   ```

### Success Criteria
- [x] File created with valid JSON
- [x] `--relative` flag converts to origin-relative coords

---

## Test 3: Verify Command

**Goal:** Verify blueprint comparison against world state.

### Steps

1. **Create test blueprint:**
   ```bash
   cat > /tmp/verify-test.json << 'EOF'
   {"name":"3x3","blocks":[
     {"pos":[250,3,320],"code":"game:cobblestone-granite"},
     {"pos":[251,3,320],"code":"game:cobblestone-granite"},
     {"pos":[252,3,320],"code":"game:cobblestone-granite"},
     {"pos":[250,3,321],"code":"game:cobblestone-granite"},
     {"pos":[251,3,321],"code":"game:cobblestone-granite"},
     {"pos":[252,3,321],"code":"game:cobblestone-granite"},
     {"pos":[250,3,322],"code":"game:cobblestone-granite"},
     {"pos":[251,3,322],"code":"game:cobblestone-granite"},
     {"pos":[252,3,322],"code":"game:cobblestone-granite"}
   ]}
   EOF
   ```

2. **Run verify (should match):**
   ```bash
   ./scripts/poliscli.py verify /tmp/verify-test.json
   ```

3. **Expected output:**
   ```
   Verified: 9/9 blocks correct (100%)
   ```

4. **Test mismatch detection - remove one block:**
   ```bash
   ./scripts/poliscli.py setblock air 251 3 321
   ./scripts/poliscli.py verify /tmp/verify-test.json -v
   ```

5. **Expected output:**
   ```
   Verified: 8/9 blocks correct (88.9%)
   Missing blocks (1):
     [251, 3, 321]: expected game:cobblestone-granite
   ```

### Success Criteria
- [x] 100% match returns exit code 0
- [x] Partial match returns non-zero exit code
- [x] Missing blocks correctly identified
- [x] Verbose mode shows details

---

## Test 4: Verify with Origin Offset

**Goal:** Verify origin offset applies correctly for relative blueprints.

### Steps

1. **Create relative blueprint:**
   ```bash
   cat > /tmp/relative-blueprint.json << 'EOF'
   {"name":"3x1 row","blocks":[
     {"pos":[0,0,0],"code":"game:cobblestone-granite"},
     {"pos":[1,0,0],"code":"game:cobblestone-granite"},
     {"pos":[2,0,0],"code":"game:cobblestone-granite"}
   ]}
   EOF
   ```

2. **Verify at specific origin:**
   ```bash
   ./scripts/poliscli.py verify /tmp/relative-blueprint.json --origin 250 3 320
   ```

3. **Expected:** Should match the first row of our test structure.

### Success Criteria
- [x] Origin offset correctly translates relative positions
- [x] Matches blocks at offset location

---

## Test 5: Build Command (Dry Run)

**Goal:** Verify build dry-run shows planned placements.

### Steps

1. **Clear target area:**
   ```bash
   for x in 260 261 262; do
     for z in 330 331 332; do
       ./scripts/poliscli.py setblock air $x 3 $z
     done
   done
   ```

2. **Create blueprint:**
   ```bash
   cat > /tmp/build-test.json << 'EOF'
   {"name":"3x3 test","blocks":[
     {"pos":[0,0,0],"code":"game:cobblestone-granite"},
     {"pos":[1,0,0],"code":"game:cobblestone-granite"},
     {"pos":[2,0,0],"code":"game:cobblestone-granite"},
     {"pos":[0,0,1],"code":"game:cobblestone-granite"},
     {"pos":[1,0,1],"code":"game:cobblestone-granite"},
     {"pos":[2,0,1],"code":"game:cobblestone-granite"},
     {"pos":[0,0,2],"code":"game:cobblestone-granite"},
     {"pos":[1,0,2],"code":"game:cobblestone-granite"},
     {"pos":[2,0,2],"code":"game:cobblestone-granite"}
   ]}
   EOF
   ```

3. **Run dry-run:**
   ```bash
   ./scripts/poliscli.py build /tmp/build-test.json --origin 260 3 330 --dry-run
   ```

4. **Expected output:**
   ```
   [dry-run] Would place game:cobblestone-granite at (260, 3, 330)
   [dry-run] Would place game:cobblestone-granite at (261, 3, 330)
   ...
   ```

### Success Criteria
- [x] Shows all planned placements
- [x] No actual blocks placed (verify with scan)

---

## Test 6: Build Command (Full Execution)

**Goal:** Verify full build with bot placement and verification.

### Steps

1. **Spawn bot and give blocks:**
   ```bash
   ./scripts/poliscli.py spawn
   # Note the bot ID from output
   ./scripts/poliscli.py select <BOT_ID>
   export POLIS_BOT_ID=<BOT_ID>
   ./scripts/poliscli.py give game:cobblestone-granite 20
   ```

2. **Verify bot has blocks:**
   ```bash
   ./scripts/poliscli.py state | jq '.Bot.RightHand'
   # Expected: {"Code": "game:cobblestone-granite", "Qty": 20}
   ```

3. **Run build:**
   ```bash
   ./scripts/poliscli.py build /tmp/build-test.json --origin 260 3 330
   ```

4. **Expected output:**
   ```
   Building '3x3 test': 9 blocks
   Progress: 9/9 (100%) - placed: 9, skipped: 0, failed: 0
   Build complete: 100% verified (9/9)
   ```

5. **Independent verification:**
   ```bash
   ./scripts/poliscli.py verify /tmp/build-test.json --origin 260 3 330
   # Expected: 100%
   ```

### Success Criteria
- [x] Bot places all blocks
- [x] Per-block verification passes
- [x] Final verification shows 100%
- [x] Blocks consumed from inventory

---

## Test 7: Build Resumability

**Goal:** Verify build skips already-placed blocks.

### Steps

1. **Run build again on same location:**
   ```bash
   ./scripts/poliscli.py give game:cobblestone-granite 10
   ./scripts/poliscli.py build /tmp/build-test.json --origin 260 3 330
   ```

2. **Expected output:**
   ```
   Progress: 9/9 (100%) - placed: 0, skipped: 9, failed: 0
   ```

### Success Criteria
- [x] All blocks skipped (already placed)
- [x] No duplicate placements
- [x] Fast completion (no unnecessary actions)

---

## Test 8: Build with Errors

**Goal:** Verify error handling and continue-on-error.

### Steps

1. **Create blueprint with invalid block:**
   ```bash
   cat > /tmp/error-test.json << 'EOF'
   {"name":"error test","blocks":[
     {"pos":[0,0,0],"code":"game:cobblestone-granite"},
     {"pos":[1,0,0],"code":"game:nonexistent-block-xyz"},
     {"pos":[2,0,0],"code":"game:cobblestone-granite"}
   ]}
   EOF
   ```

2. **Clear area and give blocks:**
   ```bash
   ./scripts/poliscli.py setblock air 270 3 340
   ./scripts/poliscli.py setblock air 271 3 340
   ./scripts/poliscli.py setblock air 272 3 340
   ./scripts/poliscli.py give game:cobblestone-granite 5
   ```

3. **Run build (should stop on error):**
   ```bash
   ./scripts/poliscli.py build /tmp/error-test.json --origin 270 3 340
   # Expected: Stops after first placement fails
   ```

4. **Run with continue-on-error:**
   ```bash
   ./scripts/poliscli.py build /tmp/error-test.json --origin 270 3 340 --continue-on-error
   # Expected: Continues past error, reports 1 failed
   ```

### Success Criteria
- [x] Default behavior stops on first error
- [x] `--continue-on-error` continues past failures
- [x] Failed count reported correctly

---

## Cleanup

```bash
# Remove test blocks
for x in 250 251 252; do
  for z in 320 321 322; do
    ./scripts/poliscli.py setblock air $x 3 $z
  done
done

for x in 260 261 262; do
  for z in 330 331 332; do
    ./scripts/poliscli.py setblock air $x 3 $z
  done
done

# Remove test files
rm -f /tmp/test-blueprint.json /tmp/test-relative.json /tmp/verify-test.json
rm -f /tmp/relative-blueprint.json /tmp/build-test.json /tmp/error-test.json

# Despawn bot
./scripts/poliscli.py despawn
```

---

## Summary Checklist

| Test | Description | Pass |
|------|-------------|------|
| 1 | Scan command returns blocks | [ ] |
| 2 | Scan saves to file | [ ] |
| 3 | Verify detects matches/mismatches | [ ] |
| 4 | Verify with origin offset | [ ] |
| 5 | Build dry-run | [ ] |
| 6 | Build full execution | [ ] |
| 7 | Build resumability | [ ] |
| 8 | Build error handling | [ ] |

## Notes

- All tests assume coordinates 250-270, 3, 320-340 are clear/available
- Adjust coordinates if testing in a different world location
- Bot needs line-of-sight to placement locations
- Build command requires both bot AND player context
