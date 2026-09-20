# Bot Inventory Sync Flow (Delta Notes)

**Date:** 2026-01-14  
**Scope:** New/updated findings only; avoids restating slot tables already captured in `phase-2/2026-01-06-bot-inventory-research.md`.

## What is new

### Persistence + sync path for `seraphinventory`
- `EntityBehaviorContainer.storeInv()` is the authoritative write/sync path for entity inventories:
  - Writes inventory into `entity.WatchedAttributes` under `InventoryClassName` (for bots: `"seraphinventory"`).
  - Calls `entity.WatchedAttributes.MarkPathDirty(InventoryClassName)` to trigger sync.
  - Marks the chunk modified for persistence.
- This is the missing link for the earlier open question: bot inventory persistence is not automatic on slot change; it must flow through `storeInv()` (or the entity serialization hooks that call it).
- Evidence: `vsessentialsmod/Entity/Behavior/BehaviorContainer.cs`

### Slot dirty vs. inventory storage
- `ItemSlot.MarkDirty()` triggers `InventoryBase.DidModifyItemSlot(...)` and the per-slot dirty tracking, but **does not** write the inventory into WatchedAttributes.
- That means server-side writes should pair `slot.MarkDirty()` with `invbh.storeInv()` for deterministic persistence and client sync.
- Evidence: `vsapi/Common/Inventory/ItemSlot.cs`, `vsapi/Common/Inventory/InventoryBase.cs`, `vsessentialsmod/Entity/Behavior/BehaviorContainer.cs`

## Minimal insertion flow (server)
1) Resolve `EntityBehaviorSeraphInventory` for the bot.
2) Choose slot id (hands/backpacks as previously documented).
3) Insert with `ItemSlot.TryPutInto(...)` or direct `Itemstack` assignment.
4) `slot.MarkDirty()`.
5) `invbh.storeInv()` to persist + sync.
6) Optional: `entity.WatchedAttributes.MarkAllDirty()` if you want an aggressive full sync.

## Implications
- Any direct bot inventory edits that skip `storeInv()` risk being lost or not synced.
- `EntityBehaviorSeraphInventory` does not override `Inventory_SlotModified` to call `storeInv()`, so you must do it explicitly for bot hands/backpacks.

## Key symbols
- `EntityBehaviorContainer.storeInv()` → `vsessentialsmod/Entity/Behavior/BehaviorContainer.cs`
- `EntityBehaviorSeraphInventory.InventoryClassName` = `"seraphinventory"` → `docs/vssurvivalmod/Entities/EntityPlayerBot.cs`
- `ItemSlot.MarkDirty()` → `vsapi/Common/Inventory/ItemSlot.cs`
- `InventoryBase.DidModifyItemSlot(...)` → `vsapi/Common/Inventory/InventoryBase.cs`
