# Implementation Plan: `PolisHarvestCropAction`

**Status:** Ready for implementation
**Date:** 2026-01-15
**Related:** Phase 2 action primitives

## Overview

Harvest mature crops from farmland blocks. This is simpler than generic harvestable blocks—just needs a maturity check followed by BreakBlock.

Unlike berry bushes (which use timed interaction), crops are harvested by breaking the crop block when mature. The farmland block entity tracks growth stage.

---

## 1. File Location

**Path:** `PolisBuilderNpcSystem.cs`

Add after `PolisMineBlockAction` to keep harvesting actions grouped.

---

## 2. Class Structure

```csharp
public class PolisHarvestCropAction : EntityActionBase
{
    // === Constructor Parameters ===
    private readonly BlockPos targetPos;            // Can be crop pos or farmland pos
    private readonly IServerPlayer player;          // For BreakBlock context
    private readonly float maxRange;
    private readonly bool autoCollectDrops;
    private readonly float collectRadius;

    // === Runtime State ===
    private BlockPos cropPos;                       // Resolved crop position
    private BlockPos farmlandPos;                   // Resolved farmland position
    private bool validated;

    // === Constants ===
    private const float DEFAULT_MAX_RANGE = 4.5f;
    private const float DEFAULT_COLLECT_RADIUS = 3f;
}
```

---

## 3. Constructor

```csharp
public PolisHarvestCropAction(
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

## 4. Start() Method - Validation, Maturity Check, Harvest

This action is instant (no tick loop needed) since we just break the block.

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

    // --- Find Farmland Block Entity ---
    // Target could be the crop (above farmland) or the farmland itself
    BlockEntityFarmland farmland = world.BlockAccessor.GetBlockEntity<BlockEntityFarmland>(targetPos);

    if (farmland != null)
    {
        // Target is farmland, crop is above
        farmlandPos = targetPos;
        cropPos = targetPos.UpCopy();
    }
    else
    {
        // Target might be the crop - check below for farmland
        farmland = world.BlockAccessor.GetBlockEntity<BlockEntityFarmland>(targetPos.DownCopy());
        if (farmland != null)
        {
            farmlandPos = targetPos.DownCopy();
            cropPos = targetPos;
        }
    }

    if (farmland == null)
    {
        Fail("No farmland found at or below target position");
        return;
    }

    // --- Check for Crop ---
    Block cropBlock = farmland.GetCrop();
    if (cropBlock == null)
    {
        Fail("No crop planted on this farmland");
        return;
    }

    // --- Maturity Check ---
    if (!farmland.HasRipeCrop())
    {
        int currentStage = farmland.GetCropStage(cropBlock);
        int maxStage = cropBlock.CropProps?.GrowthStages ?? 0;
        Fail($"Crop not mature: stage {currentStage}/{maxStage}");
        return;
    }

    // --- Harvest (Break the Crop) ---
    LogDebug($"Harvesting mature crop: {cropBlock.Code} at {cropPos}");
    world.BlockAccessor.BreakBlock(cropPos, player, 1.0f);

    // Handle auto-collect (crops drop seeds + produce)
    if (autoCollectDrops)
    {
        // Chain pickup action or inline collection
        // Could schedule a delayed pickup to let items spawn
    }

    Succeed();
}
```

---

## 5. No OnTick Needed

Crop harvesting is instant—just maturity check + break. No progress loop required.

```csharp
public override bool OnTick(float dt)
{
    // Instant action - nothing to tick
    return false;
}
```

---

## 6. Command Integration

Command: `/polis harvestcrop <x> <y> <z> [autocollect]`

```csharp
private void ExecuteHarvestCropCommand(IServerPlayer player, BotState botState, BlockPos targetPos, bool autoCollect = false)
{
    string ownerUid = botState.Entity.WatchedAttributes.GetString("polisOwnerUid");
    IServerPlayer ownerPlayer = sapi.World.PlayerByUid(ownerUid) as IServerPlayer ?? player;

    var action = new PolisHarvestCropAction(
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

## 7. HTTP API Integration

Add to `/polis/command` handler:

```csharp
case "harvestcrop":
    // harvestcrop <x> <y> <z> [autocollect]
    if (args.Length < 3) return BadRequest("harvestcrop requires x y z");
    var cropPos = new BlockPos(
        int.Parse(args[0]),
        int.Parse(args[1]),
        int.Parse(args[2])
    );
    bool autoCollect = args.Length > 3 && args[3].ToLower() == "true";
    ExecuteHarvestCropCommand(contextPlayer, botState, cropPos, autoCollect);
    return Ok($"Harvesting crop at {cropPos}");
```

---

## 8. Edge Cases & Error Handling

| Scenario | Handling |
|----------|----------|
| Target is crop block (not farmland) | Check block below for farmland |
| Target is farmland (not crop) | Crop is at targetPos.Up |
| No crop planted | Fail with message |
| Crop not mature | Fail with stage info |
| Farmland exists but GetCrop() returns null | Fail (empty farmland) |

---

## 9. Design Notes

### Why Not Use Timed Interaction?

Unlike berry bushes (which have `BlockBehaviorHarvestable` with timed right-click), crops are simply broken when mature. The farmland block entity handles:
- Growth stage tracking
- Nutrient consumption
- Regrowth timing (if replanted)

Breaking the crop via `BreakBlock()` triggers normal drop behavior—seeds + produce based on the crop type.

### Farmland vs Crop Position

```
     [Crop Block]     ← cropPos (what we break)
    [Farmland BE]     ← farmlandPos (has maturity info)
```

The `BlockEntityFarmland` is at the farmland block position, but `GetCrop()` returns the block above it.

---

## 10. Future Enhancements

- [ ] Auto-replant option (pick up seeds, immediately replant)
- [ ] Multi-crop harvesting (harvest all mature crops in radius)
- [ ] Integration with farming job scanner

---

## 11. Testing Checklist

```bash
# Setup: Plant crops, wait for maturity (or use /time command to fast-forward)

# Test mature crop harvest
curl -X POST http://localhost:8585/polis/command \
  -d '{"cmd":"harvestcrop","args":["100","70","100"]}'

# Test immature crop (should fail)
# Plant fresh crop, immediately try to harvest

# Test empty farmland (should fail)
# Target farmland with no crop planted

# Test with autocollect
curl -X POST http://localhost:8585/polis/command \
  -d '{"cmd":"harvestcrop","args":["100","70","100","true"]}'
curl http://localhost:8585/polis/state  # Verify items in inventory
```

---

## 12. Dependencies

Requires access to:
- `BlockEntityFarmland` class (from vssurvivalmod)
- `HasRipeCrop()` method
- `GetCropStage()` method
- `Block.CropProps.GrowthStages` property
