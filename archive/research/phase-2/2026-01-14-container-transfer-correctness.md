# Container Transfer Correctness (Server-Side)

Date: 2026-01-14

Purpose
- Capture the canonical server-side call order for moving items into/out of containers and syncing clients.
- Identify required land-claim checks (Use vs BuildOrBreak) when transfer is initiated server-side.

Summary
- The canonical transfer flow is `ItemSlot.TryPutInto(...)` (or `TryPutInto(IWorldAccessor, ...)`) -> `OnItemSlotModified` on both sink and source -> `InventoryBase.DidModifyItemSlot` -> `InventoryBase.MarkSlotDirty` and `SlotModified` event -> collectible `OnModifiedInInventorySlot` callback.
- `MarkSlotDirty` only queues the slot for resync; container block entities still need a `BlockEntity.MarkDirty(...)` path to sync tree attributes or redraw, which is typically wired by overriding `InventoryBase.OnItemSlotModified` (e.g., `InventoryDisplayed`) or calling `InventoryPerPlayer.MarkDirty()` for per-player inventory logic.
- Claim checks are enforced by `Block.OnBlockInteractStart` via `EnumBlockAccessFlags.Use`; server-side activation via `Block.Activate(...)` does not do claim checks, so callers must explicitly test `world.Claims.TryAccess(..., Use)` (and `BuildOrBreak` for placement/breaking flows).
- Vanilla container examples in `vssurvivalmod` follow this pattern and explicitly call `Inventory.MarkDirty()` and `BlockEntity.MarkDirty(true)` after server-side content changes.

Step-by-step call order (slot operations + dirty calls)
1) Build a move operation (or call `ItemSlot.TryPutInto(IWorldAccessor, ...)` which builds one) and call `ItemSlot.TryPutInto(ItemSlot sinkSlot, ref ItemStackMoveOperation op)`.
   - Evidence: `ItemSlot.TryPutInto` creates `ItemStackMoveOperation` then calls the overload (`vsapi/Common/Inventory/ItemSlot.cs`).
2) `ItemSlot.TryPutInto` validates permissions and compatibility.
   - Checks: `sinkSlot.CanTakeFrom(this)`, `CanTake()`, `itemstack != null`, `sinkSlot.inventory?.CanContain(...)` (`vsapi/Common/Inventory/ItemSlot.cs`).
3) If sink is empty: take `q` from source, assign to sink, set `op.MovedQuantity`, then call `sinkSlot.OnItemSlotModified(...)` and `source.OnItemSlotModified(...)`.
   - Evidence: sink empty branch in `ItemSlot.TryPutInto` (`vsapi/Common/Inventory/ItemSlot.cs`).
4) If sink has items: build `ItemStackMergeOperation`, clamp requested quantity, call `Collectible.TryMergeStacks`, then if moved call `OnItemSlotModified` on sink and source.
   - Evidence: merge branch in `ItemSlot.TryPutInto` (`vsapi/Common/Inventory/ItemSlot.cs`).
5) `ItemSlot.OnItemSlotModified` calls `inventory.DidModifyItemSlot(this, sinkStack)` and updates transition states.
   - Evidence: `ItemSlot.OnItemSlotModified` (`vsapi/Common/Inventory/ItemSlot.cs`).
6) `InventoryBase.DidModifyItemSlot` calls `MarkSlotDirty(slotId)`, `OnItemSlotModified(slot)`, fires `SlotModified`, then invokes `Collectible.OnModifiedInInventorySlot(...)`.
   - Evidence: `InventoryBase.DidModifyItemSlot` (`vsapi/Common/Inventory/InventoryBase.cs`).
7) `InventoryBase.MarkSlotDirty` queues the slot id in `dirtySlots` for client resync/redraw.
   - Evidence: `InventoryBase.MarkSlotDirty` and comments (`vsapi/Common/Inventory/InventoryBase.cs`).
8) Container/block-entity sync path (required for server-side changes):
   - If inventory uses `InventoryDisplayed`, it overrides `OnItemSlotModified` and calls `container.MarkDirty(true)`.
     - Evidence: `InventoryDisplayed.OnItemSlotModified` (`vsapi/Common/Inventory/InventoryDisplayed.cs`).
   - If inventory uses `InventoryPerPlayer`, `MarkSlotDirty` is intentionally a no-op and `ItemSlotPerPlayer` explicitly calls `Inventory.MarkDirty()`, which calls `BlockEntity.MarkDirty()` to sync `PlayerQuantities`.
     - Evidence: `InventoryPerPlayer.MarkSlotDirty`/`MarkDirty` and `ItemSlotPerPlayer.TryPutInto` (`vsapi/Common/Inventory/InventoryPerPlayer.cs`, `vsapi/Common/Inventory/ItemSlotPerPlayer.cs`).
   - For custom block entities implementing `IBlockEntityContainer`, ensure your inventory’s `OnItemSlotModified` calls `BlockEntity.MarkDirty(...)` (or call `MarkDirty` yourself after a transfer) if you store inventory in the block entity tree attributes.
     - Evidence: `IBlockEntityContainer.Inventory` contract (`vsapi/Common/Collectible/IBlockEntityContainer.cs`) and `BlockEntity.MarkDirty(...)` semantics (`vsapi/Common/Collectible/Block/BlockEntity.cs`).
   - `BlockLiquidContainerBase.SetContent(BlockPos, ItemStack)` uses `DummySlot.TryPutInto(...)` then calls `beContainer.Inventory[slot].MarkDirty()` and `beContainer.MarkDirty(true)` to sync placed container contents.
     - Evidence: `BlockLiquidContainerBase.SetContent` (`vssurvivalmod/Systems/Liquid/BlockLiquidContainerBase.cs`).
   - `BlockLiquidContainerBase.TryTakeContent(BlockPos, int)` mutates the slot directly and then calls `Inventory[slot].MarkDirty()` and `becontainer.MarkDirty(true)`.
     - Evidence: `BlockLiquidContainerBase.TryTakeContent` (`vssurvivalmod/Systems/Liquid/BlockLiquidContainerBase.cs`).
   - `BlockCrate` uses `hotbarslot.TryPutInto(Api.World, wslot.slot, quantity)` for container transfer and then calls `hotbarslot.MarkDirty()` after moving items.
     - Evidence: `BlockCrate` container interaction (`vssurvivalmod/Block/BlockCrate.cs`).

Required claim checks (Use vs BuildOrBreak)
- Use (container interaction): `Block.OnBlockInteractStart` calls `world.Claims.TryAccess(..., EnumBlockAccessFlags.Use)` and returns false if denied. Server-side `Block.Activate(...)` has no claim check.
  - Evidence: `Block.OnBlockInteractStart` and `Block.Activate` (`vsapi/Common/Collectible/Block/Block.cs`).
- BuildOrBreak (placement/breaking): `Block.CanPlaceBlock` checks `TryAccess(..., EnumBlockAccessFlags.BuildOrBreak)`; other block placement/breaking paths should use the same flag.
  - Evidence: `Block.CanPlaceBlock` (`vsapi/Common/Collectible/Block/Block.cs`).
- For server-side container transfers driven by NPCs/commands, explicitly enforce `world.Claims.TestAccess/TryAccess(..., Use)` at the target block position before moving items. Use `BuildOrBreak` when the action modifies blocks (placing/breaking) rather than only manipulating container contents.
  - Evidence: `ILandClaimAPI.TestAccess/TryAccess` and `EnumBlockAccessFlags` (`vsapi/Common/API/ILandClaimAPI.cs`, `vsapi/Common/API/EnumBlockAccessFlags.cs`).

Open questions
- The inventory network utility implementation (`IInventoryNetworkUtil`) lives in engine code; verify whether any additional server-side packet steps are required when inventories are not opened by a player.

Implications
- For server-driven container transfer actions, the safest canonical flow is `ItemSlot.TryPutInto` + explicit claim checks + `BlockEntity.MarkDirty(...)` on the container (or use an inventory class that already wires this) to ensure clients receive updates.
