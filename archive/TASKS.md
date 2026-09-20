# Tasks from Known Issues

Tasks extracted from `KNOWN_ISSUES.md`. For review before creating kanban tickets.

---

## High Priority (Blocks Core Agentic Workflows)

### TASK-001: Fix goto command overshoot

**Problem:** The `goto` command consistently overshoots target by ~0.5-1 block. Bot arrives at target then continues moving slightly, sometimes showing brief "sliding" walk animation or ending up on top of nearby blocks (e.g., landing on chest when aiming in front of it).

**Impact:** Bot positioning unreliable; affects all subsequent actions requiring precise placement (activate, place, mine, interact).

**Relevant code:**
- `PolisGotoAction` in `PolisBuilderNpcSystem.cs:5765` - uses `WaypointsTraverser.NavigateTo_Async`
- Movement handled by `StraightLineTraverser` or A* traverser

**Research refs:**
- `docs/research/phase-0/2026-01-02-waypoints-traverser-surface.md`
- `docs/research/phase-1/2026-01-06-movement-fix-plan.md`

**Suggested approach:** Add deceleration zone near target, or snap entity position on arrival callback.

---

### TASK-002: Add mining/harvesting animations to action classes

**Problem:** `PolisMineBlockAction`, `PolisHarvestBlockAction`, `PolisHarvestCropAction`, `PolisButcherEntityAction` complete their work but have no visual swing/hit animations. Only `PolisGotoAction` has animation support (walk/run).

**Impact:** No visual feedback for major bot actions. Hard to tell if bot is working or stuck. Poor UX for observation.

**Relevant code:**
- `PolisMineBlockAction` at line 6516 - no animation call
- `PolisHarvestBlockAction` at line 6952 - no animation call
- `PolisButcherEntityAction` at line 7552 - no animation call
- Compare to `PolisAnimateAction` at line 6230 which uses `AnimManager.StartAnimation()`

**Animation patterns:**
```csharp
var animMeta = new AnimationMetaData {
    Animation = "hit",  // or "interactstatic"
    Code = "hit",
    AnimationSpeed = 1f,
    EaseInSpeed = 1f,
    EaseOutSpeed = 1f
};
entity.AnimManager.StartAnimation(animMeta.Init());
```

**Suggested approach:** Add animation trigger at action start, loop during work, stop on complete. Use "hit" for mining, "interactstatic" for harvest.

---

### TASK-003: Fix berry bush harvest drops going to player inventory

**Problem:** Using `harvest` command on `BlockBehaviorHarvestable` blocks (berry bushes, resin) sends drops to the controlling player's inventory instead of dropping on ground. This differs from `harvestcrop` which correctly drops items.

**Impact:** Bot cannot collect harvested items from bushes/resin. Breaks resource gathering loop for these block types.

**Relevant code:**
- `PolisHarvestBlockAction` at line 6952
- Uses `block.OnBlockInteractStop()` which internally routes drops to player

**Research refs:**
- `docs/research/phase-2/2026-01-04-world-interaction-primitives.md`
- VS source: `BlockBehaviorHarvestable.cs` in vssurvivalmod

**Suggested approach:** Either override drop collection in the interaction, or use a different harvest method that spawns `EntityItem` directly.

---

### TASK-004: Fix bot loot not triggering carcass transformation

**Problem:** When a player opens a fully-looted corpse's inventory UI, VS despawns the dead entity and places a `game:carcass-tiny` block. The bot's `loot` command transfers items via `EntityBehaviorHarvestable.Inventory` but doesn't trigger this transformation.

**Impact:** Dead entities remain in world indefinitely. Carcass blocks (bone source) never appear. Clutters world with unusable corpses.

**Relevant code:**
- `PolisLootEntityAction` - transfers from harvestable inventory
- VS handles transformation in UI open callback, not in inventory access

**Research refs:**
- `docs/journal/2026-01-17-cli-testing-session.md` - documents VS two-stage harvest
- Carcass is BLOCK `game:carcass-medium` after transformation

**Suggested approach:** After loot transfer, check if inventory empty and call whatever VS method triggers the entity→block transformation. May need to examine `EntityBehaviorHarvestable.OnInteract` or `BlockEntityCarcass`.

---

### TASK-005: Investigate missing meat drops from chicken butcher

**Problem:** Butchering chickens via bot `butcher` command only yields feathers, not meat. Expected: meat + feathers like player butcher.

**Impact:** Incomplete resource gathering from animals. Bot farming is less useful.

**Relevant code:**
- `PolisButcherEntityAction` at line 7552
- Uses `EntityBehaviorHarvestable.SetHarvested(player, slot)`

**Possibly related:** May share root cause with TASK-004 (carcass transformation). If transformation isn't triggered, maybe harvest items aren't fully populated.

**Suggested approach:** Compare butcher action flow to player knife-use flow. Check if `SetHarvested` parameters are correct. Test in survival mode (creative mode prevents drops per KNOWN_ISSUES).

---

## Medium Priority (Impacts Reliability)

### TASK-006: Fix activate LOS validation for doors/partial blocks

**Problem:** `/polis activate` returns "No line of sight to target" for doors and partial blocks even when bot is adjacent. Raytrace hits non-target intermediate blocks.

**Impact:** Cannot reliably activate doors, trapdoors, fence gates, and other partial/thin blocks.

**Relevant code:**
- `PolisActivateBlockAction` - has LOS check before activation
- Raytrace from bot eye position to block center

**Suggested approach:** For partial blocks, use adjacency check instead of LOS. Or raytrace to multiple points on block (corners, center). Or skip LOS for known partial block types.

---

### TASK-007: Fix tall grass targeting sending bot to air block

**Problem:** Using `gotolook` when looking at tall grass sends bot to grass block position (in air) instead of ground below. Results in "no path" errors.

**Impact:** Cannot navigate to grass-covered areas by clicking on visible grass.

**Relevant code:**
- `gotolook` command uses player raytrace
- Harmony patch allows pathfinding THROUGH grass but doesn't fix targeting

**Research refs:**
- `docs/research/phase-0/2026-01-02-tall-grass-pathfinding.md`

**Suggested approach:** In raytrace handler, if hit block is tall grass/plant, snap target Y down to first solid block below.

---

### TASK-008: Investigate pickup "inventory full" after drop

**Problem:** `pickup` fails with "inventory full, nothing transferred" even immediately after a `drop` command freed space.

**Impact:** Bot can't cycle items reliably. Breaks gather→store workflows.

**Relevant code:**
- `PolisPickupItemAction` - checks slot availability
- `PolisDropItemAction` - modifies slot
- Inventory sync via `storeInv()`

**Research refs:**
- `docs/research/phase-2/2026-01-14-bot-inventory-sync-flow.md`

**Suggested approach:** Check if inventory state is stale after drop. May need explicit refresh or delay. Verify `MarkDirty()` + `storeInv()` sequence.

---

### TASK-009: Handle CanCollect false delay after item spawn

**Problem:** `pickup` fails with "CanCollect returned false" for ~1 second after an item entity spawns.

**Impact:** Automated pickup-after-drop/mine needs artificial delay. Makes action sequences slower.

**Relevant code:**
- `PolisPickupItemAction` - checks `EntityItem.CanCollect()`
- VS `EntityItem` has spawn protection timer

**Suggested approach:** Add retry with backoff in pickup action, or document required 1s wait. Could also check VS source for the timer constant and wait that duration.

---

### TASK-010: Fix CLI targets --query filter not working

**Problem:** The `--query` parameter on `poliscli.py targets` command doesn't filter results by block code. Users must post-process with jq.

**Impact:** CLI less useful for targeted queries. Extra step for users.

**Relevant code:**
- `scripts/poliscli.py` - targets subcommand
- Server-side `/polis/targets` endpoint has `q=` and `codeContains=` params

**Suggested approach:** Wire up `--query` arg to the appropriate query parameter in the HTTP request.

---

### TASK-011: Audit and fix silent action failures

**Problem:** Some actions return `Ok: true` on start then fail silently during execution. Agent thinks action succeeded when it didn't.

**Impact:** Unreliable agentic workflows. Need to always check state after actions.

**Relevant code:**
- All action classes derive from `EntityActionBase`
- `BotState.LastAction` tracks result

**Already fixed:** `takefrom`, `putinto`, `harvest`, `harvestcrop` now pre-validate range.

**Suggested approach:** Audit remaining actions for failure modes. Add failure events or ensure `LastAction` reflects actual outcome.

---

## Low Priority (Improvements)

### TASK-012: Fix looping animations not playing visually

**Problem:** `animate <code> <speed> loop` command returns success but animation doesn't actually loop on client.

**Impact:** Can't show continuous idle/waiting animations.

**Relevant code:**
- `PolisAnimateAction` at line 6230
- Uses `AnimationMetaData` with loop flag

**Suggested approach:** Debug client sync of loop flag. Check if animation needs to be re-triggered or if there's a client-side loop handler issue.

---

### TASK-013: Investigate lantern activation not toggling light

**Problem:** `/polis activate` on lanterns returns success but doesn't toggle light on/off.

**Impact:** Bots can't control lighting.

**Relevant code:**
- Uses `block.Activate()`
- Lantern may need different interaction (right-click with empty hand vs shift-click)

**Suggested approach:** Check VS lantern block code for activation behavior. May need specific interaction mode.

---

### TASK-014: Improve path visualization (lines instead of blocks)

**Problem:** Path visualization uses block highlights (semi-transparent cubes). Bot highlight is block outline. Hard to read visually.

**Impact:** Debug/development UX.

**Relevant code:**
- `HighlightBlocks` calls with slot IDs
- Path extraction in `TryExtractPathFromTraverser`

**Research refs:**
- `docs/research/phase-0/2026-01-02-path-line-renderer.md`

**Suggested approach:** Implement custom `IRenderer` for line-based path drawing. Use GL lines or cylinder meshes.

---

### TASK-015: Add server-triggered screenshot command

**Problem:** No way to trigger client screenshots from server/harness for automated visual testing.

**Impact:** Visual regression testing requires manual intervention.

**Existing system:**
- `PolisScreenCapture.cs` + `PolisScreenCaptureRenderer.cs` handle capture
- `/polis/screenshot` endpoint works but requires player UID

**Suggested approach:** Add harness endpoint or server command that triggers screenshot for specified player/bot view.

---

### TASK-016: Improve bot rendering (distinct appearance)

**Problem:** Polisbot uses `seraph-naked-hairless` texture, renders as pale featureless humanoid. Hard to distinguish bots visually.

**Impact:** Multiple bots hard to tell apart. Poor visual identity.

**Relevant files:**
- `assets/polis-builder-npc/entities/polisbot.json`
- `extraskinnable` behavior is disabled

**Suggested approach:** Enable `extraskinnable` with distinct colors, or create custom bot texture/model.

---

## Documentation Tasks

### TASK-017: Document coordinate offset behavior

**Problem:** Player HUD coordinates may be offset ~+256 on X/Z from server world coordinates. Causes confusion when specifying positions.

**Research refs:**
- `docs/research/misc/2026-01-12-coordinate-systems-offsets.md`
- `docs/research/misc/2026-01-13-coordinate-systems-deep-dive-validation.md`

**Suggested approach:** Add clear documentation in TESTING_HARNESS.md. Consider adding world coords to `/polis/state` response.

---

### TASK-018: Document creative mode limitations prominently

**Problem:** In creative mode, `mine`, `harvestcrop`, and similar actions remove blocks but don't spawn drops. This is vanilla VS behavior but causes test confusion.

**Impact:** Tests fail unexpectedly when run in creative mode.

**Suggested approach:** Add prominent warning box in TESTING_HARNESS.md and CLI help. Consider adding mode detection to warn in harness responses.

---

## Research Needed

### TASK-019: Research chair sit interaction for bots

**Question:** Are chairs meant to be bot-interactable? How do vanilla/vsvillage NPCs sit?

**Context:** Chairs appear activatable but may not have visible sit interaction for non-players.

**Suggested research:** Check vsvillage source for NPC sitting. Check chair block behaviors.

---

### TASK-020: Design bot-only container activation (no player UI)

**Question:** How to let bot activate/interact with containers without opening UI on controlling player's screen?

**Context:** Current `activate` on containers opens chest UI for the player since caller context is player.

**For:** VISION system - bot needs to query container contents without player UI popup.

**Suggested research:** Check if VS has silent container query API. May need custom inventory access without UI event.

---

### TASK-021: Research player corpse interaction path

**Question:** How to interact with `EntityPlayerCorpse` to access inventory?

**Context:** `/polis interact` on corpse doesn't open inventory UI. Regular interact path may not work.

**Suggested research:** Check EntityPlayerCorpse source. May need entity-ID based command or special interaction type.

---

## Won't Fix / By Design

These are documented behaviors, not bugs:

- **Straight-line fallback routing into holes:** Default is off; for debugging only
- **A* "no path" for unloaded chunks:** Expected; spawn bots nearby for testing
- **Place requires valid block source:** Use `give` first to put block in hand
- **Dropped items leave search radius:** Physics-based movement; query quickly or increase range
- **CLI global flags after subcommand:** argparse limitation; documented in CLI help
