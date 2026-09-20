# Task System Research (2026-01-04)

## Research Sources
- **btca: vsvillage** - Villager job/profession system
- **btca: vssurvivalmod** - AI task patterns (AiTaskBase)
- **Local: vssurvivalmod** - EntityActivitySystem source (docs/vssurvivalmod/)

---

## Two Parallel Systems in Vintage Story

VS has **two separate systems** for NPC behavior:

### 1. AiTaskBase System (Creature AI)
Used by: Animals, monsters, basic NPCs

```
EntityBehaviorTaskAI
    └── AiTaskManager
        └── Multiple AiTaskBase instances
            ├── ShouldExecute() → Can this task run?
            ├── StartExecute()  → Begin the task
            ├── ContinueExecute(dt) → Tick, return false when done
            └── FinishExecute() → Cleanup
```

**Key Pattern:**
- Tasks compete for execution based on `ShouldExecute()` returning true
- One task runs at a time (per priority tier)
- Configuration via JSON entity properties
- Used by vsvillage for villager jobs

### 2. EntityActivitySystem (Scripted Behavior)
Used by: Complex NPCs, story characters, **our polis bots**

```
EntityActivitySystem
    ├── AvailableActivities[] - All defined activities
    ├── ActiveActivitiesBySlot{} - Currently running (by slot)
    └── wppathTraverser / linepathTraverser

EntityActivity
    ├── Slot (int) - Parallel activity lanes
    ├── Priority (double) - Higher wins
    ├── Conditions[] - When to auto-trigger
    ├── Actions[] - Sequential action list
    └── currentActionIndex - Progress tracker

IEntityAction (e.g., GotoAction, ActivateBlockAction)
    ├── Start(activity) - Begin action
    ├── OnTick(dt) - Per-tick update
    ├── IsFinished() - Check completion
    ├── Cancel() / Finish() - Cleanup
    └── ExecutionHasFailed - Error flag
```

**Key Pattern:**
- Activities contain sequences of actions
- Actions execute sequentially within an activity
- Multiple activities can run in parallel (different slots)
- Auto-selection based on conditions (can be disabled with `PauseAutoSelection`)

---

## vsvillage Job System Architecture

vsvillage uses AiTaskBase, NOT EntityActivitySystem:

### Profession Enum
```csharp
public enum EnumVillagerProfession {
    smith, farmer, shepherd, mayor, soldier, herbalist, trader
}
```

### Workstation System
```csharp
public class VillagerWorkstation {
    public BlockPos Pos;
    public long OwnerId = -1;  // Claimed by villager
    public EnumVillagerProfession Profession;
}

// Village tracks all workstations
public class Village {
    public Dictionary<BlockPos, VillagerWorkstation> Workstations;

    public BlockPos FindFreeWorkstation(long villagerId, EnumVillagerProfession profession) {
        // Find unclaimed workstation matching profession
    }
}
```

### Job AI Tasks
```csharp
// Go to assigned workstation
public class AiTaskVillagerGotoWork : AiTaskGotoAndInteract {
    protected override Vec3d GetTargetPos() {
        var workPos = villager.Workstation;
        if (workPos == null) {
            workPos = village.FindFreeWorkstation(entity.EntityId, villager.Profession);
        }
        return workPos.ToVec3d();
    }
}

// Farmer-specific task
public class AiTaskVillagerCultivateCrops : AiTaskGotoAndInteract {
    protected override void ApplyInteractionEffect() {
        if (nearestFarmland.HasUnripeCrop()) {
            nearestFarmland.TryGrowCrop(...);
        }
    }
}
```

---

## Available Actions in EntityActivitySystem

From `docs/vssurvivalmod/Systems/EntityActivitySystem/Action/`:

| Action | Description |
|--------|-------------|
| `GotoAction` | A* or straight-line pathfinding to target |
| `ActivateBlockAction` | Interact with a block |
| `WaitAction` | Pause for duration |
| `PlayAnimationAction` | Trigger animation |
| `TurnAction` | Rotate to face direction |
| `LookatBlockAction` | Look at block position |
| `LookatEntityAction` | Look at entity |
| `TeleportAction` | Instant move |
| `EquipAction` / `UnequipAction` | Item handling |
| `DressAction` / `UndressAction` | Clothing |
| `MountBlockAction` / `UnmountAction` | Mounting |
| `TalkAction` | Speech/dialogue |
| `PlaySoundAction` / `PlaySongAction` | Audio |
| `SetVarAction` | Set entity attribute |
| `TriggerEmotionStateAction` | Emotion system |
| `StandardAIAction` | Delegate to AiTask system |
| `StartActivityAction` | Chain to another activity |

---

## Recommendations for Polis Task System

### Option A: Build on EntityActivitySystem (Current Approach)
**Pros:**
- Already using it in polis-builder-npc
- Sequential action chains work well
- Can PauseAutoSelection for manual control
- Supports parallel slots

**Cons:**
- Not designed for priority-based task selection
- No built-in "idle task picker"
- Need custom task queue layer on top

### Option B: Hybrid Approach
Use EntityActivitySystem for action execution, but add our own task layer:

```
PolisTaskSystem (NEW)
    └── TaskQueue per bot
        ├── Pending tasks (priority queue)
        ├── Current task → EntityActivity
        └── Task types (PolisTask subclasses)
            ├── HarvestTask → GotoAction + custom harvest action
            ├── HaulTask → GotoAction + pickup + GotoAction + drop
            ├── BuildTask → GotoAction + place block sequences
            └── IdleTask → wander / wait at location
```

### Option C: AiTaskBase (vsvillage style)
**Pros:**
- Designed for autonomous behavior
- Priority/condition system built-in
- Proven in vsvillage

**Cons:**
- Different from our current EntityActivitySystem usage
- Would require behavior refactor
- Less suitable for command-driven sequences

---

## Recommended Next Steps

1. **Keep EntityActivitySystem** for action execution
2. **Add PolisTaskQueue** layer for task management:
   - Queue of pending tasks per bot
   - Task → Activity conversion
   - Priority and interruption handling
3. **Define core task types:**
   - `PolisGotoTask` (already have)
   - `PolisHarvestTask` (goto + break + collect)
   - `PolisHaulTask` (pickup item + goto + drop)
   - `PolisBuildTask` (goto + place block)
   - `PolisIdleTask` (wait or wander)
4. **Add task assignment UI** or commands

---

## Key Code References

### EntityActivitySystem Core Methods
```csharp
// Start an activity by code
bool StartActivity(string code, float priority=9999f, int slot=-1)

// Cancel all active activities
bool CancelAll()

// Pause auto-selection (for manual control)
void PauseAutoSelection(bool paused)

// Per-tick update
void OnTick(float dt)
```

### EntityActivity Lifecycle
```csharp
void Start()       // Begin activity, start first action
void OnTick(dt)    // Tick current action, advance when finished
void Cancel()      // Abort activity
void Finish()      // Complete activity, cleanup
```

### IEntityAction Interface
```csharp
void Start(EntityActivity act)
void OnTick(float dt)
bool IsFinished()
void Cancel()
void Finish()
void Pause(EnumInteruptionType)
void Resume()
```
