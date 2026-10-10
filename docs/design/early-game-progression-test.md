# Early-Game Progression Test

Date: 2026-10-07 started; 2026-10-10 revised to the job-centric
proposal (user-approved the same day).
Status: build in progress. **Done: probe + J1 (2026-10-10)** — the knap job is
contract-verified (19-check pure suite) and live-verified end-to-end (the bot
chipped two surfaces into a knife blade and an axe head and crafted both
tools, 54 s, measured deltas). Engine facts measured along the way: the
knapping surface is CONSUMED on completion (one surface item per chip; the
executor re-places it before each chip), the completion marker is the block
go-ing to air (`CompleteKnapToBot`), and the output lands directly in the
bot's inventory. Open for the no-give P1 endogenous run: the surface item
has no recipe (creative/decorative) — its world source is still to be
settled (the flint side is solved: `looseflints` RightClickPickup).
Next: Oikistes integration (the 27B dispatches the `pots` chain), J5 tend + P7, the user runbook.

## The unit: one job = one world transformation, three proofs

Every job in the system carries the same contract (the crucible chain
and the craft job already follow it; this document extends it to the
rest):

- **preflight** — inputs checkable before the act (inputs in cargo,
  surface/form present, or a deterministic sub-step places it)
- **one actuation** — one harness command
- **measured oracle** — inventory delta / block scan / container
  state. Never the command's `ok=True` (documented to lie: phantom
  ok on `place`)
- **evidence line** — compact, lands in the run JSON

Three proofs per job, same oracle:

1. **Contract** (fast, isolated): fixture site + labeled-external
   supply (give/setblock, marked as scaffolding in the evidence) →
   job → assert oracle → run JSON. Pattern:
   `tests/contract/crucible-chain-test.py`, `forage-test.py`.
2. **Endogenous** (the real path): a mission chaining supply jobs
   (mine/forage) → this job; wall time measured; same oracle.
3. **Ladder** (regression): the job appears in a stage file; the
   runner's per-stage evidence is the proof.

## What already exists (individually verified)

| r2 job | harness command | oracle | evidence |
|--------|----------------|--------|----------|
| mine / chop / harvest / sow / pickup / place | mine, chop, harvest, harvestcrop, pick, place | inventory delta / block scan | run JSONs |
| build / build_plan | place-loop + stand search (reach-aware, c1b188f) | per-cell world scan + door-open | run JSON (cottage 30/55, 2026-10-10) |
| craft (grid) | craft <output> | inventory delta, engine GridRecipe, live-recipe precheck | run JSONs |
| forage | forage (mod-side interrupt) + eat | satiety (vitals sampler) | forage-test.py, pilot CSV |
| crucible-fire/insert/fuel/take/pour + wait | crucible-* | inventory delta (take/pour) | crucible-chain-test.py (live 10-07) |

Harness command surface already built (C#): `knap <x y z> <recipe>
[speed]`, `clayform <x y z> <recipe> [speed]`, `craft <output>`,
grind, press, butcher, seal, forge-heat, anvil-smith/state,
crucible-*, forage, vitals, zone/query.

## The new jobs (dependency order)

| # | job | wraps | oracle (world state) | unlocks |
|---|-----|-------|---------------------|---------|
| J1 | `knap` | `knap <pos> <recipe>`; sub-step places a knapping surface if absent; flint/loose-stone in cargo | delta: knife-blade-flint / axehead-flint / arrowhead-flint | P1 stone tools (keystone) | **done 2026-10-10** (contract + live; see Status) |
| J2 | `clayform` | `clayform <pos> <recipe>`; sub-step places the form block; clay-\<color\> in cargo | delta: `*-raw` item (output lands in a groundstorage the table converts into on completion; clear the target cell to air first - tufts block placement) | pots, molds, anvil |
| J3 | `kiln` | crucible-chain skeleton re-pointed at a firepit kiln (place raw → fuel → wait → take) | delta: fired item (cooking-pot, storage, mold) | P4 cooking, P6 storage |
| J4 | `smelt-copper` | crucible-copper chain + C# crucible-progress read (anvil-state pattern) so the wait ends on engine pace, not a tuned timer | delta: nuggets; 40 = the wiki's age-gate number | P8 the age transition |
| J5 | `tend` | poll farmland stage (query) → wait real clock → harvestcrop | delta: harvested grain | P7 crops |

## The ladder: data, not code

A `progression <stages-file>` mission type (the 13.11 pattern: a new
ladder is a new file). A stage is `{name, jobs:[...], exit_oracle,
evidence_shot}`. The runner, per stage:

preflight oracle → jobs → exit oracle (WORLD STATE: "cottage 55/55 +
door open", "40 copper nuggets") → fail-fast with attribution (which
job, which oracle, verbatim harness message) → one cinematic gate
photo.

- **Level 1** — `--no-planner`, deterministic: the regression suite.
  Re-runnable on a fresh world; per-stage wall time + the satiety
  curve (vitals CSV) are the measurements.
- **Level 2** — the same stage files, ordered by the agent from a
  goal ("settle here"). A failure at a stage oracle splits cleanly
  into *model* (wrong order/verb) vs *infrastructure* (job failed its
  oracle).

## The stages (from the sources, 2026-10-10)

Sources: official wiki *Survival Guide - Your first day* (canonical
order: mark spawn → knapping knife+axe → reed baskets → forage (wild
crops/seeds, mushrooms, berries, cattail) → clay early → firepit
(rain kills uncovered fires) → shelter before sunset → stationary
storage); Bisect Hosting day-1 (2-block dirt perimeter, "don't move
at night"); wiki Copper page (first metal, 1084 °C lore, requires
container, **40 nuggets = age gate**, tin bronze 88–92 %).

| stage | exit oracle | jobs |
|-------|-------------|------|
| P0 orientation | zone `base` registered, body inside it | zone |
| P1 stone tools | knife + axe in inventory (equipped) | mine flint, **knap**, craft (blade+stick) |
| P2 capacity | backpack slots +6 (2 hand baskets) | chop reeds, craft |
| P3 forage-eat | satiety ≥ threshold over N ticks, zero starvations | forage (existing, pilot-observed) |
| P4 fire & cooking | firepit lit; cooked meat in inventory | chop → firewood, firepit, hunt/forage, crucible/insert/fuel/take |
| P5 shelter | cottage 55/55 + door open (or plan-defined %) | mine dirt, build_plan (existing) |
| P6 clay & storage | registered storage + cooking pot in zone storage1 | mine clay, **clayform**, **kiln**, container-register |
| P7 crops | harvested grain stored | wild crop → seeds, till, sow, **tend**, harvest |
| P8 copper (age) | 40 nuggets / ingots in inventory | mine copper, **smelt-copper**, pour at mold |

## Build order (approved 2026-10-10)

1. **Probe** 1.22.7's live recipe tables (knapping outputs, clayform
   recipes, kiln behavior, crucible progress state) — read-only;
   parameters are live-world facts, never frozen (crucible-chain
   precedent). **Done 2026-10-10** (knapping table, clayform table,
   grid assembly, firepit block codes, ungraded ore; the knappingsurface
   endogenous source is the one gap).
2. J1 knap + contract test. **Done 2026-10-10** (knap-test.py; live run
   `flint-tools` chain: 2× knap → knife + axe in 54 s).
3. J2+J3 clayform + kiln (first cooked meal in a bot-made pot).
4. The ladder runner + first stages file (P3 and P5 first — two
   already-proven stages test the runner before new jobs depend on it).
5. J4 copper (with the C# progress read).
6. J5 tend + P7 (last — the slow-clock stage).

## What this is NOT

Not a player-experience test (no input latency, no UI comfort). Not a
performance benchmark (FPS is a host constant). Not the deity/mana
layer (that gates player powers, not the stone-age chain; it reads
this ladder's evidence later).
