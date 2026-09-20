# Entity Base Decision Gate: PolisBot Tests (2026-01-14)

**Context**
- Branch: `agent/codex/entity-base-decision`
- World: `test-lands`
- Harness: `http://localhost:8585`
- Entity: `polis-builder-npc:polisbot` (custom `EntityHumanoid` + `seraphinventory`)

**Why**
Validate the decision-gate acceptance criteria for a custom entity base before switching defaults.

## Findings (pre-visual fix)
- **Invisible render:** polisbot spawned but was invisible; required debug block to locate.
  - Root cause: entity JSON used `shape: game:entity/humanoid/player` with no texture.

## Core Primitive Tests
1) **Spawn + Goto**
   - Spawned next to player via harness `spawn` with `spawnOffset`.
   - `goto` completed successfully; `/polis state` showed action `done`.

2) **Inventory give/drop/pickup**
   - `give game:stone-granite 4` populated right hand.
   - `drop` spawned an item entity; `pickup` reclaimed it successfully.

3) **Block activate**
   - **Chest** at `(224,3,270)` activated successfully (`LastAction=handled`).
   - **Door** at `(223,3,268)` failed with `No line of sight` in the initial run.
   - Retest with the door **closed** succeeded when the bot stood at `(223,3,267)` or `(222,3,268)` (LOS passed).

4) **Possession**
   - `/polis possess` + `/polis unpossess` succeeded (camera jump observed as expected).
   - Manual mounting also worked, but with known Phase 1.5 issues (unchanged).

5) **Idle behavior**
   - Position unchanged over 3 seconds; no wander/AI ticks observed.

6) **Auto-pick behavior**
   - Dropped item stayed on ground after 2s; bot did not auto-pick.
   - This differs from playerbot and is expected because polisbot omits `collectitems`.

## Visual Fix (applied after tests)
- Updated `polisbot.json` to use **game-domain** assets:
  - `shape: game:entity/humanoid/seraph-faceless`
  - `texture: game:entity/humanoid/seraph-naked-hairless`
- Added `extraskinnable` + `repulseagents` to client/server behaviors to align with playerbot rendering.

## Open Questions
- Should we add `collectitems` to match playerbot auto-pick behavior, or keep explicit pickup only?
- Is door activation LOS failure due to target geometry, placement, or the LOS check itself?
- Confirm held-item visuals after the texture fix (requires re-run with visible model).
