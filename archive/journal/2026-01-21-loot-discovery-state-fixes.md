# Test Run: Entity Discovery, Loot Action, State Visibility Fixes

**Date:** 2026-01-21

## Summary

Fixed three issues discovered during autocollect testing:
1. `/polis/targets --mode entities` excluded dead entities
2. No way to loot items from entity corpses
3. State endpoint didn't show backpack contents

## Changes

### Issue 1: includeDead Parameter
- Added `includeDead` query parameter to targets endpoint
- Added `Alive` field to entity results
- CLI: `--include-dead` flag

### Issue 2: Loot Command
- New `loot <entityId>` command transfers items from dead entity inventory
- Works on already-butchered corpses (doesn't require `Harvestable == true`)
- Returns detailed transfer info

### Issue 3: BackpackContents
- State endpoint now includes `BackpackContents` field
- Shows items inside equipped backpacks via `IHeldBag.GetOrCreateSlots()`

## Test Plan

```bash
# Setup
./scripts/vsctl.py start --wait --window
./scripts/poliscli.py spawn
./scripts/poliscli.py select <BOT_ID>
export POLIS_BOT_ID=<BOT_ID>
./scripts/poliscli.py give game:knife-generic-copper
./scripts/poliscli.py equip righthand game:knife-generic-copper
./scripts/poliscli.py give game:linensack
./scripts/poliscli.py equip backpack0 game:linensack

# Test 1: Dead Entity Discovery
./scripts/poliscli.py spawnkill game:chicken-hen
./scripts/poliscli.py targets --mode entities --radius 16
# Should NOT show chicken (dead)
./scripts/poliscli.py targets --mode entities --radius 16 --include-dead
# Should show chicken with Alive=false

# Test 2: Loot Corpse
./scripts/poliscli.py butcher <CHICKEN_ID>
# If inventory was full, some items remain
./scripts/poliscli.py loot <CHICKEN_ID>
# Transfers remaining items to bot

# Test 3: Backpack Contents in State
./scripts/poliscli.py state
# Should show BackpackContents with items collected
```

## Files Modified

- `PolisTestHarness.cs` - includeDead param, Alive field, BackpackContents field
- `PolisBuilderNpcSystem.cs` - BackpackContents query, ExecuteLootCommand
- `scripts/poliscli.py` - --include-dead flag, loot subcommand
- `docs/KNOWN_ISSUES.md` - Marked issues as fixed

## Test Results (2026-01-21)

All three features verified working:

| Test | Result | Details |
|------|--------|---------|
| Dead entity discovery | ✅ PASSED | `--include-dead` shows dead chickens with `Alive: false` |
| Loot command | ✅ PASSED | `loot 594` transferred 4 feathers from butchered corpse |
| BackpackContents | ✅ PASSED | State shows `game:feather` x10, `game:bone-tiny` x1 |

### Carcass Investigation

After looting, chicken corpses don't automatically transform to carcass:
- **Player behavior:** Opening corpse inventory UI triggers VS to despawn entity and place `game:carcass-tiny` block
- **Bot behavior:** `loot` command transfers items but doesn't trigger transformation
- **Workaround:** Player must right-click corpse to trigger carcass placement

Carcass block workflow verified:
```bash
./scripts/poliscli.py targets --mode blocks -s carcass --radius 5
# Found: game:carcass-tiny at (242,3,274)

./scripts/poliscli.py mine 242 3 274
# Mined carcass, dropped game:bone-tiny

./scripts/poliscli.py pickup 596
# Collected bone into backpack
```

### Bugs Discovered

1. **Carcass transformation not triggered by bot** - Added to KNOWN_ISSUES.md
2. **Missing meat drops** - Butchering chickens only yields feathers, no meat

### Guidelines Updated

- `AGENTS.md`: Added bot cleanup step, visual inspection rules (2 block min distance, pitch for ground items, angle changes, offset spawns)
- `docs/TESTING_HARNESS.md`: Added 2 block minimum distance note to avoid player auto-pickup interference
