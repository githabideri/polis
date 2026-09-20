# Test Report: Autocollect Timing, Silent Failures, CLI Parsing

**Date:** 2026-01-20 (Updated 2026-01-21)
**Build:** Successful (0 warnings, 0 errors)

## Summary

Implemented fixes for autocollect timing, range pre-validation, CLI parsing, and harvest inventory. Initial testing revealed a **pre-existing bug** in `PolisInventoryHelpers.TryPutIntoBackpacks` that caused server crashes - this was **FIXED in commit 9f1fa96**.

## Test Results (2026-01-20)

| Test | Status | Notes |
|------|--------|-------|
| CLI container-contents (coordinates) | PASS | `./poliscli.py container-contents 224 3 270` |
| CLI container-contents (-c flag) | PASS | `./poliscli.py container-contents -c main-chest` |
| Range pre-validation: takefrom | PASS | Returns "Out of range: 9.6 > 4.5" immediately |
| Range pre-validation: putinto | PASS | Returns "Out of range: 9.3 > 4.5" immediately |
| Range pre-validation: harvest | PASS | Returns "Out of range: 13.4 > 4.5" immediately |
| Range pre-validation: harvestcrop | PASS | Returns "Out of range: 13.4 > 4.5" immediately |
| Butcher (no autocollect) | PASS | Successfully butchered chicken |
| Butcher (with autocollect) | FAIL | Inventory slot error with backpack |
| Mine (with autocollect + backpack) | FAIL | Server crash - 100k errors |

## Verification Test Results (2026-01-21)

After the backpack bug fix (commit 9f1fa96), retested autocollect:

| Test | Status | Notes |
|------|--------|-------|
| Mine with autocollect + backpack | PASS | "mined, collected 2" - items went to backpack contents |
| Butcher with autocollect | PASS | "Butchered game:chicken-hen" - no items on ground |
| Range pre-validation: takefrom | PASS | "Out of range: 40.6 > 4.5" - immediate failure |
| CLI container-contents (coords) | PASS | Works with positional args |
| CLI container-contents (-c flag) | PASS | Works with named container |

**Note:** Items collected via autocollect go into backpack's internal slots (bag contents), which are not visible in `/polis/state` output. The state endpoint shows the backpack item but not its contents.

## Critical Bug Found (FIXED)

**Location:** `PolisInventoryHelpers.cs` in `TryPutIntoBackpacks`

**Error:**
```
Exception: Supplied slot is not part of this inventory (gearinv-565)!
   at PolisInventoryHelpers.TryPutIntoSlot(...)
   at PolisInventoryHelpers.TryPutIntoBackpacks(...)
   at PolisInventoryHelpers.TryInsertIntoBotInventory(...)
   at PolisMineBlockAction.CollectDrops(...)
   at PolisMineBlockAction.OnTick(...)
```

**Root Cause:** Was using `TryPutIntoSlot` with wrong inventory context for bag content slots.

**Fix:** Commit 9f1fa96 - Changed to use `TryPutIntoBagContent` which properly handles bag slot operations without inventory context mismatch.

## Changes Implemented

1. **PolisMineBlockAction** - Added 1.2s delayed collection in OnTick
2. **PolisHarvestBlockAction** - Added 1.2s delayed collection in OnTick
3. **PolisHarvestCropAction** - Added 1.2s delayed collection in OnTick
4. **PolisHarvestBlockAction.CollectDrops** - Fixed to use bot inventory instead of player
5. **ExecuteTakeFromCommand** - Added range pre-validation
6. **ExecutePutIntoCommand** - Added range pre-validation
7. **ExecuteHarvestCommand** - Added range pre-validation
8. **ExecuteHarvestCropCommand** - Added range pre-validation
9. **poliscli.py container-contents** - Fixed to use `-c` flag for names, positional for coords

## Remaining Issues

1. **targets excludes dead entities:** `/polis/targets?mode=entities` filters `e.Alive`, so dead corpses (for butchering) aren't discoverable
2. **No loot corpse action:** Can't transfer remaining items from entity corpses - `takefrom` only works with block containers
3. **State doesn't show backpack contents:** Items in bag slots aren't visible in `/polis/state`

## Files Changed

- `PolisBuilderNpcSystem.cs` - Delayed collection + range pre-validation
- `PolisInventoryHelpers.cs` - Fixed bag-content insertion (commit 9f1fa96)
- `scripts/poliscli.py` - CLI container-contents fix
