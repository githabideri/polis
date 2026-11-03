# [1.22.7] Pit kiln (`game:pitkiln`) block does not persist across chunk saves, and its vanilla creation path is unreachable on a dedicated server

## Environment

Vintage Story 1.22.7, .NET 10, Linux dedicated server (embedded client
for a headless research setup; a custom mod was used only to drive and
observe the game's own methods — `BlockAccessor.SetBlock`,
`BlockEntityPitKiln.TryIgnite`, `GetBlockEntity` — nothing re-implemented).
The same block entity also appears in singleplayer; the persistence
behaviour below was observed on the dedicated-server save path.

## Observed behavior

1. **The block reverts after any chunk save.** Converting the floor cell
   of a 1-deep hole (solid, non-flammable floor and sides) to
   `game:pitkiln` — exactly what the vanilla conversion path itself does
   with `BlockAccessor.SetBlock` — works in memory: the
   `BlockEntityPitKiln` is created, its build stages accept
   dry grass/sticks/fuel, `TryIgnite` starts the 20-hour burn, and
   `OnFired` smelts a `crucible-*-raw` in its inventory to the fired
   variant. But the block is **not written to the chunk data**: after a
   server restart (or chunk reload), the cell reads back as the
   previous block (in our world: soil), not `game:pitkiln`.

2. **The orphaned block entity then crashes on load.** The chunk still
   stores a `PitKiln` block entity at that position, so it is recreated
   on chunk load — now on top of the *soil* block. Its `Initialize`
   throws a `NullReferenceException` (BEPitKiln.cs line 74): the block
   it is initialised against no longer provides the `Burning` entity
   behaviour that `BlockEntityPitKiln` expects (the pitkiln block JSON
   declares `entityBehaviors: [{ name: "Burning" }]`, soil declares none).
   The exception is logged on every restart for as long as the entity
   record exists in the chunk. The storage contents of the hole survive;
   the kiln itself is permanently dead until the entity is removed.

3. **The vanilla creation trigger has no caller.** The only path that
   converts a hole into a functioning kiln is
   `BlockPitkiln.TryCreateKiln(world, byPlayer, pos)` (validates the
   hole geometry, sets the block, starts the build stages). In the
   shipped 1.22.7 assemblies this method has **no callers in any
   shipped class**, and the block's creative inventory is empty
   (`creativeinventory: { general: [""], decorative: [""] }`). A bare
   `BlockEntityPitKiln` *does* auto-spawn when a fireable item is placed
   into a valid hole (observed live within seconds), but the floor
   conversion that would make the kiln function is never triggered. On a
   dedicated server the handbook page the block's JSON references
   (`handbook-pitkiln-createdby`) does not exist in the shipped assets.
   Net effect: on a dedicated server there is no in-game way to create a
   working pit kiln.

Block JSON of record (1.22.7 `game:pitkiln`): invisible shape
(`block/basic/invisible`), `replaceable: 100`, `sidesolid`/`sideopaque`
all-false, `entityClass: "PitKiln"`, `entityBehaviors: [{ name:
"Burning" }]`, `combustibleProps` 800/2000, empty `drops`, empty
creative inventory.

## Reproduction

1. Dedicated server, 1.22.7. Dig a 1-block-deep hole with a solid,
   non-flammable floor and all four sides.
2. Set the floor cell to `game:pitkiln` (`BlockAccessor.SetBlock` — the
   same call the vanilla conversion uses). Observe the
   `BlockEntityPitKiln` appear at the position.
3. Restart the server (or force the chunk to save and reload).
4. The floor cell reads back as the previous block. The server log shows
   the `NullReferenceException` from `BlockEntityPitKiln.Initialize` at
   that position. Repeating the restart logs the same exception every
   time.

## Proposed fix

- Persist the `game:pitkiln` block in chunk data (it is currently treated
  as an in-memory/auxiliary marker), or move the kiln's state entirely
  into the block entity and make the block a pure placeholder that is
  never written.
- Guard `BlockEntityPitKiln.Initialize` against a null `Burning`
  behaviour (and log at most once), so an orphaned entity on a
  non-pitkiln block degrades to a no-op instead of an NRE on every
  chunk load.
- Wire up (or remove) `TryCreateKiln`: if the hole-kiln flow is meant
  to work on dedicated servers, the auto-spawned entity's interact path
  should complete the floor conversion; otherwise the dead handbook
  reference and the empty creative inventory should be fixed so players
  are not pointed at an unreachable feature.

## Verification

Each step above was exercised live on the running server: in-memory
creation, stage feeding, ignition, the 20-hour burn fast-forwarded, and
the `OnFired` smelt all succeeded before the restart; the cell revert,
the per-restart NRE, and the empty creative inventory were read back
from the running game after the restart. The full sequence only
completes when run in a single live session (the fired output lands in
the hole's storage block, which does persist).
