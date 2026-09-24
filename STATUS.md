# STATUS.md — the single source of state

Updated: 2026-09-24 (model A/B verdict: **Decider 2B is the Jev candidate** — 70.7% top-1 on the 41-row corpus, p(oracle) cleanly separated (27/29 correct >0.5, 0/12 wrong), residual errors = one systematic goto_base bias; SemIf 4B readout degenerate on this stack → no valid 4B measurement, harness fix pending; results `data/ab-*-2026-09-24.json`, verdict in report §12, harness committed to `scripts/jevab/` on the CPU batch box; llmlab handoff: Decider 2B replaces Laya as candidate, SemIf paragraph superseded)
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
| Model A/B harness (Laya vs Decider 2B vs Qwen3.5-4B) | **Verdict: Decider 2B candidate** 2026-09-24 | 41-row merged corpus, `scripts/jevab/` (runner + supervisor + env; runs on the CPU batch box,  4C/16G, weights on the host's `/models/jevab` shared store; the 27B box stays prod vLLM). **Decider 2B: top-1 70.7%** (mine 81.5% / harvest 50.0%), p(oracle) 0.870 correct vs 0.136 wrong, p>0.5 on 27/29 correct & 0/12 wrong — the p-band overlap that disqualified Laya is fixed; all 12 errors are one `goto_base`-over-`goto_target` travel-phase bias. **Laya 421M (09-22): 41.5%** (mine 63% / harvest 0%). **SemIf 4B: no valid measurement** — letter-slot readout degenerate (p(oracle) ≡ 0, Brier 1.0, single-action argmax) on this transformers/bf16-CPU stack; harness fix (pin transformers to the SemIf era, verify letter mapping, fp32 probe) before any 4B claim. Latency: CPU reference path only (18.4 s/q, 4C) — deployment latency (GPU kernels or quantized GGUF) is the open question. Vision-Jev design: `docs/design/vision-jev-2026-09-22.md` |

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
    Next live work: (1) Decider 2B deployment-latency campaign (GPU kernels on the 12 GB 3060 or quantized GGUF on CPU) — the open deployment question; (2) SemIf 4B harness fix (pin transformers era, verify letter-slot mapping, fp32 probe) → first valid 4B measurement; (3) then revisit the two-tier loop wiring with Decider as the reflex layer; then (parked) publish.
