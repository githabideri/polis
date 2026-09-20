# Mine Autocollect Fix + Container Registry

**Date:** 2026-01-19
**Branch:** `agent/claude/mine-autocollect-container-registry`

## Summary

Two features implemented:
1. **Mine Autocollect Fix** - The `--autocollect` flag for mining now works, with overflow tracking
2. **Container Registry** - Named references to storage containers with persistence

## Changes

### Mine Autocollect
- Fixed stub in `PolisMineBlockAction.OnTick()` that logged "not yet implemented"
- Added `CollectDrops()` method following the pattern from `PolisHarvestCropAction`
- Added overflow tracking fields to report items left on ground when inventory is full
- Result message now includes: `"mined, collected X"` or `"mined, collected X/Y, overflow: Nx item"`

### Container Registry
- New data structures in `PolisNetworkPackets.cs`: `PolisContainerRegistry`, `ContainerRecord`
- Persistence via SaveGame data (`polis-containers` key)
- Commands: `container-register`, `container-list`, `container-remove`, `container-contents`
- GET endpoint: `/polis/container-contents?name=|x=&y=&z=`
- Extended `takefrom`/`putinto` to accept container names

### Files Modified
- `PolisBuilderNpcSystem.cs` - Mine autocollect, container registry commands, persistence
- `PolisNetworkPackets.cs` - Container registry data structures
- `PolisTestHarness.cs` - Container contents GET endpoint
- `scripts/poliscli.py` - CLI commands for container operations
- `docs/TESTING_HARNESS.md` - Documentation for new commands

## Test Plan

### Mine Autocollect

```bash
# Setup
./scripts/vsctl.py start --wait --window
./scripts/poliscli.py spawn
./scripts/poliscli.py select <BOT_ID>
export POLIS_BOT_ID=<BOT_ID>
./scripts/poliscli.py give game:pickaxe-copper

# Test basic autocollect
./scripts/poliscli.py setup-view
./scripts/poliscli.py mine <X> <Y> <Z> --autocollect --wait
./scripts/poliscli.py state  # Check inventory has items, LastAction.Msg shows "mined, collected X"

# Test overflow (fill inventory first)
./scripts/poliscli.py give game:stone-granite 64
./scripts/poliscli.py give game:stone-granite 64
# ... repeat until inventory nearly full
./scripts/poliscli.py mine <X> <Y> <Z> --autocollect --wait
# Expected: LastAction.Msg = "mined, collected X/Y, overflow: Nx item"
./scripts/poliscli.py state  # Check Items array shows overflow items on ground
```

### Container Registry

```bash
# Find a chest
./scripts/poliscli.py targets -s chest --radius 32

# Register
./scripts/poliscli.py container-register main-chest <X> <Y> <Z>
./scripts/poliscli.py container-list

# Check contents
./scripts/poliscli.py container-contents main-chest
./scripts/poliscli.py container-contents <X> <Y> <Z>  # By coordinates

# Use with takefrom/putinto
./scripts/poliscli.py give game:stone-granite 5
./scripts/poliscli.py putinto -c main-chest 0
./scripts/poliscli.py takefrom -c main-chest 0

# Persistence test
./scripts/vsctl.py restart --wait --window
./scripts/poliscli.py container-list  # Should persist

# Cleanup
./scripts/poliscli.py container-remove main-chest
```

### Stale Container Detection

```bash
# Register a container
./scripts/poliscli.py container-register temp-chest <X> <Y> <Z>

# Break the chest (or use setblock)
./scripts/poliscli.py setblock air <X> <Y> <Z>

# Verify staleness
./scripts/poliscli.py container-list  # Should show valid=false
./scripts/poliscli.py takefrom -c temp-chest 0  # Should fail with "moved or replaced" error
```

## Known Limitations

- VS block entities have no unique IDs - only coordinates
- If a container is moved, the registry entry becomes stale
- `container-list` includes a `valid` field to detect stale entries
- Using a stale container name returns an error with details

## CLI Usage Examples

```bash
# Container registry
poliscli.py container-register main-chest 224 3 270
poliscli.py container-register ore-bin 225 3 270 --type vessel --desc "Iron ore"
poliscli.py container-list
poliscli.py container-list --type chest
poliscli.py container-remove main-chest
poliscli.py container-contents main-chest
poliscli.py container-contents 224 3 270

# takefrom/putinto with names
poliscli.py takefrom -c main-chest 0      # Take from slot 0
poliscli.py putinto -c main-chest 0       # Put into container from bot slot 0
poliscli.py takefrom 224 3 270 0          # Still works with coordinates
```
