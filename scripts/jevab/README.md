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

- **The `weights/` entries must be real symlinks, not directories.** The 2026-09-22
  session left plain directories there; `ln -sfn target weights/x` then *adds a
  symlink inside* the existing directory instead of replacing it, and model
  loading fails with FileNotFoundError on the (empty) old dir. Rebuild recipe:
  `mv weights/x weights/x.old && ln -s /models/jevab/x weights/x`.
- The CT must be **restarted after adding the `mp0` mount** (PVE applies `mp*`
  at container start; a bind taken while the host dir was mid-replacement goes
  stale and the container sees a frozen dir view).
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

## GGUF / llama.cpp path (2026-09-24, 2nd session) — quantization floor + valid 4B

`gguf-runner.py` runs the Decider readout over a GGUF checkpoint in-process
through the llama.cpp C library (not the HTTP server: its logprob output is
post-sampling in current versions and cannot yield the pre-softmax letter
logits). Same prompt construction as the torch path (`decider.prompt.build`,
state_first, trailing slot), full-vocab logit row at the last prompt position,
`softmax(logits/1.3)` over the letter tokens. Tokenization is verified
token-for-token against the reference tokenizer before scoring (0 mismatches
observed). Output schema mirrors `ab-runner.py`.

`semif-post.py` maps the SemIf cli JSONL output (`--mode direct --backend
llamacpp`) onto the corpus oracle labels and emits the same summary schema.

| artifact | build | notes |
|---|---|---|
| Decider `Q8_0` (2.0 GB) | `convert_hf_to_gguf.py <hf-dir> --no-mtp --outtype f16` then `llama-quantize f16 Q8_0` | **`--no-mtp` is required**: the Qwen3.5 converter assumes MTP draft tensors and writes 25 blocks for this 24-layer, MTP-less fine-tune; without the flag the GGUF fails to load ("tensor blk.24.attn_norm.weight not found"). bf16-equivalent accuracy (report §13). |
| Decider `Q4_K_M` (1.27 GB) | same chain, `llama-quantize f16 Q4_K_M` | degrades the readout (top-1 0.537) — do not deploy. |
| 4B `UD-Q4_K_XL` (2.9 GB) | prebuilt, `unsloth/Qwen3.5-4B-GGUF` on HF | SemIf's own `llamacpp_backend` (n_gpu_layers=0, per-sequence state save/restore for the hybrid linear attention). |

Current llama.cpp main (2026-09-24) supports the Qwen3.5 hybrid
(gated-delta-net + MTP) natively (`src/models/qwen35.cpp`); the converter's
`--outtype auto` (dynamic ~15 bpw) is *not* loadable by the older llama.cpp
bundled in `llama-cpp-python 0.3.35` — build f16→Q8/Q4 explicitly.

**`llama-cpp-python` offline build** (the CT's PyPI access is flaky; no
prebuilt wheels exist for this package): fetch the sdist + its build deps
(scikit-build-core, pathspec, filelock, ninja, diskcache, jinja2, markupsafe,
pyproject-metadata, packaging) as files on a machine with good network,
`pip install --no-index --no-deps <wheels>` into each venv, then
`pip install --no-index --no-deps --no-build-isolation llama_cpp_python-*.tar.gz`
(the sdist vendors the llama.cpp source; no fetch at build time; the 0.3.35
vendor has `qwen35.cpp`).

**Gotcha: stale rootfs bind.** On the night of 2026-09-24 the running CT
started seeing a divergent, reduced view of `/var/jevab` while the host-side
just the container's mount out of sync (the PVE config/subvol themselves were
this CT, check the host-side subvol first; the data is safe.
