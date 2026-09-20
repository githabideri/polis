# Primitives to Jobs Mapping

> Planning document for Phase 2 autonomous job system. Maps harness commands and action classes to composed job sequences.

## Harness Commands (37 total)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           HARNESS COMMANDS (37 total)                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  BOT MANAGEMENT          MOVEMENT           INVENTORY                       │
│  ├─ spawn                ├─ goto            ├─ give (debug)                 │
│  ├─ select               ├─ gotolook        ├─ drop                         │
│  ├─ selectlook           └─ stop            ├─ pickup                       │
│  ├─ despawn                                 └─ equip                        │
│  └─ bots                                                                    │
│                                                                             │
│  BLOCK INTERACTION       CONTAINER OPS      ENTITY INTERACTION              │
│  ├─ activate             ├─ takefrom        ├─ interact                     │
│  ├─ mine                 ├─ putinto         ├─ butcher                      │
│  ├─ place                ├─ container-*     └─ loot                         │
│  ├─ setblock (debug)     │  (register,                                      │
│  └─ ignite               │   list, remove,                                  │
│                          │   contents)                                      │
│                                                                             │
│  HARVESTING              WORKSTATIONS       BUILDING                        │
│  ├─ harvest (berries)    ├─ grind (quern)   ├─ scan                         │
│  └─ harvestcrop          ├─ press (fruit)   ├─ verify                       │
│                          ├─ clayform        └─ build                        │
│                          ├─ knap                                            │
│                          └─ seal (barrel)                                   │
│                                                                             │
│  PLAYER/DEBUG            POSSESSION                                         │
│  ├─ teleport             ├─ possess                                         │
│  ├─ animate              ├─ unpossess                                       │
│  ├─ spawnentity          └─ setcontrols                                     │
│  ├─ killentity                                                              │
│  └─ teststate                                                               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Action Classes (IEntityAction implementations)

These are the **async primitives** that run over multiple ticks:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        ACTION CLASSES (20 total)                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  MOVEMENT                          BLOCKS                                   │
│  └─ PolisGotoAction                ├─ PolisActivateBlockAction              │
│     (A* pathfinding, walk/run)     ├─ PolisMineBlockAction                  │
│                                    ├─ PolisBreakBlockAction                 │
│                                    ├─ PolisPlaceBlockAction                 │
│                                    └─ PolisIgniteBlockAction                │
│                                                                             │
│  INVENTORY                         CONTAINERS                               │
│  ├─ PolisPickupItemAction          ├─ PolisContainerTakeAction              │
│  └─ PolisDropItemAction            └─ PolisContainerPutAction               │
│                                                                             │
│  HARVESTING                        ENTITIES                                 │
│  ├─ PolisHarvestBlockAction        ├─ PolisInteractEntityAction             │
│  └─ PolisHarvestCropAction         └─ PolisButcherEntityAction              │
│                                                                             │
│  WORKSTATIONS                                                               │
│  ├─ PolisGrindBlockAction   (quern - held-use pattern)                      │
│  ├─ PolisPressAction        (fruit press - screw interaction)               │
│  ├─ PolisClayFormAction     (progressive voxel placement)                   │
│  ├─ PolisKnapAction         (progressive voxel removal)                     │
│  └─ PolisSealBarrelAction   (barrel seal interaction)                       │
│                                                                             │
│  NOTE: loot command is INLINE (no action class) - direct inventory transfer │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Jobs (composed from primitives)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      JOBS (composed from primitives)                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ═══════════════════════════════════════════════════════════════════════   │
│  RESOURCE GATHERING                                                         │
│  ═══════════════════════════════════════════════════════════════════════   │
│                                                                             │
│  HarvestCropJob                                                             │
│  ┌─────────┐    ┌─────────────┐    ┌────────┐                              │
│  │  goto   │───▶│ harvestcrop │───▶│ pickup │  (if drops on ground)        │
│  └─────────┘    └─────────────┘    └────────┘                              │
│       │                │                │                                   │
│       ▼                ▼                ▼                                   │
│   PolisGoto    PolisHarvestCrop   PolisPickup                              │
│    Action          Action          Action                                   │
│                                                                             │
│  HarvestBerryJob                                                            │
│  ┌─────────┐    ┌─────────┐    ┌────────┐                                  │
│  │  goto   │───▶│ harvest │───▶│ pickup │  (autocollect usually works)     │
│  └─────────┘    └─────────┘    └────────┘                                   │
│                                                                             │
│  MineBlockJob                                                               │
│  ┌─────────┐    ┌───────┐    ┌────────┐                                    │
│  │  goto   │───▶│ mine  │───▶│ pickup │  (collect ore/stone drops)         │
│  └─────────┘    └───────┘    └────────┘                                    │
│                                                                             │
│  ═══════════════════════════════════════════════════════════════════════   │
│  HUNTING / ANIMAL PROCESSING                                                │
│  ═══════════════════════════════════════════════════════════════════════   │
│                                                                             │
│  ButcherJob (dead animal → meat/hide/fat)                                   │
│  ┌─────────┐    ┌─────────┐    ┌────────┐                                  │
│  │  goto   │───▶│ butcher │───▶│  loot  │  (transfer harvest inv to bot)   │
│  └─────────┘    └─────────┘    └────────┘                                  │
│       │                │                │                                   │
│       ▼                ▼                ▼                                   │
│   PolisGoto    PolisButcher      INLINE (no action)                        │
│    Action          Action                                                   │
│                                                                             │
│  BreakCarcassJob (carcass block → bones)                                    │
│  ┌─────────┐    ┌───────┐    ┌────────┐                                    │
│  │  goto   │───▶│ mine  │───▶│ pickup │  (carcass is a BLOCK, not entity)  │
│  └─────────┘    └───────┘    └────────┘                                    │
│                                                                             │
│  ═══════════════════════════════════════════════════════════════════════   │
│  HAULING / LOGISTICS                                                        │
│  ═══════════════════════════════════════════════════════════════════════   │
│                                                                             │
│  HaulGroundItemJob (item on ground → storage)                               │
│  ┌─────────┐    ┌────────┐    ┌─────────┐    ┌────────┐                    │
│  │  goto   │───▶│ pickup │───▶│  goto   │───▶│ putinto│                    │
│  └─────────┘    └────────┘    └─────────┘    └────────┘                    │
│   (to item)                    (to chest)                                   │
│                                                                             │
│  HaulFromContainerJob (container A → container B)                           │
│  ┌─────────┐    ┌──────────┐    ┌─────────┐    ┌────────┐                  │
│  │  goto   │───▶│ takefrom │───▶│  goto   │───▶│ putinto│                  │
│  └─────────┘    └──────────┘    └─────────┘    └────────┘                  │
│   (to src)                       (to dest)                                  │
│                                                                             │
│  ═══════════════════════════════════════════════════════════════════════   │
│  CRAFTING / WORKSTATIONS                                                    │
│  ═══════════════════════════════════════════════════════════════════════   │
│                                                                             │
│  GrindJob (grain → flour at quern)                                          │
│  ┌─────────┐    ┌────────┐    ┌─────────┐    ┌───────┐    ┌──────────┐     │
│  │  goto   │───▶│takefrom│───▶│  goto   │───▶│ grind │───▶│ takefrom │     │
│  └─────────┘    └────────┘    └─────────┘    └───────┘    └──────────┘     │
│  (to storage)  (get grain)    (to quern)    (process)   (get flour out)    │
│                                                                             │
│  ClayFormJob (clay → pottery)                                               │
│  ┌─────────┐    ┌────────┐    ┌─────────┐    ┌──────────┐                  │
│  │  goto   │───▶│takefrom│───▶│  goto   │───▶│ clayform │                  │
│  └─────────┘    └────────┘    └─────────┘    └──────────┘                  │
│  (to storage)  (get clay)    (to ground)   (form recipe)                   │
│                                                                             │
│  KnapJob (flint/stone → tool head)                                          │
│  ┌─────────┐    ┌────────┐    ┌─────────┐    ┌───────┐                     │
│  │  goto   │───▶│takefrom│───▶│  goto   │───▶│ knap  │                     │
│  └─────────┘    └────────┘    └─────────┘    └───────┘                     │
│  (to storage)  (get stone)   (to surface)  (knap recipe)                   │
│                                                                             │
│  PressJob (fruit → juice)                                                   │
│  ┌─────────┐    ┌───────┐                                                  │
│  │  goto   │───▶│ press │  (fruit already in press)                        │
│  └─────────┘    └───────┘                                                  │
│                                                                             │
│  SealBarrelJob (barrel → sealed for fermentation)                           │
│  ┌─────────┐    ┌───────┐                                                  │
│  │  goto   │───▶│ seal  │                                                  │
│  └─────────┘    └───────┘                                                  │
│                                                                             │
│  ═══════════════════════════════════════════════════════════════════════   │
│  CONSTRUCTION                                                               │
│  ═══════════════════════════════════════════════════════════════════════   │
│                                                                             │
│  BuildBlockJob (place single block from blueprint)                          │
│  ┌─────────┐    ┌────────┐    ┌─────────┐    ┌───────┐                     │
│  │  goto   │───▶│takefrom│───▶│  goto   │───▶│ place │                     │
│  └─────────┘    └────────┘    └─────────┘    └───────┘                     │
│  (to storage) (get material) (to build pos) (place block)                  │
│                                                                             │
│  DeconstructJob (remove block, store materials)                             │
│  ┌─────────┐    ┌───────┐    ┌────────┐    ┌─────────┐    ┌────────┐       │
│  │  goto   │───▶│ mine  │───▶│ pickup │───▶│  goto   │───▶│ putinto│       │
│  └─────────┘    └───────┘    └────────┘    └─────────┘    └────────┘       │
│                                                                             │
│  ═══════════════════════════════════════════════════════════════════════   │
│  UTILITY / MISC                                                             │
│  ═══════════════════════════════════════════════════════════════════════   │
│                                                                             │
│  IgniteFirepitJob                                                           │
│  ┌─────────┐    ┌────────┐                                                 │
│  │  goto   │───▶│ ignite │                                                 │
│  └─────────┘    └────────┘                                                 │
│                                                                             │
│  ActivateDoorJob / ActivateLeverJob                                         │
│  ┌─────────┐    ┌──────────┐                                               │
│  │  goto   │───▶│ activate │                                               │
│  └─────────┘    └──────────┘                                               │
│                                                                             │
│  IdleJob (wander or wait)                                                   │
│  ┌─────────┐                                                               │
│  │  goto   │  (random nearby position)                                     │
│  └─────────┘                                                               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Job Complexity Tiers

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         JOB COMPLEXITY TIERS                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  TIER 1: Simple (2 primitives) - Good starting points                       │
│  ─────────────────────────────────────────────────────                      │
│  • IgniteFirepit     goto → ignite                                          │
│  • ActivateDoor      goto → activate                                        │
│  • SealBarrel        goto → seal                                            │
│  • PressJob          goto → press                                           │
│  • Idle              goto (random)                                          │
│                                                                             │
│  TIER 2: Medium (3 primitives) - Core autonomous tasks                      │
│  ─────────────────────────────────────────────────────                      │
│  • HarvestCrop       goto → harvestcrop → pickup                            │
│  • HarvestBerry      goto → harvest → pickup                                │
│  • MineBlock         goto → mine → pickup                                   │
│  • ButcherAnimal     goto → butcher → loot                                  │
│  • BreakCarcass      goto → mine → pickup                                   │
│                                                                             │
│  TIER 3: Complex (4+ primitives) - Full logistics chains                    │
│  ─────────────────────────────────────────────────────                      │
│  • HaulGroundItem    goto → pickup → goto → putinto                         │
│  • HaulContainer     goto → takefrom → goto → putinto                       │
│  • BuildBlock        goto → takefrom → goto → place                         │
│  • Deconstruct       goto → mine → pickup → goto → putinto                  │
│  • ClayForm          goto → takefrom → goto → clayform                      │
│  • Knap              goto → takefrom → goto → knap                          │
│  • Grind             goto → takefrom → goto → grind → takefrom              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Animal Processing Flow

Clarification of loot vs butcher:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    ANIMAL PROCESSING FLOW                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Living Animal                                                              │
│       │                                                                     │
│       │ (kill - combat or killentity)                                       │
│       ▼                                                                     │
│  Dead Animal (Entity)  ◄── Harvestable=true                                 │
│       │                                                                     │
│       │ butcher (requires knife) → produces meat, hide, fat                 │
│       │                             items go to harvest inventory           │
│       ▼                                                                     │
│  Dead Animal (Entity)  ◄── Harvestable=false, still has items in inv        │
│       │                                                                     │
│       │ loot → transfers harvest inventory items to bot                     │
│       │        triggers carcass transformation                              │
│       ▼                                                                     │
│  Carcass (BLOCK!)      ◄── game:carcass-medium/small/etc                    │
│       │                                                                     │
│       │ mine (or break) → produces bones                                    │
│       ▼                                                                     │
│  Gone                                                                       │
│                                                                             │
│  ════════════════════════════════════════════════════════════════════════   │
│                                                                             │
│  FULL ANIMAL PROCESSING JOB:                                                │
│                                                                             │
│  ┌──────┐   ┌─────────┐   ┌──────┐   ┌──────┐   ┌────────┐   ┌────────┐    │
│  │ goto │──▶│ butcher │──▶│ loot │──▶│ mine │──▶│ pickup │──▶│ putinto│    │
│  └──────┘   └─────────┘   └──────┘   └──────┘   └────────┘   └────────┘    │
│  (to dead   (cut up,     (get meat  (break    (get bones)  (store all)    │
│   animal)   needs knife)  etc)      carcass)                               │
│                                                                             │
│  NOTE: loot is INLINE command, not an action - runs synchronously           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Sensing Requirements by Job

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SENSING REQUIREMENTS BY JOB                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Job Type          │ Needs to Sense                    │ Current Support    │
│  ──────────────────┼───────────────────────────────────┼─────────────────── │
│  HarvestCrop       │ Crop ripeness (block variant)     │ ❓ Unknown         │
│  HarvestBerry      │ Berry bush harvestable state      │ ❓ Unknown         │
│  MineBlock         │ Block type at position            │ ✅ /targets        │
│  ButcherAnimal     │ Dead entities nearby              │ ❓ Partial         │
│  HaulGroundItem    │ Dropped item entities             │ ✅ /state          │
│  HaulContainer     │ Container contents + space        │ ✅ /container-*    │
│  BuildBlock        │ Blueprint missing blocks          │ ✅ /verify         │
│  GrindJob          │ Quern has input, is empty         │ ❓ Need sensor     │
│  ClayFormJob       │ Clay forming surface empty        │ ❓ Need sensor     │
│  IgniteFirepit     │ Firepit is unlit                  │ ❓ Need sensor     │
│  SealBarrel        │ Barrel ready to seal              │ ❓ Need sensor     │
│                                                                             │
│  Legend: ✅ = Already have   ❓ = Need to add/verify                        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Implementation Recommendation

Given this mapping, recommended order for first autonomous jobs:

### 1. HaulGroundItem (First)

Why:
- **Sensors exist**: `/polis/state` already returns nearby items
- **Simple logic**: if (items on ground) && (storage has space) → haul
- **4 primitives** but well-tested ones (goto, pickup, goto, putinto)
- **Immediately useful**: cleans up after mining/harvesting
- **Visible feedback**: items disappear from ground, appear in chest

### 2. HarvestCrop (Second)

Once we verify crop ripeness sensing works.

### 3. ButcherAnimal (Third)

Combines: butcher → loot → mine carcass → pickup bones chain.

---

## Open Questions

1. What sensing capabilities do we currently have for crop ripeness?
2. Can `/state` detect dead entities vs living ones?
3. Do we need a unified "workstation state" sensor for quern/barrel/firepit?
