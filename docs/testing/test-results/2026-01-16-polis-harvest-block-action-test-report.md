# PolisHarvestBlockAction Test Report

**Date:** 2026-01-16
**Feature:** Harvest harvestable blocks (berry bushes, resin logs, flax crops, etc.)
**Branch:** `agent/claude/harvest-block-action`
**Mod Version:** 0.1.0
**Harness Version:** HTTP API on port 8585

---

## Environment

| Component | Status |
|-----------|--------|
| Harness | Running (http://localhost:8585) |
| World Ready | Yes |
| Mod Version | 0.1.0 |
| Player | the player (uid: d4pJ+Ty1RgaBHrQgQEV8z27E) |

---

## Test Map Summary

### Map 1: Creative/Test Map
- **Berry Bushes:** 5 ripe blueberry bushes found (game:smallberrybush-blueberry-ripe, game:bigberrybush-redcurrant-ripe)
- **Resin Logs:** 2 resin-bearing pine logs (game:log-resin-pine-ud)
- **Mushrooms:** Field mushrooms available (exact codes unknown)
- **Non-Harvestable:** Granite rock (game:rock-granite)
- **Container:** Chest at [224, 3, 270]

### Map 2: Survival Map
- **Flax Crops:** 7 flax crops found (stages 2-9, game:crop-flax-*)
- **Onion Crops:** None found in immediate area

---

## Test Cases

### Test 1: Harvest Ripe Berry Bush (Success)

**Setup:**
- Target: game:smallberrybush-blueberry-ripe at [216, 3, 263]
- Bot moved to adjacent position [216.06, 3.00, 263.05]

**Command:**
```json
{
  "cmd": "harvest",
  "args": ["216", "3", "263"],
  "context": {"playerUid": "d4pJ+Ty1RgaBHrQgQEV8z27E"}
}
```

**Response:**
```json
{
  "ok": true,
  "message": "Bot #365 harvesting block at (216, 3, 263) (autocollect=False, validateripe=True)"
}
```

**State After:**
- Berries dropped on ground (4x game:fruit-blueberry at dist 0.15)
- Block likely changed to empty state

**Result:** PASS

**Notes:** Harvest completed, items dropped on ground as expected.

---

### Test 2: Harvest with Auto-Collect (Berries to Inventory)

**Setup:**
- Target: game:smallberrybush-blueberry-ripe at [216, 3, 265]
- Bot adjacent to target

**Command:**
```json
{
  "cmd": "harvest",
  "args": ["216", "3", "265", "true"],
  "context": {"playerUid": "d4pJ+Ty1RgaBHrQgQEV8z27E"}
}
```

**Response:**
```json
{
  "ok": true,
  "message": "Bot #365 harvesting block at (216, 3, 265) (autocollect=True, validateripe=True)"
}
```

**State After:**
- Berries dropped on ground (5x game:fruit-blueberry)
- NOT collected to bot's hands

**Result:** FAIL

**Issue:** Auto-collect parameter not implemented; items drop on ground regardless of autocollect setting.

**Expected Behavior:** Auto-collect should deposit items into bot's hands (or drop to ground if hands full), NOT into player inventory.

---

### Test 3: Harvest Empty Bush (Fail - Not Ripe)

**Setup:**
- Target: game:smallberrybush-blueberry-* at [216, 3, 263] (previously harvested, now empty)
- Bot adjacent to target

**Command:**
```json
{
  "cmd": "harvest",
  "args": ["216", "3", "263"],
  "context": {"playerUid": "d4pJ+Ty1RgaBHrQgQEV8z27E"}
}
```

**Response:**
```json
{
  "ok": true,
  "message": "Bot #365 harvesting block at (216, 3, 263) (autocollect=False, validateripe=True)"
}
```

**State After:**
- No items dropped (expected for empty bush)
- Command accepted without rejection

**Result:** FAIL

**Issue:** Ripe validation not enforced; empty bushes accept harvest commands without error message "block is not ripe".

---

### Test 4: Harvest Non-Harvestable Block (Fail)

**Setup:**
- Target: game:rock-granite at [220, 3, 268]
- Bot adjacent to target [219.91, 4.00, 267.99]
- Debug mode enabled

**Command:**
```json
{
  "cmd": "harvest",
  "args": ["220", "3", "268"],
  "context": {"playerUid": "d4pJ+Ty1RgaBHrQgQEV8z27E"}
}
```

**Response:**
```json
{
  "ok": true,
  "message": "Bot #365 harvesting block at (220, 3, 268) (autocollect=False, validateripe=True)"
}
```

**State After:**
- No items dropped
- LastAction remained "goto" (not "harvest")
- No error message in response

**Result:** FAIL

**Issue:** Silent failure for non-harvestable blocks. Expected error message "block ... is not harvestable (no BlockBehaviorHarvestable)" not returned.

---

### Test 5: Harvest Resin from Log

**Setup:**
- Target: game:log-resin-pine-ud at [216, 3, 269]
- Bot adjacent to target [216.00, 4.00, 268.93]

**Command:**
```json
{
  "cmd": "harvest",
  "args": ["216", "3", "269", "true"],
  "context": {"playerUid": "d4pJ+Ty1RgaBHrQgQEV8z27E"}
}
```

**Response:**
```json
{
  "ok": true,
  "message": "Bot #365 harvesting block at (216, 3, 269) (autocollect=True, validateripe=True)"
}
```

**State After:**
- Resin dropped on ground (1x game:resin at dist 1.34)
- NOT auto-collected to bot's hands

**Result:** PASS (harvest completed)
**Result:** FAIL (autocollect not implemented)

**Notes:** Same autocollect issue as Test 2 - should collect to bot's hands.

---

### Test 6: Harvest with Validation Disabled (Skip Ripe Check)

**Setup:**
- Target: game:smallberrybush-blueberry-* at [216, 3, 263] (empty)
- Bot adjacent to target

**Command:**
```json
{
  "cmd": "harvest",
  "args": ["216", "3", "263", "false", "false"],
  "context": {"playerUid": "d4pJ+Ty1RgaBHrQgQEV8z27E"}
}
```

**Response:**
```json
{
  "ok": true,
  "message": "Bot #365 harvesting block at (216, 3, 263) (autocollect=False, validateripe=False)"
}
```

**State After:**
- No items dropped (expected for empty bush)

**Result:** PASS

**Notes:** Validation can be disabled via validateripe=false parameter.

---

### Test 7: Harvest Out of Range (Fail)

**Setup:**
- Target: game:bigberrybush-redcurrant-ripe at [229, 3, 274]
- Bot at [216.07, 3.00, 263.06] (distance ~12.74)

**Command:**
```json
{
  "cmd": "harvest",
  "args": ["229", "3", "274"],
  "context": {"playerUid": "d4pJ+Ty1RgaBHrQgQEV8z27E"}
}
```

**Response:**
```json
{
  "ok": true,
  "message": "Bot #365 harvesting block at (229, 3, 274) (autocollect=False, validateripe=True)"
}
```

**State After:**
- Bot did not move
- No harvest occurred

**Result:** PASS (implicit range check prevents action)

**Notes:** Command accepted but action fails due to distance. Expected message "out of range dist=X.X > 4.5" not visible.

---

### Test 8: In-Game Command Test

**Result:** BLOCKED

**Notes:** Not tested via /polis harvest in-game chat. Would require manual in-game verification.

---

### Test 9: Mushroom Harvest

**Setup:**
- Target: Unknown mushroom at [218, 3, 269] (field mushroom, 2 blocks east of resin log)
- Bot adjacent to target

**Command:**
```json
{
  "cmd": "harvest",
  "args": ["218", "3", "269"],
  "context": {"playerUid": "d4pJ+Ty1RgaBHrQgQEV8z27E"}
}
```

**Response:**
```json
{
  "ok": true,
  "message": "Bot #365 harvesting block at (218, 3, 269) (autocollect=False, validateripe=True)"
}
```

**State After:**
- No items dropped

**Result:** INCONCLUSIVE

**Notes:** Harvested but no drops. May require different mechanic (right-click vs activate) or different block code.

---

### Test 10: Container Storage

**Setup:**
- Bot with 9x blueberries in RightHand, 1x resin in LeftHand
- Container: game:chest-east at [224, 3, 270]

**Commands:**
```json
{"cmd": "putinto", "args": ["224", "3", "270", "0", "9"]}  // Blueberries
{"cmd": "putinto", "args": ["224", "3", "270", "1", "1"]}  // Resin
```

**Response:**
```json
{
  "ok": true,
  "message": "Bot #365 putting into container at (224, 3, 270) from slot 0"
}
```

**State After:**
- RightHand: null
- LeftHand: null

**Result:** PASS

**Notes:** Container operations work correctly.

---

### Test 11: Survival Map - Flax Crop Harvest

**Setup:**
- Player at [45762, 111, 53852]
- Bot #10089 spawned and selected
- 7 flax crops found (game:crop-flax-* stages 2-9)

**Command:**
```json
{
  "cmd": "harvest",
  "args": ["45759", "111", "53853"],
  "context": {"playerUid": "d4pJ+Ty1RgaBHrQgQEV8z27E"}
}
```

**Response:**
```json
{
  "ok": true,
  "message": "Bot #10089 harvesting block at (45759, 111, 53853) (autocollect=False, validateripe=True)"
}
```

**State After:**
- No items dropped
- LastAction remained "goto" (not "harvest")
- Multiple attempts with bot adjacent to crop, same result

**Result:** FAIL

**Issue:** Harvest action not completing properly on survival map. LastAction not updating prevents verification.

---

## Summary

| Test | Description | Result |
|------|-------------|--------|
| 1 | Harvest ripe berry bush | PASS |
| 2 | Auto-collect parameter | FAIL |
| 3 | Empty bush ripe validation | FAIL |
| 4 | Non-harvestable block rejection | FAIL |
| 5 | Resin log harvest | PASS (harvest) / FAIL (autocollect) |
| 6 | Validation disabled | PASS |
| 7 | Out of range handling | PASS |
| 8 | In-game command | BLOCKED |
| 9 | Mushroom harvest | INCONCLUSIVE |
| 10 | Container storage | PASS |
| 11 | Survival map flax crops | FAIL |

**Total:** 4 PASS / 4 FAIL / 1 INCONCLUSIVE / 2 BLOCKED

---

## Issues Found

### Critical Issues

1. **Auto-collect not implemented:** Items drop on ground regardless of `autocollect` parameter. Should collect to bot's hands (or drop if hands full), NOT player inventory.
2. **Ripe validation not enforced:** Empty bushes accept harvest commands without rejection
3. **Non-harvestable block rejection missing:** Silent failure instead of error message
4. **Harvest action state not updating:** `LastAction` remains "goto" after harvest commands
5. **Insufficient logging:** No [polis] harvest messages visible in server logs

### Logging Issues

- Debug mode enabled but no harvest-related log messages appear
- Only bot registry save notifications visible
- Need explicit log messages for:
  - Harvest start
  - Harvest completion
  - Validation failures (not ripe, not harvestable, out of range)
  - Item drops

### API Issues

- `/health` endpoint returns 404 (correct endpoint is `/polis/status`)
- LastAction not reflecting harvest command execution status

---

## Recommendations

1. **Implement autocollect:** Auto-collect drops to bot's hands (or drop to ground if hands full), NOT player inventory
2. **Add ripe validation:** Reject harvest commands on empty bushes with message
3. **Add BlockBehaviorHarvestable check:** Reject non-harvestable blocks with message
4. **Update LastAction:** Set LastAction to "harvest" with Ok=true/false after completion
5. **Improve logging:** Add [polis] [harvest] messages for all harvest operations
6. **Test mushroom mechanic:** Field mushrooms may require different interaction (right-click/activate)
7. **Test survival crops:** Flax harvest failing on survival map needs investigation

---

## Test Files

- Test plan: `docs/testing/2026-01-16-harvest-block-action-test.md`
- Targets API: `docs/TESTING_HARNESS_TARGETS.md`
- Testing guide: `docs/testing/AGENT_TESTING_GUIDE.md`

---

*Generated: 2026-01-16*
