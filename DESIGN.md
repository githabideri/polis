# DESIGN.md — architecture contract

Distilled from the frozen history in `archive/` (VISION/TECHNICAL/journals).
This document is the living design contract; when code and this doc
disagree, fix the doc in the same change.

## The concept

**"Deity RTS with Possession."** A player oversees a population of
autonomous workers (colony/build/RTS layer) and can *possess* one of them
to take direct control (action layer) when the AI isn't good enough.
Possession is only powerful once autonomous behavior exists; today the
autonomy layer is just command-driven primitives (Phase 0/1 shipped,
Phase 2 job system planned — see `archive/VISION.md` for the full plan and
research links).

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
| `Compat/VS122/` | **Version shim** — the only place 1.22.x API specifics live |

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
5. **Version boundary:** feature code → `Compat/<ver>/` facades → game API.
   Bumping the game version touches one facade directory + csproj, nothing
   else (the "version shim law").
