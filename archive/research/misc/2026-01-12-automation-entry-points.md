# Automation Entry Points (Harness)

**Date:** 2026-01-12

## Purpose

Define a reliable launch, world-load, and log-capture sequence for the agentic
harness, plus a concrete "world ready" detection signal.

## Summary

- Use the Flatpak client with `--openWorld test-lands` for fastest local launch.
- Detect readiness by scanning `server-main.log` for `Entering runphase WorldReady`,
  then wait for the harness log line before issuing HTTP commands.
- Capture logs from the Flatpak data path (or an explicit `--logPath`) and filter
  `[polis]`/errors for automation signals.
- Keep a server-only entrypoint in reserve for headless runs (`VintagestoryServer`
  via Flatpak), using the existing `serverconfig.json` save target.

## Evidence

- `polis-builder-npc/scripts/run-client-test.sh` launches with
  `flatpak run at.vintagestory.VintageStory --openWorld "${WORLD_NAME}"`
  and defaults `WORLD_NAME=test-lands`, `LOG_DIR=.../VintagestoryData/Logs`.
- `polis-builder-npc/scripts/run-client-test.sh` uses
  `READY_LOG_REGEX="Entering runphase WorldReady"` against `server-main.log`
  as its readiness gate.
- `polis-builder-npc/docs/TESTING_HARNESS.md` instructs waiting for
  `Entering runphase WorldReady` in `server-main.log` before sending commands
  and notes the harness start line `[polis] Test harness started on port 8585`.
- `polis-builder-npc/docs/research/misc/2026-01-06-automation-loop-findings.md`
  documents Flatpak client/server entrypoints and the Flatpak data/log paths,
  plus `serverconfig.json` pointing to `Saves/test-lands.vcdbs`.

## Open questions

- Should the harness expose a "world ready" endpoint to avoid log polling?
- Do we prefer client automation (xdotool + `--openWorld`) or a server-only
  headless loop for CI?
- Is the `Entering runphase WorldReady` line always present for the target
  VS version and config, or should we also watch for the harness log line as
  the primary readiness gate?

## Implications for harness design

- Gate all automation on log-based readiness to avoid `Timeout waiting for game thread`
  errors when the HTTP server is up but the world thread is not yet ready.
- Treat the log path as configurable input (support `--logPath`) to keep scripts
  stable across Flatpak/user environments.
- If a headless server mode is added, reuse the same readiness signals and log
  capture flow so the harness can operate identically across client/server runs.
