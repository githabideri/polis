# Container Transfer Implementation Plan (Phase 2)

**Date:** 2026-01-06  
**Status:** Draft plan

## Purpose
Define bot ↔ container transfer flow that matches VS inventory semantics and sync requirements.

## Known Engine Semantics (vsapi)

**Core inventory APIs:**
- `ItemSlot.TryPutInto(IWorldAccessor world, ItemSlot sinkSlot, int quantity = 1)` handles merge/stacking, calls `OnItemSlotModified`.
- `ItemSlot.MarkDirty()` queues inventory sync and calls `Inventory.DidModifyItemSlot(...)`.
- `InventoryBase.MarkSlotDirty(slotId)` triggers server → client slot sync.
- `BlockEntity.MarkDirty(redrawOnClient)` resyncs BE tree attributes and optionally redraws the block.
- Canonical call chain: `ItemSlot.TryPutInto` → `OnItemSlotModified` → `InventoryBase.DidModifyItemSlot` → `MarkSlotDirty` → `SlotModified` → `Collectible.OnModifiedInInventorySlot`.
- Inventory implementations like `InventoryDisplayed` call `BlockEntity.MarkDirty(true)` in `OnItemSlotModified`.

**Access checks:**
- `InventoryBase.CanPlayerAccess(...)` defaults to `true` unless overridden.
- Range/LOS validation is not enforced in `InventoryBase` by default; must be handled by the caller (e.g., BE or action logic).
- `Block.OnBlockInteractStart(...)` uses `EnumBlockAccessFlags.Use`; `Block.Activate(...)` does **not** enforce claims.
- `Block.CanPlaceBlock(...)` uses `EnumBlockAccessFlags.BuildOrBreak`.

## Observed Patterns (vssurvivalmod)

**Ground storage (`BEGroundStorage.TryPutItem`)**:
- Uses `hotbarSlot.TryPutInto(Api.World, invSlot, qty)`.
- Calls `MarkDirty()` on the block entity after modification.
- Uses `InventoryManager.TryGiveItemstack` when taking items out.
**Liquid containers (`BlockLiquidContainerBase`)**:
- After mutating slots, calls `slot.MarkDirty()` and `beContainer.MarkDirty(true)`.
**Crates (`BlockCrate`)**:
- Uses `TryPutInto(Api.World, ...)` and `hotbarslot.MarkDirty()` after transfer.

## Open Questions (Need Verification)
1) Any server packets required for container transfer when done by bots (IInventoryNetworkUtil)?

## Proposed Bot → Container Flow (Server)
1) Resolve target BE implementing `IBlockEntityContainer`.
2) Enforce validation:
   - Range/LOS checks for the target block.
   - Claims check: `world.Claims.TryAccess(..., EnumBlockAccessFlags.Use)`.
3) Select source slot from bot inventory (hands/backpacks).
4) Select destination slot from container inventory (use `GetSlotAt` for GroundStorage if a BlockSelection is available).
5) Move items:
   - `sourceSlot.TryPutInto(Api.World, destSlot, qty)`.
6) Sync:
   - `sourceSlot.MarkDirty()` and `destSlot.MarkDirty()`.
   - `blockEntity.MarkDirty(true)` (safe default for BE inventory changes).
   - `invbh.storeInv()` on the bot to persist/sync `seraphinventory`.

## Proposed Container → Bot Flow (Server)
1) Resolve target BE and container inventory.
2) Select source slot from container.
3) Transfer to bot using explicit slots (avoid `TryGiveItemStack` for PlayerBot):
   - `sourceSlot.TryPutInto(Api.World, botSlot, qty)`.
4) Sync:
   - `sourceSlot.MarkDirty()` + `blockEntity.MarkDirty(true)`.
   - `botSlot.MarkDirty()` + `invbh.storeInv()` for PlayerBot sync.

## Implementation Steps (Polis)
1) Add `/polis takefrom` and `/polis putinto` commands:
   - target BE by looked-at block selection.
2) Create `PolisContainerTransferAction`:
   - handles selection, transfer, and sync.
3) Add claims/permissions check before transfer.
4) Add debug logs: source/destination slot, quantity moved, failure reason.
5) For GroundStorage, allow `slotIndex` override or use `GetSlotAt(blockSelection)`.

## References
- `vsapi/Common/Inventory/ItemSlot.cs`
- `vsapi/Common/Inventory/InventoryBase.cs`
- `vsapi/Common/Collectible/Block/BlockEntity.cs`
- `vssurvivalmod/BlockEntity/BEGroundStorage.cs`
- `docs/research/phase-2/2026-01-14-container-transfer-correctness.md`
- `docs/research/misc/2026-01-13-claims-enforcement-patterns.md`
