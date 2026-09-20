# Entity Type Decision: Replacing `survival:playerbot`

**Date:** 2026-01-13
**Context:** Phase 1 (Possession System)
**Decision Required:** Choose entity base class for polis-builder NPCs

## Background

Current implementation uses `survival:playerbot`, which research reveals is **not suitable for production use**:
- Primary purpose: Cinematic/video recording tool (not gameplay)
- Command-based control (not AI-driven)
- No built-in gameplay features (health, inventory, etc.)
- Minimal modding documentation
- Uncertain long-term support

**Key Finding:** VSVillage (reference mod, 11k+ downloads) uses `EntityVillager` (vanilla VS class), NOT playerbot.

---

## Option 1: EntityVillager (Proven, Feature-Rich)

### What It Is
- **Vanilla Vintage Story class** designed for humanoid NPC gameplay
- Used by successful mods: VSVillage, (NDL Villagers is closed source but likely similar)
- Supports dual AI architecture: `taskai` + `activitydriven`

### Technical Architecture

Based on vsvillage source at `docs/vsvillage/VSVillage/assets/vsvillage/entities/villager.json`:

```json
{
  "code": "polisbot",
  "class": "EntityVillager",
  "canClimb": true,
  "eyeHeight": 1.4,
  "hitboxSize": { "x": 0.5, "y": 1.75 },
  "deadHitboxSize": { "x": 0.75, "y": 0.5 },
  "client": {
    "renderer": "Shape",
    "shape": { "base": "game:entity/humanoid/villager-{sex}" },
    "behaviors": [
      { "code": "nametag", "showtagonlywhentargeted": true },
      { "code": "repulseagents" },
      { "code": "controlledphysics", "stepHeight": 1.01 },
      { "code": "interpolateposition" }
    ]
  },
  "server": {
    "behaviors": [
      { "code": "nametag" },
      { "code": "repulseagents" },
      { "code": "controlledphysics", "stepHeight": 1.01 },
      { "code": "health", "currenthealth": 20, "maxhealth": 20 },
      {
        "code": "emotionstates",
        "states": [
          { "code": "aggressiveondamage", "duration": 6, "chance": 0.6, "slot": 0, "priority": 2 },
          { "code": "fleeondamage", "duration": 10, "chance": 0.4, "slot": 0, "priority": 1, "whenHealthRelBelow": 0.3 }
        ]
      },
      {
        "code": "deaddecay",
        "hoursToDecay": 96,
        "decayedBlock": "drycarcass-humanoid1"
      },
      {
        "code": "activitydriven",
        "activityCollectionPathByType": {
          "*": "working-villager"
        }
      },
      {
        "code": "taskai",
        "aitasks": [
          {
            "code": "idle",
            "priority": 1.2,
            "minduration": 2500,
            "maxduration": 2500,
            "animation": "idle2"
          },
          {
            "code": "wander",
            "priority": 1.0,
            "movespeed": 0.01,
            "animation": "Walk",
            "wanderChance": 0.005,
            "maxDistanceToSpawn": 15
          },
          {
            "code": "lookaround",
            "priority": 0.5
          }
        ]
      }
    ]
  }
}
```

### Built-in Features

**Health System:**
- `EntityBehaviorHealth` with configurable max health
- Damage, death, healing all handled
- Death animations and corpse decay

**Emotion States:**
- `EntityBehaviorEmotionStates` for reactive behaviors
- `aggressiveondamage`: Can attack player if hit (configurable)
- `fleeondamage`: Flee when low health
- Supports custom emotion states

**Activity-Driven AI:**
- `EntityBehaviorActivityDriven` - **This is what we're already using via EntityActivitySystem**
- Points to activity collection JSON (we'd create our own)
- Works alongside taskai (priority-based override)

**Task AI Fallback:**
- `EntityBehaviorTaskAI` for autonomous behaviors
- Lower priority than activitydriven
- Provides idle/wander when not commanded
- Can be minimal or disabled entirely

**Physical Behaviors:**
- `controlledphysics`: Handles movement, collisions, gravity
- `repulseagents`: Prevents entity stacking
- `interpolateposition`: Smooth client rendering
- Climbing support (`canClimb: true`)

**Visual Features:**
- Uses vanilla humanoid shape (male/female variants)
- Full animation support (walk, run, sit, sleep, work, combat)
- Nametag support
- Outfit/clothing system (can be customized or stripped)

### Advantages

1. **Purpose-Built for Gameplay:**
   - Designed for long-running, autonomous NPCs
   - Stable across VS versions (vanilla class)
   - Well-tested by VSVillage community

2. **Aligns with Phase 2+ Vision:**
   - Already uses `activitydriven` (EntityActivitySystem)
   - Task system integration proven by VSVillage
   - Built-in idle behaviors (wander, look around)

3. **Reduces Future Work:**
   - Health system (Phase 5+): Already implemented
   - Death/respawn (Phase 5+): Already implemented
   - Combat (Phase 5+): Emotion states ready
   - Animations (Phase 4+): Rich set included

4. **Ecosystem Compatibility:**
   - Other survival mods expect villager-type entities
   - Hunger, temperature, needs systems will work
   - Compatible with furniture (sitting, sleeping)

5. **Possession System:**
   - Still uses `EntityAgent` base class
   - IMountable/IMountableSeat should work identically
   - Same control routing, camera placement

### Disadvantages

1. **Migration Cost:**
   - Need to create new entity asset JSON
   - Update `DefaultBotCode` constant
   - Test all existing commands (goto, activate, etc.)
   - Update spawn logic, persistence (entityCode changes)
   - Regression test all interactions

2. **Built-in Behaviors May Interfere:**
   - `taskai` wander/idle might conflict with commands
   - Need to tune priorities or disable unwanted tasks
   - Emotion states could trigger unwanted aggression
   - May need to override or disable some behaviors

3. **Model/Appearance:**
   - Uses vanilla villager model by default
   - May want custom appearance (doable but more work)
   - Outfit system is complex (can be simplified or removed)

4. **Less Direct Control:**
   - Some behaviors are "baked in" to EntityVillager class
   - May need to work around vanilla assumptions
   - Less of a "blank slate" than custom EntityAgent

### Migration Steps

**Phase 1: Entity Definition**
1. Create `assets/polis-builder-npc/entities/polisbot.json`
2. Base on vsvillage villager.json, strip profession/dialogue
3. Keep: activitydriven, health, emotionstates (simplified), nametag
4. Remove/simplify: outfit system, voice sounds, trade support
5. Test entity spawns and moves correctly

**Phase 2: Code Updates**
1. Change `DefaultBotCode` from `"survival:playerbot"` to `"polis-builder-npc:polisbot"`
2. Update spawn command to use new code
3. Test persistence (BotRecord.EntityCode field)
4. Verify all actions still work (goto, activate, break, place, etc.)

**Phase 3: Possession Testing**
1. Test possession mount/dismount
2. Verify control routing (should be identical)
3. Check camera placement (eyeHeight should match)
4. Test player hiding (RenderTransform)

**Phase 4: Polish**
1. Disable unwanted taskai behaviors (or reduce priority)
2. Tune emotion state triggers (or disable if not wanted yet)
3. Simplify appearance if desired
4. Update documentation (TECHNICAL.md, AGENTS.md)

**Estimated Effort:** 4-8 hours (mostly testing)

### Open Questions

**Q1: Does IMountable work with EntityVillager?**
- **Why it matters:** Core possession mechanic depends on it
- **How to test:** Spawn villager, try player.TryMount(), check seat creation
- **Fallback:** If not, may need custom EntityVillagerPossessable subclass

**Q2: How to disable/tune default taskai behaviors?**
- **Why it matters:** Don't want wander/idle interfering with commands
- **Options explored:**
  - Set very low priorities (< 1.0)
  - Remove aitasks array entirely
  - Use `EntityActivitySystem.PauseAutoSelection(true)` (already doing this)
- **Need to test:** Does PauseAutoSelection block taskai as well as activity auto-selection?

**Q3: Will emotion states cause unwanted aggression?**
- **Why it matters:** Bot should not attack player unless explicitly commanded (Phase 5+)
- **Options:**
  - Remove emotion states entirely for now
  - Set `aggressiveondamage` chance to 0.0
  - Remove meleeattack/seekentity tasks
- **Recommended:** Remove emotion states until Phase 5

**Q4: Can we use custom player model instead of villager model?**
- **Why it matters:** May want different appearance for "robots" vs "villagers"
- **How to test:** Change `shape.base` to point to custom model or player model
- **Research needed:** Is there a generic humanoid shape we can use?

**Q5: Does EntityVillager have special inventory behavior?**
- **Observed:** VSVillage uses `villagerinventory` behavior
- **Unknown:** Is this required? Can we use standard inventory?
- **Need to check:** What does `villagerinventory` do vs vanilla inventory behavior?
- **Test:** Try removing it, see if pickup/drop/equip still work

**Q6: Will health/death system work with our persistence?**
- **Why it matters:** Shadow Registry tracks entity ID; if entity dies and respawns, ID changes
- **Current behavior:** OnEntityDespawn with Death reason removes from registry
- **Phase 5 requirement:** Need bot to respawn at TownCenter after death
- **Decision needed:** Keep current death=permanent, or implement respawn now?

**Q7: Performance impact of built-in behaviors?**
- **Concern:** Extra behaviors (health, emotions, taskai) have tick cost
- **Unknown:** How much overhead vs minimal EntityAgent?
- **Target:** 50 bots, <2ms AI per frame
- **Need to test:** Profile 50 EntityVillager bots vs 50 playerbots

**Q8: Compatibility with existing bot registry?**
- **Issue:** BotRecord stores EntityCode string
- **Migration path:** Change "survival:playerbot" → "polis-builder-npc:polisbot"
- **Backward compat:** Existing saves have playerbot entityCode
- **Solution needed:** Migration code on load? Or force re-spawn?

---

## Option 2: Custom EntityAgent Subclass (Maximum Control)

### What It Is
- Create new C# class: `EntityPolisBot : EntityAgent`
- Register as entity class in mod startup
- Define entity asset JSON pointing to custom class
- Blank slate: Implement only what you need

### Example from Other Mods

**Sam's Humanoid Creatures** (reference):
- Uses player model for entities
- Simple behavior similar to vanilla animals
- Custom EntityAgent subclass for special logic

**PPRP NPCs** (reference):
- Custom NPCs with dialogue
- Uses entity class system
- Added custom behaviors

### Technical Architecture

**C# Class Structure:**
```csharp
public class EntityPolisBot : EntityAgent
{
    public override void Initialize(EntityProperties properties, ICoreAPI api, long InChunkIndex3d)
    {
        base.Initialize(properties, api, InChunkIndex3d);

        // Custom initialization
        // Add behaviors programmatically if needed
    }

    // Override methods as needed:
    // - OnInteract
    // - OnGameTick
    // - GetInfoText
    // etc.
}
```

**Entity Asset JSON:**
```json
{
  "code": "polisbot",
  "class": "EntityPolisBot",
  "canClimb": true,
  "eyeHeight": 1.4,
  "hitboxSize": { "x": 0.5, "y": 1.75 },
  "client": {
    "renderer": "Shape",
    "shape": { "base": "game:entity/humanoid/player" },
    "behaviors": [
      { "code": "controlledphysics", "stepHeight": 1.01 },
      { "code": "interpolateposition" }
    ]
  },
  "server": {
    "behaviors": [
      { "code": "controlledphysics", "stepHeight": 1.01 }
      // Add only behaviors we want
    ]
  }
}
```

**Registration:**
```csharp
public override void Start(ICoreAPI api)
{
    api.RegisterEntityClass("EntityPolisBot", typeof(EntityPolisBot));
}
```

### Advantages

1. **Maximum Control:**
   - No unwanted behaviors
   - No assumptions about NPC type
   - Full control over lifecycle

2. **Clean Architecture:**
   - Purpose-built for polis-builder
   - No VSVillage baggage
   - Minimal dependencies

3. **Performance:**
   - Only pay for features you use
   - No hidden tick costs
   - Optimize exactly for your use case

4. **Flexibility:**
   - Can add custom fields/properties
   - Override any EntityAgent behavior
   - Implement custom logic in C#

5. **Independence:**
   - Not tied to vanilla NPC expectations
   - Can diverge from "villager" concept
   - Future-proof against vanilla changes

### Disadvantages

1. **High Implementation Cost:**
   - Must implement health system from scratch
   - Death/respawn logic custom
   - Damage handling custom
   - Inventory management custom
   - All animations must be defined

2. **Reinventing the Wheel:**
   - Health system: ~200 lines of code
   - Emotion states: ~100 lines
   - Death decay: ~50 lines
   - Combat: ~300 lines (Phase 5+)
   - Total: ~650+ lines vs free with EntityVillager

3. **Testing Burden:**
   - Every system needs testing
   - Edge cases to discover
   - Balance/tuning required
   - More surface area for bugs

4. **Less Ecosystem Fit:**
   - Other mods expect standard entity types
   - May not work with hunger/temp mods
   - Custom integration required

5. **Delayed Features:**
   - Can't leverage vanilla systems
   - Phase 5+ features need custom impl
   - More work before "feature complete"

### When to Choose This Option

**Choose custom EntityAgent if:**
- You want complete control over every behavior
- You're building a very unique NPC type (e.g., robots, not humanoids)
- You need to optimize heavily (100+ bots)
- You have time to implement all systems
- You don't need vanilla ecosystem integration

**Don't choose if:**
- You want to ship faster
- You need standard NPC features (health, death, etc.)
- You want to follow proven patterns (VSVillage)
- Your NPCs are "standard humanoids"

### Implementation Steps

**Phase 1: Minimal Entity**
1. Create `EntityPolisBot.cs` class
2. Register class in ModSystem.Start()
3. Create minimal entity JSON
4. Test spawn, movement

**Phase 2: Core Behaviors**
1. Add controlledphysics behavior
2. Implement possession support (IMountable in subclass?)
3. Test goto, stop commands

**Phase 3: Health System (if needed)**
1. Implement IHP interface
2. Add damage handling
3. Add death logic
4. Test combat/damage

**Phase 4: Extended Features**
1. Inventory management
2. Animation system
3. Interaction handlers
4. Polish and tune

**Estimated Effort:** 20-40 hours (substantial)

### Open Questions

**Q1: Does EntityAgent have IMountable support built-in?**
- **Why it matters:** May need to implement mounting from scratch
- **How to check:** Test player.TryMount() on vanilla EntityAgent
- **Research:** Check if EntityAgent has GetMountable() or similar

**Q2: What behaviors are required vs optional?**
- **Unknown:** Can entity exist without controlledphysics?
- **Unknown:** Is interpolateposition required for smooth rendering?
- **Need to test:** Minimal viable behavior set

**Q3: How to implement health without EntityBehaviorHealth?**
- **Option A:** Implement IHP interface directly on EntityPolisBot
- **Option B:** Create custom EntityBehaviorPolisBotHealth
- **Option C:** Don't have health until Phase 5
- **Recommendation:** Option C (defer until needed)

**Q4: Can we reuse vanilla animations?**
- **Unknown:** Do vanilla humanoid animations work with custom entity class?
- **Test needed:** Set shape to `game:entity/humanoid/player`, verify walk/run anims
- **Fallback:** May need to copy animation JSON from vanilla

**Q5: Inventory system - custom or use vanilla InventoryCharacter?**
- **Unknown:** Does EntityAgent have inventory by default?
- **Check:** Does base.Initialize() set up inventory?
- **Research:** Look at vanilla EntityAgent source

**Q6: How to handle pathfinding with custom entity?**
- **Current:** Uses WaypointsTraverser, works with EntityAgent
- **Question:** Does it depend on entity class or just EntityAgent base?
- **Test:** Spawn custom entity, try goto command

**Q7: Performance baseline - what's the tick cost of bare EntityAgent?**
- **Need to measure:** Spawn 50 minimal EntityPolisBots, profile OnTick
- **Compare to:** 50 EntityVillagers, 50 playerbots
- **Target:** <0.05ms per entity per tick

**Q8: Can we add behaviors programmatically vs JSON?**
- **Why:** Might want dynamic behavior based on bot state
- **How:** `entity.GetBehavior<T>()`, `entity.AddBehavior()`?
- **Research:** Check EntityAgent API for runtime behavior management

---

## Decision Matrix

| Criteria | EntityVillager | Custom EntityAgent |
|----------|----------------|-------------------|
| **Implementation Time** | 4-8 hours | 20-40 hours |
| **Feature Completeness** | High (built-in) | Low (DIY) |
| **Control/Flexibility** | Medium | Maximum |
| **Ecosystem Fit** | Excellent | Poor |
| **Performance** | Good (some overhead) | Optimal (minimal) |
| **Risk** | Low (proven) | Medium (untested) |
| **Phase 2 Synergy** | Excellent (activitydriven) | Good (manual impl) |
| **Phase 5+ Readiness** | Excellent (health, death) | Poor (must build) |
| **Maintainability** | Good (vanilla class) | Good (our code) |

---

## Local Mod Evidence (No btca)

### VSVillage (local copy)
- Entity class is **vanilla** `EntityVillager` (not playerbot).
  - File: `docs/vsvillage/VSVillage/assets/vsvillage/entities/villager.json` (`"class": "EntityVillager"`).
- Uses **villagerinventory** + **activitydriven** + **taskai** + **conversable** + **emotionstates** + **health** + **deaddecay**.
  - File: `docs/vsvillage/VSVillage/assets/vsvillage/entities/villager.json` (server behaviors).
- `EntityVillager` derives from `EntityTradingHumanoid`, which pulls in trading/dialogue systems and trader inventory.
  - Files: `docs/vssurvivalmod/Lore/Village/EntityVillager.cs`, `docs/vssurvivalmod/Systems/Trading/EntityTradingHumanoid.cs`.
- Inventory for villager base is **small**: `EntityBehaviorVillagerInv` uses `InventoryGeneric(6)`, and hands are slots 0/1.
  - File: `docs/vssurvivalmod/Lore/Village/EntityDressedHumanoid.cs`.

**Implication:** VSVillage’s path favors vanilla villagers with trading + dialog baggage and a 6-slot inventory. This conflicts with Phase 2 inventory + bags goals.

### OutlawMod / ExpandedAI (local copy)
- Shows a minimal `EntityAgent` with a curated behavior set (physics, interpolation, optional taskai/emotionstates).
  - File: `docs/OutlawMod-src/mods/expandedaitasksloader/assets/game/entities/debug/test-dummy.json`.

### Wolftaming (local copy)
- Uses `EntityAgent` with explicit behaviors and command systems; no playerbot dependency.
  - File: `docs/wolftaming/resources/assets/wolftaming/entities/land/dog-adult.json`.

---

## Custom Entity Setup (Lean Option A)

If we switch to our own entity class (recommended for Phase 2 alignment), this is the **minimal setup** that still supports movement, inventory, and possession.

### 1) C# entity class
Prefer subclassing **EntityHumanoid** (still an EntityAgent, but with humanoid assumptions) unless you want the absolute minimum surface area.

```csharp
public class EntityPolisBot : EntityHumanoid
{
    EntityBehaviorSeraphInventory invbh;

    public override ItemSlot RightHandItemSlot => invbh?.Inventory[15];
    public override ItemSlot LeftHandItemSlot => invbh?.Inventory[16];

    public override void Initialize(EntityProperties properties, ICoreAPI api, long chunkindex3d)
    {
        base.Initialize(properties, api, chunkindex3d);
        invbh = GetBehavior<EntityBehaviorSeraphInventory>();
    }

    public override void OnEntitySpawn()
    {
        base.OnEntitySpawn();
        if (World.Side == EnumAppSide.Client)
        {
            (Properties.Client.Renderer as EntityShapeRenderer).DoRenderHeldItem = true;
        }
    }
}
```

**Why:** `EntityBehaviorSeraphInventory` provides the InventoryGear model (hands 15/16, backpacks 17/18) which aligns with Phase 2 inventory research. `EntityPlayerBot` uses the same pattern for held item rendering.

### 2) ModSystem registration
```csharp
api.RegisterEntityClass("EntityPolisBot", typeof(EntityPolisBot));
```

### 3) Entity JSON (minimal behavior set)
```json
{
  "code": "polisbot",
  "class": "EntityPolisBot",
  "canClimb": true,
  "eyeHeight": 1.4,
  "hitboxSize": { "x": 0.5, "y": 1.75 },
  "deadHitboxSize": { "x": 0.75, "y": 0.5 },
  "client": {
    "renderer": "Shape",
    "shape": { "base": "game:entity/humanoid/player" },
    "behaviors": [
      { "code": "seraphinventory" },
      { "code": "nametag", "showtagonlywhentargeted": true },
      { "code": "controlledphysics", "stepHeight": 1.01 },
      { "code": "interpolateposition" }
    ]
  },
  "server": {
    "behaviors": [
      { "code": "seraphinventory" },
      { "code": "nametag", "showtagonlywhentargeted": true },
      { "code": "controlledphysics", "stepHeight": 1.01 },
      { "code": "activitydriven", "activityCollectionPathByType": { "*": "polis-builder-npc:activities/working" } },
      { "code": "taskai", "aitasks": [] }
    ]
  }
}
```

**Notes:**
- `seraphinventory` requires survival mod behavior registration (already in vanilla survival). It gives a better inventory than villagerinv (6 slots).
- `activitydriven` enables EntityActivitySystem; `taskai` can be empty or omitted if you fully drive jobs yourself.
- `repulseagents` is optional but can be expensive (see Outlaw’s custom LOD repulse). Avoid unless interpenetration becomes a problem.
- `health`/`deaddecay` can be added later once Phase 2 is stable.

### 4) Possession compatibility
`EntityAgent` (and thus EntityHumanoid) already has `TryMount`/`TryUnmount` per vsapi docs, so IMountable should still work with a custom humanoid entity.

### 5) Migration considerations
- Update `DefaultBotCode` to `polis-builder-npc:polisbot`.
- Add migration logic for existing `BotRecord.EntityCode` values if you want to keep old bots.
- Re-test held-item rendering and inventory sync (MarkDirty + `storeInv()` pattern from `EquipAction`/`UnequipAction`).

---

## Recommendation Criteria

**Use EntityVillager if:**
- ✅ You want to ship Phase 1 soon (within weeks)
- ✅ You value proven, stable foundation
- ✅ You want built-in health, death, emotions for Phase 5+
- ✅ You're okay with some "extra" features you might not use
- ✅ You want ecosystem compatibility (hunger, temp mods)

**Use Custom EntityAgent if:**
- ✅ You have 20+ hours to invest in entity system
- ✅ You need absolute control over every behavior
- ✅ Your NPCs are very different from "villagers"
- ✅ Performance is critical (100+ bots)
- ✅ You're willing to implement health/death/combat from scratch

---

## Next Steps for Decision Maker

1. **Test IMountable with EntityVillager:**
   - Spawn a vanilla villager or vsvillage villager
   - Try `player.TryMount(villagerEntity)` in a test command
   - Verify mounting works (critical for possession)
   - **If this fails, custom EntityAgent may be forced**

2. **Profile EntityVillager performance:**
   - Spawn 50 vsvillage villagers
   - Measure tick time with VS profiler or logs
   - Compare to project performance budget (2ms/frame target)
   - **If too slow, consider custom EntityAgent**

3. **Review Phase 2 requirements:**
   - Does `activitydriven` behavior give us what we need?
   - Look at vsvillage's activity JSON structure
   - Confirm it matches planned task system architecture
   - **If incompatible, custom EntityAgent may be better**

4. **Check user/stakeholder preference:**
   - Do bots need to look like "villagers" or more generic?
   - Are health/combat/death needed for MVP (Phase 1-2)?
   - Is ecosystem mod compatibility important?
   - **Answers inform which option aligns with vision**

5. **Prototype migration:**
   - If leaning EntityVillager: Create polisbot.json, test spawn
   - If leaning custom: Create EntityPolisBot.cs, test basic functionality
   - **30-60 min prototype to de-risk**

6. **Make decision and document:**
   - Update TECHNICAL.md with chosen entity type
   - Update ROADMAP.md with any Phase 1 adjustments
   - Document decision rationale in this journal entry
   - Create migration task branch

---

## References

**Research Sources:**
- [Bot System - Vintage Story Wiki](https://wiki.vintagestory.at/Bot_System)
- [VS Village - Vintage Story Mod DB](https://mods.vintagestory.at/vsvillage)
- [VS Village GitHub](https://github.com/G3rste/vsvillage)
- [Modding:Basic Entity - Vintage Story Wiki](https://wiki.vintagestory.at/Modding:Basic_Entity)
- [Modding:Entity Behaviors - Vintage Story Wiki](https://wiki.vintagestory.at/Modding:Entity_Behaviors)
- [Sam's humanoid creatures](https://mods.vintagestory.at/show/mod/7378)
- [PPRP NPCs](https://mods.vintagestory.at/show/mod/27138)

**Local Code References:**
- `docs/vsvillage/VSVillage/assets/vsvillage/entities/villager.json` - EntityVillager example
- `docs/vsvillage/VSVillage/src/Entity/Behavior/BehaviorVillager.cs` - Custom behavior example
- Current implementation: `PolisBuilderNpcSystem.cs` lines 22-23 (DefaultBotCode)

**Related Documentation:**
- `docs/VISION.md` - Phase roadmap, possession system design
- `docs/TECHNICAL.md` - Current architecture, bot tracking
- `docs/KNOWN_ISSUES.md` - Current limitations

---

**Status:** Decision pending
**Blocking:** Phase 1 completion, Phase 2 planning
**Priority:** High (architectural decision)
