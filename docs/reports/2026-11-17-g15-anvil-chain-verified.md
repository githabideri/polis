# G15 anvil casting chain — first pour verified on 1.22.7

2026-11-17, world `polis-survival-7` (surgically transplanted from the
former game host to the estate's flexibility host that morning: the world
database, Oikistes state and agent wiring moved out of the former host's
PBS snapshot; the target box kept its own network/GPU/runtime and its
old 1.21-era worlds stay on disk untouched). Campaign bot #2746130
(same world; the pre-migration body was #650). Session 2026-11-17_002.
Method: ildasm of `VSSurvivalMod.dll` plus live harness runs. Every
transformation below runs through the game's own code paths; the harness
contributes only the bypasses explicitly marked "force" or "disclosed
stand-in", all logged in the session transcript.

## Result

```
10 clay-red
  → clayform <anvil mold cell> anvilmold-fire-anvil   (the engine's own sculpt; ~5 s)
  → kiln: floor → pitkiln, anvilmold-fire-raw in the hole storage
  → kiln feed / ignite / ff
      → game:toolmold-fire-fired-anvil in the kiln's groundstorage (OnFired → KillFire(true))
  → kiln: crucible-fire-raw in the hole storage
  → kiln feed / ignite / ff
      → game:crucible-fire-fired in the groundstorage (the kiln, NOT the firepit, fires crucibles)
  → firepit: crucible-fire (fired, input slot) / crucible-insert 20 nuggets
  → crucible-fuel 1 charcoal (burning)
  → crucible-fire force            (the disclosed cook-clock fill; the smelt is the engine's DoSmelt)
      → crucible-fire-smelted, units = 100, output = game:ingot-copper
  → crucible-pour <mold> force     (the disclosed re-heat; the pour is the engine's ReceiveLiquidMetal)
      → mold-info: type=toolmold, content=game:ingot-copper, temperature 1055.68°C
```

**The first pour of the anvil cast is live-verified: molten copper
entered the fired anvil toolmold through the engine's own
`ReceiveLiquidMetal`, and the filled state is PERSISTENT** — the world
survived a full game restart with the mold's contents serialized
(content = ingot-copper, hardened to ambient). One pour carries
100 units against the fired toolmold's 900 (`requiredUnits`), so the
full cast is 9 pours: a multi-day campaign, not a single-session one.

## The anvil-smith branch (partially verified)

New harness surface added for G15 (all in `PolisHarnessCommandHandlers.cs`):

- `anvil-put <x> <y> <z> [item]`: first placement via the engine's own
  `ItemWorkItem.TryPlaceOn` (creates the workitem + `CreateVoxelsFromIngot`,
  42 voxels in the canonical 7×2×3 footprint); re-calls on an existing
  workitem merge through the engine's `AddVoxelsFromIngot` (adds voxels
  into the *same* footprint, so a workitem whose footprint is full
  reports `requireshammering` and adds 0 — the engine's own compaction
  gate). Pre-heats the ingot to 800°C before the place check as the
  disclosed fire-heat stand-in (the engine's >20°C workable gate is
  checked, not bypassed; logged on every call).
- `anvil-heat <x> <y> <z> <t>`: disclosed stand-in setting the workitem's
  temperature attribute (same family as `crucible-fire force`).
- `anvil-state <x> <y> <z>`: workitem code, temperature, selected recipe,
  metal/slag/empty voxel counts (direct read of the BE voxel grid).
- `anvil-smith <x> <y> <z> <tool> <metal>`: routes the player into the
  engine's own smithing action (finished items land in the caller's
  cargo). Recipe resolution fixed: the chisel is ONE item code with a
  metal variantgroup, so the candidate match now accepts `path == code`
  or (`path == base` AND the variant metal matches the requested metal).

Measured behavior: the engine's smithing action runs and consumes
workitem voxels — 29 per invocation on a fresh 42-voxel copper
workitem (42 → 13), then stalls at 13 regardless of further
invocations or re-heating (temperature still 550-770°C, `CanWork`
true). The chisel's smithing pattern is 16 voxels
(`recipes/smithing/chisel.json`); the 13 remaining voxels of a fresh
workitem do not match the pattern, and the engine gates further
consumption behind an interactive step (the hammer/compaction workflow)
that the harness does not yet drive. **The smithing branch is
therefore partially verified: the engine's smithing action executes
against the workitem through the harness; full chisel completion needs
a `anvil-smith` that also drives the between-batch compaction — the
next gap in this branch.**

## Engine gaps measured this session (add to the bug-report list)

1. **The explicit world save API is not reachable from a mod, and the
   signal shutdown does not save.** `GameServer`'s save entry points are
   only invoked by the server tick loop; the 1.22.7 native headless
   build's SIGTERM/SIGINT exit path saves nothing (the "World saved!"
   autosave line appears in the log, yet chunk edits were observed lost
   across a restart — a placed anvil block survived one restart but was
   gone after the next; the poured toolmold survived because its state
   rides the world database, not just the chunk index). Operational
   rule adopted: run each campaign in ONE game-process lifetime; after
   a meaningful mutation wait for the next autosave (5 min) before any
   restart; a clean vsgame exit (the unit is Restart=on-failure) is a
   state-loss event until the autosave has landed.
2. **Entity inventories are not persisted across a clean shutdown**
   (same root as 1: entity state is part of the not-saved path). Bots
   lose every held item on a vsgame restart — world-side storage
   (groundstorage) is the only durable campaign bank.
3. **`BEPitKiln.OnFired` → `KillFire(true)` lost its contents once**
   (the raw ingot mold vanished; three subsequent identical
   create→feed→ignite→ff cycles converted cleanly, including both
   crucible raws and the anvil mold). One-off instance; suspected
   interaction with the failed-ignite → manual-ignite sequence on the
   first run. Folded into the existing pitkiln persistence report.
4. **`setblock` resolves item codes, not block template parents.**
   `game:rock` is unknown (it is a template parent); concrete variant
   codes (`game:soil-medium-normal`, `game:anvil-copper`,
   `game:toolmold-fire-fired-anvil`) work. Variantless blocks whose
   default variant is a template parent also fail. The anvil and the
   toolmold are variant-grouped (metal / type) — always address them
   with the full variant code.

## Session-log notes (estate side, sanitized out of this repo)

- The NPM front for the web UI was re-pointed to the new host the same
  morning (the proxy's `forward_scheme` DB field controls the backend
  scheme — it was `https`, the harness is plain HTTP; both fixed).
- A 5-minute persistence watcher (vsgame + harness + oikistes liveness,
  JSONL) is running on the host; it has logged healthy since the
  transplant.
- World 7's PBS safety net: the former host's PBS snapshots remain the
  last complete backup (15 snapshots through 2026-11-13); a new backup
  roster for the transplanted world is pending the estate's backup
  re-organization.
