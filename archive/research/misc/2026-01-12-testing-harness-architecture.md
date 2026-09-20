# Testing Harness Architecture

**Date:** 2026-01-12
**Status:** Fully implemented
**Supersedes:** External automation approach (`2026-01-06-automation-loop-findings.md`)

## Problem Statement

The current testing approach has critical limitations:

1. **Timing brittleness**: xdotool scripts rely on fixed delays, but game loading is variable
2. **No state verification**: Can only observe via logs, not query actual world state
3. **No live control**: Must run pre-made scripts, can't interact dynamically
4. **Agent unfriendly**: External agent sessions can't drive tests or observe results reliably

## Goals

1. **Robust verification**: Query actual game state (inventories, entities, positions)
2. **Live control**: Send commands on-demand from outside the game
3. **Structured feedback**: JSON output for both human and agent consumption
4. **Diagnostic failures**: When tests fail, output points directly to the cause
5. **Multi-mode access**: Same API works for manual testing, web UI, and agent automation

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                      EXTERNAL CLIENTS                           │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │  Web Browser │  │  Agent/CLI   │  │  Manual (in-game)    │  │
│  │  test-ui.html│  │  HTTP client │  │  /polis commands     │  │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────┘  │
│         │                 │                      │              │
│         └────────┬────────┘                      │              │
│                  │ HTTP (localhost:8585)         │ Chat         │
│                  ▼                               ▼              │
├─────────────────────────────────────────────────────────────────┤
│                   POLIS MOD (VS Server Process)                 │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    PolisTestHarness                      │   │
│  │  ┌─────────────────┐    ┌─────────────────────────┐     │   │
│  │  │  HttpListener   │───▶│ EnqueueMainThreadTask() │     │   │
│  │  │  (port 8585)    │    │ (thread-safe bridging)  │     │   │
│  │  └─────────────────┘    └───────────┬─────────────┘     │   │
│  └─────────────────────────────────────┼───────────────────┘   │
│                                        │                        │
│                                        ▼                        │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                 Existing /polis Commands                 │   │
│  │  spawn, select, goto, pickup, drop, teststate, etc.     │   │
│  └─────────────────────────────────────┬───────────────────┘   │
│                                        │                        │
│                                        ▼                        │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              BotState + World State                      │   │
│  │  - Bot inventory (hand slots)                           │   │
│  │  - Nearby entities (EntityItem, etc.)                   │   │
│  │  - Last action result (name, ok, message)               │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## Implementation Layers

### Layer 1: State Query Command (`/polis teststate`)

**Purpose:** Query current bot and world state from within the game.

**Command:** `/polis teststate [radius]`

**Output (Chat - human readable):**
```
=== POLIS TESTSTATE ===
Bot #12345 @ (100.5, 65.0, -200.3)
  RightHand: game:stone-granite x5
  LeftHand: (empty)
Items (r=10): 2 found
  #67890 game:flint x1 @ 1.2m
  #67891 game:stick x4 @ 4.5m
LastAction: pickup ok=true "picked 5x game:stone-granite"
```

**Output (Log - machine readable):**
```
[polis] TESTSTATE {"bot":{"id":12345,"pos":[100.5,65.0,-200.3],"rightHand":{"code":"game:stone-granite","qty":5},"leftHand":null},"items":[{"id":67890,"code":"game:flint","qty":1,"dist":1.2}],"lastAction":{"name":"pickup","ok":true,"msg":"picked 5x game:stone-granite"}}
```

**Implementation:**
- Uses `api.World.GetEntitiesAround()` with filter `e => e is EntityItem`
- Reads `bot.Entity.RightHandItemSlot` and `LeftHandItemSlot`
- Reads action result from `BotState` fields

### Layer 2: Action Result Tracking

**Purpose:** Store last action result for diagnostic queries.

**BotState additions:**
```csharp
public string LastActionName;      // "pickup", "drop", "goto", etc.
public bool LastActionOk;          // Success or failure
public string LastActionMsg;       // Detailed message with IDs, counts, reasons
public long LastActionMs;          // api.World.ElapsedMilliseconds when recorded
```

**Action reporting pattern:**
```csharp
// In action Start() method, after execution:
RecordActionResult(botState, "pickup", true, $"picked {count}x {itemCode} from #{entityId}");

// On failure:
RecordActionResult(botState, "pickup", false, $"CanCollect returned false for entity {entityId}");
```

**Failure messages must include:**
- Entity IDs involved
- Distances/ranges (if relevant)
- Stack sizes (if relevant)
- Specific API return values or error reasons

### Layer 3: HTTP API

**Purpose:** Enable external control without xdotool timing issues.

**Endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/polis/state?botId=&radius=10` | Returns teststate JSON |
| `POST` | `/polis/command` | Execute a command, body: `{"cmd":"pickup","args":[]}` |
| `GET` | `/polis/bots` | List all bots with basic info |

**Thread Safety:**
All HTTP handlers must use `api.Event.EnqueueMainThreadTask()` to bridge from HTTP thread to game thread:

```csharp
httpListener.BeginGetContext(ar => {
    var context = httpListener.EndGetContext(ar);
    // Parse request...

    api.Event.EnqueueMainThreadTask(() => {
        // Safe to access world/entities here
        var result = ExecuteCommand(cmd, args);
        // Write response
        SendJsonResponse(context, result);
    }, "polis-http-cmd");

    httpListener.BeginGetContext(...); // Continue listening
}, null);
```

**Configuration:**
- Default port: 8585 (configurable via mod config)
- Bind to localhost only by default (security)
- Optional: config flag to enable/disable HTTP server

### Layer 4: Web UI

**Purpose:** Visual control panel for manual testing and observation.

**File:** `assets/polis-builder-npc/test-ui.html` (served by mod or opened locally)

**Features:**
- Command buttons: Spawn, Give Item, Drop, Pickup, Stop, TestState
- Live state display: Polls `/polis/state` every 1-2 seconds
- Action log: Shows recent commands and their results
- Bot selector: Dropdown if multiple bots exist

**Minimal implementation:** Single HTML file with vanilla JS, ~200 lines.

## Diagnostic Design

### Truth Table for Test Verification

| State After Action | LastAction Result | Interpretation |
|--------------------|-------------------|----------------|
| Correct | `ok=true` | Working correctly |
| Correct | `ok=false` + reason | Bug: result tracking wrong |
| Wrong | `ok=true` | Bug: action logic wrong |
| Wrong | `ok=false` + reason | Expected failure, reason explains why |

### Example: Pickup Failure Diagnosis

| Symptom | LastAction Message | Diagnosis |
|---------|-------------------|-----------|
| Item still on ground, hand empty | `"CanCollect returned false for #12345"` | Item too fresh (< 1s since spawn) |
| Item still on ground, hand empty | `"out of range dist=8.5 range=5.0"` | Bot didn't walk close enough |
| Item still on ground, hand empty | `"inventory full, nothing transferred"` | Bot hands already occupied |
| Item still on ground, hand empty | `"target entity 12345 not found"` | Item despawned or wrong ID |

## Test Workflow Example

### Manual Test: Drop → Pickup Round-Trip

```bash
# In-game or via HTTP:

/polis spawn
/polis teststate
# Verify: Bot exists, hands empty

/polis give game:stone-granite 5
/polis teststate
# Verify: RightHand has stone x5

/polis drop
# Wait for action to complete
/polis teststate
# Verify: RightHand empty, Items list has stone x5

# Wait 2 seconds for CanCollect gate

/polis pickup
/polis teststate
# Verify: RightHand has stone x5, Items list empty
# Verify: LastAction = pickup, ok = true
```

### Web UI Test Flow

1. Open `test-ui.html` in browser
2. Click [Spawn] → State panel shows new bot
3. Enter "game:stone-granite" in item field, click [Give]
4. State panel updates: RightHand shows stone x5
5. Click [Drop] → State updates: RightHand empty, Items shows stone
6. Wait 2s, click [Pickup] → State updates: RightHand has stone, Items empty
7. Action log shows all commands with success/failure

## Implementation Plan

| Step | Component | Effort | Dependencies | Status |
|------|-----------|--------|--------------|--------|
| 1 | BotState action result fields | 30 min | None | ✅ Done |
| 2 | `/polis teststate` command | 1 hour | Step 1 | ✅ Done |
| 3 | Modify actions to record results | 1 hour | Step 1 | ✅ Done |
| 4 | HTTP server skeleton | 1 hour | .NET HttpListener | ✅ Done |
| 5 | HTTP → command bridge | 30 min | Steps 2-4 | ✅ Done |
| 6 | Basic web UI | 1-2 hours | Step 5 | ✅ Done |

### Implementation Notes (2026-01-12)

**Layer 1: BotState fields**
- Added to `BotState` class: `LastActionName`, `LastActionOk`, `LastActionMsg`, `LastActionMs`
- Added `RecordActionResult(name, ok, msg, elapsedMs)` method

**Layer 2: /polis teststate**
- Uses `GetEntitiesAround()` with `e => e is EntityItem` filter
- Outputs human-readable to chat, JSON to log with `[polis] TESTSTATE` prefix
- Shows: bot ID/pos, hand contents, nearby items (sorted by distance), last action result

**Layer 3: Action result callbacks**
- `PolisPickupItemAction` and `PolisDropItemAction` accept `Action<bool, string> resultCallback`
- Callbacks record to BotState via closure capturing bot reference
- Messages include entity IDs, item codes, quantities for diagnosis

## Security Considerations

- HTTP server binds to `127.0.0.1` only (localhost)
- No authentication by default (local testing only)
- Future: Optional API key for non-localhost access
- Consider: Disable HTTP server by default, enable via config

## Future Extensions

### Agent Integration
- Agent calls HTTP API to observe state and send commands
- Structured JSON enables reliable parsing
- Action result messages provide diagnostic context for agent reasoning

### Test Scenarios
- Define named test scenarios (e.g., "pickup-drop-roundtrip")
- `/polis test run <scenario>` executes predefined sequence
- Report pass/fail with detailed diagnostics

### State Diffing
- Track state before/after each action
- Automatically detect unexpected changes
- "Expected: hand empty → hand has stone. Actual: hand still empty"

## References

- VS API: `IWorldAccessor.GetEntitiesAround()` - [API Docs](https://apidocs.vintagestory.at/api/Vintagestory.API.Common.IWorldAccessor.html)
- VS API: `IEventAPI.EnqueueMainThreadTask()` - [API Docs](https://apidocs.vintagestory.at/api/Vintagestory.API.Common.IEventAPI.html)
- .NET: `System.Net.HttpListener` - [Microsoft Docs](https://learn.microsoft.com/en-us/dotnet/fundamentals/runtime-libraries/system-net-httplistener)
- Related: `docs/research/misc/2026-01-06-automation-loop-findings.md` (superseded approach)
