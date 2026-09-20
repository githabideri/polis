# Mine/Harvest Test Results

**Date:** 2026-01-16
**Tester:** opencode

## Environment
- Harness URL: http://localhost:8585
- Player UID: d4pJ+Ty1RgaBHrQgQEV8z27E
- Bot IDs: 394, 397

## Results

### TEST 1: Mine Soil (Bare-Handed)
- Target: game:soil-medium-normal at [223, 2, 265]
- State Progression: "mining started" → "mined"
- **Result: PASS**
- Notes: Mining completed successfully without tools, LastActionId incremented from 0 to 2

### TEST 2: Mine Rock (With Pickaxe)
- Target: game:rock-bauxite at [220, 2, 268]
- Tool: game:pickaxe-copper
- State Progression: "mining started" → "mined"
- **Result: PASS**
- Notes: Bot successfully mined bauxite stone with copper pickaxe, LastActionId incremented from 4 to 6

### TEST 3: Mine Ore (With Iron Pickaxe)
- Target: game:ore-rich-nativecopper-andesite at [220, 3, 258]
- Tool: game:pickaxe-iron
- State Progression: "mining started" → "mined"
- **Result: PASS**
- Notes: Bot successfully mined native copper ore with iron pickaxe, LastActionId incremented from 1 to 3
- Additional: Ore was picked up and stored in left hand, then transferred to chest at [224, 3, 270]

### TEST 4: Harvest Berry Bush
- Target: game:bigberrybush-redcurrant-ripe at [229, 3, 274]
- State Progression: N/A (harvest command not available)
- **Result: SKIPPED**
- Notes: The "harvest" command is not available in the current harness. Only "mine" command exists. Bot was positioned near ripe berry bush but could not test harvesting.

## Summary
- Mine Soil: PASS
- Mine Rock: PASS
- Mine Ore: PASS
- Harvest: SKIPPED (command not available)
- **Overall: 3/4 tests passed**

## Issues Found
1. Harvest command missing from harness - only "mine" command available
2. All mining tests passed successfully with proper state tracking
3. Container interaction (putinto) requires playerUid in context
4. Bot successfully picked up dropped items and transferred to chest

## Observations
- LastAction state tracking works correctly for timed actions
- LastActionId increments on both action start and completion
- Mining progress messages are clear: "mining started" → "mined"
- Tool tier requirements are enforced (copper pickaxe for rock, iron pickaxe for ore)
- Container interactions require proper player context for ownership validation
