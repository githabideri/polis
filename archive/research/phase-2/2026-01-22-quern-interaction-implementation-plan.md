# Quern Interaction Implementation Plan

**Date:** 2026-01-22
**Status:** Implementation Plan
**btca Queries:** vssurvivalmod (BlockQuern, BEQuern, GrindingProps)

## Overview

This document details how to implement quern grinding interactions for polisbots. The quern is a VS workstation that converts grindable items (grain→flour, etc.) through continuous player interaction.

## Research Summary

### VS Quern Mechanics (from btca)

**Source:** `vssurvivalmod/Block/BlockQuern.cs`, `vssurvivalmod/BlockEntity/BEQuern.cs`

1. **Block Structure**
   - Two selection boxes:
     - **Index 0 (base):** Opens GUI/inventory dialog
     - **Index 1 (top/handle):** Starts grinding if `CanGrind()` returns true

2. **Grinding Flow**
   ```
   Player right-click (SelectionBoxIndex=1) + hold:
   1. OnBlockInteractStart → SetPlayerGrinding(player, true) → quantityPlayersGrinding++
   2. OnBlockInteractStep  → returns true (continue), updates timestamp
   3. Every100ms tick      → inputGrindTime += dt * GrindSpeed
   4. When inputGrindTime >= maxGrindingTime() → grindInput() → consume input, produce output
   5. OnBlockInteractStop  → SetPlayerGrinding(player, false) → quantityPlayersGrinding--
   ```

3. **Key APIs**
   - `BlockEntityQuern.CanGrind()` → checks if input slot has item with `GrindingProps`
   - `BlockEntityQuern.InputGrindProps` → returns `GrindingProperties` from input item
   - `BlockEntityQuern.maxGrindingTime()` → returns 4.0f (default grind duration per item)
   - `BlockEntityQuern.SetPlayerGrinding(player, bool)` → registers/unregisters grinder
   - `GrindingProperties.GroundStack` → the output itemstack definition

4. **Automation Support**
   - Quern also supports mechanical power via `BEBehaviorMPConsumer`
   - When automated, `mpc.TrueSpeed` provides grinding speed without players
   - Bot interaction is NOT automation - it's player-like interaction

### Current Mod State

**Existing Commands:**
- `activate` → single `OnBlockInteractStart` call, no hold
- `harvest` → timed `OnBlockInteractStart/Step/Stop` pattern for harvestable blocks
- `mine` → timed progress accumulation with `BreakBlock` at end

**Gap:** No command for continuous timed block interaction that uses `OnBlockInteract*` pattern for grinding/spinning/churning type workstations.

## Design

### New Command: `grind`

A new harness/CLI command for quern grinding that:
1. Validates quern block and grindable input
2. Calls `OnBlockInteractStart` with `SelectionBoxIndex=1`
3. Continues with `OnBlockInteractStep` each tick
4. Completes after grinding time or manually stopped
5. Calls `OnBlockInteractStop` to finalize

**CLI Usage:**
```bash
polis grind <x> <y> <z> [--duration <seconds>] [--count <items>] [--wait]
```

**Options:**
- `--duration <seconds>` → grind for fixed duration (default: until stopped or input exhausted)
- `--count <items>` → grind specific number of input items, then stop
- `--wait` → block until grinding completes (default: true for grind)

**HTTP API:**
```
POST /polis/command
{
  "cmd": "grind",
  "args": ["<x>", "<y>", "<z>", "<duration|count>"],
  "context": {"playerUid": "..."}
}
```

### New Action: `PolisGrindBlockAction`

**Location:** `PolisBuilderNpcSystem.cs` (alongside other actions)

**Class Design:**
```csharp
class PolisGrindBlockAction : EntityActionBase
{
    // Constructor params
    readonly BlockPos targetPos;
    readonly IServerPlayer player;
    readonly float maxRange;
    readonly float targetDuration;  // 0 = until manually stopped
    readonly int targetCount;       // 0 = unlimited
    readonly Action<string> debugLog;
    readonly Action<bool, string> onResult;

    // Runtime state
    Block block;
    BlockEntityQuern quern;
    BlockSelection blockSel;
    float elapsedTime;
    int itemsGround;
    int startInputCount;
    bool interactionStarted;
    bool validated;
    bool done;
    string activeAnimation;

    const float DEFAULT_MAX_RANGE = 4.5f;
    const float GRIND_TIME_PER_ITEM = 4.0f;  // VS default
}
```

**Lifecycle:**

1. **Start()**
   - Range check (bot → quern center)
   - Player validation
   - Block validation (`GetBlock`, check for quern)
   - Get `BlockEntityQuern` from block entity
   - Check `CanGrind()` (input slot has grindable item)
   - Record initial input count
   - Build `BlockSelection` with `SelectionBoxIndex = 1`
   - Call `block.OnBlockInteractStart(world, player, blockSel)`
   - Start grinding animation
   - Report "grinding started"

2. **OnTick(dt)**
   - Accumulate `elapsedTime += dt`
   - Call `block.OnBlockInteractStep(elapsedTime, world, player, blockSel)`
   - Check for completion:
     - Duration target reached
     - Count target reached (monitor quern input slot changes)
     - Input exhausted (`!CanGrind()`)
   - If complete → finalize

3. **Finalize / Cancel()**
   - Call `block.OnBlockInteractStop(elapsedTime, world, player, blockSel)`
   - Stop animation
   - Report result with items ground count

### BlockSelection Setup

Critical: The selection box index must be 1 to trigger grinding mode.

```csharp
var blockSel = new BlockSelection
{
    Position = targetPos,
    Face = BlockFacing.UP,
    HitPosition = new Vec3d(0.5, 1.0, 0.5),  // Top of block
    Block = block,
    SelectionBoxIndex = 1  // CRITICAL: 1 = grinding, 0 = open inventory
};
```

### Animation

Use `hit` animation (looping) during grinding:
```csharp
void StartGrindingAnimation()
{
    var animMeta = new AnimationMetaData
    {
        Code = "hit",
        Animation = "hit",
        AnimationSpeed = 0.8f,  // Slightly slower for grinding feel
        BlendMode = EnumAnimationBlendMode.Average
    };
    vas.Entity.AnimManager.StartAnimation(animMeta.Init());
    activeAnimation = "hit";
}
```

### Progress Tracking

The quern's `inputGrindTime` and `maxGrindingTime()` track internal grinding progress. However, we track our own `elapsedTime` to know when to stop:

- **Duration mode:** Stop after `elapsedTime >= targetDuration`
- **Count mode:** Check `quern.inventory[0].StackSize` periodically, stop when decreased by `targetCount`
- **Default mode:** Stop when `!quern.CanGrind()` (input exhausted)

### Harness Integration

Add to command handler in `PolisTestHarness.cs`:
```csharp
case "grind":
    return HandleGrindCommand(args, context, botState, player);
```

**HandleGrindCommand:**
1. Parse coordinates
2. Parse optional duration/count
3. Get block entity, validate it's a quern
4. Create `PolisGrindBlockAction`
5. Start action sequence
6. Return immediate response with estimated time

### CLI Integration

Add to `poliscli.py`:
```python
def cmd_grind(client: HarnessClient, args, fmt: OutputFormatter) -> int:
    """Grind items in a quern."""
    # ... coordinate validation

    cmd_args = [str(args.x), str(args.y), str(args.z)]
    if getattr(args, "duration", None):
        cmd_args.append(f"duration={args.duration}")
    if getattr(args, "count", None):
        cmd_args.append(f"count={args.count}")

    context = build_context(args, client)
    result = send_command(client, "grind", cmd_args, context, fmt)

    if getattr(args, "wait", True):
        return wait_for_action(client, args, fmt, "grind", "ground")

    return EXIT_SUCCESS
```

### Targets Discovery

The `/polis/targets` endpoint should already discover querns as blocks with `EntityClass: Quern`. No changes needed for discovery.

To check if a quern has grindable input, add optional `quernState` to targets response:
```json
{
  "pos": [100, 65, 200],
  "code": "game:quern-granite",
  "entityClass": "Quern",
  "behaviors": ["..."],
  "quernState": {
    "canGrind": true,
    "inputCode": "game:grain-spelt",
    "inputQty": 5,
    "outputCode": "game:flour-spelt",
    "outputQty": 2
  }
}
```

## Test Plan

### Pre-requisites
- VS running in survival mode
- Quern placed in world
- Grindable items available (grain, etc.)

### Visual Test Protocol

Following repo best practices from `AGENTS.md`:

```bash
# 0. Clean up existing bots
./scripts/poliscli.py bots
./scripts/poliscli.py despawn --bot <OLD_BOT_ID>  # For each

# 1. Spawn and select bot
./scripts/poliscli.py spawn
./scripts/poliscli.py select <BOT_ID>
export POLIS_BOT_ID=<BOT_ID>

# 2. Give grain to bot
./scripts/poliscli.py give game:grain-spelt 10

# 3. Position bot near quern
./scripts/poliscli.py goto <QUERN_X> <QUERN_Y> <QUERN_Z-1> --wait

# 4. Position camera to view bot and quern
./scripts/poliscli.py setup-view --screenshot --save

# 5. Put grain into quern (using putinto with quern coords)
./scripts/poliscli.py putinto <QUERN_X> <QUERN_Y> <QUERN_Z> 0

# 6. Screenshot to verify grain in quern
./scripts/poliscli.py screenshot --save

# 7. Run grind command
./scripts/poliscli.py grind <QUERN_X> <QUERN_Y> <QUERN_Z> --count 3 --wait

# 8. Screenshot mid-grinding (if possible)
./scripts/poliscli.py screenshot --save

# 9. After completion, verify output
./scripts/poliscli.py container-contents <QUERN_X> <QUERN_Y> <QUERN_Z>
./scripts/poliscli.py screenshot --save
```

### Test Cases

| Test | Input | Expected | Verify |
|------|-------|----------|--------|
| Basic grind | Quern with 5 grain | Flour produced | container-contents shows flour |
| Count limit | `--count 2` with 5 grain | 2 ground, 3 remain | container-contents shows 3 grain, 2 flour |
| Duration limit | `--duration 10` | Stops after 10s | Action completes, flour produced |
| Empty input | Quern with no grain | Error "nothing to grind" | LastAction.Ok=false |
| Out of range | Bot 10 blocks from quern | Error "out of range" | LastAction.Ok=false |
| Wrong block | Coords point to chest | Error "not a quern" | LastAction.Ok=false |
| Animation | During grinding | Bot plays hit animation | Visual inspection |
| Cancel | `/polis stop` during grind | Grinding stops | Action cancelled, partial progress |

### Structured Verification

After each grind:
```bash
# Check bot state
./scripts/poliscli.py state

# Check quern contents
./scripts/poliscli.py container-contents <QUERN_X> <QUERN_Y> <QUERN_Z>

# Check action result
# LastAction should show: {Name: "grind", Ok: true, Msg: "ground 3 items"}
```

## Implementation Checklist

### Phase 1: Core Action (Minimum Viable)
- [ ] Add `PolisGrindBlockAction` class
- [ ] Implement Start() with validation and OnBlockInteractStart
- [ ] Implement OnTick() with OnBlockInteractStep and completion check
- [ ] Implement Cancel() with OnBlockInteractStop
- [ ] Add grinding animation
- [ ] Add harness command handler
- [ ] Test basic grinding flow

### Phase 2: CLI Integration
- [ ] Add `grind` subcommand to poliscli.py
- [ ] Add `--duration`, `--count`, `--wait` flags
- [ ] Add `--no-wait` option
- [ ] Update CLI.md documentation

### Phase 3: Enhanced Features
- [ ] Add quernState to targets response
- [ ] Add container-contents support for quern slots
- [ ] Add progress tracking in events
- [ ] Consider generalizing to other workstations (butter churn, etc.)

### Phase 4: Documentation
- [ ] Update TECHNICAL.md with action details
- [ ] Add grind examples to TESTING_HARNESS.md
- [ ] Update CLI.md with grind command
- [ ] Add test report to journal

## Future Considerations

### Generalization to Other Workstations

The quern pattern (timed OnBlockInteract\* with selection box) may apply to:
- **Butter Churn** - likely same pattern
- **Spinning Wheel** - fiber → thread
- **Forge** - metal working (may have additional complexity)

Consider creating a generic `PolisTimedBlockInteractAction` base class after quern is working.

### Integration with Task System (Phase 2)

When the task/job system is implemented:
- Grinding becomes a task type
- WorkGiver scans for querns with grindable input
- Job assigns bot to grind until complete or interrupted
- Reservation prevents multiple bots grinding same quern

## References

- `vssurvivalmod/Block/BlockQuern.cs` - block interaction handlers
- `vssurvivalmod/BlockEntity/BEQuern.cs` - block entity with CanGrind, grinding state
- `docs/TECHNICAL.md` - action pattern documentation
- `docs/research/phase-2/2026-01-06-held-use-implementation.md` - timed interaction patterns
- `docs/journal/2026-01-13-harness-activate-misc-blocks.md` - quern activate test (GUI only)
