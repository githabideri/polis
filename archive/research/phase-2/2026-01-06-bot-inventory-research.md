# Bot Inventory Research (Phase 2)

**Date:** 2026-01-06  
**Updated:** 2026-01-13  
**Status:** In progress

## Goal
Define how bot inventory should work in polis-builder-npc, with concrete evidence from Vintage Story code/assets. Avoid "Minecraft-style" infinite inventory; match VS semantics (hands + backpacks).

## Current Evidence (Grounded)

### Bot entity and behaviors
- `survival:playerbot` is the bot entity used by this mod (see `PolisBuilderNpcSystem.cs` default entity code).
- `playerbot.json` includes `seraphinventory` in both client and server behaviors.
  - File: `/home/mf/.local/share/flatpak/app/at.vintagestory.VintageStory/x86_64/stable/active/files/extra/vintagestory/assets/survival/entities/humanoid/playerbot.json`
- Decompiled classes show:
  - `EntityPlayerBot` uses `EntityBehaviorSeraphInventory` and maps hands to slots 15 and 16.
    - Source: `VSSurvivalMod.dll` → `Vintagestory.GameContent.EntityPlayerBot`
  - `EntityBehaviorSeraphInventory` is a container-based inventory behavior using `InventoryGear`.
    - Source: `VSSurvivalMod.dll` → `Vintagestory.GameContent.EntityBehaviorSeraphInventory`
  - `InventoryGear` has 19 slots:
    - Slots 15/16 are `ItemSlotSurvival` (right/left hand).
    - Slots 17/18 are `ItemSlotBackpack`.
    - Slots 0-14 are clothing/gear.
    - Source: `VSSurvivalMod.dll` → `Vintagestory.GameContent.InventoryGear`
  - `EntityBehaviorSeraphInventory` listens for `"wearablesInv"` changes, but stores inventory using `InventoryClassName = "seraphinventory"` via `EntityBehaviorContainer`.
    - Source: `VSSurvivalMod.dll` → `Vintagestory.GameContent.EntityBehaviorSeraphInventory`
    - Source: `vsessentialsmod/Entity/Behavior/BehaviorContainer.cs` (storage key)
  - `EntityBehaviorAttachable` uses an **actual** `InventoryClassName = "wearablesInv"` with `InventoryGeneric + ItemSlotWearable`.
    - Source: `VSSurvivalMod.dll` → `Vintagestory.GameContent.EntityBehaviorAttachable`
  - `EntityBehaviorRideableAccessories` extends `EntityBehaviorAttachable` and is registered as `"rideableaccessories"`.
    - Source: `VSSurvivalMod.dll` → `Vintagestory.GameContent.EntityBehaviorRideableAccessories`

### Player inventory model
- Player inventory is not a single "big grid"; it is composed of multiple inventories:
  - Hotbar (10 slots + skill slot + offhand): `InventoryPlayerHotbar` (12 slots).
  - Backpack slots (4 slots) plus bag contents: `InventoryPlayerBackPacks`.
  - Source: `VintagestoryLib.dll` → `Vintagestory.Common.InventoryPlayerHotbar`, `Vintagestory.Common.InventoryPlayerBackPacks`
- Backpack slot semantics:
  - `ItemSlotBackpack` only holds the container item (basket/backpack).
  - Bag contents are managed by `BagInventory` inside `InventoryPlayerBackPacks`.
  - Source: `../vsapi/Common/Inventory/ItemSlotBackpack.cs`, `VintagestoryLib.dll` → `InventoryPlayerBackPacks`
  - Bag contents are driven by `IHeldBag` on the bag item; it defines slot count, storage flags, and persistence.
    - Source: `../vsapi/Common/Inventory/BagInventory.cs` (`IHeldBag`, `ItemSlotBagContent`)
  - `HeldBag` is a CollectibleBehavior implemented in VSEssentials and persists bag contents in `ItemStack.Attributes["backpack"]`.
    - Source: `VSEssentials.dll` → `Vintagestory.GameContent.CollectibleBehaviorHeldBag`

### Non-player usage (pack animals)
- Tamed hooved animals use `rideableaccessories` with `wearableSlots` (e.g., `elk-tamed.json`).
  - File: `/home/mf/.local/share/flatpak/app/at.vintagestory.VintageStory/x86_64/stable/active/files/extra/vintagestory/assets/survival/entities/animal/mammal/hooved/elk-tamed.json`
- Hooved wearable items include saddlebags with `HeldBag` behavior and `backpackByType` slot counts (16/20).
  - File: `/home/mf/.local/share/flatpak/app/at.vintagestory.VintageStory/x86_64/stable/active/files/extra/vintagestory/assets/survival/itemtypes/wearable/animal/hooved.json`
- This indicates bag-backed storage is already used on non-player entities via attachable slots.

### BagInventory usage beyond players
- `AttachedContainerWorkspace` uses `BagInventory` to wrap a held bag into an `InventoryGeneric` for entity-attached storage UI and sync.
  - Source: `VSEssentials.dll` (decompiled) → `AttachedContainerWorkspace`
- `CollectibleBehaviorHeldBag` uses `AttachedContainerWorkspace` for on-entity bag interaction and packet handling.
  - Source: `VSEssentials.dll` → `Vintagestory.GameContent.CollectibleBehaviorHeldBag`
- `CollectibleBehaviorBoatableCrate` (extends `CollectibleBehaviorHeldBag`) uses `BagInventory` for a crate attached to entities.
  - Source: `VSSurvivalMod.dll` → `Vintagestory.GameContent.CollectibleBehaviorBoatableCrate`

## Server-side Bag Operations (No UI)

### Core facts
- Bag contents are persisted on the **bag item** itself: `ItemStack.Attributes["backpack"]["slots"]`.
- `CollectibleBehaviorHeldBag.GetOrCreateSlots(...)` rebuilds `ItemSlotBagContent` from those attributes.
- `BagInventory.SaveSlotIntoBag(...)` writes changes back into the bag item attributes.

### Working patterns found in engine code
- `AttachedContainerWorkspace.TryLoadInv(...)`:
  1) Creates `BagInventory`.
  2) Calls `BagInventory.ReloadBagInventory(wrapperInv, bagSlotArray)`.
  3) Builds an `InventoryGeneric wrapperInv` whose slots are backed by `ItemSlotBagContent`.
  4) On slot modified, calls `BagInventory.SaveSlotIntoBag(...)`.
- This pathway is used for entity-attached bags and does **not** require a `PlayerInventoryManager` for storage updates (only for UI open/close).

### How bots could reuse this (server-only)
Option 1: **Direct slots via IHeldBag**
- Use the bag’s `IHeldBag.GetOrCreateSlots(bagstack, parentInv, bagIndex, world)` to get `ItemSlotBagContent[]`.
- Move items with `ItemSlot.TryPutInto(...)` between bot slots and these bag content slots.
- After changes, call `bag.Store(...)` or `BagInventory.SaveSlotIntoBag(...)` to persist.
- **Note:** you must provide a valid `parentInv` (e.g., a dedicated `InventoryGeneric`) because `ItemSlotBagContent` needs an owning inventory.

Option 2: **Wrapper inventory (AttachedContainerWorkspace pattern)**
- Build a temporary `InventoryGeneric wrapperInv` with `NewSlot` returning `bagInv[slotId]`.
- Use `wrapperInv.GetBestSuitedSlot(...)` and `TryPutInto(...)` to move items.
- On every change, call `bagInv.SaveSlotIntoBag((ItemSlotBagContent)slot)` or hook `SlotModified`.

### Implications for bots
- Bots can have bag contents without a player inventory manager; the storage system is item-attribute based.
- The main requirement is an **`ItemSlotBackpack` containing a HeldBag item** and a helper inventory context to manipulate its slots.

## Proposed Implementation Plan (Pending Validation)

1) **Choose a target inventory model**
   - **Selected**: use `EntityBehaviorSeraphInventory` / `InventoryGear` as-is; treat bot inventory as "hands + 2 backpack slots" (no hotbar).
   - Rationale: matches existing bot entity behavior and aligns with current design preference.

2) **Define bot inventory scope**
   - **Target**: hands (right/left) + 2 backpack slots (with bag contents when a HeldBag is inserted).

3) **Integrate with pickup/drop**
   - Ensure `TryGiveItemStack` targets a real inventory with valid slot suitability rules.
   - Avoid "magic" storage unrelated to VS inventory classes.

## Bot Inventory Target (Decision)

**Target model**: `EntityPlayerBot` + `EntityBehaviorSeraphInventory` + `InventoryGear`.

**Slots available:**
- Right hand: `InventoryGear[15]` (`ItemSlotSurvival`)
- Left hand: `InventoryGear[16]` (`ItemSlotSurvival`)
- Backpack slots: `InventoryGear[17]` and `InventoryGear[18]` (`ItemSlotBackpack`)

**No hotbar.** Bots will not have a player-style hotbar or 4 backpack slots.

**Bag contents:**  
If a backpack slot contains a `HeldBag` item (basket/backpack/saddlebags), bag contents are stored on the item via `ItemStack.Attributes["backpack"]` and can be accessed with `IHeldBag.GetOrCreateSlots(...)` or `BagInventory`.

### Operational routing (for later implementation)
- **Pickup (server):** attempt to place into right/left hand (if empty or best suited), then into backpack slots and their contents.
- **Drop (server):** select from right/left hand or from bag contents, update bag attributes via `BagInventory.SaveSlotIntoBag`.

### Implementation Steps (Polis)
1) Resolve `EntityBehaviorSeraphInventory` and `InventoryGear` for the bot.
2) Insert/remove using explicit slots:
   - Hands: `InventoryGear[15]` (right), `InventoryGear[16]` (left).
   - Backpacks: `InventoryGear[17]` / `[18]` (ItemSlotBackpack).
3) For item moves, prefer `ItemSlot.TryPutInto(...)` over `Entity.TryGiveItemStack` when the target is a PlayerBot.
4) After any slot change:
   - Call `slot.MarkDirty()` on changed slots.
   - Call `invbh.storeInv()` (EntityBehaviorContainer.storeInv) to persist/sync `seraphinventory`.
5) If a backpack slot contains a HeldBag:
   - Use `IHeldBag.GetOrCreateSlots(...)` or `BagInventory` to access bag contents.
   - After modifying bag slots, call `BagInventory.SaveSlotIntoBag(...)`.
   - Call `invbh.storeInv()` for persistence and client sync.
6) Update action entry points:
   - `PolisPickupItemAction`: insert into hand/backpack slots directly (no TryGiveItemStack).
   - `CmdGive`: same slot-based insert flow.
   - `PolisDropItemAction`: allow drop from backpack/bag contents (optional; defer if scope is hands only).

**References:**  
`docs/research/phase-2/2026-01-14-bot-inventory-sync-flow.md`  
`docs/research/phase-2/2026-01-13-held-item-visual-sync-playerbot.md`

## Assumptions to Scrutinize (Testable)

1) **A1: `EntityBehaviorSeraphInventory` is the only inventory behavior for `playerbot`.**  
   - Test: inspect `playerbot.json` behaviors and decompile `EntityPlayerBot` for any other inventory behaviors.

2) **A2: `InventoryGear` is the intended inventory for bots.**  
   - Test: locate any references to `InventoryGear` in `EntityPlayerBot` logic and related behaviors, and confirm its use in entity initialization.

3) **A3: Bot hands are only slots 15/16 in `InventoryGear`.**  
   - Test: confirm `EntityPlayerBot.RightHandItemSlot` / `LeftHandItemSlot` mapping.

4) **A4: `InventoryGear` backpack slots (17/18) represent actual backpack items, but do NOT include bag contents.**  
   - Test: confirm `InventoryGear.NewSlot` uses `ItemSlotBackpack` for slots >16 and verify no `BagInventory`/`ItemSlotBagContent` is used.

5) **A5: Using `InventoryPlayerHotbar` or `InventoryPlayerBackPacks` for bots is not viable without a player inventory manager.**  
   - Test: review their dependencies on `IPlayer`, `PlayerInventoryManager`, and network utilities.

6) **A6: The current bot inventory is *not* equivalent to the player’s backpack system (4 slots + scalable contents).**  
   - Test: compare `InventoryGear` slot counts with `InventoryPlayerBackPacks` and validate number of backpack slots in player UI.

7) **A7: The inventory storage key used by `EntityBehaviorSeraphInventory` is `seraphinventory`, not `wearablesInv`.**  
   - Status: confirmed storage key is `seraphinventory`; `wearablesInv` belongs to `EntityBehaviorAttachable`.

8) **A8: Bag capacity is driven purely by item JSON attributes (e.g., `backpack.quantitySlots` or `backpackByType`).**  
   - Test: inspect backpack/bag JSON and verify `CollectibleBehaviorHeldBag.GetQuantitySlots` reads from `ItemStack.ItemAttributes["backpack"]`.

9) **A9: Any entity can host bag contents as long as it has an `ItemSlotBackpack` and the bag item uses `HeldBag`.**  
   - Status: confirmed `BagInventory` is used in `AttachedContainerWorkspace` for entity-attached bags; not tied to `EntityPlayer` for storage operations.
   - Remaining test: confirm if any non-player inventory uses `BagInventory` outside the UI pathway (e.g., bot server-side pickup/put flow).

## Open Research Questions

1) Is there an entity-oriented equivalent of player backpack contents (bag storage) for NPCs?
2) Is `playerbot` intended to be limited to two backpack slots, or is that just a convenience for bots?
3) If we add a bot hotbar, how should "active slot" be defined without a `PlayerInventoryManager`?
4) Are there any existing NPC inventory behaviors (other than `seraphinventory`) that already model bags or hotbar-like behavior?
5) Are there non-player inventories using `HeldBag`/`BagInventory` successfully (e.g., pack animals, armor stands, or other entities)?

**Resolved:** persistence/sync uses `EntityBehaviorContainer.storeInv()` for `seraphinventory` (see `2026-01-14-bot-inventory-sync-flow.md`).

## Next Research Steps (Planned)

1) Trace `wearablesInv` usage across VSSurvival/VSEssentials to confirm inventory key expectations.
2) Decompile or locate any NPC inventory behaviors besides `EntityBehaviorSeraphInventory`.
3) Validate UI slot counts for player inventory (hotbar + backpack slots) and confirm bag contents capacity scaling.
4) Locate references to `InventoryGear` in the survival mod to see how it is intended to be used beyond clothing.
5) Identify whether any entity inventories use `HeldBag`/`BagInventory` without a `PlayerInventoryManager`.

## Research Log (Initial Pass)

- Confirmed `BagInventory` and `IHeldBag` drive backpack contents, with per-bag slot counts and storage flags (`vsapi/Common/Inventory/BagInventory.cs`).
- Confirmed `EntityBehaviorContainer` persists inventory under `InventoryClassName` via `InWorldContainer` (`vsessentialsmod/Entity/Behavior/BehaviorContainer.cs`).
- Found `EntityBehaviorAttachable` as the owner of `wearablesInv`; `EntityBehaviorSeraphInventory` appears to be listening so clothing/attachments trigger shape refresh.
- Confirmed `CollectibleBehaviorHeldBag` persists contents in `ItemStack.Attributes["backpack"]` and provides `GetQuantitySlots`/`GetStorageFlags`.
- Inspected bag JSONs: `handbasket` uses `backpack.quantitySlots: 3`; `backpack` uses `backpackByType` (6 normal / 8 sturdy); `miningbag` uses `quantitySlots: 12` and custom `storageFlags`.
- Found pack animals using `rideableaccessories` wearable slots and `HeldBag` saddlebags (non-player entity storage).
- Found `BagInventory` usage in `AttachedContainerWorkspace` and `CollectibleBehaviorBoatableCrate` (entity-attached container flow).

## User-Supplied Context (2026-01-13)

This is a condensed summary of user research on VS NPC architecture that
affects bot inventory behavior:

- NPCs inherit from `EntityAgent`, which provides controls/locomotion and core
  lifecycle hooks.
- AI uses `EntityBehaviorTaskAI` with a priority-based task list (slots 0-7).
- Human-like NPCs (including `EntityPlayerBot`) use the seraph model, with
  inventory and gear handled by `EntityBehaviorSeraphInventory` (`InventoryGear`).
- `TryGiveItemStack` is a best-effort suggestion. If the entity has no behavior
  that accepts the stack, the call fails by default.
- PlayerBot inventory is stricter than generic animal loot behavior and expects
  explicit slot management.

**Implication:** pickup/transfer must be implemented by writing to specific
`InventoryGear` slots (hands/backpack) rather than relying on
`Entity.TryGiveItemStack`.
