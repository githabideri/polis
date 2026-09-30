# Test Execution: Mine and Harvest Block Actions

---

## THIS IS AN EXECUTION TASK

**You will RUN commands and REPORT results.**
**Do NOT edit files except the final results report.**

**Required Reading:** `docs/TESTING_HARNESS_TARGETS.md` for filter parameters.

---

## Quick Reference

```bash
HARNESS_URL="http://localhost:8585"
```

**Key Endpoints:**
- `GET /polis/status` → Check if world ready
- `GET /polis/players` → Get player UIDs
- `GET /polis/targets?botId=X&radius=Y&mode=blocks&codeContains=Z` → Find blocks
- `POST /polis/command` → Execute commands

**Results Directory:** `docs/testing/test-results/`

---

## PRE-FLIGHT CHECKLIST

Before running tests, verify the environment:

### 1. Check harness is running and list available commands

```bash
curl -s "http://localhost:8585/polis"
```

**Expected response includes:**
```json
{
  "message": "Polis Test Harness",
  "endpoints": ["/polis/status", "/polis/command", ...]
}
```

### 2. Verify required commands exist

Send an invalid command to see the available list:
```bash
curl -s -X POST "http://localhost:8585/polis/command" \
  -H "Content-Type: application/json" \
  -d '{"cmd":"_list_"}'
```

**Expected response shows available commands:**
```json
{
  "Ok": false,
  "Message": "Unknown command: _list_. Available: spawn, select, ..., mine, harvest"
}
```

**CHECKPOINT:** Verify `mine` and `harvest` appear in the Available list.
If `harvest` is missing, the mod may need to be updated and game restarted.

---

## STEP 1: CHECK HARNESS

```bash
curl -s "http://localhost:8585/polis/status"
```

**Expected response (verify these fields):**
```json
{
  "ok": true,
  "server": {
    "runPhase": "RunGame",
    "worldReady": true
  }
}
```

| If `worldReady` is... | Then... |
|-----------------------|---------|
| `true` | Continue to Step 2 |
| `false` | Wait 5 seconds, retry up to 3 times |
| Connection refused | STOP - game not running |

---

## STEP 2: GET PLAYER UID

```bash
curl -s "http://localhost:8585/polis/players"
```

**Expected response:**
```json
{
  "players": [
    {
      "name": "PlayerName",
      "uid": "xYz+AbCdEfGhIjKlMnOpQrSt",
      "pos": [100.5, 65.0, 200.5]
    }
  ]
}
```

**Extract and store the UID:**
```bash
PLAYER_UID="xYz+AbCdEfGhIjKlMnOpQrSt"
```
Replace with the actual `uid` value from YOUR response.

### URL Encoding for Player UID

**IMPORTANT:** When using playerUid in **query parameters** (GET requests), you must URL-encode special characters:
- `+` becomes `%2B`
- `=` becomes `%3D`

**Example:** If uid is `xYz+AbCdEfGhIjKlMnOpQrSt`
- In JSON body (POST): Use as-is → `"playerUid":"xYz+AbCdEfGhIjKlMnOpQrSt"`
- In URL query (GET): Encode → `?playerUid=xYz%2BAbCdEfGhIjKlMnOpQrSt`

For this test, we use POST requests with JSON body, so **no encoding needed**.

**CHECKPOINT:** You must have a valid PLAYER_UID before continuing.

---

## STEP 3: SPAWN BOT

```bash
curl -s -X POST "http://localhost:8585/polis/command" \
  -H "Content-Type: application/json" \
  -d '{"cmd":"spawn","context":{"playerUid":"YOUR_PLAYER_UID_HERE","spawnOffset":[0,0,2]}}'
```

**Expected response:**
```json
{
  "Ok": true,
  "Message": "Spawned polis:polisbot #393 at (223.5, 3, 267.5)",
  "Data": {
    "id": 393,
    "code": "polis:polisbot",
    "pos": [223.5, 3, 267.5]
  }
}
```

**Extract and store the bot ID:**
```bash
BOT_ID=393
```
Replace `393` with the actual `Data.id` value from your response.

**CHECKPOINT:** If `Ok` is `false`, STOP and report the error message.

---

## STEP 4: SELECT BOT

```bash
curl -s -X POST "http://localhost:8585/polis/command" \
  -H "Content-Type: application/json" \
  -d '{"cmd":"select","args":["393"]}'
```

Replace `393` with your actual BOT_ID.

**Expected:** `"Ok": true`

---

## TEST CASE 1: MINE SOIL (Bare-Handed)

This tests mining a soft block without tools.

### Step 1.1: Find a SOIL block

Search specifically for soil:

```bash
curl -s "http://localhost:8585/polis/targets?botId=393&radius=6&mode=blocks&codeContains=soil"
```

Replace `393` with your BOT_ID.

**Expected response:**
```json
{
  "Ok": true,
  "Center": [223.5, 3.0, 267.5],
  "Radius": 6,
  "Blocks": [
    {
      "Pos": [223, 2, 265],
      "Code": "game:soil-medium-normal",
      "Dist": 2.5
    }
  ]
}
```

**Extract coordinates from the FIRST block in the `Blocks` array:**
- `SOIL_X` = first number in `Pos` (e.g., `223`)
- `SOIL_Y` = second number in `Pos` (e.g., `2`)
- `SOIL_Z` = third number in `Pos` (e.g., `265`)
- `SOIL_CODE` = the `Code` value (e.g., `game:soil-medium-normal`)

**CHECKPOINT:** If `Blocks` is empty `[]`, try increasing radius to 10:
```bash
curl -s "http://localhost:8585/polis/targets?botId=393&radius=10&mode=blocks&codeContains=soil"
```

### Step 1.2: Record initial state

```bash
curl -s "http://localhost:8585/polis/state?botId=393"
```

**Note the `LastActionId` value** (e.g., `0` or `5`). Store as `INITIAL_ID`.

### Step 1.3: Execute mine command

**IMPORTANT:** Include `playerUid` in context!

```bash
curl -s -X POST "http://localhost:8585/polis/command" \
  -H "Content-Type: application/json" \
  -d '{"cmd":"mine","args":["223","2","265"],"context":{"playerUid":"YOUR_PLAYER_UID_HERE"}}'
```

Replace coordinates with your SOIL_X, SOIL_Y, SOIL_Z values.

**Expected response:**
```json
{
  "Ok": true,
  "Message": "Bot #393 mining game:soil-medium-normal at (223, 2, 265), est 2.0s",
  "Data": {
    "blockCode": "game:soil-medium-normal",
    "pos": [223, 2, 265],
    "estimatedSeconds": 2.0
  }
}
```

### Step 1.4: Check state IMMEDIATELY (within 1 second)

```bash
curl -s "http://localhost:8585/polis/state?botId=393"
```

**Look for `LastAction` field:**
```json
{
  "LastAction": {
    "Name": "mine",
    "Ok": true,
    "Msg": "mining started"
  },
  "LastActionId": 1
}
```

**VERIFY:**
- `LastAction.Msg` should be `"mining started"`
- `LastActionId` should be greater than `INITIAL_ID`

### Step 1.5: Wait for mining to complete

Soil takes ~2 seconds. Wait 3 seconds to be safe:
```bash
sleep 3
```

### Step 1.6: Check final state

```bash
curl -s "http://localhost:8585/polis/state?botId=393"
```

**Expected `LastAction`:**
```json
{
  "LastAction": {
    "Name": "mine",
    "Ok": true,
    "Msg": "mined"
  },
  "LastActionId": 2
}
```

**VERIFY:**
- `LastAction.Msg` should be `"mined"` (NOT `"mining started"`)
- `LastActionId` should have incremented again

### Evaluate TEST 1 Result

**PASS if ALL are true:**
- [ ] Mine command returned `Ok: true`
- [ ] State during mining showed `Msg: "mining started"`
- [ ] State after mining showed `Msg: "mined"`
- [ ] `LastActionId` incremented at least twice

**Record:** MINE_SOIL_RESULT = PASS or FAIL

---

## TEST CASE 2: MINE ROCK (With Tool)

This tests mining a hard block that requires a tool.

### Step 2.1: Give bot a pickaxe

```bash
curl -s -X POST "http://localhost:8585/polis/command" \
  -H "Content-Type: application/json" \
  -d '{"cmd":"give","args":["game:pickaxe-copper","1"]}'
```

**Expected:** `"Ok": true`

Verify bot has pickaxe:
```bash
curl -s "http://localhost:8585/polis/state?botId=393"
```

**Look for `Bot.RightHand`:**
```json
{
  "Bot": {
    "RightHand": {
      "Code": "game:pickaxe-copper",
      "Qty": 1
    }
  }
}
```

### Step 2.2: Find a ROCK or STONE block

Search for rock or stone (NOT soil):

```bash
curl -s "http://localhost:8585/polis/targets?botId=393&radius=10&mode=blocks&codeContains=rock-,stone-"
```

**Expected response (example):**
```json
{
  "Ok": true,
  "Blocks": [
    {
      "Pos": [220, 1, 268],
      "Code": "game:rock-granite",
      "Dist": 4.2
    }
  ]
}
```

**CHECKPOINT:** If `Blocks` is empty, try these alternatives in order:

```bash
# 1. Try just "rock" with larger radius
curl -s "http://localhost:8585/polis/targets?botId=393&radius=15&mode=blocks&codeContains=rock"

# 2. Try specific rock types (granite, andesite, basalt, bauxite)
curl -s "http://localhost:8585/polis/targets?botId=393&radius=15&mode=blocks&codeContains=granite,andesite,basalt,bauxite"

# 3. Try ore blocks (require higher tier tools)
curl -s "http://localhost:8585/polis/targets?botId=393&radius=15&mode=blocks&codeContains=ore-"

# 4. Use broad text search
curl -s "http://localhost:8585/polis/targets?botId=393&radius=20&mode=blocks&q=stone"
```

**If still no results:** The area may not have exposed rock. Move to a different location or skip TEST 2.

**Extract coordinates:**
- `ROCK_X`, `ROCK_Y`, `ROCK_Z` from `Pos`
- `ROCK_CODE` from `Code`

### Step 2.3: Move bot closer if needed

If `Dist` is greater than 4.5:

```bash
curl -s -X POST "http://localhost:8585/polis/command" \
  -H "Content-Type: application/json" \
  -d '{"cmd":"goto","args":["220","1","268"]}'
```

Wait for movement:
```bash
sleep 3
```

### Step 2.4: Mine the rock

```bash
curl -s -X POST "http://localhost:8585/polis/command" \
  -H "Content-Type: application/json" \
  -d '{"cmd":"mine","args":["220","1","268"],"context":{"playerUid":"YOUR_PLAYER_UID_HERE"}}'
```

**Expected:** `"Ok": true` with estimated time (rock takes longer, ~5-10s)

### Step 2.5: Wait and check completion

Rock mining takes longer. Wait 10 seconds:
```bash
sleep 10
```

Check state:
```bash
curl -s "http://localhost:8585/polis/state?botId=393"
```

**Expected:**
```json
{
  "LastAction": {
    "Name": "mine",
    "Ok": true,
    "Msg": "mined"
  }
}
```

### Evaluate TEST 2 Result

**PASS if ALL are true:**
- [ ] Bot received pickaxe
- [ ] Found rock/stone block
- [ ] Mine command returned `Ok: true`
- [ ] Final state showed `Msg: "mined"`

**Record:** MINE_ROCK_RESULT = PASS or FAIL

---

## TEST CASE 3: HARVEST (Berry Bush)

This tests harvesting a harvestable block.

### Step 3.1: Find a harvestable block

Search for berry bushes (look for "ripe" in the code):

```bash
curl -s "http://localhost:8585/polis/targets?botId=393&radius=20&mode=blocks&codeContains=berrybush"
```

**Expected response (look for "ripe" in Code):**
```json
{
  "Ok": true,
  "Blocks": [
    {
      "Pos": [230, 4, 275],
      "Code": "game:bigberrybush-redcurrant-ripe",
      "Dist": 8.5,
      "Behaviors": ["BlockBehaviorHarvestable"]
    }
  ]
}
```

**IMPORTANT:** The block code must contain `ripe` for harvesting to succeed.

**CHECKPOINT:** If no ripe bushes found:
```bash
# Try searching for any harvestable
curl -s "http://localhost:8585/polis/targets?botId=393&radius=30&mode=blocks&q=ripe"

# Or look for beehives
curl -s "http://localhost:8585/polis/targets?botId=393&radius=20&mode=blocks&codeContains=wildbeehive"
```

**If still nothing:** Skip this test and note "No harvestable blocks in range"

### Step 3.2: Move closer if needed

If `Dist` > 4:
```bash
curl -s -X POST "http://localhost:8585/polis/command" \
  -H "Content-Type: application/json" \
  -d '{"cmd":"goto","args":["230","4","275"]}'
```

Wait:
```bash
sleep 4
```

### Step 3.3: Record initial state

```bash
curl -s "http://localhost:8585/polis/state?botId=393"
```

Note `LastActionId` as `HARVEST_INITIAL_ID`.

### Step 3.4: Execute harvest command

```bash
curl -s -X POST "http://localhost:8585/polis/command" \
  -H "Content-Type: application/json" \
  -d '{"cmd":"harvest","args":["230","4","275","true"],"context":{"playerUid":"YOUR_PLAYER_UID_HERE"}}'
```

The `"true"` argument enables auto-collect of drops.

**Expected:** `"Ok": true`

### Step 3.5: Check state during harvest (immediately)

```bash
curl -s "http://localhost:8585/polis/state?botId=393"
```

**Expected:**
```json
{
  "LastAction": {
    "Name": "harvest",
    "Ok": true,
    "Msg": "harvest started"
  }
}
```

### Step 3.6: Wait and check completion

Harvesting takes ~1-2 seconds:
```bash
sleep 2
```

```bash
curl -s "http://localhost:8585/polis/state?botId=393"
```

**Expected:**
```json
{
  "LastAction": {
    "Name": "harvest",
    "Ok": true,
    "Msg": "harvested"
  }
}
```

### Evaluate TEST 3 Result

**PASS if ALL are true:**
- [ ] Found ripe harvestable block
- [ ] Harvest command returned `Ok: true`
- [ ] State showed `Msg: "harvest started"` then `Msg: "harvested"`

**Record:** HARVEST_RESULT = PASS or FAIL (or SKIPPED if no harvestable blocks)

---

## CLEANUP

```bash
curl -s -X POST "http://localhost:8585/polis/command" \
  -H "Content-Type: application/json" \
  -d '{"cmd":"despawn"}'
```

---

## WRITE RESULTS REPORT

Create a summary with your results:

```markdown
# Mine/Harvest Test Results

**Date:** [TODAY'S DATE]
**Tester:** [YOUR NAME]

## Environment
- Harness URL: http://localhost:8585
- Player UID: [VALUE]
- Bot ID: [VALUE]

## Results

### TEST 1: Mine Soil (Bare-Handed)
- Target: [SOIL_CODE] at [X, Y, Z]
- State Progression: "mining started" → "mined"
- **Result: [PASS/FAIL]**

### TEST 2: Mine Rock (With Pickaxe)
- Target: [ROCK_CODE] at [X, Y, Z]
- Tool: game:pickaxe-copper
- State Progression: "mining started" → "mined"
- **Result: [PASS/FAIL]**

### TEST 3: Harvest Berry Bush
- Target: [BUSH_CODE] at [X, Y, Z]
- State Progression: "harvest started" → "harvested"
- **Result: [PASS/FAIL/SKIPPED]**

## Summary
- Mine Soil: [PASS/FAIL]
- Mine Rock: [PASS/FAIL]
- Harvest: [PASS/FAIL/SKIPPED]
- **Overall: X/3 passed**

## Issues Found
[List any errors or unexpected behavior]
```

---

## ERROR REFERENCE

| Error Message | Meaning | Fix |
|---------------|---------|-----|
| `Tool tier insufficient: X < Y` | Tool too weak for block | Use better pickaxe |
| `Tool required: block needs tier X` | Can't mine bare-handed | Give bot a tool |
| `No block at target position` | Wrong coordinates or block gone | Re-scan for targets |
| `out of range dist=X > Y` | Bot too far | Use `goto` to move closer |
| `No line of sight` | Bot can't see the block | Move bot to different position, try `goto` to a nearby clear spot |
| `block is not harvestable` | Not a harvestable type | Find berry bush or beehive |
| `block is not ripe` | Harvestable but not ready | Find one with "ripe" in code |
| `Bot owner is offline` | Player context missing/wrong | Check playerUid |
| `Unknown command: X` | Command not available | Check available commands list, may need mod update |

### Handling "No line of sight" Errors

If mining fails with LOS error:
1. The bot may be inside a block or at a bad angle
2. Try moving the bot to a different position near the target:
   ```bash
   # Move bot 1-2 blocks away from target, then retry
   curl -s -X POST "http://localhost:8585/polis/command" \
     -H "Content-Type: application/json" \
     -d '{"cmd":"goto","args":["TARGET_X+1","TARGET_Y","TARGET_Z"]}'
   ```
3. Wait 2-3 seconds for movement, then retry the mine command

---

## TOOL TIER REFERENCE

| Block Type | Required Tier | Example |
|------------|---------------|---------|
| Soil, Gravel, Sand | 0 | Bare hands OK |
| Loose stones | 0 | Bare hands OK |
| Rock, Stone | 1+ | Needs pickaxe |
| Ore | 2+ | Needs bronze+ pickaxe |

| Tool | Tier |
|------|------|
| Bare hands | 0 |
| Flint | 1 |
| Copper | 2 |
| Bronze | 3 |
| Iron | 4 |
