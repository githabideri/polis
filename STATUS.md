# STATUS.md — the single source of state

Updated: 2026-09-21 (overnight port session)
Game target: **Vintage Story 1.22.7** (released 2026-08-16). 1.23 expected before end of 2026.

## Overall state

| Layer | Level | Notes |
|-------|-------|-------|
| 1.22.7 code port | **implemented → build in progress** | retargeted to net10.0; API drift being fixed against `anegostudios/vsessentialsmod@1.22.7` as reference |
| 1.21-era feature set (bots, A*, block actions, possession) | **live verified** (previous 1.21.6 testbed) | see `archive/KNOWN_ISSUES.md` for the detailed, per-feature history |
| CT-114 testbed (VNC + game + auto-login) | **live verified** 2026-09-20 | keyboard + clipboard input through noVNC work; see `ops/CT114-VNC.md` |
| Harness (poliscli / vsctl / HTTP) | **implemented** (pre-1.22.7 build) | re-verification pending on the 1.22.7 build |
| Jev decision loop (openjev/Laya → `/polis`) | **not started** | design target: text-grid question → typed choice → command |

## Open issues carried into 1.22.7 (from archive/KNOWN_ISSUES.md, unresolved)

- **Movement physics (top priority):** client prediction writes `Pos.Motion`
  directly, fighting the server's `interpolateposition`; root cause not yet
  fixed (bot movement works with snaps/teleports but is not smooth/robust).
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

## Next (in order)
1. Green build on 1.22.7 (this session).
2. In-game smoke test on the game testbed: mod loads, `/polis spawn`, `/polis goto`,
   `/polis state` via harness; then possession.
3. Movement-physics root-cause pass (the top open issue).
4. Harness re-verification + first deterministic mission with pass/fail.
5. Jev-loop v1 (Laya decision → command) pass-rate measurement.
