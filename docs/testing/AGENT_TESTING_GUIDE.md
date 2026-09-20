# Agent Testing Guide for polis-builder-npc

This guide enables AI agents (Claude, Codex, etc.) to autonomously test the mod via the HTTP harness.

## Environment Variables

These can be overridden; defaults work for the standard dev setup:

| Variable | Default | Purpose |
|----------|---------|---------|
| `HARNESS_URL` | `http://localhost:8585` | Test harness base URL |
| `VSDATA` | `../vsdata` | VS user data (relative to repo root) |
| `HARNESS_TIMEOUT` | `10` | Seconds to wait for harness ready |

## Architecture Overview

### HTTP Test Harness
- The mod runs an HTTP server (default port 8585) for automated testing
- All game interactions happen via HTTP - no in-game commands needed
- Harness starts automatically when VS server loads the mod
- Check server log for: `[polis] Test harness started on port 8585`

### Request/Response Patterns

**Command requests** (POST /polis/command):
```json
{
  "cmd": "command_name",
  "args": ["arg1", "arg2"],
  "context": {
    "playerUid": "player-uid-here",
    "spawnOffset": [0, 0, 2],
    "useLookTarget": true
  }
}
```

**Command responses**:
```json
{
  "Ok": true,
  "Message": "Human-readable result",
  "Data": { "optional": "structured data" }
}
```

**State responses** (GET /polis/state):
```json
{
  "Bot": {
    "Id": 12345,
    "Pos": [X, Y, Z],
    "CurrentHealth": 20,
    "MaxHealth": 20,
    "RightHand": {"Code": "game:item-code", "Qty": 5},
    "LeftHand": null,
    "Backpack": null
  },
  "Items": [{"Id": 123, "Code": "game:item", "Qty": 1, "Dist": 2.5}],
  "LastAction": {"Name": "cmd", "Ok": true, "Msg": "result"},
  "LastActionMs": 12345,
  "LastActionId": 1,
  "Error": null
}
```

## Core Endpoints Reference

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/polis` | GET | Health check, list endpoints |
| `/polis/status` | GET | World ready state, mod version |
| `/polis/players` | GET | Online players with positions |
| `/polis/player?uid=X` | GET | Single player details |
| `/polis/look?uid=X&range=48` | GET | Player look ray trace |
| `/polis/targets?botId=X&...` | GET | Nearby interactable blocks/entities |
| `/polis/state?botId=X` | GET | Bot state, inventory, nearby items |
| `/polis/bots` | GET | List all bots |
| `/polis/command` | POST | Execute harness command |
| `/polis/servercmd` | POST | Execute raw server command (local only) |

**Important:** Player UIDs must be URL-encoded in query params (`+` → `%2B`).

## Standard Test Workflow

### Phase 0: Cleanup (required)

Always remove old bots before a new run to avoid state confusion.

```bash
# List bots
curl -s "$HARNESS_URL/polis/bots"

# Despawn each existing bot by id
curl -s -X POST "$HARNESS_URL/polis/command" \
  -H "Content-Type: application/json" \
  -d '{"cmd":"despawn","args":["BOT_ID"]}'
```

### Phase 1: Environment Check

```bash
# Check harness availability
HARNESS_URL="${HARNESS_URL:-http://localhost:8585}"
curl -s "$HARNESS_URL/polis/status"
```

Expected: `"worldReady": true`

If connection refused → Game not running
If worldReady false → Wait and retry (world still loading)

### Phase 2: Get Player Context

```bash
# Get player UID (needed for context)
curl -s "$HARNESS_URL/polis/players"
```

Extract `uid` from response. Store for subsequent calls.

### Phase 3: Spawn and Select Bot

```bash
# Spawn near player (2 blocks forward)
curl -s -X POST "$HARNESS_URL/polis/command" \
  -H "Content-Type: application/json" \
  -d '{"cmd":"spawn","context":{"playerUid":"PLAYER_UID","spawnOffset":[0,0,2]}}'

# Select the bot (use id from spawn response)
curl -s -X POST "$HARNESS_URL/polis/command" \
  -H "Content-Type: application/json" \
  -d '{"cmd":"select","args":["BOT_ID"]}'
```

### Phase 4: Execute Test Commands

Commands are executed via POST to `/polis/command`.

### Phase 5: Verify Results

```bash
# Check bot state after action
curl -s "$HARNESS_URL/polis/state?botId=BOT_ID"
```

Verify:
- `LastAction.Name` matches expected command
- `LastAction.Ok` is true/false as expected
- Bot inventory/position reflects expected changes

**Visual actions:** Always take screenshots and manually inspect them. Do not rely solely on structured output.

## Available Commands

### Bot Management
| Command | Args | Description |
|---------|------|-------------|
| `spawn` | `[entityCode] [x y z]` | Spawn bot (context.spawnOffset for relative) |
| `select` | `[botId]` | Select bot by ID |
| `selectlook` | - | Select bot under player look (needs context.playerUid) |
| `despawn` | - | Despawn selected bot |
| `bots` | - | List all bots |

### Movement
| Command | Args | Description |
|---------|------|-------------|
| `goto` | `[x y z] [astar] [speed] [fallback]` | Move to position |
| `gotolook` | `[range]` | Move to player look target |
| `stop` | - | Cancel current action |

### Inventory
| Command | Args | Description |
|---------|------|-------------|
| `give` | `[itemCode] [qty]` | Give item to bot |
| `drop` | `[slot] [qty]` | Drop from slot (-1=auto, 0=right, 1=left) |
| `pickup` | `[entityId] [range]` | Pick up item entity |
| `equip` | `[slot] [itemCode] [qty]` | Equip item to hand |

### Block/Entity Interaction
| Command | Args | Description |
|---------|------|-------------|
| `activate` | `[x y z] [argsJson]` | Activate block (door, chest, etc.) |
| `interact` | `[entityId] [mode] [range]` | Interact with entity |
| `break` | `[x y z] [dropMult]` | Break block |
| `place` | `[blockCode] [x y z] [face]` | Place block |

### Container Transfer
| Command | Args | Description |
|---------|------|-------------|
| `takefrom` | `[x y z] [containerSlot] [qty]` | Take from container to bot |
| `putinto` | `[x y z] [botSlot] [qty]` | Put from bot to container |

### Mining & Harvesting (NEW)
| Command | Args | Context Required | Description |
|---------|------|------------------|-------------|
| `mine` | `[x y z] [autocollect]` | `playerUid` | Mine block with timed progress |
| `harvest` | `[x y z] [autocollect] [validateripe]` | `playerUid` | Harvest berry bushes, resin, etc. |

**Context Requirement:** Both `mine` and `harvest` require `playerUid` in the context for claims validation:
```json
{"cmd":"mine","args":["100","65","100"],"context":{"playerUid":"PLAYER_UID_HERE"}}
```

### Utility
| Command | Args | Description |
|---------|------|-------------|
| `teststate` | - | Get full state via command |
| `validate` | `[x y z] [access]` | Validate LOS/claims for target |

## Finding Targets

### Find Containers
```bash
curl -s "$HARNESS_URL/polis/targets?botId=BOT_ID&radius=10&mode=blocks&codeContains=chest,barrel,vessel,trunk"
```

Containers have `EntityClass` like `GenericTypedContainer`, `Barrel`, etc.

### Find Items on Ground
```bash
curl -s "$HARNESS_URL/polis/targets?botId=BOT_ID&radius=6&mode=entities&q=stone"
```

### Find Specific Blocks
```bash
curl -s "$HARNESS_URL/polis/targets?botId=BOT_ID&radius=12&mode=blocks&q=door"
```

## Common Error Messages

| Error | Cause | Fix |
|-------|-------|-----|
| `actor is not an agent` | Action missing vas parameter | Code bug - report |
| `out of range dist=X range=Y` | Bot too far from target | Move bot closer with goto |
| `block is not a container` | Target isn't a container | Check coordinates |
| `container slot X is empty` | Nothing in that slot | Try different slot |
| `right hand is empty` | No item to transfer | Give item first |
| `inventory full` | Bot can't hold more | Drop something first |
| `No line of sight` | Bot can't see target | Reposition bot |
| `CanCollect returned false` | Item just spawned | Wait 1-2 seconds |
| `Bot X not found` | Invalid bot ID | Check /polis/bots |

## Output Format Template

Agents should structure test output as:

```
=== TEST: [Test Name] ===

ENVIRONMENT:
- Harness: [URL] - [READY/UNAVAILABLE]
- Player: [name] (uid: [uid])
- Bot: #[id] at [x, y, z]

SETUP:
- [Setup step 1]: [result]
- [Setup step 2]: [result]

TEST CASES:

[Test Case 1 Name]
- Command: [command with args]
- Response: [Ok: true/false, Message: "..."]
- State Check: [what was verified]
- Result: [PASS/FAIL]
- Notes: [any observations]

[Test Case 2 Name]
- ...

SUMMARY:
- Passed: X/Y
- Failed: [list]
- Blocked: [list with reasons]

ISSUES:
- [Any bugs or unexpected behavior found]
```

## LastAction State Tracking

The `LastAction` field in state responses tracks action progress and completion:

```json
{
  "LastAction": {
    "Name": "mine",
    "Ok": true,
    "Msg": "mined"
  },
  "LastActionId": 42,
  "LastActionMs": 1705420800000
}
```

### State Progression for Timed Actions

Actions like `mine` and `harvest` report multiple states:

| Phase | LastAction.Msg | LastActionId |
|-------|----------------|--------------|
| Started | `"mining started"` | N |
| Completed | `"mined"` | N+1 |

**Verification pattern:**
1. Record `LastActionId` before command
2. Execute command
3. Poll state - check for "started" message, `LastActionId` incremented
4. Wait for completion time
5. Poll state - check for final message ("mined", "harvested"), `LastActionId` incremented again

### Detecting Completion

```bash
# Wait for action to complete by polling LastActionId
INITIAL_ID=$(curl -s "$HARNESS_URL/polis/state?botId=$BOT_ID" | jq -r '.LastActionId')
# ... execute command ...
while true; do
  CURRENT=$(curl -s "$HARNESS_URL/polis/state?botId=$BOT_ID")
  CURRENT_ID=$(echo "$CURRENT" | jq -r '.LastActionId')
  CURRENT_MSG=$(echo "$CURRENT" | jq -r '.LastAction.Msg')
  if [[ "$CURRENT_MSG" == "mined" ]] || [[ "$CURRENT_MSG" == "harvested" ]]; then
    echo "Action completed: $CURRENT_MSG"
    break
  fi
  sleep 0.5
done
```

---

## Tool Tier Reference (Mining)

| Block Type | Required Tier | Can Mine Bare-Handed |
|------------|---------------|----------------------|
| Soil, Gravel | 0 | Yes |
| Sand, Clay | 0 | Yes |
| Loose stones | 0 | Yes |
| Stone/Rock | 1 | No - needs pickaxe |
| Ore (copper, tin) | 2 | No - needs bronze+ |
| Hard ore (iron) | 3 | No - needs iron+ |

| Tool Material | Tier |
|---------------|------|
| Bare hands | 0 |
| Flint | 1 |
| Copper | 2 |
| Bronze | 3 |
| Iron | 4 |
| Steel | 5 |

**Error when tier insufficient:**
```json
{"Ok": false, "Message": "Tool tier insufficient: 1 < 2"}
```

---

## Tips for Robust Testing

1. **Always check harness status first** - Don't assume game is running
2. **Store IDs** - Bot IDs, entity IDs from responses are needed for subsequent calls
3. **Add small delays** - `sleep 1` between commands allows game state to update
4. **Verify state after actions** - Don't just check Ok; verify actual state changed
5. **Handle partial success** - Some operations may partially complete
6. **Use botId for targets** - Bot-anchored scans are more reliable than player-anchored
7. **Check LastAction** - It persists until next action; verify the action name matches
8. **Track LastActionId** - For timed actions, the ID increments on start AND completion
9. **Include playerUid in context** - Required for `mine`, `harvest`, and other claim-validated actions

## See Also

- `docs/TESTING_HARNESS.md` - Full harness documentation
- `docs/TESTING_HARNESS_OUTPUTS.md` - Example responses from live runs
- `docs/TESTING_HARNESS_TARGETS.md` - Targets endpoint details
- `docs/testing/test-plans/` - Specific test case templates:
  - `container-transfer.md` - Container interaction tests
  - `mine-harvest-actions.md` - Mining and harvesting tests (NEW)
