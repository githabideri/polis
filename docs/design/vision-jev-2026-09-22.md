# Vision-Jev: typed decisions from game screenshots (design)

**Status: design — not yet deployed.** 2026-09-22.
Sanitized: hardware referred to by role, not name.

## 1. Why

The decision loop (`scripts/jev-loop-v4.py`) is text-state driven: the bot's
state is serialized to a structured string, Laya answers a `noul` veto, the
27B judge resolves doubt. Everything the bot "knows" comes from what we choose
to serialize. That leaves three blind spots a camera fixes:

1. **Scene verification.** `marker_present=yes` is a block-code scan; a
   screenshot confirms the marker is actually visible and in the expected
   place (guards against scan/aliasing bugs like the DDA boundary case).
2. **Wedge detection.** The 2026-09-21 wedge showed up as *zero pixel
   change* across screenshots minutes apart while the world was supposedly
   live. A "has the frame changed at all?" noul question is a cheap, robust
   world-alive probe — the exact check that was missing.
3. **Ambiguity escalation.** When the text state is genuinely ambiguous
   (e.g. `near_target` heuristic and the block scan disagree), a vision
   noul ("is the target block visible in front of the bot?") is the natural
   arbiter — and a 2B vision model answering one typed question is exactly
   the Jev shape.

## 2. Model candidates (two consumer GPUs, ~2 GB VRAM each, sm_61)

The vision model must fit **one 2 GB card at int4/int8, batch 1** and must
emit **typed decisions in one forward pass** (no generation).

| Candidate | Base | Why it fits | Risk |
|---|---|---|---|
| **decider-2b-vision** (Mapika) | Qwen3.5-2B-VL | Same wire format as the text loop (choice/score/noul, one forward pass, per-option probabilities, TypeSafe-compatible). Published: 10 held-out image questions, 59 ms median on a datacenter GPU. int4 ≈ 1.3–1.5 GB → fits 2 GB. | Newest of the four 2026-09-20 models; Pascal (sm_61) support for the Qwen3.5 architecture unproven — transformers ≥ 5.17 + CUDA 11.8/12.4 build needed. |
| MiniCPM-V 2.8 | MiniCPM | Battle-tested on 2 GB cards (int4). Mature tooling. | Answers by generation → needs a logit-readout head or a parse layer; not natively typed. |
| Qwen2.5-VL 3B | Qwen2.5 | Strong, well supported. | 3B int4 ≈ 2 GB → at the edge of the card; same sm_61 question. |
| ~~27B / 26B class~~ | — | Out: 14+ GB int4 minimum. | — |

**Primary: decider-2b-vision**, because it is the same decision family as the
text loop (and as Decider 2B in the A/B harness on the CPU container): one
served model class, one calibration discipline, two input modalities.

## 3. Interface

```
harness observer-screenshot (PNG, base64, 1920x1080)
        │
        ▼
image question  ──┬─ noul: "is the stone marker block visible?"
                  ├─ noul: "has this frame changed compared to the previous one?"
                  └─ choice: "what is the bot facing? [stone | crop | empty | wall | other]"
        │
        ▼
one forward pass → per-option probabilities → same threshold discipline
as the text loop (calibrated per (model, question) on a labeled screenshot set)
```

The screenshot endpoint already exists in the harness (teleport-observe-
restore; 4–5 s spacing or `wait_stable()` — see the visual-proof report).
A vision question costs one screenshot + one forward pass.

## 4. Host & memory policy

- Runs on **the GPU LXC** (the box with the two consumer GPUs that also
  hosts the WhisperX transcription service).
- **One card per service**: vision-Jev takes the faster card, WhisperX keeps
  the other. No time-slicing in v1 (both are low-frequency: WhisperX runs on
  demand, vision-Jev answers at most a few times per mission step).
- sm_61 (Pascal): no FP16 tensor cores, no FP8 → int4 (GPTQ/AWQ) or int8
  (bitsandbytes) only. Batch 1. Downscale images to 768–1024 px on the long
  edge before encoding (the full 1080p PNG is overkill for "is the marker
  visible").
- Provenance: model repo + revision + quant method recorded in the run
  metadata (campaign-discipline law).

## 5. Phases

- **P1 — smoke (a day):** get decider-2b-vision int4 serving on the GPU
  LXC; answer three hand-picked noul questions against the committed
  visual-proof screenshots (`docs/proofs/2026-09-22-harvest/`). Go/No-Go:
  correct on the crop-present / crop-gone pair and the marker question.
- **P2 — labeled screenshot set (a few days of mission runs):** every
  mission step in the harness writes a small screenshot + label to
  `data/screenshot-set-*.json` (same shape as the text labeled sets).
  Target: ~200 labeled frames covering marker-present/absent,
  crop-present/gone, night/day, changed/unchanged. Calibrate thresholds.
- **P3 — loop integration:** the harness escalates to a vision noul when
  (a) the wedge probe fires (frame unchanged), or (b) the text state
  contains a `disagreement:` line (scan vs heuristic conflict). Vision is an
  *escalation path*, never the fast reflex — the 421M text noul stays at
  the hot seat (33 ms vs ~1 s).

## 6. What this is not

- Not a VLM that "plays the game" by generation. The typed-decision
  constraint is the whole point: one forward pass, probabilities over a
  declared answer set, nothing to parse.
- Not a replacement for the block scan. Vision answers questions the text
  state cannot; the structured state remains the primary input.
- Not on the game container (no GPU there). Screenshots cross the LAN;
  decisions come back as JSON.

## 7. Open questions

- Does the Qwen3.5-VL architecture load on a Pascal-era CUDA toolchain at
  all? (Check `torch.cuda.is_available()` + a 2B int4 load before buying
  anything else.) Fallback: Qwen2.5-VL 3B int4, then MiniCPM-V 2.8.
- Frame-difference noul: does the model do perceptual diffing, or does it
  need the two frames side-by-side in one prompt? Decide in P1.
- Cost per screenshot-question on a 2 GB Pascal card: measure, don't guess
  (the 59 ms figure is a B300).
