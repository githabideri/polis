# Test Results: Animate Command and Action Commands

**Date:** 2026-01-18
**Tester:** Claude
**Branch:** main

## Overview

Tested the new `animate` command and verified action commands (mine, harvest, harvestcrop, putinto, pickup).

## Environment

- Harness: http://localhost:8585 - READY
- Player UID: d4pJ+Ty1RgaBHrQgQEV8z27E
- Bot ID: 482

## Animate Command Tests

| Test | Description | API Result | Visual Result |
|------|-------------|------------|---------------|
| 1 | Basic one-shot animation (`hit`) | PASS | PASS - Bot waved |
| 2 | Animation with speed modifier (2x) | PASS | PASS - Visibly faster |
| 3 | Looping animation (`interact`) | PASS | FAIL - No animation |
| 4 | Stop specific animation | SKIPPED | - |
| 5 | Stop all animations | SKIPPED | - |
| 6 | Invalid animation code | SKIPPED | - |
| 7 | CLI wrapper | SKIPPED | - |
| 8 | Chat command | SKIPPED | - |

### Findings

- **One-shot animations work** - Both API and visual confirmed
- **Looping animations don't work** - API returns success but no visual animation plays
- Tests 4-8 skipped due to looping animation issue investigation

## Action Command Tests

| Command | Result | Notes |
|---------|--------|-------|
| **mine** (iron ore) | PASS | Needs correct tier tool |
| **mine** (mushroom) | PASS | Instant break |
| **pickup** | PASS | |
| **goto** | PASS | |
| **putinto** (chest) | PASS | Needs to be in range first |
| **targets** | PASS | Query filter not working, but jq filtering works |
| **give** | PASS | |
| **harvest** (berry bush) | FAIL | Drops go to player inventory, not ground |
| **harvestcrop** (sunflower) | PASS | Drops on ground correctly |

## Bugs Found

### 1. Looping animations don't play visually
- **Severity:** Medium
- **Description:** `animate <code> 1.0 loop` returns success but animation doesn't play
- **Note:** One-shot animations work fine

### 2. Harvest (berry bush) drops go to player inventory
- **Severity:** Medium
- **Description:** When using `harvest` on BlockBehaviorHarvestable (berry bushes), drops go to the player's inventory instead of the ground
- **Affected:** `PolisHarvestBlockAction`
- **Note:** `harvestcrop` works correctly (drops on ground)

### 3. CLI --player flag doesn't work
- **Severity:** Low
- **Description:** `./scripts/poliscli.py --player UID look` fails with "Player UID required"
- **Workaround:** Use environment variable `POLIS_PLAYER_UID=...`
- **Status:** FIXED - use `polis look --player UID` (flag after subcommand)

### 4. CLI targets --query doesn't filter
- **Severity:** Low
- **Description:** The `--query` parameter on targets command doesn't filter results by block code
- **Workaround:** Use jq filtering on raw curl output

## Action Classes Animation Status

| Class | Has Animation |
|-------|---------------|
| PolisGotoAction | YES (walk/run + Controls.Sprint) |
| PolisMineBlockAction | NO |
| PolisHarvestBlockAction | NO |
| PolisHarvestCropAction | NO |
| PolisButcherEntityAction | NO |

## Next Steps

1. Fix harvest drops going to player inventory
2. Investigate why looping animations don't work (one-shot works)
3. Add animation calls to action classes (mine, harvest, butcher)
