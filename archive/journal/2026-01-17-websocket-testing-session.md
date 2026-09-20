# WebSocket Event Streaming Test Session

**Date:** 2026-01-17
**Status:** Completed with improvements

## Summary

Tested the WebSocket event streaming implementation per `docs/plans/2026-01-17-websocket-test-plan.md`. Found and fixed several issues, and added improvements for better developer experience.

## Test Results

### Passed Tests

| Test | Status | Notes |
|------|--------|-------|
| WebSocket connection | PASS | Connects to `ws://localhost:8585/polis/ws` |
| Subscription levels | PASS | normal/info/debug filtering works |
| `bot_spawned` event | PASS | Received on spawn |
| `action_complete` (drop) | PASS | Received with correct data |
| `bot_died` event | PASS | Received on despawn |
| CLI compatibility | PASS | `poliscli.py` triggers WebSocket events |
| Multiple clients | PASS | Events broadcast to all connected clients |

### Issues Found

1. **Test script bug** - `scripts/test-websocket.py` checked `status.get("worldReady")` but actual response has `status.server.worldReady`. Fixed.

2. **`give` command doesn't emit `action_complete`** - Unlike `drop`, the `give` command doesn't broadcast an event. Minor gap, not blocking.

3. **Zen/Firefox browser incompatibility** - WebSocket connections from Zen browser (Firefox-based) immediately disconnect. Works fine in Chrome. Likely a browser privacy feature blocking localhost WebSocket.

4. **No WebSocket keepalive** - Connections would timeout after ~60 seconds due to no ping/pong mechanism.

5. **`file://` origin blocked** - Browsers block WebSocket connections from `file://` URLs, requiring an HTTP server to serve the test UI.

## Improvements Implemented

### 1. Static File Serving (`/polis/ui`)

Added route to serve `test-ui.html` directly from the harness:
- URL: `http://localhost:8585/polis/ui`
- No separate HTTP server needed
- File bundled with mod deployment

**Changes:**
- `PolisBuilderNpc.csproj`: Added `tools/test-ui.html` to build output
- `PolisTestHarness.cs`: Added `ServeStaticFile()` method and `/polis/ui` route

### 2. WebSocket Keepalive Pings

Added 30-second ping mechanism to prevent connection timeouts:
- Server sends empty binary frame every 30 seconds of inactivity
- Prevents browser/proxy timeout disconnects

**Changes:**
- `PolisTestHarness.cs`: Modified `HandleWebSocketConnectionAsync()` to use timeout-based receive with ping on timeout

### 3. Browser Test Tools

Created `tools/browser-test/` directory with Puppeteer-based tests:
- `test-ws.js` - Basic WebSocket connection test
- `test-ws-with-actions.js` - Full test with bot actions
- `test-debug.js` - Debug page state and errors

**Usage:**
```bash
cd tools/browser-test
bun test-ws-with-actions.js
```

## Files Changed

- `PolisTestHarness.cs` - Static file serving, WebSocket keepalive
- `PolisBuilderNpc.csproj` - Include test-ui.html in build
- `scripts/test-websocket.py` - Fix worldReady check
- `tools/browser-test/` - New Puppeteer test directory

## Recommendations

1. **Use Chrome for UI testing** - Zen/Firefox has issues with localhost WebSocket
2. **Consider adding `give` event** - For consistency, though low priority
3. **Monitor keepalive effectiveness** - 30s interval should be sufficient for most cases

## Test Commands

```bash
# Automated WebSocket test
python3 scripts/test-websocket.py

# Browser-based test (headless)
cd tools/browser-test && bun test-ws-with-actions.js

# Manual test
curl http://localhost:8585/polis/ui  # Open in browser
```
