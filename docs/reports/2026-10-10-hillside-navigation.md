# Hillside navigation fix — F5–F9 implementation and live validation (2026-10-10)

Implemented by the delegated sub-session of the polis dev session
(2026-10-10), per the hillside-nav spec in this session's working
tree. Scope: `PolisGotoAction.cs`,
`PolisAStar.cs`, `PolisPathNode.cs` only. No engine patching.

## Verdict

- **Gate 1 (flat suite): PASS, no regressions.** T1–T4/T6 exact-arrival
  15.1 s; the two one-block-below cases (R2, Cliff) now fail *honestly*
  (`one step short`) instead of the original silent `ok:true`
  short-arrival.
- **Gate 2 (hillside round trip, run twice): PASS.** Four legs, each
  ~30–35 s to exact arrival, zero falls, zero oscillation, zero stuck
  events — against the 17:40 baseline of 98 s + a 3.4-block fall + 5
  bounded-repath firings + a pocket wedge.
- **Gate 3 (P6 pots chain): blocked at the engine, not the mod.** All
  navigation legs of the chain pass; the chain fails because the
  vanilla firepit converts only 1 of 2 raw meats in five consecutive
  runs (engine drop when the fuel runs out mid-cook). See below.
- **F5 is reverted** (both candidate values regressed the flat suite);
  **F6, F7, F8, F9 are shipped.** F10 was not needed.

## Before / after matrix

All measurements on the game world of the polis container, daylocked,
dedicated test bots, harness `goto` with a 0.02 tolerance.

### Flat suite (leveled field, feet level 123)

| Test | Baseline (original nav) | 0.2 near-test build | 0.35 near-test build | **Shipped (0.7 + F6–F9)** |
|---|---|---|---|---|
| T1 flat 30 blocks | ok:true, 15 s, exact | ok:true, 15.1 s, exact | ok:true, 15.1 s, exact | ok:true, 15.1 s, exact |
| T2 1-step row | ok:true, 15 s, exact | ok:true, 15.1 s, exact | ok:true, 15.1 s, exact | ok:true, 15.1 s, exact |
| T3 2-high wall, 1-wide gap | ok:true, 15 s, exact | ok:true, 15.1 s, exact | ok:true, 15.1 s, exact | ok:true, 15.1 s, exact |
| T4 2-high wall, 2-high door | ok:true, 15 s, exact | ok:true, 15.1 s, exact | ok:true, 15.1 s, exact | ok:true, 15.1 s, exact |
| T6 door-shaped columns | ok:true, 15 s, exact | ok:true, 15.1 s, exact | ok:true, 15.1 s, exact | ok:true, 15.1 s, exact |
| R2 one-block-below (non-standable target) | **ok:true silent (the bug)** | **ok:true silent (regression)** | **ok:true silent (regression)** | **ok:false "one step short" (honest)** |
| R2 west 1-step (standable 1-up) | — | ok:true, exact | ok:true, exact | ok:true, exact (12 s) |
| Cliff: valley floor → base edge (32-block pass, non-standable target 1 up) | **ok:true silent after ~30 s** | ok:true silent | ok:true silent | **ok:false "one step short" (honest), bot at the lip** |
| Cliff: base → valley (valley is a *pond* in this world; no swim) | — | bounded fail | bounded fail | ok:false "all navigation modes timed out" (bounded, correct) |

The target cells at (512138, 511967) and the valley lip are **not
standable in this world** (non-solid foot level); the honest failure is
the correct end state for them. The standable 1-step variant
(R2-west1step) passes with exact arrival on every build.

### Hillside round trip (granite hill country, run twice)

Legs: field start (512105, 511966) → forage target (512098, 512033) →
back to the field's east edge (512135, 511966) — both directions cross
the hill.

| Run | Baseline (17:40, original nav) | **Shipped (0.7 + F6–F9)** |
|---|---|---|
| Leg A (downhill/southbound) | 98 s; fell 3.4 blocks off the ridge; 5 bounded-repath firings; wedged in a 1-block pocket | ~30–35 s; exact arrival (512098, 512033); no falls; monotonic progress |
| Leg B (uphill/northbound) | wedged in the same pocket on the return | ~35 s; exact arrival; clean climb over the crest (feet 123→124→125→123); no falls |
| Repeat A | — | ~30 s; exact arrival; no falls |
| Repeat B | — | ~35 s; exact arrival (ok:true); no falls |

Position was sampled every 5 s during each leg; no leg showed
back-and-forth motion (the 17:40 oscillation is gone), no Δy > 1.5
between samples, and no period of ~10 s+ without positional progress.

## What shipped, and what was reverted

- **F6 — admissible heuristic** (`PolisPathNode`): start-node cost and
  `Init()` now use `sqrt(DistanceSqTo)` like the reference mod's
  `VillagerPathNode`, instead of the squared (non-admissible) value
  that made the frontier stop widening and oscillate around
  obstacles.
- **F7 — phantom-path validation** (`PolisGotoAction.onFoundPath`):
  any consecutive step of ≥ +2 blocks in a core-A* path marks it a
  phantom route; the traverser is stopped and the action falls through
  to the next ladder phase instead of following it.
- **F8 — no-progress watchdog** (`PolisGotoAction.OnTick`): on the 1 s
  heartbeat, if the bot's distance to the target hasn't improved by
  >10 % for 20 s (best-so-far, persists across repaths), the same
  bounded-repath ladder as `OnStuck` fires (shared budget — no new
  unbounded loop). Kills the 12 s wedge-push window.
- **F9 — slope preference + pocket rejection** (`PolisAStar`): g-cost
  gains `0.5·|Δy|` per step (flat 1.0, one-block step 1.5), computed
  from the actual stand level found during traversability testing; a
  candidate whose column surface is a local minimum with all four
  neighbours ≥ 2 above is rejected as a pocket (target cell exempt).
- **F5 — near-test tolerance — REVERTED to 0.7.** Both candidate
  values were measured live: 0.2 and 0.35 each eliminated the
  hillside waypoint-run-ahead oscillation, but each re-broke the
  one-block-below R2 case — the action then completes through the
  final-arrival handler's within-1.5 snap and reports a false `done`
  on the non-standable target (the original silent short-arrival, the
  14:10 repro). The 0.7 value leaves that final waypoint un-reached,
  so the honest failure path is taken. The hillside fix comes from
  F6 + F9 instead (gentle-gradient routes that the 0.7 near-test can
  follow without run-ahead). F5's code comment records both
  measurements.

**F10 (step executor) was not needed**: the hillside legs converged
cleanly after F6–F9.

## Gate 3 — P6 pots chain: engine-level blocker

The spec's integration gate (`r2-progression.py --start P6`) could not
reach `outcome: "complete"` in this world, in any build:

- p1 clayform, p2 pit-kiln fire, p3 firepit fuel, p4 cook all **pass**
  on every run (all navigation inside the chain works).
- p4 receives **1 of 2** cooked meats: with 2 raw meats in the firepit
  input and 2 charcoal as fuel (~2 s of burn), the vanilla firepit
  extinguishes before the second item finishes; the uncooked second
  meat **vanishes** (not in the bot's inventory, not in any firepit
  slot, not on the ground — an engine drop). p5 then fails with
  "consume failed partway (ate 1/2)".
- Reproduced on five consecutive runs across two builds (this
  session's evening window); one earlier run in the same world did
  cook 2 of 2, so the engine behaviour is timing-dependent but is
  clearly not in the mod's code (the mod only writes items to slots
  and polls; it never touches the fire's fuel or smelt timers).
- A sixth run after the final build: same single-cook failure.

This is outside the F5–F9 scope (it needs an engine firepit change or
a fixture change, e.g. `meat_n=1`), which is why the child escalates
rather than papering over it.

## Residuals / honest caveats

1. **F2's within-1.5 snap is unsafe on non-standable targets.** It is
   what converted the honest R2/Cliff failure into a silent `done`
   whenever the traverser's list completed (i.e. with a strict
   near-test). The next nav batch should make the snap verify the
   target is standable (or that the bot actually remains at the snap
   position) before reporting done. Out of F5–F9 scope; flagged for
   the parent.
2. **Hillside path provenance**: the legs arrive in 30–35 s (faster
   than the two 15 s phase timeouts plus walking), which suggests the
   polis A* phase now produces a followable gentle route directly —
   but confirming *which* phase produced the path requires a
   debug-enabled run, which was not done to keep the world
   undisturbed. The behavioural gate (≤1 stuck, no falls, exact
   arrival, twice) is met either way.
3. **The spec's "valley" is a pond** in this world (solid floor
   ~4 blocks below the surrounding land, water to the lip); entering
   it is a swim, which the mod does not do — the bounded failure is
   correct.
4. **P6 exit oracle** (`any_bot_sat ≥ 1400`) is trivially satisfied by
   a fresh-spawned chain bot (sat 1500); the oracle measures world
   state, not chain success. Fixture caveat, not a nav issue.

## World state at handoff

Deployed build = this commit (F6–F9, F5 at 0.7), daylocked during
deploy, `vsgame` restarted, daylock then released (vanilla day
running), oikistes active, mod debug off, deploy-check all-pass
(harness, oikistes, Xvnc, render smoke), chunkprobe clean
(gateNanCount=0, gameCaptured=true), temporal stability clean. The
test firepit was emptied of leftover cooked meat (to a test bot); the
village's own firepit is in normal use. No player-entity
touching.
