# R2: the job system + world model — goals become job lists, the cascade stays the reflex

**Status: design (frozen 2026-09-27, 14th pass); Phase 0 executed 2026-09-27 (15th pass — see status log below).** Started 2026-09-26 (11th pass);
extended 2026-09-27 with the world-model layer after external review. Extends
`archive/VISION.md` (phase 2) with the model stack as measured through 14 passes.

## 1. Where we are

Phase 1 (done, live on the game testbed): one bot, one mission at a time, driven
by the v5 loop — a phase machine over the serialized state, with the
three-tier cascade (Decider-2B reflex → Laya noul → 27B doubt-arbiter)
deciding each step, and a last-resort repair. Three mission families are
live and complete (mine / harvest / build), the 7-option reflex
vocabulary is closed, the reflex is fine-tuned (round 2 adopted) and
drift-guarded (nightly canary).

What the current architecture is, precisely: **a single-job driver**.
The mission *is* the job; the phase machine *is* the JobDriver; the
fixture *is* the reservation; the step budget *is* the anti-thrash.

**Where the machinery lives** (the fact that determines R2's shape): the
phase machine, the fixtures, the scan bookkeeping, the cascade readouts,
the dashcam and the per-step prompt assembly all live in
`scripts/jev-loop-v5.py` — Python. The C# mod is a thin **authoritative
fact provider**: commands in, facts out (scan / verify / state / bots /
events), no planning state. That split is an asset and R2 preserves it.

## 2. What R2 adds (and what it deliberately does not)

R2 adds, in two layers:

1. **A world model in the Python decision layer** — the shared semantic
   view of the game (resources, fixtures, claims), so that planning,
   reflex, dashcam and the future WorkGivers all read one source instead
   of each building an ad-hoc scan path.
2. **The planner on top**: a goal arrives (natural language or
   structured), it becomes an **ordered list of jobs** (the mission
   families we already run), and a **job queue** feeds them to the
   existing driver one at a time.

Everything per-step stays exactly as measured in the reports: the reflex
option set, the cascade, the thresholds, the canary. Deliberately
deferred to phase 3: multi-bot scheduling, deadlock-aware reservations,
scoring-based matching, aging priorities, tick throttling, navigation
graphs, entity belief, chunk/region staleness, WorkGivers,
vision/perception, a C# world store, RenderDoc/GPU capture.

## 3. Architecture

```
┌────────────────── Vintage Story / C# (the truth machine) ──────────────┐
│  authoritative state · IEntityActions · scan/verify/state/bots/events  │
└─────────────────────────────────┬──────────────────────────────────────┘
                                  │  HTTP harness (127.0.0.1 loopback)
                                  ▼
                        ┌──────────────────┐
                        │  Python adapters │   Polis client: http_json, cmd, state
                        └────────┬─────────┘
                                 │ observations
                                 ▼
        ┌────────────────────────────────────────────────┐
        │  WorldModel   (remembered / indexed facts)     │   r2/worldmodel.py
        │   resources (scanned clusters, stamped)        │
        │   fixtures  (identity only — see §5.3)         │
        │   claim index (read-only view of JobQueue's)   │
        │   tick                                        │
        └──────────────┬─────────────────────────────────┘
                       │  r2/queries.py (deterministic)
          ┌────────────┴─────────────┐
          ▼                          ▼
  PlannerProjection            ReflexProjection           (r2/projection.py)
  candidate IDs + goal         the byte-stable per-step    │
  (r2/plannerprompt.py)        state text (FT contract)    │
          ▼                          ▼                     │
      27B planner          Decider-2B FT → Laya noul       │
          │                          → 27B judge → repair  │
          ▼                          │                     │
      r2/plancheck.py (deterministic validation;
      symbolic refs only; 1 repair attempt)                │
          ▼                          ▼                     │
      JobQueue ── claims ─────────→ Executor (per-job phase machine,
          │                          = today's v5 run_once, one job at a time)
          └──────────────────────────┴→ actions via harness → game
```

### 3.1 Placement decision (the load-bearing one)

The world model lives **in Python, beside the decision loop — not in C#**.
Rationale:

- Every consumer of world state (planner, reflex, canary, dashcam, the job
  queue) is already Python; a C# `World/` module would create a second
  state store that Python must mirror for planning anyway — the exact
  two-worlds divergence the abstraction exists to prevent.
- The harness's design invariant is *thin, fire-and-verify*: it exposes
  authoritative facts and executes actions. Adding a persistent world
  model inside the game would make it a planner, which the 14 passes of
  measurement have kept it from being.
- R2 adds **zero new C# API surface**: `scan` / `verify` / `state` /
  `bots` / `events` already are the ground-truth interface. The
  game-version compat boundary stays unstressed.
- When in-game consumers (WorkGivers, GUI, R3+) eventually need world
  facts inside the game, the C# side can grow a *publisher* of facts; the
  Python model remains the consumer of record. That door stays open
  because the model speaks only in harness-visible facts.

Semantic distinction, kept at every boundary:

```
C# / game          = authoritative truth (right now)
Python WorldModel  = remembered, structured, stamped view of that truth
Models (27B/2B/Laya)= consumers of projections of that view — they never
                      write to it and never see the raw game internals
```

The model stack **consumes, never owns, ground truth** (the brief's §7,
adopted): observe → world model → decide → act → observe.

## 4. The world model — minimal R2 schema

```python
# r2/types.py
@dataclass(frozen=True)
class Vec3:
    x: float; y: int; z: float

# r2/worldmodel.py
@dataclass
class ResourceRecord:
    """A scanned cluster of same-material cells (an *observation*, stamped)."""
    id: str                    # "res-17" — stable within a goal run
    material: str              # "granite" / "crop-wheat-3" / ...
    cells: list[Vec3]
    centroid: Vec3
    source: str                # "scan" | "verified" | "fixture"
    last_observed_tick: int    # freshness metadata from day one (R3's
                               # belief/staleness machinery builds on this
                               # field, not on new types)

@dataclass
class FixtureRecord:
    """Fixture *identity* — authoritative configuration (we created it).
    Never carries current condition; state is an observation, see §5.3."""
    id: str                    # "site-A"
    kind: str                  # "build-site" | "marker" | "stockpile"
    cell: Vec3
    requirement: str           # "empty" | "block:rock-granite" | "absent"

@dataclass
class ClaimRecord:
    target_id: str             # "res-17" | "site-A"
    job_id: str; bot_id: int
    tick: int

@dataclass
class WorldModel:
    tick: int
    resources: dict[str, ResourceRecord]
    fixtures: dict[str, FixtureRecord]
    claim_index: dict[str, ClaimRecord]   # READ-ONLY view; JobQueue owns
    def find_resources(self, material, reachable_by, radius) -> list[ResourceRecord]
    def get_fixture(self, id) -> FixtureRecord
    def find_unclaimed(self, ...) -> ...
```

**`LiveState` is not in the model.** Per-step bot state (position, current
inventory, health, current action) is **ephemeral**: it is refetched from
`/polis/state` every step (as today) and passed alongside, never stored as
"world knowledge". The decision context makes the split explicit:

```python
ctx = DecisionContext(
    bot=polis.get_state(bot_id),   # ephemeral, authoritative this tick
    world=world_model,             # remembered/indexed, stamped
    job=current_job,               # queue-owned
)
```

`WorldModel` owns the record dicts and the tick. `queries.py` is
deterministic (no model calls, no actions). `projection.py` renders
narrow inputs for planner / reflex / debug UI / run JSON — the same
function is the only path by which a prompt ever sees the world, which is
what keeps game internals out of model context.

## 5. Ownership, identity, invariants

### 5.1 Ownership table

| thing | owner | who else sees it |
|---|---|---|
| world facts (as truth) | the game (C#) | everyone, via harness |
| remembered world facts (resources/fixtures/claims-index/tick) | `WorldModel` (Python) | projections only |
| claims (authoritative) | `JobQueue` | `WorldModel.claim_index` (read-only, for `find_unclaimed`) |
| goals / jobs / status | `JobQueue` | run JSON |
| action/phase state | per-job executor (= v5 machine) | run JSON |
| fixture completion checks | deterministic fixture functions (one per job family) | executor |
| actuation | C# harness + actions | — |

No separate reservation service in R2: one bot, one claimed target at a
time; a set of claimed cells in the job record plus the read-only index is
the entire reservation system.

### 5.2 The trust boundary: symbolic references

The planner receives **candidate IDs** (from `find_resources` /
fixture registry) in its projection, and its output references those IDs:

```json
[
  { "type": "mine",   "source": "res-17", "quantity": 5 },
  { "type": "place",  "site": "site-A",   "quantity": 5, "depends_on": ["j1"] }
]
```

It may **choose among** supplied candidates; it may not **invent** one.
Any unknown `res-*` / `site-*` is a hard deterministic rejection
(`planner_invalid_reference`) — no coordinates are ever model-generated.
The same principle extends to bot IDs and fixtures.

### 5.3 Fixture identity vs fixture state (invariant)

A fixture's **identity is authoritative** (we created it: kind, cell,
requirement — `FixtureRecord`). Its **current condition is an observation**
and is only ever obtained by asking the game (`scan` / `verify`) at check
time:

```
site-A is a defined build-site at (x,y,z), requirement empty   ← configuration (authoritative)
site-A currently contains air                                   ← observation (stamped)
site-A currently contains granite                               ← observation (stamped)
```

Job completion always re-queries the game; the model record is never
consulted for "what is in the cell now". (The v5 per-mission fixture
functions — marker gone / crop gone + item carried / site filled — become
the completion oracles, unchanged.)

### 5.4 The reflex invariant (non-negotiable)

Given identical state, the refactored projection code produces a
**byte-identical** reflex state text (the FT-trained 8-line format:
task / phase / facts / carrying / items / since / last_action / proposal)
and therefore the same cascade decision. The 2B model was fine-tuned on
exactly this representation; any drift is a model regression, not a
refactor. Gates: nightly canary (96/96) + abstain corpus (45/45) + a local
deterministic regression fixture (Phase 0) + a live-mission step-decision
diff.

### 5.5 Structured failure codes (defined before the planner exists)

```
unsupported_goal          goal outside the grammar
planner_invalid_json      output not parseable as the job-list schema
planner_invalid_reference unknown res-*/site-*/bot id
planner_dependency_error  depends_on inconsistent with the order
resource_not_found        no candidate in scope for the required material
target_not_reachable      query says unreachable (distance/probe)
claim_conflict            target already claimed by a live job
job_budget_exhausted      job abandoned at its step budget
fixture_failed            completion oracle false at budget end
```

Each failure is attributed to a layer (observation / query / planner /
validation / execution / oracle) in the run JSON. A failed plan gets the
planner **one** repair attempt, then a structured rejection to the user —
no silent re-planning loops. A job that exhausts its budget is
*abandoned*, not retried in place; the planner may re-queue it as a fresh
job; a second abandonment of the same goal escalates to the user with the
state trail.

## 6. Goals, jobs, queue

- **Goal grammar (v1):** `{verb, object, at, n}` — verbs restricted to the
  live mission families (mine / harvest / place / goto). Anything outside
  the grammar is a planner rejection, not a planning attempt.
- **Job representation: an ordered list with an optional `depends_on`
  field**, validated to be consistent with the order (a dependency that
  contradicts the list is `planner_dependency_error`). Execution stays
  strictly sequential in R2; the field costs one line and keeps the
  semantics for the DAG phase.

```python
@dataclass
class Job:
    id: str                     # "j1"
    type: str                   # "mine" | "harvest" | "place" | "goto"
    source: str | None          # "res-17"
    target: str | None          # "site-A"
    material: str | None
    quantity: int | None
    depends_on: list[str]
    claims: list[str]           # cells/targets reserved while live
    budget: int                 # max execution steps (the stall valve)
    status: str                 # ready | running | blocked | done | abandoned
```

- **Completion:** a job completes when its fixture condition holds (the
  per-mission checks already implemented). A *goal* completes when its
  last job completes; the loop reports `goal_complete` exactly like
  `mission_complete` today.

## 7. Run JSON (the replay fixture)

```json
{
  "goal": {},
  "worldSnapshot": {},
  "plannerProjection": {},
  "plannerProjectionVersion": 1,
  "reflexProjectionVersion": 5,
  "plannerRawOutput": "...",
  "planValidation": { "ok": true, "checks": [], "rejections": [] },
  "jobs": [
    {
      "job": {},
      "claims": [],
      "steps": [],
      "fixtureResult": {},
      "result": { "status": "done", "failureCode": null }
    }
  ],
  "goalResult": { "complete": true, "failureCode": null, "layer": null }
}
```

Projection versions are recorded so historical runs stay replayable across
prompt changes. Persistence story for R2: **in-memory per goal run; the
run JSON is the persistence** (durable fixtures can move to world config
later — the `polis_oikistes_autonomy` key proved that mechanism in this
codebase).

## 8. Implementation plan (six slices, each gated)

**Phase 0 — freeze behavioral contracts.** Capture representative
existing runs (serialized state → reflex prompt → Decider/Laya/27B
outputs → chosen action → fixture result) as a local deterministic
regression fixture: `old v5(state) == refactored(state)` for prompt text
and resulting action. The nightly canary stays the high-level gate; this
is the refactor's own gate.

**Phase 1 — extract the executor, no planner yet.** `scripts/
jev-loop-v5.py` becomes `r2/{executor,projection,types}.py` + a thin
orchestration script. No job queue, no planner, no new goal format, no
new world semantics; the old mission path runs exactly as before.
*Gate: byte-identical reflex prompt; canary 96/96; abstain 45/45; ≥1 live
mission with identical step decisions.* This is the most important gate.

**Phase 2 — the minimal WorldModel underneath existing missions.**
`r2/{worldmodel,queries}.py` with the §4 records; existing calls move
from `scan → bespoke mission dict` to `scan → WorldModel → query →
executor`. The abstraction is proven before any planner relies on it.
*Gate: mine/harvest/build missions still behave identically.*

**Phase 3 — job/goal contracts.** The §6 types + §5.5 failure codes,
defined and unit-tested before any model output meets them.

**Phase 4 — planner projection + validator before trusting output.**
`r2/projection.py` (planner side) + `r2/plancheck.py` implementing the
checklist: known job types, known symbolic references, valid quantities,
grammar, dependency validity, source/material compatibility,
**material-before-use**, claim compatibility. The model never bypasses
this.

**Phase 5 — planner A/B (measure before wiring).** A fixed fixture set
(~20–30 cases: simple mine/harvest/place; mine→place; missing resource;
invalid candidate; unsupported verb; multiple valid sources; invalid
quantities; deliberately tempting nonexistent references) run against
the 27B. Measure separately: parse success, schema success,
valid-reference rate, dependency correctness, semantic validity,
repair-attempt success. Do **not** preemptively switch to a degraded
text grammar — measure first; if JSON is unreliable, decide between a
structured decoder or the narrow grammar with the numbers in hand.

**Phase 6 — JobQueue + the two-job milestone.** Goal → planner →
validated jobs → queue → executor(job 1) → oracle → executor(job 2) →
`goal_complete`. No multi-bot, no retry scheduler, no deadlock handling,
no WorkGivers.

## 9. Milestone (definition of done for R2)

1. **Two-job goal live:** "mine the granite in the pocket and build a
   pillar here" → planner emits [mine, place] → both complete in
   sequence, `goal_complete=true`, full run JSON.
2. **Dependent material flow:** the place job's material is the mine
   job's drop (inventory hand-off — the bot carries it; no new action).
3. **Rejection is honest:** a goal outside the grammar ("make a bread")
   returns a structured rejection with the reason — never a silently
   mis-planned job.
4. **Reflex regression gate:** canary + abstain + the live 4-fixture A/B
   (mine/harvest × d12/d20) before and after; per-step cascade numbers
   must not move (they cannot — same contract, §5.4).
5. **No new thresholds:** R2 introduces no new tau. The planner's output
   is deterministically validated; its only "probability" is the 27B's,
   which stays inside the judge's existing contract.

## 10. Open questions (deliberately small)

- Job-queue persistence across restarts: in-process for R2; a durable
  store only if goals start spanning maintenance windows (they won't in
  R2).
- Natural-language goals: the 27B parses them into the grammar; the
  grammar check is the trust boundary (a parsed goal that fails the
  checks is rejected, never guessed at).
- Planner model choice: the 27B judge model as of R2 (whatever the
  inference hub resolves at the time); the prompt/contract is
  model-agnostic by design (projections are versioned, §7).

## Status log (append-only)
- **2026-09-27 (15th pass) — Phase 0 done.** The behavioral contract is
  frozen and gated: `build_state_text` / `needs_judge` / `decide_cascade`
  extracted from v5 into pure functions (the loop calls them unchanged), and
  `tests/reflex/contract.py` pins them against goldens captured **before**
  the extraction — 237/237 prompt byte-identity (96 val-world + 96 OOV +
  45 abstain), 45/45 decision replays (all five cascade path branches, 4
  stall bypasses, 1 last-resort repair, 1 synthetic decider-err), 237/237
  readout coherence. Post-extraction, mine/harvest/build d12 missions all
  completed live (faults corrected by the cascade as before). The gate's
  `--impl v5|r2` hook is the Phase 1 comparison point. Phase 1 (executor
  extraction) is next.
- **2026-09-27 (15th pass, review round 2) — amendments below adopted.**
  External review of the Phase 0 shape; adopted: the state-construction
  seam (T4) and run-level transition assertions join the Phase 1 gate;
  the visual-sensor service moves to Phase 2 (no new consumer exists
  until then — the C# endpoint already serializes/rejects/lifecycle-guards
  today); the NaN policy is formalized as a layered hierarchy with a
  predicate-mirroring rule (IsNaN, not IsFinite — see §11.3); the Phase 2
  staleness invariant is adopted verbatim (§11.4).

## 11. Amendments — review round 2 (2026-09-27, after Phase 0)

Additive to the frozen §1–§10. Where this section and an earlier section
disagree, this section wins for the phases it names.

### 11.1 The gate gains the state-construction seam (T4) and run-level transitions

The Phase 0 gate proves: given state object S, rendering and deciding S is
unchanged. It does not prove: given game observation O, the executor
constructs the same S. That is the one remaining semantic hole before
Phase 1, and it is closed with two additions to `tests/reflex/contract.py`:

- **T4 — reflex-state construction identity.** New fixture: per step, the
  RAW harness observation (`/polis/state` payload) **and** the constructed
  reflex-state DTO (the exact input dict
  `build_state_text` receives — target name, phase, distance, carrying,
  inventory counts, since/last lines, options), plus the mission context
  (mission, fixture identity, step index, previous action + its outcome).
  **Both raw payload and DTO are goldens, deliberately** — three clean
  diagnostic boundaries for any later regression: harness semantics
  changed (raw differs) vs normalization changed (raw same, DTO differs)
  vs prompt projection changed (DTO same, bytes differ). The full frozen
  chain becomes: raw facts → ReflexState (T4) → prompt bytes (T1) →
  cascade decision (T2) → action request + **run-level transitions
  (T2b)**: same
  run length, same completion step, same completion/abort reason, same
  budget accounting. Per-step decisions matching while the run ends one
  step early is a gate failure.
- **Capture procedure:** v5's per-step recorder gains two additive fields
  (raw observation + constructed DTO) — recording only, no behavior
  change (the pure-function gate stays green; one live run after the
  change confirms it). One daylight capture pass per mission type
  (mine/harvest/build) produces the T4 goldens; they are captured
  **before** any Phase 1 code exists, same rule as Phase 0's goldens. No
  "v6 fixture set": the same fixtures run against both implementations
  until Phase 1 passes.
- Known construction hazards the seam is built to catch (from review):
  wrong normalized item code with identical rendering; stale fixture
  state reused one extra step; previous-action outcome sourced from the
  wrong action; distance/LOS computed before vs after the state refresh;
  reordered refresh→verify→construct; completion checked one step
  early/late; budget-decrement timing; target/claim ID rebind under an
  identical-looking prompt.

### 11.2 Visual sensor: one owned service, scheduled at Phase 2 (not Phase 1)

The `/polis/observer-screenshot` endpoint is treated as a **scarce
visual sensor**, not an HTTP detail: one capture in flight, ~0.6–1 s,
viewer can disappear, capture has teleport/restore side effects (all now
enforced in C#: atomic in-flight guard, JSON rejection, restore skips a
disconnecting/unloaded entity). The Python-side **ObservationService**
(capture queue, request ids, timeout, disconnect outcome, coalescing with
`maxAgeMs` + `reason`, capture timestamps, result provenance) is a **Phase
2** deliverable alongside the WorldModel observation layer — not Phase 1:
Phase 1 introduces no new consumers (today's three — UI auto-capture,
dashcam, judge-image attachment — already run safely through the hardened
endpoint), and freezing the service before the executor exists would
freeze implementation accidents. Phase 2 target shape:

- Semantic sensors (`/polis/state`, scan, verify, action outcomes) stay
  on the direct-query path — **fixtures and completion verification never
  depend on the visual sensor** (a deterministic completion oracle must
  not hang on a serialized 1-second sensor).
- Only the screenshot path goes through the serialized service; consumers
  request with `{maxAgeMs, reason}` and the service may coalesce
  (judge ≈ 100 ms, debug UI ≈ 500 ms, dashcam ≈ 1000 ms).

### 11.3 NaN policy: layered, and the guard mirrors the engine — never IsFinite

Recovery hierarchy (most to least preferred):

1. **Prevent the bad update** — at the issue boundary: one capture in
   flight; the restore skips when the player no longer holds the exact,
   loaded, world-member entity (lifecycle guard: entity reference +
   alive + world membership + capture token).
2. **Restore a recent same-lifecycle finite pose** — position only,
   when the position itself is NaN. Motion is *not* restored from an old
   snapshot: position-from-t-200ms + velocity-from-t-200ms against
   current collisions creates a second bad integration step.
3. **Crash containment** — zero non-finite motion (vanilla rejects it,
   we log and continue instead of dying). Worst case: one tick of stalled
   physics.

**Predicate-mirroring rule:** the guard mirrors the engine's *actual*
checks, decompiled (VSEssentials 1.22.7, `ApplyTests`): `double.IsNaN`
on pos.X/Y/Z **and** motion.X/Y/Z (the throw prints `pos.ToString()`,
which shows XYZ/YPR/Dim — hence the 09-27 "clean-looking" crash),
`float.IsNaN(dt)` (dt is the server tick delta; we never perturb it, so
no dt action), plus the EntityPos-level NaN checks (X+Y+Z, roll+yaw+pitch,
motion) — the installed guard is the union of these. **Explicitly not
`IsFinite`**: the engine accepts ±Infinity; sanitizing it would diverge
from vanilla behavior and hide the fact that an infinite value is a
different (real) bug. If Vintage Story adds a pose field to a NaN check
in a later version, the mirror is extended deliberately — that is a
versioned, reviewed change, not a generalized clamp.

**Observability:** every guard event logs entity, capture token, the
invalid field(s), the policy taken (dropped/restored/zeroed), entity
alive state, and viewer-connected state. A NaN that is no longer fatal
must not become silent weirdness.

### 11.4 The Phase 2 staleness invariant (adopted verbatim)

> WorldModel may nominate targets.
> Only fresh game observations may prove completion or immediate action
> preconditions.

Stronger formulation frozen alongside it:

> WorldModel records may be stale.
> Action preconditions and completion checks must never be satisfied from
> cached records alone.

That covers the immediate-execution decisions, not just completion:
*target still exists, site still empty, resource still mineable, bot still
holds the required item.* The division of labor: the WorldModel answers
**"what should I consider?"**; the live game must still answer **"may I do
this now?"** and **"did it succeed?"** The next likely architectural risk in
R2 is no longer the reflex contract — it is accidentally letting cached
world knowledge acquire authority while `ResourceRecord`s start looking
temptingly authoritative.

Once `ResourceRecord`/`FixtureRecord` exist, using "known state" where
the old code used "current state" becomes a one-line developer error with
no visible per-step regression. Phase 2's gate includes a dedicated check
for both invariants (no fixture, completion, or action-precondition path
reads a WorldModel record without a same-step fresh observation).

- **2026-09-28: Phase 1-A COMPLETE - the extraction is done and proven.**
  The pure reflex core now lives in `r2/{types,projection,executor}.py`,
  VERBATIM-extracted from v5 (one implementation for both entry points; v5
  is the live orchestration importing from it). The T4 goldens were captured
  the way 11.1 specifies: daylight passes with additive instrumentation (each
  step records the full observation triple - f1 state, f2 carry, post-
  injection f3 - plus the fixture scan and the prev record, and the exact
  reflex-state DTO the loop built at the moment of the decision);
  `tests/reflex/fixtures/reflex-state-t4.json` freezes 8 steps (3 runs,
  mine/harvest/build, clean and complete) with run-level transition data for
  T2b. The gate now runs **T1 237/237, T2 45/45, T3 237/237, T4 8/8, T2b 3/3
  on BOTH `--impl v5` and `--impl r2`** - the behavior-identity proof the
  plan required, plus the state-construction seam T1 could not cover.
  Verification paid: the first T4 replay caught a real recording bug (the
  row's `raw.scan` was re-read from `pol.last_scan` at append time - after
  the post-execute goal check had re-issued the scan - so the recorded
  "pre-decision" scan was actually post-execution; the DTO itself was
  fine because it was built from the earlier ctx capture). Post-extraction
  live spot runs (faults on, mine + harvest) completed in 2 steps each with
  the 27B judge correcting both injected skip-goal faults as designed.
  Phase 1-B (next daylight): nothing left except the Phase 2 work -
  WorldModel + ObservationService under the now-fully-frozen reflex.

## 12. Amendments — review round 3 (2026-09-28, before Phase 4)

Additive to the frozen §1–§11. Where this section disagrees with an
earlier section, this section wins for the material it covers. Six
central rules are adopted verbatim:

1. **Wall time is diagnostic; `observation_seq` / monotonic ordering is
   operational.** (Wall clocks jump; a game tick is not a prerequisite
   for R2 — the invariant is causal: cached observation ≠ fresh proof.)
2. **Resource quantities are observed quantities, never assumed complete
   extents** (a 3×3×4 scan cuts veins at its boundary).
3. **WorldModel nominates; fresh game observations authorize actions and
   prove outcomes.**
4. **`"inventory"` is an execution source, not material provenance.**
   Material-before-use is validated by *simulating inventory effects over
   the ordered job list* (ledger = current bot inventory; mine →
   ledger += expected yield; place → requires ledger ≥ n, ledger −= n;
   harvest → +harvest result; goto → none). `depends_on` describes job
   dependency only.
5. **Planner candidate IDs are scoped to the projection/snapshot that
   introduced them** (`projection_id` in the run JSON); a later
   WorldModel refresh must not silently rebind a job's target — the job
   retains its binding (cells/material from the snapshot).
6. **Every observation records why/when in the action lifecycle it was
   obtained** (`reason`: pre_action / post_action / oracle /
   planner_scan / fixture_setup, plus optional `caused_by_action_id`).

Specific amendments:

### 12.1 ObservationService (Phase 2): unit-test only, result taxonomy

Agreed: no migration of the three existing consumers (dashcam / judge
attachment / UI) tonight — that is a later controlled pass. The service
API distinguishes outcomes, never collapsing non-images into `None`:
`ok` | `unavailable` (endpoint rejected) | `timeout` | `disconnected`
(transport failure / viewer gone) | `coalesced` (satisfied by a capture
within `maxAgeMs`). The future judge path cares WHY visual evidence is
unavailable.

### 12.2 Observation stamps: sequence + monotonic + wall

Records carry `seq` (monotonic within run — the operational freshness
basis), `monotonic_ms` (process clock), `wall_ms` (diagnostics only),
`reason` (lifecycle phase, rule 6). The WorldModel's logical `tick` is
renamed to this `seq` discipline; no C# tick endpoint in R2 (it becomes
worthwhile only with long-lived knowledge, concurrent observers,
time-decay, save/reload).

### 12.3 Resource records: raw identity kept, extent flagged

Cluster records carry BOTH raw identity and normalized class:
`code` (e.g. `crop-flax-7`), `kind` (`crop`/`ore`/`rock`/...), `material`
(`flax`/`granite`/... — crops are NOT collapsed to a bare `crop`),
`properties` (e.g. stage), `observed_quantity = len(cells)`,
`is_complete_extent = False` always in R2. Clusters are keyed by
(kind, material); IDs are stable within a run/snapshot (rule 5), not
globally.

### 12.4 Job-effect catalog (P3 design hole closed)

Jobs carry **deterministic effect semantics** in a shared catalog
(`r2/jobs.py`), so validator, executor and planner schema all agree on
the same job semantics instead of each inventing rules:

```
mine    requires: target resource      effect: +material × n
place   requires: inventory material n effect: −material × n
harvest requires: crop fixture         effect: +harvest result (item)
goto    inventory effect: none
```

Deliberately crude in R2; the architecture is the point.

### 12.5 Goal grammar is verb-specific (no placeholder fields)

`goto`: requires `at`; object/n irrelevant. `mine`: object required, n
optional (default 1), at optional/candidate-resolved. `place`: object +
at, n optional (default 1). The grammar check rejects fields a verb does
not use — fake placeholders are a validation failure, not padding.

### 12.6 Validator ≠ oracle

`plan_valid` (deterministic checks over the snapshot: types,
symbolic references IN THAT SNAPSHOT, quantities, grammar, dependency
order, source/material compatibility, ledger simulation) is a different
guarantee from `action_precondition_current` (fresh same-step
observation). The validator may use observed availability to judge
plausibility; it never implies the resource will still exist at
execution.

### 12.7 P5 measurement conditions

Strict JSON is the correct baseline. Measured separately: **A** raw
model (parse / schema / semantic success), **B** same model + one
semantic repair turn (validator error strings fed back; repaired
success). Mechanical syntax-repair middleware is a separate experimental
condition (C), reported apart — it must not silently improve A. Planner
context stays minimal: schema/version + `projection_id`, goal, relevant
bot inventory, allowed job types, candidate resources
(id/material/observedQuantity), candidate sites, execution semantics,
output schema. **No coordinates** in the projection.

### 12.8 Amended order + the material capability probe

The live material capability probe moves **before the P4/P5 schema
freeze**: mine one known-NATURAL granite → inspect the exact inventory
delta/item code → select it → place once. The probe establishes actual
drop code, quantity behavior, normalization, and whether place accepts
the representation, BEFORE material-compatibility rules are encoded in
`plancheck`. (R2 caveat: set-placed rock blocks yield no item in 1.22 —
block removal only — so the probe must use natural stone variants.)

Amended execution order:
P2 → material probe → P3 (contracts + job-effect catalog) →
P4 (planner projection + inventory-ledger validator) → P5 (27B
measurement, conditions A/B) → P6 (JobQueue + live two-job milestone).

## Status log (append-only)
- **2026-09-28 (night run, review round 3) — amendments §12 adopted.**
  Phase 2 in execution: `r2/{queries,worldmodel,observation}.py` built
  per the amended shape (seq/monotonic/wall stamps, reason-tagged
  observations, kind/material resource records with observed_quantity +
  is_complete_extent, ObservationService with the five-outcome taxonomy,
  fake-transport tests only). The next gates: T5 staleness (both
  polarities: stale-filled + fresh-empty ⇒ NOT complete; stale-empty +
  fresh-filled ⇒ complete), nomination-vs-authorization, then the live
  material capability probe, then P3–P6 per §12.8.
- **2026-09-28 (Phase 2 complete, ~03:20 CEST).** WorldModel +
  ObservationService built per §12 and wired under the live loop:
  `r2/worldmodel.py` (seq/monotonic/wall stamps, reason-tagged
  observations, freshness-gated fixture reads - unknown is never
  yes/no, nomination vs authorization, claims view, worldSnapshot),
  `r2/queries.py` (classify + connected-cluster with observed_quantity
  and is_complete_extent=False), `r2/observation.py` (5-outcome
  taxonomy, maxAgeMs coalescing; fake-transport unit tests only - the
  three live screenshot consumers stay untouched per 12.1). v5's run
  loop now feeds its own stamped observations in and records the
  worldSnapshot in the run JSON (§7; per-run outcomes are now
  persisted in the --out file). New gate test T5 (staleness invariants,
  both completion polarities, monotone satisfaction, nomination-only
  resources): gate is T1+T2+T2b+T3+T4+T5, green on --impl v5 AND
  --impl r2. Live verification (same params as the T4 goldens): mine
  2 steps, harvest 2 steps, build 3 steps - all complete; per-step
  phase/proposal sequences match the T4 goldens; the worldSnapshots
  show the expected reason-tagged logs and fresh oracle confirmations.
  Two model-level wobbles observed (NOT code drift - recorded for the
  canary/dashcam watch list): (1) mine step 1: Laya p=0.286 <
  tau_yes on travel -> 27B judge goal-first-skipped to mine_target
  (executed fine - privileged harness action - mission still 2 steps);
  (2) harvest step 1: Laya p=0.40 exactly at tau_strong ->
  consensus-hole escalation -> judge harvested early (2 steps vs
  golden 3). Both are the known travel-phase bias / boundary behavior
  of the small models, not the loop. Next: the material capability
  probe (12.8), then Phase 3 (job contracts + effect catalog).

## 12.9 Material capability probe — findings (2026-09-28, ~04:30 CEST)

Executed per §12.8 before the P4/P5 schema freeze
(`scripts/probe-material.py`; JSON: `data/material-probe-<date>.json`).
Findings, live-verified against the 1.22 testbed:

1. **Drop code.** Mining a `game:rock-granite` block (the code shared by
   set-placed and any granite block in this world) yields the item
   **`game:stone-granite`** — not `rock-granite`.
2. **Quantity.** 2–3 items per single-cell mine (autocollect); treat
   expected yield as ≥1, measured, never assumed.
3. **Normalization.** `stone-granite` and `rock-granite` are DISTINCT
   materials in the ledger: the mined raw stone vs the placeable stone
   (what `give`/`give_tool` provide and what `place` consumes).
4. **Place acceptance.** The harness `place <blockcode> x y z` resolves
   a BLOCK code and matches inventory items by exact code; it accepts
   `rock-granite` items and rejects `stone-granite` ("Unknown block").
   Vanilla right-click can place raw stone, but the public 1.22 API
   exposes no item→block mapping (checked the API surface: no
   IPlaceable, no Item.GetBlock) — so the harness cannot mirror that
   path without internal-API surgery, which is not acceptable for a
   repo staged for public release. No C# change made.

**Consequence for the Phase 6 two-job milestone (honest rescope):**
a mine→place material chain is NOT currently executable end-to-end in
the harness (the mined material needs a stone→rock conversion the game
exposes only as internal placement). The live two-job milestone is
therefore re-scoped to a goal whose jobs the executor can actually run:
**`give_tool` (external source, ledger: +material) → `place` (ledger:
−material)** plus a second independent job type to make it a real
two-action sequence (`harvest`), i.e. goal "harvest the crop and place
granite at the site" → jobs [give_tool granite, harvest crop, place
granite@site]. The mine→place case is NOT dropped — it moves into the
P5 planner fixtures as the validator's strongest semantic test: a
naive [mine granite, place granite] plan must be REJECTED by the
inventory-ledger simulation (mine yields stone-granite, place needs
rock-granite) — the validator doing real work, not rubber-stamping.
A future `craft/convert` job type (stone→rock) is the follow-up that
makes mine→place live; it needs a game-exposed conversion (grind/press
candidates) and is out of scope tonight.

## Status log (append-only)
- **2026-09-28 (material probe complete, ~04:35 CEST).** Probe results
  above recorded; the Phase 6 milestone is re-scoped per §12.9
  (give_tool→place + harvest as the second job type; mine→place lives
  on as the P5 validator rejection case). Next: Phase 3 (r2/jobs.py —
  job catalog with effect semantics, goal grammar, failure taxonomy),
  then P4 (planner prompt + ledger validator), P5 (27B measurement),
  P6 (JobQueue + live milestone + honest rejection).

### 12.10 Phase 6 live outcomes (2026-09-28, 04:00-05:10 CEST)

Ten live runs on the testbed via `scripts/r2-live-mission.py`
(`data/r2-live-2026-09-28-01..10.json`):

1. **One-job GOAL COMPLETE - verified live** (run 05): goal
   "place granite at site-A x1" with the bot pre-supplied one
   rock-granite (operator setup, recorded in the run JSON) -> the 27B
   proposed a single place job -> validator passed -> the queue
   executed it (goto + place) -> the FRESH oracle (site filled)
   confirmed -> `goal_complete` in 8 s. The full chain
   (intake -> world observation -> planner -> goal-aware validator ->
   JobQueue -> executor -> oracle) works end to end.
2. **Honest rejection - verified live 8 times** (runs 01, 02, 03, 06,
   07, 08, 09, 10): the model rejected with reasons; the pipeline
   recorded `unsupported_goal` and terminated safely without
   executing. Notable: "site-A already has granite" (a stale site
   from an earlier pass - the model was right) and "no granite in
   inventory and no producer yields granite" (world fact: granite
   drops stone).
3. **Two-job live completion - NOT achieved; recorded as a finding,
   not a defect.** For every supply goal (empty inventory, no world
   producer of the placeable material) the 27B rejected, consistently
   and fluently ("only 3 sources of qty 1 each", "no external supply
   justified"). Prompt interventions were MEASURED, not asserted:
   making give_tool MANDATORY in rule 6 (run 09) and a worked
   few-shot example (run 10) did not change the outcome. The model's
   prior (matter must come from the world) is not prompt-overridable
   at this size.
4. **Prompt A/B regression discipline.** The experimental prompt edits
   made while chasing (3) - a measured/assumed drops label, "FILLED"
   fixture wording, a split rule 9 - regressed the 25-case P5 suite
   20/25 -> 18/25 (r5), with C3/E1/G2 each attributable to a specific
   edit. Reverting to the r4 prompt (keeping only an int() quantity
   guard) restored 20/25 (r6). **The planner prompt now changes only
   through an A/B against the 25-case suite.**

**Remediation options for the supply-plan refusal** (user decision):
(a) operator declaration at intake: a goal may carry a
`supply: external` flag (the operator decides when the goal is set);
the orchestrator then inserts the give_tool job for the shortfall
DETERMINISTICALLY, before the planner sees the goal - the planner
only plans world actions. Fits the ownership table (operator owns the
goal, planner proposes, validator decides) and needs no model
training.
(b) a fine-tuned planner (the decider's proven FT pattern) on the P5
fixtures plus labeled supply goals.
(c) accept the refusal as R2 planner policy: supply goals are an
operator-level operation, not a planner-level one.
**Recommendation: (a).** With (a) the two-job live milestone
([give_tool, place]) becomes executable without any model change; the
sequential execution itself is already covered by the queue unit
tests (13/13) and the P5 validator fixtures.

## Status log (append-only)
- **2026-09-28 (Phase 6 complete, ~05:15 CEST).** JobQueue (r2/
  jobqueue.py, 13/13 unit tests) + r2-live-mission.py. Live: one-job
  GOAL COMPLETE (8 s) + 8 honest rejections verified; the two-job
  live completion is blocked by the 27B's supply-refusal prior
  (finding 12.10.3) - remediation (a) is the recommended follow-up.
  The planner prompt is back at the r4 wording (r5/r6 A/B); prompt
  changes are now suite-gated.
