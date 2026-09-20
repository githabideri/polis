# Automated Test Strategy: Agentic Verification Loop (Revised)

**Date:** 2026-01-13
**Revised:** 2026-01-13 (v2 - practical architecture)
**Purpose:** Enable **automated iteration** on Phase 1.5 possession smoothing without manual gameplay
**Audience:** Claude agents, developers, QA automation

---

## Problem Statement

### The Real Issue
- Manual test cycle: **10 minutes per iteration**
- Feedback: "nothing changed" (subjective, no metrics)
- Result: Phase 1.5 development abandoned due to iteration friction

### What We Need
- Agent makes code change → builds → runs test → reports metrics
- Human reviews numbers, not feelings
- Multiple iterations while human does other things

### Architectural Constraint (Critical)
- `PolisClientPossessionHandler` runs **client-side** (IRenderer)
- `PolisTestHarness` runs **server-side** (HTTP API)
- **No network channel exists** to transport client diagnostics to server
- **Solution:** Focus on server-side measurable metrics + optional log parsing

---

## Revised Test Architecture (2-Tier + Manual)

```
┌─────────────────────────────────────────────────────────────┐
│ TIER 1: Server-Side Tests (HTTP, CI-Ready)                  │
│ ✓ Possession mount/unmount cycle                            │
│ ✓ Controlled movement via setcontrols                       │
│ ✓ Position sampling at 10 Hz                                │
│ ✓ Velocity consistency measurement                          │
│ ✓ Goto completion time                                      │
│                                                             │
│ Tooling: polis-prediction-test.py (new)                     │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ TIER 2: Client Log Analysis (Local Development Only)        │
│ ✓ Parse client-main.log for [polis] diagnostics             │
│ ✓ Extract FPS, divergence, prediction state                 │
│ ✓ No C# code changes required                               │
│                                                             │
│ Tooling: polis-parse-client-logs.py (optional)              │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ TIER 3: Manual Validation (Human Required)                  │
│ ✓ Does possession FEEL smooth?                              │
│ ✓ Camera tracking natural?                                  │
│ ✓ No visible jitter/popping?                                │
│                                                             │
│ Tooling: Checklist + human tester                           │
└─────────────────────────────────────────────────────────────┘
```

---

## Prerequisites: New HTTP Commands

### Required Commands

These commands **do not exist** in the current harness and must be added:

#### 1. `possess` - Mount player on selected bot
```
POST /polis/command {"cmd": "possess", "context": {"playerUid": "..."}}
```

**Implementation:** Find player by UID, get selected bot, call `player.Entity.TryMount(seat)`

#### 2. `unpossess` - Unmount player from bot
```
POST /polis/command {"cmd": "unpossess", "context": {"playerUid": "..."}}
```

**Implementation:** Call `player.Entity.TryUnmount()`

#### 3. `setcontrols` - Inject movement controls
```
POST /polis/command {"cmd": "setcontrols", "args": ["forward", "backward", "left", "right", "sprint", "jump"]}
```
Args are "true"/"false" strings.

**Implementation:** Set `seat.Controls.Forward = true` etc. directly on the possession seat.

**Why setcontrols?** Enables testing possession movement without simulating actual keyboard input.

---

## TIER 1: Server-Side Tests

### Test 1: Possession Mount/Unmount Cycle

**What we test:** Can we possess and unpossess via HTTP?

```python
def test_possession_cycle():
    # Setup
    spawn = client.post("/polis/command", {"cmd": "spawn"})
    bot_id = spawn["Data"]["id"]
    client.post("/polis/command", {"cmd": "select", "args": [str(bot_id)]})

    # Get player UID (first online player)
    players = client.get("/polis/players")
    player_uid = players["players"][0]["uid"]

    # Possess
    result = client.post("/polis/command", {
        "cmd": "possess",
        "context": {"playerUid": player_uid}
    })
    assert result["Ok"], f"Possess failed: {result}"

    time.sleep(1)

    # Verify mounted (check player state or bot state)
    state = client.get(f"/polis/state?botId={bot_id}")
    # Could add "isPossessed" field to state response

    # Unpossess
    result = client.post("/polis/command", {
        "cmd": "unpossess",
        "context": {"playerUid": player_uid}
    })
    assert result["Ok"], f"Unpossess failed: {result}"

    # Cleanup
    client.post("/polis/command", {"cmd": "despawn"})

    return {"PASS": True, "message": "Mount/unmount cycle successful"}
```

### Test 2: Movement via setcontrols

**What we test:** Does injecting controls cause NPC movement?

```python
def test_controlled_movement():
    # Setup + possess
    bot_id = spawn_and_possess()

    # Record start position
    state = client.get(f"/polis/state?botId={bot_id}")
    start_pos = state["Bot"]["Pos"]

    # Inject forward movement
    client.post("/polis/command", {
        "cmd": "setcontrols",
        "args": ["true", "false", "false", "false", "false", "false"]  # forward only
    })

    time.sleep(3)  # Move for 3 seconds

    # Stop movement
    client.post("/polis/command", {
        "cmd": "setcontrols",
        "args": ["false", "false", "false", "false", "false", "false"]
    })

    # Record end position
    state = client.get(f"/polis/state?botId={bot_id}")
    end_pos = state["Bot"]["Pos"]

    # Calculate distance moved
    dist = math.sqrt(
        (end_pos[0] - start_pos[0])**2 +
        (end_pos[2] - start_pos[2])**2
    )

    # Should have moved at least 1 block in 3 seconds
    passed = dist > 1.0

    # Cleanup
    unpossess_and_despawn()

    return {
        "PASS": passed,
        "distance_moved": dist,
        "expected": "> 1.0 blocks in 3s"
    }
```

### Test 3: Velocity Consistency (Core Smoothness Proxy)

**What we test:** Is movement velocity consistent over time? (Low stddev = smooth)

```python
def measure_velocity_consistency(duration=5.0):
    """
    Core smoothness measurement.

    Theory: If server sees consistent velocity, the NPC is moving smoothly.
    High velocity variance = jerky movement.
    """
    bot_id = spawn_and_possess()

    # Start forward movement
    client.post("/polis/command", {
        "cmd": "setcontrols",
        "args": ["true", "false", "false", "false", "false", "false"]
    })

    # Sample positions at 10 Hz
    positions = []
    start = time.time()
    while time.time() - start < duration:
        state = client.get(f"/polis/state?botId={bot_id}")
        pos = state["Bot"]["Pos"]
        positions.append((time.time(), pos[0], pos[1], pos[2]))
        time.sleep(0.1)

    # Stop movement
    client.post("/polis/command", {
        "cmd": "setcontrols",
        "args": ["false"] * 6
    })

    # Calculate velocities
    velocities = []
    for i in range(len(positions) - 1):
        t0, x0, y0, z0 = positions[i]
        t1, x1, y1, z1 = positions[i+1]
        dt = t1 - t0
        if dt > 0:
            dist = math.sqrt((x1-x0)**2 + (z1-z0)**2)
            vel = dist / dt
            velocities.append(vel)

    # Statistics
    avg_vel = sum(velocities) / len(velocities) if velocities else 0
    variance = sum((v - avg_vel)**2 for v in velocities) / len(velocities) if velocities else 0
    stddev = math.sqrt(variance)

    # Consistency: 1.0 = perfect, lower = more jittery
    consistency = 1.0 - min(1.0, stddev / avg_vel) if avg_vel > 0 else 0

    unpossess_and_despawn()

    return {
        "avg_velocity": avg_vel,
        "velocity_stddev": stddev,
        "consistency": consistency,
        "samples": len(positions),
        "PASS": consistency > 0.7  # Threshold TBD
    }
```

### Test 4: Stop Behavior

**What we test:** Does NPC stop cleanly when controls released?

```python
def test_stop_behavior():
    bot_id = spawn_and_possess()

    # Move for 2 seconds
    client.post("/polis/command", {"cmd": "setcontrols", "args": ["true"] + ["false"]*5})
    time.sleep(2)

    # Stop
    client.post("/polis/command", {"cmd": "setcontrols", "args": ["false"]*6})

    # Record position
    state = client.get(f"/polis/state?botId={bot_id}")
    stop_pos = state["Bot"]["Pos"]

    # Wait and verify no drift
    time.sleep(2)
    state = client.get(f"/polis/state?botId={bot_id}")
    final_pos = state["Bot"]["Pos"]

    drift = math.sqrt(
        (final_pos[0] - stop_pos[0])**2 +
        (final_pos[2] - stop_pos[2])**2
    )

    unpossess_and_despawn()

    return {
        "drift_distance": drift,
        "PASS": drift < 0.1,  # Should not drift more than 0.1 blocks
        "message": "NPC stopped cleanly" if drift < 0.1 else f"NPC drifted {drift:.3f} blocks"
    }
```

---

## TIER 2: Client Log Analysis (Optional)

The client already logs diagnostics to `client-main.log`:

```
[polis] OnRenderFrame FPS: 25 frames in last 1.03s
[polis] Divergence: 0.032 blocks
[polis] PredictNpcMovement: DISABLED (no improvement observed)
```

### Log Parser Script

```python
#!/usr/bin/env python3
"""
Parse polis diagnostics from client-main.log.
For local development only - requires file system access.
"""
import re
from pathlib import Path

def parse_client_logs(log_path, since_line=0):
    """Extract [polis] diagnostics from client log."""
    metrics = {
        "fps_samples": [],
        "divergences": [],
        "prediction_enabled": None,
        "lines_parsed": 0
    }

    with open(log_path) as f:
        for i, line in enumerate(f):
            if i < since_line:
                continue
            metrics["lines_parsed"] += 1

            # FPS
            match = re.search(r"\[polis\] OnRenderFrame FPS: (\d+)", line)
            if match:
                metrics["fps_samples"].append(int(match.group(1)))

            # Divergence
            match = re.search(r"\[polis\] Divergence: ([\d.]+)", line)
            if match:
                metrics["divergences"].append(float(match.group(1)))

            # Prediction state
            if "[polis] PredictNpcMovement: DISABLED" in line:
                metrics["prediction_enabled"] = False
            elif "[polis] PredictNpcMovement: Enabled" in line:
                metrics["prediction_enabled"] = True

    # Calculate averages
    if metrics["fps_samples"]:
        metrics["avg_fps"] = sum(metrics["fps_samples"]) / len(metrics["fps_samples"])
    if metrics["divergences"]:
        metrics["avg_divergence"] = sum(metrics["divergences"]) / len(metrics["divergences"])
        metrics["max_divergence"] = max(metrics["divergences"])

    return metrics

if __name__ == "__main__":
    import sys
    log_path = sys.argv[1] if len(sys.argv) > 1 else "../vsdata/Logs/client-main.log"
    metrics = parse_client_logs(log_path)
    print(f"FPS: {metrics.get('avg_fps', 'N/A'):.1f}")
    print(f"Divergence: avg={metrics.get('avg_divergence', 'N/A'):.4f}, max={metrics.get('max_divergence', 'N/A'):.4f}")
    print(f"Prediction enabled: {metrics.get('prediction_enabled', 'Unknown')}")
```

---

## TIER 3: Manual Validation Checklist

Some things can only be judged by humans:

```markdown
## Possession Smoothness Checklist

### Movement Feel
- [ ] Walk forward for 10s - movement consistent? No stutters?
- [ ] Walk backward - same quality as forward?
- [ ] Strafe left/right - smooth lateral movement?
- [ ] Diagonal movement - natural feel?

### Speed Variants
- [ ] Sprint - noticeable speed increase?
- [ ] Sneak - slower movement, no jitter?

### Transitions
- [ ] Start moving - responsive? No delay?
- [ ] Stop moving - immediate? No drift?
- [ ] Direction change - smooth transition?

### Camera
- [ ] Rotate while stationary - smooth?
- [ ] Rotate while moving - no judder?
- [ ] Look up/down - natural pitch?

### Edge Cases
- [ ] Jump while moving - animation smooth?
- [ ] Walk into wall - no spasms?
- [ ] Uneven terrain - handles gracefully?

### Overall
- [ ] Would you use this for actual gameplay?
- [ ] Any nausea or discomfort? (important for first-person)
```

---

## Implementation Roadmap

### Phase 1: HTTP Commands (This Branch)

**Files to modify:** `PolisBuilderNpcSystem.cs`

- [ ] Add `possess` command
- [ ] Add `unpossess` command
- [ ] Add `setcontrols` command
- [ ] Test via curl

### Phase 2: Test Script

**New file:** `scripts/polis-prediction-test.py`

- [ ] Import HarnessClient from polis-http-smoke.py
- [ ] Implement test_possession_cycle()
- [ ] Implement test_controlled_movement()
- [ ] Implement measure_velocity_consistency()
- [ ] Implement test_stop_behavior()
- [ ] Add comparison mode (before/after)

### Phase 3: Agent Iteration Loop

With infrastructure in place:
1. Re-enable prediction in `PolisClientPossessionHandler.cs`
2. Run baseline test (prediction OFF)
3. Run test with prediction ON
4. Compare metrics
5. If improved: tune parameters, repeat
6. If no improvement: try different approach

---

## A/B Test Workflow

```bash
# 1. Baseline (current code, prediction disabled)
python3 scripts/polis-prediction-test.py --label baseline > results/baseline.json

# 2. Enable prediction, rebuild
# (modify PolisClientPossessionHandler.cs line 87-94)
dotnet build -c Release && cp -r bin/Release/Mods/polis-builder-npc ../vsdata/Mods/

# 3. Test with prediction
python3 scripts/polis-prediction-test.py --label prediction-v1 > results/prediction-v1.json

# 4. Compare
python3 scripts/polis-compare-results.py results/baseline.json results/prediction-v1.json
```

**Expected Output:**
```
COMPARISON: baseline vs prediction-v1
=====================================

Velocity Consistency:
  baseline:      0.72
  prediction-v1: 0.85  (+18.1% improvement)

Stop Drift:
  baseline:      0.08 blocks
  prediction-v1: 0.05 blocks  (-37.5% improvement)

VERDICT: prediction-v1 shows measurable improvement
         Recommend manual testing to verify feel
```

---

## Success Criteria

### Minimum Viable
- [ ] Can possess/unpossess via HTTP
- [ ] Can inject controls via HTTP
- [ ] Can measure velocity consistency
- [ ] Numbers change when code changes

### Full Success
- [ ] Automated tests pass
- [ ] Metrics show measurable improvement with prediction
- [ ] Manual testing confirms improved feel
- [ ] Phase 1.5 can be re-enabled with confidence

---

## Key Insight

**We're not testing "smoothness" directly.** We're testing **objective proxies**:

| Proxy Metric | What It Indicates |
|--------------|-------------------|
| Velocity consistency | Low = jerky, High = smooth |
| Stop drift | Movement physics working correctly |
| Mount/unmount success | Basic functionality works |

If these metrics improve, the feel *should* improve. If they don't change, something else is the bottleneck (likely server tick rate).

---

## Files Referenced

| File | Purpose |
|------|---------|
| `PolisBuilderNpcSystem.cs` | Add new HTTP commands |
| `PolisClientPossessionHandler.cs` | Prediction code to test |
| `PolisPossessableSeat.cs` | Seat.Controls access |
| `scripts/polis-http-smoke.py` | Existing HarnessClient |
| `scripts/polis-prediction-test.py` | New test script (to create) |
| `../vsdata/Logs/client-main.log` | Client diagnostics |
