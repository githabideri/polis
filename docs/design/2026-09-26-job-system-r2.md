# R2: the job system — goals become job lists, the cascade stays the reflex

**Status: design.** 2026-09-26 (11th pass). Supersedes nothing; extends
`archive/VISION.md` (phase 2) with the model stack as measured through
11 passes.

## 1. Where we are

Phase 1 (done, live on the game testbed): one bot, one mission at a time, driven by
the v5 loop — a phase machine over the serialized state, with the
three-tier cascade (Decider-2B reflex → Laya noul → 27B doubt-arbiter)
deciding each step, and a last-resort repair. Three mission families are
live and complete (mine / harvest / build), the 7-option reflex
vocabulary is closed, the reflex is fine-tuned (round 2 in progress) and
drift-guarded (nightly canary).

What the current architecture is, precisely: **a single-job driver**.
The mission *is* the job; the phase machine *is* the JobDriver; the
fixture *is* the reservation; the step budget *is* the anti-thrash.

## 2. What R2 adds (and what it deliberately does not)

R2 adds the **planner**: a goal arrives (natural language or structured),
it becomes an **ordered list of jobs** (the mission families we already
run), and a **job queue** feeds them to the existing driver one at a
time. Everything per-step stays exactly as measured in §12–18: the
reflex option set, the cascade, the thresholds, the canary.

Deliberately deferred to phase 3: multi-bot scheduling, the RimWorld
reservation manager (deadlock prevention across bots), scoring-based
matching, aging priorities, tick throttling. Single bot, one claimed
target at a time, keeps every reservation trivial (a set of claimed
cells in the job record) and keeps the model contract unchanged.

## 3. Architecture (RimWorld terms → what we actually have)

```
Goal  (e.g. "build a 5-block wall here from granite")
  │  planner (27B, goal-first, thinking off, few-hundred-ms)
  ▼
Job list  [ {mine granite @ pocket}, {build: place granite @ site} ]
  │  job queue (claim per job; budget per job; status:
  │  ready / running / blocked / done / abandoned)
  ▼
JobDriver  = the v5 phase machine, one job at a time
  │  per step: reflex (Decider-2B FT) → Laya noul → 27B judge →
  │  last-resort repair; stall valve per job budget
  ▼
Toils  = the harness actions (goto / mine / harvest / pickup /
         place / give_tool), unchanged
```

- **Goal grammar (v1):** `{verb, object, at, n}` — verbs restricted to
  the live mission families (mine / harvest / place / goto). Anything
  outside the grammar is a planner rejection, not a planning attempt
  (the reflex is never shown goals it cannot execute; same discipline
  as the 7-option set).
- **Planner = the 27B as goal-parser.** The 27B is already goal-first
  (§15: it jumps straight to the goal action, not the phase). A
  structured goal → jobs prompt with the job-family catalog and the
  world scan as evidence; output is a JSON job list. **Deterministic
  post-checks** gate the plan: every job's `at` must be scannable,
  every material must be claimed to a source (a pocket / a crop), the
  order must respect dependencies (material before use). A plan that
  fails the checks is returned to the planner once, then to the user
  (no silent re-planning loops).
- **WorkGiver / scanner:** the harness `scan` + `verify` commands are
  the scanner (target discovery by block code / item code in a radius).
  The planner prompt carries a compact world summary (claimed cells,
  known fixtures, bot inventory) — the same facts channel the reflex
  reads, so the tiers see one world.
- **Job = the v5 mission, plus:** `claims` (cells reserved for this
  job), `budget` (max steps; on exhaustion the job is *abandoned* —
  not retried in place; the planner may re-queue it as a fresh job, and
  a second abandonment of the same goal escalates to the user with the
  state trail). The stall valve (§15) stays the per-job backstop.
- **Completion:** a job completes when its fixture condition holds
  (mine: marker gone; harvest: crop gone + item carried; build: site
  filled — the per-mission checks already implemented). A *goal*
  completes when its last job completes; the loop reports
  `goal_complete` exactly like `mission_complete` today.

## 4. Model placement (what changes and what doesn't)

| tier | today | under R2 |
|---|---|---|
| reflex (Decider-2B FT) | 7-option readout per step of one mission | **unchanged** — it sees one job at a time; jobs are the missions |
| Laya noul | anchored yes/no veto | unchanged |
| 27B judge | per-step doubt-arbiter | unchanged + **also the planner** (separate prompt/contract: plan-out, not step-out) |
| last-resort repair | policy fallback | unchanged, per job |

The reflex is never asked to plan; the planner is never asked about a
step. The §16/§17/§18 calibration work (world reading, OOV
generalization, wait-escape) carries over untouched because the per-step
contract is byte-identical.

## 5. Milestone (definition of done for R2)

1. **Two-job goal live:** "mine the granite in the pocket and build a
   pillar here" → planner emits [mine, build] → both jobs complete in
   sequence, `goal_complete=true`, with the job list and per-job
   fixture checks in the run JSON.
2. **Dependent material flow:** the build job's material is the mine
   job's drop (inventory hand-off between jobs — the bot carries it;
   no new action, `give`/`drop` only if needed).
3. **Rejection is honest:** a goal outside the grammar ("make a
   bread") returns a structured rejection with the reason — not a
   silently mis-planned job.
4. **Reflex regression gate:** the nightly canary and a 4-fixture live
   A/B (mine/harvest × d12/d20) run before and after; the per-step
   cascade numbers must not move (they cannot — same contract).
5. **No new thresholds:** R2 introduces no new tau; the planner's
   plans are deterministic-checked, and its only "probability" is the
   27B's, which stays inside the judge's existing contract.

## 6. Open questions (for the R2 implementation pass)

- Planner prompt: one world summary, or the per-job scans resolved by
  the scanner first (planner sees candidate cells, not raw scans)?
  Lean: scanner-resolved — smaller prompt, fewer hallucinatable
  coordinates.
- Where the job queue lives: in the v5 process (simplest) vs a
  persistent store (survives restarts; needed once goals span
  maintenance windows).
- Natural-language goals: the 27B parses them into the grammar; the
  grammar check is the trust boundary (a parsed goal that fails the
  checks is rejected, never guessed at).
