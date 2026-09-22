# STATUS.md — the single source of state

Updated: 2026-09-22 (harness LAN-reachable + uid hardening + look/aim-verify; Jev-loop v3 noul-veto measured)
Game target: **Vintage Story 1.22.7** (released 2026-08-16). 1.23 expected before end of 2026.

## Overall state

| Layer | Level | Notes |
|-------|-------|-------|
| 1.22.7 code port | **locally verified** | net10.0, hermetic csproj, 5 API drift fixes; build: 0 errors |
| 1.21-era feature set (bots, A*, block actions, possession) | **live verified** (previous 1.21.6 testbed) | see `archive/KNOWN_ISSUES.md` for the detailed, per-feature history |
| CT-114 testbed (VNC + game + auto-login) | **live verified** 2026-09-20 | dialog-free boots since the moddata fix; see `ops/CT114-VNC.md` |
| Core loop on 1.22.7 (load → spawn → goto → verify) | **live verified** 2026-09-21 | harness :8585; short and long (100-block) gotos arrive; smoke-v1 mission **PASS** (move/give/inventory-assert/move-back) |
| Possession on 1.22.7 | **live verified** 2026-09-21 | possess → setcontrols (bot moved 53 blocks on held forward) → unpossess; NaN seat crash found & fixed (see below) |
| Block actions on 1.22.7 (setblock/give/mine/place) | **live verified** 2026-09-21 | place ok; natural-ground mine ok; rock mine gated by tool tier (correct) and mined with pickaxe-iron; plant/harvest codes still unresolved in 1.22 (see quirks) |
| Jev decision loop (openjev/Laya → `/polis`) | **v1/v2 measured** 2026-09-21 | v1 choice 0/8 (goal-word bias); v2 phase-split 0/8 but 8/8 confidence-gated — Laya cannot *select*, its abstention is honest; see `docs/reports/2026-09-21-jev-loop.md` |
| Jev-loop v3 (noul veto + 27B escalation) | **measured** 2026-09-22 | policy-proposes / Laya-vetoes / 27B-escalates: faults caught 1/2, false alarms 3/6, **fault and false-alarm at the same p (0.37)** — 421M is a conservative safety net, not a precision gate; 27B with thinking off = 124 ms conservative arbiter. Verdict: v4 = 27B per-step judge + Laya obvious-yes pre-filter; see `docs/reports/2026-09-22-jev-loop-v3-noul-veto.md` |

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
2. In-game smoke test on the game testbed — **done 2026-09-21** (core loop, possession,
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
9. Movement-physics root-cause pass (the top open issue from
   archive/KNOWN_ISSUES.md).
10. Publish prep: sanitized copy for GitHub + VS mod store (exclude
    `ops/` and `archive/`); archive old `vspolis` repo + decommission
    Daedalus (a gateway container agent id `polis`). **Parked — owner decision
    pending.**
