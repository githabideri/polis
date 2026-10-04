# 2026-10-04 — Endogenous craft chain live-verified (log → planks)

The bot can now produce materials from raw ingredients using the game's
own recipe engine — the crafting half of the endogenous tool-production
milestone (13.13's M2 family, the "craft" gap left open by the 09-28
closing sequence: mine and harvest were green, place-from-inventory was
an engine gap, and *craft* had never existed).

## What was built

- **`PolisCraftAction`** (`src/Actions/Workstations/PolisCraftAction.cs`) —
  a proper `EntityActionBase`: finds the first grid recipe whose output
  matches the requested code in the world's live recipe table, matches it
  against the bot's own cargo slots, and calls the engine's own
  `ConsumeInput` so the game consumes inputs, produces output, and
  handles the result routing itself. No hand-rolled inventory math.
- **`craft <code>`** harness command (`poliscli craft plank-oak`) and the
  matching handler.
- **`GET /polis/recipes`** — the live recipe table out of the running
  world (12,995 grid recipes in 1.22.7): name, output code, quantity,
  shapeless flag, ingredients. Queryable by output substring / limit.
  This is what makes the recipe surface inspectable from outside the
  game — the 1.22 workbench blocks are gone, so the recipe *table* is
  the only crafting UI left.
- **R2 integration** — `craft` added to the job catalog
  (`r2/jobs.py`) and plan validation (`r2/plancheck.py`): a plan that
  wants to craft checks the live recipe table for the output and checks
  the projected inventory for the ingredients.
- **API probe** (`src/PolisApiProbe.cs`, opt-in via `POLIS_API_PROBE=1`) —
  the reflection dump that produced the 1.22.7 API facts below.

## The 1.22.7 API facts (measured, not guessed)

- Workbench-type blocks are **removed/disabled** in 1.22.7; crafting is
  pure grid recipes in `IWorldAccessor.GridRecipes` (12,995 of them).
- `GridRecipe.Matches(forPlayer, world, slots, gridWidth)` — the fourth
  argument is the grid **width** (3), not the slot count; slots are the
  ingredient source.
- **`EntityAgent` does not implement `IPlayer` in 1.22** (a cast yields
  null; the engine NPEs on the null). The action runs under the bot's
  *owner* player as the engine's actor; the cargo slots stay the
  ingredient source. A bot with an unresolvable owner falls back to the
  command-sending player.
- Item codes keep the `game:` namespace prefix in 1.22.7
  (`game:plank-oak`, `game:saw-copper`, `game:log-placed-oak-ud`). The
  wood variant names changed across versions (no `omok` in 1.22; the
  set is acacia/aged/baldcypress/birch/ebony/kapok/larch/maple/oak/
  pine/purpleheart/redwood/veryaged/walnut).
- Smelting is **not** a grid recipe — it is the industrial multiblock
  domain (bloomery etc.). Deferred; a furnace is out of scope for the
  pilot.

## Live verification (oracle-verified, not ok-flag)

World: the survival test world (playstyle survival — health *and* hunger
bars in the in-game view; the survival help hint on first entry). Bot
#2, all from the harness:

```
give  game:log-placed-oak-ud  4     -> "Gave 4x"
give  game:saw-copper         1     -> "Gave 1x"
craft plank-oak                             -> LastAction: ok
state:  RH log x3   LH saw x1   backpack slot0: plank-oak x12
```

The arithmetic is exact: 4 logs − 1 consumed = 3; the recipe output is
12 planks (`recipes/grid/plank.json`, shapeless, 1 log + 1 saw → 12
planks); the saw is **not** consumed (it is a tool). A second run on a
fresh inventory after a restart reproduced the same delta
(8 → 7 logs, +12 planks). The saw surviving makes the craft chain
compounding: one saw can produce indefinitely given logs.

## The startup stall, and the pilot launcher

The in-game (singleplayer) server suspends ticking when the client sits
on a full-screen screen around world entry (loading/intro; the server
log line is "Server ticking has been suspended", typically 60–95 s
after start). Episodes last 2–4 minutes and **self-resolve**, but
`Escape` (the game's own skip key) ends them in seconds. The survival/
creative help dialogs are *not* the cause (disabling them in
`clientsettings.json` did not change it); it is the entry sequence
itself.

**`scripts/vsgame-pilot-launch.sh`** automates the whole thing for
unattended pilot runs: starts the game service, polls the harness for
tick progress (`timeMs` on `/polis/status`), and sends `Escape` **only
while the tick is actually frozen** (20 s grace, one press per frozen
episode), reporting when the tick runs again. Verified live: one boot
resumed on its own (0 unblocks), the next was unblocked by the script
after a single Escape, both with the server confirming
"Server ticking has been resumed".

Two small traps found while instrumenting this:

- The CLI's JSON formatter **redacts long strings** (`<1294968 chars>`)
  — screenshot base64 must be read from the raw harness endpoint
  (`GET /polis/screenshot?playerUid=…`), not through the CLI.
- `poli…y` has a **positional** bot id on `state` (and `--host` is a
  per-subcommand option, not global): `poliscli state 2 --host …`.

## Where this leaves the pilot

Mine (09-28), harvest/sow (09-28), place (09-29), build (3x3 hut, 09-29;
5x5 resolved in the sequencer this week) and now **craft** are all
live-verified. The survival pilot is ready to run: fresh world,
survival mode, the r2 live-mission orchestrator with the pilot goal
grammar, the launcher handling the startup stall, and operator-only-on-
failure as the safety boundary. Smelting (ore → ingot) is the one
known endogenous gap: it needs a multiblock, which is a build-plan
problem more than a crafting one — a follow-up, not a pilot blocker.
