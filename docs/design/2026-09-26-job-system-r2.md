# R2: the job system + world model — goals become job lists, the cascade stays the reflex

**Status: design (frozen 2026-09-27, 14th pass).** Started 2026-09-26 (11th pass);
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
