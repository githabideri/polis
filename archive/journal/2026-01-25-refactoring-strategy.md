# Polis Builder NPC Refactoring Strategy

This document outlines a comprehensive plan to restructure the polis-builder-npc codebase for improved maintainability, testability, and developer experience.

## Current State Analysis

### File Structure Overview

| File | Lines | % of Total | Description |
|------|-------|------------|-------------|
| PolisBuilderNpcSystem.cs | 11,845 | 73% | Monolithic system class |
| PolisTestHarness.cs | 1,234 | 8% | HTTP API harness |
| PolisEventBroadcaster.cs | 337 | 2% | WebSocket events |
| PolisPossessableSeat.cs | 294 | 2% | Possession mechanic |
| PolisInventoryHelpers.cs | 291 | 2% | Inventory utilities |
| PolisContainerPutAction.cs | 233 | 1% | Container deposit action |
| PolisNetworkPackets.cs | 217 | 1% | Network packet definitions |
| PolisContainerTakeAction.cs | 214 | 1% | Container withdraw action |
| PolisScreenCaptureRenderer.cs | 200 | 1% | Screenshot renderer |
| PolisAnimationHelpers.cs | 197 | 1% | Animation utilities |
| PolisBuilderNpcHarmony.cs | 187 | 1% | Harmony patches |
| PolisInteractEntityAction.cs | 179 | 1% | Entity interaction action |
| Gui/GuiDialogBotManager.cs | 168 | 1% | Bot manager UI |
| PolisScreenCapture.cs | 168 | 1% | Screenshot capture |
| PolisDropItemAction.cs | 167 | 1% | Item drop action |
| PolisPickupItemAction.cs | 136 | 1% | Item pickup action |
| PolisClientPossessionHandler.cs | 131 | 1% | Client possession |
| PolisBuilderNpcHotkeys.cs | 105 | 1% | Hotkey bindings |
| EntityPolisBot.cs | 31 | <1% | Bot entity type |
| **Total** | **16,334** | 100% | |

### Problem: PolisBuilderNpcSystem.cs Breakdown

The monolithic System.cs file contains multiple distinct concerns:

| Section | Lines | Span | Description |
|---------|-------|------|-------------|
| Core System | 1-622 | 622 | Fields, initialization, lifecycle |
| RegisterCommands | 623-823 | 200 | Chat command registration |
| Chat Cmd* handlers | 825-1240 | 415 | Chat command implementations |
| ExecuteHarnessCommand | 1244-1358 | 115 | Harness command dispatch |
| Execute*Command methods | 1360-7346 | 5,986 | HTTP API implementations |
| Nested Action classes | 7348-11845 | 4,497 | 15 action class definitions |

### Nested Actions in System.cs

These action classes are defined inside `PolisBuilderNpcSystem`:

| Class | Lines | Span | Category |
|-------|-------|------|----------|
| PolisGotoAction | 7348-7585 | 237 | Navigation |
| PolisActivateBlockAction | 7588-7729 | 141 | Blocks |
| PolisIgniteBlockAction | 7732-7838 | 106 | Blocks |
| PolisBreakBlockAction | 7841-7924 | 83 | Blocks |
| PolisMineBlockAction | 7927-8264 | 337 | Blocks |
| PolisPlaceBlockAction | 8267-8366 | 99 | Blocks |
| PolisHarvestBlockAction | 8369-8803 | 434 | Harvesting |
| PolisHarvestCropAction | 8806-9057 | 251 | Harvesting |
| PolisGrindBlockAction | 9060-9371 | 311 | Workstations |
| PolisPressAction | 9374-9733 | 359 | Workstations |
| PolisButcherEntityAction | 9736-9997 | 261 | Entities |
| PolisClayFormAction | 10000-10437 | 437 | Workstations |
| PolisKnapAction | 10440-10920 | 480 | Workstations |
| PolisSealBarrelAction | 10923-11066 | 143 | Workstations |
| PolisAnvilSmithAction | 11069-11845 | 776 | Workstations |

### Already-Extracted Actions (Good Patterns)

These files demonstrate the target structure:

| File | Lines | Category |
|------|-------|----------|
| PolisContainerTakeAction.cs | 214 | Inventory |
| PolisContainerPutAction.cs | 233 | Inventory |
| PolisPickupItemAction.cs | 136 | Inventory |
| PolisDropItemAction.cs | 167 | Inventory |
| PolisInteractEntityAction.cs | 179 | Entities |

### Other Issues

1. **No namespaces**: All 18 C# files use global namespace
2. **Magic numbers**: Constants scattered across files (slot IDs, ports, ranges)
3. **Stale artifacts**: Debug screenshots and zip file in root
4. **Duplicate validation**: Container actions repeat range/block/claims checks

## Target Architecture

### Directory Structure

```
polis-builder-npc/
├── src/
│   ├── Actions/
│   │   ├── Navigation/
│   │   │   └── PolisGotoAction.cs
│   │   ├── Blocks/
│   │   │   ├── PolisActivateBlockAction.cs
│   │   │   ├── PolisBreakBlockAction.cs
│   │   │   ├── PolisIgniteBlockAction.cs
│   │   │   ├── PolisMineBlockAction.cs
│   │   │   └── PolisPlaceBlockAction.cs
│   │   ├── Harvesting/
│   │   │   ├── PolisHarvestBlockAction.cs
│   │   │   └── PolisHarvestCropAction.cs
│   │   ├── Workstations/
│   │   │   ├── PolisAnvilSmithAction.cs
│   │   │   ├── PolisClayFormAction.cs
│   │   │   ├── PolisGrindBlockAction.cs
│   │   │   ├── PolisKnapAction.cs
│   │   │   ├── PolisPressAction.cs
│   │   │   └── PolisSealBarrelAction.cs
│   │   ├── Inventory/
│   │   │   ├── PolisContainerPutAction.cs
│   │   │   ├── PolisContainerTakeAction.cs
│   │   │   ├── PolisDropItemAction.cs
│   │   │   └── PolisPickupItemAction.cs
│   │   └── Entities/
│   │       ├── PolisButcherEntityAction.cs
│   │       └── PolisInteractEntityAction.cs
│   ├── Commands/
│   │   ├── PolisCommandRegistry.cs      (~200 lines from RegisterCommands)
│   │   └── PolisChatCommandHandlers.cs  (~415 lines of Cmd* methods)
│   ├── Harness/
│   │   └── PolisHarnessCommandHandlers.cs (~6100 lines)
│   ├── Core/
│   │   ├── PolisBuilderNpcSystem.cs     (reduced to ~600 lines)
│   │   ├── PolisConstants.cs            (all magic numbers)
│   │   └── PolisValidation.cs           (shared validation helpers)
│   ├── Helpers/
│   │   ├── PolisInventoryHelpers.cs
│   │   └── PolisAnimationHelpers.cs
│   └── Network/
│       ├── PolisNetworkPackets.cs
│       └── PolisEventBroadcaster.cs
├── Gui/
│   └── GuiDialogBotManager.cs
├── EntityPolisBot.cs
├── PolisTestHarness.cs
├── PolisScreenCapture.cs
├── PolisScreenCaptureRenderer.cs
├── PolisPossessableSeat.cs
├── PolisClientPossessionHandler.cs
├── PolisBuilderNpcHotkeys.cs
└── PolisBuilderNpcHarmony.cs
```

### Namespace Structure

```csharp
// Core system
namespace PolisBuilderNpc.Core;

// Actions by category
namespace PolisBuilderNpc.Actions.Navigation;
namespace PolisBuilderNpc.Actions.Blocks;
namespace PolisBuilderNpc.Actions.Harvesting;
namespace PolisBuilderNpc.Actions.Workstations;
namespace PolisBuilderNpc.Actions.Inventory;
namespace PolisBuilderNpc.Actions.Entities;

// Commands
namespace PolisBuilderNpc.Commands;

// Harness
namespace PolisBuilderNpc.Harness;

// Helpers
namespace PolisBuilderNpc.Helpers;

// Network
namespace PolisBuilderNpc.Network;

// GUI
namespace PolisBuilderNpc.Gui;

// Root namespace for loose files
namespace PolisBuilderNpc;
```

## Phased Approach

### Phase 1: Quick Wins (No Code Changes)

1. **Remove stale artifacts**
   - `gui-fail.png`, `gui-fail2.png` (debug screenshots)
   - `polis-builder-npc.zip` (old build artifact)

2. **Create PolisConstants.cs**
   - Move all magic numbers to central location
   - Update references to use constants

3. **Move helper classes to src/Helpers/**
   - `PolisInventoryHelpers.cs`
   - `PolisAnimationHelpers.cs`

### Phase 2: Foundation

4. **Create PolisValidation.cs**
   - Extract common validation patterns
   - Range checks, block entity checks, claims checks
   - Reduces duplication across actions

### Phase 3: Action Extraction

Extract nested actions from System.cs to individual files:

5. **Navigation**: `PolisGotoAction` (lines 7348-7585)

6. **Block actions** (5 files):
   - `PolisActivateBlockAction` (7588-7729)
   - `PolisBreakBlockAction` (7841-7924)
   - `PolisIgniteBlockAction` (7732-7838)
   - `PolisMineBlockAction` (7927-8264)
   - `PolisPlaceBlockAction` (8267-8366)

7. **Harvest actions** (2 files):
   - `PolisHarvestBlockAction` (8369-8803)
   - `PolisHarvestCropAction` (8806-9057)

8. **Workstation actions** (6 files):
   - `PolisGrindBlockAction` (9060-9371)
   - `PolisPressAction` (9374-9733)
   - `PolisClayFormAction` (10000-10437)
   - `PolisKnapAction` (10440-10920)
   - `PolisSealBarrelAction` (10923-11066)
   - `PolisAnvilSmithAction` (11069-11845)

9. **Entity action**: `PolisButcherEntityAction` (9736-9997)

### Phase 4: Organization

10. **Move already-extracted actions** to `src/Actions/{Category}/`
    - `PolisContainerPutAction.cs` -> `src/Actions/Inventory/`
    - `PolisContainerTakeAction.cs` -> `src/Actions/Inventory/`
    - `PolisPickupItemAction.cs` -> `src/Actions/Inventory/`
    - `PolisDropItemAction.cs` -> `src/Actions/Inventory/`
    - `PolisInteractEntityAction.cs` -> `src/Actions/Entities/`

11. **Add namespaces** to all files

### Phase 5: Command Extraction

12. **Extract RegisterCommands**
    - Create `src/Commands/PolisCommandRegistry.cs`
    - Move lines 623-823 from System.cs

13. **Extract harness commands** (largest change)
    - Create `src/Harness/PolisHarnessCommandHandlers.cs`
    - Move `ExecuteHarnessCommand` and all `Execute*Command` methods
    - Lines 1244-7346 (~6100 lines)

## Expected Impact

| Metric | Before | After |
|--------|--------|-------|
| System.cs lines | 11,845 | ~600 |
| Root-level files | 18 | ~12 |
| Files with namespaces | 0 | All |
| Magic number locations | 50+ | 1 |
| Average file size | 900 lines | <400 lines |
| Max file size | 11,845 lines | ~1,234 lines |

## Verification Strategy

Each refactoring step should:

1. **Build verification**: `./build.sh` must succeed
2. **No new warnings**: Compiler output should not introduce warnings
3. **Git history**: Use `git mv` to preserve file history
4. **Incremental commits**: One commit per logical change

Final verification:
1. Build succeeds: `./build.sh --deploy`
2. Harness responds: `./scripts/poliscli.py status`
3. Basic bot operations work (manual spot check)

## Issue Dependency Graph

```
                        polis-cleanup-stale (independent)
                        polis-constants     (independent)
                        polis-move-helpers  (independent)
                                 |
                                 v
                      polis-validation-helper
                                 |
        +------------------------+------------------------+
        |           |            |           |            |
        v           v            v           v            v
  polis-extract  polis-extract  polis-extract  polis-extract  polis-extract
  -goto          -block-actions -harvest-actions -workstation -butcher
        |           |            |           |            |
        +------------------------+------------------------+
                                 |
                                 v
                      polis-move-existing-actions
                                 |
                                 v
                        polis-add-namespaces
                                 |
        +------------------------+
        |                        |
        v                        v
  polis-extract-command   polis-extract-harness
  -registration           -commands
```

## Notes

- **Backward compatibility**: Public APIs remain unchanged
- **No runtime changes**: This is pure organizational refactoring
- **Build-only verification**: No game launch required for most steps
- **Parallel work**: Many action extractions can happen concurrently
