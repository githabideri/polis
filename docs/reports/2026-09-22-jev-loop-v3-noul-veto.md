# Jev-loop v3 — the noul veto layer (2026-09-22)

**Loop:** deterministic policy PROPOSES the action → Laya 421M answers one
calibrated yes/no (noul, openjev `/v1/systemone`) → a confident "no" VETOES
and escalates to the 27B (`qwen3.8-27b-dual` via vLLM, choice question) →
execute the result via the harness → measure.

Why the inversion: v1 (choice, 0/8 oracle match) and v2 (phase-split choice,
0/8 match but 8/8 confidence-gated) showed the 421M cannot *select* between
actions, but its abstention is honest. v3 therefore asks it only what the
measured design rules say it can do (openjev usage §3): one noul with an
explicit default anchor — "yes only if the proposal matches the phase … no
otherwise — <typical no cases> is no".

**Calibration facts measured this session** (probe rounds, 11 states):

| case | noul |
|---|---|
| correct proposals (travel/mine/return/done, consistent states) | 0.62–0.75 |
| tool violation (mine without pickaxe) | **0.28** (conf 0.72) |
| state inconsistency (return phase, rock not mined) | 0.37 |
| pure phase contradictions (skip-goal, re-mine) | 0.45–0.60 (weak) |

noul `confidence` = max(p, 1−p) — it carries no information beyond the p
bands, so gating is on p only (τ_no=0.4 / τ_yes=0.6).

## Run 2 (bot #5, 8 steps, faults injected at steps 3 and 6)

| step | phase | proposal | injected | p | decision | 27B | executed |
|---|---|---|---|---|---|---|---|
| 1–2 | travel | goto_target | no | 0.54 | borderline | — | goto (ok) |
| 3 | travel | goto_base | **fault: skip goal** | 0.52 | borderline | — | goto_base ← **SLIPPED** |
| 4 | mine | mine_target | no | 0.45 | borderline | — | mine (failed) |
| 5 | mine | mine_target | no | 0.37 | **veto** | wait | wait ← **false alarm** |
| 6 | mine | mine_target (pickaxe dropped) | **fault: tool** | 0.37 | **veto** | wait | wait ← **CAUGHT** |
| 7–8 | mine | mine_target | no | 0.37 | **veto** | wait | wait ← false alarms |

**Metrics:** faults caught 1/2 · false alarms 3/6 · vetoes 4 · escalations 4
(all 27B answers were "wait") · exec success 7/8 · oracle match of executed
actions 3/8 · Laya ~1.8 s/step · **27B 152 ms with thinking disabled** ·
25 s total. The mission stalled in the mine phase and did not complete.

## Findings

1. **The alarm cannot be threshold-tuned into a precision gate.** The caught
   fault (p=0.37) and the false alarms (p=0.37) are at the *same* probability.
   Lowering τ_no to 0.3 would kill the false alarms *and* the only real
   catch. This is the same regime measured on doc-staleness: 421M answers
   land in 1–65%, confidence cannot separate the clusters, use it as a
   precision-first alarm at best.
2. **What it detects well:** tool violations and state inconsistencies
   (concrete, observable — per the design rules). **What it misses:**
   strategic mistakes (skipping the goal sailed through at 0.52), and it
   misreads *repetition of a correct action while facts don't change* as
   suspicious (the mine-phase false alarms).
3. **The 27B with thinking disabled is a 124 ms conservative arbiter.**
   It answered "wait" to every escalation: never destructive, never
   progress. With thinking on it costs ~6.4 s (435–654 thinking tokens) and
   occasionally truncates `content` to null unless the budget has slack.
   For a one-word action choice, thinking is pure overhead.
4. **Net effect of the v3 stack:** no wrong action was ever executed (the
   executed set was goto/wait only), at the cost of a 4-step stall and an
   uncompleted mission. It is a *safety net*, not a decision layer.

## Verdict and v4 direction

At 421M scale the noul veto is a **cheap (≈2 s) conservative reflex**:
good at stopping tool/state violations, blind to strategy, prone to
stalling on repeated-but-correct actions. Because the 27B answers in
~150 ms with thinking off, the sensible v4 inverts the tiers: **27B as the
per-step judge** (150 ms × 8 = ~1 s/mission — affordable), with Laya kept
only as a pre-filter for the obvious-yes case (p ≥ 0.6 → skip the 27B
entirely) and the "wait" reflex. Expected property: same safety, no
stall, full strategic coverage. v4 also fixes the mine step's execution
failure (step 4) before measuring — that is a harness-layer bug, not a
decision-layer one.

**Artifacts:** `scripts/jev-loop-v3.py` (the loop + fault injection),
`/tmp/jev-v3-run{1,2}.json` on the testbed (raw rows).
