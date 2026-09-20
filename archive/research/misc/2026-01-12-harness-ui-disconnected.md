# Harness UI "Disconnected" Root Cause (R6)

**Date:** 2026-01-12

## Purpose

Identify why `tools/test-ui.html` shows "Disconnected" and document low-risk fixes or usage notes.

## Summary

The UI only switches to "Connected" after a successful `fetch()` to the harness. Any network/CORS error, wrong host/port, or a non-running harness leaves the status in "Disconnected". The UI hard-codes `http://localhost:8585`, while the harness binds only to `localhost` and `127.0.0.1`. CORS is already allowed for browser access, so the most likely causes are: the HTTP server is not running, the browser cannot reach localhost (different machine or sandboxed environment), or the port is blocked.

## Evidence

- UI hard-codes the API base and marks "Disconnected" on any fetch error: `tools/test-ui.html` (API_BASE, `api()` `catch`).
- Harness only listens on `http://localhost:8585/` and `http://127.0.0.1:8585/`: `PolisTestHarness.cs`.
- CORS headers are explicitly set to allow browser access: `PolisTestHarness.cs`.
- Usage note calls out that the UI is opened from disk and should be able to hit `http://localhost:8585/polis`: `docs/TESTING_HARNESS.md`.

## Open Questions

- Are users opening the UI from a different machine or container where `localhost` is not the game host?
- Is the game running inside a sandboxed environment where the HTTP listener is not reachable from the host browser?

## Implications for Harness Design

- Document that the UI must be opened on the same machine as the game server, or the API base must be changed to match the host.
- Consider a low-risk UX improvement: allow `API_BASE` override via query string or input field in the UI to avoid code edits for remote testing.
- Provide a simple connectivity checklist: verify the server log line for harness start and confirm `curl http://localhost:8585/polis` succeeds before using the UI.
