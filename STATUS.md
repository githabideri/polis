# STATUS.md — the single source of state

Updated: 2026-09-21 (overnight port session)
Game target: **Vintage Story 1.22.7** (released 2026-08-16). 1.23 expected before end of 2026.

## Overall state

| Layer | Level | Notes |
|-------|-------|-------|
| 1.22.7 code port | **locally verified** | net10.0, hermetic csproj, 5 API drift fixes; build: 0 errors |
| 1.21-era feature set (bots, A*, block actions, possession) | **live verified** (previous 1.21.6 testbed) | see `archive/KNOWN_ISSUES.md` for the detailed, per-feature history |
| CT-114 testbed (VNC + game + auto-login) | **live verified** 2026-09-20 | keyboard + clipboard input through noVNC work; see `ops/CT114-VNC.md` |
| Core loop on 1.22.7 (load → spawn → goto → verify) | **live verified** 2026-09-21 | CT-114: mod loads (4 mods, 0 errors), harness :8585 worldReady, bot #2 spawned, `goto +10x` arrived=true, bot visible in VNC screenshot |
| Possession + block actions (mine/harvest/place/activate) on 1.22.7 | **not yet tested** | compiles; pending live verification |
| Jev decision loop (openjev/Laya → `/polis`) | **not started** | design target: text-grid question → typed choice → command |

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

## Known 1.22.7 harness quirks (found 2026-09-21)
- `observer-screenshot --save` returns `filePath: null` (silent write failure;
  base64 path works). Use VNC/noVNC screenshots for visual evidence meanwhile.
- In-game the cursor is pointer-locked (re-centered at 512,384): noVNC
  absolute clicks don't land on UI buttons in-world. Keyboard works (ESC closes
  dialogs; the first-run `Customize Skin` dialog completes via close/ESC).

## Next (in order)
1. Green build on 1.22.7 — **done 2026-09-21** (see top table).
2. In-game smoke test on the game testbed: mod loads, `/polis spawn`, `/polis goto`,
   `/polis state` via harness; then possession.
3. Movement-physics root-cause pass (the top open issue).
4. Harness re-verification + first deterministic mission with pass/fail.
5. Jev-loop v1 (Laya decision → command) pass-rate measurement.
