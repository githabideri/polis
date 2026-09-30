# DESIGN.md — architecture contract

Distilled from the frozen history in `archive/` (VISION/TECHNICAL/journals).
This document is the living design contract; when code and this doc
disagree, fix the doc in the same change.

## The concept

**"Deity RTS with Possession."** A player oversees a population of
autonomous workers (colony/build/RTS layer) and can *possess* one of them
to take direct control (action layer) when the AI isn't good enough.
Possession is only powerful once autonomous behavior exists. The autonomy
layer is the R2 job system (`r2/` — see
`docs/design/2026-09-26-job-system-r2.md`); the full pre-1.22.7 plan and
research trail are frozen in `archive/VISION.md`.

## Module map (src/)

| Module | Responsibility |
|--------|----------------|
| `PolisBuilderNpc.cs` (+ `Core/`) | Mod entry, systems, block/entity registration |
| `PolisBuilderNpcSystem.cs` | Server-side bot registry & command execution (the "god" side) |
| `EntityPolisBot.cs` | The bot entity: inventory, health, movement target |
| `Actions/` | `IEntityAction` implementations: Goto (A* + fallback), Mine, Harvest, Pickup, Place, Activate, Butcher, … |
| `PolisClientPossessionHandler.cs` + `PolisPossessableSeat.cs` | Possession: IMountable/IMountableSeat at the bot's eyes, input routing to bot locomotion, player render-hide, client-side smoothing |
| `PolisNetworkPackets.cs` | Client↔server sync (selection, possession, debug flags) |
| `PolisEventBroadcaster.cs` | Game event feed for observers (harness/Web UI) |
| `PolisScreenCapture*.cs` | In-game screen capture for visual verification |
| `PolisTestHarness.cs` + `Harness/` | HTTP server on `localhost:8585` (`/polis/*`) + test command handlers |
| `Gui/` | Bot manager GUI, debug overlays |
| `Helpers/` | A* pathfinder, LOS, selection math, etc. |

## Command surface

- Chat: `/polis <subcommand>` (full list in `docs/SERVER_COMMANDS.md`).
- Hotkeys: Alt+N/L/G/A/B/H (+Shift variants) — `docs/CLI.md` + README.
- HTTP: `GET/POST /polis/*` on `localhost:8585` (harness) — `docs/CLI.md`,
  `docs/TESTING_HARNESS.md`. CLI wrapper: `scripts/poliscli.py` (TOON output,
  env-driven player/bot ids, `--wait` for timed actions).

## Key invariants

1. **Server is authoritative** for bot state; the client mirrors what it
   needs (selection highlight, possession, debug visuals).
2. **Possession is a mount relationship** (VS IMountable), so it composes
   with vanilla seat/mount handling; the player entity is hidden
   (render scale 0) while possessed.
3. **Commands resolve coordinates absolutely** (`=x =y =z`); relative
   selection (`l[]`) is client-only and not a reliable target source
   (see KNOWN_ISSUES in `archive/`).
4. **Harness calls are fire-and-verify**: actions can report `Ok: true` at
   start and fail later — tests must re-read `/polis/state` (this is the
   "silent failure" class of bug; see `archive/KNOWN_ISSUES.md`).
5. **Version boundary:** the mod targets one game version at a time.
   Version-specific API usage is kept isolated so a port is a bounded change
   — from the next version on through `Compat/<ver>/` facades (one facade
   directory + csproj TFM bump, nothing else; the "version shim law"). The
   1.22 port predates the facade discipline and calls the API directly.
