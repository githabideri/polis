# Butcher Fix and Inventory Gaps (2026-01-17)

## Summary

Fixed the butcher harvest transfer bug, verified the fix works, but discovered inventory capacity limitations and missing features needed for complete butchering workflow.

## The Bug

**Problem**: Butchering a dead animal transferred items to the bot but the corpse didn't despawn to carcass.

**Root Cause**: `TransferHarvestInventory` created a LOCAL copy of the harvest inventory from tree attributes:
```csharp
// OLD CODE - WRONG
var harvestInv = new InventoryGeneric(16, "harvestSlot-0", api);
harvestInv.FromTreeAttributes(targetEntity.WatchedAttributes.GetTreeAttribute("harvestableInv"));
```

Items were cloned and transferred to bot, but slots were NOT cleared in the actual inventory. VS checks `EntityBehaviorHarvestable.Inventory` for despawn logic, not our copy.

**Fix**: Access the actual inventory directly and clear slots after transfer:
```csharp
// NEW CODE - CORRECT
var harvestBehavior = targetEntity.GetBehavior<EntityBehaviorHarvestable>();
var harvestInv = harvestBehavior.Inventory;

// After transfer:
slot.Itemstack = null;  // or reduce stack size for partial
slot.MarkDirty();       // Critical - notify VS of change
```

## Test Results

### Test 1: Bot with no free hands
- Bot 421 had knives in BOTH hands (leftover from prior session)
- Butcher command succeeded (called `SetHarvested`) but transfer failed (no space)
- Sheep marked as harvested but all items remained in corpse

### Test 2: Bot with 1 free hand
- Stored knife in chest, kept 1 hand empty
- Spawned sheep 439, butchered it
- Bot received 2x redmeat-raw in left hand
- **Verified**: Meat slot in corpse WAS cleared (fix works!)
- **But**: Fat remained because bot had no second free slot
- Corpse didn't despawn (still has items)

### Key Finding
Sheep drop multiple item types (meat + fat). Bot has only 2 hand slots. With knife in right hand, only 1 slot available. Fix is correct, but inventory capacity is the limiting factor.

## VS Corpse Mechanics (Researched)

From `refs/vsessentialsmod/Entity/Behavior/BehaviorHarvestable.cs`:

1. `EntityBehaviorHarvestable` extends `EntityBehaviorContainer`
2. `SetHarvested(IPlayer, float)` populates harvest inventory with drops
3. After `SetHarvested()`, corpse acts like a container (players right-click to open GUI and take items)
4. Corpse-to-carcass transition: Only when `inv.Empty && DropsGenerated`
5. The despawn timer only starts after inventory is completely empty

**Two-Stage Harvest Process**:
1. Dead animal (entity) → butcher with knife → meat, fat, hide
2. Carcass (block) → mine/break → bones

## Identified Gaps

### 1. Debug Mode Not Available via Harness
- `/polis debug on` works in-game chat
- HTTP harness returns "Unknown command: debug"
- Need to expose debug toggle via `/polis/command` endpoint

### 2. Equip Backpack Command Missing
- Backpack slots are 17 and 18
- Current `/polis equip` only supports `lefthand`/`righthand`
- `TryInsertIntoBotInventory` tries hands FIRST, then backpack slots
- Giving a linensack puts it in hand, not backpack slot
- Need: `equip backpack <bot> <slotnum>` command

### 3. Loot Entity Action Missing
- After partial butcher, corpse has remaining items
- No way for bot to re-open corpse and take remaining items
- Need: `loot <bot> <entityId>` action to transfer remaining items

### 4. Move Slot Command Missing
- No way to move items between arbitrary inventory slots
- Would help relocate bags from hand to backpack slot
- Need: `move <bot> <fromSlot> <toSlot>` command

## Inventory Slot Layout Reference

| Slot | Purpose |
|------|---------|
| 0-14 | Main hotbar/inventory |
| 15 | Right hand |
| 16 | Left hand |
| 17 | Backpack slot 0 |
| 18 | Backpack slot 1 |

## Files Changed

- `PolisBuilderNpcSystem.cs` (lines 5861-5915): `TransferHarvestInventory` fix
- `docs/ROADMAP.md`: Updated with fix details

## Next Steps

1. **Immediate**: Test butcher with bot that has equipped backpack (more storage)
2. **Short-term**:
   - Add debug command to harness
   - Add equip backpack command
   - Add loot entity action
3. **Future**: Consider auto-retry butcher if partial transfer (loop until inventory full or corpse empty)
