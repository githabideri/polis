# Implementation Plan: `PolisHarvestBlockAction`

**Status:** Ready for implementation
**Date:** 2026-01-15
**Related:** Phase 2 action primitives

## Overview

Harvest blocks with `BlockBehaviorHarvestable` (berry bushes, resin logs, wild crops, etc.) by simulating timed right-click interaction.

Unlike instant `BreakBlock`, harvestable blocks use a timed interaction that:
1. Swaps the block to a harvested variant (e.g., ripe bush → empty bush)
2. Drops items via `harvestedStacks`
3. Allows regrowth (block isn't destroyed)

---

## 1. File Location

**Path:** `PolisBuilderNpcSystem.cs`

Add after `PolisHarvestCropAction` to keep harvesting actions grouped.

---

## 2. Class Structure

```csharp
public class PolisHarvestBlockAction : EntityActionBase
{
    // === Constructor Parameters ===
    private readonly BlockPos targetPos;
    private readonly IServerPlayer player;          // For interaction context
    private readonly float maxRange;
    private readonly bool autoCollectDrops;
    private readonly float collectRadius;

    // === Runtime State ===
    private Block block;
    private BlockBehaviorHarvestable harvestBehavior;
    private float harvestTime;                      // Total time needed
    private float elapsedTime;                      // Progress
    private BlockSelection blockSel;                // For interaction calls
    private bool interactionStarted;
    private bool validated;

    // === Constants ===
    private const float DEFAULT_MAX_RANGE = 4.5f;
    private const float DEFAULT_COLLECT_RADIUS = 3f;
    private const float DEFAULT_HARVEST_TIME = 1.0f; // Fallback if behavior has 0
}
```

---

## 3. Constructor

```csharp
public PolisHarvestBlockAction(
    EntityActivitySystem vas,
    BlockPos targetPos,
    IServerPlayer player,
    float maxRange = DEFAULT_MAX_RANGE,
    bool autoCollectDrops = false,
    float collectRadius = DEFAULT_COLLECT_RADIUS
) : base(vas)
{
    this.targetPos = targetPos;
    this.player = player;
    this.maxRange = maxRange;
    this.autoCollectDrops = autoCollectDrops;
    this.collectRadius = collectRadius;
}
```

---

## 4. Start() Method - Validation & Begin Interaction

```csharp
public override void Start()
{
    var world = vas.Entity.Api.World;

    // --- Range Check ---
    double dist = vas.Entity.ServerPos.DistanceTo(targetPos.ToVec3d().Add(0.5, 0.5, 0.5));
    if (dist > maxRange)
    {
        Fail($"Target too far: {dist:F1} > {maxRange}");
        return;
    }

    // --- Block Validation ---
    block = world.BlockAccessor.GetBlock(targetPos);
    if (block == null || block.Id == 0)
    {
        Fail("No block at target position");
        return;
    }

    // --- Check for Harvestable Behavior ---
    harvestBehavior = block.GetBehavior<BlockBehaviorHarvestable>();
    if (harvestBehavior == null)
    {
        Fail($"Block {block.Code} is not harvestable (no BlockBehaviorHarvestable)");
        return;
    }

    // --- Get Harvest Time ---
    // harvestTime is private but we can access it via reflection or use a default
    // For now, use reflection or assume typical values (1-2 seconds)
    harvestTime = GetHarvestTime(harvestBehavior);
    if (harvestTime <= 0)
    {
        harvestTime = DEFAULT_HARVEST_TIME;
    }

    // --- Prepare Block Selection ---
    blockSel = new BlockSelection
    {
        Position = targetPos,
        Face = BlockFacing.UP,
        HitPosition = new Vec3d(0.5, 0.5, 0.5)
    };

    // --- Start Interaction ---
    bool canStart = block.OnBlockInteractStart(world, player, blockSel);
    if (!canStart)
    {
        Fail("Interaction blocked (claims or block state)");
        return;
    }

    interactionStarted = true;
    elapsedTime = 0f;
    validated = true;

    LogDebug($"Harvesting {block.Code}: harvestTime={harvestTime:F2}s");
}

private float GetHarvestTime(BlockBehaviorHarvestable behavior)
{
    // harvestTime is private, so we use reflection
    // Alternatively, check block attributes or use defaults per block type
    try
    {
        var field = typeof(BlockBehaviorHarvestable).GetField("harvestTime",
            System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance);
        if (field != null)
        {
            return (float)field.GetValue(behavior);
        }
    }
    catch { }

    return DEFAULT_HARVEST_TIME;
}
```

---

## 5. OnTick() Method - Progress & Complete Interaction

```csharp
public override bool OnTick(float dt)
{
    if (!validated) return false;

    var world = vas.Entity.Api.World;

    // --- Check block still exists and is same type ---
    Block currentBlock = world.BlockAccessor.GetBlock(targetPos);
    if (currentBlock == null || currentBlock.Id != block.Id)
    {
        // Block changed (maybe already harvested by someone else)
        LogDebug("Block changed during harvest");
        Succeed();
        return false;
    }

    // --- Accumulate time ---
    elapsedTime += dt;

    // --- Call interaction step (for animations/sounds) ---
    bool continueInteraction = block.OnBlockInteractStep(elapsedTime, world, player, blockSel);

    // --- Check completion ---
    // Behavior completes when secondsUsed >= harvestTime - 0.05f
    if (!continueInteraction || elapsedTime >= harvestTime - 0.05f)
    {
        // Complete the harvest
        block.OnBlockInteractStop(elapsedTime, world, player, blockSel);

        LogDebug($"Harvested {block.Code} in {elapsedTime:F2}s");

        // Handle auto-collect (harvestable blocks often spawn EntityItems)
        if (autoCollectDrops)
        {
            // Schedule pickup or inline collect
        }

        Succeed();
        return false;
    }

    return true; // Continue ticking
}
```

---

## 6. Cancel Handling

```csharp
public override void Cancel()
{
    if (interactionStarted && block != null && player != null)
    {
        var world = vas.Entity.Api.World;
        // Call stop with current elapsed time (incomplete harvest)
        block.OnBlockInteractStop(elapsedTime, world, player, blockSel);
    }
    base.Cancel();
}
```

---

## 7. Command Integration

Command: `/polis harvest <x> <y> <z> [autocollect]`

```csharp
private void ExecuteHarvestBlockCommand(IServerPlayer player, BotState botState, BlockPos targetPos, bool autoCollect = false)
{
    string ownerUid = botState.Entity.WatchedAttributes.GetString("polisOwnerUid");
    IServerPlayer ownerPlayer = sapi.World.PlayerByUid(ownerUid) as IServerPlayer ?? player;

    var action = new PolisHarvestBlockAction(
        botState.Activity,
        targetPos,
        ownerPlayer,
        maxRange: 4.5f,
        autoCollectDrops: autoCollect
    );

    StartSingleAction(botState, action);
}
```

---

## 8. HTTP API Integration

Add to `/polis/command` handler:

```csharp
case "harvest":
    // harvest <x> <y> <z> [autocollect]
    if (args.Length < 3) return BadRequest("harvest requires x y z");
    var harvestPos = new BlockPos(
        int.Parse(args[0]),
        int.Parse(args[1]),
        int.Parse(args[2])
    );
    bool autoCollect = args.Length > 3 && args[3].ToLower() == "true";
    ExecuteHarvestBlockCommand(contextPlayer, botState, harvestPos, autoCollect);
    return Ok($"Harvesting block at {harvestPos}");
```

---

## 9. Hotkey

Add `Alt+H` for "harvest at look target" (reuse existing hotkey pattern).

Note: `Alt+H` is currently `placeheld` - may need a different binding like `Alt+R` (reap).

---

## 10. Edge Cases & Error Handling

| Scenario | Handling |
|----------|----------|
| Block has no Harvestable behavior | Fail with message |
| Block already harvested (empty bush) | Behavior handles this - interaction will fail |
| Claims block interaction | OnBlockInteractStart returns false |
| Block changes mid-harvest | Succeed (someone else got it) |
| harvestTime is 0 or missing | Use default (1.0s) |
| Interaction step returns false early | Complete harvest |

---

## 11. Design Notes

### Block Interaction Flow

The `BlockBehaviorHarvestable` uses a three-phase interaction:

```
OnBlockInteractStart() → Setup, check permissions
         ↓
OnBlockInteractStep(elapsed) → Animate, play sounds (each tick)
         ↓
OnBlockInteractStop(elapsed) → If elapsed >= harvestTime: give drops, swap block
```

### Harvestable vs Breakable

| Aspect | Harvestable | Breakable |
|--------|-------------|-----------|
| Block after | Swapped to harvested variant | Removed (air) |
| Regrowth | Yes (via Transient behavior) | No |
| Drops | Via harvestedStacks | Via block drops |
| Time | harvestTime (1-2s typical) | Resistance-based |

### Common Harvestable Blocks

- Berry bushes (blueberry, cranberry, etc.)
- Resin logs
- Wild crops (flax, onion)
- Mushrooms (some)
- Honey combs

---

## 12. Future Enhancements

- [ ] Detect harvestable state (don't try to harvest empty bushes)
- [ ] Forage skill multiplier integration
- [ ] Animation/particle triggers on bot

---

## 13. Testing Checklist

```bash
# Find a ripe berry bush in-game

# Test harvest
curl -X POST http://localhost:8585/polis/command \
  -d '{"cmd":"harvest","args":["100","70","100"]}'
curl http://localhost:8585/polis/state  # Check LastAction

# Test cases:
# 1. Harvest ripe berry bush (should take ~1s, drop berries)
# 2. Harvest already-empty bush (should fail or instant-complete)
# 3. Harvest resin log (should take ~1-2s, drop resin)
# 4. Harvest non-harvestable block (should fail)
# 5. Harvest with autocollect=true (berries in inventory)
```

---

## 14. Dependencies

Requires:
- `BlockBehaviorHarvestable` class (from vssurvivalmod)
- Block interaction API (`OnBlockInteractStart/Step/Stop`)
- Reflection for `harvestTime` access (or alternative approach)
