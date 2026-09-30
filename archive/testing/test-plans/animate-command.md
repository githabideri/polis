# Test Execution: Animate Command

---

## THIS IS AN EXECUTION TASK

**You will RUN commands and REPORT results.**
**Do NOT edit files except the final results report.**

---

## Overview

The `animate` command triggers animations on a selected bot. It supports:
- One-shot animations (play once)
- Looping animations (play until stopped)
- Speed modifiers (0.1x - 10x)
- Stop specific or all animations

---

## STEP 0: ENVIRONMENT SETUP

```bash
# Set up environment
export HARNESS_URL="http://localhost:8585"

# Optional: Use poliscli for ergonomic commands
alias polis='./scripts/poliscli.py'
```

---

## STEP 1: VERIFY HARNESS

```bash
curl -s "$HARNESS_URL/polis/status" | jq '.server.worldReady'
```

**Expected:** `true`

| If you see... | Then... |
|---------------|---------|
| Connection refused | STOP. Report: "Harness unavailable - is VS running?" |
| `false` | Wait 5s, retry up to 3 times. If still false, STOP. |
| `true` | Continue to Step 2. |

---

## STEP 2: GET PLAYER UID

```bash
PLAYER_UID=$(curl -s "$HARNESS_URL/polis/players" | jq -r '.players[0].uid')
echo "PLAYER_UID=$PLAYER_UID"
```

**If no players:** STOP. Report: "No players online"

---

## STEP 3: SPAWN AND SELECT BOT

```bash
# Spawn bot near player
SPAWN_RESP=$(curl -s -X POST "$HARNESS_URL/polis/command" \
  -H "Content-Type: application/json" \
  -d "{\"cmd\":\"spawn\",\"context\":{\"playerUid\":\"$PLAYER_UID\",\"spawnOffset\":[2,0,0]}}")
echo "$SPAWN_RESP"

BOT_ID=$(echo "$SPAWN_RESP" | jq -r '.Data.id')
echo "BOT_ID=$BOT_ID"

# Select the bot
curl -s -X POST "$HARNESS_URL/polis/command" \
  -H "Content-Type: application/json" \
  -d "{\"cmd\":\"select\",\"args\":[\"$BOT_ID\"]}"
```

**Expected:** `"Ok": true` with valid bot ID

---

## TEST CASE 1: Basic One-Shot Animation

### Execute

```bash
echo "=== TEST 1: One-shot animation ==="
RESP=$(curl -s -X POST "$HARNESS_URL/polis/command" \
  -H "Content-Type: application/json" \
  -d '{"cmd":"animate","args":["hit"]}')
echo "Response: $RESP"
```

### Evaluate

**PASS if:**
- Response has `"Ok": true`
- Message contains `"Started animation 'hit'"` and `"(one-shot)"`

**Visual check:** Bot should play hit animation once.

**Record:** TEST1_RESULT = PASS or FAIL

---

## TEST CASE 2: Animation with Speed Modifier

### Execute

```bash
echo "=== TEST 2: Animation with speed ==="
RESP=$(curl -s -X POST "$HARNESS_URL/polis/command" \
  -H "Content-Type: application/json" \
  -d '{"cmd":"animate","args":["hit","2.0"]}')
echo "Response: $RESP"
```

### Evaluate

**PASS if:**
- Response has `"Ok": true`
- Message contains `"speed=2.00"`

**Visual check:** Bot should play hit animation noticeably faster.

**Record:** TEST2_RESULT = PASS or FAIL

---

## TEST CASE 3: Looping Animation

### Execute

```bash
echo "=== TEST 3: Looping animation ==="
RESP=$(curl -s -X POST "$HARNESS_URL/polis/command" \
  -H "Content-Type: application/json" \
  -d '{"cmd":"animate","args":["interact","1.0","loop"]}')
echo "Response: $RESP"
```

### Evaluate

**PASS if:**
- Response has `"Ok": true`
- Message contains `"(looping)"`

**Visual check:** Bot should continuously play interact animation.

**Record:** TEST3_RESULT = PASS or FAIL

---

## TEST CASE 4: Stop Specific Animation

### Execute

```bash
echo "=== TEST 4: Stop specific animation ==="
# First ensure we have a looping animation running (from TEST 3)
# If not, start one:
curl -s -X POST "$HARNESS_URL/polis/command" \
  -H "Content-Type: application/json" \
  -d '{"cmd":"animate","args":["interact","1.0","loop"]}'

sleep 2

# Stop specific animation
RESP=$(curl -s -X POST "$HARNESS_URL/polis/command" \
  -H "Content-Type: application/json" \
  -d '{"cmd":"animate","args":["stop","interact"]}')
echo "Response: $RESP"
```

### Evaluate

**PASS if:**
- Response has `"Ok": true`
- Message contains `"Stopped animation 'interact'"`

**Visual check:** Bot should stop the interact animation.

**Record:** TEST4_RESULT = PASS or FAIL

---

## TEST CASE 5: Stop All Animations

### Execute

```bash
echo "=== TEST 5: Stop all animations ==="
# Start multiple animations
curl -s -X POST "$HARNESS_URL/polis/command" \
  -H "Content-Type: application/json" \
  -d '{"cmd":"animate","args":["walk","1.0","loop"]}'
curl -s -X POST "$HARNESS_URL/polis/command" \
  -H "Content-Type: application/json" \
  -d '{"cmd":"animate","args":["interact","1.0","loop"]}'

sleep 2

# Stop all
RESP=$(curl -s -X POST "$HARNESS_URL/polis/command" \
  -H "Content-Type: application/json" \
  -d '{"cmd":"animate","args":["stop"]}')
echo "Response: $RESP"
```

### Evaluate

**PASS if:**
- Response has `"Ok": true`
- Message contains `"Stopped"` and a count (e.g., `"Stopped 2 animation(s)"`)

**Visual check:** Bot should return to idle pose.

**Record:** TEST5_RESULT = PASS or FAIL

---

## TEST CASE 6: Invalid Animation Code

### Execute

```bash
echo "=== TEST 6: Invalid animation code ==="
RESP=$(curl -s -X POST "$HARNESS_URL/polis/command" \
  -H "Content-Type: application/json" \
  -d '{"cmd":"animate","args":["nonexistent_animation_xyz"]}')
echo "Response: $RESP"
```

### Evaluate

**PASS if:**
- Response has `"Ok": false`
- Message contains `"Failed to start animation"` or `"not found"`

**Record:** TEST6_RESULT = PASS or FAIL

---

## TEST CASE 7: CLI Wrapper Test

### Execute

```bash
echo "=== TEST 7: CLI wrapper ==="

# Test basic animation
polis animate hit
sleep 1

# Test with speed
polis animate hit --speed 1.5
sleep 1

# Test with loop
polis animate interact --loop
sleep 2

# Stop
polis animate stop
```

### Evaluate

**PASS if:**
- All commands execute without Python errors
- Output shows success messages

**Record:** TEST7_RESULT = PASS or FAIL

---

## TEST CASE 8: Chat Command Test

This test requires in-game execution.

### Execute (In-Game)

```
/polis animate hit
/polis animate hit 1.5
/polis animate hit 1.0 loop
/polis animate stop
```

### Evaluate

**PASS if:**
- All commands work without errors
- Chat shows success messages
- Bot performs animations visually

**Record:** TEST8_RESULT = PASS or FAIL

---

## STEP 4: CLEANUP

```bash
curl -s -X POST "$HARNESS_URL/polis/command" \
  -H "Content-Type: application/json" \
  -d '{"cmd":"despawn"}'
```

---

## STEP 5: SAVE RESULTS REPORT

```bash
mkdir -p docs/testing/results
TODAY=$(date +%Y-%m-%d)
REPORT_FILE="docs/testing/test-results/${TODAY}-animate-command.md"
echo "Saving report to: $REPORT_FILE"
```

Use this template:

```markdown
# Animate Command Test Results

**Date:** YYYY-MM-DD
**Tester:** [name]
**Branch:** main (or branch name)

## Environment
- Harness: [URL] - [READY/UNAVAILABLE]
- Player UID: [value]
- Bot ID: [value]

## Results

| Test | Description | Result |
|------|-------------|--------|
| 1 | Basic one-shot animation | PASS/FAIL |
| 2 | Animation with speed modifier | PASS/FAIL |
| 3 | Looping animation | PASS/FAIL |
| 4 | Stop specific animation | PASS/FAIL |
| 5 | Stop all animations | PASS/FAIL |
| 6 | Invalid animation code | PASS/FAIL |
| 7 | CLI wrapper | PASS/FAIL |
| 8 | Chat command (in-game) | PASS/FAIL/SKIPPED |

## Summary
- **Passed:** X/8
- **Failed:** Y/8
- **Skipped:** Z/8

## Issues Found
[List any errors, unexpected behavior, or observations]

## Visual Observations
[Note any visual issues with animations]
```

---

## VISUAL VERIFICATION TIPS

### Timing Considerations

LLM token generation is slower than most animations. For reliable visual capture:

1. **Chain commands in single bash invocation** - Don't wait for LLM response between animate and screenshot
2. **Use slow speed (0.3x)** for one-shot animations to widen capture window
3. **Add brief sleep (0.3s)** after starting looping animations before screenshot

### Recommended Capture Pattern

```bash
# One-shot: slow speed, immediate capture
polis animate hit --speed 0.3 && polis screenshot --save

# Looping: start, pause, capture
polis animate walk --loop && sleep 0.3 && polis screenshot --save
```

### Verifying Animation State

The `stop` command reports how many animations were actually running:
- `"Stopped 1 animation(s)"` = animation was playing correctly
- `"Stopped 0 animation(s)"` = animation code doesn't exist or failed to start

### Player Positioning

For clear bot visibility:
1. Spawn bot with offset: `--spawnOffset [3,0,0]`
2. Teleport player 2 blocks from bot
3. Use `--face-bot` or `--yaw e/w/n/s` to face the bot

```bash
polis teleport 221 3 272 --face-bot
```

---

## ANIMATION CODES REFERENCE

Standard seraph humanoid animations (availability depends on entity shape):

| Category | Codes |
|----------|-------|
| Locomotion | `walk`, `run`, `idle`, `stand`, `sit`, `lie`, `crouch` |
| Combat | `hit`, `attack`, `hurt`, `die` |
| Interaction | `interact`, `dig`, `chop`, `use` |
| Movement | `fall`, `climb`, `jump`, `land` |

### Confirmed Working (polisbot entity)

| Code | Type | Verified |
|------|------|----------|
| `hit` | one-shot | ✅ Arm swing visible |
| `walk` | looping | ✅ Leg movement visible, stop=1 |

### Not Working (polisbot entity)

These return API success but no visual animation, `stop` returns 0:
- `interact`, `sit`, `run`

This indicates the animation codes don't exist in the polisbot shape file.

---

## ERROR REFERENCE

| Error | Meaning |
|-------|---------|
| `No bots available` | Spawn a bot first |
| `Bot entity not loaded` | Bot exists but entity not spawned |
| `Failed to start animation 'X'` | Animation code not in shape |
| `Invalid speed: X` | Speed arg not a valid number |

---

## COMMANDS UNDER TEST

| Command | Args | Purpose |
|---------|------|---------|
| `animate` | `<animCode> [speed] [loop]` | Play animation |
| `animate` | `stop [animCode]` | Stop animation(s) |
