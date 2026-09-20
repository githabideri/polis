# World Interaction Primitives (Phase 2 Prep)

Goal: expand what bots can do in the world before a full job/task system. These notes summarize deep-research findings across VS API + vanilla mod patterns.

## 1) Item entities: pickup and drop

### Pickup pipeline (vanilla pattern)
- Item entities are `EntityItem` (vsapi).
- Collection is **collector-driven**, not item-driven:
  - Collector scans nearby entities and calls:
    - `EntityItem.CanCollect(Entity byEntity)`
    - `EntityItem.OnCollected(Entity byEntity)` → returns `ItemStack`
- Vanilla collector behavior is in `vsessentialsmod/Entity/Behavior/BehaviorCollectEntities.cs` (search this file for the scan/collect loop).

### btca confirmation (vsapi)
- `EntityItem.CanCollect(...)` returns `Alive && World.ElapsedMilliseconds - itemSpawnedMilliseconds > 1000` (1s pickup delay).
- `EntityItem.OnCollected(...)` returns `Slot.Itemstack` (no inventory insertion).
- Collector must call its own `TryGiveItemStack(ItemStack)` to accept the stack.
- `EntityAgent.TryGiveItemStack` dispatches to behaviors via `EntityBehavior.TryGiveItemStack(...)`.
- `EntityPlayer.TryGiveItemStack` routes to `player.InventoryManager.TryGiveItemstack(...)`.

### Inventory acceptance is behavior-driven
- The collector hands the stack to the collecting entity via the **behavior chain**.
- Hook: `EntityBehavior.TryGiveItemStack(ItemStack, ref EnumHandling)`.
- If the bot has no behavior that handles this, pickup fails (stack not accepted).

### Drop into world
- Canonical spawn: `IWorldAccessor.SpawnItemEntity(ItemStack, Vec3d|BlockPos, Vec3d velocity=null)`.
- Alternate: `EntityItem.FromItemstack(...)` then `world.SpawnEntity(entity)` for more control.
- If `stack.StackSize == 0`, spawn can immediately despawn (per API docs).

### Bot implications
- Implement a **collector behavior** (or manual one-shot pickup) plus a bot inventory behavior handling `TryGiveItemStack`.
- Use the same `OnCollected` flow so `EntityItem` applies vanilla rules (ownership, age, etc.).

### Collector behavior details (vsessentialsmod)
- File: `vsessentialsmod/Entity/Behavior/BehaviorCollectEntities.cs`
- Registration: `vsessentialsmod/Core.cs` registers behavior `"collectitems"` → `EntityBehaviorCollectEntities`.
- Scan loop:
  - `OnGameTick(...)` throttles to `ItemsPerSecond` (23).
  - Uses `entity.World.GetEntitiesAround(tmp, 1.5f, 1.5f, entityMatcher)`.
- Collector-side gates:
  - Skips if entity not active/alive.
  - Skips when `ItemCollectMode == 1` **unless** sneaking (`Controls.Sneak == true`).
  - Skips if `entity.IsActivityRunning("invulnerable")` (wait ticks).
  - Skips in spectator mode.
- Pickup order:
  1) `foundEntity.OnCollected(entity)` first.
  2) `entity.TryGiveItemStack(itemstack)` if stack size > 0.
  3) If `itemstack.StackSize <= 0`, `foundEntity.Die(EnumDespawnReason.PickedUp)`.
  4) If collected: `itemstack.Collectible.OnCollected(itemstack, entity)` + `onitemcollected` event + sound.

## 2) Container inventories (chests, barrels, crates)

### Accessing inventories
- Container block entities expose `IBlockEntityContainer.Inventory`.
- Work with `IInventory` and its `ItemSlot`s (`inventory[slotId]`).

### Core transfer primitives (no GUI)
- Move/merge:
  - `ItemSlot.TryPutInto(IWorldAccessor world, ItemSlot sinkSlot, int quantity=1)`
  - `ItemSlot.TryPutInto(ItemSlot sinkSlot, ref ItemStackMoveOperation op)` for full semantics
- Remove:
  - `ItemSlot.TakeOut(int qty)` / `ItemSlot.TakeOutWhole()`
- Sync:
  - `ItemSlot.MarkDirty()` for save + client resend
- Slot selection helper:
  - `IInventory.GetBestSuitedSlot(...)` does *not* check permissions.

### Access checks to mirror
- Land claims: `api.World.Claims.TestAccess(IPlayer, BlockPos, EnumBlockAccessFlags.Use|BuildOrBreak|Traverse)`
- Inventory gates:
  - `InventoryBase.CanPlayerAccess/CanPlayerModify`
  - `PutLocked` / `TakeLocked`
- Locks/reinforcement are separate (Lockable behavior / reinforced blocks). You’ll need to decide whether to check these in bot logic.

### btca confirmation (vsapi)
- `IBlockEntityContainer.Inventory` exposes the container inventory.
- `ItemSlot.MarkDirty()` queues slot for save and client resend.
- `IInventory` exposes slot indexer, `GetBestSuitedSlot(...)`, `ActivateSlot(...)`, and `DirtySlots`.

### Bot transfer recipe (vanilla-like)
1) Resolve `IBlockEntityContainer` → `IInventory`.
2) Test access (`Use` for containers).
3) Check `CanPlayerModify` + `PutLocked/TakeLocked`.
4) Use `TryPutInto` / `TakeOut`.
5) Mark dirty slots.

## 3) Workstations: quern, pit kiln, anvil, clayforming

### Quern
- Files: `vssurvivalmod/BlockEntity/BEQuern.cs`, `Block/BlockQuern.cs`.
- No-GUI; driven by block interaction and BE tick/progress.
- Likely bot path: call the same block interaction entrypoints (right-click/held-interact) and let BE tick handle progress.

### btca confirmation (vssurvivalmod)
- `BlockQuern.OnBlockInteractStart/Step/Stop/Cancel` are the main entrypoints.
- Flow:
  - Start: checks claims, gets `BlockEntityQuern`, validates `CanGrind()` and selection, calls `beQuern.SetPlayerGrinding(byPlayer, true)`.
  - Step: calls `beQuern.IsGrinding(byPlayer)` and returns `beQuern.CanGrind()` to continue.
  - Stop/Cancel: calls `beQuern.SetPlayerGrinding(byPlayer, false)`.

### BEQuern server-side work (vssurvivalmod)
- Tick driver: `Every100ms` (via `RegisterGameTickListener`).
- Progress + output:
  - `inputGrindTime` accumulates while `GrindSpeed > 0`.
  - On completion, `grindInput()` consumes input and produces output.
- Player grinding is tracked via `playersGrinding`; `SetPlayerGrinding` and `IsGrinding` keep it alive.
- Mechanical power path: `BEBehaviorMPConsumer` sets `automated = true` and drives `GrindSpeed` without manual interaction.

### Pit kiln
- Files: `vssurvivalmod/BlockEntity/BEPitKiln.cs`, `Block/BlockPitkiln.cs`.
- Interaction (ignite/add fuel/cover) is block-driven; firing is BE state machine + tick.
- Bot path: use block interactions to reach “lit” state, then BE ticks.

### Pit kiln search targets (local source audit)
- Look for: `Ignite`/`TryIgnite`, `RegisterGameTickListener`/`OnGameTick`, `burn`/`firing`/`Finish`.

### Anvil
- Files: `vssurvivalmod/BlockEntity/BEAnvil.cs`, `Block/BlockAnvil.cs`.
- GUI-driven smithing (voxel edits + tool hits).
- Bot path options:
  1) emulate GUI packet flow, or
  2) implement a validated server-side shortcut that matches vanilla completion rules.

### Clayforming
- Files: `vssurvivalmod/BlockEntity/BEClayForm.cs`.
- GUI-driven voxel edits like anvil.
- Same options as anvil; likely requires server-side shortcut for bots.

## 4) Right-click block pipeline (vanilla ordering + sync rules)

### Client-side driver (closed-source, but seen in stacks)
- `SystemMouseInWorldInteractions.HandleMouseInteractionsBlockSelected(...)`
- Chooses between:
  - `TryBeginUseActiveSlotItem(...)` → held item path
  - `TryBeginUseBlock(...)` → block path
- `BlockSelection.HitPosition` is documented as **relative to block position** (0..1 within the block).

### Raytrace entrypoints (vsapi)
- `IWorldAccessor.RayTraceForSelection(...)` overloads:
  - `RayTraceForSelection(Vec3d fromPos, Vec3d toPos, ref BlockSelection, ref EntitySelection, ...)`
  - `RayTraceForSelection(IWorldIntersectionSupplier supplier, Vec3d fromPos, Vec3d toPos, ref BlockSelection, ref EntitySelection, ...)`
  - `RayTraceForSelection(Vec3d fromPos, float pitch, float yaw, float range, ref BlockSelection, ref EntitySelection, ...)`
  - `RayTraceForSelection(Ray ray, ref BlockSelection, ref EntitySelection, ...)`

### Held-item path (vsapi)
- `CollectibleObject.OnHeldUseStart(...)` is the general entrypoint; it dispatches by `EnumHandInteract`:
  - `HeldItemAttack`
  - `HeldItemInteract`
  - `BlockInteract`
- For right-click item use, `OnHeldUseStart(... HeldItemInteract ...)` → `OnHeldInteractStart(...)`.
- `EnumHandHandling` determines whether the interaction is sent to the server:
  - `NotHandled` → no server call, no Step/Stop.
  - Handled/PreventDefault* → server call + Step/Stop.
  - Doc on `OnHeldUseStart`: if `handling` is `NotHandled`, the action is not called on the server.

### Decompile notes (VintagestoryLib)
- `SystemMouseInWorldInteractions.TryBeginUseActiveSlotItem(...)`:
  - Calls `Collectible.OnHeldUseStart(...)`.
  - If `handling != NotHandled`, sets `controls.HandUse`, resets using timers, and sends `SendHandInteraction(... StartHeldItemUse ...)`.
  - If stack becomes empty, clears slot and `MarkDirty()`.

### Block path (vsapi)
- `Block.OnBlockInteractStart(...)` return value controls sync:
  - `false` → not synced to server (client-only).
  - `true` → server call.
  - Doc: returning `false` stops the interaction and prevents server sync.

### Decompile notes (VintagestoryLib)
- `SystemMouseInWorldInteractions.TryBeginUseBlock(...)`:
  - Calls `game.tryAccess(... Use)` before interact.
  - If `OnBlockInteractStart` returns true, sets `controls.HandUse = BlockInteract`, stores `HandUsingBlockSel`, and sends `SendHandInteraction(... StartBlockUse ...)`.

### Priority resolution (sneak)
- `HeldPriorityInteract` (item) vs `PlacedPriorityInteract` (block).
- Practical rule:
  1) If block has `PlacedPriorityInteract == true`, block-first
  2) Unless held item has `HeldPriorityInteract == true`, which overrides to item-first

### Server-side continuation
- Server drives the use lifecycle via `ServerSystemInventory.OnUsingTick(...)` → `CollectibleObject.OnHeldUseStop(...)`.
- Bot interactions that only call `OnHeldInteractStart` skip this lifecycle unless emulated.
### Decompile notes (VintagestoryLib)
- `ServerSystemInventory.OnUsingTick(...)`:
  - Calls `Collectible.OnHeldUseStep(...)` while `controls.HandUse != None`.
  - On stop, calls `Collectible.OnHeldUseStop(...)`.

## 5) Tool-driven interactions (items vs blocks)

### Where logic lives
- **Held item side**: `CollectibleObject` / `Item` / `CollectibleBehavior`.
  - Entry: `OnHeldInteractStart/Step/Stop(...)`
  - Use `EnumHandHandling` / `EnumHandling` to prevent default and stop other handlers.
- **Block side**: `Block` / `BlockBehavior` / `BlockEntity` via `OnBlockInteractStart/Step/Stop`.

### Interaction priority
- Engine picks **item vs block** based on `HeldPriorityInteract` / `PlacedPriorityInteract`.
- Handling flags determine whether server-side execution continues.

### Why `Block.Activate(...)` is not enough
- Hoe tilling is on `ItemHoe.OnHeldInteractStart`, not the block.
- Knife harvesting uses `ItemKnife.OnHeldInteract...` + `EntityBehaviorHarvestable`.
- Tool-based special drops often route through `CollectibleObject.OnBlockBrokenWith(...)`.

### Bot entrypoints to mirror
1) Use tool on block: call `OnHeldUseStart(... Interact ...)` → `OnHeldInteractStart(...)`, respect handling, then call block interaction if not handled.
2) Use tool on entity: same held-interact flow with `EntitySelection`.
3) Break with tool: include `OnBlockBrokenWith(...)` in the break pipeline.

### btca confirmation (vsapi)
- `CollectibleObject.OnHeldInteractStart(...)` signature:
  - `OnHeldInteractStart(ItemSlot slot, EntityAgent byEntity, BlockSelection blockSel, EntitySelection entitySel, bool firstEvent, ref EnumHandHandling handling)`
  - Doc: called when player right-clicks with item; `firstEvent` true on initial press; `handling` controls subsequent actions and whether the server call happens.
- `CollectibleObject.OnHeldInteractStep(...)` signature:
  - `OnHeldInteractStep(float secondsUsed, ItemSlot slot, EntityAgent byEntity, BlockSelection blockSel, EntitySelection entitySel)`
  - Doc: called every frame while using; return false to stop.
- `CollectibleObject.OnHeldInteractStop(...)` signature:
  - `OnHeldInteractStop(float secondsUsed, ItemSlot slot, EntityAgent byEntity, BlockSelection blockSel, EntitySelection entitySel)`
  - Doc: called once when interaction completes.
- `CollectibleObject.OnBlockBrokenWith(...)` signature:
  - `OnBlockBrokenWith(IWorldAccessor world, Entity byEntity, ItemSlot itemslot, BlockSelection blockSel, float dropQuantityMultiplier = 1)`
  - Doc: return false to cancel the block break.

## 6) Block placement flow (vanilla)

### Held-use placement entrypoints
- Placement runs through the held-item path (`OnHeldUseStart` → `OnHeldInteractStart`).
- The block itself is the collectible (`Block : CollectibleObject`) for most placements.

### Placement core (vsapi)
- `Block.TryPlaceBlock(...)` → `CanPlaceBlock(...)` → `DoPlaceBlock(...)`.
- `BlockBehavior.TryPlaceBlock(...)` → `CanPlaceBlock(...)` → `DoPlaceBlock(...)` → `OnBlockPlaced(...)` sequence.

### Handling + sync rules
- `EnumHandHandling` determines whether placement is sent to server.
- Claim checks are server-side; client `TestAccess` always returns true.

### Bot implication
- To mimic vanilla, drive placement via `TryPlaceBlock` (not direct `SetBlock`).
- If you skip the held-use path, you must still apply claims + block behavior pipeline.

### Decompile notes (VintagestoryLib)
- `ServerSystemBlockSimulation.TryModifyBlockInWorld(...)` placement:
  - Range check: uses `PickingRange + 0.7` unless privilege `pickingrange`.
  - Validates active hotbar slot + `EnumItemClass.Block`.
  - Rejects non-replaceable blocks unless `ignoreServerReplaceableTest` or decor.
  - Rejects if another player intersects the placement.
  - Calls `Block.TryPlaceBlock(...)` and decrements stack (non-creative).

## 7) Block breaking flow (vanilla)

### Server flow (authoritative)
- `ServerSystemBlockSimulation.HandleBlockPlaceOrBreak(...)` → `TryModifyBlockInWorld(...)` (closed-source, seen in stacks).
- Claims + permission gates are checked here; use `ILandClaimAPI.TryAccess/TestAccess`.

### Tool callback + break path
- `CollectibleObject.OnBlockBrokenWith(...)` is called if held item exists.
  - Return `false` to cancel the break.
- Default continuation:
  - `Block.OnBlockBroken(...)`
  - `Block.GetDrops(...)`
  - `IBlockAccessor.BreakBlock(...)` performs removal + drops + neighbor updates

### Drop multiplier
- `dropQuantityMultiplier` is passed through all break callbacks and applied in `BlockDropItemStack`.

### Bot implication
- Use `OnBlockBrokenWith(...)` + `BreakBlock(...)` to preserve vanilla drops and BE lifecycle.

### Decompile notes (VintagestoryLib)
- `HandleBlockPlaceOrBreak(...)`:
  - Enforces `TestBlockAccess(... BuildOrBreak)` before placement/break.
  - Reverts client state on failure.
- `TryModifyBlockInWorld(...)` break:
  - Checks tool tier vs `RequiredMiningTier`.
  - Calls `EventManager.TriggerBreakBlock(...)` (can alter `dropQuantityMultiplier`).
  - Calls `OnBlockBrokenWith(...)` for held item or `OnBlockBroken(...)` if empty hand.

## 8) Entity interactions (milk, shear, trade, mount)

### Core call
- `Entity.OnInteract(EntityAgent byEntity, ItemSlot itemslot, Vec3d hitPos, EnumInteractMode mode)`
- Behaviors hook `EntityBehavior.OnInteract(...)` for actual logic.

### btca confirmation (vsapi)
- `hitPos` is **relative to the entity hitbox**.
- `EnumInteractMode.Attack = 0`, `EnumInteractMode.Interact = 1`.

### Hit position
- `hitPos` is **relative to the entity hitbox**, not world coords.
- Best practice: raytrace for selection and reuse its hit position.

### Range + LOS
- Use `IWorldAccessor.RayTraceForSelection(...)` with explicit range to enforce LOS and reach.

### Bot implications
- Call `OnInteract` with a **real item slot** from the bot’s hand.
- Trade/dialog likely assumes a real player session; may need server-side shortcuts.

### Client/server pipeline (stacks + API)
- Client selection updates via `SystemMouseInWorldInteractions.UpdatePicking/UpdateCurrentSelection`.
- Selection raycast uses `GameMain.RayTraceForSelection(...)`.
- Server receives interactions via `ServerSystemEntitySimulation.HandleEntityInteraction(...)`.
- Client uses `EntitySelection.HitPosition` when calling `Entity.OnInteract(...)` and when sending `EntityInteraction` packets.
- Server uses packet `HitX/Y/Z` directly for `Entity.OnInteract(...)`.
- Implication: for bots, use `RayTraceForSelection` and pass `EntitySelection.HitPosition` as-is (matches vanilla behavior).

## 9) Equipment / hand management

### Hands
- `EntityAgent.LeftHandItemSlot`, `RightHandItemSlot`, `ActiveHandItemSlot`.
- “Equip” = put item stack into hand slot and `MarkDirty()`.

### Player-like hotbar selection (if bot exposes IPlayer)
- `IPlayerInventoryManager.ActiveHotbarSlotNumber` + `BroadcastHotbarSlot()`.

## 10) Inventory sync + NPC visuals

### Slot-level sync
- `ItemSlot.MarkDirty()` queues slot for save + client resend.
- `IInventory.MarkSlotDirty(slotId)` is the inventory-level equivalent.

### BlockEntity persistence
- If a container BE changes inventory, also `BlockEntity.MarkDirty()` to sync BE state.

### Player-held visuals
- `IPlayerInventoryManager.BroadcastHotbarSlot()` is needed for other clients to see player-held changes.

### NPC held visuals
- NPCs are not players; consider syncing via `Entity.WatchedAttributes` + `MarkPathDirty(...)` if held item visuals are needed.

## 11) Non-player interaction patterns (fake player vs null)

### What exists in vanilla APIs
- No canonical `FakePlayer`/`DummyPlayer` class found.
- Many BE callbacks accept `IPlayer byPlayer = null` (nullable is the intended “no player” path).
- `DummySlot` / `DummyInventory` exist for item slots, not players.
- `EntityPlayerBot` exists in `vssurvivalmod/Entities/EntityPlayerBot.cs` (player-like entity pattern with inventory + held item rendering).

### Container caveat
- `BehaviorContainer` routes to `BE...OnPlayerRightClick(byPlayer, ...)`, which expects a real player context.
- If bot is not a player, consider:
  - Direct BE/inventory manipulation, or
  - Use the owning player’s `IPlayer` for permission fidelity.

## 12) Claims / protection checks

### Canonical access test
- `api.World.Claims.TestAccess(...)` / `TryAccess(...)`
- Use flags:
  - `Use` for interactions (containers, doors, etc.)
  - `BuildOrBreak` for placement/breaking
  - `Traverse` for movement through protected areas

### Hook points
- `ICoreAPI.Event.OnTestBlockAccess` and `OnTestBlockAccessClaim` allow mods to override access.
- Use these tests before bot actions to match vanilla protection expectations.

### btca confirmation (vsapi)
- `ILandClaimAPI.TestAccess(...)` returns `EnumWorldAccessResponse` (e.g., `Granted`, `LandClaimed`, `NoPrivilege`, `DeniedByMod`).
- `TryAccess(...)` performs the same check but also sends the error message and marks the block dirty on failure.

## 13) EntityActivitySystem actions (inventory/container?)

We confirmed the system lives in `VSSurvivalMod/Systems/EntityActivitySystem/Action/`, but the exact action class list wasn’t retrievable in the deep-research session. Next step: locally list that folder and search for inventory/container-related actions.

## 14) Vanilla container interaction routing (vssurvivalmod)

### BlockBehaviorContainer
- File: `VSSurvivalMod/BlockBehavior/BehaviorContainer.cs`
- `OnBlockInteractStart(...)`:
  - Sets `handling = EnumHandling.PreventSubsequent`.
  - Fetches the BE and, if it is a `BlockEntityOpenableContainer`, calls `beContainer.OnPlayerRightClick(byPlayer, blockSel)`.
- `BlockEntityOpenableContainer.OnPlayerRightClick(IPlayer byPlayer, BlockSelection blockSel)` is the abstract BE entrypoint.
