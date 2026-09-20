# Held-Item Visual Sync for PlayerBot (Local Repo Scan)

Date: 2026-01-13
Scope: local source only (`vsapi`, `vsessentialsmod`, `vssurvivalmod`).

## Sources (local)
- `vsapi/Common/Inventory/ItemSlot.cs`
- `vsapi/Common/Inventory/InventoryBase.cs`
- `vsapi/Common/Entity/EntityPlayer.cs`
- `vsessentialsmod/EntityRenderer/EntityShapeRenderer.cs`
- `vsessentialsmod/EntityRenderer/EntityPlayerShapeRenderer.cs`
- `vsessentialsmod/Entity/Behavior/BehaviorContainer.cs`
- `vsessentialsmod/Inventory/InWorldContainer.cs`
- `vssurvivalmod/Entities/EntityPlayerBot.cs`
- `vssurvivalmod/Systems/EntityActivitySystem/Action/EquipAction.cs`
- `vssurvivalmod/Systems/EntityActivitySystem/Action/UnequipAction.cs`
- `vssurvivalmod/Entity/Behavior/BehaviorAttachable.cs`

## Evidence notes
- `EntityPlayer.RightHandItemSlot` and `LeftHandItemSlot` are computed from the player’s inventory manager:
  - `RightHandItemSlot` returns `player?.InventoryManager.ActiveHotbarSlot`.
  - `LeftHandItemSlot` returns `player?.InventoryManager?.GetHotbarInventory()?[11]`.
  - Source: `vsapi/Common/Entity/EntityPlayer.cs`.
- The held item is rendered every frame from those slots:
  - `EntityShapeRenderer.RenderHeldItem(...)` pulls `eagent?.RightHandItemSlot` / `LeftHandItemSlot` and feeds that into `capi.Render.GetItemStackRenderInfo(...)`.
  - Source: `vsessentialsmod/EntityRenderer/EntityShapeRenderer.cs`.
- PlayerBot hand slots are **InventoryGear indices**:
  - `EntityPlayerBot.RightHandItemSlot => invbh.Inventory[15]`.
  - `EntityPlayerBot.LeftHandItemSlot => invbh.Inventory[16]`.
  - Source: `vssurvivalmod/Entities/EntityPlayerBot.cs`.
- Slot changes propagate through `ItemSlot.MarkDirty()` → `InventoryBase.DidModifyItemSlot(...)` → `InventoryBase.MarkSlotDirty(slotId)`.
  - `InventoryBase.MarkSlotDirty` explicitly states: server resends the slot to clients; client refreshes stack size/model when rendered.
  - Sources: `vsapi/Common/Inventory/ItemSlot.cs`, `vsapi/Common/Inventory/InventoryBase.cs`.
- PlayerBot equip/unequip explicitly **marks slot dirty** and **stores inventory to WatchedAttributes**:
  - `targetslot.MarkDirty(); vas.Entity.GetBehavior<EntityBehaviorContainer>().storeInv();`
  - Sources: `vssurvivalmod/Systems/EntityActivitySystem/Action/EquipAction.cs`, `vssurvivalmod/Systems/EntityActivitySystem/Action/UnequipAction.cs`.
- `EntityBehaviorContainer.storeInv()` writes the inventory tree and marks the path dirty:
  - `container.ToTreeAttributes(entity.WatchedAttributes);`
  - `entity.WatchedAttributes.MarkPathDirty(InventoryClassName);`
  - Source: `vsessentialsmod/Entity/Behavior/BehaviorContainer.cs`, `vsessentialsmod/Inventory/InWorldContainer.cs`.
- `EntityBehaviorSeraphInventory` registers a modified listener for `"wearablesInv"` even though its `InventoryClassName` is `"seraphinventory"`:
  - `eagent.WatchedAttributes.RegisterModifiedListener("wearablesInv", wearablesModified);`
  - Base `EntityBehaviorContainer.Initialize(...)` also registers a listener for `InventoryClassName` (so `"seraphinventory"` still gets handled).
  - Sources: `vssurvivalmod/Entities/EntityPlayerBot.cs`, `vsessentialsmod/Entity/Behavior/BehaviorContainer.cs`.

## Findings
### Where the visual refresh happens (method + file)
- Rendering uses **live hand slots each frame**:
  - `EntityShapeRenderer.RenderHeldItem(...)` in `vsessentialsmod/EntityRenderer/EntityShapeRenderer.cs`.
  - `EntityPlayerShapeRenderer.RenderHeldItem(...)` (override) in `vsessentialsmod/EntityRenderer/EntityPlayerShapeRenderer.cs`.
- The **data refresh trigger** for rendered stacks is **inventory dirtying**:
  - `InventoryBase.MarkSlotDirty(int slotId)` in `vsapi/Common/Inventory/InventoryBase.cs` (comment states client refreshes stack size/model when rendered).
- For **PlayerBot**, hand slot data comes from `EntityBehaviorSeraphInventory`’s `InventoryGear` (slots 15/16), and persistence/sync is handled via `EntityBehaviorContainer.storeInv()` writing `seraphinventory` to `WatchedAttributes` (see `EntityPlayerBot.cs`, `BehaviorContainer.cs`).

### What must be called after slot change to update held item visuals
- For **PlayerBot/SeraphInventory**, follow the pattern used by `EquipAction`/`UnequipAction`:
  - **`targetslot.MarkDirty()`** to mark the slot dirty and update transition states.
  - **`vas.Entity.GetBehavior<EntityBehaviorContainer>().storeInv()`** to write the inventory into `WatchedAttributes` and `MarkPathDirty("seraphinventory")` for client sync.
- For **EntityPlayer** (real player), ensure the slot you updated is the **active hotbar slot** (`EntityPlayer.RightHandItemSlot` uses `InventoryManager.ActiveHotbarSlot`). Otherwise the render path won’t point at the changed slot.

### Is `ItemSlot.MarkDirty` alone enough?
- **For PlayerBot (SeraphInventory): likely no.** The canonical pattern in `EquipAction`/`UnequipAction` uses **both** `MarkDirty()` and `storeInv()`. That implies `MarkDirty()` alone does not ensure the `seraphinventory` tree is synced to clients.
- **For real players:** `MarkDirty()` is usually sufficient for slot content changes as long as the **active hotbar slot** is the one being rendered.

## Gaps / Follow-ups
- `wearablesInv` is only referenced by `EntityBehaviorAttachable` (inventory class `"wearablesInv"`) and the extra listener in `EntityBehaviorSeraphInventory`. There are no other `wearablesInv` writes in `vssurvivalmod`, so the extra listener on PlayerBot appears redundant/legacy.
