# Phase 2 Roadmap (Task/Job System)

**Date:** 2026-01-06

## Goals
- Expand world interaction primitives so bots can interact with the world reliably.
- Add a task/job system on top of EntityActivitySystem (scanner/executor split).
- Keep existing primitives in place for now; layer validation and new primitives first, then refactor if needed.
- Stay server-authoritative and match VS semantics (claims, range, LOS, tool behavior).

## Non-Goals (Phase 2)
- Full UI/Work Tab system (can be stubbed with commands first).
- Major refactor of possession or network architecture.
- Complex GUI-driven workstations (anvil, clayforming) beyond minimal shortcuts.

## Constraints and Invariants
- Shadow Registry persistence stays authoritative (PolisGlobalData).
- All debug logs are prefixed with "[polis]" and gated by debug flag.
- Action validation must check range, LOS, and claims before running.
- Prefer existing primitives and extend them; replace only after validation failures.

## Phase 2.0: Primitive Hardening and Missing Primitives

### 2.0.0 Entity Base Decision Gate (Playerbot vs Custom)
**Decision**
- Choose the long-term bot entity base **before** expanding inventory/task primitives.
- Options: keep `survival:playerbot`, switch to `EntityVillager`, or custom `EntityHumanoid` + `seraphinventory`.
- References:
  - `docs/journal/2026-01-13-entity-type-decision.md`
  - `docs/research/phase-2/2026-01-15-entity-replacement-options.md`

**Acceptance Criteria**
- Inventory model matches Phase 2 assumptions (hands + backpack slots).
- Harness primitives (goto/activate/pickup/drop) operate without regressions.
- Possession (IMountable) works with the chosen entity.
- No unwanted taskai/emotion behaviors interfere with commands.
- Migration path defined for existing BotRecord entity codes.

**Test Plan**
- Spawn bot with candidate entity code; run core primitives + harness `/polis state` checks.
- Verify hands/backpack slot mapping and held-item visuals.
- Mount/dismount possession, confirm camera + controls.
- Idle test (no commands) for 2-3 minutes; ensure no stray wander/AI if undesired.

### 2.0.1 Shared Selection + Validation Layer
**Implementation**
- Add a shared resolver for block/entity selection (ray trace from bot or player).
- Add common validation: range, LOS, claims (Use vs BuildOrBreak).
- Route activate/break/place/interact through the validation layer.

**Test Plan**
- LOS: place a wall between bot and target, run `/polis activate l[]` and `/polis break l[]`; expect failure.
- Range: target at 6-7 blocks; expect out-of-range.
- Claims: test in claimed land without permissions; expect denial.

### 2.0.2 Entity Interact (HitPosition Fix + Command)
**Implementation**
- Wire `/polis interact` to ray-traced entity selection.
- Pass `EntitySelection.HitPosition` directly to `Entity.OnInteract`.

**Test Plan**
- Interact with an entity that has a known right-click behavior (trader/boat/animal).
- Repeat from a side angle; interaction should still trigger.

### 2.0.3 Held-Use Action (Tool Pipeline)
**Implementation**
- Add `PolisHeldUseAction` using `OnHeldUseStart/Step/Stop`.
- Honor `EnumHandHandling`; stop early if `NotHandled`.
- Expose via `/polis use` or as a primitive used by workstation actions.

**Test Plan**
- Hoe: convert dirt to farmland.
- Knife: harvest a plant and verify drops.
- Quern or timed action: verify Start/Step/Stop run until completion.

### 2.0.4 Pickup/Drop
**Implementation**
- Add `PolisPickupItemAction` using `CanCollect` -> `OnCollected` -> explicit slot insertion.
- Handle partial transfer (keep entity alive if stack remains).
- Add `/polis drop` to spawn item entity from bot inventory slot/hand.

**Test Plan**
- Full pickup: item entity despawns, inventory gains item.
- Partial pickup: remaining stack stays in world.
- Inventory full: pickup fails, entity remains.
- Drop: item entity spawns at bot position.

### 2.0.5 Container Transfer (Bot <-> Container)
**Implementation**
- Add `/polis takefrom` and `/polis putinto`.
- Use `IBlockEntityContainer.Inventory` and `ItemSlot.TryPutInto`.
- Mark slots dirty and `BlockEntity.MarkDirty()`; enforce claim checks (Use).

**Test Plan**
- Transfer to chest and back; verify contents persist.
- Confirm client sync by reopening chest.
- Deny transfer in claimed land without permissions.

### 2.0.6 Inventory Model Validation (seraphinventory + bags)
**Implementation**
- Validate `EntityBehaviorSeraphInventory` / `InventoryGear` usage for bots.
- Confirm hands + backpack slots and bag contents persistence.

**Test Plan**
- Give items, save/reload, verify persistence.
- Equip a bag in backpack slot, transfer items, save/reload, verify contents.
- Observe held-item visuals from another client.

### 2.0.7 Workstations (No-GUI First)
**Implementation**
- Quern and pit kiln via block/held-use pipeline.
- Treat GUI-heavy stations (anvil, clayforming) as out of scope for now.

**Test Plan**
- Quern: insert input, start grinding, verify output.
- Pit kiln: ignite and verify firing completion.

## Phase 2.1: Job System Scaffolding

### 2.1.1 Data Definitions
**Implementation**
- Add `PolisWorkType`, `PolisWorkGiver`, `PolisJobDef`, `PolisJob`.
- Map JobDef -> JobDriver type and required reservations.

**Test Plan**
- Create a dummy job type and ensure it serializes and can be instantiated.

### 2.1.2 Job Tracker + Reservation Manager
**Implementation**
- Per-bot `PolisJobTracker`: current job, queue, cooldowns, last-scan time.
- `PolisReservationManager` with lock ordering and release-on-fail.

**Test Plan**
- Two bots target the same item/block; ensure only one reserves it.
- Failed reservation releases and retries after a backoff.

### 2.1.3 Scheduler + Performance Budget
**Implementation**
- Add a global job scheduler with tick throttling and per-bot jitter.
- Implement a pathfinding token bucket and optional path request cache.

**Test Plan**
- Spawn multiple bots (10-20) and confirm stable tick time.
- Log how many path requests run per tick; ensure cap enforced.

### 2.1.4 WorkGivers (Scanner Layer)
**Implementation**
- Implement minimal work givers for Haul, Harvest, Build, Idle.
- Use scoring (distance + urgency) with anti-thrash cooldowns.

**Test Plan**
- Place items in world: bots pick a closest haul.
- Create multiple harvest targets: bots distribute work without ping-pong.

## Phase 2.2: Minimal Job Drivers (Execution Layer)

### 2.2.1 Haul (A -> B)
**Implementation**
- Goto source -> pickup -> goto destination -> drop.

**Test Plan**
- Haul stack into a chest, verify inventory updates.

### 2.2.2 Harvest (Break + Collect)
**Implementation**
- Goto -> break -> pickup.

**Test Plan**
- Harvest a crop block and verify drops + inventory.

### 2.2.3 Build (Place)
**Implementation**
- Goto -> place using real inventory stack.

**Test Plan**
- Place a block from bot inventory; verify stack decrements.

### 2.2.4 Idle/Wander
**Implementation**
- Wait or short wander when no jobs.

**Test Plan**
- With no tasks, bots idle without spamming job scans.

## Phase 2.3: Debugging and Telemetry
**Implementation**
- Expand debug logging around selection/validation and job selection.
- Optional: task indicators or nameplate suffix for active job.

**Test Plan**
- `/polis debug on` shows action start/fail reasons.
- Logs include reservation decisions and job transitions.

## Open Questions / Decision Points
- How strict should claims enforcement be for bot actions (Use vs BuildOrBreak)?
- Should bots use their own inventory only, or borrow from player inventory?
- When a job fails (no path), do we backoff or requeue immediately?
- When to refactor existing primitives to use full held-use pipeline?

## Exit Criteria for Phase 2
- All primitives (activate/break/place/interact/use/pickup/drop/transfer) validated with tests.
- Minimal job system can execute Haul, Harvest, Build, and Idle tasks.
- Job selection is stable (no thrash) with 10-20 bots in a test world.
