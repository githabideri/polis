# Grind Action Testing Report

**Date:** 2026-01-22
**Feature:** Quern grinding action for polisbots
**Branch:** vk/6663-implement-quern

## Overview

Implemented and tested the `grind` command which allows polisbots to interact with quern blocks to grind items (grain → flour). The implementation follows the existing held-use block action pattern (similar to harvest).

## Test Environment

- VS game running with polis-builder-npc mod
- Test world: test-lands
- Querns pre-placed at coordinates 229,3,270 and 229,3,272
- Bot spawned and positioned near querns

## Test Scenarios

### 1. Count-Limited Grind (`--count 3`)

**Setup:**
- Put 10 grain-spelt into quern input slot
- Bot positioned within range of quern

**Command:**
```bash
./scripts/poliscli.py grind 229 3 270 --count 3
```

**Result:** ✅ PASS
- Ground exactly 3 items
- Bot played hit animation during grinding
- Quern showed grinding visual/audio
- Input reduced from 10 to 7 grain-spelt
- Output increased by 3 flour

### 2. Duration-Limited Grind (`--duration 5`)

**Setup:**
- 7 grain-spelt remaining in quern input

**Command:**
```bash
./scripts/poliscli.py grind 229 3 270 --duration 5
```

**Result:** ✅ PASS
- Ground 1 item (grind time ~4s per item)
- Stopped after ~5 seconds as expected
- Input reduced to 6 grain-spelt

### 3. Unlimited Grind (until input exhausted)

**Setup:**
- 6 grain-spelt remaining in quern input

**Command:**
```bash
./scripts/poliscli.py grind 229 3 270
```

**Result:** ✅ PASS
- Ground all 6 remaining items
- Total grinding time ~24 seconds
- Quern input slot now empty
- Output slot contains flour

### 4. Error: Empty Quern

**Setup:**
- Quern with empty input slot

**Command:**
```bash
./scripts/poliscli.py grind 229 3 270
```

**Result:** ✅ PASS (proper error handling)
- Returns error: "quern has nothing to grind"
- Exit code 1

### 5. Error: Non-Quern Block

**Command:**
```bash
./scripts/poliscli.py grind 229 3 271  # pointing at non-quern block
```

**Result:** ✅ PASS (proper error handling)
- Returns error: "not a quern block"
- Exit code 1

### 6. Error: Out of Range

**Setup:**
- Bot positioned far from quern

**Command:**
```bash
./scripts/poliscli.py grind 229 3 270
```

**Result:** ✅ PASS (proper error handling)
- Returns error with distance info
- Exit code 1

## Implementation Details

### Files Modified

1. **PolisBuilderNpcSystem.cs** (+419 lines)
   - `PolisGrindBlockAction` class - timed action using OnBlockInteractStart/Step/Stop
   - `ExecuteGrindCommand` handler - validates quern, creates action
   - Command switch case for "grind"

2. **scripts/poliscli.py** (+43 lines)
   - `cmd_grind` function
   - Subparser with `--count`, `--duration`, `--no-wait` options

3. **docs/CLI.md**
   - Added grind command documentation

4. **docs/TESTING_HARNESS.md**
   - Added grind endpoint and LastAction examples

### Key Technical Points

- Uses `SelectionBoxIndex = 1` to trigger grinding (index 0 opens GUI)
- Tracks output slot to count items ground
- Default grind time is 4.0f seconds per item (from `GrindingProps.grindTime`)
- Plays "hit" animation during grinding
- Proper cleanup on completion or interruption

## Commit

```
687b793 Add grind command for quern grinding action
```

## Conclusion

All test scenarios passed. The grind action correctly:
- Grinds items when count/duration limits specified
- Grinds until input exhausted when no limits
- Reports proper errors for invalid targets
- Integrates with CLI and harness documentation
