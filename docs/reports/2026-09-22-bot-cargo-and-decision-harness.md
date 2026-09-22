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
