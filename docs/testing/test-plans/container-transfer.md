# Test Execution: Container Transfer Commands

---

## THIS IS AN EXECUTION TASK

**You will RUN commands and REPORT results.**
**Do NOT edit files except the final results report.**

---

## STEP 0: LOAD CONFIGURATION

Source the local testing config to get machine-specific paths:

```bash
source .local/testing.env
```

If that fails, try the full path from the worktree root:
```bash
source "$PWD/.local/testing.env" 2>/dev/null || source /home/mf/Code/polis-builder/worktrees/claude-container-transfer/.local/testing.env
```

Verify it loaded:
```bash
echo "WORKTREE_BASE=$WORKTREE_BASE"
echo "HARNESS_URL=$HARNESS_URL"
```

**Expected:** Both variables print real paths/URLs.
**If empty or errors:** STOP. Report: "Missing .local/testing.env - cannot proceed"

---

## STEP 1: VERIFY WORKTREE LOCATION

```bash
cd "$WORKTREE_BASE/claude-container-transfer" && pwd && git branch --show-current
```

**Expected:**
- Path ends with: `worktrees/claude-container-transfer`
- Branch is: `agent/claude/container-transfer`

**If wrong:** STOP. Report actual location and branch.

---

## STEP 2: CHECK HARNESS

```bash
curl -s "$HARNESS_URL/polis/status"
```

**Expected:** JSON with `"worldReady": true`

| If you see... | Then... |
|---------------|---------|
| Connection refused | STOP. Report: "Harness unavailable - is VS running?" |
| `"worldReady": false` | Wait 5s, retry up to 3 times. If still false, STOP. |
| `"worldReady": true` | Continue to Step 3. |

---

## STEP 3: GET PLAYER UID

```bash
PLAYERS_RESP=$(curl -s "$HARNESS_URL/polis/players")
echo "$PLAYERS_RESP"
```

**Expected:** JSON with `players` array containing at least one entry.

Extract the UID:
```bash
PLAYER_UID=$(echo "$PLAYERS_RESP" | jq -r '.players[0].uid')
echo "PLAYER_UID=$PLAYER_UID"
```

**If no players:** STOP. Report: "No players online"
**If successful:** Record PLAYER_UID value for later steps.

---

## STEP 4: SPAWN BOT

Use the PLAYER_UID from Step 3:

```bash
SPAWN_RESP=$(curl -s -X POST "$HARNESS_URL/polis/command" \
  -H "Content-Type: application/json" \
  -d "{\"cmd\":\"spawn\",\"context\":{\"playerUid\":\"$PLAYER_UID\",\"spawnOffset\":[0,0,2]}}")
echo "$SPAWN_RESP"
```

**Expected:** `"Ok": true` with `Data.id` as a number.

Extract the bot ID:
```bash
BOT_ID=$(echo "$SPAWN_RESP" | jq -r '.Data.id')
echo "BOT_ID=$BOT_ID"
```

**If Ok is false:** STOP. Report the error message.
**If successful:** Record BOT_ID for later steps.

---

## STEP 5: SELECT BOT

```bash
curl -s -X POST "$HARNESS_URL/polis/command" \
  -H "Content-Type: application/json" \
  -d "{\"cmd\":\"select\",\"args\":[\"$BOT_ID\"]}"
```

**Expected:** `"Ok": true`

---

## STEP 6: FIND CONTAINER

```bash
TARGETS_RESP=$(curl -s "$HARNESS_URL/polis/targets?botId=$BOT_ID&radius=10&mode=blocks&codeContains=chest,barrel,vessel,trunk,crate")
echo "$TARGETS_RESP" | jq '.Blocks[:3]'
```

**Expected:** `Blocks` array with at least one entry that has `EntityClass` containing "Container", "Barrel", or "Vessel".

Extract container position:
```bash
CONTAINER_X=$(echo "$TARGETS_RESP" | jq -r '.Blocks[0].Pos[0]')
CONTAINER_Y=$(echo "$TARGETS_RESP" | jq -r '.Blocks[0].Pos[1]')
CONTAINER_Z=$(echo "$TARGETS_RESP" | jq -r '.Blocks[0].Pos[2]')
CONTAINER_DIST=$(echo "$TARGETS_RESP" | jq -r '.Blocks[0].Dist')
echo "Container at: $CONTAINER_X, $CONTAINER_Y, $CONTAINER_Z (dist: $CONTAINER_DIST)"
```

**If Blocks is empty or null:** STOP. Report: "No container found within 10 blocks"
**If successful:** Record container coordinates.

---

## STEP 7: MOVE BOT CLOSER (if CONTAINER_DIST > 4)

Check distance and move if needed:
```bash
if (( $(echo "$CONTAINER_DIST > 4" | bc -l) )); then
  echo "Moving bot closer..."
  curl -s -X POST "$HARNESS_URL/polis/command" \
    -H "Content-Type: application/json" \
    -d "{\"cmd\":\"goto\",\"args\":[\"$CONTAINER_X\",\"$CONTAINER_Y\",\"$CONTAINER_Z\"]}"
  sleep 3
else
  echo "Bot is close enough (dist=$CONTAINER_DIST)"
fi
```

---

## STEP 8: GIVE ITEM TO BOT

```bash
curl -s -X POST "$HARNESS_URL/polis/command" \
  -H "Content-Type: application/json" \
  -d '{"cmd":"give","args":["game:stone-granite","5"]}'
```

**Expected:** `"Ok": true`

Verify bot has item:
```bash
sleep 1
curl -s "$HARNESS_URL/polis/state?botId=$BOT_ID" | jq '.Bot.RightHand'
```

**Expected:** `{"Code": "game:stone-granite", "Qty": 5}`

---

## TEST CASE 1: PUTINTO

### Execute Command

```bash
echo "=== PUTINTO TEST ==="
PUTINTO_RESP=$(curl -s -X POST "$HARNESS_URL/polis/command" \
  -H "Content-Type: application/json" \
  -d "{\"cmd\":\"putinto\",\"args\":[\"$CONTAINER_X\",\"$CONTAINER_Y\",\"$CONTAINER_Z\",\"0\"]}")
echo "Response: $PUTINTO_RESP"
```

### Check State

```bash
sleep 1
STATE=$(curl -s "$HARNESS_URL/polis/state?botId=$BOT_ID")
echo "RightHand: $(echo "$STATE" | jq '.Bot.RightHand')"
echo "LastAction: $(echo "$STATE" | jq '.LastAction')"
```

### Evaluate Result

**PASS if ALL of these are true:**
- Response has `"Ok": true`
- `Bot.RightHand` is `null`
- `LastAction.Name` is `"putinto"`
- `LastAction.Ok` is `true`

**Record:** PUTINTO_RESULT = PASS or FAIL

---

## TEST CASE 2: TAKEFROM

### Execute Command

```bash
echo "=== TAKEFROM TEST ==="
TAKEFROM_RESP=$(curl -s -X POST "$HARNESS_URL/polis/command" \
  -H "Content-Type: application/json" \
  -d "{\"cmd\":\"takefrom\",\"args\":[\"$CONTAINER_X\",\"$CONTAINER_Y\",\"$CONTAINER_Z\",\"0\"]}")
echo "Response: $TAKEFROM_RESP"
```

### Check State

```bash
sleep 1
STATE=$(curl -s "$HARNESS_URL/polis/state?botId=$BOT_ID")
echo "RightHand: $(echo "$STATE" | jq '.Bot.RightHand')"
echo "LastAction: $(echo "$STATE" | jq '.LastAction')"
```

### Evaluate Result

**PASS if ALL of these are true:**
- Response has `"Ok": true`
- `Bot.RightHand.Code` is `"game:stone-granite"`
- `LastAction.Name` is `"takefrom"`
- `LastAction.Ok` is `true`

**Record:** TAKEFROM_RESULT = PASS or FAIL

---

## STEP 9: CLEANUP

```bash
curl -s -X POST "$HARNESS_URL/polis/command" \
  -H "Content-Type: application/json" \
  -d '{"cmd":"despawn"}'
```

---

## STEP 10: SAVE RESULTS REPORT

Create results directory:
```bash
mkdir -p "$WORKTREE_BASE/claude-container-transfer/docs/testing/results"
```

Get today's date:
```bash
TODAY=$(date +%Y-%m-%d)
REPORT_FILE="$WORKTREE_BASE/claude-container-transfer/docs/testing/test-results/${TODAY}-container-transfer.md"
echo "Saving report to: $REPORT_FILE"
```

Write the report using this template (fill in the recorded values):

```bash
cat > "$REPORT_FILE" << 'REPORT_EOF'
# Container Transfer Test Results

**Date:** YYYY-MM-DD (fill in)
**Branch:** agent/claude/container-transfer
**Tester:** [agent name]

## Environment
- Harness: [URL] - [READY/UNAVAILABLE]
- Player UID: [value]
- Bot ID: [value]
- Container: [code] at [X, Y, Z]

## Results

### PUTINTO (Bot → Container)
- **Result:** [PASS/FAIL]
- **Command Response:** [paste response]
- **State After:**
  - RightHand: [value]
  - LastAction: [value]

### TAKEFROM (Container → Bot)
- **Result:** [PASS/FAIL]
- **Command Response:** [paste response]
- **State After:**
  - RightHand: [value]
  - LastAction: [value]

## Summary
- PUTINTO: [PASS/FAIL]
- TAKEFROM: [PASS/FAIL]
- **Overall: X/2 passed**

## Issues Found
[List any errors, unexpected behavior, or blockers]
REPORT_EOF
```

Then edit the file to fill in actual values, or use echo/sed to substitute.

---

## ERROR REFERENCE

| Error | Meaning |
|-------|---------|
| `actor is not an agent` | **CRITICAL BUG** - vas parameter missing |
| `out of range dist=X range=Y` | Bot too far - move closer |
| `block is not a container` | Wrong coordinates |
| `container slot X is empty` | Nothing to take |
| `right hand is empty` | Nothing to put |
| `Connection refused` | VS not running |
| `worldReady: false` | World still loading |

---

## COMMANDS UNDER TEST

| Command | Args | Purpose |
|---------|------|---------|
| `putinto` | `X Y Z BOT_SLOT [QTY]` | Transfer from bot hand to container |
| `takefrom` | `X Y Z CONTAINER_SLOT [QTY]` | Transfer from container to bot hand |

Bot slots: 0 = right hand, 1 = left hand
Container slots: 0-based index
