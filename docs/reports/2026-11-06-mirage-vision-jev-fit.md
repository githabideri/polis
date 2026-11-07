# Mirage 21 MB on-device vision model against the Vision-Jev design — negative

Date: 2026-11-06. Evaluation of Cactus Compute's **Mirage** (21 MiB, 51.3M
parameters, 2-bit; `Cactus-Compute/mirage`, Apache-2.0) as a candidate for the
three blind spots in [docs/design/vision-jev.md](../design/vision-jev.md).
Full technical benchmark (provenance, 110-image corpus, all capability
classes): the companion llmlab report
`2026-11-06-cactus-mirage-vision-evaluation.md`. This report is the
game-screenshot fit (Phase B) and the verdict for this project.

## Environment

The model ran in isolation on a 4-core CPU LXC (Intel i5-8500T, 12 GiB RAM,
no GPU) — the consumer-CPU class the vendor targets. No live game service
was touched; nothing was installed on any game host; no model was deployed
anywhere. Inputs: the six 1920×1080 screenshots from the 2026-09-22 harvest
(`docs/proofs/2026-09-22-harvest/viz8-*.png`, already committed here) plus one
side-by-side composite of `04` and `05`. Engine 4.0.0 / library
`cactus-compute` 4.0.1, model pinned at
`76c1e9e53381aca8fc3843c636216c96ff220122`, telemetry off. 25 calls, all
sequential, single process.

## Method

Ground truth first, model second. Each of the six frames was visually
verified by a human before any model call. The one clean discriminating pair
is **04 vs 05** (bot at the crop, then after harvesting): the green crop
bush next to the pale pillar is present in 04 and absent in 05; the yellow
rye cluster is present in both; the dropped carrots are not resolvable at
1920×1080. The question battery per frame: `describe` (objects + text),
`bush_visible` (yes/no/abstain), `rye_visible`, `facing` (6-way enum of what
is at the crosshair); plus one `changed` (yes/no) call on the 04|05
side-by-side. The form field name carries the question (a generic name makes
the model answer an unspecified default question — see the llmlab report).

## Results

| Question | 04 (bush present) | 05 (bush gone) | other frames |
|---|---|---|---|
| bush_visible | yes (p 0.68) ✓ | **yes (p 0.65) ✗** | yes (0.64–0.69) |
| rye_visible | yes (p 0.81) ✓ | yes (p 0.80) ✓ | yes (0.80–0.84) |
| facing (6-way) | **abstain (p − 0.94)** | **abstain (0.93)** | abstain (0.93–0.95) |
| changed (04|05 pair) | **no (p 0.59) ✗** — the frames are clearly different | | |

`describe` never saw the crop: the object lists for 04/05 are HUD elements
(tooltip text, minimap-as-"digital display", sky, field) plus the stone
walls rendered as "cabin" (04) / "shed" (05) — no bush, no rye, no pillar,
and the two frames come back nearly identical. The in-game tooltip is read
consistently as "Medium fertility soil (Grassy" (truncated string; the
reader's 320 px width appears to cut long lines).

Against the design's three blind spots:

1. **Scene verification (P1 "crop present / gone")** — fails. The
   discriminating noul question (bush present vs gone) answers "yes" in both
   states at nearly the same probability (0.68 vs 0.65). The model has a
   strong yes-bias (0.64–0.69 on every frame, including frames where the
   crop area is far off-screen) and cannot see the crop at the 512 px
   canvas resolution the model uses internally.
2. **Wedge detection ("has the frame changed?")** — fails as a learned
   probe (answers "no" to two visibly different frames), and it does not
   need to: the whole-frame pixel diff of 04 vs 05 is 84 % byte difference
   (camera micro-shift dominates), so a *deterministic* region-of-interest
   diff around the expected crop/scene area is the cheaper and more robust
   probe — no model required.
3. **Ambiguity escalation (scene context for the 27B judge)** — the
   `describe` output is parseable and mostly coherent, but it carries no
   game-domain vocabulary (stone walls are "cabin/shed/castle", the
   minimap is a "digital display", the rye is "wheat") and omits the very
   objects that make a scene state verifiable. As an escalation payload it
   would mostly add noise.

Reliability notes: 0/25 calls truncated on these frames (the Phase-A
truncation defect is concentrated on dense-text images, not on game
screenshots); outputs were deterministic across repeats; 1.5–3 s per call
on 4 CPU cores with ~190 MB RSS.

## Verdict

**NOT SUITABLE** as the Vision-Jev sensor in this release. The one question
the design actually needs for the verified harvest pair (crop present vs
gone) is answered wrong, the facing question always abstains, and the
frame-change question is both wrong and unnecessary (deterministic region
diff instead). The yes-bias plus uncalibrated probabilities disqualify it
as an arbiter regardless of which question is asked. The design doc is
unchanged: the planned sensor remains the Jev 421M (GPU, calibrated, typed
decisions).

If an on-device vision path is revisited, the failure analysis says what to
change before re-measuring: (a) region-cropped inputs (the crop area at
full resolution, not a whole HUD frame downscaled to a 512 px canvas),
(b) a model with game-vocabulary grounding (or fine-tuned on harvested
pairs like 04/05), (c) an abstention channel that actually abstains on
unresolved detail. Re-measure against the same verified pair before
considering any loop integration.

## Appendix — raw answers (all 25 calls)

Questions as field names: `bush_visible` = "Is there a green crop bush
with orange carrot tops next to the pale pillar in the middle of the
field?"; `rye_visible` = "Is there a cluster of yellow rye plants in the
field?"; `facing` = "What is at the center crosshair?" with options
stone_wall / crop_or_plant / farmland / empty_ground / sky / other;
`changed` = "Are the two screenshots on the left and right visibly
different?" `describe` uses the objects+text sections.

| frame | call | answer | probabilities (top) |
|---|---|---|---|
| viz8-01-before-story | describe | 7 objects | button, wheat field, sky, wheat stalk ×2, wheat field, text box |
| viz8-01-before-story | bush_visible | yes | yes 0.64 · − 0.27 · no 0.09 |
| viz8-01-before-story | rye_visible | yes | yes 0.81 · − 0.13 · no 0.05 |
| viz8-01-before-story | facing | − (abstain) | − 0.95 · stone_wall 0.03 |
| viz8-02-before-cropclose | describe | 6 objects | text overlay, building, sky, fence, field, wooden fence |
| viz8-02-before-cropclose | bush_visible | yes | yes 0.66 · − 0.25 · no 0.09 |
| viz8-02-before-cropclose | rye_visible | yes | yes 0.84 · − 0.11 · no 0.05 |
| viz8-02-before-cropclose | facing | − (abstain) | − 0.94 · stone_wall 0.03 |
| viz8-04-at-crop | describe | 6 objects | text, digital display, sky, cabin, field, text |
| viz8-04-at-crop | bush_visible | yes | yes 0.68 · − 0.25 · no 0.07 |
| viz8-04-at-crop | rye_visible | yes | yes 0.81 · − 0.13 · no 0.06 |
| viz8-04-at-crop | facing | − (abstain) | − 0.94 · stone_wall 0.04 |
| viz8-05-after-crop-gone | describe | 5 objects | text overlay, digital display, sky, shed, field |
| viz8-05-after-crop-gone | bush_visible | **yes (wrong)** | yes 0.65 · − 0.26 · no 0.09 |
| viz8-05-after-crop-gone | rye_visible | yes | yes 0.80 · − 0.13 · no 0.07 |
| viz8-05-after-crop-gone | facing | − (abstain) | − 0.93 · stone_wall 0.05 |
| viz8-06-return-mid | describe | 5 objects | text overlay, logo, sky, stone building, field |
| viz8-06-return-mid | bush_visible | yes | yes 0.69 · − 0.24 · no 0.07 |
| viz8-06-return-mid | rye_visible | yes | yes 0.81 · − 0.13 · no 0.06 |
| viz8-06-return-mid | facing | − (abstain) | − 0.94 · stone_wall 0.04 |
| viz8-07-at-base-carrying | describe | 6 objects | text, banner, sky, castle, grass, checkered border |
| viz8-07-at-base-carrying | bush_visible | yes | yes 0.69 · − 0.25 · no 0.06 |
| viz8-07-at-base-carrying | rye_visible | yes | yes 0.81 · − 0.12 · no 0.07 |
| viz8-07-at-base-carrying | facing | − (abstain) | − 0.93 · stone_wall 0.05 |
| pair 04|05 | changed | **no (wrong)** | no 0.59 · − 0.21 · yes 0.20 |

Text read from every frame (identical): "Medium fertility soil (Grassy".

Verification level: **locally verified** (single machine, single run, all
25 calls recorded verbatim in the llmlab benchmark directory
`results/phaseB-polis/`; the harvest screenshots and this report are in
this repo).
