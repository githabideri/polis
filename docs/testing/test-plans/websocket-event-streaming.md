# WebSocket Event Streaming Test Plan

**Last Updated:** 2026-01-17
**Status:** Verified working

## Quick Start

### Automated Test (Python)
```bash
python3 scripts/test-websocket.py
```

### Automated Test (Browser/Puppeteer)
```bash
cd tools/browser-test
bun test-ws-with-actions.js
```

### Manual Test (Web UI)
Open in Chrome: `http://localhost:8585/polis/ui`

## Prerequisites

1. Vintage Story server running with polis-builder-npc mod
2. Server log shows: `[polis-harness] HTTP/WebSocket server started on port 8585`
3. Server log shows: `[polis-harness] UI available at http://localhost:8585/polis/ui`

## Known Issues

| Issue | Status | Notes |
|-------|--------|-------|
| `give` command no event | Open | Does not emit `action_complete` (drop works) |
| Firefox/Zen browser | Wontfix | Use Chrome - Firefox may block localhost WebSocket |

## Server Features

- **Keepalive ping**: Server sends ping every 30 seconds to prevent timeout
- **UI served from harness**: No separate HTTP server needed (`/polis/ui`)

---

## Test 1: WebSocket Connection

**Goal:** Verify WebSocket connects and upgrades successfully

**Steps:**
1. Open `http://localhost:8585/polis/ui` in Chrome
2. Check log panel for connection status

**Expected:**
- Log shows "WebSocket connected"
- Log shows "Subscribed to normal events"
- UI shows "WS: Live" indicator

**Alternative (curl):**
```bash
curl -i -N \
  -H "Connection: Upgrade" \
  -H "Upgrade: websocket" \
  -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" \
  -H "Sec-WebSocket-Version: 13" \
  http://localhost:8585/polis/ws
```
Expected: `HTTP/1.1 101 Switching Protocols`

---

## Test 2: Subscription Levels

**Goal:** Verify subscription filtering works

**Steps:**
1. Connect via web UI
2. Set "Events" dropdown to "Normal"
3. Spawn a bot → should see `bot_spawned` event
4. Change to "Debug" level
5. Enable debug: run `/polis debug on` in game
6. Trigger an action (e.g., goto)

**Expected:**
- Normal level: Only key events (spawn, action_complete, died)
- Debug level: Additional `log` events with internal details

**Browser console test:**
```javascript
ws = new WebSocket("ws://localhost:8585/polis/ws");
ws.onmessage = (e) => console.log(JSON.parse(e.data));
ws.onopen = () => ws.send(JSON.stringify({subscribe:{level:"debug"}}));
```

---

## Test 3: action_complete Event

**Goal:** Verify action completion events are emitted

**Steps:**
```bash
# 1. Spawn a bot
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"spawn"}'

# 2. Give item (NOTE: does not emit event currently)
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"give","args":["game:stone-granite","5"]}'

# 3. Drop item (emits event)
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"drop"}'
```

**Expected event (drop):**
```json
{"type":"action_complete","data":{"botId":123,"action":"drop","ok":true,"msg":"dropped 5x game:stone-granite",...}}
```

**Verify:**
- `botId` matches spawned bot
- `ok` is true for successful actions
- `msg` describes what happened
- `actionId` increments with each action

---

## Test 4: bot_spawned Event

**Goal:** Verify spawn events from different sources

### 4a: Spawn via harness command
```bash
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"spawn"}'
```
**Expected:**
```json
{"type":"bot_spawned","data":{"botId":123,"pos":[x,y,z],"type":"polisbot","source":"spawn_command"}}
```

### 4b: Spawn via in-game command
Run `/polis spawn` in game chat.

**Expected:**
```json
{"type":"bot_spawned","data":{"botId":456,"pos":[x,y,z],"type":"polisbot","source":"player_command"}}
```

---

## Test 5: bot_died Event

**Goal:** Verify death events are emitted

**Steps:**
```bash
# Despawn the bot
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"despawn"}'
```

**Expected:**
```json
{"type":"bot_died","data":{"botId":123,"cause":"Removed"}}
```

**Causes:**
- `Removed` - despawned via command
- `Death` - killed

---

## Test 6: Keepalive (Connection Persistence)

**Goal:** Verify WebSocket stays connected beyond 60 seconds

**Steps:**
1. Open web UI, verify "WebSocket connected"
2. Wait 2+ minutes without interaction
3. Connection should remain open

**Expected:**
- No disconnection messages
- Server sends ping every 30 seconds (visible in DevTools Network → Socket → Messages)

---

## Test 7: UI Integration

**Goal:** Full integration test with web UI

**Steps:**
1. Open `http://localhost:8585/polis/ui`
2. Click "Spawn Bot" button
3. Enter item code, click "Give"
4. Click "Drop" button

**Expected:**
- Each action updates log immediately (real-time via WebSocket)
- Bot state panel updates after each action
- Events appear without page refresh

---

## Quick Smoke Test

```bash
# 1. Check server ready
curl -s http://localhost:8585/polis/status | jq .server.worldReady

# 2. Open web UI in browser
# http://localhost:8585/polis/ui

# 3. Spawn, give, drop, despawn
curl -s -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" -d '{"cmd":"spawn"}'

curl -s -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" -d '{"cmd":"give","args":["game:stone-granite","5"]}'

curl -s -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" -d '{"cmd":"drop"}'

curl -s -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" -d '{"cmd":"despawn"}'

# 4. Verify events appeared in web UI log
```

---

## Pass/Fail Criteria

| Test | Pass Criteria |
|------|---------------|
| 1. Connection | "WebSocket connected" in log |
| 2. Subscription | Level filtering works |
| 3. action_complete | Events for drop action |
| 4. bot_spawned | Events on spawn |
| 5. bot_died | Events with correct cause |
| 6. Keepalive | Connection persists > 2 min |
| 7. UI Integration | Real-time updates |
