# GroundStorage Contents Access (Harness)

Date: 2026-01-13

Purpose
Determine how to read `BlockEntityGroundStorage` contents without UI; identify access points, minimal JSON summary, and sync/dirty requirements.

Summary
- Contents are exposed via `BlockEntityGroundStorage.Inventory` (override of `InventoryBase`), which returns the internal `InventoryGeneric inventory` holding the `ItemSlot`s. Iterate slots and read `slot.Itemstack?.Collectible?.Code` + `slot.StackSize`.
- Slot selection by hit position is handled by `GetSlotAt(BlockSelection)` (layout-aware). Useful when a ray-hit selection exists and you want the specific slot.
- Modifying stacks uses `slot.MarkDirty()` and `MarkDirty(true)` on the block entity; clearing all slots can delete the block entity (`SetBlock(0, Pos)`), so emptying is destructive.

Evidence (vssurvivalmod repo)
- Inventory exposure + internal field: `vssurvivalmod/BlockEntity/BEGroundStorage.cs:43-148` (`inventory`, `Inventory` override).
- Slot mapping by layout: `vssurvivalmod/BlockEntity/BEGroundStorage.cs:713-742` (`GetSlotAt`).
- Total count helper: `vssurvivalmod/BlockEntity/BEGroundStorage.cs:117-124` (`TotalStackSize`).
- Dirty/sync patterns: `vssurvivalmod/BlockEntity/BEGroundStorage.cs:288-300` (`slot.MarkDirty`, `MarkDirty(true)`), `vssurvivalmod/BlockEntity/BEGroundStorage.cs:678-681` (`MarkDirty()` after interaction).
- Empty-inventory deletes BE: `vssurvivalmod/BlockEntity/BEGroundStorage.cs:254-260` (`CheckInventoryClearedMidTick`), `vssurvivalmod/BlockEntity/BEGroundStorage.cs:683-686` (empties block on interact).
- Typical BE lookup: `vssurvivalmod/Block/BlockGroundStorage.cs:70-106` (`GetBlockEntity<BlockEntityGroundStorage>(pos)`).

Deliverables
- Which property/method exposes contents: `BlockEntityGroundStorage.Inventory` (returns `InventoryBase`, backed by `InventoryGeneric inventory`), and `GetSlotAt(BlockSelection)` for selection-aware slot access.
- Minimal JSON summary suggestion:
```json
{
  "slots": [
    { "slot": 0, "code": "game:firewood", "qty": 4 }
  ]
}
```
- Sync/dirty requirements:
  - Read-only: no `MarkDirty` needed.
  - Write: call `slot.MarkDirty()` on changed slots and `be.MarkDirty(true)` (or `be.MarkDirty()` depending on context) to sync/retessellate; emptying all slots triggers removal of the block entity (`SetBlock(0, Pos)`).

Open questions
- None beyond thread safety: there is `inventoryLock` because tesselation is on another thread; if harness reads off-thread, wrap access in `lock (be.inventoryLock)`.

Implications for harness design
- Use `BlockAccessor.GetBlockEntity<BlockEntityGroundStorage>(pos)` and read `be.Inventory` (iterate slots).
- Avoid destructive emptying unless explicitly intended; empty inventory removes the ground storage block entity.
- If you later allow writes, follow the `MarkDirty` pattern in the class to keep client sync correct.
