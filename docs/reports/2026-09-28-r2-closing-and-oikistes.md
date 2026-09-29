# 2026-09-28 — R2 closing sequence complete; Oikistes inaugurated

Status report for the 13.6 closing sequence (steps 1-6) and the
inauguration of the settlement agent. Companion to the design doc
`docs/design/2026-09-26-job-system-r2.md` (§13.7-13.9), which carries
the full evidence; this report is the condensed picture.

## Where the R2 job system stands

| Milestone | State |
|---|---|
| M1 (supplied-material two-job: operator-give → place) | **CLOSED** (run 11, 8.5 s) |
| M2 (endogenous production → consumption) | **CLOSED** (run 31, 9.6 s: harvest mature rye → measured seeds+grain → sow a new crop on the farmland; oracle-verified) |
| Planner (27B, structured goals) | precision **1.000** across ten rounds; coverage **0.48-0.62** (variance across runs); the 5-way attribution (P5 r10) puts the *entire* offline failure mass in the **model** layer (6/25: over-rejections + one wrong pick; validation/observation/executor/environment all zero) |
| Deterministic compiler | owns the structured verbs: mine, harvest, sow (the two-job chain), place-from-inventory |

Two model-capability findings, both measured, both now design inputs:
1. the 27B **refuses external supply** and, on the *new* `sow`
   vocabulary, **degenerates into a silent token loop** (thinking on:
   the whole budget burns invisibly; thinking off: clean).
2. the 35B conversational model has the same thinking-degeneration
   trait; on its 12 GB GPU it also runs at the memory edge (a crash +
   ~1 min reload was measured today and survived by the service).

**The planner fine-tune is deferred** (13.9): the 27B is the
production judge (not a training target), the deterministic compiler
has taken the structured cases, and the remaining job (the ambiguous
long tail) needs its own small model and a real corpus — the corpus
program starts with the rejection data already collected.

## Oikistes (οἰκιστής) — live

`scripts/oikistes.py`: the settlement's builder manager. A 35B-class
text model with a lean tool surface over the harness:

- **observe**: state / scan / screenshot / events / autonomy-read
- **act**: mission (the R2 job system — the only way work gets done),
  give, and — `free` autonomy only — direct harness commands
- **policy**: the mod-owned autonomy preset (strict/guarded/free,
  world config) is read on every turn and enforced in the execution
  path — the model proposes, the gate disposes, and the agent can
  never change its own autonomy. 24/24 gate tests.
- **lean & resilient**: compact observations, single-flight chat,
  rolling transcript memory, string-arg normalization, model-reload
  wait-out, honest failure reporting (a failed tool call is fed back
  as an observation — and the demonstrably self-correcting agent
  recovered from its own compound-goal syntax error on the first live
  order).

Every actuation carries `actor=oikistes` and lands in the event
stream; the run JSON stays the persistence of record for missions.

## What is missing for an actual test run (assessment)

**Ready now:** scoped missions on the testbed, end-to-end and
honest; the agent loop; monitoring + dashcam; the full evidence
trail. A *piloted* run (operator at the UI, agent at `guarded`)
could start this week.

**The gaps, in order of bindingness:**
1. **Survival vocabulary** — craft (knap/clayform/press exist as
   harness commands but have no job types), smelting, eating,
   tool wear. A real world kills a bot that can't eat; the testbed
   never does. First additions: a `craft` job type + a food job.
2. **Memory across missions** — the world model is rebuilt per boot
   and the agent's memory is a rolling transcript. A multi-day
   campaign needs: persistent resource map, episodic memory (what
   was built where), and a goal stack (long objective → daily
   missions). The run JSON already stores everything; the aggregation
   is the work.
3. **Model stability** — the 35B at the edge of a 12 GB card (crash +
   reload measured); the 27B degeneration needs a guard
   (finish=length with empty content → classify as rejection, retry
   once with smaller budget).
4. **Repair path** — the `repair` job origin exists; the loop that
   turns a failed mission into a repaired re-plan is not built.
   Until then, failures end honest (`abandoned` + reason), which the
   testbed runs demonstrate is survivable.
5. **World** — the testbed is a handcrafted pocket (no trees, flat
   ground, one farmland). The first "real" pilot should be a fresh
   small world with staged variety (trees, water, a slope), 3-5
   permadays, goal: "a small base — wood, a platform, a working crop
   plot", agent at `guarded`, operator only on failure.

**A/B (same battery, both brains, live today):** the 27B (vLLM
judge engine, always-on) and the 35B (llama.cpp mux) are a near-tie
on this work - inspection in 7-9 s, the endogenous sow mission in
13.5 s each, both with correct tool choice and honest reporting.
The 27B is marginally more thorough (double-scan), the 35B marginally
more frugal (single scan). Given the 35B's memory-edge instability on
the 12 GB card, the **27B is the default brain**, with the 35B kept
as the swappable alt (`POST /oikistes/model` / the UI selector).

**Verdict:** the architecture is done; the pilot is a vocabulary and
memory problem, not an architecture problem. The two-tier design
(reflex 2B / judge 27B / deterministic compiler / conversational
35B) survives contact with the real world; the binding constraint is
the action space, not the planning.

## 09-29 follow-up: the build verb

The first real conversation ended at the vocabulary wall (the agent
suggested buildings it could not order). The response, overnight:

- **`build <material> xN at <site>` is a live goal verb**: one
  composite job places N blocks as a ring platform at the site,
  verified per attempt (the engine silently refuses a place into the
  bot's own cell while the place command reports ok=True - the
  oracle is the only ground truth for placement; this is the
  execution-vs-oracle split doing its job on day one).
- First platform: site-A, GOAL COMPLETE in 11 s (run 29-2, delta=4,
  a phantom caught and retried). The 27B also produced a valid build
  plan unaided, first try - noted for the record; the deterministic
  compiler is the default path.
- **P5 r11** (gate for the prompt's build contract line): 20/25,
  precision 1.000, coverage 0.524 - inside the measured variance
  band of the same prompt family (r8 0.476 / r9 0.619); all
  failures the known over-rejection species. r9 remains the
  reference baseline.
- Residual, recorded not chased: placement geometry at head-height
  ring cells is vantage-dependent (a C#-harness question - how
  `place` approaches a target one layer up), most visible when a
  second build overlaps the first ring. The failure message now
  says exactly that, so the agent can choose a fresh site.
- Next verb: **craft** (knap/press/clayform harness commands into
  job types) - the workbench, then the furnace. Phase 7.
