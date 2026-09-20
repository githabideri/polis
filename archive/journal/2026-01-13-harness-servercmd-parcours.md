# 2026-01-13: Harness servercmd parcours

## Context
We added `POST /polis/servercmd` as a local-only escape hatch to run raw server/chat commands and wanted to validate its behavior and output richness while the game was running.

## Test parcours
- Harness readiness: `GET /polis/status` returned `worldReady=true`.
- Player context: `GET /polis/players`, `GET /polis/player?uid=...`, and `GET /polis/look?uid=...` all returned expected state.
- Server command help:
  - `/servercmd` with `/help weather` returned a full subcommand list in `message`.
- Player-required command failure:
  - `/servercmd` with `/weather set clearsky` (no `playerUid`) returned `Error: Caller must be player`.
- Player-context commands succeeded:
  - `/weather set clearsky` -> `Success` and updated weather.
  - `/weather stoprain` -> `Success` with note about precipitation override (`/weather setprecipa` to reset).
  - `/time` -> returned formatted server time + game speed.
  - `/player <name> entity` -> returned server coords, satiety, and health.
  - `/polis list` -> returned bot list + server coords.
- Harness command flow:
  - `spawn` near player -> `goto` (context offset) -> `stop` -> `despawn` all succeeded.

## Addendum: activation tests (door/chest)
- Looked at a placed door/chest via `/polis/look` (server raytrace) and received a concrete block code + position (e.g., `game:chest-east`).
- Ran `/polis activate <x y z>` via `servercmd` using those coordinates; response was `No block at target position`.
- Tried selector form `/polis activate l[]`; response was still `No block at target position`.
- Likely cause: `WorldPosition` parsing treats bare numeric coords as map-middle relative (needs `=x =y =z` for absolute) and `l[]` depends on server-side `CurrentBlockSelection`, which may be stale or unavailable even when `/polis/look` resolves a block.

## Findings
1) `servercmd` returns structured success/failure with helpful messages.
2) Many vanilla commands require a player context; without `playerUid` they fail with `Caller must be player`.
3) `servercmd` is useful for quick state probes (`/time`, `/player <name> entity`) without additional harness endpoints.
4) `servercmd` can trigger global overrides (e.g., `/weather stoprain`), which persist until explicitly reset (`/weather setprecipa`).
5) Position-based chat commands are sensitive to coordinate parsing; unprefixed numeric coords can target the wrong location.

## Evidence
- Raw output log: `/tmp/polis-harness-parcours-20260113-010229.json`

## Open questions
- Should scripts always pass `playerUid` when using `servercmd` to avoid player-only failures?
- Do we want a helper endpoint to fetch the server command handbook output (e.g., `.chb`) instead of relying on wiki snapshots?
- Verify whether `/polis activate =x =y =z` works with absolute coords, and whether `l[]` works when `CurrentBlockSelection` is set server-side.
