# 2026-01-13: /polis/targets state scan plan

## Goal
Add an optional `includeState=1` parameter to `GET /polis/targets` (blocks mode)
so agents can read a small, structured state object for common interactables.
Keep it opt-in and lightweight to avoid bloating normal scans.

## State sources (where the truth lives)
State is not standardized. It is stored in different places depending on block:

- Block variants (e.g., `Variant["state"] == "opened"` on some gates/torches).
- BlockEntity fields/properties (doors, trapdoors, containers, ground storage).
- BlockEntityBehavior fields (door bar lock, burning).
- External systems (reinforcement lock status).

## Candidate state map (vssurvivalmod references)
Doors (block entity behavior):
- `BEBehaviorDoor.Opened`, `InvertHandles`, `StoryLockedCode`
  (`docs/vssurvivalmod/BlockEntityBehavior/BEBehaviorDoor.cs`)

Trapdoors:
- `BEBehaviorTrapDoor.Opened`, `AttachedFace`, `RotDeg`
  (`docs/vssurvivalmod/BlockEntityBehavior/BEBehaviorTrapDoor.cs`)

Door bar lock:
- `BEBehaviorDoorBarLock.IsLocked`
  (`docs/vssurvivalmod/BlockEntityBehavior/BEBehaviorDoorBarLock.cs`)

Fence gates (no BE):
- Block variant `Variant["state"]` (opened/closed) via `BlockBaseDoor`
  (`docs/vssurvivalmod/Block/BlockBaseDoor.cs`, `BlockFenceGate.cs`)

Containers:
- `BlockEntityOpenableContainer.LidOpenEntityId` count
  (`docs/vssurvivalmod/BlockEntity/BEOpenableContainer.cs`)
- Inventory counts from `BlockEntityGenericContainer` and
  `BlockEntityGenericTypedContainer`
  (`docs/vssurvivalmod/BlockEntity/BEGenericContainer.cs`,
   `docs/vssurvivalmod/BlockEntity/BEGenericTypedContainer.cs`)

Ground storage:
- `BlockEntityGroundStorage.IsBurning`, `TotalStackSize`, `Capacity`,
  `MeshAngle`, `AttachFace`
  (`docs/vssurvivalmod/BlockEntity/BEGroundStorage.cs`)

Burning behavior:
- `BEBehaviorBurning.IsBurning`, `remainingBurnDuration`, `startDuration`
  (`docs/vssurvivalmod/BlockEntityBehavior/BEBehaviorBurning.cs`)

Lanterns:
- `BELantern.material`, `lining`, `glass`, `MeshAngle`
  (`docs/vssurvivalmod/BlockEntity/BELantern.cs`)

Torches:
- Variant `Variant["state"]` (e.g., `lit`, `extinct`) from `BlockEntityTorch`
  (`docs/vssurvivalmod/BlockEntity/BETorch.cs`)

Berry bushes:
- Block code variant `...-ripe` vs `...-empty` (state lives in block code;
  `BlockBehaviorHarvestable` changes the block and spawns item entities).

Lockable behavior:
- `BlockBehaviorLockable` checks `ModSystemBlockReinforcement.IsLockedForInteract`
  (requires `playerUid` for access)
  (`docs/vssurvivalmod/BlockBehavior/BehaviorLockable.cs`)

## Proposed output shape (draft)
Add optional `State` object to each block entry when `includeState=1`:

```json
{
  "Pos": [223, 3, 268],
  "Code": "game:door-solid-oak",
  "State": {
    "variantState": "opened",
    "door": { "opened": true, "invertHandles": false, "storyLocked": false },
    "lock": { "doorBarLocked": false, "reinforcementLocked": false }
  }
}
```

Notes:
- Always include `variantState` when `block.Variant["state"]` exists.
- Only include type-specific sub-objects when the BE/behavior exists.
- Keep inventories summarized: `slotCount`, `filledSlots`, `totalStackSize`.

## Test plan (manual + automated)

### Setup (what to place, all within ~8 blocks)
Minimum objects:
1) Door (solid oak) with open/close toggle.
2) Trapdoor with open/close toggle.
3) Fence gate with open/close toggle.
4) Chest (generic container) with a few items inside.
5) Crate (generic typed container) with a few items.
6) Ground storage stack (place a stack of items on the ground).
7) Lantern (any material/glass) placed.
8) Torch (lit and then extinguished).
9) Berry bushes (ripe and empty).

Optional objects (lock state):
- Door bar lock (if available in build).
- Padlocked container (requires reinforcement lock).

### Test steps (per object)
1) `GET /polis/players` -> capture `playerUid`.
2) `GET /polis/targets?playerUid=<uid>&radius=8&mode=blocks&includeState=1&codeContains=<keyword>`
3) Toggle state in-game (open/close, lock/unlock, extinguish).
4) Repeat the same `GET /polis/targets` call and confirm state change.

### Example filters
- Door: `codeContains=door`
- Trapdoor: `codeContains=trapdoor`
- Gate: `codeContains=gate`
- Chest: `codeContains=chest`
- Crate: `codeContains=crate`
- Ground storage: `codeContains=groundstorage` or the stored item code
- Torch: `codeContains=torch`
- Lantern: `codeContains=lantern`
- Berry: `codeContains=berrybush` or `q=bush`

### Expected verification
- `variantState` flips `opened` <-> `closed` on gates.
- `door.opened` / `trapdoor.opened` flips.
- `container.slotCount`, `filledSlots` stable and >0 with items.
- `groundStorage.totalStackSize` reflects placed stack.
- `burning.isBurning` true for active fire behaviors.
- `lantern.material/glass` matches the placed lantern.
- `berry.state` or `variantState` indicates `ripe`/`empty`.

## Notes for automation
- Keep `includeState` opt-in to avoid large responses.
- Always filter with `codeContains` or `q` during tests.
- For lock checks, require `playerUid` because reinforcements are per-player.
