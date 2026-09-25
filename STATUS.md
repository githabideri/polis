# STATUS.md — the single source of state

Updated: 2026-09-25 (7th–8th pass, ~14:00–17:00 CEST — **tau stress test done** (151 offline dual-p rows: no gate separates on the broad corpus — defaults kept at 0.35/0.50/0.40 by decision: gates = load control, 27B + last-resort repair = safety); **pickup phase verified live** (mine drops go to the inventory first, so the `--drop-after-mine` world event gives+drops a stone-granite at the mine site; first pickup-phase short-circuit: Laya 0.58 + Decider 0.73, GOAL 3 steps/27 s); **two loop bugs found + fixed** (the 3-tier gate silently ran Laya-only when only `--decider-fast` was passed; `mine_target` had no approach step — a goal-first mine from 12+ blocks away failed out-of-range and repeated until step budget, now gootos first); **world-variety corpus growth**: +240 rows → 363, base Decider Q8 top-1 61.8% → 71.9%, travel family 84% (the standing bias largely gone), B-substitution still 0/12 — the deferred gentle fine-tune is unblocked. Predecessor: 6th session (afternoon — 7-option reflex vocabulary live — `pickup_item` + `place_block` added to the Decider's option set (7 per mission, same letter positions), pickup phase live-wired in v5; corpus grown to **123 labeled rows** (60 generated pickup/place grid rows + all prior rows remapped: 41 A/B corpus, 30 give_tool grid, v5/v1-v4 live). **Fine-tune experiment on the the 12 GB 3060: negative result** — aggressive LoRA (r16/0.89% params, lr 1e-4, 4 epochs) collapsed the model (holdout top-1 76% base → 29% adapter, degenerate `give_tool` one-answer at p≈1.0); the base model needs less help than expected: it selects the new options **by reading the option list in the prompt** — 76/123 on the full grid, production Q8 identical (quantization-neutral), give_tool 10/12 (the 5-option era measured 0/12 — adding the option flipped detector→selector), place_block 6/6 when proposed; the 0/24 remainder is the documented spontaneous-substitution gap (upper tiers cover it). **Fine-tune deferred** pending corpus growth; gentle recipe recorded (r 4-8, lr 1-3e-5, early-stop). Live 7-option missions: mine 2 steps/42 s (fault corrected, return short-circuited), harvest 2 steps/26 s (fault corrected). Predecessor: 5th session (morning — tailnet approved, fast decider path 286 ms/row, first live short-circuit, 4 more labeled runs, detector-not-selector refinement on the 30-row give_tool grid; 4th session — overnight v5 three-tier loop, strong-gate, tau-strong re-derived to 0.40, give_tool as 5th action; 3rd session — Decider on the 3060 host, report §14; 2nd session — quantization floor 8-bit, first valid SemIf 4B measurement)
Game target: **Vintage Story 1.22.7** (released 2026-08-16). 1.23 expected before end of 2026.

## Overall state

| Layer | Level | Notes |
|-------|-------|-------|
| 1.22.7 code port | **locally verified** | net10.0, hermetic csproj, 5 API drift fixes; build: 0 errors |
| 1.21-era feature set (bots, A*, block actions, possession) | **live verified** (previous 1.21.6 testbed) | see `archive/KNOWN_ISSUES.md` for the detailed, per-feature history |
| CT-114 testbed (VNC + game + auto-login) | **live verified** 2026-09-20 | dialog-free boots since the moddata fix; see `ops/the game container-VNC.md` |
| Core loop on 1.22.7 (load → spawn → goto → verify) | **live verified** 2026-09-21 | harness :8585; short and long (100-block) gotos arrive; smoke-v1 mission **PASS** (move/give/inventory-assert/move-back) |
| Possession on 1.22.7 | **live verified** 2026-09-21 | possess → setcontrols (bot moved 53 blocks on held forward) → unpossess; NaN seat crash found & fixed (see below) |
| Block actions on 1.22.7 (setblock/give/mine/place) | **live verified** 2026-09-21 | place ok; natural-ground mine ok; rock mine gated by tool tier (correct) and mined with pickaxe-iron; plant/harvest codes still unresolved in 1.22 (see quirks) |
| Jev decision loop (openjev/Laya → `/polis`) | **v1/v2 measured** 2026-09-21 | v1 choice 0/8 (goal-word bias); v2 phase-split 0/8 but 8/8 confidence-gated — Laya cannot *select*, its abstention is honest; see `docs/reports/2026-09-21-jev-loop.md` |
| Jev-loop v3 (noul veto + 27B escalation) | **measured** 2026-09-22 | policy-proposes / Laya-vetoes / 27B-escalates: faults caught 1/2, false alarms 3/6, **fault and false-alarm at the same p (0.37)** — 421M is a conservative safety net, not a precision gate; 27B with thinking off = 124 ms conservative arbiter. Verdict: v4 = 27B per-step judge + Laya obvious-yes pre-filter; see `docs/reports/2026-09-22-jev-loop-v3-noul-veto.md` |
| Decision-harness passes 4–6 + harvest pipeline | **live verified** 2026-09-22 | pass 6: diff-based state line + stall valve → 2/2 missions, 0 stalls; harvest 2/2 (crop BEs + SeraphInventory cargo fix); 8 labeled sets in `data/`; visual proof in `docs/proofs/`; see `docs/reports/2026-09-22-bot-cargo-and-decision-harness.md` |
| Model A/B harness (Laya vs Decider 2B vs Qwen3.5-4B) | **Verdict: Decider 2B candidate; quantization floor 8-bit** 2026-09-24 | 41-row merged corpus, `scripts/jevab/` (runner + supervisor + env; runs on the CPU batch box,  4C/16G, weights on the host's `/models/jevab` shared store; the 27B box stays prod vLLM). **Decider 2B: top-1 70.7%** (mine 81.5% / harvest 50.0%), p(oracle) 0.870 correct vs 0.136 wrong, p>0.5 on 27/29 correct & 0/12 wrong — the p-band overlap that disqualified Laya is fixed; all 12 errors are one `goto_base`-over-`goto_target` travel-phase bias. **Quantized GGUF (2nd session): Q8_0 = bf16-equivalent** (Δtop-1 0, Δp(oracle) +0.002, 3.6 s/row 4C) — 8-bit is the quantization floor; **Q4_K_M breaks the readout** (top-1 0.537, p(oracle) 0.545, Brier 0.58). Side effect: Q8 makes the systematic wrong choice confidently (conf_wrong 0.136→0.746) without moving top-1/Brier. **Laya 421M (09-22): 41.5%** (mine 63% / harvest 0%). **SemIf 4B: first valid measurement (GGUF path)** — §12's bf16-CPU degeneracy (p(oracle)≡0) was a runtime artifact; the llama.cpp readout is healthy (allowed_token_mass 0.993) but the frozen base judges weakly: top-1 **46.3%**, p(oracle) 0.298, 12.2 s/row 4C → 2B task-tuned beats the larger frozen model, as the Jev premise predicts. Vision-Jev design: `docs/design/vision-jev-2026-09-22.md` |
| **Jev-loop v5 (live three-tier cascade)** | **measured** 2026-09-25 (overnight) | `scripts/jev-loop-v5.py` on the game testbed: Laya noul (1.3–1.5 s) → Decider-2B readout (3–4 s on the CPU batch box's 4C; ~0.3 s via the the 3060 card once the tailnet path is up) → 27B doubt-arbiter (272 ms, thinking off). Strong-gate (tau-strong, default re-derived overnight to 0.40: false-yes cap 0.371 vs correct floor 0.400) puts the 27B on any borderline consensus. Eight labeled mission runs: **harvest 2/2 steps in 16 s** (27B jumped straight to `harvest_target` — goal-first), **mine 2–5 steps / 11–81 s** across the fault-injected and 24-block-fixture runs; the goal-first jump is the dominant live pattern (five of the last six runs completed in 2 steps), faults: travel-skip caught by the 27B after a Laya-yes/Decider-0.76 consensus (the borderline hole), tool-drop self-repaired by the loop *choosing* `give_tool` (27B endorses a proposed give_tool but repeats a tool-less mine_target against its own rule; the imperative substitution-form rewrite did not change goal-first). `give_tool` is a first-class 5th action (measured on 30 labeled no-tool rows: the 2B **detects** the no-tool state — p(give_tool) 0.255 no-tool vs 0.009 with-tool, controls unshifted at 0.92 — but never **selects** it, 0/30 choice — *superseded by the 7-option rollout: with the option in the prompt set it selects 10/12 of the A-rows (bf16 and Q8 alike); see report §15 "7-option rollout and the fine-tune experiment"*; a proposed give_tool reads 0.255 < tau_dec so the 27B is consulted, while a proposed tool-less mine reads 0.843 *confirmed* — the Decider doesn't flag its own tier's failure mode; B-type is the Laya-veto + last-resort-repair regime, and the generated A/B rows are the fine-tune path to make it a selector); `place_block` execute() ready; `--dist` parameter for world variety. `botview.py` = one-command live overview + JSONL sidecar. Report §15 (findings 1–6 incl. the granularity finding + both-tiers-down resilience); run data `data/v5-*-2026-09-25*.json` |

## Open issues carried into 1.22.7 (from archive/KNOWN_ISSUES.md, unresolved)

- **Movement physics (top priority):** client prediction writes `Pos.Motion`
  directly, fighting the server's `interpolateposition`. 1.22.7 note: `goto`
  10 blocks completed with `arrived=true` (2026-09-21); smoothness unassessed.
- Tall-grass targeting: `gotolook` can target the grass block instead of the
  ground below → "no path".
- A* reports `no path` across unloaded chunks (spawn nearby for visual tests).
- Goto arrival snap: functionally exact, visually a ~0.5-block jump.
- Looping animations don't play on client; several action classes have no
  animation at all.
- Pickup timing: `CanCollect` false for ~1s after a drop; dropped items can
  leave the search radius quickly.
- Creative-mode caveats: no drops on mine/harvest (vanilla behavior) — run
  drop-dependent tests in survival.
- HUD coordinates can be offset from server coordinates (~+256 X/Z observed
  on the old build) — use `/polis list` / F3 for absolute coords.

## 1.22.7 environment gotchas found 2026-09-21 (affects any test/agent work)
- **World migration drops player moddata (field 15).** The 1.21.6→1.22.7
  upgrade rewrote the playerdata record and silently dropped the moddata
  container — `createCharacter=true` was lost, so the first-run dialog
  re-appeared on every boot and suspended the embedded server's tick
  (all harness commands hang). Fixed by splicing the field-15 blob back into
  the live save (backup: `Saves/*.pre-charsel.bak`); also added harness
  routes `/polis/debug/charsel` (inspect) and `/polis/admin/moddata`
  (set via the game's own SetModData — the dialog is unconfirmable headless).
  Any 1.21-era world will hit this on first 1.22 boot.
- **Collectible namespaces moved.** `survival:stone`-style codes no longer
  resolve via the world accessors; content resolves under plain / `game:`
  and hyphen-variant codes (`rock-granite`, `pickaxe-iron`, `packeddirt`).
  The harness now uses a lenient resolver (as-is → stripped → `game:` →
  `survival:`) in setblock/place/give. Plant/harvest blocks still not
  found under any tried namespace — open.
- **Possession NaN crash (fixed):** seat exposed a shared mutable EntityPos;
  on first possession frame the client entity got a NaN pos and the physics
  tick threw, killing the client. Seat now returns copies, guards NaN, and
  the client reconciler self-heals.
- `observer-screenshot --save` returns `filePath: null` (silent write
  failure; base64 path works). Use VNC/noVNC screenshots for visual evidence.
- In-game the cursor is pointer-locked (re-centered at 512,384): noVNC
  absolute clicks don't land on UI buttons in-world. Keyboard works (ESC
  closes dialogs; the first-run `Customize Skin` dialog could only be
  *closed*, never *confirmed*, headless — hence the admin/moddata route).

## Known 1.22.7 harness quirks (found 2026-09-21)
- `observer-screenshot --save` returns `filePath: null` (silent write failure;
  base64 path works). Use VNC/noVNC screenshots for visual evidence meanwhile.
- In-game the cursor is pointer-locked (re-centered at 512,384): noVNC
  absolute clicks don't land on UI buttons in-world. Keyboard works (ESC closes
  dialogs; the first-run `Customize Skin` dialog completes via close/ESC).

## Next (in order)
1. Green build on 1.22.7 — **done 2026-09-21**.
2. In-game smoke test on the game container — **done 2026-09-21** (core loop, possession,
   block ops live-verified; smoke-v1 PASS).
3. **Jev-loop v2/v3/v4** — done 2026-09-22: v2 (phase oracle, 0/8 match,
   8/8 gated), v3 (noul veto: conservative net, not precision),
   v4 (27B per-step judge + Laya pre-filter: decision side works, see
   `docs/reports/2026-09-22-jev-loop-v4-27b-judge.md`).
4. **Bot inventory + 1.22 loot routing** — done 2026-09-22: 16-slot cargo
   on `EntityPolisBot`; mine breaks as the bot and routes `GetDrops` into
   the cargo; set-placed rocks yield no item drops, so the mission's
   success criterion is marker removal (scan-verified); `POLIS_SKIP_CLAIMS`
   test-world bypass — `docs/reports/2026-09-22-bot-cargo-and-decision-harness.md`.
5. **Decision loop as optimization harness** — done 2026-09-22:
   `scripts/jev-loop-v4.py` (labeled set, mission outcome, phase-relative
   faults, threshold re-derivation). Five passes measured: mission complete
   2/2 at the re-derived tau; the doubt-arbiter stall (failure evidence
   sticks) is a robust, prompt-resistant finding for the method record.
6. **Doubt-arbiter stall fix** — done 2026-09-22 (pass 6): diff-based
   `since_last_step` state line + max-stall valve (2 waits -> policy
   resumes). Mission 2/2 in 25 s, 4/4 faults handled by the judge, 0
   stalls; threshold converged (suggested 0.358 ~ applied 0.35).
7. **Harvest pipeline + second mission** — done 2026-09-22: 1.22 crop
   system (farmland + `crop` variants, stage 7 = mature), harvest action
   breaks as the bot and routes drops to the cargo; harness is
   mission-parameterized (`--mission mine|harvest`); harvest mission
   complete 2/2 in 2 steps / 13 s, bot carries 11x carrot + seed home;
   openjev use cases `polis-action-noul` + `polis-harvest-noul`; labeled
   corpus in `data/`.
8. Grow the labeled corpus (a few more harvest/mine runs at varied
   taus) and hand the question JSONs + labeled sets to the llmlab side
   for the decision-classifiers page.
9. **Movement pass** — done 2026-09-22 (report section 9): the goto freeze
   root-caused to persisted idle-bot accumulation (19 bots; a restart
   mid-goto wedges the traverser one-shot async search); harness now sweeps
   bots before every run; goto has a bounded 3-phase fallback ladder (async
   A* -> sync A* -> straight line, 15 s timeouts) instead of a silent hang.
10. ~~WORLD WEDGED~~ - resolved 09-22 morning (see item 11 and report section 11). The
    `polis-testbed-pristine` world is persistently navigation-wedged (all
    entities fail to move; every recovery attempt failed; full incident
    record: report section 10). Next session, first task: delete the world
    (noVNC with a viewer connected, or stop the game and rm the Worlds/ and
    Saves/ entries), create `polis-testbed-2` WITH THE VIEWER CONNECTED
    (headless new-world creation hangs), set `VSGAME_WORLD`, restart,
    re-verify spawn+goto. Rules: never restart mid-goto; sweep bots before
    stopping the game.
11. **Wedge RESOLVED 09-22 morning** (supersedes item 10): world
    healthy again, full mine mission green. Root-cause trace + external
    corroboration (open vanilla VS issues #5334/#5422/#5875: entities
    alive-but-frozen; repro "saving and reloading a save within a
    vertical distance") in report section 11. Defenses: never restart
    mid-goto, `POLIS_PATH_PROBE=1` diagnostic, dawn-screenshot pause
    check. Done since: harvest pipeline + corpus growth + visual proof +
    repo sanitization + llmlab handoff (reports/2026-09-22-polis-jev-loop-model-handoff.md).
12. **v5 live loop — done 2026-09-25 (overnight, report §15)**: three-tier
    cascade measured on the game testbed (harvest 2/16 s, mine 4–5/76–81 s,
    faults handled, `give_tool` action live, botview live).
13. **Tailnet fast path — done 2026-09-25 (report: fast decider path)**:
    user approved the game testbed's tailnet node; the Decider now serves the loop
    from the the 3060 card via the `/prompt` + `decider-fast-client` split
    (286 ms/row warm vs 3–4 s CPU); first live short-circuit recorded
    (harvest return, Laya 0.41 + Decider 0.96, no 27B call).
14. **7-option reflex vocabulary — done 2026-09-25 (report §16)**:
    `pickup_item` + `place_block` joined the option set (7 per mission),
    pickup phase live-wired in the loop; corpus grown to 123 labeled
    rows (generated pickup/place grids + all prior rows remapped).
    **Fine-tune experiment (the 12 GB 3060 window): negative result** —
    aggressive LoRA (r16, lr 1e-4, 4 epochs on 102 rows) collapsed the
    model (holdout 76% base → 29% adapter, degenerate give_tool
    one-answer); the base model already selects the new options by
    reading the option list in the prompt (76/123, Q8 ≡ bf16,
    quantization-neutral), including give_tool 10/12 where the 5-option
    era measured 0/12. **Fine-tune deferred** until the corpus is
    several times larger; next attempt must be gentle (r 4-8, lr
    1-3e-5, early-stop, holdout covering the new families). Live
    7-option missions: mine 2 steps/42 s + harvest 2 steps/26 s,
    injected faults corrected, short-circuit on mine return.
    **Remaining on the v5 line:** (a) **done** — tau
    re-derivation on the new calibration unit, run as an *offline stress
    test* on 151 dual-p rows (dualp-runner.py: 84 correct-side vs 67
    faulty-side — 26 goto_base skip-goal + 46 give_tool-while-carrying
    variants): **no gate separates on the broad corpus** (all Youden
    points negative-margin; the clean 09-22/09-25 derivations ran on
    narrow live distributions); at current defaults 47/151 short-circuit,
    20 faulty (Wilson UB 19.6%) — both known leak families. **Decision:
    defaults stay 0.35/0.50/0.40** — the gates are load control, the
    27B + last-resort repair carry safety; chasing Youden points would
    kill the SC benefit (10/39 correct) without a real boundary. The
    leak families are tier-quality problems (report §15 stress-test
    section); (b) **done** — world-variety corpus growth: `gen-world-variety-
    rows.py` generated 240 rows (distance 3-30, carrying, items
    distractors, phase-consistent since/last) → 363-row merged corpus;
    base Decider Q8 re-measured on the full grid: **top-1 61.8% → 71.9%
    (261/363), travel family 84%** (was the 24/30 bias), return 100%,
    B-substitution still 0/12 (the known in-context gap the gentle
    fine-tune / judge tier targets); (c) **done** — pickup phase verified
    live: mine drops insert into the inventory first, so the working
    mechanism is the `--drop-after-mine` world event (give+drop a
    stone-granite at the mine site); first pickup-phase short-circuit
    (Laya 0.58 + Decider 0.73, GOAL 3 steps/27 s). **Two loop bugs found
    + fixed along the way:** the 3-tier gate silently degraded to Laya-only
    when only `--decider-fast` was passed (Decider tier gated on
    `--decider`; now self-sufficient), and `mine_target` had no approach
    step so a goal-first mine from 12+ blocks away failed out-of-range
    and repeated 8× until step-budget (now gootos the target first).
    `--drop-after-harvest` exists but is inert (harvestcrop puts the crop
    in the backpack directly). (d) `place_block` build mission
    end-to-end (execute() exists); (e) **unblocked** — gentle fine-tune
    (r 4-8, lr 1-3e-5, p-oracle-plateau early-stop) on the 363-row
    corpus (B-family 0/12 is the target).
