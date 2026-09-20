# Test Plan: PolisHarvestBlockAction

**Date:** 2026-01-16
**Feature:** Harvest harvestable blocks (berry bushes, resin logs, etc.)
**Branch:** `agent/claude/harvest-block-action`

---

## Prerequisites

1. **Deploy the mod:**
   ```bash
   cd /home/mf/Code/polis-builder/worktrees/claude-harvest-block-action
   export VINTAGE_STORY="/home/mf/.local/share/flatpak/app/at.vintagestory.VintageStory/x86_64/stable/active/files/extra/vintagestory"
   dotnet build -c Release
   cp -r bin/Release/Mods/polis-builder-npc ../vsdata/Mods/
   ```

2. **Start the game server** (restart if already running to reload mod)

3. **Verify harness is running:**
   ```bash
   curl http://localhost:8585/health
   ```
   Should return: `{"status":"ok"}`

4. **Join the world** and spawn a bot:
   ```bash
   # In-game: /polis spawn
   # Or via harness:
   curl -X POST http://localhost:8585/polis/command \
     -H "Content-Type: application/json" \
     -d '{"cmd":"spawn","args":[]}'
   ```

5. **Find harvestable blocks** in the world:
   - Ripe berry bushes (blueberry, cranberry, etc.)
   - Resin-bearing logs
   - Wild crops (flax, onions)

   Note the coordinates (X, Y, Z) of these blocks.

---

## Test Cases

### Test 1: Harvest Ripe Berry Bush (Success)

**Setup:**
- Find a **ripe** berry bush (variant state = "ripe")
- Note coordinates, e.g., `100 70 100`

**Execute:**
```bash
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"harvest","args":["100","70","100"]}'
```

**Expected Result:**
- Bot navigates to berry bush
- Bot performs harvest animation (~1-2 seconds)
- Bush changes from ripe to empty state
- Berries drop on ground
- Action completes successfully

**Verify:**
```bash
curl http://localhost:8585/polis/state
```
Check:
- `LastActionName`: `"harvest"`
- `LastActionOk`: `true`
- `LastActionMs`: ~1000-2000ms

**Logs to check:**
```bash
tail -50 ../vsdata/Logs/server-main.log | grep -i "polis.*harvest"
```
Should show:
```
[polis] [harvest] started: game:bushes/berry-blueberry-ripe harvestTime=1.50s
[polis] [harvest] completed: game:bushes/berry-blueberry-ripe in 1.51s
```

---

### Test 2: Harvest with Auto-Collect (Berries to Inventory)

**Setup:**
- Find another ripe berry bush
- Note coordinates, e.g., `105 70 102`

**Execute:**
```bash
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"harvest","args":["105","70","102","true"]}'
```

**Expected Result:**
- Bot harvests bush (same as Test 1)
- **Berries are automatically collected** to bot owner's inventory
- No berry items remain on ground

**Verify:**
```bash
curl http://localhost:8585/polis/state
```
Check logs for:
```
[polis] [harvest] completed: ...
[polis] [harvest] collected 2 item(s)
```

**In-game:** Check player inventory - should have berries

---

### Test 3: Harvest Empty Bush (Fail - Not Ripe)

**Setup:**
- Find an **empty** berry bush (variant state = "empty")
- Note coordinates, e.g., `110 70 108`

**Execute:**
```bash
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"harvest","args":["110","70","108"]}'
```

**Expected Result:**
- Action starts
- Bot navigates to bush
- **Action fails with message:** `"block ... is not ripe"`
- No harvest occurs

**Verify:**
```bash
curl http://localhost:8585/polis/state
```
Check:
- `LastActionOk`: `false` (or check logs for failure message)

**Logs:**
```
[polis] [harvest] failed: block game:bushes/berry-blueberry-empty is not ripe
```

---

### Test 4: Harvest Non-Harvestable Block (Fail)

**Setup:**
- Target a regular block (stone, dirt, etc.)
- Note coordinates, e.g., `100 69 100`

**Execute:**
```bash
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"harvest","args":["100","69","100"]}'
```

**Expected Result:**
- Bot navigates to block
- **Action fails:** `"block ... is not harvestable"`
- No interaction occurs

**Logs:**
```
[polis] [harvest] failed: block game:stone is not harvestable (no BlockBehaviorHarvestable)
```

---

### Test 5: Harvest Resin from Log

**Setup:**
- Find a resin-bearing log (if available in world)
- Note coordinates

**Execute:**
```bash
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"harvest","args":["<x>","<y>","<z>","true"]}'
```

**Expected Result:**
- Bot harvests resin
- Resin items collected to inventory (if autocollect=true)
- Log block changes to harvested state

---

### Test 6: Harvest with Validation Disabled (Skip Ripe Check)

**Setup:**
- Find an empty berry bush
- Note coordinates, e.g., `110 70 108`

**Execute with `validateripe=false`:**
```bash
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"harvest","args":["110","70","108","false","false"]}'
```

**Expected Result:**
- Bot attempts harvest even though bush is empty
- Block interaction may fail or succeed (depending on game mechanics)
- **Use case:** Testing or forcing harvest regardless of state

---

### Test 7: Harvest Out of Range (Fail)

**Setup:**
- Target a ripe berry bush far from bot (~10+ blocks away)
- Note coordinates

**Execute:**
```bash
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"harvest","args":["<far_x>","<far_y>","<far_z>"]}'
```

**Expected Result:**
- **Action fails:** `"out of range dist=X.X > 4.5"`
- Bot does not move

---

### Test 8: In-Game Command Test

**In-game chat command:**
```
/polis harvest ~100 ~70 ~100
/polis harvest ~100 ~70 ~100 true
/polis harvest ~100 ~70 ~100 true false
```

**Expected Result:**
- Bot harvests block at specified coordinates
- Same behavior as HTTP API tests

---

## Verification with Harness

### Check Action State

```bash
curl http://localhost:8585/polis/state | jq '.LastActionName, .LastActionOk, .LastActionMs, .LastActionMsg'
```

### Watch Logs (Real-time)

```bash
tail -f ../vsdata/Logs/server-main.log | grep -i "polis.*harvest"
```

### Debug Mode (if needed)

In-game:
```
/polis debug on
```

Then run harvest commands - detailed logs will appear.

---

## Success Criteria

- ✅ **Test 1:** Ripe berry bush harvested successfully
- ✅ **Test 2:** Auto-collect works (items in inventory)
- ✅ **Test 3:** Empty bush rejected with "not ripe" message
- ✅ **Test 4:** Non-harvestable block rejected
- ✅ **Test 5:** Resin log harvested (if available)
- ✅ **Test 6:** Validation can be disabled
- ✅ **Test 7:** Out of range blocks rejected
- ✅ **Test 8:** In-game commands work

---

## Troubleshooting

### Bot doesn't move
- Check bot is spawned and selected
- Verify coordinates are correct
- Check pathfinding (solid ground to target)

### "Unknown command: harvest"
- Mod not loaded correctly
- Restart server after deploying mod
- Check `../vsdata/Logs/server-main.log` for mod load errors

### "Block is not harvestable"
- Target block doesn't have `BlockBehaviorHarvestable`
- Try a different harvestable block type
- Use `/polis debug on` to see block code in logs

### Harvest completes but no drops
- Check if autocollect is enabled
- Look around bot - items may have spawned nearby
- Some harvestable blocks may have empty drop tables

---

## Harness Integration Summary

### HTTP API

**Endpoint:** `POST /polis/command`

**Payload:**
```json
{
  "cmd": "harvest",
  "args": ["<x>", "<y>", "<z>", "<autocollect>", "<validateripe>"]
}
```

**Parameters:**
- `x, y, z` (required): Block coordinates
- `autocollect` (optional, default `false`): Auto-collect drops to bot owner inventory
- `validateripe` (optional, default `true`): Validate block is ripe before harvesting

**Response:**
```json
{
  "ok": true,
  "message": "Bot #12345 harvesting block at (100, 70, 100) (autocollect=true, validateripe=true)"
}
```

### In-Game Command

```
/polis harvest <x> <y> <z> [autocollect] [validateripe]
```

Example:
```
/polis harvest ~100 ~70 ~100 true true
```

---

## Next Steps

After testing:
1. Document results in `docs/testing/test-results/`
2. Report any issues found
3. If all tests pass, mark feature as complete
4. Merge branch to main (if approved)
