# 2026-01-14: Polisbot migration

## Context
Switch default bot from `survival:playerbot` to a custom `polisbot` entity and
remove the playerbot fallback. This keeps the mod independent of Survival assets
and lets us evolve the bot entity in-mod.

## Changes
- Added `assets/polis-builder-npc/entities/polisbot.json` (seraph humanoid).
- Added `EntityPolisBot` (EntityHumanoid + seraph inventory for hands).
- Register entity class in `PolisBuilderNpcSystem.Start()`.
- Default bot code now `polis-builder-npc:polisbot`.
- On save load, migrate old bot records with `playerbot` codes to `polisbot`.
- Removed fallback to any `playerbot` entity in spawn resolution.
- Removed `extraskinnable` behavior to avoid NRE (missing `skinnableParts`).

## Follow-up tests
- Spawn and confirm polisbot renders with default seraph texture.
- Validate give/drop/pickup/activate/goto behaviors match playerbot.
- Verify old saves migrate to polisbot and bots persist.
- If we want clothing or gear visuals, add `extraskinnable` back with
  `attributes.skinnableParts` populated.

## Test run (2026-01-14)
- Despawned old `playerbot`, spawned `polisbot` near player via `spawnOffset`.
- `/polis/targets` from bot anchor found door/gate/chest; `activate` succeeded on all three.
- `give`/`drop`/`pickup` succeeded; inventory persisted with seraph slots.
- No server log errors on spawn after removing `extraskinnable`.
