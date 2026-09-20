# Container Transfer Test Plan

**Date:** 2026-01-15
**Phase:** Phase 2 (Task/Job System)
**Feature:** Container Transfer Actions (takefrom / putinto)

## Overview

Step-by-step testing plan for container transfer functionality using the HTTP test harness. Each step is independent and should be executed sequentially to verify bot behavior at each stage.

**Approach:** LLM-guided step execution with state verification between each step. No scripted batch runs—each curl command is independent and observable.

---

## Prerequisites

1. Vintage Story server running with polis-builder-npc mod loaded
2. HTTP test harness responding on `http://localhost:8585`
3. A nearby chest or container block in the test world
4. Terminal with curl available
5. Ability to monitor `../vsdata/Logs/server-main.log` (optional but recommended)

---

## Test Steps

### Step 1: Verify World Ready
**Endpoint:** `GET /polis/status`
**Command:**
```bash
curl http://localhost:8585/polis/status
```

**Expected Result:**
```json
{
  "Ok": true,
  "worldReady": true,
  ...
}
```

**Interpretation:** If `worldReady` is false, wait 10-20 seconds and retry. World must be loaded before bot operations work.

---

### Step 2: Spawn Bot
**Endpoint:** `POST /polis/command`
**Command:**
```bash
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"spawn"}'
```

**Expected Result:**
```json
{
  "Ok": true,
  "Message": "Spawned bot #12345",
  "Data": { "EntityId": 12345 }
}
```

**Save:** Bot ID (e.g., `12345`) for all future commands.
**Interpretation:** Bot is now present in world at spawn location.

---

### Step 3: Get Player UID
**Endpoint:** `GET /polis/players`
**Command:**
```bash
curl http://localhost:8585/polis/players
```

**Expected Result:**
```json
{
  "Ok": true,
  "Players": [
    {
      "Name": "YourPlayerName",
      "Uid": "your-player-uid",
      "Pos": [x, y, z]
    }
  ]
}
```

**Save:** Your player UID (e.g., `your-player-uid`).
**Interpretation:** Confirms you are logged in; UID needed for context in some commands.

---

### Step 4: Find Nearby Chest
**Endpoint:** `GET /polis/targets`
**Command:**
```bash
curl "http://localhost:8585/polis/targets?botId=<BOT_ID>&radius=8&requireEntityClass=true&q=chest"
```
Replace `<BOT_ID>` with your bot ID from Step 2.

**Expected Result:**
```json
{
  "Ok": true,
  "Center": [x, y, z],
  "Blocks": [
    {
      "Pos": [224, 3, 270],
      "Code": "game:chest-east",
      "Dist": 1.5,
      "EntityClass": "GenericTypedContainer",
      "Behaviors": [...]
    }
  ]
}
```

**Save:** Chest position as `[X, Y, Z]` (e.g., `224, 3, 270`).
**Interpretation:** Confirms nearby chest exists and has container interface. If no chest found, place one nearby and retry.

---

### Step 5: Give Bot Items
**Endpoint:** `POST /polis/command`
**Command:**
```bash
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"give","args":["game:stone-granite","5"]}'
```

**Expected Result:**
```json
{
  "Ok": true,
  "Message": "..."
}
```

**Interpretation:** Bot now has 5 granite stones. Needed for putinto test.

---

### Step 6: Verify Bot Inventory (Baseline)
**Endpoint:** `GET /polis/state`
**Command:**
```bash
curl "http://localhost:8585/polis/state?botId=<BOT_ID>"
```

**Expected Result:**
```json
{
  "Bot": {
    "Id": 12345,
    "RightHand": { "Code": "game:stone-granite", "Qty": 5 },
    "LeftHand": null,
    ...
  },
  "LastAction": {...},
  "LastActionId": 5
}
```

**Save:** `LastActionId` value (e.g., `5`) for comparison after next action.
**Interpretation:** Bot has items in right hand. This is our baseline for putinto test.

---

### Step 7: Test PUTINTO (Partial Transfer)
**Goal:** Transfer 3 of 5 items from bot hand into chest.

**Endpoint:** `POST /polis/command`
**Command:**
```bash
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{
    "cmd": "putinto",
    "args": ["<X>", "<Y>", "<Z>", "0", "3"]
  }'
```
Replace `<X>`, `<Y>`, `<Z>` with chest coordinates from Step 4.
Args: slot index `0` (right hand), quantity `3`.

**Expected Result:**
```json
{
  "Ok": true,
  "Message": "transferred 3 items from bot to container"
}
```

**Interpretation:** Action queued successfully. Bot will execute putinto action.

---

### Step 8: Verify Bot Inventory After PUTINTO
**Endpoint:** `GET /polis/state`
**Command:**
```bash
curl "http://localhost:8585/polis/state?botId=<BOT_ID>"
```

**Expected Result:**
```json
{
  "Bot": {
    "RightHand": { "Code": "game:stone-granite", "Qty": 2 },
    ...
  },
  "LastAction": {
    "Name": "putinto",
    "Ok": true,
    "Msg": "transferred 3 items..."
  },
  "LastActionId": 6
}
```

**Verification Checklist:**
- [ ] `LastActionId` increased from Step 6 (was 5, now 6+)
- [ ] `RightHand.Qty` is 2 (5 - 3)
- [ ] `LastAction.Ok` is true
- [ ] `LastAction.Name` is "putinto"

**Interpretation:** PUTINTO succeeded. Chest now has 3 granite, bot has 2 remaining.

---

### Step 9: Test TAKEFROM (Withdraw All)
**Goal:** Take all items from chest slot back into bot.

**Endpoint:** `POST /polis/command`
**Command:**
```bash
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{
    "cmd": "takefrom",
    "args": ["<X>", "<Y>", "<Z>", "0", "0"]
  }'
```
Replace coordinates. Args: container slot `0`, quantity `0` (meaning "all").

**Expected Result:**
```json
{
  "Ok": true,
  "Message": "transferred 3 items from container to bot"
}
```

---

### Step 10: Verify Bot Inventory After TAKEFROM
**Endpoint:** `GET /polis/state`
**Command:**
```bash
curl "http://localhost:8585/polis/state?botId=<BOT_ID>"
```

**Expected Result:**
```json
{
  "Bot": {
    "RightHand": { "Code": "game:stone-granite", "Qty": 5 },
    ...
  },
  "LastAction": {
    "Name": "takefrom",
    "Ok": true,
    "Msg": "transferred 3 items..."
  },
  "LastActionId": 7
}
```

**Verification Checklist:**
- [ ] `LastActionId` increased (was 6, now 7+)
- [ ] `RightHand.Qty` is 5 (2 + 3 from container)
- [ ] `LastAction.Ok` is true
- [ ] `LastAction.Name` is "takefrom"

**Interpretation:** TAKEFROM succeeded. Items returned to bot. Chest is now empty (or has less).

---

### Step 11: Test Range Failure
**Goal:** Verify "out of range" validation works.

**Step 11a:** Move bot far from chest
**Command:**
```bash
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{
    "cmd": "goto",
    "args": ["<CHEST_X>", "<CHEST_Y>", "<CHEST_Z + 10>"]
  }'
```
This moves bot 10 blocks above the chest.

**Step 11b:** Wait for goto to complete
**Command:**
```bash
curl "http://localhost:8585/polis/state?botId=<BOT_ID>" | jq '.LastAction'
```
Poll until `LastAction.Name` is "goto" and `Ok` is true.

**Step 11c:** Attempt putinto from out-of-range
**Command:**
```bash
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{
    "cmd": "putinto",
    "args": ["<X>", "<Y>", "<Z>", "0", "1"]
  }'
```

**Expected Result:**
```json
{
  "Ok": false,
  "Message": "out of range dist=10.XX range=4.50"
}
```

**Interpretation:** Range check works. Bot at 4.5+ blocks cannot access container.

---

### Step 12: Test Empty Slot Failure
**Goal:** Verify "empty slot" validation works.

**Step 12a:** Drop bot's items
**Command:**
```bash
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"drop"}'
```

**Step 12b:** Move bot back to chest
**Command:**
```bash
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{
    "cmd": "goto",
    "args": ["<CHEST_X>", "<CHEST_Y>", "<CHEST_Z>"]
  }'
```
Wait for goto to complete.

**Step 12c:** Attempt putinto with empty hand
**Command:**
```bash
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{
    "cmd": "putinto",
    "args": ["<X>", "<Y>", "<Z>", "0", "1"]
  }'
```

**Expected Result:**
```json
{
  "Ok": false,
  "Message": "right hand is empty"
}
```

**Interpretation:** Slot validation works. Cannot putinto from empty hand.

---

## Success Criteria

| Test | Criterion | Status |
|------|-----------|--------|
| Step 8 | PUTINTO reduces bot hand qty by 3 | ✓ |
| Step 10 | TAKEFROM increases bot hand qty by 3 | ✓ |
| Step 11 | Out-of-range returns failure message | ✓ |
| Step 12 | Empty slot returns failure message | ✓ |

All 4 criteria must pass.

---

## Known Limitations (Not Tested Yet)

- **Claims enforcement:** Requires claimed land + lack of permissions (world-dependent)
- **Full inventory:** Bot backpack must be full; requires manual filling
- **Container inventory verification:** Chest contents not exposed in harness; relies on bot inventory delta

---

## Debugging Tips

### Check Server Logs
```bash
tail -f ../vsdata/Logs/server-main.log | grep -i "polis"
```
Look for `[polis]` prefixed messages from action execution.

### Verify Action Execution
After each action command, immediately check state to see if `LastActionId` changed and `LastAction.Name` matches expected command.

### Timeout Issues
If harness seems unresponsive, restart the server and verify `/polis/status` returns `worldReady: true` before proceeding.

---

## References

- Test Harness Guide: `docs/TESTING_HARNESS.md`
- Target Endpoint: `docs/TESTING_HARNESS_TARGETS.md`
- Bot Inventory Model: `docs/research/phase-2/2026-01-06-bot-inventory-research.md`
- Container Transfer Research: `docs/research/phase-2/2026-01-14-container-transfer-correctness.md`
