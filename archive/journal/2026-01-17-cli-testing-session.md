# CLI Testing Session Report

**Date:** 2026-01-17
**Tester:** Claude + User

## Summary

Comprehensive testing of the `poliscli.py` CLI wrapper and bot action primitives. Validated butcher workflow, container interactions, movement, and discovery commands. Identified several bugs and areas for improvement.

## Test Environment

- Server running with HTTP harness on port 8585
- Bot selected for testing
- Player UID set via environment variable

---

## Tests Performed

### 1. Basic Connectivity
**Status:** PASS

```bash
polis status   # OK - worldReady: true
polis players  # OK - 1 player online
polis bots     # OK - listed bots with positions
```

### 2. Spawn with Offset
**Status:** PASS (after fix)

**Issue Found:** CLI was sending `spawnOffset` as string `"2,0,0"` but server expects `double[]` array `[2,0,0]`.

**Fix Applied:** Updated `cmd_spawn()` to send array format.

```bash
polis spawn  # Now spawns 2 blocks offset from player (not on top)
```

**Enhancement Added:**
- `--offset X Y Z` flag for custom offset
- `--worldspawn` flag to spawn at world spawn instead of near player
- Default offset `[2,0,0]` when spawning near player

**Future Enhancement Noted:** Support `spawnOffset: "forward:3"` to spawn in player's look direction using `player.Entity.ServerPos.Yaw`.

### 3. Knife Item Code Resolution
**Status:** RESOLVED

**Issue:** `game:knife-copper` not found - incorrect item code format.

**Resolution:** Correct format is `game:knife-{type}-{material}`:
- `game:knife-generic-copper` (not `game:knife-copper`)
- Types: `generic`, `dagger`, `stiletto`, `khanjar`, `baselard`
- Materials: `flint`, `copper`, `tinbronze`, `iron`, `steel`, etc.

**Docs Updated:** CLI.md, butcher plan doc, ROADMAP.md, journal

### 4. Butcher Workflow
**Status:** PARTIAL - needs investigation

#### 4.1 Entity Spawning for Butcher Testing

**Problem:** Spawning animals and killing them with delay causes animals to run away before death, leaving corpse out of range.

**Solution Implemented:** Added `spawnkill` CLI command:
```bash
polis spawnkill game:sheep-bighorn-adult-male
# Spawns 1 block from bot position, kills immediately
# Returns entity ID for butchering
```

**Entity Code Format:** `game:{animal}-{variant}-{age}-{gender}`
- Example: `game:sheep-bighorn-adult-male`

#### 4.2 Butcher Action

```bash
polis give game:knife-generic-copper  # Equip knife
polis spawnkill game:sheep-bighorn-adult-male  # Spawn+kill → entity #NNN
polis butcher <entity-id>  # Butcher the corpse
```

**Result:** Bot received `2x game:redmeat-raw` in left hand.

#### 4.3 ISSUE: Incomplete Harvest Inventory Transfer

**Observation:** After bot butchered sheep:
- Bot received: 2x redmeat-raw
- User manually checked corpse: **still had meat inside**
- Corpse did NOT despawn into carcass (skeleton) because items remained

**Expected Behavior:** `SetHarvested()` should populate harvest inventory, `TransferHarvestInventory()` should transfer ALL items to bot.

**Actual Behavior:** Only partial transfer occurred. Sheep harvest inventory likely contains multiple item types (meat, fat, hide) across multiple slots, but bot only received 2 meat.

**Relevant Code Path:**
1. `PolisButcherEntityAction.Start()` calls `harvestBehavior.SetHarvested(player, multiplier)`
2. `TransferHarvestInventory()` reads from `entity.WatchedAttributes["harvestableInv"]`
3. Iterates slots with `harvestInv.Count` and calls `PolisInventoryHelpers.TryInsertIntoBotInventory()`

**Investigation Needed:**
- Is `qslots` being read correctly?
- Are all slots being iterated?
- Is `TryInsertIntoBotInventory` failing silently for some items?
- Is bot inventory slot matching failing (e.g., can't stack different item types)?

**Note:** This is NOT an inventory capacity issue - each slot can hold 32-64 items. The issue is items not being transferred at all.

### 5. VS Two-Stage Harvest System
**Status:** DOCUMENTED

VS has a two-stage harvest for animals:

| Stage | Entity/Block | Action | Drops |
|-------|--------------|--------|-------|
| 1 | Dead animal (Entity) | Butcher with knife | Meat, fat, hide |
| 2 | Carcass (Block) | Mine/break | Bones |

**Discovery:** After user manually emptied the sheep corpse:
- Corpse entity despawned
- `game:carcass-medium` BLOCK appeared at same location
- Carcass is harvestable by breaking (mine), not butcher

**Commands for Carcass:**
```bash
polis look  # Found: blockSelection.code = "game:carcass-medium"
polis mine 225 3 269 --autocollect  # Breaks carcass, drops bones
```

**Carcass Mine Result:**
- 1x `butchering:strongbone`
- 4x `game:bone`

**Note:** `autocollect` flag on mine did not auto-pickup items - they dropped on ground. Needed manual `polis pickup <id>` for each.

### 6. Container Interaction
**Status:** PASS

```bash
polis targets --mode blocks  # Found chest at (224, 3, 270)
polis putinto 224 3 270 1    # Store from left hand (slot 1) into chest
# Result: "transferred 2 items from bot to container"
```

**Multiple Store Cycles:** Due to bot having only 2 hand slots (right=knife, left=items), storing bones required multiple pickup/store cycles:
```bash
polis pickup <item-id>        # Pick item
polis putinto 224 3 270 1     # Store it
# ... repeat for each item
```

### 7. Movement (goto --wait)
**Status:** PASS

```bash
polis goto 245 3 261 --wait
# Result: arrived: true, position: [244.39, 3.0, 261.63]
```

**Note:** One goto timed out in CLI but actually completed successfully (server-side action finished after CLI timeout).

### 8. Discovery Commands
**Status:** PASS

```bash
polis targets --mode entities --radius 20  # Lists nearby entities
polis targets --mode blocks --radius 20    # Lists nearby interactable blocks
polis look  # Raytrace what player is looking at
```

**Limitation:** Radius appears capped at 16 blocks regardless of requested value.

**Issue:** `targets` command did not show:
- Harvested but non-empty corpses (after bot butchered it)
- Possibly filters out "harvested" entities even if they still contain items

---

## CLI Enhancements Made

### 1. Spawn Offset (Fixed)
- Changed `spawnOffset` from string to array format
- Added `--offset X Y Z` and `--worldspawn` flags
- Default 2-block offset when spawning near player

### 2. New Command: `spawnkill`
```bash
polis spawnkill <entity-code> [x y z]
```
- Spawns entity and immediately kills it
- Defaults to 1 block from bot position
- Returns entity ID for butchering
- Useful for testing butcher workflow without animals running away

---

## Bugs / Issues Identified

### Critical
1. **Incomplete Harvest Transfer:** Bot butcher action does not transfer all items from harvest inventory. Needs investigation of `TransferHarvestInventory()` logic.

### Medium
2. **Targets Filtering:** `targets --mode entities` may not show harvestable corpses that have been partially harvested.

3. **Mine Autocollect:** `--autocollect` flag on mine command did not auto-pickup dropped items.

4. **CLI Argparse Order:** Global flags (`--player`, `--bot`) must come AFTER subcommand, not before. Argparse quirk with subparser parents.

### Low / Enhancements
5. **Container Registry:** No way to remember chest locations. Proposed: shadow registry for containers/workstations (similar to bot registry) so bots can reference "main storage" without re-discovering coordinates.

6. **Spawn Forward Direction:** Add support for spawning in player's look direction using yaw calculation.

---

## Test Commands Reference

### Full Butcher Workflow (Working)
```bash
export POLIS_PLAYER_UID="abc+123YourPlayerUidHere"
export POLIS_BOT_ID="<id>"

# Setup
polis give game:knife-generic-copper

# Spawn and kill animal
polis spawnkill game:sheep-bighorn-adult-male
# Note entity ID from output

# Butcher
polis butcher <entity-id>

# Check inventory
polis state

# Store in chest
polis putinto <chest-x> <chest-y> <chest-z> 1
```

### Carcass (Bones) Workflow
```bash
# After corpse becomes carcass block
polis look  # Confirm carcass-medium block

# Mine to get bones
polis mine <x> <y> <z>

# Pickup bones (autocollect not working)
polis state  # See Items[] list with IDs
polis pickup <item-id>
polis putinto <chest-x> <chest-y> <chest-z> 1
# Repeat for each bone
```

---

## Files Modified This Session

| File | Changes |
|------|---------|
| `scripts/poliscli.py` | Fixed spawnOffset array format, added `--offset`/`--worldspawn` flags, added `spawnkill` command |
| `docs/CLI.md` | Updated knife item code example |
| `docs/plans/2026-01-15-polis-butcher-entity-action.md` | Fixed knife item code |
| `docs/ROADMAP.md` | Updated butcher status from blocked to resolved |
| `docs/journal/2026-01-17-poliscli-implementation.md` | Updated knife code resolution |

---

## Next Steps

1. **Investigate incomplete harvest transfer** - Debug `TransferHarvestInventory()` to find why not all items are collected
2. **Fix mine autocollect** - Ensure drops are picked up after mining
3. **Consider container registry** - Design shadow registry for important blocks/containers
4. **Test remaining commands** - `takefrom`, environment variables, error handling
