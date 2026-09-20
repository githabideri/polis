# Implementation Plan: `PolisButcherEntityAction`

**Status:** Implemented (2026-01-17)
**Date:** 2026-01-15
**Related:** Phase 2 action primitives

## Overview

Butcher dead entities (animals, creatures) using a knife to collect meat, hide, fat, and other drops. Uses the vanilla `EntityBehaviorHarvestable` system.

The key insight from research: we can directly call `behavior.SetHarvested(player, multiplier)` instead of simulating the full knife interaction. This populates the harvest inventory which we then transfer to the bot.

---

## 1. File Location

**Path:** `PolisBuilderNpcSystem.cs`

Add after `PolisHarvestBlockAction` to keep harvesting actions grouped.

---

## 2. Class Structure

```csharp
public class PolisButcherEntityAction : EntityActionBase
{
    // === Constructor Parameters ===
    private readonly long targetEntityId;
    private readonly IServerPlayer player;          // For SetHarvested context
    private readonly float maxRange;
    private readonly bool autoCollectDrops;         // Transfer harvest inv to bot
    private readonly float dropQuantityMultiplier;

    // === Runtime State ===
    private Entity targetEntity;
    private EntityBehaviorHarvestable harvestBehavior;
    private bool validated;

    // === Constants ===
    private const float DEFAULT_MAX_RANGE = 4.5f;
    private const float DEFAULT_DROP_MULTIPLIER = 1.0f;
}
```

---

## 3. Constructor

```csharp
public PolisButcherEntityAction(
    EntityActivitySystem vas,
    long targetEntityId,
    IServerPlayer player,
    float maxRange = DEFAULT_MAX_RANGE,
    bool autoCollectDrops = true,
    float dropQuantityMultiplier = DEFAULT_DROP_MULTIPLIER
) : base(vas)
{
    this.targetEntityId = targetEntityId;
    this.player = player;
    this.maxRange = maxRange;
    this.autoCollectDrops = autoCollectDrops;
    this.dropQuantityMultiplier = dropQuantityMultiplier;
}
```

---

## 4. Start() Method - Validation, Butcher, Transfer

This action is instant (like crop harvesting) - SetHarvested does the work immediately.

```csharp
public override void Start()
{
    var world = vas.Entity.Api.World;
    var agent = vas.Entity as EntityAgent;

    // --- Find Target Entity ---
    targetEntity = world.GetEntityById(targetEntityId);
    if (targetEntity == null)
    {
        Fail($"Entity {targetEntityId} not found");
        return;
    }

    // --- Range Check ---
    double dist = vas.Entity.ServerPos.DistanceTo(targetEntity.ServerPos.XYZ);
    if (dist > maxRange)
    {
        Fail($"Target too far: {dist:F1} > {maxRange}");
        return;
    }

    // --- Get Harvestable Behavior ---
    harvestBehavior = targetEntity.GetBehavior<EntityBehaviorHarvestable>();
    if (harvestBehavior == null)
    {
        Fail($"Entity {targetEntity.Code} is not harvestable");
        return;
    }

    // --- Check if Already Harvested ---
    if (harvestBehavior.IsHarvested)
    {
        Fail("Entity already harvested");
        return;
    }

    // --- Check if Harvestable (dead and not harvested) ---
    if (!harvestBehavior.Harvestable)
    {
        // Harvestable = entity.Alive == false && !IsHarvested
        if (targetEntity.Alive)
        {
            Fail("Entity is still alive - kill it first");
        }
        else
        {
            Fail("Entity not harvestable (unknown reason)");
        }
        return;
    }

    // --- Validate Knife Equipped ---
    var invbh = agent.GetBehavior<EntityBehaviorSeraphInventory>();
    if (invbh == null)
    {
        Fail("Bot has no inventory behavior");
        return;
    }

    var toolSlot = invbh.Inventory[15]; // Right hand
    if (toolSlot?.Itemstack?.Collectible?.Tool != EnumTool.Knife)
    {
        Fail("Knife required in right hand for butchering");
        return;
    }

    // --- Perform Butchering ---
    LogDebug($"Butchering {targetEntity.Code} (id={targetEntityId})");
    harvestBehavior.SetHarvested(player, dropQuantityMultiplier);

    // --- Transfer Harvest Inventory to Bot ---
    if (autoCollectDrops)
    {
        TransferHarvestInventory(agent);
    }

    Succeed();
}

private void TransferHarvestInventory(EntityAgent agent)
{
    // Read harvest inventory from entity attributes
    var tree = targetEntity.WatchedAttributes["harvestableInv"] as ITreeAttribute;
    if (tree == null)
    {
        LogDebug("No harvest inventory found after butchering");
        return;
    }

    // Determine slot count
    int slotCount = tree.GetInt("qslots", 4);

    // Create inventory to deserialize into
    var harvestInv = new InventoryGeneric(slotCount, "harvest-temp", null);
    harvestInv.FromTreeAttributes(tree);

    // Transfer each slot to bot
    int transferred = 0;
    for (int i = 0; i < harvestInv.Count; i++)
    {
        var slot = harvestInv[i];
        if (slot?.Itemstack == null) continue;

        // Try to give to bot inventory
        ItemStack stack = slot.Itemstack.Clone();
        bool success = PolisInventoryHelpers.TryInsertIntoBotInventory(agent, stack);

        if (success)
        {
            transferred++;
            LogDebug($"Transferred: {stack.StackSize}x {stack.Collectible.Code}");
        }
        else
        {
            LogDebug($"Could not transfer: {stack.StackSize}x {stack.Collectible.Code} (inventory full?)");
            // Could spawn as EntityItem as fallback
        }
    }

    // Persist bot inventory
    PolisInventoryHelpers.StoreSeraphInventory(agent);

    LogDebug($"Butchering complete: transferred {transferred} item stacks");
}
```

---

## 5. No OnTick Needed

Butchering is instant via `SetHarvested()`. No progress loop required.

```csharp
public override bool OnTick(float dt)
{
    // Instant action - nothing to tick
    return false;
}
```

---

## 6. Command Integration

Command: `/polis butcher <entityId> [autocollect]`

```csharp
private void ExecuteButcherCommand(IServerPlayer player, BotState botState, long targetEntityId, bool autoCollect = true)
{
    string ownerUid = botState.Entity.WatchedAttributes.GetString("polisOwnerUid");
    IServerPlayer ownerPlayer = sapi.World.PlayerByUid(ownerUid) as IServerPlayer ?? player;

    var action = new PolisButcherEntityAction(
        botState.Activity,
        targetEntityId,
        ownerPlayer,
        maxRange: 4.5f,
        autoCollectDrops: autoCollect
    );

    StartSingleAction(botState, action);
}
```

---

## 7. HTTP API Integration

Add to `/polis/command` handler:

```csharp
case "butcher":
    // butcher <entityId> [autocollect]
    if (args.Length < 1) return BadRequest("butcher requires entityId");
    long butcherTargetId = long.Parse(args[0]);
    bool autoCollect = args.Length < 2 || args[1].ToLower() != "false";
    ExecuteButcherCommand(contextPlayer, botState, butcherTargetId, autoCollect);
    return Ok($"Butchering entity {butcherTargetId}");
```

---

## 8. Alternative: Butcher Nearest Dead Entity

Convenience command to find and butcher the nearest harvestable corpse:

```csharp
case "butchernearest":
    // Find nearest dead, unbutchered entity
    var nearestCorpse = FindNearestHarvestableCorpse(botState.Entity, 10f);
    if (nearestCorpse == null)
    {
        return NotFound("No harvestable corpse nearby");
    }
    ExecuteButcherCommand(contextPlayer, botState, nearestCorpse.EntityId, true);
    return Ok($"Butchering nearest corpse: {nearestCorpse.Code} (id={nearestCorpse.EntityId})");

private Entity FindNearestHarvestableCorpse(Entity bot, float radius)
{
    var world = bot.Api.World;
    var entities = world.GetEntitiesAround(bot.ServerPos.XYZ, radius, radius,
        e => !e.Alive && e.GetBehavior<EntityBehaviorHarvestable>()?.Harvestable == true);

    return entities
        .OrderBy(e => e.ServerPos.DistanceTo(bot.ServerPos))
        .FirstOrDefault();
}
```

---

## 9. Edge Cases & Error Handling

| Scenario | Handling |
|----------|----------|
| Entity not found | Fail with message |
| Entity still alive | Fail with "kill it first" message |
| Entity already harvested | Fail with message |
| No harvestable behavior | Fail with message |
| No knife equipped | Fail with message |
| Harvest inventory empty | Log warning, still succeed |
| Bot inventory full | Log warning, items lost (or spawn as EntityItem) |

---

## 10. Design Notes

### SetHarvested vs Manual Interaction

We call `SetHarvested()` directly instead of simulating knife interaction because:
1. It's the clean public API
2. It handles all drop calculations (weight, death cause modifiers)
3. It properly marks the entity as harvested
4. No timing simulation needed

### Drop Quantity Multipliers

`SetHarvested` accepts a `dropQuantityMultiplier`:
- Default: 1.0
- Could be modified by bot skills/traits in future
- Vanilla applies additional modifiers for death cause (fall = 0.5, non-player = 0.4)

### Harvest Inventory Structure

After `SetHarvested`, drops are in `entity.WatchedAttributes["harvestableInv"]`:
- TreeAttribute with serialized InventoryGeneric
- `qslots` key for slot count
- Slots contain meat, hide, fat, bones, etc.

### Entity Lifecycle

After butchering, the corpse remains but is marked harvested. The entity will eventually despawn naturally (corpse decay).

---

## 11. Future Enhancements

- [ ] Timed butchering (simulate knife hold time for realism)
- [ ] Tool durability damage
- [ ] Skill-based drop multiplier
- [ ] Auto-butcher after kill (combat integration)
- [ ] Spawn overflow items as EntityItem instead of losing them

---

## 12. Testing Checklist

```bash
# Setup: Kill an animal (chicken, pig, etc.) near the bot

# Give bot a knife (note: format is knife-{type}-{material})
curl -X POST http://localhost:8585/polis/command \
  -d '{"cmd":"give","args":["game:knife-generic-copper"]}'

# Find dead entity ID via /polis/targets or in-game
# Or use butchernearest

# Test butcher
curl -X POST http://localhost:8585/polis/command \
  -d '{"cmd":"butcher","args":["12345"]}'
curl http://localhost:8585/polis/state  # Check inventory for meat/hide

# Test cases:
# 1. Butcher dead chicken (should get poultry, feathers)
# 2. Butcher dead pig (should get pork, fat, hide)
# 3. Butcher without knife (should fail)
# 4. Butcher alive entity (should fail)
# 5. Butcher already-harvested corpse (should fail)
# 6. Butchernearest with no corpses (should fail)
```

---

## 13. Dependencies

Requires:
- `EntityBehaviorHarvestable` class (from vsessentialsmod)
- `SetHarvested(IPlayer, float)` method
- `Harvestable` and `IsHarvested` properties
- `PolisInventoryHelpers.TryInsertIntoBotInventory()`
- `InventoryGeneric.FromTreeAttributes()`
