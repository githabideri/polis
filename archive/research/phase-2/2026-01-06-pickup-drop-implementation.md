# Pickup/Drop Implementation Plan (Phase 2)

**Date:** 2026-01-06
**Status:** Implemented (untested) - 2026-01-12

## Purpose
Define the server-side pickup/drop flow for bots, aligned with VS engine semantics and current Polis primitives.

## Known Engine Semantics (vsapi)

**Pickup (EntityItem):**
- `EntityItem.CanCollect(Entity byEntity)` returns true only after ~1s since spawn.
- `EntityItem.OnCollected(Entity byEntity)` returns the `Slot.Itemstack`.
- `Entity.OnCollected(Entity byEntity)` is called by `BehaviorCollectEntities`; if fully collected, the collector kills the entity.
- `Entity.TryGiveItemStack(ItemStack itemstack)` is the standard way to hand items to an entity.
  - For `EntityPlayerBot`, prefer explicit slot insertion (hands/backpacks) + `storeInv()` for sync.

**Drop:**
- Use `IWorldAccessor.SpawnItemEntity(itemstack, position, velocity?)`.

## Current Polis Alignment
- Pickup/give use `PolisInventoryHelpers.TryInsertIntoBotInventory` (hands → backpack/bag contents) rather than `TryGiveItemStack`.

## Additional Patterns (vssurvivalmod)

- **Projectiles (`EntityProjectile`)**: `CanCollect` requires:
  - `Alive`
  - >1s since launch
  - `ServerPos.Motion.Length() < 0.01`
  - (and not `NonCollectible`)
  This suggests item entities should generally be stationary before pickup.
- **Block right-click pickup (`BlockBehaviorRightClickPickup`)**:
  - Uses claims check: `world.Claims.TryAccess(... BuildOrBreak)`
  - Gives items via `InventoryManager.TryGiveItemstack(...)`
  - If inventory full, falls back to `world.SpawnItemEntity(...)`
  - Logs an audit event and pushes `"onitemcollected"`

## Open Questions (Need Verification)
1) **BehaviorCollectEntities source**: not found in vssurvivalmod; likely engine (VintagestoryLib).  
   - **To decompile:** `Vintagestory.Server.ServerSystemEntitySimulation` and any `BehaviorCollect*` types in `VintagestoryLib.dll` to confirm pickup flow and partial stack handling.
   - **Decompile status (2026-01-06):** searched `VintagestoryLib.dll`, `VintagestoryServer.dll`, and `Vintagestory.dll` without finding `BehaviorCollect*`, `CanCollect(`, or `OnCollected(` call sites. Likely obfuscated, embedded under a different name, or in another assembly.
2) **Coordinate/ownership rules**: is there any ownership or pickup filtering beyond `CanCollect`?
3) **Partial pickup**: how does the engine split stacks when inventory is partially full?
4) **Networking**: any packets required for server-side pickup (for bots) or is server-only authoritative enough?
5) **Selection**: do we need a raycast/LOS check or just proximity for item pickup?

## Additional Findings (2026-01-06)
- `EntityItem.ByPlayerUid` exists (stored in `WatchedAttributes`) but no pickup gating was found in decompiled engine code. Ownership-based restrictions remain unverified.
- `ItemCollectMode` appears in runtime settings and UI config, but no pickup logic references were found in the decompiled assemblies searched.
- No `onitemcollected` event usage was found in engine decompile; only vssurvivalmod uses it for block pickup.
- `PlayerInventoryManager.TryGiveItemstack(...)` (engine decompile) uses a `DummySlot` and `TryTransferAway(...)`:
  - Partial transfers reduce the source `ItemStack` size.
  - If nothing moves, returns false.
  - If fully transferred, the source `ItemStack` can end at size 0.
  - This supports partial pickup by inspecting the remaining stack size after transfer.

## Field Observations (2026-01-13)
- **Drop height:** item entities can spawn above ground (y ≈ 6) even when dropping at y ≈ 3.
  - Immediate pickup often returns `CanCollect returned false` until the item falls/settles.
- **Range gate:** pickup returns `out of range dist=4.66 range=3.00` when bot is >3 blocks away.
- **Slot availability:** with both hands occupied and no backpack, pickup returns `inventory full or no valid slots`.
- **Auto-pick:** dropping at the bot’s feet can auto-collect immediately if a hand slot is free.
  - Move the bot 1-2 blocks away right after drop to preserve the item on the ground.

## Proposed Bot Pickup Flow (Server)
1) Find target `EntityItem` (nearest, within range, optional whitelist).
2) Validate:
   - target is alive
   - `EntityItem.CanCollect(botEntity)` is true
   - optionally require low motion (projectile pattern)
   - range check (distance to selection box or item center)
3) Get stack:
   - `ItemStack stack = target.OnCollected(botEntity)`
4) Try insert:
   - `bool ok = PolisInventoryHelpers.TryInsertIntoBotInventory(botEntity, stack, out moved, ...)`
5) Resolve result:
   - If fully transferred: despawn item entity.
   - If partial transfer: update item entity stack (remaining) and keep it alive.
   - If `ok` is false: abort (inventory full).

## Implementation Implications
- Slot insertion uses `ItemSlot.TryPutInto(...)`; track moved quantity to compute remaining stack.
- Only despawn the `EntityItem` if the remaining stack is zero.
- If partial, keep the entity alive and sync its stack.

## Assumption (until engine collector is found)
- Bot pickup should be safe to implement using the public contract:
  - `EntityItem.CanCollect(...)` gate
  - `EntityItem.OnCollected(...)` to obtain stack
  - `PolisInventoryHelpers.TryInsertIntoBotInventory(...)` to transfer into inventory
  - Despawn item entity when fully transferred
- This mirrors the documented intent in `Entity.OnCollected` and should align with engine behavior even if the collector logic is opaque.

## Proposed Bot Drop Flow (Server)
1) Identify stack to drop (from bot inventory slot or hand).
2) Remove from inventory (reduce stack or clear slot).
3) Call `IWorldAccessor.SpawnItemEntity(stack, dropPos, velocity?)`.

## Implementation Steps (Polis)
1) Add `/polis pickup` command:
   - target by entity id, or nearest `EntityItem` in range.
   - create an action sequence: `PolisGotoAction` → `PolisPickupItemAction`.
2) Add `PolisPickupItemAction` (EntityActionBase):
   - performs validation and calls `CanCollect` / `OnCollected` / `PolisInventoryHelpers.TryInsertIntoBotInventory`.
   - handles partial stacks and entity despawn.
3) Add `/polis drop` command:
   - target slot or active hand.
   - spawns item entity at bot position.
4) Add tests/logging:
   - debug messages for pickup failures (range, CanCollect false, inventory full).
   - confirm item entity despawns on full pickup.

## References
- `docs/research/phase-2/interaction-primitives-checklist.md`
- `vsapi/Common/Entity/EntityItem.cs`
- `vsapi/Common/Entity/Entity.cs`
