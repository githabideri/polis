# Bot cargo inventory, 1.22 loot routing, and the decision-loop harness

Date: 2026-09-22 · Environment: the game container (VS 1.22.7, world polis-testbed-pristine), openjev Laya 421M, Qwen3.8-27B (thinking off)

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

## 9. Movement & world-state findings (same day)

### 9.1 The goto freeze: bot accumulation

Mid-session, every `goto` stopped producing movement or a result
(no LastAction, no exception in the server logs) - for reloaded and
freshly spawned bots alike, across all three navigation modes
(PolisAStar, VS A*, straight line). The freeze **reproduced across a
full game restart**, which ruled out in-process accumulation.

Root cause: **persisted idle-bot accumulation.** Every harness run
spawns a bot and never despawns the previous ones; the bot entity
class is `StoreWithChunk = true`, so each despawn-less run wrote
another idle bot into the world. By the time the freeze appeared the
world carried **19 idle persisted bots**. Despawning all of them
immediately restored goto (A* and straight line, all directions); the
decision-loop missions ran green again right after (harvest 1/1, 2
steps, 13 s).

Exact micro-mechanism not yet identified (suspect: a persisted bot
holding an interrupted goto activity wedging the
`wppathTraverser` job queue after reload). The operational fix is in
the harness: `run_once` now **sweeps all persisted bots before each
run** (`Polis.sweep_bots`) - the world stays at ~1 bot and the
harness is self-cleaning.

### 9.2 Baselines measured while diagnosing

- The client renders at a steady **~1.5 FPS** in this headless
  iGPU/Xvnc setup - that is the *normal* state (constant since world
  load, including all the successful mission runs). The server clock
  still runs near real time (a full in-game day ~ 10 real minutes).
  Mission wall-times above are at this rate.
- `setblock` does not accept `0` for air ("Unknown block: 0"); the
  code **`air`** works and is the fixture-clearing primitive.
- **Set-placed crops do not grow**: a `crop-carrot-1` on a set-placed
  `farmland` stayed at stage 1 for ~7 in-game days (the farmland BE
  immediately flips to `farmland-dry-verylow` and the crop's
  nutrient-gated growth rate stays ~0). Set-placed mature crops
  (stage 7) are the right fixture for the harvest mission; real
  growth would need worldgen farmland or an explicit nutrient state.
- The goto arrival **snap** (the old vspolis overshoot fix) is intact:
  after arrival the bot sits at the exact requested cell center.

## 10. Lighting control for visual proof (photo-run pattern)

Goal: a 6-frame elevated-angle sequence proving the harvest cycle (crop present -> bot
harvests -> crop gone with drops -> bot returns with loot), in stable daylight.

Findings:

1. **Server-side `Calendar.Timelapse` does not change rendered light.** The property
   is in *days* (the cinematic `/timelapse <speed> <days>` feature) and the client
   overwrites it every frame from its own local value (`GameWorldCalendar.Timelapse =
   timelapsedCurrent` in `MainRenderLoop`). Setting it from the server (a harness
   `timelapse` command tried both raw-hour and day-fraction values) left the scene
   unchanged; the command was removed again after the finding.
2. **The working pattern (proven, viz8 run):** temporarily `settime 50`, poll `time`
   until `fullHour` enters a chosen window (10-15h), then `settime 1` and shoot.
   Full wait-to-shoot: ~3.5 real minutes. At the 2x effective speed of this world
   (unknown second +60 modifier, see wedge report), a 3-minute shoot at `settime 1`
   drifts ~5 in-game hours - enough to stay in daylight from a 10:00 start.
3. **Elevated cameras (y=5-6) beat ground-level ones here**: the mine-fixture
   geometry (2-high stone walls) repeatedly swallowed y=4 observers; elevated
   positions are immune and give a readable wide shot of the whole fixture.
4. **VS twilight/night skies are dramatic** (flat red gradient at dusk, star field
   at night) - a shot that "looks wrong" is usually just night, not corruption.
   Verify with the `time` command before blaming a broken world.

Frames (this run, bot #98, world time ~10:00-13:00):

- `docs/proofs/2026-09-22-harvest/viz8-01-before-story.png` - wide scene, crop visible
- `viz8-02-before-cropclose.png` - crop close-up: green crop bush with carrot tops on the farmland
- `viz8-04-at-crop.png` - bot at the crop (crop still present)
- `viz8-05-after-crop-gone.png` - same camera, crop gone, dropped carrots at the spot
- `viz8-06-return-mid.png` - post-harvest scene
- `viz8-07-at-base-carrying.png` - bot back at base (carrots + seed in inventory, see run log)

## 11. First model A/B: Laya is a mine-specialist (2026-09-22 evening)

The A/B harness (`ab-runner.py`, 8 labeled sets merged into one 41-row corpus:
27 mine + 14 harvest, each row a choice question with the observed action as
oracle) produced its first completed model run: **Laya 421M**.

| | top-1 | mean p_oracle |
|---|---|---|
| mine (27 rows) | **63.0%** | 0.386 |
| harvest (14 rows) | **0.0%** | 0.238 |
| overall (41) | 41.5% | 0.335 |

Brier 0.641 (poorly calibrated); confidence: correct 0.481 vs wrong 0.378 —
a gap exists but the bands overlap, consistent with pass-5 findings. Latency
10.4 s/question (429 s wall for 41 rows) on the 4-core CPU box — two orders of
magnitude above the live loop's 1–2 s decision cadence.

Two independent, both disqualifying for the live-loop role:

1. **Domain shift, not just error.** Laya was trained in our loop on
   mine-format state text; it has never seen harvest-format states. 0/14 is
   the expected result for a 421M model outside its training distribution,
   and 63% inside it. One classifier per state schema — or training on the
   merged corpus — is what a general-purpose Jev needs.
2. **Latency.** Even where it is right, 10 s/decision on small-CPU hardware
   puts Laya out of the live loop. Its honest role stays the one v3 measured:
   a conservative off-line/low-rate safety net, not the per-step decider.

**Hosting note (sanitized).** The 2B (Decider, gated-delta-net architecture)
and 4B (Qwen3.5-4B as the SemIf base) models do not fit the 4-core/4G box:
bf16 weights alone exceed its memory cap, and Decider's GDR kernels are
triton-only (GPU). They run on the 2x24G box instead, CPU bf16 with 64G RAM;
for Decider the `fla` import is suppressed so transformers takes its
pure-torch reference GDR path. Same corpus, same runner, same metrics — the
accuracy comparison stays valid; latency is recorded per box, which is the
deployment-relevant number anyway.

Results land here as `data/ab-<model>-2026-09-22.json` (plus per-row
`*.rows.json` sidecars with full probability vectors) as each run completes.

## 12. Decider 2B vs SemIf 4B on the same 41-row corpus (2026-09-24)

The two candidates the 2026-09-20 "Open Jev" analysis picked — **Decider 2B**
(`Mapika/decider-2b`, gated-delta-net 2B) and **SemIf 4B** (`Qwen/Qwen3.5-4B`
as a frozen base with a letter-slot logit readout, `TheoLeeCJ/SemIf`) — were
run on the identical 41-row merged corpus (27 mine + 14 harvest, §11) as
choice questions over the mission action set.

**Hosting.** The 2026-09-22/23 attempt on the 27B box (2x3090 box) never produced
results: HF weight downloads stalled all night, and the host was reinstalled
2026-09-23 (the toolchain was recovered from the old rpool, imported
read-only as `oldrpool` on the 5600X host). The runs were re-homed on **the CPU batch box
"jevab" (, 4-core i5-8500T, 16 G after the 2026-09-24 bump — the 4 G
cgroup was the original disqualifier)** with weights on the host's shared
model store `/models/jevab/`. the 27B box stays production vLLM; bench work no
longer sits on a prod inference box. Both models ran CPU bf16 on the
transformers **pure-torch reference** gated-delta-net path (no
`causal_conv1d`/`flash-linear-attention` kernels installed) — so the latency
numbers below are reference-path numbers, not deployment numbers. Harness,
runner and environment: `scripts/jevab/` (committed 2026-09-24; the
durability bug of the 324 attempt — toolchain only on an ephemeral CT — is
fixed by keeping it in the repo).

**Results** (`data/ab-decider-2026-09-24.json`, `data/ab-semif-2026-09-24.json`,
per-row `*.rows.json` sidecars):

| model | top-1 | p(oracle) mean | Brier | conf. correct | conf. wrong | p(oracle)>0.5: correct / wrong | wall (4C) |
|---|---|---|---|---|---|---|---|
| Laya 421M (09-22) | 0.415 | 0.335 | 0.641 | 0.517 | 0.341 | 25/27 · 0/14 | 429 s |
| **Decider 2B** | **0.707** | **0.655** | **0.426** | **0.870** | **0.136** | **27/29 · 0/12** | 762 s |
| SemIf 4B | 0.463 | **0.000** | **1.000** | 0.000 | 0.000 | 0/19 · 0/22 | 1909 s |

By mission (Decider): mine top-1 0.815 (p_or 0.712), harvest 0.500 (p_or 0.547)
— vs Laya's 0.630 / 0.000.

**Reading.**

1. **Decider 2B fixes the p-band overlap problem.** That overlap (Laya:
   confident on both correct and wrong answers, §11 and the doubt-arbiter
   analysis) was what disqualified the 421M reflex for the
   concrete-observable regime. Decider separates cleanly: p(oracle) > 0.5 on
   27/29 correct rows and **0/12** wrong rows; mean p(oracle) 0.870 correct
   vs 0.136 wrong. Its remaining 12 errors are not noise — they are **one
   systematic bias**: `goto_base` chosen where the oracle is `goto_target`
   (travel-phase rows, p(oracle) ≈ 0.13 throughout). A single fixable habit
   (base-preference in the travel phase), the kind of thing a prompt/label
   tweak or a small fine-tune targets — not a capacity wall.
2. **Harvest sensitivity survived** (0% → 50%), at roughly the same level as
   the mine improvement — the 2B generalizes across the two state schemas,
   which a 421M fine-tune could not.
3. **SemIf 4B is not a measurement.** p(oracle) = exactly 0.000 on all 41
   rows (Brier 1.0, all probability mass collapsed onto a single
   argmax action, `goto_target`, even on the 27 mine rows the small models
   handle). The letter-slot readout produced a degenerate distribution on
   this stack — most plausibly a mismatch between the readout and this
   model/tokenizer build (or bf16-CPU collapse of the reference
   gated-delta-net path), not "the 4B is bad". We **cannot claim the 4B is
   worse than the 2B** on this evidence. Harness follow-up: pin the
   transformers version to the SemIf development era, verify the
   letter-slot mapping against Qwen3.5's tokenizer, and run one fp32 probe
   before re-judging.
4. **Latency is the deployment question, not the accuracy question.**
   Reference-path CPU: Decider 18.4 s/question on the 4-core i5-8500T (the
   09-22 handoff's "10.4 s" Laya figure was the same story — choice-type
   questions, small CPU; the live loop's noul questions run ~1.1 s on the
   2-core openjev box). For a per-step reflex the 2B needs the fast kernels
   (`fla`/`causal_conv1d`) on a GPU or a quantized GGUF on CPU; that
   latency measurement is the next step (the 12 GB 3060, campaign handoff) before
   anyone calls the 2B "the Jev".

**Verdict (accuracy-only, 41 rows):** Decider 2B is the Jev candidate —
clearly better than Laya 421M on every axis that mattered, with its residual
error concentrated in one systematic direction. SemIf 4B: verdict withheld
(harness, not model). Caveats carried forward: oracle labels are coarse by
design ("better-than-oracle" rows exist), this measures choice-type
questions only (the live noul gate is a different question type), and all
latency here is CPU-reference.

## 13. Quantized GGUF readout: what 8-bit costs, what 4-bit breaks (2026-09-24, second session)

The bf16 A/B in §12 was torch-on-CPU: 18.4 s/row for the 2B — fine for a 41-row
batch, useless for a per-step reflex. The Decider authors ship an FP8 production
path and claim quantization "changes accuracy and calibration by less than the
evaluation noise" (their B300 numbers: eager 18.9 ms, CUDA-graphed 3.2 ms p50).
This session measures that claim on our hardware with our corpus, and makes the
first *valid* 4B measurement.

**Method.** Decider 2B safetensors → GGUF with llama.cpp main (2026-09-24):
`Q8_0` (2.0 GB, near-lossless reference) and `Q4_K_M` (1.27 GB). One conversion
gotcha: the converter assumes Qwen3.5 checkpoints carry MTP draft tensors and
writes 25 blocks even when the file has 24 layers and none — Decider's
checkpoint (fine-tuned from the 2B base) has no MTP tensors, so the conversion
needs `--no-mtp`. Readout runs in-process through the C library (the server's
HTTP logprob path is post-sampling in this version, unusable for the pre-softmax
letter logits): identical prompt construction to the torch path
(`decider.prompt.build`, state_first, same slots), full-vocab logit row at the
last prompt position, `softmax(logits/1.3)` over the ≤16 letter tokens.
Tokenization verified token-for-token against the reference tokenizer
(0 mismatches across all rows). SemIf 4B ran through its own `llamacpp_backend`
on the unsloth `UD-Q4_K_XL` GGUF (2.9 GB), T=1 native readout. 4 threads,
i5-8500T (the CPU batch box, ).

**Decider 2B, same 41 rows:**

| weights | top-1 | mean p(oracle) | Brier | conf right/wrong | ms/row |
|---|---|---|---|---|---|
| bf16 torch (§12, reference) | 0.7073 | 0.6554 | 0.4262 | 0.870 / 0.136 | 18 390 |
| Q8_0 (2.0 GB) | **0.7073** | 0.6576 | 0.4199 | 0.872 / **0.746** | 3 566 |
| Q4_K_M (1.27 GB) | 0.5366 | 0.5449 | 0.5804 | 0.900 / 0.627 | 4 077 |

- **Q8_0 is numerically indistinguishable from bf16**: Δtop-1 = 0,
  Δp(oracle) = +0.002, ΔBrier = −0.006, while running 5.2× faster. The
  authors' "within evaluation noise" claim holds on CPU at 8-bit. One real
  side effect: on the 12 systematically-wrong rows (§12's `goto_base` travel
  bias) Q8 makes the *wrong* choice confidently (0.746) where bf16 was flat
  (0.136). Top-1 and Brier are untouched, so any threshold-on-p(oracle)
  decision is unaffected — but "model confidence in its choice" is not a
  stable signal across quantizations.
- **Q4_K_M degrades this readout**: top-1 −17 pp (mine 0.81 → 0.56),
  p(oracle) 0.655 → 0.545, Brier 0.43 → 0.58. The letter-logit contrast this
  use case depends on is more quantization-sensitive than text generation
  (where 4-bit is fine). **8-bit is the quantization floor; 4-bit is ruled
  out** for the Decider readout (matches the authors' FP8-only production
  choice).
- 4-bit also didn't help latency (4.1 vs 3.6 s/row) — no reason to take the
  accuracy hit even if it had.

**SemIf 4B, first valid measurement.** The §12 bf16-torch run was degenerate
(p(oracle) = 0.000, Brier 1.0) — that turned out to be an artifact of that
specific runtime path (bf16 gated-delta-net on CPU), not the model. The
llama.cpp GGUF path (fp32-accumulated) produces a healthy readout:
**allowed_token_mass 0.993** (99.3 % of the vocabulary softmax mass lands on
the four letter answer slots — the frozen 4B genuinely answers in-slot),
p(oracle) 0.298, conf right 0.544 vs wrong 0.535. The judgment itself is weak:
top-1 **0.463** (chance = 0.25; Decider 2B fine-tuned = 0.707), p(oracle) 0.298
vs 0.658. The §12 conclusion stands, now with the 4B leg actually measured:
**the 2B task-tuned model beats the 2×-larger frozen base** on this readout,
exactly the Jev premise (small tuned model + narrow question beats big
untuned one). Latency: 12.2 s/row on 4C — the 4B is not a reflex candidate
on this hardware anyway.

**Latency verdict (4C, i5-8500T).** Q8_0 2B: 3.6 s/row (5.2× faster than
bf16-torch) — still short of a per-step reflex, but within reach of the
next tier on the deployment menu (a 5600X 6C/12T box should roughly halve
again; the 3060/FP8 path should be 10–30 ms). The CPU-4C box remains the
reference/measurement machine; the deployment box is still an open decision
(§12's menu stands: 4C → 12T → 3060).

**Artifacts** (`data/`): `ab-decider-q8-2026-09-24.json{,.rows.json}`,
`ab-decider-q4-2026-09-24.json{,.rows.json}` (gguf-runner summaries),
`semif4b-q4.jsonl` (cli output) + `semif4b-q4-summary.json{,.rows,.extra}.json`
(semif-post). Toolchain: `scripts/jevab/gguf-runner.py`,
`scripts/jevab/semif-post.py` (committed with the A/B toolchain).

## 14. Deployment: the Decider on the the 12 GB 3060 (2026-09-25) — the reflex is real

**Placement decision (owner):** the Decider runs on the **the 12 GB 3060** —
the llama-mux card of the Freistadt GPU server. The 3090 pair is explicitly out
(it is the production 27B vLLM TP2), llama-backup's 3060 is the box the user
does not want touched, and the 5600X 12T would only buy another ~2× over the
measured CPU number — the 3060 is the only menu entry that actually hits the
reflex target. (The earlier "the 3060 host = Pascal cards, excluded" note was wrong:
those cards belong to the pascal VM; the 3060 host's own GPU is the 3060.)

**Wiring.** `decider-2b-Q8_0.gguf` (2.01 GB) on the card's shared model store;
a no-MTP section (the fine-tune has no MTP draft — the preset's global MTP
settings are overridden) + a mux entry as the third model on the card, sibling
of the 35B on the mainline router. The mux's `ensure_loaded` was extended (v2.5)
to evict *same-port* siblings (35B ↔ Decider; together they don't fit the 12 GB
card): loading one evicts the other, load ≈ 6 s, evict ≈ 4 s. The card is in
the inference hub (`hub_model_*{server="the 3060 host",model="qwen35-decider-2b"}` —
real engine metrics, no synthesis), so Prometheus/Grafana pick it up without
new scrape targets. It is **exclusive with the 35B**: whatever is resident,
the other's next request pays the ~10–60 s switch. The Decider is the resident
model right now (OpenClaw/Dolly's 35B must be re-loaded from the hub).

**The HTTP readout protocol (the non-obvious part).** The 925e1179
llama-server's OAI `top_logprobs` body key only feeds the *chat* path; on
`/v1/completions` the raw **`n_probs`** body key must be sent. With
`logprobs:true, n_probs:8192, max_tokens:1` the server returns the raw
**full-vocabulary T=1 softmax** for the slot (partial-sort over the whole
row, no temperature, no sampler filtering). The Decider's T=1.3 option readout
is recovered exactly:

    p_T(i) = p_1(i)^(1/1.3) / Σ_j p_1(j)^(1/1.3)     (over the option letters)

(the partition-function constant cancels in the ratio). Client:
`scripts/jevab/decider-http-client.py` (imports `decider_readout()`; the live
loop on the game testbed should call it directly per step). The Decider's tokenizer +
`decider` package (text files only, 23 KB) are vendored at
`models/decider-2b/`; the GGUF lives on host model stores, never in git.

**Validation (41/41 corpus rows, 2026-09-25):** the HTTP/CUDA path reproduces
the C-API/CPU Q8 reference run (report §13) — per-row Δp(oracle) 0.001–0.03
(one outlier 0.086), top-1 identical on every row; summary
conf_correct/conf_wrong 0.861/0.134 vs 0.856/0.141. I.e. **Q8 on the GPU is
the same Q8 floor on the CPU** — float32/kernel noise, not a new variable.
The one outlier (Δ 0.086, `mine-regress#4`, both runs chose correctly) had the
CUDA path ~0.09 *less* confident in the oracle than the CPU path; the other 40
rows are within 0.036 — no systematic direction between the two paths.

**Latency (the answer to §13's open question).** ~**290 ms/row end-to-end**
from a tailnet client (RTT + ~70–100 ms prefill for the 130-token harness
prompt) — **~12× faster than the 4-core CPU Q8 run and 4× inside the ≪1 s
reflex target.** The Decider is now a credible per-step reflex: at 1 decision
per game-step the GPU cost is a few percent of one frame's budget.

**Status of the two-tier loop.** The decision side of v4 (27B per-step judge +
Laya obvious-yes pre-filter) is measured (report §7–11); the *reflex* layer is
now the Decider. Wiring v5 = Decider readout (this script) as the per-step
action chooser with its p(oracle) as the confidence, Laya's noul as the cheap
veto (the Laya box), and the 27B (the 27B box) as the escalation judge on
low-confidence/negative-veto — the design in the 2026-09-22 handoff, with the
reflex finally fast enough to matter. Open: corpus world variety (the 29%
travel-phase bias in the Decider's errors says the training data was weak
exactly where its failure mode is), new actions (`give`, `place`), and the
resident-model etiquette on the 3060 (a running Polis mission and heavy
OpenClaw use on the same card ping-pong the switch).

## 15. v5: the live three-tier loop (2026-09-25 overnight) — the cascade runs for real

`scripts/jev-loop-v5.py` puts the §14 Decider into the live loop and
re-orders the tiers cheapest-first:

    policy proposes an action for the current phase
      -> 1) Laya 421M noul pre-filter (anchored yes/no, ~1.3-1.5 s)
             p < tau_yes (0.35)        -> straight to the 27B
             p >= tau_yes              -> 2) Decider-2B choice readout
                  p(proposal) < tau_dec (0.5)      -> 27B (doubt)
                  p(proposal) >= tau_dec:
                       Laya p >= tau_strong (0.6)  -> execute the proposal
                       Laya p <  tau_strong        -> 27B (borderline doubt)
      -> 3) 27B doubt-arbiter (thinking off, 272 ms measured) answers the
             same choice; fallback: the proposal. Stall valve unchanged.

The **strong-gate** is the load-bearing addition. In the first v5 run the
injected skip-goal fault passed *both* small tiers in consensus: Laya yes
at 0.37 (barely over 0.35) and the Decider's known travel-phase bias at
p(goto_base)=0.76 — two "no doubt" signals, one confidently wrong decision,
and the 27B never got to look. Making the 27B run on *borderline* consensus
(as well as on disagreement) closes that hole while keeping short-circuits
for genuinely confident steps. Every step is still labeled (both p's, the
path, the judge answer, executed, oracle) — the threshold re-derivation
protocol applies to tau_dec and tau_strong alike.

The Decider endpoint for these runs was **the CPU batch box** (the A/B box):
`scripts/jevab/decider-service.py` is a thin HTTP wrapper over the
validated in-process llama.cpp Q8 readout (same code path as `gguf-runner.py`,
one model load, requests serialized). Four corpus rows replayed through it
returned **bit-identical** p(oracle) to the batch file (0.1512, 0.9484,
0.9477, ...) — deterministic CPU inference; cost ~3-4 s/row on 4 cores.
Once the game testbed's tailnet node is approved the same client points at the the 3060 host
card (the 3060 model mux) at ~290 ms/row — one env var, no code change.

### Run results (the game testbed, fixture 8 blocks east of the player)

| run | mission | steps | wall | injected fault | outcome |
|---|---|---|---|---|---|
| v5a | mine | 6 | 81 s | travel-skip | not corrected (the 0.37/0.76 consensus hole; run that motivated the strong-gate) |
| v5b | mine | 4 | 76 s | travel-skip, tool-drop | travel caught by the 27B; tool-drop: 27B repeated mine_target (exec FAIL), loop re-proposed **give_tool** at step 3 — Decider 0.23 (doubt) -> 27B endorsed it -> pickaxe re-given -> mine OK -> GOAL |
| v5c | harvest | 2 | 16 s | travel-skip | Laya 0.21 (no) -> **27B jumped straight to `harvest_target`** (the action auto-walks) -> crop harvested -> return -> GOAL; fault corrected 1/1 |
| v5d | mine (5 options) | 2 | 12 s | (travel) | 27B again goal-first: `mine_target` from base in one action -> GOAL; mine-phase fault never reached |
| v5f | mine (imperial tool rule) | 2 | 11 s | (mine — never fired) | Laya 0.31 (no) -> 27B goal-jump `mine_target` from base -> GOAL; the strengthened substitution-form rule text did not change the goal-first behavior |
| v5g | mine, **24-block fixture** | 2 | 25 s | travel-skip | fault injected (goto_base, Laya 0.26 no) -> 27B goal-jump `mine_target`; the traverser walked the full 24 blocks inside the action; GOAL — long gotos hold at this distance |

Plus a dedicated tool-fault run (v5e): travel OK -> mine-phase drop -> 27B
repeats the tool-less `mine_target` against its own explicit tool rule
(exec FAIL) -> next step's proposal is `give_tool`: Laya 0.48, Decider
0.23 (doubt), **27B answers give_tool, exec OK** -> mine with the tool ->
GOAL in 5 steps / 76 s. The loop self-repairs; the arbiter just needs the
correct action *proposed* to endorse it.

### Findings

1. **The 27B is goal-first, not phase-first — and it is the dominant live pattern.** Because actions include
   their own approach (goto is part of mine/harvest execution), the arbiter
   completes the whole mission in one action; on the follow-up runs this
   happened on *every* 27B contact (five of the last six runs: the mine
   fixture was consumed in step 1, from base, 24 blocks away — 25 s wall
   including the walk). Consequence: the mission collapses to two steps
   (act, return) and the injected phase faults often never fire, because
   the phase they belong to is skipped. Mission completion is the true
   metric; the phase oracle stays conservative by construction. (Also
   found the same night: with *both* model tiers unreachable — the
   defaults were unresolvable placeholder hosts — the loop ran on policy
   alone and still completed the mine mission in 5 steps, the give_tool
   oracle proposal doing the repair. The deterministic policy is the
   floor, not the failure mode.)
2. **The 27B's tool rule is conditional, not substitutive.** It endorses a
   proposed `give_tool` but does not proactively replace a tool-less
   `mine_target` proposal even when told "never mine_target without a
   pickaxe". The fix is a substitution-form rule ("no pickaxe in inventory
   ⇒ answer give_tool"), not a stronger warning.
3. **The Decider generalizes to a new 5th option as a detector, not a selector.**
   30 labeled rows built around the live no-tool states
   (`scripts/jevab/gen-give-tool-rows.py`, `data/give-tool-rows-2026-09-25.json`):
   with-pickaxe controls stay at 0.921–0.926 (no 5-option drift in the
   trained readout); p(give_tool) separates cleanly by state — 0.255 (no
   tool, give_tool proposed), 0.060 (no tool, mine proposed), 0.009
   (with tool) — but the *choice* is mine_target on 30/30: the trained
   phase action owns the argmax, the new option only gets probability
   mass. Loop consequence: a proposed `give_tool` reads 0.255 < tau_dec
   0.5, so the Decider correctly raises doubt and the 27B endorses it
   (the self-repair path); but a proposed tool-less `mine_target` reads
   0.843 — *confirmed* — so the Decider does not flag the 27B's own
   failure mode. B-type rows are the Laya-veto + last-resort-repair
   regime (exactly how v5e completed); fine-tuning on the generated
   A/B rows is the path to make the 2B a give_tool selector.
4. **Live Laya noul sits lower than its corpus band**: 0.21-0.48 across
   these runs (vs up to ~0.9 in the 09-22 sets). Mostly below tau-strong
   0.6, so with the strong-gate the 27B is the actual decider on most
   steps. At 272 ms that is acceptable. **Re-derived overnight from the
   21 dual-p rows** (15 carrying both Laya-noul and Decider readings):
   the false-yes cap is 0.371 (the injected skip-goal, twice — the
   Decider's travel bias at 0.76 confirmed it, so both p's looked
   "confident") vs the correct floor 0.400. `--tau-strong` now defaults
   to **0.40** (advisory: a thin 0.029 gap on N=15): short-circuits 9/15
   vs 4/15 at 0.6 with **zero short-circuit errors** on the data, while
   every 0.371 false consensus still escalates. `--tau-yes` default
   likewise set to its 09-22 derived 0.35 (faulty 0.29-0.32 vs correct
   0.36-0.39).
5. **The travel bias is live and caught by design**: the Decider's
   p(goto_base)~0.76 for the injected skip passes a borderline Laya yes;
   the strong-gate routes that exact consensus to the 27B, which answers
   goto_target. The §12/§14 "gate on p(oracle), never on argmax confidence"
   rule is what makes this catch possible.
6. **Action granularity sets which tier does the work.** With
   self-approaching actions the mine/harvest missions are 2-step
   (act, return); "travel" is at most one step (or zero, when the 27B
   jumps). The small tiers therefore mostly see *veto* opportunities
   (a proposed skip-goal) and *return/done* confirmations — exactly the
   decisions the 421M noul question was built for — while goal selection
   goes to the 27B. The Decider's corpus-measured strength (phase
   selection, 70.7%) has little live surface on this action set; its
   live role is the calibrated p(proposal) that feeds the strong-gate.
   If the loop ever needs the small tiers to *drive* (not just veto),
   the action set has to be decomposed (goto and mine as separate
   actions) — that trades steps and latency for small-tier utilization.
   On the current substrate (27B at 272 ms) the coarse action set is the
   better deal.

### Infrastructure notes (same night)

- **the CPU batch box**: the stale-rootfs-bind anomaly recurred (the CT-side
  it (third occurrence — this is the pattern, not a one-off).
  `decider.service` (the live readout) and `jevab2` (batch supervisor) are
  both active. The Q8 GGUF lives at `/var/jevab/weights/decider-2b-Q8_0.gguf`
  (conversion output, CT rootfs); the safetensors stay in `/models/jevab/`.
  trixie repo is stale at 1.90.6 — the bookworm pool .deb is the working
  source; the Debian tailscaled unit also needs `/etc/default/tailscaled`,
  its EnvironmentFile has no `-`). The node `polis` is **registered in the
  tailnet** (the testnet address, `--accept-routes=false` per the 09-17
  invariants); the one pending step is a user click on the login URL
  (it regenerates on every `tailscale up` re-run — the current one is in
- **`scripts/botview.py`**: one-command live overview (player/bots/zones/
  last events in one line; `--follow N` streams ticks with move detection
  and appends a JSONL sidecar to `data/botview.jsonl`; optional single
  `--screenshot`).

### Fast decider path over the tailnet (done this morning, 2026-09-25)

The tailnet node was approved; the Decider now runs on the **the 3060 card**
for the live loop. Because the polis testbed box does not carry the
decider package/tokenizer, the path is split in two:
`decider-service.py` gained a **`/prompt`** endpoint (returns the exact
state-first prompt text plus the option-letter token ids — the service
already holds the tokenizer), and **`decider-fast-client.py`** (pure
stdlib, runs on the testbed) takes that prompt to the the 3060 host llama-server
over the tailnet and recovers the T=1.3 letter distribution from the raw
`n_probs` (same math as the C-API path). `jev-loop-v5.py` now takes
`--decider-fast`/`--prompt` and falls back to the in-process CPU readout
on any error.

Measured end-to-end from the testbed: **286 ms/row warm** (10.6 s first
call, includes the one-time model load on the card) — the 3-4 s CPU
readout is ~12× slower. The the 3060 card's letter-logit readout is
numerically the validated Q8 (mine_target 0.918 here vs 0.921-0.926 on
the in-process controls; choice identical). This produced the **first
live short-circuit** of the loop: a harvest return-step with Laya 0.41
(>= tau-strong 0.40) and Decider 0.96 (>= tau_dec 0.5) executed directly,
no 27B call — the two small tiers doing their designed job. After each
window the card is switched back to the 35B resident (the mux
`/models/load` evicts the decider automatically).

### 7-option rollout and the fine-tune experiment (2026-09-25, the 3060 host window)

The reflex vocabulary was extended to seven options —
`goto_target`, `mine_target`/`harvest_target`, **`pickup_item`**,
**`place_block`**, `give_tool`, `goto_base`, `wait` — with a `pickup`
phase inserted between the work phase and return (fast-skipped when
nothing is on the ground, which is the fixture reality: set-placed rock
yields no drops; the harvest crop is auto-collected). Design rule behind
the shape: the fine-tuned 2B covers the *reflex* primitives (frequent,
sub-second), the long tail of the mod's ~20 action implementations
(workstations, inventory, entities) routes through the 27B judge tier —
no fine-tune needed there.

The labeled corpus for the new options was assembled in two parts:
60 generated grid rows (`gen-pickup-place-rows.py`, A/B contrast +
controls per family) plus everything already labeled, remapped into the
7-option format (`remap-7opt-rows.py`): the 41-row A/B corpus, the
30-row give_tool grid, the v5 live rows, and the v1-v4 live sets —
**123 rows after dedupe** (25 give_tool, 36 pickup, 12 place_block,
49 goto/mine), related records grouped for the split.

**The fine-tune itself was a negative result.** A LoRA on top of the
Decider checkpoint (r16/α32, "all-linear", 16.8M trainable = 0.89% of
1.9B, lr 1e-4, 4 epochs, 102 train / 21 grouped holdout, 3060) drove the
train loss 0.43 → 0.06 while the holdout sat flat at 0.190 top-1 for all
four epochs. A per-row probe explained why: **the base model (no
adapter) scores 76% top-1 on the very same holdout** — the fine-tune
collapsed to answering `give_tool` with p≈1.0 on most rows (the largest
oracle class). Diagnosis: 16.8M free parameters against 102 short rows
is a degenerate regime — the adapter memorized the training rows and
overwrote the letter behaviour instead of refining it.

**The base model needs less help than expected.** On the full 123-row
grid, the unmodified Decider (bf16, 7-option prompt) scores **76/123
(61.8%)**, and the production **Q8 scores the identical 76/123** —
quantization-neutral for 7-option selection. Per family (Q8):

| family | rows | top-1 | mean p(oracle) | reading |
|---|---|---|---|---|
| give_tool A (no tool, propose give) | 12 | 10/12 | 0.464 | **detector → selector by adding the option** (5-option era: 0/12) |
| give_tool B (no tool, propose mine) | 12 | 0/12 | 0.053 | substitution gap — by design, covered upstream |
| with-tool controls | 2 | 2/2 | 0.928 | clean |
| build (place_block) | 18 | 12/18 | 0.637 | selects 6/6 when proposed; 0/6 substitution; controls clean |
| pickup (mine+harvest) | 42 | 24/42 | ~0.43 | A-rows selected, B-rows not — same split |
| mine (old corpus + live) | 30 | 24/30 | 0.694 | the known travel-phase bias survives the re-prompt |
| harvest (live) | 7 | 4/7 | 0.604 | mixed, small N |

Two consequences. First, the original "detector, not selector" finding
refined further: **listing an option in the prompt makes the 2B select
it** — the earlier grid measured detection (mass) because the model's
policy prior preferred the phase-matching action; with the option
explicit it overcomes that prior 10/12 times. Second, the fine-tune
decision (per the jev-designer rule: last, and only on evidence) is now
evidence-based: **defer it.** What the loop still can't do —
*spontaneously substituting* a proposed action (the 0/24 B-rows) and the
travel-phase bias — is a harder conditional that wants a much larger,
world-varied corpus before another training attempt, and any next
attempt must be gentle (r 4-8, lr 1-3e-5, early-stop, holdout covering
the new families) to avoid the measured collapse.

**Live 7-option missions** (the 3060 host-card decider via the fast path,
the game testbed): mine — goal in 2 steps/42 s, injected skip-goal fault
corrected (judge jumped to mine_target, goal-first), return step
short-circuited (Laya 0.43 + Decider 0.91); harvest — goal in 2
steps/26 s, fault corrected (judge → harvest_target), both steps via
judge (Laya 0.38/0.39, just under the advisory tau-strong 0.40). No
pickup phase was exercised live (no ground items in either fixture), as
expected. Note the (model, question, state-text) calibration unit
changed (new `items:` line, new option list) — the tau defaults are
advisory pending re-derivation on the next batch of dual-p rows.

### Threshold stress test on the broad corpus (2026-09-25, third dual-p pass)

Item (e) — re-deriving the taus on the new calibration unit (the 7-option
`items:`-bearing state text) — was done by generating the dual readouts
*offline* instead of waiting for live rows (live missions collapse to 2
steps and produced only 4 dual-p rows in 6 runs). `scripts/jevab/
dualp-runner.py` ran all 169 corpus rows (123 original + 46 added
`give_tool`-while-carrying variants; 151 carry both readouts — the 18
build-mission rows have no Laya question by design) through Laya noul
(the Laya box) and the Decider (the 3060 card, fast path): **84 correct-side**
(proposal = oracle) vs **67 faulty-side** (26 goto_base skip-goal, 46
give_tool-while-carrying, 1 mine_target).

The result is a *negative* one, and it is the useful one:

- **No gate separates on this corpus.** Every Youden point has negative
  margins on both sides: Laya p (correct 0.260–0.780 vs faulty
  0.183–0.764, J=0.167), Decider p among Laya-passing (0.013–0.954 vs
  0.027–0.905, J=0.364), Laya p among doubly-confident (0.351–0.780 vs
  0.358–0.764, J=0.218). The 09-22/09-25 tau derivations looked clean
  because they ran on *narrow* live distributions (policy proposals on
  active missions), where the two populations barely mix.
- **At the current defaults (0.35/0.50/0.40) the stress corpus
  short-circuits 47/151 rows, of which 20 are faulty** (Wilson 95% UB
  19.6%) — 13 goto_base skip-goals (Laya p up to 0.764 — no Laya
  threshold catches them, correct rows reach 0.780) and 7
  give_tool-while-carrying. Both leak families are exactly the two known
  weak points: the Decider's travel-phase bias and the spontaneous-
  substitution gap.
- **Consequence for the defaults:** the tau values were left *where
  they are*. Chasing the Youden points (e.g. tau_dec 0.907, tau_strong
  0.747) would be an artifact of the overlap — they "separate" by
  killing the short-circuit benefit (correct SC 10/39, 20/55) rather
  than by finding a boundary. On this corpus the gates' function is
  **load control** (47% of rows skip the 27B; the live narrow
  distribution short-circuits more), and *safety is carried by the 27B
  catching what leaks plus the last-resort deterministic repair* — which
  is the architecture's design, not a compromise. The lever for the two
  leak families is the tiers themselves: world-variety corpus growth +
  the gentle fine-tune (boundary smoothing; see the llmlab addendum's
  in-context-boundary literature), not threshold tuning.

### Next (in order)

(a) **done** — tailnet node approved, fast decider path live on the the 3060 host
card (~286 ms/row, first short-circuit observed); (b) **done overnight:**
`tau-strong` re-derived to 0.40 and `tau-yes` to 0.35 (see finding 4);
re-run the four missions at the new defaults to measure the short-circuit
rate; (c) **done** — substitution-form 27B tool rule (v5f run);
(d) **in progress** — corpus growth: give_tool grid (**done**), 7-option
corpus (**done**, 123 rows) — next: world variety (distances, target
types, night/day) and missions that actually produce ground items (the
pickup phase is live-wired but unexercised); (e) **done** — tau
re-derivation on the new calibration unit ran as an offline stress test
on 151 dual-p rows: no gate separates (all Youden points negative-margin);
defaults left at 0.35/0.50/0.40 by decision — gates do load control, the
judge + last-resort repair do safety (see the stress-test section above);
(f) gentle fine-tune (r 4-8, lr 1-3e-5,
early-stop) once the corpus is several times larger — the aggressive
r16 attempt collapsed the model (76% → 29% holdout); (g) `place_block`
build mission end-to-end (execute() exists).
