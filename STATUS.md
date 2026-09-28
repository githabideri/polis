# STATUS.md — the single source of state

Updated: 2026-09-28 (15th pass, **Phase 1-A complete** — the reflex extraction is done and proven: `r2/{types,projection,executor}.py` hold the pure reflex core (build_reflex_state/build_state_text/needs_judge/decide_cascade + oracle/fixture predicates), verbatim from v5, with v5 as the live orchestration importing from it — one implementation for both entry points. The contract gate now runs five tests on both `--impl v5` and `--impl r2`: T1 237/237 prompt byte-identity, T2 45/45 decision replays, T3 237/237 readout coherence, **T4 8/8 state-construction** (new — the reflex-state DTO replayed from the frozen raw observation triple: f1 state, f2 carry, post-injection f3, fixture scan, prev), **T2b 3/3 run transitions** (new — run ends at goal step or budget, completion implies goal seen). The T4 goldens came from three daylight capture passes (mine 2 steps, harvest 3, build 3 — all clean and complete) frozen in `tests/reflex/fixtures/reflex-state-t4.json`. The verification paid: the first T4 replay caught a real recording bug (row `raw.scan` was re-read from `pol.last_scan` at append time — after the post-execute goal check re-issued the scan — so the "pre-decision" snapshot was actually post-execution; the DTO itself was fine, it was built from the earlier ctx capture). Live spot runs after the extraction (faults on, mine + harvest) completed in 2 steps each with the 27B judge correcting both injected skip-goal faults. Next: Phase 2 — WorldModel + ObservationService under the frozen reflex.)

Previous state (2026-09-27 ~23:50, 15th pass Phase 0): (behavioral contract frozen: v5's reflex prompt builder + three-tier decision rule extracted into pure functions and pinned by `tests/reflex/contract.py` — 237/237 prompt byte-identity, 45/45 decision replays, 237/237 readout coherence; three live missions re-ran on the extracted code, all completed) **and the 23:13 crash root-caused & closed**: the NaN that killed the game was in `pos.Motion` (velocity), which the vanilla `ApplyTests` check inspects but `pos.ToString()` never prints — the original guard (XYZ/YPR only) let it through. Guard extended (NaN motion detected + zeroed), the `/polis/observer-screenshot` teleport-capture-restore round trip hardened (one in flight at a time; restore skips a disconnecting entity), and the webui frame renderer rewritten canvas-based after a sysadmin heads-up that the per-frame `data:`-URL flow had grown to 7.5 GB in a long-lived headless page (OOM-risked the box running the session daemon). Verified live: concurrent captures reject cleanly with JSON; two viewer disconnect/reconnect cycles survived with the world intact — previously every viewer disconnect was a process death.) Research first: the community "unslop" skill (`unslop-ui`, dataset `vibecoded-design-tells` — 3.2M posts) lists the actual AI-slop tells (purple/indigo primary, gradients, neon glow, emoji icons, Inter, shadcn-default, hero+3-cards); its community critique decided the approach — anti-slop defaults (beige/serif) are now themselves a tell, so the redesign follows neither: it's derived from the function (an ops console around a live game image). Design contract: `docs/design/webui-design.md` (stable identity: dark instrument panel, self-hosted IBM Plex, warm off-white on charcoal, single amber accent, semantic status colors, four areas: Stage/World/Control/Console). **Controls root-cause fix**: movement and view are now **hold-to-repeat** (pointer hold or WASD/arrows; 12°/120 ms turns, 0.5b/150 ms moves, 8°/110 ms pitch) with a one-shot **180° turnaround** — "look around" is continuous, not 8 clicks. Pose comes from a local shadow projected per step, resynced from a 1.5 s server poll (the old 5 s poll made every step feel stale). Screenshot pane now uses the real `/polis/observer-screenshot` GET endpoint (player POV, no-op teleport); old ui modules folded into `app.js`; mission buttons stay out (missions live in the v5 script, not the harness). Verified live: 180° one-shot + hold burst, game alive. **Left known**: noVNC still wants a TLS front (secure-context warning; docs). Same-day sweep (dev→debug→dev loop now runs: pre-handoff click-through + in-UI **diagnostics export** — a bug report is a JSON artifact of every network call/error, not prose): three UI bugs found & fixed (unguarded setPointerCapture silently swallowed the hold start; the bot "scan" button called the region-scanner command instead of /polis/state; raw response shape). Theme system (auto/dark/light, auto follows the OS and is the default). NPM front for the UI is **proposed, not built** (name/cert/auth/TLS + same-origin /vnc pass-through that fixes the noVNC secure-context problem; lives in the 13th-pass conversation, durable records go to the private homelab repo if adopted — this repo is staged for public release and takes no internal identifiers).
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
| Model A/B harness (Laya vs Decider 2B vs Qwen3.5-4B) | **Verdict: Decider 2B candidate; quantization floor 8-bit** 2026-09-24 | 41-row merged corpus, `scripts/jevab/` (runner + supervisor + env; runs on the CPU batch box, 4C/16G, weights on the host's `/models/jevab` shared store; the 27B box stays prod vLLM). **Decider 2B: top-1 70.7%** (mine 81.5% / harvest 50.0%), p(oracle) 0.870 correct vs 0.136 wrong, p>0.5 on 27/29 correct & 0/12 wrong — the p-band overlap that disqualified Laya is fixed; all 12 errors are one `goto_base`-over-`goto_target` travel-phase bias. **Quantized GGUF (2nd session): Q8_0 = bf16-equivalent** (Δtop-1 0, Δp(oracle) +0.002, 3.6 s/row 4C) — 8-bit is the quantization floor; **Q4_K_M breaks the readout** (top-1 0.537, p(oracle) 0.545, Brier 0.58). Side effect: Q8 makes the systematic wrong choice confidently (conf_wrong 0.136→0.746) without moving top-1/Brier. **Laya 421M (09-22): 41.5%** (mine 63% / harvest 0%). **SemIf 4B: first valid measurement (GGUF path)** — §12's bf16-CPU degeneracy (p(oracle)≡0) was a runtime artifact; the llama.cpp readout is healthy (allowed_token_mass 0.993) but the frozen base judges weakly: top-1 **46.3%**, p(oracle) 0.298, 12.2 s/row 4C → 2B task-tuned beats the larger frozen model, as the Jev premise predicts. Vision-Jev design: `docs/design/vision-jev-2026-09-22.md` |
| **Jev-loop v5 (live three-tier cascade)** | **measured** 2026-09-25 (overnight) | `scripts/jev-loop-v5.py` on the game testbed: Laya noul (1.3–1.5 s) → Decider-2B readout (3–4 s on the CPU batch box's 4C; ~0.3 s via the 3060 card once the tailnet path is up) → 27B doubt-arbiter (272 ms, thinking off). Strong-gate (tau-strong, default re-derived overnight to 0.40: false-yes cap 0.371 vs correct floor 0.400) puts the 27B on any borderline consensus. Eight labeled mission runs: **harvest 2/2 steps in 16 s** (27B jumped straight to `harvest_target` — goal-first), **mine 2–5 steps / 11–81 s** across the fault-injected and 24-block-fixture runs; the goal-first jump is the dominant live pattern (five of the last six runs completed in 2 steps), faults: travel-skip caught by the 27B after a Laya-yes/Decider-0.76 consensus (the borderline hole), tool-drop self-repaired by the loop *choosing* `give_tool` (27B endorses a proposed give_tool but repeats a tool-less mine_target against its own rule; the imperative substitution-form rewrite did not change goal-first). **Reflex model as of 11th pass: `qwen35-decider-2b-ft2`** (LoRA round 2: build mission + wait-abstention corpus; val 96/96 floor 0.883, OOV 96/96, abstention 45/45 `wait` at p≈1.0 vs FT-1's 13/45 and 71% confidently-wrong; live build 7 steps complete — report §19). FT-1 (round 1, val 96/96 vs base 70/96, B-family 12/12 vs 0/12, distractor fall-through 1/57 vs 55/57) and base stay registered as A/B references. `give_tool` is a first-class 5th action; `place_block` is a real action (build mission live); `--dist` parameter for world variety. `botview.py` = one-command live overview + JSONL sidecar. Report §15–19; run data `data/v5-*-2026-09-25*.json`, `data/v5-r1-*-2026-09-26.json`, `data/v5-build-*-2026-09-26.json`, `data/ft2-ab/`, `data/{base,ft}-measure-{val,train}-2026-09-25.jsonl` |

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
    from the 3060 card via the `/prompt` + `decider-fast-client` split
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
15. **R2 Phase 0 — freeze the behavioral contract** — done 2026-09-27: v5's
    `build_state_text` (the 8-line FT-trained prompt) and `decide_cascade`/
    `needs_judge` (three-tier decision rule + stall valve) extracted into pure
    functions; `tests/reflex/contract.py` pins them against pre-extraction
    goldens (237 corpus states + 44 live cascade steps incl. all five path
    branches and 4 stall bypasses + 1 synthetic decider-err). Gate green both
    before and after the extraction; three live missions (mine/harvest/build)
    completed on the extracted code.
16. **R2 Phase 1-A — the r2/ extraction** — done 2026-09-28 (same night): the
    pure core moved to `r2/` verbatim; T4 (raw observation -> reflex-state
    DTO, 8 frozen steps) + T2b (run transitions) added to the contract gate
    and passing on BOTH implementations; live spot runs (faults on) green.
17. **R2 Phase 2: WorldModel + ObservationService** — the visual sensor
    (serialized, coalescing, staleness-bounded) plus the world model with
    its staleness invariants in the gate (see the design doc §11.2/11.4).

## 14th pass — 2026-09-27 — cockpit groundwork + the module-kill incident

**NPM front (homelab side, done & verified):** a public TLS front for the UI
(`REDACTED-UI-DOMAIN`, wildcard cert, force-SSL, WS → the 8586 proxy on the
game container; the address is a homelab-side detail — private service docs).
The 8586 proxy gained a
**basic-auth gate** (all non-WS requests; a file-based auth store on the
CT, constant-time, re-read per request; credentials in the private
homelab service docs) and
**`/vnc/*` → websockify 6080** passthrough (prefix-stripped; `/websockify`
unstripped). noVNC in the UI is now **same-origin** (`/vnc/vnc.html?path=
vnc/websockify`) — over the TLS front the stream is **wss** and the
secure-context warning is gone. Dashy: "Polis" item in the LLM & AI section.
Public: `https://REDACTED-UI-DOMAIN/polis/ui/` (basic auth).

**Cockpit (C# — built, deployed, game restarted):**
- `CommandContext.Actor` — every `/polis/command` now emits a
  `PolisEvent("command")` with `actor` (user/agent/devops/harness) + cmd +
  result into the event stream/history. The action stream shows **who did
  what**; the UI dedupes its own user-tagged events (logged locally).
- **`autonomy get | autonomy set <free|guarded|strict>`** — the Oikistes'
  autonomy level, **mod-owned** (world config key `polis_oikistes_autonomy`,
  default `guarded`; persisted with the world save). The decision runtime
  injects the current level into its context each turn and enforces it in
  the execution path — the LLM never carries the policy. The UI (new
  Oikistes rail section) reads/writes it live; later a cultural/tech-tree
  system will too.
- `TryGetHarnessBot` already prefers an explicit `context.BotId` — the UI now
  sends it for all bot-scoped actions (the despawn select-first hack is
  superseded, kept only to keep the game's selection state in sync).

**Web UI:** Oikistes rail section (live autonomy select + chat stub — honest
"not yet inaugurated" until R2), actor badges in the console log,
`node --check` → **`tools/webui/syntax-check.sh`** (acorn ESM parse) as the
pre-deploy gate.

**The incident (why the gate exists):** the Oikistes-panel edit left a stray
top-level `}` in app.js. `node --check` passed (script-mode parse); the
browser's module parser killed the whole module — the UI loaded **dead**
(no polling, no wiring, no visible error; "disconnected" badge). Diagnosis:
a dynamic-import trap page surfaced `Unexpected token '}'`; acorn pinpointed
the line. Lesson recorded: for ESM, the browser's parser is the source of
truth; the gate runs before every webui deploy.

**Verified live:** autonomy roundtrip UI→C#→world-config (guarded→free→
guarded) with log feedback; devops actor tag appears in the console from a
curl-issued command; chat stub exchanges; page fully connected through the
public TLS front (clock, bots, players, stream state).

**Still to do (next passes):** R2 job system → Oikistes runtime (this panel
is its home); FT-3 corpus; dashcam demo run under the TLS front.

## 15th pass — 2026-09-27 — Phase 0 (behavioral contract) + the 23:13 NaN-motion crash

**Phase 0 of the R2 plan (`docs/design/2026-09-26-job-system-r2.md`) is done.**
The inline decision flow of `scripts/jev-loop-v5.py` was frozen as a
behavioral contract before any refactoring: `build_state_text(...)` (the
8-line FT-trained reflex prompt) and `needs_judge(...)` / `decide_cascade(...)`
(the Laya→Decider→27B rule plus stall valve) are now pure functions; the loop
calls them unchanged. The gate is `tests/reflex/contract.py` with fixtures
captured from **pre-extraction** artifacts (v5 run JSONs of 09-25/09-26 + ft2-ab
measurements), so a green run is the behavior-identity proof:
- T1 prompt byte-identity: 237/237 (96 val-world + 96 OOV + 45 abstain rows)
- T2 decision replay: 45/45 (44 live steps covering all five path branches,
  4 stall bypasses, 1 last-resort repair; +1 synthetic decider-err case)
- T3 recorded readout coherence: 237/237
Post-extraction live check: mine/harvest/build d12 missions all completed
(injected travel faults corrected by the cascade; build's `place_block` at
p_decider=1.00 via reflex+decider). The `--impl v5|r2` hook on the gate is
Phase 1's cross-implementation comparison point.

**The 23:13 crash — root-caused and closed.** The vsgame process died at
23:13:23 while a web viewer was attached. The `client-crash.log` said
`ArgumentException: Given pos contained NaN` in `ApplyTests` — but the printed
pos was **clean** (511996.9/3/512018.1, YPR finite). Decompiling VSEssentials
1.22.7 (ilspycmd) showed why: the vanilla check inspects `pos.Motion`
(velocity) in addition to XYZ, and `pos.ToString()` only prints XYZ/YPR/Dim —
so the NaN sat in the field the message never shows. The 09-26 guard only
checked XYZ/Yaw/Pitch/Roll and let it through. NaN motion is a client-prediction
artefact of rapid/nested server→client position updates; the generator in this
deployment is the `/polis/observer-screenshot` teleport-capture-restore round
trip (the crash landed exactly on a viewer disconnect mid-capture; the same
family killed the 09-21 and 09-26 incidents).

**Fixes (all verified live):**
- `PolisNanPosGuardPatch` now detects NaN motion too and zeroes it (position
  restore only when the position itself is NaN) — a NaN event is now a logged
  `[polis] NaN physics pos sanitized ... motion-zeroed=True`, not a death.
- `observer-screenshot`: atomic in-flight guard (one capture at a time;
  concurrent requests get `ok:false` JSON — the harness serves each request on
  its own thread-pool thread, and rejected requests must not early-return:
  the JSON writer sits below the big if/else chain); the restore now skips the
  teleport when the player no longer holds the exact entity (viewer gone
  mid-capture → entity mid-disposal with NaN marks).
- **Viewer disconnect is now safe:** two consecutive disconnect/reconnect
cycles with a live page survived, world intact. Previously every viewer
disconnect was a process death.

**Web UI frame memory bomb (sysadmin heads-up).** The capture flow set a fresh
`data:` URL per frame; Blink's renderer keeps every unique `data:` bitmap until
the page dies — one long-lived headless page grew to **7.5 GB** (~1 MB/min)
and OOM-risked the 12 GB box running the session daemon. `agent-browser` has
no auto-close (upstream #885/#1334). The renderer is now canvas-based
(`renderFrameImage()`: offscreen buffer + letterbox composite, in place,
zero `data:` URLs); the payload is a genuine PNG (an earlier build served
JPEG under `base64Png` — checked, current build is PNG/SkiaSharp). Discipline
for agents: kill the browser after UI work; keep capture loops ≥ 2 s apart.

**Left:** the in-flight guard's rejection is untested under sustained load
(one concurrent pair verified); a viewer disconnect *while the restore
callback is queued but not yet run* is the one residual NaN-motion window the
restore-skip closes but that is not yet covered by a forced repro.

### Phase 1-A (same night, 2026-09-28): the r2/ extraction — done & proven

The pure reflex core moved to `r2/{types,projection,executor}.py` —
**verbatim** from v5 (one implementation; v5 is now the live orchestration
importing from it). The step recorder gained additive capture of the full
observation context per step (f1 state, f2 carry, post-injection f3, fixture
scan, prev) plus the exact reflex-state DTO; three daylight passes froze
`tests/reflex/fixtures/reflex-state-t4.json` (8 steps, mine/harvest/build —
all clean and complete, with run-level transition data). The contract gate
now runs **T1 237/237, T2 45/45, T3 237/237, T4 8/8, T2b 3/3 on BOTH
`--impl v5` and `--impl r2`**. The first T4 replay caught a real bug in the
new recorder (see the design-doc status log); live spot runs after the
extraction (faults on, mine + harvest) completed in 2 steps each with the
27B judge correcting both injected skip-goal faults. Phase 1 of the plan is
therefore complete — Phase 2 (WorldModel + ObservationService) is next.

### Phases 2-6 (2026-09-28 overnight): world model -> planner -> queue -> live

- **Phase 2** — `r2/{queries,worldmodel,observation}.py`: the mission-
  agnostic WorldModel (resources with measured drops, fixtures with
  stamped conditions, the claim index, logical-tick freshness) and the
  single-threaded ObservationService. T5 staleness invariants in the
  contract gate; gate green on both impls.
- **Material probe** (`scripts/probe-material.py`) — the authoritative
  1.22 fact: mining `rock-granite` yields `stone-granite`; place only
  accepts `rock-granite`; there is NO public API for the item->block
  mapping. §12.9 re-scoped the live two-job milestone to external-
  supply place (+harvest); mine->place lives on as the validator's
  strongest rejection case.
- **Phase 3** — `r2/jobs.py`: goal grammar (v1), the 8-type job catalog
  with effect semantics, the 9-code failure taxonomy with layer
  attribution. 31/31 unit tests.
- **Phase 4** — `r2/{plannerprompt,plancheck}.py`: the deterministic
  projection (candidate index = the trust boundary) and the goal-aware
  validator (schema, references, dependencies, the material ledger with
  the measured-drop hard check, the goal-target check, intake). 21/21
  unit tests (a mid-file sys.exit had been silencing the last 5 —
  found and fixed during this night).
- **Phase 5** — the 27B planner A/B on the 25-case suite, 4 rounds
  (r1-r4: 9 -> 17 -> 19 -> 20 CORRECT, 1 CAUGHT, 4 WRONG). Findings:
  the 27B over-rejects on quantity (never over-accepts — the safe
  failure mode), reads "mine X" as outcome, hallucinates "no site" on
  mine goals; bare-object plans are normalized at the parse boundary.
- **Phase 6** — `r2/jobqueue.py` (13/13: lifecycle, abandonment,
  rejection, ledger, run-JSON) + `scripts/r2-live-mission.py` (the live
  orchestrator reusing the v5 action primitives). **Live: one-job GOAL
  COMPLETE in 8 s (run 05), 9 honest rejections, and the two-job
  milestone COMPLETE (run 11, 8.5 s) via 12.10 remediation (a): a
  goal-level `supply: external` declaration - the operator give is
  deterministic and pre-planning (job j0, source=operator), the 27B
  then plans the single place job it can actually see.** The 27B's
  refusal of the pre-supply world is the standing finding (12.10): it
  is not prompt-overridable; prompt changes to the planner are gated
  by the 25-case A/B (r4/r5/r6/r7; the adopted diff is one sentence in
  rule 9). Open: the mine-oracle async-drop finding (run 12) and the
  goal-grammar question (12.5) — both follow-ups, not blockers.

### Round-3 amendments (2026-09-28, morning): §13
ChatGPT's feedback round 3 was grounded and adopted as design-doc
§13. Code changes: **M1/M2 milestone split** (run 11 = M1 supplied-
material two-job execution, DONE; M2 endogenous mine→place remains
open); **execution/oracle separation** in the run-JSON step record;
**JobOrigin** (frozen set planner/operator/deterministic/repair —
j0 corrected from the abused `source` field); **VisualCaptureService**
rename (my "1 Hz/2 Hz refresher" description was wrong — that loop
does not exist); **P5 dual metrics** — precision 1.000 / coverage
0.524-0.476 (the 27B never fabricates, covers ~half of feasible
goals). Confirmed already-true: CAUGHT is evaluation-only (not in
the runtime 9-code taxonomy), depends_on is job-ids-only, freshness
is current-sequence match with the seq/monotonic/wall triple, and the
operator-supply intake meets all five of ChatGPT's requirements.
Planner fine-tune explicitly deferred until the 6-step closing
sequence (13.6): approach-retry port → deterministic endogenous
proof → 27B on the same goal → M2 close → P5 re-run with 5-way
failure classification → then (and only then) a planner-specific
fine-tune as its own artifact.

### 13.6 step 1 executed (2026-09-28, 09:35): approach port + the mine path is green
`r2/approach.py` (12/12 offline tests) formalizes the neighbour retry
as `goto(position)` vs `approach(target, interaction)`; the queue
sees one job, the per-candidate log lands in the run JSON. Wired into
mine/harvest live. **Mine goal now GOAL COMPLETE in both modes**:
deterministic (run 18, 11.4 s, `--no-planner`) and 27B-planned
(run 19, 16.3 s), each with a measured 2x stone-granite delta. Two
latent bugs died in the process (the inventory-diff KeyError that
crashed runs 15/17; deterministic jobs now carry `origin`). P5 r8
re-measured with the 13.3 dual metrics: 19/25, precision 1.000,
coverage 0.476 (stable vs r7). **Remaining sequence:** the M2 place
half is blocked on the 1.22 item->block mapping wall (granite drops
`stone-granite`, place wants `rock-granite`; no public mapping) -
next investigation: the soil round-trip probe; then step 4 (close
M2), step 5 (P5 5-way classification), step 6 (the planner-FT
decision - precision 1.000 means an FT can only work on coverage).
