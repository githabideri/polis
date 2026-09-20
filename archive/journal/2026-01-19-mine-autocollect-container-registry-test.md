# Mine Autocollect & Container Registry Test Report

**Date:** 2026-01-19
**Tester:** Claude (automated)
**Branch:** `main`

## Summary

Tested the mine autocollect fix and container registry system from commit `fa33cad`.

| Feature | Status | Notes |
|---------|--------|-------|
| Mine autocollect | **BUG** | Timing issue - items not collectible immediately |
| Container register | PASS | |
| Container list | PASS | |
| Container remove | PASS | |
| Container contents (name) | PASS | |
| Container contents (coords) | PASS | Via GET endpoint |
| takefrom with name | PASS | |
| putinto with name | PASS | |
| Container persistence | PASS | Survives game restart |
| Stale container detection | PASS | Shows valid=false, clear error message |

## Mine Autocollect Bug

### Observed Behavior
- Command returns success: `"Bot #553 mining... (autocollect)"`
- After mining completes, `LastAction.Msg` is just `"mined"` (not `"mined, collected X"`)
- Items remain on ground as EntityItem entities
- Manual `pickup` command works on dropped items

### Root Cause
`CollectDrops()` runs immediately after `BreakBlock()` in the same tick, but:
1. Item entities spawned by BreakBlock may not be in the spatial index yet for `GetEntitiesAround()`
2. VS items require ~1 second after spawn before `CanCollect()` returns true (see `PolisPickupItemAction.cs:63`)

### Fix Recommendation
Delay collection by scheduling it for 1-1.5 seconds after block break:
```csharp
// Option A: Schedule delayed callback
api.World.RegisterCallback((dt) => CollectDrops(world), 1200);

// Option B: Use action state machine to wait
// Add a "collecting" phase that waits before running CollectDrops
```

### Code Location
`PolisBuilderNpcSystem.cs:6476-6498` - BreakBlock followed immediately by CollectDrops

## Container Registry Tests

### Register & List
```bash
./scripts/poliscli.py container-register main-chest 224 3 270
# Ok: Registered container 'main-chest' at (224, 3, 270) type=chest

./scripts/poliscli.py container-list
# Shows: main-chest, loot-chest with valid=true
```

### Contents Query
```bash
# By name (works)
./scripts/poliscli.py container-contents main-chest
# Ok: 14/16 slots used

# By coordinates (CLI parsing issue - use GET endpoint)
curl "http://localhost:8585/polis/container-contents?x=224&y=3&z=270"
# Ok: returns same data
```

### takefrom/putinto with Names
```bash
# Move bot into range first
./scripts/poliscli.py goto 225 3 270 --wait

# Put items into named container
./scripts/poliscli.py putinto -c main-chest 1
# Ok: transferred 2 items from bot to container

# Take from named container
./scripts/poliscli.py takefrom -c main-chest 0
# Ok: transferred 7 items from container to bot
```

### Persistence
```bash
./scripts/vsctl.py stop && ./scripts/vsctl.py start --wait --window
./scripts/poliscli.py container-list
# Containers persist correctly after restart
```

### Stale Detection
```bash
# Break registered container
./scripts/poliscli.py setblock air 232 3 270

# List shows stale
./scripts/poliscli.py container-list
# loot-bin: valid=false, currentBlockCode="game:air"

# Using stale container gives clear error
./scripts/poliscli.py takefrom -c loot-bin 0
# Error: "Container 'loot-bin' at (232, 3, 270) has been moved or replaced.
#         Expected: game:chest-north, Found: game:air"
```

## Minor Issues

### CLI Parsing
1. `container-contents 224 3 270` interprets `224` as container name, not X coordinate
   - Workaround: Use GET endpoint directly or use registered name
2. `--desc` argument parsed as `--type` in container-register
   - Low priority cosmetic issue

### Silent Action Failures (Agentic Workflow Issue)
When bot is out of range for container operations:
- Command returns `Ok: true` ("action started")
- Action fails silently with "out of range"
- Only visible by checking `state` afterwards

**Impact:** Agents can't reliably chain tasks without polling state after each action.

**Recommendations:**
1. Pre-validate range before starting action (return Ok: false immediately)
2. Make `--wait` return actual action result, not just "started"
3. Consider auto-goto for container actions (composite task)

## Test Environment
- Game: Vintage Story via Flatpak
- World: test-lands
- Bot ID: 553
- Registered containers: main-chest (224,3,270), loot-chest (230,3,270)
