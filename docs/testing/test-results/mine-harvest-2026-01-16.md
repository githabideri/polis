# Mine/Harvest Test Results

**Date:** 2026-01-16
**Tester:** opencode

## Environment
- Harness URL: http://localhost:8585
- Player UID: d4pJ+Ty1RgaBHrQgQEV8z27E
- Bot ID: 400

## Results

### TEST 1: Mine Soil (Bare-Handed)
- Target: game:soil-medium-verysparse at (227, 2, 271)
- State Progression: "mining started" → "mined"
- **Result: PASS**

### TEST 2: Mine Rock (With Pickaxe)
- Target: game:rock-bauxite at (232, 2, 270)
- Tool: game:pickaxe-copper
- State Progression: "mining started" → "mined"
- **Result: PASS**

### TEST 3: Harvest Berry Bush
- Target: game:bigberrybush-redcurrant-ripe at (229, 3, 274)
- State Progression: "harvest started" → "harvested"
- **Result: PASS**

### TEST 4: Mine Ore (With Pickaxe)
- Target: game:ore-lignite-chalk at (222, 3, 258)
- Tool: game:pickaxe-copper
- State Progression: "mining started" → "mined"
- **Result: PASS**

## Summary
- Mine Soil: PASS
- Mine Rock: PASS
- Harvest: PASS
- Mine Ore: PASS
- **Overall: 4/4 passed**

## Issues Found
None - All tests passed successfully

## Items Collected and Stored
All mined/harvested items were successfully stored in chest at (224, 3, 270):
- 1x game:soil-medium-none
- 2x game:stone-bauxite  
- 1x game:ore-lignite
- 1x game:pickaxe-copper (returned to chest)
