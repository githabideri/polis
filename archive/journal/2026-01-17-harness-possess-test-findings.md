# Harness Possess/Unpossess/Setcontrols Test Findings

**Date:** 2026-01-17
**Tested by:** Claude (agent)
**Related:** Phase 1.5 (client smoothing), HTTP harness commands

## Summary

First test of newly added HTTP harness commands: `possess`, `unpossess`, `setcontrols`.

## Test Results

### Commands Tested

| Command | Result | Response |
|---------|--------|----------|
| `possess` | ✅ Pass | "Player player now possessing bot 365" |
| `setcontrols` (forward=true) | ✅ Pass | Controls set correctly |
| `setcontrols` (all false) | ✅ Pass | Movement stopped |
| `unpossess` | ✅ Pass | "Exited possession mode" |

### Movement Observations

**Initial position:** `(219.7, 3.0, 268.0)`
**After forward movement:** `(197.8, 3.0, 387.7)`
**Distance traveled:** ~122 blocks (diagonal)

**Timing issue:** No precise measurement of how long the bot moved forward. The agent only tracked command send/receive times, not actual in-game movement duration.

**Return trip (via `goto`):** Bot successfully pathfound back to origin. Actual duration unknown - agent polled after 3 seconds and bot had already arrived, but user reports it took "way longer than 3 seconds."

## Measurement Gaps Identified

### Problem 1: No Timestamps on Movement

Current harness doesn't expose:
- When movement actually started (possession mount complete)
- When movement stopped (controls zeroed)
- Current velocity or movement state

### Problem 2: Polling vs Event-Driven

The test used:
```bash
sleep 3 && curl .../polis/bots
```

This only tells us "position at poll time", not:
- When the bot arrived
- Total travel time
- Average speed

### Problem 3: LastAction Doesn't Track Possession

The `LastAction` field in bot state tracks action results (mine, harvest, etc.), but `setcontrols` doesn't record to it since it's continuous input, not a discrete action.

## Recommendations for Phase 1.5 Testing

### 1. Add Movement Timestamps to State

Extend `/polis/state` response:
```json
{
  "bot": {
    "pos": [...],
    "velocity": [...],
    "isMoving": true,
    "lastMoveStartMs": 1705456789000,
    "lastMoveEndMs": null
  }
}
```

### 2. Add Possession State to Harness

Extend `/polis/state` or add `/polis/possession`:
```json
{
  "isPossessed": true,
  "possessedBy": "player-uid",
  "possessionStartMs": 1705456789000,
  "controls": {
    "forward": true,
    "backward": false,
    ...
  }
}
```

### 3. Create Timed Test Script

The existing `scripts/polis-prediction-test.py` was designed for Phase 1.5 validation. Consider extending it or creating a simpler timing harness:

```python
import time
import requests

start = time.time()
requests.post('.../polis/command', json={"cmd": "setcontrols", "args": ["true",...], ...})

# Poll until position changes by threshold
while True:
    pos = requests.get('.../polis/state').json()['Bot']['Pos']
    if distance(pos, target) < 1.0:
        break
    time.sleep(0.1)

elapsed = time.time() - start
print(f"Travel time: {elapsed:.2f}s")
```

### 4. Record Server Timestamps

Have the mod log timestamps to server log or return them in responses:
```
[polis] 02:45:12.345 Possess started: player=X bot=365
[polis] 02:45:12.890 Controls set: F=true
[polis] 02:45:18.123 Controls set: F=false
[polis] 02:45:18.456 Unpossess complete
```

Then correlate with position snapshots.

## Action Items

- [ ] Add possession state to `/polis/state` response
- [ ] Add movement velocity/timing fields
- [ ] Extend `polis-prediction-test.py` for automated timing
- [ ] Document expected speeds for comparison (player walk, sprint, etc.)

## Related Files

- `PolisBuilderNpcSystem.cs` - ExecutePossessCommand, ExecuteSetControlsCommand
- `scripts/polis-prediction-test.py` - Phase 1.5 test script (extracted from old branch)
- `docs/research/misc/2026-01-13-automated-test-strategy.md` - Testing architecture
