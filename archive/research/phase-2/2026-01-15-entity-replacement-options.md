# Entity Replacement Options (Playerbot -> Custom)

Date: 2026-01-15

Purpose
Document local evidence for replacing `survival:playerbot`, propose a minimal custom entity setup,
and list migration considerations without code changes.

Summary
- VSVillage uses vanilla `EntityVillager` with trading/dialog and a small inventory, which is a poor
  fit for Phase 2 inventory + job goals.
- A custom entity based on `EntityHumanoid` + `seraphinventory` aligns with the Phase 2 inventory
  research (hands + backpacks) and avoids trading/UI baggage.
- Minimal behavior set can be kept lean and compatible with ActivitySystem.

Evidence (local sources)
- VSVillage uses `EntityVillager` with behaviors: `villagerinventory`, `activitydriven`, `taskai`,
  `conversable`, `emotionstates`, `health`, `deaddecay`.
  - `docs/vsvillage/VSVillage/assets/vsvillage/entities/villager.json`
- `EntityVillager` derives from `EntityTradingHumanoid`, which pulls in trading + dialog systems and
  trader inventory.
  - `docs/vssurvivalmod/Systems/Trading/EntityTradingHumanoid.cs`
  - `docs/vssurvivalmod/Lore/Village/EntityVillager.cs`
- `villagerinventory` is `InventoryGeneric(6)` with hands in slots 0/1.
  - `docs/vssurvivalmod/Lore/Village/EntityDressedHumanoid.cs`
- `seraphinventory` (InventoryGear) is used by `EntityPlayerBot` and provides hands + backpacks.
  - `docs/vssurvivalmod/Entities/EntityPlayerBot.cs`
- Minimal `EntityAgent` entities with curated behaviors are common in other mods.
  - `docs/OutlawMod-src/mods/expandedaitasksloader/assets/game/entities/debug/test-dummy.json`
  - `docs/wolftaming/resources/assets/wolftaming/entities/land/dog-adult.json`

Custom Entity Setup (Recommended)

1) C# entity class (lean, humanoid)
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

2) ModSystem registration
```csharp
api.RegisterEntityClass("EntityPolisBot", typeof(EntityPolisBot));
```

3) Entity JSON (minimal behavior set)
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
      { "code": "health", "currenthealth": 20, "maxhealth": 20 },
      { "code": "deaddecay", "hoursToDecay": 96, "decayedBlock": "drycarcass-humanoid1" },
      { "code": "activitydriven", "activityCollectionPathByType": { "*": "polis-builder-npc:activities/working" } },
      { "code": "taskai", "aitasks": [] }
    ]
  }
}
```

Migration Suggestions (No Code Yet)
- Files that will need changes (code + docs):
  - `PolisBuilderNpcSystem.cs`: DefaultBotCode, spawn resolution fallback, BotRecord code defaults.
  - `PolisNetworkPackets.cs`: BotRecord.EntityCode (migration on load).
  - `README.md`, `docs/TESTING_HARNESS.md`, `docs/TESTING_HARNESS_TARGETS.md`: update spawn examples.
  - `tools/test-ui.html`: include `EntityPolisBot` in entity class filters.
- Update `DefaultBotCode` to `polis-builder-npc:polisbot`.
- On load, migrate `BotRecord.EntityCode` if it equals `survival:playerbot`.
  - If the old entity is loaded, allow both codes temporarily or respawn as new entity type.
- Consider a one-time "upgrade" command to replace existing bots in-place and preserve
  name/owner/last position.

Pathing Behavior vs Custom Pathing
- `activitydriven` provides the EntityActivitySystem, which can run actions that use
  `WaypointsTraverser` (same core pathing as the current `PolisGotoAction` flow).
- `taskai` uses `AiTaskManager` + per-task pathing (e.g., `AiTaskGotoEntity`), which is a
  different control loop than the current command-driven action pipeline.
- If we keep our current primitives/jobs, there is nothing to replace: the bot’s movement
  remains driven by `PolisGotoAction` and its `WaypointsTraverser`.
- If we ever want to switch to native task AI, we would implement custom `AiTask*` classes
  and let `EntityBehaviorTaskAI` drive them instead of `EntityActivitySystem`.

Open Questions
- Do we want to keep `health` + `deaddecay` configured or make them optional via a server config?
- Should `taskai` be removed entirely or kept empty for compatibility?
- Any need for `repulseagents` or a cheaper alternative (Outlaw uses LOD repulse)?

Implications for Phase 2
- `seraphinventory` aligns with planned pickup/drop/transfer flow.
- `EntityHumanoid` keeps `EntityAgent` base features (mounting, controls, AI activity system).
- Avoiding `EntityVillager` prevents trading/dialog side effects and limits inventory bloat.

Hunger Check (Local Mods)
- Searched vsvillage, wolftaming, and OutlawMod sources for `EntityBehaviorHunger` or hunger behaviors in entity JSON.
- Found only player-focused hunger references (wearables, player hunger speed modifiers), no NPC hunger behavior usage.
- No evidence of NPC hunger behaviors in these mods; assume custom entity will not have hunger unless we implement a system.

Engine Code Check (Local Decompile)
- Ran `ilspycmd -l c` on `VintagestoryLib.dll`, `Vintagestory.dll`, and `VintagestoryServer.dll` and searched for `Hunger` type names.
- No `Hunger`-named types surfaced in class lists.
- `strings` search for `hunger` in those DLLs returned no matches.
- This suggests hunger is not implemented as a generic entity behavior in engine-visible types, or the naming is not exposed.
- Additional term scan (`saturation`/`satiety`/`food`):
  - `ilspycmd -l c` only found `Packet_NutritionProperties` in `VintagestoryLib.dll`.
  - `strings` found `Saturation`, `FoodCategory`, `Satiety` terms, but no behavior types.
  - Decompiling `Packet_NutritionProperties` shows a simple packet with `FoodCategory`, `Saturation`, `Health`, `EatenStack`.
  - No explicit hunger or satiety entity behavior types surfaced.
