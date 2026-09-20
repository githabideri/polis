# Implementation Plan: `PolisMineBlockAction`

**Status:** Ready for implementation
**Date:** 2026-01-15
**Related:** Phase 2 action primitives

## Overview

A timed mining action that respects block resistance, tool tier requirements, and mining speed—making NPC mining feel like vanilla player mining.

The key difference from `PolisBreakBlockAction` is **time simulation**. Instead of instant break, we accumulate progress each tick based on: `progress += miningSpeed * dt`. When `progress >= resistance`, we call `BreakBlock()`.

---

## 1. File Location

**Path:** `PolisBuilderNpcSystem.cs`

Add after `PolisBreakBlockAction` (around line ~4200) to keep related actions grouped.

---

## 2. Class Structure

```csharp
public class PolisMineBlockAction : EntityActionBase
{
    // === Constructor Parameters ===
    private readonly BlockPos targetPos;
    private readonly IServerPlayer player;          // Owner player for BreakBlock context
    private readonly float maxRange;
    private readonly bool autoCollectDrops;
    private readonly float collectRadius;

    // === Runtime State ===
    private Block block;
    private float resistance;                       // Block.Resistance (total time needed)
    private float miningSpeed;                      // Effective speed after all multipliers
    private float progress;                         // Accumulated mining progress
    private ItemSlot toolSlot;                      // Reference to track tool durability
    private bool validated;                         // Start() succeeded

    // === Constants ===
    private const float DEFAULT_MAX_RANGE = 4.5f;
    private const float DEFAULT_COLLECT_RADIUS = 3f;
    private const float MIN_MINING_SPEED = 0.1f;    // Prevent division issues
}
```

---

## 3. Constructor

```csharp
public PolisMineBlockAction(
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

## 4. Start() Method - Validation & Setup

```csharp
public override void Start()
{
    var agent = vas.Entity as EntityAgent;
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

    resistance = block.Resistance;
    if (resistance <= 0)
    {
        // Instant break (air, water, etc.) - just break it
        world.BlockAccessor.BreakBlock(targetPos, player, 1.0f);
        LogDebug($"Instant break: {block.Code} (resistance=0)");
        Succeed();
        return;
    }

    // --- Tool Validation ---
    var invbh = agent.GetBehavior<EntityBehaviorSeraphInventory>();
    if (invbh == null)
    {
        Fail("Bot has no inventory behavior");
        return;
    }

    toolSlot = invbh.Inventory[15]; // Right hand
    if (toolSlot?.Itemstack?.Collectible == null)
    {
        // No tool - use bare hands (ToolTier = 0, slow speed)
        miningSpeed = 1.0f * GlobalConstants.ToolMiningSpeedModifier;
        int requiredTier = block.RequiredMiningTier;
        if (requiredTier > 0)
        {
            Fail($"Tool required: block needs tier {requiredTier}");
            return;
        }
    }
    else
    {
        var tool = toolSlot.Itemstack.Collectible;
        int toolTier = tool.ToolTier;
        int requiredTier = block.RequiredMiningTier;

        // --- Tier Check ---
        if (toolTier < requiredTier)
        {
            Fail($"Tool tier insufficient: {toolTier} < {requiredTier}");
            return;
        }

        // --- Mining Speed Calculation ---
        EnumBlockMaterial material = block.BlockMaterial;
        float baseMiningSpeed = 1.0f;

        if (tool.MiningSpeed != null && tool.MiningSpeed.TryGetValue(material, out float speedMult))
        {
            baseMiningSpeed = speedMult;
        }

        miningSpeed = baseMiningSpeed * GlobalConstants.ToolMiningSpeedModifier;
    }

    // Clamp to minimum
    if (miningSpeed < MIN_MINING_SPEED)
    {
        miningSpeed = MIN_MINING_SPEED;
    }

    progress = 0f;
    validated = true;

    float estimatedTime = resistance / miningSpeed;
    LogDebug($"Mining {block.Code}: resistance={resistance:F2}, speed={miningSpeed:F2}, est={estimatedTime:F2}s");
}
```

---

## 5. OnTick() Method - Progress Loop

```csharp
public override bool OnTick(float dt)
{
    if (!validated) return false; // Start() failed

    var world = vas.Entity.Api.World;

    // --- Check block still exists ---
    Block currentBlock = world.BlockAccessor.GetBlock(targetPos);
    if (currentBlock == null || currentBlock.Id == 0 || currentBlock.Id != block.Id)
    {
        // Block changed/removed by something else
        LogDebug("Block changed during mining");
        Succeed(); // Consider it done
        return false;
    }

    // --- Accumulate progress ---
    progress += miningSpeed * dt;

    // --- Check completion ---
    if (progress >= resistance)
    {
        // Break the block
        world.BlockAccessor.BreakBlock(targetPos, player, 1.0f);

        // Tool durability (TODO: implement in later step)
        // if (toolSlot?.Itemstack != null)
        // {
        //     toolSlot.Itemstack.Collectible.DamageItem(world, vas.Entity, toolSlot, 1);
        //     PolisInventoryHelpers.StoreSeraphInventory(vas.Entity as EntityAgent);
        // }

        LogDebug($"Mined {block.Code} in {progress / miningSpeed:F2}s");

        // Handle auto-collect
        if (autoCollectDrops)
        {
            // Queue pickup action or do inline collection
            // For now, we'll handle this in the command layer
        }

        Succeed();
        return false;
    }

    return true; // Continue ticking
}
```

---

## 6. Command Integration

Command: `/polis mine <x> <y> <z> [autocollect]`

```csharp
private void ExecuteMineCommand(IServerPlayer player, BotState botState, BlockPos targetPos, bool autoCollect = false)
{
    // Resolve owner player - use commanding player as fallback
    // NOTE: May need revision when ownership system matures
    string ownerUid = botState.Entity.WatchedAttributes.GetString("polisOwnerUid");
    IServerPlayer ownerPlayer = sapi.World.PlayerByUid(ownerUid) as IServerPlayer ?? player;

    var action = new PolisMineBlockAction(
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
case "mine":
    // mine <x> <y> <z> [autocollect]
    if (args.Length < 3) return BadRequest("mine requires x y z");
    var minePos = new BlockPos(
        int.Parse(args[0]),
        int.Parse(args[1]),
        int.Parse(args[2])
    );
    bool autoCollect = args.Length > 3 && args[3].ToLower() == "true";
    ExecuteMineCommand(contextPlayer, botState, minePos, autoCollect);
    return Ok($"Mining at {minePos}");
```

---

## 8. Hotkey

Add `Alt+M` for "mine at look target" (similar to existing gotolook pattern).

---

## 9. Edge Cases & Error Handling

| Scenario | Handling |
|----------|----------|
| Block has 0 resistance | Instant break, skip progress loop |
| No tool equipped | Use bare hands (speed=1.0), fail if tier required |
| Tool tier too low | Fail with descriptive message |
| Block changes mid-mining | Succeed (someone else broke it) |
| Owner player offline | Use commanding player as fallback |
| Bot moves away during mining | Continue mining (range checked only at start) |

---

## 10. Future Enhancements

- [ ] Tool durability damage on completion
- [ ] Block damage decals during mining (visual feedback)
- [ ] Animation/sound triggers

---

## 11. Testing Checklist

```bash
# Basic mining test
curl -X POST http://localhost:8585/polis/command \
  -d '{"cmd":"give","args":["game:pickaxe-copper"]}'
curl -X POST http://localhost:8585/polis/command \
  -d '{"cmd":"mine","args":["100","70","100"]}'
curl http://localhost:8585/polis/state  # Check LastAction

# Test cases:
# 1. Mine stone with copper pickaxe (should work, ~0.5s)
# 2. Mine granite with stone pickaxe (should work, ~0.75s)
# 3. Mine iron ore with stone pickaxe (should fail - tier too low)
# 4. Mine soil with bare hands (should work, slow)
# 5. Mine with autocollect=true (drops collected)
```
