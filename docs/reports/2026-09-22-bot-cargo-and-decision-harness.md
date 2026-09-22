# Bot cargo inventory, 1.22 loot routing, and the decision-loop harness

Date: 2026-09-22 · Environment: the game testbed (VS 1.22.7, world polis-testbed-pristine), openjev Laya 421M, Qwen3.8-27B (thinking off)

## 1. The bot inventory fix (mod change)

**Root cause.** In 1.22 `EntityBehaviorSeraphInventory` (VSSurvivalMod) became a
sub-class of `EntityBehaviorTexturedClothing` holding an **`InventoryGear`** —
an equipment/clothing inventory that rejects non-wearable items. The old
19-slot seraph layout (hands at [15]/[16], backpacks at [17]/[18]) no longer
exists. Every `give` failed with "inventory full or no valid slots" and mined
loot overflowed onto the ground ("collected 0/2, overflow: 1x …").

**Fix.** `EntityPolisBot` now owns a real cargo inventory:
`InventoryGeneric` with 16 generic slots — `[0]`=right hand, `[1]`=left hand,
`[2..15]`=grid (slots 2/3 are reported as "backpack0"/"backpack1"). All
mod-internal inventory access goes through one seam,
`PolisInventoryHelpers.BotCargo(agent)`; the 14 former
`GetBehavior<EntityBehaviorSeraphInventory>().Inventory` use sites
(harness, state dump, professions, mine, butcher, container put/take, clay,
knapping) were re-pointed. The seraph behavior stays for clothing rendering.
Cargo is not persisted to entity attributes: bots are ephemeral (respawned
per mission, repopulated by the harness).

Verified live: give/drop/select work on hands and grid; state now reports
`RightHand`/`LeftHand`/`Backpack` from the cargo.

## 2. 1.22 loot routing (why mines "succeeded" without collecting)

- `IBlockAccessor.BreakBlock` has **only an `IPlayer` overload**; the game's
  break path gives loot to the *player's* `InventoryManager`
  (`TryGiveItemstack`, ground fallback) — the harness drives breaks as the
  context player, so mined items vanished into the player's inventory.
- Fix: `PolisMineBlockAction.BreakBlockAsBot` breaks via
  `SetBlock(0, pos)` (air) and computes loot itself from
  `Block.GetDrops(world, pos, null, 1.0f)` — the virtual the game calls
  (rock blocks override it with per-clutter-type drops; the plain `Drops`
  field is empty for them) — inserting drops into the bot's cargo, spawning
  overflow on the ground for the existing autocollect.
- **Set-placed rocks yield no drops**: the clutter-type property comes from
  worldgen block entities; a `setblock`-placed `rock-granite`/
  `crackedrock-granite` has no type, so `GetDrops` is empty. Consequence:
  the mission's success criterion is **marker block removed** (verified by
  `scan`), not "item in backpack". Carrying drops is best-effort for
  blocks that do define drops.
- Tool gate confirmed live: cracked rocks need tier 2 — a bot without a
  pickaxe gets "Tool required: block needs tier 2".

## 3. Claims bypass (test world)

The harness' claim checks (`TryValidateBlockTarget`, place handler) reject
cells covered by claims other than the requesting player's — the test
world's claim rectangles are stored inside the binary chunk DB and are not
queryable. New env flag **`POLIS_SKIP_CLAIMS=1`** (set in
`/etc/vsgame.env`) disables all harness claim checks; off by default.

## 4. The decision loop as an optimization harness

`scripts/jev-loop-v4.py` is now a repeatable benchmark pass:

- **Two tiers**: policy proposes → Laya noul pre-filter (anchored
  yes/no) → `p >= tau` executes directly, else the 27B doubt-arbiter
  (thinking off, single-word 4-action answer, ~0.2 s) executes.
- **Phase-relative positive controls**: `--faults travel,mine` inject a
  known-wrong proposal on the first step of the named phase
  (skip-goal; tool-drop + mine).
- **Labeled set**: every step records (state text, proposal, oracle action,
  reflex p, path, judge answer, executed, exec outcome) — the raw material
  for re-deriving `tau` when the model or wording changes (calibration
  protocol: llmlab `docs/decision-classifiers.md`).
- **Mission outcome**: marker removed (scan-verified) + bot at base;
  per-run completion, steps-to-complete, wall time; `--repeat N`.

### Five passes, what each taught

| pass | tau | mission | reflex share | judge false-waits | lesson |
|---|---|---|---|---|---|
| 1 (index faults) | 0.6 | complete in 3 steps, 14 s | 5/8 | 0 | baseline works end-to-end |
| 2 (phase faults) | 0.6 | stuck | 1/8 | 0 | judge oracle 7/7 but a tool fault let mine through at p=0.62; drop-detection bug in the script (hands vs grid) |
| 3 (hands fix) | 0.6 | stuck | 0/16 | 12 | travel fault caught by judge; **judge latches to `wait` after a visible failure and never recovers** — the v3 stall, now at the arbiter tier |
| 4 (judge prompt: tool rule + recovery clause) | 0.6 | stuck | 0/16 | 10 | Laya p's drifted down with the state-text change (0.35–0.40) → *all* steps escalated; judge still stalls — **failure evidence sticks**; the stall is robust to prompt repair |
| 5 (re-derived tau 0.35) | 0.35 | **complete 2/2** (5 steps, 68 s) | 6/10 | 0 | re-deriving the threshold restored the tiers; faults self-heal (mine fails without tool → repair → next mine succeeds) |

### Findings for the method record

1. **The doubt-arbiter stall is a real, reproducible failure mode of a
   thinking-off 27B placed per-step**: once a step fails, the judge's
   conservative prior dominates and it waits indefinitely, even after the
   failure is repaired. Prompt-level recovery clauses did not fix it.
   Candidates: (a) state-level "failure cleared" signal after repair,
   (b) a max-stall policy (N identical waits → force the oracle action),
   (c) a diff-based judge input ("what changed since last step").
2. **Thresholds drift with the state text.** Rewording the state moved Laya's
   p-band from ~0.6 to ~0.35–0.48; the tiers only work at the re-derived tau.
   Per the calibration protocol this is expected — the threshold is a
   property of (model, question, state format), re-derived on the labeled
   set, never guessed.
3. **At 421M the correct/faulty p-bands overlap** (correct 0.35–0.48, faulty
   0.32–0.43 across passes) — no single threshold separates the two
   populations. The tiers are complementary, not separable: the cheap tier
   carries the common case, the arbiter adds (imperfect) conservatism where
   the reflex is unsure. This is the polis row of the regime map's
   concrete-observable case with its measured limits.

## 5. Ops

- `/etc/vsgame.env`: `POLIS_SKIP_CLAIMS=1` (test-world claim bypass).
- Build ritual unchanged: `set -a && source .env && set +a && rm -rf obj bin
  && dotnet build -c Release && ./build.sh --deploy`; restart = stop, wait
  for port 8585 to clear, start (TIME_WAIT).
- Bot ids increment monotonically; fresh respawn per harness run.

## Next

- Doubt-arbiter stall: implement (a)/(b)/(c) above and re-run the harness
  (a sixth pass with the same labeled protocol makes the comparison clean).
- Harvest pipeline: crop blocks have the same setblock-without-BE-state
  problem; the mine-action loot pattern is the template.
- Send the labeled set + question JSON to the openjev/llmlab side for the
  use-case catalog entry and the decision-classifiers page (their request,
  2026-09-22).

## 6. Pass 6: the stall fix works (2026-09-22, second session)

Two changes, both deterministic and testable:

1. **Diff-based state line** — every step's state now carries
   `since_last_step:` (marker removed / pickaxe dropped or re-given /
   phase change / no change). The judge sees *changes*, not just
   accumulated failure history.
2. **Max-stall safety valve** — after two consecutive executed `wait`s,
   control returns to the deterministic policy (`path=stall-bypass`). The
   arbiter gets exactly two says; an infinite wait loop is structurally
   impossible.

Result (same protocol as pass 5: tau 0.35, faults travel+mine, 2 runs):
mission **2/2**, 5 steps, **25 s** each (pass 5: 68 s — its time went to a
45 s doomed mine attempt), **4/4 faults handled by the judge with `wait`**
(the diff line made the judge see "pickaxe dropped" and hold the mine; the
repair then let the reflex mine cleanly on the next step), **0
stall-bypasses needed**, 0 false-waits. Suggested tau from the growing
labeled set: **0.358 ≈ the applied 0.35 — the threshold has converged**.

Measurement nuance recorded for the method page: `judge_oracle_match`
reports 0/4 here, but the oracle is *phase-based* while the judge was
*fault-aware* — all four waits were the correct action given the injected
faults (that is what `faults_corrected` measures). A per-step oracle that
knows about active faults is the right ground truth for fault steps; the
phase oracle only works on clean steps.

## 7. Where this leaves the loop

- Clean steps: the cheap reflex carries them (6/10 at the re-derived tau);
  the 27B is consulted only on the unsure minority (~0.2 s per call).
- Fault steps: the 27B now handles both fault classes correctly (conservative
  wait), and the loop self-heals (repair → next step succeeds) — the
  positive controls pass.
- Known residual: the judge is conservative *by prior*; with more labeled
  data the (question, state-format) pair can be re-derived again, and the
  fine-tune path in the method doc is the long-term route from
  "conservative arbiter" to "fast pre-filter".

## 8. Harvest pipeline + second mission (same day, second session)

### 8.1 The 1.22 crop system (decompiled/asset survey)

- Crops are one block code **`crop`** with variant groups `type`
  (carrot, cabbage, wheat, rye, onion, … 17 types) and `stage` (1..7);
  mature = stage 7 (`crop-carrot-7`). Growth is time-based (carrot:
  ~1.03 months over 7 stages, nutrient-gated via the farmland BE).
- Farmland: code **`farmland`**, variants `state` (dry/moist) x
  `fertility` (verylow..high), BE `BlockEntityFarmland` (soil
  nutrition); a crop sits in the cell **above** the farmland.
- Drops are declared in the block JSON `dropsByType`: mature carrot =
  ~1x `seeds-carrot` + ~11x `vegetable-carrot` (stage 6: ~3 carrots).
  `BlockCrop.GetDrops` honors this - so the same break-as-bot pattern
  as the mine action works for harvest.

### 8.2 The harvest action fix (mod)

`PolisHarvestCropAction` (maturity-gated via `farmland.HasRipeCrop()`)
used the player-only `BreakBlock` - the same 1.22 loot-routing bug as
mine. It now breaks the crop as the bot: `GetDrops` -> bot cargo,
overflow to ground, `SetBlock(0)`. `POLIS_SKIP_CLAIMS` bypass added to
its claims check. Live-verified: bot harvested `crop-carrot-7` and
ended up carrying **11x vegetable-carrot + 1x seeds-carrot** in its own
inventory.

### 8.3 The harness is now mission-parameterized

`jev-loop-v4.py --mission {mine,harvest}`. The harvest mission:
fixture = farmland + mature crop 8 blocks east; phases travel ->
harvest -> return; **success = the bot carries a harvested item AND is
back at base** - the agent *produced and carried a real in-game item*.
The `harvest_target` execution moves the bot to the ground-level cell
next to the crop (harvest range 4.5) and then harvests.

Measured (two 2-run passes, faults = skip-goal at travel + harvest):
mission **2/2 complete in 2 steps / 13 s per run**, 0 false-waits, 0
stalls, **2/2 faults handled - by the 27B jumping straight to
`harvest_target`** (its execution absorbs the missing travel step).
Laya p's on the new question are remarkably stable: skip-goal ~0.21,
correct ~0.41-0.47 (noul is effectively deterministic at this
temperature). Suggested tau 0.408 re-derives cleanly.

### 8.4 Findings for the method record

1. **The oracle measures fidelity, not optimality.** The judge's
   `harvest_target` on a `travel`-phase skip-fault is *better* than the
   oracle (`goto_target`): fewer steps, same goal. The labeled set
   should record "better-than-oracle" as its own class - an
   oracle-match metric alone would score the judge's best answer as
   wrong.
2. **Mission-level success is the right top metric.** Both mine (marker
   removed) and harvest (item carried home) missions complete under
   fault injection, with self-repair where the tiers let a fault
   through. The loop is now a *useful* game process, not just a
   decision benchmark: it moves, works, and brings produce home.
3. **p-band overlap is mission- and wording-specific.** Mine: correct
   0.46-0.79 vs faulty 0.36-0.47 at the re-derived tau (overlapping -
   faults self-repair; at high tau the judge tier catches 4/4).
   Harvest: clean separation (0.21 vs 0.41+) - the 4-action set with
   the crop fact gives the small model something concrete to latch on.
   Question design (which facts are in the state text, how many
   actions) is a first-class lever on separability.
4. **File-rewrite gotcha (harness ops)**: a rewritten script's
   `if __name__ == "__main__":` guard lost its trailing `__` in
   transit - valid Python that silently never runs `main()` (exit 0,
   no output). Verify the guard after any whole-file rewrite.

### 8.5 Openjev catalog

Two saved use cases: `polis-action-noul` (mine question) and
`polis-harvest-noul` (harvest question, measured skip-goal p~0.22 on
the canonical state). Labeled sets: `data/labeled-set-2026-09-22-*.json`
(pass 5, pass 6, harvest 1+2, mine regression) - the calibration
corpus for the llmlab decision-classifiers page.
