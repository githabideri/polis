# vsctl Game Controller Implementation

**Date:** 2026-01-18
**Feature:** Automated VS game lifecycle control for agentic development loop

## Summary

Created `scripts/vsctl.py` - a Python tool to control VS game lifecycle (start, stop, restart, wait) with proper ready detection. This enables fully automated testing loops without manual intervention.

## Problem

For an agentic development loop, we need to:
1. Start the game programmatically
2. Know when it's truly ready (not just server ready, but client rendered)
3. Stop cleanly without corrupting saves

Previous approach (`worldReady=true` from harness) was insufficient - there's a significant gap between server ready and client visually ready.

## Ready Detection Timeline

Collected during testing on 2026-01-18:

| Time | Event | Signal |
|------|-------|--------|
| 00:00 | VS launched | `flatpak run ... --openWorld test-lands` |
| ~01:40 | Harness reachable | HTTP responds |
| ~01:45 | `LoadGamePre` phase | `/polis/status` |
| ~01:50 | `worldReady=true` | Server ready (previous stop point) |
| ~01:50 | `players=0` | Player entity not yet spawned |
| ~02:05 | `players=1` | Player entity exists |
| ~02:08 | Render handler fires | `[polis] OnRenderFrame: Handler registered and called!` |
| ~02:10 | FPS stabilizes | 19-24 FPS (game visually ready) |
| ~02:15 | User confirms visual | Loading screen gone |

**Key finding:** ~25 second gap between `worldReady=true` and client visually ready.

## Solution: Three-Stage Ready Detection

1. **Server ready:** Wait for `worldReady=true` from `/polis/status`
2. **Client ready:** Watch `client-main.log` for `[polis] OnRenderFrame: Handler registered and called!`
3. **Post-delay:** Configurable settling time (default 5s) for final loading

## vsctl.py Commands

```bash
vsctl status              # Show all ready states
vsctl start               # Start VS with test-lands world
vsctl start --wait        # Start and wait for fully ready
vsctl stop                # Clean shutdown (server /stop, then kill client)
vsctl restart             # Full cycle: stop + start + wait
vsctl wait                # Wait for running game to be ready
```

**Options:**
- `--timeout` / `-t` - Total timeout in seconds (default: 180)
- `--post-ready-delay` / `-d` - Settling time after client signal (default: 5)
- `--world` / `-w` - World name (default: test-lands)

## Clean Shutdown Sequence

1. Send `/stop` via harness (`POST /polis/servercmd {"cmd": "/stop"}`)
2. Wait for harness to become unreachable (server saved and stopped)
3. Kill client process (`flatpak kill at.vintagestory.VintageStory`)

**Server log signals for clean shutdown:**
- `Server stop requested, begin shutdown sequence`
- `Entering runphase Shutdown`
- `[polis-harness] HTTP/WebSocket server stopped`
- `[polis] Harmony patches removed.` (final)

## Test Results

### Full Restart Cycle (PASS)
```
[vsctl] Restarting VS...
[vsctl] Sending /stop to server...
[vsctl] Waiting for server to stop...
[vsctl] Server stopped
[vsctl] Killing VS client...
[vsctl] VS stopped
[vsctl] Starting VS with world 'test-lands'...
[vsctl] VS process launched
[vsctl] Waiting for game ready (timeout: 180s, post-delay: 5s)...
[vsctl] VS starting, waiting for harness...
[vsctl] Run phase: LoadGamePre
[vsctl] Server ready (worldReady=true)
[vsctl] Waiting for client ready signal...
[vsctl] Client ready (render handler registered)
[vsctl] Waiting 5s for final settling...
[vsctl] Game fully ready!
```

### Status Check (PASS)
```
process_running: True
harness_reachable: True
world_ready: True
client_ready: True
run_phase: RunGame
mod_version: 0.1.0
```

## Known Issues / Future Investigation

### Race condition on stop
Occasionally `flatpak kill` reports process still running, but subsequent status check shows it's stopped. Likely a timing issue between kill signal and process exit detection.

**Workaround:** Current code continues anyway; status check confirms stopped.

**TODO:** Add retry loop or longer wait after kill before checking.

### Process spawn delay
After `flatpak run`, there's a brief delay before the process is detectable by `pgrep`.

**Fix applied:** Added 3-second delay in `cmd_start` before calling `cmd_wait`.

### FPS-based detection considered but rejected
Initially considered using FPS threshold (>15 FPS) as ready signal, but this is hardware-dependent and unreliable across systems. The render handler registration is a better signal.

## Files Created/Modified

| File | Change |
|------|--------|
| `scripts/vsctl.py` | New - game lifecycle controller |
| `docs/journal/2026-01-18-vsctl-game-controller.md` | New - this report |

## Agentic Loop Enablement

With vsctl, the agentic development loop can now be:

```
1. Agent modifies code
2. dotnet build
3. cp to Mods folder
4. vsctl restart --wait
5. Run tests via poliscli
6. vsctl stop (or continue testing)
```

All steps are now automatable without human intervention.
