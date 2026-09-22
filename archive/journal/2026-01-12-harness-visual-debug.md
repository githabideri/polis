# 2026-01-12: Harness visual debug + coordinate mismatch

## Context
We validated the HTTP harness against live gameplay because bots were spawning but not visible to the player. The goal was to prove the harness is driving real in-game state and to identify why the player could not see spawned bots.

## Evidence (logs + harness)
- Server log shows player placed around 230,3,267:
  - `Placing player at 230.080078125 3.00006103515625 267.67401123046875`
- Harness bot list shows bot coords near 228,3,260:
  - `/polis/bots` includes bot #160 at `228.2622, 3.0001, 260.3043`.
- Player-reported HUD coords were around `-28, 3, 2` while server-side was ~`230, 3, 260`.
- Offset between HUD and server coords is approximately +256 on X/Z.
- A* gotolook attempts failed with `no path` when the bot was far away/unloaded:
  - `[polis] [goto] no path`
  - Bot #158 later logged as `stuck` at `-28.00,3.00,18.00`.

## Actions taken
- Spawned bot #161 next to bot #160 using server coordinates:
  - Spawn: `228.2622, 3.0001, 261.3043`.
  - Moved bot #160 to `229.2622, 3.0001, 260.3043`.
- Result: visible movement confirmed when using server-side coordinates.

## Findings
1) **Coordinate mismatch**
   - Player HUD appears to show relative/offset coords (likely from an observer/camera mod). The server uses absolute world coords. Bots spawn where the server thinks the player is, not where the HUD indicates.
   - Net effect: bots are real but appear "missing" due to coordinate drift (+256 X/Z).

2) **Harness is tied to the running game**
   - Port 8585 is bound by the Vintagestory process and harness start is logged (`[polis-harness] HTTP server started`).
   - Harness actions do create entities; invisibility was due to coordinate mismatch, not missing spawns.

3) **World readiness matters**
   - Early harness commands can return `Timeout waiting for game thread` if sent before WorldReady. We need a readiness gate in docs or retries in tools.

4) **Pickup action failure**
   - Pickup often fails with `inventory full, nothing transferred` after drop. This suggests playerbot inventory constraints even when hands look empty. Needs investigation (hand slot vs inventory container).

5) **A* from unloaded/far chunks**
   - `gotolook` can fail with `no path` when the bot is far away or in unloaded chunks. For debugging, use nearby spawns or `astar=false`.

## Next steps
- Document coordinate mismatch and how to obtain absolute server coords (F3 or /polis list), and warn about observer/camera mods.
- Add a readiness note for harness usage (wait for WorldReady in logs).
- Investigate playerbot inventory for pickup failures and decide whether to target hand slots explicitly.
- Consider a harness `despawn` command for cleanup.
