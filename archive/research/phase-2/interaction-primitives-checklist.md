# Interaction Primitives Checklist (Phase 2 Prep)

This checklist enumerates the interaction primitives needed for robust bot world interaction. Each primitive includes the minimal API entrypoints to implement vanilla-like behavior.

## 1) Selection + Validation Layer

### 1.1 Target selection (block/entity)
- **API:** `IWorldAccessor.RayTraceForSelection(...)`
- **API:** `BlockSelection`, `EntitySelection`, `EntitySelection.HitPosition`
- **Status:** partial (research complete; implementation pending)
- **Notes (vsapi):**
  - `BlockSelection.HitPosition` is **block-local** (relative to `BlockSelection.Position`, 0..1)
  - `EntitySelection.HitPosition` is **entity-relative**; see `docs/research/phase-2/2026-01-13-hitposition-coordinate-space-resolution.md`.
  - `BlockSelection.Face` is "the face the player aimed at"

### 1.2 Range + LOS checks
- **API:** `RayTraceForSelection(..., float range, ...)`
- **Status:** partial (research complete; implementation pending)
- **Notes:** LOS can be enforced by ray trace; range should clamp ray length

### 1.3 Claims/permissions checks
- **API:** `ILandClaimAPI.TestAccess` / `TryAccess`
- **API:** `EnumBlockAccessFlags` (Use, BuildOrBreak, Traverse)
- **Status:** partial (research complete; implementation pending)
- **Notes (vsapi):**
  - `TestAccess(...)` checks permissions; returns true client-side regardless.
  - `TryAccess(...)` also sends error + marks block dirty (server-side).
  - `EnumBlockAccessFlags`: `BuildOrBreak`, `Use`, `Traverse`.
- **Notes (vssurvivalmod patterns):**
  - `BuildOrBreak` used for placement/breaking (e.g., `ItemWrench`, `BlockLayered`, `ItemChisel`).
  - `Use` used for container interaction (e.g., `BEOpenableContainer`), block use (e.g., `BlockTorch`, `BlockQuern`).
  - See `docs/research/misc/2026-01-13-claims-enforcement-patterns.md` for examples.

### 1.4 Action result/telemetry
- **API:** (mod-local) `ActionResult` / `EnumFailureReason` (proposed)
- **Status:** todo

### 1.5 HitPosition semantics (resolved)
- **Status:** resolved (entity-relative)
- **Rule:** `EntitySelection.HitPosition` is **relative to the entity hitbox**. Use ray-traced results directly; manual world-space hits must subtract `entity.ServerPos.XYZ`.
- **Reference:** `docs/research/phase-2/HITPOSITION-RESOLUTION-SUMMARY.md` (evidence + examples).

## 2) Core Action Entry Points

### 2.1 Use block (right-click block)
- **API:** `Block.OnBlockInteractStart`
- **API:** `BlockSelection.HitPosition`
- **Status:** partial (activate/break/place exist; use pipeline not unified)
- **Notes:** `Block.Activate(...)` expects a valid `BlockSelection` (face + local hit position)

### 2.2 Use entity (right-click entity)
- **API:** `Entity.OnInteract(..., EnumInteractMode.Interact)`
- **API:** `EntitySelection.HitPosition`
- **Status:** implemented (interact works; attack currently fails on playerbot)
- **Notes:** action uses ray trace hit position and moves into range before interact
- **Resolution note:** `EntitySelection.HitPosition` is **entity-relative** per vsapi docs; `NormalizeHitPos` is correct as a defensive fallback.
- **Reference:** `docs/research/phase-2/2026-01-13-hitposition-coordinate-space-resolution.md`.
- **Observed behavior (2026-01-06):**
  - `/polis interact` on a trader works (nodding interaction loop visible).
  - `/polis interact` on a seat does not work.
  - `/polis interact attack` throws NRE in `EntityAgent.OnInteract` when the actor is not `EntityPlayer`, and can suspend server ticks.

### 2.3 Break block (with tool)
- **API:** `CollectibleObject.OnBlockBrokenWith`
- **API:** `IBlockAccessor.BreakBlock`
- **Status:** partial (break command exists, tool pipeline not unified)

### 2.4 Place block (with item)
- **API:** `Block.TryPlaceBlock` + `BlockBehavior.TryPlaceBlock` chain
- **Status:** partial (place exists, not using full held-use pipeline)
- **Notes:** `TryPlaceBlock(...)` is the canonical placement entrypoint; relies on correct `BlockSelection` (pos/face/hit)

## 3) Tool Use Pipeline

### 3.1 Held-use start/step/stop
- **API:** `CollectibleObject.OnHeldUseStart`
- **API:** `CollectibleObject.OnHeldUseStep`
- **API:** `CollectibleObject.OnHeldUseStop`
- **Status:** partial (research complete; implementation pending)
- **Notes (vsapi):**
  - `Collectible.OnHeldUseStart(...)` routes to `OnHeldAttackStart` or `OnHeldInteractStart` based on `EnumHandInteract`.
  - `OnHeldUseStep(...)` / `OnHeldUseStop(...)` route to `OnHeldAttack*` or `OnHeldInteract*`.
  - `OnHeldInteractStart` receives `firstEvent` (true on initial mouse down, false on subsequent calls).
  - `EnumHandHandling` controls default animations/actions and whether server should call step/stop.

### 3.2 Attack vs interact routing
- **API:** `EnumHandInteract` (`HeldItemAttack`, `HeldItemInteract`, `BlockInteract`)
- **Status:** partial (research complete; implementation pending)
- **Notes (vsapi):**
  - `EnumHandInteract` values: `None`, `HeldItemAttack`, `HeldItemInteract`, `BlockInteract`.
  - `EnumHandHandling` values govern default behavior vs custom handling (`NotHandled`, `Handled`, `PreventDefault*`).

## 4) Inventory + Items

### 4.1 Equip tool (hand slots)
- **API:** `EntityAgent.RightHandItemSlot` / `LeftHandItemSlot`
- **API:** `ItemSlot.MarkDirty` + `EntityBehaviorSeraphInventory.storeInv()`
- **Status:** partial (equip command exists)

### 4.2 Pickup item entity
- **API:** `EntityItem.CanCollect` / `OnCollected`
- **API:** `ItemSlot.TryPutInto(...)`
- **API:** `EntityBehaviorSeraphInventory.storeInv()`
- **Status:** implemented (untested)
- **Implementation:** `PolisPickupItemAction.cs`, `/polis pickup [entityid] [range]`
- **Notes (vsapi):**
  - `EntityItem.CanCollect` returns true only after ~1s since spawn.
  - `EntityItem.OnCollected` returns the `Slot.Itemstack`.
  - `Entity.OnCollected` comment: called by `BehaviorCollectEntities`; if fully picked up, collector kills the entity.
  - Pickup flow should mirror: `CanCollect` → inventory transfer → despawn entity when stack is fully transferred.
- **Implementation notes:**
  - Uses explicit slot insertion (hands → backpack/bag contents) via `PolisInventoryHelpers.TryInsertIntoBotInventory`.
  - Calls `storeInv()` to persist/sync bot inventory after insertion.
  - Despawns with `Die(EnumDespawnReason.PickedUp)` on full transfer.
  - Command finds nearest `EntityItem` if no id provided.

### 4.3 Drop item entity
- **API:** `IWorldAccessor.SpawnItemEntity`
- **Status:** implemented (untested)
- **Implementation:** `PolisDropItemAction.cs`, `/polis drop [slot] [qty]`
- **Notes:** drop uses `SpawnItemEntity(itemstack, position, velocity?)`.
- **Implementation notes:**
  - Supports hand slots only (0=right, 1=left, -1=auto).
  - Persists inventory via `EntityBehaviorSeraphInventory.storeInv()`.
  - Backpack slot access deferred (requires bag content routing).

### 4.4 Container transfer (bot ↔ container)
- **API:** `IBlockEntityContainer.Inventory`
- **API:** `ItemSlot.TryPutInto` / `TakeOut`
- **API:** `ItemSlot.MarkDirty` + `BlockEntity.MarkDirty`
- **Status:** partial (research complete; implementation pending)
- **Notes (vsapi):**
  - `ItemSlot.TryPutInto(...)` handles merge/stacking and calls `OnItemSlotModified`.
  - `ItemSlot.MarkDirty()` queues inventory sync; calls `Inventory.DidModifyItemSlot(...)`.
  - `InventoryBase.MarkSlotDirty(...)` triggers slot sync to clients.
  - `BlockEntity.MarkDirty(redrawOnClient)` resyncs block entity tree attrs and optionally redraws the block.
- **Notes (vssurvivalmod):**
  - `BEGroundStorage.TryPutItem` uses `hotbarSlot.TryPutInto(Api.World, invSlot, qty)` and then `MarkDirty()` on the block entity.
- **Reference:** `docs/research/phase-2/2026-01-14-container-transfer-correctness.md` (canonical call order + dirtying).

## 5) Workstations (No-GUI First)

### 5.1 Quern (grind loop)
- **API:** `BlockQuern.OnBlockInteractStart/Step/Stop`
- **API:** `BlockEntityQuern.SetPlayerGrinding`
- **Status:** todo

### 5.2 Pit kiln (ignite + wait)
- **API:** `BlockPitkiln.OnBlockInteractStart` + BE ignition path
- **Status:** todo

### 5.3 Mechanical power variant (optional)
- **API:** `BEBehaviorMPConsumer` (quern automation)
- **Status:** deferred

## 6) Workstations (GUI-driven, deferred)

### 6.1 Anvil (smithing)
- **API:** `BlockEntityAnvil` server packet handlers
- **Status:** deferred

### 6.2 Clayforming
- **API:** `BlockEntityClayForm` server packet handlers
- **Status:** deferred

## 7) NPC Visual/Sync

### 7.1 Inventory sync
- **API:** `ItemSlot.MarkDirty` / `IInventory.MarkSlotDirty`
- **Status:** research complete; implementation pending
- **Notes:** `storeInv()` is required to persist/sync `seraphinventory`. See `docs/research/phase-2/2026-01-14-bot-inventory-sync-flow.md`.

### 7.2 NPC held-item visuals
- **API:** `Entity.WatchedAttributes.MarkPathDirty`
- **Status:** research complete; implementation pending
- **Notes:** update hands + `storeInv()` for PlayerBot visuals. See `docs/research/phase-2/2026-01-13-held-item-visual-sync-playerbot.md`.

### 7.3 Player-like entity option
- **API:** `EntityPlayerBot` (vssurvivalmod pattern)
- **Status:** research only

## 8) Commands/Hotkeys Coverage

### 8.1 Existing `/polis` coverage
- **Status:** partial (spawn/select/goto/activate/break/place/equip)

### 8.2 Missing commands
- **Candidates:** interact entity, pickup/drop, container transfer, use tool
- **Status:** todo

---

## Implementation Notes (Current Mod)

### Implemented primitives
- Block activate/break/place use `BlockSelection` constructed in `PolisBuilderNpcSystem.cs` actions
- Entity interact action exists in `PolisInteractEntityAction.cs` (ray hitpos normalized to relative when needed)
- Bot give uses `PolisInventoryHelpers.TryInsertIntoBotInventory` (`CmdGive`) for explicit slot insertion

### Known mismatches vs vsapi semantics
- `PolisInteractEntityAction` currently normalizes the hit position to **relative** if the ray hit point is close to the entity position (heuristic to handle world-space hits); confirm against vanilla before locking this down

---

## Proposed Implementation: Selection + Validation Layer (Todo 1.1 / 1.2 / 1.3)

### Server helper (single ray source of truth)
```
bool TryRaySelect(
    IWorldAccessor world,
    Vec3d fromPos, float pitch, float yaw, float range,
    out BlockSelection blockSel, out EntitySelection entSel,
    BlockFilter bfilter = null, EntityFilter efilter = null
)
```
- Use `RayTraceForSelection(fromPos, pitch, yaw, range, ref blockSel, ref entSel, ...)`
- Choose block or entity target based on action type

### Validation steps
1) **Range**: check distance to target center or `HitPosition`
2) **LOS**: implicit from ray trace (optionally revalidate)
3) **Claims**: `ILandClaimAPI.TestAccess` / `TryAccess` before action

### Action wiring guidance
- Block actions: pass `BlockSelection` as-is (local `HitPosition`)
- Entity actions: pass `EntitySelection.HitPosition` (world-space)
