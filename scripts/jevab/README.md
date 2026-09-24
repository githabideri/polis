# Jev A/B harness — Decider 2B vs SemIf 4B vs Laya 421M (the polis decision class)

Runs the polis labeled corpus (`../../data/labeled-set-2026-09-22-*.json`, 41
merged rows) through the two 2026-09-20 "Open Jev" candidates as *choice*
questions over the mission action set, and reports top-1 vs oracle, p(oracle),
multiclass Brier, per-row latency, and calibration split. Answers: does a
2B/4B model fix the p-band overlap that disqualifies the 421M reflex in the
concrete-observable regime, and at what cost?

Verdict lands in `docs/reports/2026-09-22-bot-cargo-and-decision-harness.md`
(§12) + the llmlab handoff report.

## Where it runs

Dedicated unprivileged LXC **the CPU batch box** on  (4 cores, 16 G since
2026-09-24, IP the CPU batch box). No GPU — this is an offline batch verdict, not
a live service; deployment latency for a winning model is a GPU question
decided after the accuracy verdict. Not the vLLM CT (324): prod inference
boxes do not host bench work.

## Layout on the CT

```
/var/jevab/
  ab-runner.py            # this dir's copy (Decider: device="cpu"; SemIf: bf16)
  supervisor2.sh          # serial: decider -> semif; gated on markers; 30-min recheck
  setup-venvs2.sh         # idempotent venv build (py3.13, torch-CPU, transformers)
  src/SemIf/src/          # TheoLeeCJ/SemIf (worktree restored from the 2026-09-22 clone)
  corpus/data/*.json      # the labeled sets (canonical copies from data/)
  weights/decider-2b -> /models/jevab/decider-2b    # symlinks
  weights/qwen3.5-4b -> /models/jevab/qwen3.5-4b
  results/<model>.json    # summary; <model>.json.rows.json = per-row sidecar
```

## Model provenance (weights: shared store, NOT CT rootfs)

Weights live on the host's shared model store **`/models/jevab/`** (mounted
into the CT; `mp0` in the LXC config) — the lab pattern for model files.
Host-side `hf download` writes them; completion markers
`/models/jevab/<dir>.done` gate the supervisor.

| model | HF repo | notes |
|---|---|---|
| Decider 2B | `Mapika/decider-2b` | ships its `decider/` Python package inside the weights dir (PYTHONPATH). CPU: `Decider(path, device="cpu")` → `use_graphs=False`, pure-torch reference gated-delta-net (no fla). bf16. |
| SemIf 4B | `Qwen/Qwen3.5-4B` | frozen base model, letter-slot logit readout via `semif_phase1.direct.score` (PYTHONPATH). bf16 (fp32 needs ~16 G weights, over the cgroup). |

## Operational notes

- `systemctl start jevab2` runs the supervisor; the old 4-model
  `jevab-supervisor` unit is stopped+disabled (superseded; its 2026-09-22
  skip placeholders are kept in `results/skipped-2026-09-22/`).
- Re-run a single model: delete `results/<model>.json` and let the 30-min
  recheck pick it up, or run the runner line by hand (see `supervisor2.sh`).
- Collecting results: copy `results/<model>.json{,.rows.json}` to
  `../../data/` as `ab-<model>-2026-09-24.json` and commit.
- If the box must be rebuilt: `./setup-venvs2.sh` (idempotent) is the only
  in-CT setup; SemIf source re-clones from `https://github.com/TheoLeeCJ/SemIf`
  (2026-09-22 clone was at `1f2dea3`).
- The Decider/SemIf run originally attempted on the 27B box (2026-09-22/23) never
  produced results: HF weight downloads stalled and the host was reinstalled
  2026-09-23 (the toolchain was recovered from the old rpool, now imported
  read-only as `oldrpool` on the 5600X host).
