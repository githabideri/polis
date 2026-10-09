# Early-Game Progression Test

Date: 2026-10-10 (design; implementation pending)
Status: proposal — stage table + oracle list, no code yet.

## What this is

A staged, gate-driven test that runs the exact capability chain the game
demands of a bare-spawn survivor, **endogenously** (no harness gives of
tools/materials except the one sanctioned initial food supply), and
verifies every stage by **world state**, not by action logs. It serves
three masters at once:

1. **Executor capability test** — every job type the chain needs
   (mine, chop, craft, knap, fire, smelt, sow, build) is exercised on
   real terrain, fail-fast with honest attribution.
2. **Agent benchmark** — the same ladder ordered by the settlement
   agent (the 27B) under `free` autonomy measures what the model can
   plan from a goal like "survive and settle"; failures split cleanly
   into *model* (wrong goal/verb order) vs *infrastructure* (job
   failed) because each stage's gate is deterministic.
3. **Pilot content** — the survival pilot's "first 7 days" IS this
   ladder; a fully passing run on a fresh world is the pilot's
   definition of done.

## The chain the game actually requires (sources)

The official wiki's first-day guide fixes the canonical order
([Survival Guide - Your first day](https://wiki.vintagestory.at/Survival_Guide_-_Your_first_day)):

1. Mark the spawn (waypoint) — "It's a good idea to set a marker for
   this spawn point when a player first appears in the world."
2. **Stone Age first**: "Find Flint or loose knappable stones … an
   axe and a knife are highly recommended as first tools"; stone head
   + stick in the crafting grid = the finished tool.
3. **Portable containers**: "collect 10 of them [reeds] to craft a
   hand basket … Each hand basket adds 3 inventory slots."
4. **Food**: wild crops (harvest young, keep the seeds), mushrooms
   (handbook check for poison), berry bushes ("harvested without
   tools … cuttings … replanted anywhere"), cattail roots (knife;
   eating the root kills the plant), animals (meat must be "cooked in
   a fire pit before eating").
5. **Clay early**: "a required resource to progress through the ages";
   early clay = "cheap stationary storage options and your first
   means to preserve food"; items "must be fired in a Pit kiln".
6. **Light/cooking**: firepit = dry grass + 4 firewood + firestarter;
   "rain will extinguish any uncovered fires … build a simple roof
   over any firepits"; a torch in the off-hand raises satiety drain.
7. **Combat**: spears (knapped head + stick), clubs, improvised
   grass/firewood armor, crude shield.
8. **Shelter before sunset** — "temporal monsters will start to
   spawn"; early materials: dry-grass bed, hay/cob, "soil … packed
   dirt, rammed earth, or daub".
9. **Stationary storage** (clay-based) to finish day one.

A day-by-day player walkthrough (Bisect Hosting,
[Day 1](https://www.bisecthosting.com/blog/vintage-story-beginners-guide-day-1-tools-food))
confirms the order with concrete recipes and adds the survival rule:
"a two-block-high wall surrounding your character should suffice" and
"Don't Move! … don't move from your small campsite when night falls."

Community tips worth encoding (r/VintageStory,
[tips](https://www.reddit.com/r/VintageStory/comments/1602n7b/any_tips_before_i_start_playing/)):
"Start crops early if you can, as soon as you have at least medium
fertility soil … a simple pit trap around your farm solves a lot."

The age transition is gated and quantified (wiki,
[Copper](https://wiki.vintagestory.at/Copper)): copper is "the first
metal available to players", smelting point 1084 °C, "Requires
Container: Yes … Output: Ingot mold", and "players will need to obtain
40 copper nuggets in total to properly enter the Copper Age".

## The ladder

Each stage: entry condition (oracle), action chain, **exit oracle
(world-state check)**, and the capability it certifies. Oracles use
the existing patterns: fresh scans (12.6), the vitals sampler,
container-list, the zone registry.

| # | Stage | Chain (jobs) | Exit oracle (world state) | Certifies |
|---|-------|-------------|---------------------------|-----------|
| P0 | Orientation | register zone `base` at spawn | zone registered; body inside it | zone system |
| P1 | Stone tools | find flint (query), `knap` surface + head, craft knife & axe on sticks | inventory: flint knife + axe (equipped) | **knap job (new)**, craft |
| P2 | Capacity | chop reeds, craft 2× hand basket | backpack slot count +6 | chop, craft |
| P3 | Forage-eat | forage berries/mushrooms, eat | vitals: satiety ≥ threshold over N ticks, zero starvations | forage controller |
| P4 | Fire & cooking | chop tree → firewood → firepit (crucible-fire), hunt/kill, `insert` + fuel, cook, `take` | inventory: cooked meat; firepit block lit | crucible chain |
| P5 | Shelter | build hut-flat (walls + roof) at base; firepit under roof | 54/54 present (or plan-defined %), door open, firepit cell has cover above | build executor + reach-aware stand search |
| P6 | Clay & storage | find clay (scan), clayform, kiln-fire, stationary storage + cooking pot in `storage1` | container-list: registered pot/storage; fired item in inventory | **clayform + kiln (new)** |
| P7 | Crops | wild crop → seeds; till farmland (soil fertility), sow rye, grow (real clock or `ripen` flagged as test-aid), harvest | harvest measured; food stored in P6 storage | farmland chain, storage |
| P8 | Copper (age) | find copper ore, smelt in crucible (1084 °C), 40 nuggets, cast ingots in mold | inventory: copper ingots ≥ plan; (age gate if the mod exposes one) | metallurgy chain, crucible at high temp |

P4's "hunt/kill" can be replaced by forage-only (berries + cattail
roots) for the minimal ladder; hunting stays a variant (the bot's
combat path is untested ground).

## Two levels of the same ladder

- **Level 1 (infrastructure):** the chain runs as a deterministic
  campaign (`--no-planner`), one stage per mission or one long
  campaign with per-stage gates. Failure = a job/oracle defect. This
  is the regression suite.
- **Level 2 (agent):** the agent receives the whole goal in one
  sentence ("settle here and be able to survive winters") and must
  compile, order and monitor the stages itself, using `state`/`query`
  to check gates between missions. Failure splits: the stage gate
  says which step broke, the transcript says whether the *model*
  miscompiled the goal (infrastructure vs model attribution).

## What exists vs what is missing

Already in the job system: mine, harvest (incl. `ripen` test-aid),
sow, place, build/build_plan (with the reach-aware stand search,
2026-10-10), craft, chop, pickup, forage (mod-side interrupt + job),
crucible-fire/insert/fuel/take/pour, container-register/list, zone
registry, the query tool, the vitals sampler (1 Hz) and the
cinematic camera for gate photos.

New for the ladder (implementation order = dependency order):

1. **knap** — place a knapping surface (flint), target it with a
   second stone, knock out the orange boxes, take the head. The
   1.22 knapping UI needs a harness command pair (surface + strike)
   or a guided action sequence.
2. **clayform + kiln-fire** — shape a clayform, place it, fire in a
   pit kiln (a second crucible-family container with a fuel/heat
   loop and a "ready" oracle).
3. **copper smelt at temperature** — the crucible chain exists; the
   1084 °C smelt point means the fuel/heat management needs a
   temperature oracle (not just "done").
4. **farmland tending** — till + sow exist; growth needs the real
   clock (or a flagged `ripen` aid, logged as such) and the harvest
   oracle.
5. **age-gate oracle** — if the mod exposes the age as a config/skill
   state, read it; if not, the 40-nugget/ingot inventory check IS the
   gate (documented as inventory-based, not engine-based).

## Measurement

- Per stage: wall time at the running FPS, attempts, rescues,
  measured quantities (the run JSON already carries all of it).
- The vitals CSV gives the satiety curve through the whole ladder —
  the food system's stress test in one plot (this is the pilot's
  primary reliability signal).
- Gate photos: one cinematic shot per stage, named
  `prog-P<n>-<stage>.png`, for the report.
- Attribution vocabulary stays the 13.2/12.6 split: engine verdict
  (execution) vs fresh-world check (oracle); a stage fails at its
  gate, never by drift.

## What this is NOT

- Not a player-experience test (no input latency, no UI comfort).
- Not a performance benchmark (FPS is a constant of the host, not a
  variable of the test).
- Not the deity/mana layer (that gates *player* powers, not the
  stone-age chain; it lands later and reads this ladder's evidence).
