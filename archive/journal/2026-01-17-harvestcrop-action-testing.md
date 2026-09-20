# PolisHarvestCropAction Testing Journal

**Date:** 2026-01-17
**Status:** ✅ Resolved - Working as Expected

## Summary

Implemented `PolisHarvestCropAction` for harvesting mature crops on farmland. The action works correctly - the initial "drops not spawning" issue was caused by **testing with a Creative mode player**.

### Root Cause

The vanilla `Block.OnBlockBroken()` in `vsapi/Common/Collectible/Block/Block.cs:1061` has this check:

```csharp
if (world.Side == EnumAppSide.Server && (byPlayer == null || byPlayer.WorldData.CurrentGameMode != EnumGameMode.Creative))
{
    ItemStack[] drops = GetDrops(world, pos, byPlayer, dropQuantityMultiplier);
    // ... spawn drops
}
```

Since `BreakBlock()` is called with the **controlling player** (not the bot), drops are skipped when that player is in Creative mode. This is intentional vanilla VS behavior.

### Resolution

Retested with the controlling player in **Survival mode** - drops spawn correctly:
- 7x grain-flax
- 1x seeds-flax
- 7x flaxfibers

Full harvest→pickup→deposit workflow verified working.

---

## What Works ✅

1. **Farmland detection** - Correctly finds `BlockEntityFarmland` at target or below target
2. **Maturity validation** - `HasRipeCrop()` correctly identifies mature vs immature crops
3. **Stage reporting** - Reports accurate "crop not mature: stage X/Y" for immature crops
4. **Block removal** - `BreakBlock()` successfully removes the crop block
5. **Claims checking** - Respects land claim permissions

## What Doesn't Work ❌

1. ~~**Drops not spawning**~~ - **RESOLVED**: Was caused by Creative mode player; works in Survival
2. **Wild crops not supported** - Action requires farmland beneath the crop; wild crops (naturally spawning `crop-*` blocks on regular soil) cannot be harvested with this action - farmland must be tilled beneath them first

## Observations During Testing

- **Goto overshoot** - The `goto` command consistently overshoots the target position slightly. Bot arrives at target then continues moving ~0.5-1 block further, sometimes resulting in a brief "sliding" walk animation or ending up on top of nearby blocks (e.g., landing on a chest when aiming in front of it).

---

## Test Environment

- New survival world, Spring Year 0
- Wild flax crops (`game:crop-flax-*`) with farmland tilled beneath them
- Time advanced via `/time add 120` to mature crops to stage 9/9
- Bot spawned near crops, selected via harness

## Test Results

### Test 1: Immature Crop (flax-8 on farmland)
```bash
curl -s -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"harvestcrop","args":["51147","132","51260"],"context":{"playerUid":"abc+123PlayerUidHere"}}'
```
**Result:** `{"Ok":false,"Msg":"crop not mature: stage 8/9"}` ✅ Correct rejection

### Test 2: Wild Crop (no farmland below)
```bash
curl -s -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"harvestcrop","args":["51145","132","51258"],"context":{"playerUid":"abc+123PlayerUidHere"}}'
```
**Result:** `{"Ok":false,"Msg":"no farmland found at or below target"}` ✅ Correct rejection

### Test 3: Mature Crop on Farmland (flax-9)
```bash
curl -s -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"harvestcrop","args":["51144","132","51259"],"context":{"playerUid":"abc+123PlayerUidHere"}}'
```
**Result:** `{"Ok":true,"Msg":"harvested game:crop-flax-9"}`
- Block removed: ✅
- Drops spawned: ❌ **NO DROPS VISIBLE**

---

## Working Harness Commands

### Get Player UID
```bash
curl -s http://localhost:8585/polis/players | jq '.players[0].uid'
# Returns: "abc+123PlayerUidHere"
# NOTE: + must be URL-encoded as %2B in query params
```

### Search for Crops/Farmland
```bash
curl -s "http://localhost:8585/polis/targets?mode=blocks&radius=50&playerUid=abc%2B123PlayerUidHere&limit=300" \
  | jq -r '.Blocks[] | select(.Code | test("crop|farmland"; "i")) | "\(.Code) at (\(.Pos[0]), \(.Pos[1]), \(.Pos[2]))"'
```

### Advance Time (for crop maturation)
```bash
curl -s -X POST http://localhost:8585/polis/servercmd \
  -H "Content-Type: application/json" \
  -d '{"cmd":"/time add 120","playerUid":"abc+123PlayerUidHere"}'
# Adds 120 hours (~5 days)
# NOTE: Use plain integer hours, NOT "5d" or "120:0" format
```

### Spawn and Select Bot
```bash
# Spawn at world spawn
curl -s -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"spawn"}'

# Or spawn near player
curl -s -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"spawn","context":{"playerUid":"abc+123PlayerUidHere","spawnOffset":[0,0,2]}}'

# Select existing bot
curl -s -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"select","args":["BOT_ID"]}'
```

### Harvest Crop Command
```bash
# Without autocollect
curl -s -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"harvestcrop","args":["X","Y","Z"],"context":{"playerUid":"PLAYER_UID"}}'

# With autocollect (currently broken anyway)
curl -s -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"harvestcrop","args":["X","Y","Z","true"],"context":{"playerUid":"PLAYER_UID"}}'
```

### Check Action Result
```bash
curl -s "http://localhost:8585/polis/state?botId=BOT_ID" | jq '.LastAction'
```

---

## Coordinate System Note

**HUD coordinates ≠ Server coordinates**

- HUD shows: `-55, 132, 57`
- Server uses: `51145, 132, 51255`
- Offset: ~51200 in X and Z (map center offset)

Always use `/polis/players` or `/polis/targets` to get server-absolute coordinates for commands.

---

## Investigation Completed ✅

### Why didn't BreakBlock spawn drops for crops?

**Answer:** The controlling player was in Creative mode.

The vanilla `Block.OnBlockBroken()` explicitly skips drop spawning when `byPlayer.WorldData.CurrentGameMode == EnumGameMode.Creative`. This is intentional - Creative mode players don't get drops when breaking blocks.

Since `harvestcrop` (and `mine`) pass the **controlling player** to `BreakBlock()`, the player's game mode affects whether drops spawn.

**Hypothesis 3 was closest** - the player context affects drop spawning, but via game mode check rather than position.

### Research Resources Used

- `refs/vsapi/Common/Collectible/Block/Block.cs:1061` - OnBlockBroken with Creative mode check
- `refs/vssurvivalmod/Block/BlockCrop.cs` - GetDrops implementation
- `refs/vssurvivalmod/BlockEntity/BEFarmland.cs` - OnCropBlockBroken

---

## Files Changed

- `PolisBuilderNpcSystem.cs` - Added:
  - `PolisHarvestCropAction` class (~220 lines) at line 5209
  - `ExecuteHarvestCropCommand()` handler at line 2064
  - HTTP routing case for "harvestcrop" at line 1038
  - Updated help text at line 1048

## Commit

```
1bf400e Add PolisHarvestCropAction for farmland crop harvesting
```

---

## Next Steps

1. ~~Research `BlockCrop.OnBlockBroken` implementation in vssurvivalmod~~ ✅ Done
2. ~~Test if `mine` command on crops produces drops (compare behavior)~~ N/A - same underlying issue
3. ~~Try alternative approaches~~ N/A - not needed, works in Survival mode
4. ~~Check if player position/context affects drop logic~~ ✅ Game mode was the issue

**Remaining:**
- Document Creative mode limitation in KNOWN_ISSUES.md
- Investigate goto overshoot behavior (separate issue)
