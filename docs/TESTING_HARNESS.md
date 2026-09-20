# Testing Harness Usage Guide

This document describes how to use the HTTP test harness for automated testing of polis-builder-npc.

For example outputs from a live run, see `docs/TESTING_HARNESS_OUTPUTS.md`.
For recent activation tests (lantern/valve/quern/etc.), see `docs/journal/2026-01-13-harness-activate-misc-blocks.md`.

## Overview

The mod runs an HTTP server on `localhost:8585` that allows external control of bots without needing to type in-game commands. This enables:
- Agent-driven testing (Claude, scripts)
- Automated test sequences
- Web UI control panel

## CLI Tool (Recommended)

For ergonomic command-line usage, use the `polis` CLI wrapper:

```bash
./scripts/poliscli.py status          # Check server ready
./scripts/poliscli.py spawn           # Spawn bot
./scripts/poliscli.py give game:pickaxe-copper
./scripts/poliscli.py mine 100 65 -200
```

See `docs/CLI.md` for full reference. The CLI provides:
- Subcommand pattern (like `git`)
- Environment variables for player UID and bot ID
- Optional TOON output format (26% token savings vs JSON)
- `--wait` flags for timed actions

The raw HTTP API documented below remains available for direct integration.

## Prerequisites

1. Vintage Story server running with polis-builder-npc mod loaded
2. Check server log for: `[polis] Test harness started on port 8585`

## UI Notes (Web)

- **Recommended:** Open `http://localhost:8585/polis/ui` (served directly from harness)
- Alternative: Open `tools/test-ui.html` via a local HTTP server (file:// may not work with WebSocket)
- If the UI shows `Disconnected`, verify `http://localhost:8585/polis` loads in the same browser.
- You can override the API base via the Connection field (stored in localStorage).
- **Browser:** Use Chrome. Firefox/Zen may have issues with localhost WebSocket.

## Agentic Usage (HTTP)

**Workflow:**
1. Wait for `GET /polis/status` to return `worldReady=true`.
2. Call `GET /polis/players` to pick a `playerUid`.
3. If you already have a bot, prefer `/polis/targets?botId=<id>` for discovery (bot-anchored scans are more reliable).
4. Call `GET /polis/look?uid=<playerUid>` when you need a player look target. **URL-encode** the uid (e.g. `+` must become `%2B`).
5. Send `POST /polis/command` with a `context` object.
6. Poll `/polis/state` and verify `LastActionId`/`LastActionMs`.

**Context object:**
```json
{
  "playerUid": "player-uid",
  "useLookTarget": true,
  "spawnOffset": [0, 0, 2],
  "gotoOffset": [0, 0, 1]
}
```
Offsets are in server-absolute world axes.

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/polis` | Health check, lists available endpoints |
| `GET` | `/polis/status` | Readiness + metadata (worldReady/runPhase) |
| `GET` | `/polis/players` | List online players (server-absolute positions) |
| `GET` | `/polis/player?uid=` | Single player detail (uid must be URL-encoded) |
| `GET` | `/polis/look?uid=&range=` | Server-side raytrace from player look (uid must be URL-encoded) |
| `GET` | `/polis/targets?playerUid=&botId=&radius=&limit=&mode=&q=&codeContains=&requireEntityClass=` | Nearby interactables (blocks/entities); prefer `botId` once a bot exists |
| `GET` | `/polis/state?botId=&radius=` | Get bot state, inventory, nearby items |
| `GET` | `/polis/bots` | List all bots |
| `GET` | `/polis/container-contents?name=\|x=&y=&z=` | Get container inventory contents |
| `GET` | `/polis/events?limit=20` | Recent event history (for polling/debugging) |
| `GET` | `/polis/screenshot?playerUid=&save=` | Capture screenshot from player's client |
| `POST` | `/polis/command` | Execute a command |
| `POST` | `/polis/servercmd` | Execute a raw server/chat command (local only) |

`/polis/state` includes `LastActionId` and `LastActionMs` for ordering and verification.
For `/polis/targets` response structure and examples, see `docs/TESTING_HARNESS_TARGETS.md`.
State scan plan + test checklist: `docs/research/misc/2026-01-13-targets-state-scan-plan.md`.

## WebSocket Event Streaming

The harness provides real-time event streaming via WebSocket at `ws://localhost:8585/polis/ws`.

**Features:**
- Server sends keepalive ping every 30 seconds (prevents timeout disconnects)
- Subscription levels for filtering event verbosity

### Connecting

```javascript
// Browser
const ws = new WebSocket('ws://localhost:8585/polis/ws');
ws.onopen = () => console.log('Connected');
ws.onmessage = (e) => console.log(JSON.parse(e.data));
```

```bash
# CLI (requires websocat or similar)
websocat ws://localhost:8585/polis/ws
```

### Subscription Levels

After connecting, send a subscription message to choose the event verbosity:

```json
{"subscribe":{"level":"normal"}}
```

| Level | Events Included |
|-------|-----------------|
| `normal` | `action_complete`, `bot_spawned`, `bot_died`, `debug_toggled` |
| `info` | Normal + `bot_unloaded` |
| `debug` | Info + `log` (internal debug details) |

### Event Types

| Event | Level | Payload |
|-------|-------|---------|
| `action_complete` | Normal | `{botId, action, ok, msg, ms, actionId}` |
| `bot_spawned` | Normal | `{botId, pos[], type, source}` |
| `bot_died` | Normal | `{botId, cause}` |
| `bot_unloaded` | Info | `{botId}` |
| `debug_toggled` | Normal | `{enabled}` |
| `log` | Debug | `{botId, category, msg}` |

### Event Format

All events have this structure:
```json
{
  "type": "action_complete",
  "level": 0,
  "data": {
    "botId": 12345,
    "action": "pickup",
    "ok": true,
    "msg": "picked 5x game:stone-granite",
    "ms": 1234567890,
    "actionId": 42
  },
  "ts": 1705500000000
}
```

### Usage in Web UI

Open `http://localhost:8585/polis/ui` - the UI polls `/polis/events` every second to display real-time events. This is more reliable than WebSocket for browser clients.

**Note:** WebSocket works reliably for Python/CLI clients but has known issues with some browsers (see Known Issues).

## Event History Endpoint

The `/polis/events` endpoint provides recent event history, useful for polling-based clients and debugging.

```bash
# Get last 20 events (default)
curl http://localhost:8585/polis/events

# Get last 50 events
curl "http://localhost:8585/polis/events?limit=50"
```

**Response:**
```json
{
  "ok": true,
  "count": 3,
  "wsConnections": 1,
  "events": [
    {"type": "action_complete", "level": 0, "data": {"botId": 123, "action": "drop", "ok": true, "msg": "dropped 5x game:stone-granite"}, "ts": 1705500000000},
    {"type": "bot_spawned", "level": 0, "data": {"botId": 123, "pos": [100, 65, 200]}, "ts": 1705499990000}
  ]
}
```

Events are returned newest-first. The `wsConnections` field shows current WebSocket client count (useful for debugging).

## Screenshot Endpoint

The `/polis/screenshot` endpoint captures a screenshot from a player's game client. This is useful for:
- LLM/VLM vision (send images to AI for bot perception)
- Debug/logging (save screenshots for test documentation)
- Automated testing verification

### Usage

```bash
# Capture screenshot (returns base64 PNG)
curl "http://localhost:8585/polis/screenshot?playerUid=<UID>"

# Capture and save to file on client
curl "http://localhost:8585/polis/screenshot?playerUid=<UID>&save=true"
```

**Note:** The `playerUid` must be URL-encoded (e.g., `+` becomes `%2B`).

### Response

```json
{
  "ok": true,
  "width": 1290,
  "height": 756,
  "base64": "iVBORw0KGgo...",
  "filePath": "/home/user/Pictures/Vintagestory/polis/screenshot-2026-01-18_13-30-00-123.png",
  "captureTimeMs": 129
}
```

### Saving the Image

```bash
# Decode base64 and save to file
curl -s "http://localhost:8585/polis/screenshot?playerUid=<UID>" | jq -r '.base64' | base64 -d > screenshot.png
```

### How It Works

1. HTTP request received by server
2. Server sends `PolisScreenshotRequestPacket` to player's client
3. Client's `PolisScreenCaptureRenderer` captures framebuffer via OpenGL `glReadPixels`
4. Client encodes to PNG using SkiaSharp
5. Client sends `PolisScreenshotResponsePacket` back to server
6. Server returns base64 PNG to HTTP client

**Performance:** Typical capture takes 50-150ms depending on resolution.

## Command Reference

Commands are sent via POST to `/polis/command` with JSON body:
```json
{"cmd": "command_name", "args": ["arg1", "arg2"], "context": {"playerUid":"..."}}
```

### spawn
Spawn a new bot at world spawn or specified coordinates. You can also pass an
explicit entity code (defaults to the mod's bot resolver).
```bash
# At world spawn
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"spawn"}'

# Explicit entity code
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"spawn","args":["polis-builder-npc:polisbot"]}'

# At specific coordinates
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"spawn","args":["100","65","-200"]}'

# Entity code + coordinates
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"spawn","args":["polis-builder-npc:polisbot","100","65","-200"]}'

# Spawn relative to a player
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"spawn","context":{"playerUid":"player-uid","spawnOffset":[0,0,2]}}'
```

### select
Select a specific bot by ID (for multi-bot scenarios).
```bash
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"select","args":["12345"]}'
```

### selectlook
Select the bot under a player's look ray.
```bash
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"selectlook","context":{"playerUid":"player-uid"}}'
```

### despawn
Despawn the selected (or first) bot.
```bash
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"despawn"}'
```

### give
Give an item to the bot's inventory (prefers right hand, then left hand, then backpacks/bag contents).
```bash
# Give 5 granite stones
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"give","args":["game:stone-granite","5"]}'

# Give 1 flint (quantity defaults to 1)
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"give","args":["game:flint"]}'
```

### equip
Equip an item directly to a specific slot (lefthand, righthand, backpack0, backpack1).
```bash
# Equip pickaxe to right hand
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"equip","args":["righthand","game:pickaxe-copper"]}'

# Equip linen sack to first backpack slot
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"equip","args":["backpack0","game:linensack"]}'

# Equip multiple items with quantity
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"equip","args":["lefthand","game:torch-basic","5"]}'
```

### place
Place a block from bot's inventory at specified coordinates. Bot will path to the location first.
```bash
# Place cobblestone at coordinates (face defaults to "up")
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"place","args":["game:cobblestone-granite","230","4","260"]}'

# Place with specific face direction (up, down, north, south, east, west)
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"place","args":["game:cobblestone-granite","230","4","260","north"]}'
```
**Note:** The coordinates specify where the block will be placed (target position), not the surface being clicked.

### setblock
Directly set a block in the world (admin/debug command, no bot required, no pathfinding).
```bash
# Set cobblestone at coordinates
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"setblock","args":["game:cobblestone-granite","230","4","260"]}'

# Clear a block (set to air)
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"setblock","args":["air","230","4","260"]}'
```

### drop
Drop items from bot's hand.
```bash
# Drop from auto-selected hand (right first, then left)
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"drop"}'

# Drop from specific slot: -1=auto, 0=right hand, 1=left hand
# Drop 3 items from right hand
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"drop","args":["0","3"]}'
```

### pickup
Pick up an item entity. Bot must be within range.
```bash
# Pickup nearest item within default range (3 blocks)
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"pickup"}'

# Pickup specific entity by ID
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"pickup","args":["67890"]}'

# Pickup nearest within 5 block range
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"pickup","args":["","5"]}'
```

### goto
Move bot to coordinates using pathfinding.
```bash
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"goto","args":["100.5","65","-200.3"]}'

# Goto relative to a player
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"goto","context":{"playerUid":"player-uid","gotoOffset":[0,0,2]}}'

# Goto player look target
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"goto","context":{"playerUid":"player-uid","useLookTarget":true}}'
```

### gotolook
Move bot to the player look target (server-side raytrace).
```bash
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"gotolook","context":{"playerUid":"player-uid"}}'
```

### activate
Activate a block (e.g., door/chest). Requires `context.playerUid` even when
passing explicit coordinates. Uses bot line-of-sight for validation.
```bash
# Activate by absolute coords
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"activate","args":["228","3","260"],"context":{"playerUid":"player-uid"}}'

# Activate the player's look target
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"activate","context":{"playerUid":"player-uid","useLookTarget":true}}'
```

### ignite
Ignite an IIgnitable block (firepit, torch holder, etc.). Requires `context.playerUid`.
Bot will walk to the block and ignite it. For firepits specifically:
- The firepit must have fuel in **slot 0** (fuel slot) to ignite
- Ignite sets `canIgniteFuel=true`, which triggers auto-ignition when fuel is present
- Transition: `firepit-cold` → `firepit-extinct` → `firepit-lit` (auto when fuel in slot 0)

```bash
# Ignite a firepit at coordinates
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"ignite","args":["224","3","270"],"context":{"playerUid":"player-uid"}}'

# Ignite player's look target
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"ignite","context":{"playerUid":"player-uid","useLookTarget":true}}'
```

**Firepit Workflow (full ignition):**
```bash
# 1. Give bot firewood
./scripts/poliscli.py give firewood 4

# 2. Put firewood in fuel slot (slot 0) - NOT slot 1
./scripts/poliscli.py putinto <x> <y> <z> 0 4

# 3. Ignite - firepit will light immediately if fuel is in slot 0
./scripts/poliscli.py ignite <x> <y> <z>
```

**Note:** Fuel in slot 1 (input slot) won't trigger auto-ignition. Use slot 0 (fuel slot).

### interact
Interact with an entity by id (use `/polis/targets?mode=entities` to find ids).
```bash
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"interact","args":["197","interact","4.5"]}'
```

### stop
Cancel current bot activity.
```bash
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"stop"}'
```

### teststate
Get full state (same as GET /polis/state but via command).
```bash
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"teststate"}'
```

### bots
List all bots (same as GET /polis/bots but via command).
```bash
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"bots"}'
```

### Container Registry Commands

The container registry allows you to register named references to storage containers (chests, vessels, barrels, crates). Once registered, containers can be referenced by name instead of coordinates in takefrom/putinto commands.

**Note:** VS block entities have no unique IDs - only coordinates. If a container is moved or destroyed, the registry entry becomes stale. Use `container-list` to check validity.

#### container-register
Register a named container at specific coordinates. Requires `playerUid` for ownership.

**Usage:** `container-register <name> <x> <y> <z> [type] [description]`
- `type`: optional, inferred from block code (chest, vessel, barrel, crate, generic)
- `description`: optional user description

```bash
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"container-register","args":["main-chest","224","3","270"],"context":{"playerUid":"player-uid"}}'

# With type and description
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"container-register","args":["ore-bin","225","3","270","vessel","Iron ore storage"],"context":{"playerUid":"player-uid"}}'
```

#### container-list
List all registered containers with validation status.

**Usage:** `container-list [type]`
- `type`: optional filter by container type

```bash
# List all
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"container-list"}'

# Filter by type
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"container-list","args":["chest"]}'
```

**Response includes:** `valid` field (true if container still exists at location with matching block code)

#### container-remove
Remove a container from the registry.

**Usage:** `container-remove <name>`

```bash
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"container-remove","args":["main-chest"]}'
```

#### container-contents
Get the contents of a container by name or coordinates.

**Usage:**
- By name: `container-contents <name> [includeEmpty]`
- By coordinates: `container-contents <x> <y> <z> [includeEmpty]`

```bash
# By registered name
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"container-contents","args":["main-chest"]}'

# By coordinates
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"container-contents","args":["224","3","270"]}'

# Include empty slots
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"container-contents","args":["main-chest","true"]}'
```

**Response:**
```json
{
  "Ok": true,
  "Message": "3/16 slots used",
  "Data": {
    "pos": [224, 3, 270],
    "blockCode": "game:chest-east",
    "inventoryType": "chest",
    "slotCount": 16,
    "occupiedCount": 3,
    "isEmpty": false,
    "slots": [
      {"slot": 0, "code": "game:firewood", "qty": 4},
      {"slot": 1, "code": "game:stone-granite", "qty": 32},
      {"slot": 5, "code": "game:clay-blue", "qty": 8}
    ]
  }
}
```

Also available as GET endpoint: `GET /polis/container-contents?name=main-chest` or `GET /polis/container-contents?x=224&y=3&z=270`

#### container-set
Set a container slot directly without requiring a bot. This is an admin-level command useful for test setup automation.

**Usage:** `container-set <x> <y> <z> <slot> <itemCode> [qty]`

**Parameters:**
- `x y z`: Container coordinates
- `slot`: 0-indexed slot in the container
- `itemCode`: Full item/block code (e.g., `game:stone-granite`, `game:firewood`)
- `qty`: optional, defaults to 1

```bash
# Set slot 0 to 10 granite stones
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"container-set","args":["507","4","525","0","game:stone-granite","10"]}'

# Add firewood to firepit fuel slot
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"container-set","args":["496","4","520","0","game:firewood","8"]}'
```

**CLI usage:**
```bash
./scripts/poliscli.py container-set 507 4 525 0 game:stone-granite 10
```

**Response:**
```json
{
  "Ok": true,
  "Message": "Set slot 0 at 507,4,525 to 10x game:stone-granite"
}
```

**Notes:**
- Does not require a bot to be spawned
- Does not check claims (admin-level command for test setup)
- Works with any IBlockEntityContainer (chests, firepits, querns, barrels, etc.)
- Replaces existing contents in the target slot

### takefrom
Take items from a container block into bot's inventory. Requires `playerUid` for ownership validation.

**Usage:**
- By coordinates: `takefrom <x> <y> <z> <containerSlot> [qty]`
- By registered name: `takefrom <name> <containerSlot> [qty]`

**Parameters:**
- `containerSlot`: 0-indexed slot in the container
- `qty`: optional, defaults to all items in slot

```bash
# Take all items from container slot 0 (by coordinates)
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"takefrom","args":["224","3","270","0"],"context":{"playerUid":"player-uid"}}'

# Take 5 items from slot 2
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"takefrom","args":["224","3","270","2","5"],"context":{"playerUid":"player-uid"}}'

# Take from registered container by name
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"takefrom","args":["main-chest","0"],"context":{"playerUid":"player-uid"}}'
```

**LastAction result:** `{"Name":"takefrom","Ok":true,"Msg":"transferred 5 items from container to bot"}`

### putinto
Put items from bot's inventory into a container block. Requires `playerUid` for ownership validation.

**Usage:**
- By coordinates: `putinto <x> <y> <z> <botSlot> [qty]`
- By registered name: `putinto <name> <botSlot> [qty]`

**Parameters:**
- `botSlot`: 0=right hand, 1=left hand, 2+=backpack slots
- `qty`: optional, defaults to all items in slot

```bash
# Put all items from bot's right hand (slot 0) into container
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"putinto","args":["224","3","270","0"],"context":{"playerUid":"player-uid"}}'

# Put 3 items from bot's left hand (slot 1)
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"putinto","args":["224","3","270","1","3"],"context":{"playerUid":"player-uid"}}'

# Put into registered container by name
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"putinto","args":["main-chest","0"],"context":{"playerUid":"player-uid"}}'
```

**LastAction result:** `{"Name":"putinto","Ok":true,"Msg":"transferred 5 items from bot to container"}`

### mine
Mine a block (timed action). Respects tool tier requirements. Bot must have appropriate tool equipped.

**Usage:** `mine <x> <y> <z> [autocollect]`
- `autocollect`: "true" to auto-pickup drops, "false" (default) to leave on ground

**State progression:** `"mining started"` → `"mined"` (or `"mined, collected X"` with autocollect)

```bash
# Mine block, leave drops on ground
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"mine","args":["218","3","263","false"],"context":{"playerUid":"player-uid"}}'

# Mine with auto-collect
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"mine","args":["218","3","263","true"],"context":{"playerUid":"player-uid"}}'
```

**Response includes estimated time:** `"Bot #334 mining game:ore-lignite-chalk at (218, 3, 263), est 8.0s"`

**LastAction results:**
- No autocollect: `{"Name":"mine","Ok":true,"Msg":"mined"}`
- Autocollect successful: `{"Name":"mine","Ok":true,"Msg":"mined, collected 5"}`
- Autocollect with overflow (inventory full): `{"Name":"mine","Ok":true,"Msg":"mined, collected 3/8, overflow: 5x game:gravel"}`

**Tool tier examples:**
- Soil: bare-handed OK
- Rock (granite, bauxite): copper pickaxe (tier 2) required
- Ore (lignite, limonite): copper pickaxe (tier 2) required
- Higher-tier ores: iron pickaxe or better required

### harvest
Harvest a harvestable block (berries, resin, etc.) using timed interaction.

**Usage:** `harvest <x> <y> <z> [autocollect] [validateripe]`
- `autocollect`: "true" to auto-pickup drops (default: false)
- `validateripe`: "true" to check ripeness (default: true), "false" to skip check

**State progression:** `"harvest started"` → `"harvested"`

```bash
# Harvest ripe berry bush
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"harvest","args":["229","3","274"],"context":{"playerUid":"player-uid"}}'

# Harvest with auto-collect, skip ripeness check
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"harvest","args":["229","3","274","true","false"],"context":{"playerUid":"player-uid"}}'
```

**Tested targets:** `game:bigberrybush-redcurrant-ripe`

### grind
Grind items in a quern (timed action). The quern must have grindable items in its input slot.

**Usage:** `grind <x> <y> <z> [count] [duration]`
- `count`: max items to grind (0 = unlimited, grind until input exhausted)
- `duration`: max grinding time in seconds (0 = unlimited)

**State progression:** `"grinding started"` → `"ground N item(s): <reason>"`

```bash
# Grind all items in quern until input exhausted
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"grind","args":["229","3","274"],"context":{"playerUid":"player-uid"}}'

# Grind at most 5 items
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"grind","args":["229","3","274","5"],"context":{"playerUid":"player-uid"}}'

# Grind for at most 10 seconds
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"grind","args":["229","3","274","0","10"],"context":{"playerUid":"player-uid"}}'
```

**LastAction results:**
- Success (input exhausted): `{"Name":"grind","Ok":true,"Msg":"ground 5 item(s): input exhausted"}`
- Success (count limit): `{"Name":"grind","Ok":true,"Msg":"ground 3 item(s): reached count limit (3)"}`
- Success (duration limit): `{"Name":"grind","Ok":true,"Msg":"ground 2 item(s): reached duration limit (10.0s)"}`
- Not a quern: `{"Name":"grind","Ok":false,"Msg":"block game:chest-north is not a quern"}`
- No grindable input: `{"Name":"grind","Ok":false,"Msg":"quern cannot grind (no input or not grindable)"}`

**Grindable items:** grain (wheat, spelt, flax, rice, etc.) → flour

### press
Press fruit in a fruit press to extract juice. The fruit press must have fruit mash loaded and an empty bucket in position.

**Usage:** `press <x> <y> <z> [duration] [autounscrew]`
- `duration`: max pressing time in seconds (0 = unlimited, press until complete)
- `autounscrew`: whether to auto-unscrew when pressing completes (default: true)

**State progression:** `"pressing started"` → `"extracted N.nnL juice: <reason>"`

```bash
# Press fruit until complete (auto-unscrew enabled)
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"press","args":["230","3","275"],"context":{"playerUid":"player-uid"}}'

# Press for at most 15 seconds
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"press","args":["230","3","275","15"],"context":{"playerUid":"player-uid"}}'

# Press without auto-unscrew
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"press","args":["230","3","275","0","false"],"context":{"playerUid":"player-uid"}}'
```

**LastAction results:**
- Success (complete): `{"Name":"press","Ok":true,"Msg":"extracted 2.50L juice: pressing complete (fully compressed)"}`
- Success (duration limit): `{"Name":"press","Ok":true,"Msg":"extracted 1.20L juice: reached duration limit (15.0s)"}`
- Not a fruit press: `{"Name":"press","Ok":false,"Msg":"block game:chest-north is not a fruit press"}`
- No mash: `{"Name":"press","Ok":false,"Msg":"Fruit press has no mash to press"}`
- Already compressed: `{"Name":"press","Ok":false,"Msg":"Fruit press cannot screw (already fully compressed or animation active)"}`

**Pressable items:** fruit mash (from crushing berries, grapes, etc.) → juice

### clayform
Form clay into a recipe shape (timed action). Bot must have clay in inventory.
Places voxels progressively with visible animation.

**Usage:** `clayform <x> <y> <z> <recipe> [speed]`
- `recipe`: output code (e.g., "bowl-raw", "toolmold-fire-raw-anvil")
- `speed`: voxels per tick (default: 4, higher = faster)

**State progression:** `"forming started: <recipe>"` → `"completed: placed N voxel(s) for <recipe>"`

```bash
# Form a clay bowl (places clayform block, sets recipe, places voxels progressively)
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"clayform","args":["229","3","274","bowl-raw"],"context":{"playerUid":"player-uid"}}'

# Form anvil toolmold at faster speed (8 voxels/tick)
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"clayform","args":["229","3","274","toolmold-fire-raw-anvil","8"],"context":{"playerUid":"player-uid"}}'
```

**Key behavior:**
- Places a `clayform` block at target position if one doesn't exist
- Consumes 1 clay from bot inventory to initialize
- Sets the recipe and places voxels progressively (with timing to allow visible animation)
- Bot plays "hit" animation during forming
- Calls `CheckIfFinished` when complete to produce output item

**LastAction results:**
- Success: `{"Name":"clayform","Ok":true,"Msg":"completed: placed 42 voxel(s) for bowl-raw"}`
- No clay: `{"Name":"clayform","Ok":false,"Msg":"bot has no clay in inventory"}`
- Recipe not found: `{"Name":"clayform","Ok":false,"Msg":"recipe 'invalid-name' not found"}`

### knap
Knap flint or stone on a knapping surface to create tools. Bot removes voxels progressively to reveal the recipe pattern.

**Usage:** `knap <x> <y> <z> <recipe> [speed]`
- `x y z`: Position of the knapping surface block
- `recipe`: Output item code (e.g., `arrowhead-flint`, `knifeblade-flint`)
- `speed`: Voxels removed per tick (default: 4, higher = faster)

**State progression:** Poll `LastAction` for `Name=="knap"` with `Ok==true` and `Msg` containing "completed"

```bash
# Knap a flint arrowhead
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"knap","args":["229","3","274","arrowhead-flint"],"context":{"playerUid":"player-uid"}}'

# Knap faster (8 voxels per tick)
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"knap","args":["229","3","274","knifeblade-flint","8"],"context":{"playerUid":"player-uid"}}'
```

**Response:** `"Bot #334 knapping arrowhead (220 voxels to remove) at (229, 3, 274), speed=4, ~5.5s"`

**Notes:**
- Requires a `knappingsurface` block at target position
- If surface is empty, bot will initialize it with matching material from inventory
- If surface already has material, it must match the recipe ingredient
- Bot plays "hit" animation during knapping
- Calls `CheckIfFinished` when complete to produce output item

**LastAction results:**
- Success: `{"Name":"knap","Ok":true,"Msg":"completed: knapped game:flint arrowhead"}`
- No material: `{"Name":"knap","Ok":false,"Msg":"knapping surface has no material and bot has no matching material"}`
- Recipe not found: `{"Name":"knap","Ok":false,"Msg":"recipe 'invalid-name' not found"}`
- Wrong material: `{"Name":"knap","Ok":false,"Msg":"material 'stone-granite' doesn't match recipe ingredient"}`

### seal
Seal a barrel for fermentation/pickling. The barrel must contain items and liquid matching a valid sealing recipe.

**Usage:** `seal <x> <y> <z>`
- `x y z`: Position of the barrel block

**State progression:** Instant action, result in `LastAction`

```bash
# Seal a barrel at coordinates
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"seal","args":["229","3","264"],"context":{"playerUid":"player-uid"}}'
```

**Response:** `"Bot #334 sealing barrel at (229, 3, 264)"`

**Notes:**
- Barrel must contain both items and liquid matching a sealing recipe (e.g., vegetables + brine for pickling)
- Once sealed, contents will ferment over time
- Barrels auto-unseal when fermentation completes
- There is no manual unseal command - barrels unseal automatically

**LastAction results:**
- Success: `{"Name":"seal","Ok":true,"Msg":"sealed"}`
- Empty/invalid: `{"Name":"seal","Ok":false,"Msg":"barrel cannot be sealed (no valid sealing recipe - needs items + liquid for fermentation)"}`
- Already sealed: `{"Name":"seal","Ok":false,"Msg":"barrel already sealed"}`
- Wrong block: `{"Name":"seal","Ok":false,"Msg":"block game:chest is not a barrel"}`
- Out of range: `{"Name":"seal","Ok":false,"Msg":"out of range: 5.2 > 4.5"}`

### butcher
Butcher a dead entity (animal corpse) to collect meat, hide, and other drops. Bot must have a knife equipped.

**Usage:** `butcher <entityId> [autocollect]`
- `entityId`: The entity ID of a dead, harvestable creature
- `autocollect`: "true" (default) to transfer drops to bot inventory

**State progression:** Instant action, result in `LastAction`

```bash
# Butcher a dead animal (after killing it)
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"butcher","args":["12345"],"context":{"playerUid":"player-uid"}}'
```

**Response:** `"Bot #334 butchering entity 12345 (autocollect=true)"`

**LastAction results:**
- Success: `{"Name":"butcher","Ok":true,"Msg":"Butchered game:chicken-hen"}`
- No knife: `{"Name":"butcher","Ok":false,"Msg":"Knife required in right hand for butchering"}`
- Still alive: `{"Name":"butcher","Ok":false,"Msg":"Entity is still alive - kill it first"}`
- Already harvested: `{"Name":"butcher","Ok":false,"Msg":"Entity already harvested"}`

### spawnentity
Spawn any entity type (not registered as a bot). Useful for testing butcher, interact, etc.

**Usage:** `spawnentity <entityCode> [x y z]`

```bash
# Spawn a chicken near the context player
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"spawnentity","args":["game:chicken-hen"],"context":{"playerUid":"player-uid"}}'

# Spawn at specific coordinates
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"spawnentity","args":["game:pig-wild-male","100","65","200"]}'
```

**Response:** `{"Ok":true,"Message":"Spawned entity #12345 (chicken-hen) at (100.0, 65.0, 200.0)","Data":{"id":12345,...}}`

**Common animal codes:**
- `game:chicken-hen`, `game:chicken-rooster`
- `game:pig-wild-male`, `game:pig-wild-female`
- `game:sheep-bighorn-male`, `game:sheep-bighorn-female`
- `game:hare-male`, `game:hare-female`

### killentity
Instantly kill an entity by ID. Useful for testing butcher action on animals.

**Usage:** `killentity <entityId>`

```bash
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"killentity","args":["12345"]}'
```

**Response:** `"Killed entity #12345 (chicken-hen)"`

### possess
Mount a player onto the selected bot for direct control (Phase 1 possession system). Bot must be selected first.
```bash
# Select bot, then possess
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"select","args":["365"],"context":{"playerUid":"player-uid"}}'

curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"possess","context":{"playerUid":"player-uid"}}'
```

**Response:** `"Player YourPlayerName now possessing bot 365"`

### unpossess
Unmount player from possessed bot.
```bash
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"unpossess","context":{"playerUid":"player-uid"}}'
```

**Response:** `"Exited possession mode"`

### setcontrols
Inject movement controls while possessing a bot. All args are "true" or "false".

**Usage:** `setcontrols <forward> <backward> <left> <right> <sprint> <jump>`

```bash
# Move forward
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"setcontrols","args":["true","false","false","false","false","false"],"context":{"playerUid":"player-uid"}}'

# Sprint forward-right with jump
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"setcontrols","args":["true","false","false","true","true","true"],"context":{"playerUid":"player-uid"}}'

# Stop all movement
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"setcontrols","args":["false","false","false","false","false","false"],"context":{"playerUid":"player-uid"}}'
```

**Response:** `"Controls set: F=True B=False L=False R=False Sprint=False Jump=False"`

**Note:** Movement via `setcontrols` is faster than normal player movement as it directly sets control flags. For timed movement tests, use timestamps or position polling.

### animate
Play or stop animations on the selected bot. Useful for testing animation codes and future skill integration.

**Usage:** `animate <animCode> [speed] [loop]` or `animate stop [animCode]`
- `animCode`: Animation code (e.g., `hit`, `interact`, `walk`)
- `speed`: Speed multiplier (0.1-10.0, default: 1.0)
- `loop`: If present, animation loops until stopped

```bash
# Play one-shot animation
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"animate","args":["hit"]}'

# Play with speed modifier
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"animate","args":["hit","1.5"]}'

# Play looping animation
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"animate","args":["interact","1.0","loop"]}'

# Stop specific animation
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"animate","args":["stop","interact"]}'

# Stop all animations
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"animate","args":["stop"]}'
```

**Response:** `"Started animation 'hit' speed=1.00 (one-shot)"` or `"Stopped 2 animation(s)"`

**Common animation codes:**
- Locomotion: `walk`, `run`, `idle`, `sit`
- Combat: `hit`, `attack`, `hurt`
- Interaction: `interact`, `dig`, `chop`

**Note:** Available animations depend on the entity's shape file. Invalid codes return `"Failed to start animation"`.

### teleport
Teleport a player to coordinates with optional view direction (yaw/pitch). Sets the client camera direction via network packet.

**Usage:** `teleport <playerUid> <x> <y> <z> [yaw] [pitch]`
- `playerUid`: The player's UID
- `x y z`: Target coordinates
- `yaw`: Optional view yaw in radians (horizontal rotation)
- `pitch`: Optional view pitch in radians (vertical rotation)

```bash
# Teleport without view direction
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"teleport","args":["<playerUid>","100","65","-200"]}'

# Teleport facing East (yaw ≈ 4.71 radians)
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"teleport","args":["<playerUid>","100","65","-200","4.71","0"]}'

# Teleport looking slightly down (negative pitch)
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"teleport","args":["<playerUid>","100","65","-200","4.71","-0.3"]}'
```

**Response:** `"Teleported PlayerName to (100.0, 65.0, -200.0) facing yaw=4.71 pitch=0.00"`

**VS Yaw Convention:**
To face a target position from player position, use: `yaw = atan2(target.x - player.x, target.z - player.z) + π`

| Direction | Yaw (radians) |
|-----------|---------------|
| North (-Z) | 0 |
| South (+Z) | π (3.14) |
| East (+X) | 3π/2 (4.71) |
| West (-X) | π/2 (1.57) |

**Pitch:** 0 = level, negative = look down, positive = look up

**How it works:**
1. Server teleports player entity to position
2. Server sends `PolisSetViewDirectionPacket` to player's client
3. Client sets `player.CameraYaw` and `player.CameraPitch` to rotate view

### scan
Scan a bounding box region and return all blocks within it. Useful for capturing existing builds as blueprints.

**Usage:** `scan <x1> <y1> <z1> <x2> <y2> <z2> [--include-air]`
- Coordinates define two corners of the bounding box
- Order doesn't matter (min/max normalized automatically)
- Max area: 1M blocks (100x100x100)

**CLI-only options** (client-side filtering via poliscli.py):
- `--filter <pattern>` - Include only blocks matching pattern (e.g., `--filter cobble`)
- `--exclude-natural` - Exclude terrain blocks (soil, stone, gravel, sand, clay, rock, etc.)

```bash
# Scan a 7x1x7 foundation area
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"scan","args":["235","3","307","241","3","313"]}'

# Include air blocks in output
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"scan","args":["235","3","307","241","3","313","--include-air"]}'
```

**Response:**
```json
{
  "Ok": true,
  "Message": "Scanned 49 blocks",
  "Data": {
    "from": [235, 3, 307],
    "to": [241, 3, 313],
    "blockCount": 49,
    "blocks": [
      {"pos": [235, 3, 307], "code": "game:cobblestone-granite"},
      {"pos": [236, 3, 307], "code": "game:cobblestone-granite"}
    ]
  }
}
```

### verify
Verify a blueprint against world state. Returns match statistics and lists of missing/wrong blocks.

**Usage:** `verify <json_blueprint>`
- Blueprint is a JSON array of `{pos: [x,y,z], code: "blockcode"}` entries
- Returns completion percentage and detailed mismatch info

```bash
# Verify a simple blueprint
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"verify","args":["[{\"pos\":[235,3,307],\"code\":\"game:cobblestone-granite\"}]"]}'
```

**Response:**
```json
{
  "Ok": true,
  "Message": "Verified: 1/1 blocks correct (100%)",
  "Data": {
    "total": 1,
    "matched": 1,
    "missing": 0,
    "wrong": 0,
    "completionPct": 100,
    "missingBlocks": [],
    "wrongBlocks": []
  }
}
```

**Mismatch example:**
```json
{
  "Data": {
    "total": 9,
    "matched": 7,
    "missing": 1,
    "wrong": 1,
    "completionPct": 77.8,
    "missingBlocks": [{"pos": [237,3,309], "expected": "game:cobblestone-granite", "actual": "air"}],
    "wrongBlocks": [{"pos": [238,3,309], "expected": "game:cobblestone-granite", "actual": "game:planks-oak"}]
  }
}
```

## Blueprint Building (CLI)

The CLI provides high-level commands for blueprint-driven building with verification.

### Creating Blueprints

**Scan existing structure:**
```bash
# Scan and save to file
./scripts/poliscli.py scan 235 3 307 241 3 313 --output foundation.json

# Scan with relative coordinates (for reusable blueprints)
./scripts/poliscli.py scan 235 3 307 241 3 313 --output foundation.json --relative

# Filter out natural terrain blocks (soil, stone, gravel, sand, clay, rock, etc.)
./scripts/poliscli.py scan 200 1 300 250 20 350 --exclude-natural --output structure.json

# Filter to only specific block types
./scripts/poliscli.py scan 200 1 300 250 20 350 --filter cobble --output cobble-only.json
```

**Blueprint format:**
```json
{
  "name": "7x7 Foundation",
  "blocks": [
    {"pos": [0, 0, 0], "code": "game:cobblestone-granite"},
    {"pos": [1, 0, 0], "code": "game:cobblestone-granite"}
  ]
}
```

### Verifying Blueprints

```bash
# Verify blueprint at absolute positions
./scripts/poliscli.py verify foundation.json

# Verify with origin offset (for relative blueprints)
./scripts/poliscli.py verify foundation.json --origin 235 3 307

# Verbose output shows missing/wrong blocks
./scripts/poliscli.py verify foundation.json --origin 235 3 307 -v
```

### Building from Blueprints

```bash
# Build with verification (default)
./scripts/poliscli.py build blueprint.json --origin 250 3 320

# Dry-run (show what would be placed)
./scripts/poliscli.py build blueprint.json --origin 250 3 320 --dry-run

# Skip verification (faster but no progress tracking)
./scripts/poliscli.py build blueprint.json --origin 250 3 320 --no-verify

# Continue on errors
./scripts/poliscli.py build blueprint.json --origin 250 3 320 --continue-on-error
```

**Build workflow:**
1. Pre-flight checks (bot selected, inventory)
2. For each block:
   - Skip if already placed (verification)
   - Place block via `place` command
   - Verify placement
3. Final verification scan
4. Report completion percentage

**Example full workflow:**
```bash
# 1. Spawn bot and give blocks
./scripts/poliscli.py spawn
./scripts/poliscli.py select <BOT_ID>
export POLIS_BOT_ID=<BOT_ID>
./scripts/poliscli.py give game:cobblestone-granite 50

# 2. Create a simple blueprint
cat > test.json << 'EOF'
{"name":"3x3","blocks":[
  {"pos":[0,0,0],"code":"game:cobblestone-granite"},
  {"pos":[1,0,0],"code":"game:cobblestone-granite"},
  {"pos":[2,0,0],"code":"game:cobblestone-granite"},
  {"pos":[0,0,1],"code":"game:cobblestone-granite"},
  {"pos":[1,0,1],"code":"game:cobblestone-granite"},
  {"pos":[2,0,1],"code":"game:cobblestone-granite"},
  {"pos":[0,0,2],"code":"game:cobblestone-granite"},
  {"pos":[1,0,2],"code":"game:cobblestone-granite"},
  {"pos":[2,0,2],"code":"game:cobblestone-granite"}
]}
EOF

# 3. Build at target location
./scripts/poliscli.py build test.json --origin 250 3 320

# 4. Verify independently
./scripts/poliscli.py verify test.json --origin 250 3 320
```

## Server Command Endpoint (Local Only)

This endpoint executes a raw server/chat command using the server command API.
It is intended as a local-only escape hatch for live development.

```bash
curl -X POST http://localhost:8585/polis/servercmd \
  -H "Content-Type: application/json" \
  -d '{"cmd":"/time set 0"}'
```

If the command requires a player context, pass `playerUid`:
```bash
curl -X POST http://localhost:8585/polis/servercmd \
  -H "Content-Type: application/json" \
  -d '{"cmd":"/polis list","playerUid":"<player-uid>"}'
```

Response format:
```json
{
  "ok": true,
  "status": "Success",
  "message": "Bot list updated",
  "errorCode": "",
  "data": null
}
```

Notes:
- Local-only: requests are rejected unless they come from loopback.
- Uses wildcard privileges, so treat it as a trusted developer tool.
- Command reference: `docs/SERVER_COMMANDS.md` (wiki snapshot; may be outdated).
- Many vanilla commands require a player context and return `Caller must be player` if `playerUid` is omitted.
- World position args use VS parsing: bare numbers are map-middle relative. Use `=x =y =z` for absolute coords or selectors like `l[]` (look target). `l[]` depends on server-side selection and may be unavailable.

## Response Format

All responses are JSON with this structure:

### Command Response
```json
{
  "Ok": true,
  "Message": "Spawned bot #12345",
  "Data": { ... }  // Optional additional data
}
```

### State Response (GET /polis/state)
```json
{
  "Bot": {
    "Id": 12345,
    "Pos": [100.5, 65.0, -200.3],
    "CurrentHealth": 20,
    "MaxHealth": 20,
    "RightHand": {"Code": "game:stone-granite", "Qty": 5},
    "LeftHand": null
  },
  "Items": [
    {"Id": 67890, "Code": "game:flint", "Qty": 1, "Dist": 1.23},
    {"Id": 67891, "Code": "game:stick", "Qty": 4, "Dist": 4.56}
  ],
  "LastAction": {
    "Name": "pickup",
    "Ok": true,
    "Msg": "picked 5x game:stone-granite from #67890"
  },
  "Error": null
}
```

## Testing Patterns

### Pattern 1: Drop-Pickup Round Trip
Verify item transfer works correctly.

```bash
# 1. Spawn bot
curl -X POST http://localhost:8585/polis/command -H "Content-Type: application/json" -d '{"cmd":"spawn"}'

# 2. Give item
curl -X POST http://localhost:8585/polis/command -H "Content-Type: application/json" -d '{"cmd":"give","args":["game:stone-granite","5"]}'

# 3. Check state - should show item in RightHand
curl http://localhost:8585/polis/state

# 4. Drop item
curl -X POST http://localhost:8585/polis/command -H "Content-Type: application/json" -d '{"cmd":"drop"}'

# 5. Check state - RightHand empty, Items list has stone
curl http://localhost:8585/polis/state

# 6. Wait 2 seconds (CanCollect gate)
sleep 2

# 7. Pickup item
curl -X POST http://localhost:8585/polis/command -H "Content-Type: application/json" -d '{"cmd":"pickup"}'

# 8. Verify - RightHand has stone, Items empty, LastAction ok
curl http://localhost:8585/polis/state
```

### HTTP Smoke Test Runner (Script)

For a state-driven smoke test (no fixed sleeps), use the Python runner:

- Script: `scripts/polis-http-smoke.py`
- Requires: Python 3 (stdlib only)
- Flow: wait for `/polis/status` worldReady -> spawn -> select -> give -> drop -> pickup, optional goto
- Verification: polls `/polis/state?botId=...` until predicates pass or time out

Example:
```bash
python3 scripts/polis-http-smoke.py
```

Optional goto + verbose output:
```bash
python3 scripts/polis-http-smoke.py --goto 100 65 -200 --stop-after-goto --verbose
```

Key options:
- `--item-code`, `--item-qty`
- `--entity-code`
- `--pickup-range`, `--pickup-timeout`
- `--goto X Y Z`, `--goto-timeout`, `--goto-distance`
- `--timeout`, `--poll`
- `--ready-timeout`

### Pattern 2: Verify Action Results
Check LastAction for diagnostic info on failures.

```bash
# After any action, check LastAction in state
STATE=$(curl -s http://localhost:8585/polis/state)
echo "$STATE" | jq '.LastAction'

# Expected success:
# {"Name": "pickup", "Ok": true, "Msg": "picked 5x game:stone-granite from #67890"}

# Expected failure examples:
# {"Name": "pickup", "Ok": false, "Msg": "CanCollect returned false for #12345"}
# {"Name": "pickup", "Ok": false, "Msg": "out of range dist=8.5 range=3.0"}
# {"Name": "drop", "Ok": false, "Msg": "right hand is empty"}
```

### Pattern 3: Multi-Bot Testing
```bash
# Spawn first bot
curl -X POST http://localhost:8585/polis/command -H "Content-Type: application/json" -d '{"cmd":"spawn"}'
# Note the bot ID from response

# Spawn second bot at different location
curl -X POST http://localhost:8585/polis/command -H "Content-Type: application/json" -d '{"cmd":"spawn","args":["110","65","-200"]}'

# List all bots
curl http://localhost:8585/polis/bots

# Select specific bot
curl -X POST http://localhost:8585/polis/command -H "Content-Type: application/json" -d '{"cmd":"select","args":["<bot_id>"]}'
```

### Pattern 4: Butcher Workflow (Spawn → Kill → Butcher)
Full workflow for testing the butcher action with a spawned animal.

```bash
# 1. Spawn bot and give it a knife
curl -X POST http://localhost:8585/polis/command -H "Content-Type: application/json" \
  -d '{"cmd":"spawn","context":{"playerUid":"<UID>"}}'
BOT_ID=$(curl -s http://localhost:8585/polis/state | jq -r '.Bot.Id')

curl -X POST http://localhost:8585/polis/command -H "Content-Type: application/json" \
  -d '{"cmd":"give","args":["game:knife-generic-copper"]}'

# 2. Spawn a chicken near the bot
SPAWN_RESULT=$(curl -s -X POST http://localhost:8585/polis/command -H "Content-Type: application/json" \
  -d '{"cmd":"spawnentity","args":["game:chicken-hen"],"context":{"playerUid":"<UID>"}}')
CHICKEN_ID=$(echo "$SPAWN_RESULT" | jq -r '.Data.id')
echo "Spawned chicken: $CHICKEN_ID"

# 3. Kill the chicken
curl -X POST http://localhost:8585/polis/command -H "Content-Type: application/json" \
  -d "{\"cmd\":\"killentity\",\"args\":[\"$CHICKEN_ID\"]}"

# 4. Butcher the dead chicken
curl -X POST http://localhost:8585/polis/command -H "Content-Type: application/json" \
  -d "{\"cmd\":\"butcher\",\"args\":[\"$CHICKEN_ID\"],\"context\":{\"playerUid\":\"<UID>\"}}"

# 5. Verify - check bot inventory for poultry/feathers
curl -s http://localhost:8585/polis/state | jq '.Bot.RightHand, .Bot.LeftHand, .LastAction'
```

**Expected LastAction:** `{"Name":"butcher","Ok":true,"Msg":"Butchered game:chicken-hen"}`

**Verification:**
- Bot inventory should contain `game:poultry-raw` and/or `game:feather`
- Entity should be marked as harvested (butchering again fails with "already harvested")

## Diagnostic Truth Table

| State After Action | LastAction.Ok | Interpretation |
|--------------------|---------------|----------------|
| Correct | `true` | Working correctly |
| Correct | `false` | Bug: result tracking wrong |
| Wrong | `true` | Bug: action logic wrong |
| Wrong | `false` + reason | Expected failure, reason explains why |

## Common Item Codes

| Code | Description |
|------|-------------|
| `game:stone-granite` | Granite stone |
| `game:stone-andesite` | Andesite stone |
| `game:flint` | Flint |
| `game:stick` | Wooden stick |
| `game:firewood` | Firewood |
| `game:drygrass` | Dry grass |

## Web UI

For visual testing, open `http://localhost:8585/polis/ui` in Chrome. The UI:
- **Real-time updates via WebSocket** (with HTTP polling fallback)
- **Keepalive**: Server pings every 30 seconds to prevent timeout
- Shows bot inventory and nearby items
- Provides buttons for common commands
- Displays action log with success/failure status
- **Event level selector**: Choose between Normal/Info/Debug verbosity
- **Radar Map**: Visualization of surroundings (Gray=Blocks, Red=Entities, Green=Items). Click to `goto`.
- Connection status indicators for both HTTP and WebSocket

## Visual Testing (Screenshot Verification)

For automated visual verification of animations, actions, or game state, use the screenshot endpoint with careful timing.

**Always open and inspect screenshots.** Structured output is not sufficient for visual validation.

**Minimum 2 blocks distance:** Keep the player at least 2 blocks from the bot/action area to avoid player auto-pickup interfering with item drops meant for bot testing. Use `--pitch -0.5` or lower when viewing small items on the ground.

### Key Insight: Timing Matters

LLM token generation is slower than most game animations. To capture animations mid-frame:
1. Chain commands in a single shell invocation
2. Use speed modifiers to slow animations
3. For looping animations, add brief sleep before capture

### Pattern: Position Player to View Bot

```bash
# 1. Spawn bot with offset from player
curl -X POST http://localhost:8585/polis/command -H "Content-Type: application/json" \
  -d '{"cmd":"spawn","context":{"playerUid":"<UID>","spawnOffset":[3,0,0]}}'
# Note bot position from response

# 2. Teleport player near bot, facing it (yaw=4.71 faces East/+X)
curl -X POST http://localhost:8585/polis/command -H "Content-Type: application/json" \
  -d '{"cmd":"teleport","args":["<UID>","<X-2>","<Y>","<Z>","4.71","0"]}'

# 3. Capture baseline screenshot
curl -s "http://localhost:8585/polis/screenshot?playerUid=<UID-encoded>&save=true"
```

**Yaw reference (radians):**
| Direction | Yaw |
|-----------|-----|
| North (-Z) | 0 |
| East (+X) | 4.71 (3π/2) |
| South (+Z) | 3.14 (π) |
| West (-X) | 1.57 (π/2) |

### Pattern: Capture Animation

```bash
# One-shot animation with slow speed (0.3x) for capture window
curl -X POST http://localhost:8585/polis/command -H "Content-Type: application/json" \
  -d '{"cmd":"animate","args":["hit","0.3"]}' && \
curl -s "http://localhost:8585/polis/screenshot?playerUid=<UID>&save=true" | jq '.filePath'

# Looping animation - start, brief pause, capture
curl -X POST http://localhost:8585/polis/command -H "Content-Type: application/json" \
  -d '{"cmd":"animate","args":["walk","1.0","loop"]}' && \
sleep 0.3 && \
curl -s "http://localhost:8585/polis/screenshot?playerUid=<UID>&save=true" | jq '.filePath'
```

### Pattern: Verify Animation State

```bash
# Check if animation is actually running (stop reports count)
curl -X POST http://localhost:8585/polis/command -H "Content-Type: application/json" \
  -d '{"cmd":"animate","args":["stop"]}'
# "Stopped 1 animation(s)" = was running
# "Stopped 0 animation(s)" = animation code may not exist in entity shape
```

### CLI Alternative (Recommended)

Using `poliscli.py` is more ergonomic for visual testing:

```bash
export POLIS_PLAYER_UID="<your-uid>"
export POLIS_BOT_ID=<bot-id>

# Position and capture in one line
polis teleport 221 3 272 --face-bot && \
polis animate hit --speed 0.3 && \
polis screenshot --save

# Verify looping works (check stop count)
polis animate walk --loop && sleep 0.3 && polis screenshot --save
polis animate stop  # Should show "Stopped 1"
```

### Known Working Animations (polisbot)

| Animation | Type | Visual Verified |
|-----------|------|-----------------|
| `hit` | one-shot | ✅ Arm swing |
| `walk` | looping | ✅ Leg movement |
| `interact` | - | ❌ No visual (stop=0) |
| `sit` | - | ❌ No visual (stop=0) |
| `run` | - | ❌ No visual (stop=0) |

Animation codes that don't exist in the entity's shape file will return API success but produce no visual change.

### Screenshot Storage

Screenshots are saved to `~/Pictures/Vintagestory/polis/` with timestamp filenames.
A symlink at `refs/screenshots` points to this directory for easy access.

## Troubleshooting

### "Connection refused"
- Server not running or mod not loaded
- Check: `curl http://localhost:8585/polis`

### "Disconnected" in Web UI
- Verify the harness is started: `curl http://localhost:8585/polis`
- Use Chrome (Firefox/Zen may block localhost WebSocket)
- If running on a different host/port, set the API base in the UI Connection field

### "Timeout waiting for game thread"
- The harness is reachable but the world is not ready yet
- Wait for `GET /polis/status` to return `worldReady=true` (or check `Entering runphase WorldReady` in `server-main.log`)

### Coordinate mismatch
- Player HUD coords can be offset from server coords (observed ~+256 X/Z)
- Use `/polis list` or F3 debug overlay for absolute coords when spawning/moving bots

### "No bots available"
- No bot spawned yet
- Run: `spawn` command first
- If old bots exist, despawn them to avoid selecting stale IDs

### "CanCollect returned false"
- Item too fresh (just spawned, < 1 second old)
- Wait 1-2 seconds after drop before pickup

### "Dropped item is instantly re-picked"
- Bots auto-pick items they stand on when a hand slot is free
- Move the bot 1-2 blocks away immediately after drop to keep the item on the ground

### "Pickup fails right after drop"
- Drops can spawn slightly above ground; wait for the item to fall/settle before pickup

### "inventory full, nothing transferred"
- Bot inventory has no free slots
- There is no harness command to clear inventory yet

### "No item entity found nearby"
- Item left the search radius (drops can fly a few blocks)
- Increase pickup range or sample `/polis/state` quickly after drop

### "out of range"
- Bot too far from target
- Use `goto` to move closer, or increase pickup range

### Checking server logs
```bash
tail -f ../vsdata/Logs/server-main.log | grep -i "polis"
```
