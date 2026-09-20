## Harness Inventory Give/Drop/Pickup (2026-01-13)

**Context**
- Build: `agent/codex/bot-inventory-sync`
- World: `test-lands`
- Harness: HTTP `localhost:8585`
- Player: `the player`

**Goal**
Validate that the new slot-based inventory insertion works end-to-end via the harness
and that drop/pickup flows update bot inventory as expected.

**Setup**
- Spawned bot near player with harness `spawn` + `spawnOffset`.
- Selected bot with harness `select`.

**Results**
1) **Give (harness)**
   - `give game:stone-granite 10` inserted into **left hand** because right hand
     already held `game:blade-blackguard-iron`.
   - `/polis/state` confirmed left hand stack size = 10.

2) **Drop (left hand)**
   - `drop 1 4` reduced left-hand stack from 10 → 2.
   - In one run, `/polis/state` showed **no nearby items** immediately after drop.
     A second drop produced an item entity visible in `/polis/state`.
   - This suggests either:
     - items can spawn outside the scan radius on first drop, or
     - there is a timing/visibility edge case in the harness item scan.

3) **Pickup (by entity id)**
   - Dropped entity `#235` (2x granite) was picked up with `pickup 235 6`.
   - Left hand returned to 2x granite; item entity list empty afterward.

**Notes**
- The harness `give` path now uses the same slot-based insertion helper as `/polis give`,
  so results match expectations even when right hand is occupied.
- Item scan may miss a freshly spawned drop in some cases; consider
  adding a short delay or re-query before asserting absence.

**Follow-up tests (same session)**
4) **Right-hand full drop + pickup**
   - `drop 0 0` (full stack) cleared the right hand after a reselect retry and spawned
     `game:blade-blackguard-iron` as an item entity.
   - `pickup <id> 6` inserted the blade back into right hand as expected.

5) **Left-hand full drop (qty 0) inconsistency**
   - `drop 1 0` sometimes reported success but left-hand count remained unchanged in `/polis/state`.
   - Partial drops (`drop 1 1`) reliably reduced the stack and spawned item entities.
   - An explicit `drop 1 2` (with stack size 1) cleared the left hand and spawned an entity.
   - This suggests a possible edge case in full-stack drop handling or a state refresh issue.

6) **Pickup merge into left hand**
   - With right hand occupied, consecutive pickups merged into left hand (1 → 2), as expected.

**Follow-up (survival, ground level)**
7) **Drop height + CanCollect timing**
   - Dropped stacks sometimes spawned above ground (y ≈ 6) even at ground level.
   - Immediate pickup returned `CanCollect returned false` until the item fell/settled.
   - After the drop landed (y ≈ 3), pickup succeeded.

8) **Range gating**
   - Pickup returned `out of range dist=4.66 range=3.00` when the bot was ~4-5 blocks away.

9) **Inventory capacity gating**
   - With both hands occupied and no backpack, pickup returned `inventory full or no valid slots`.
   - Dropping a hand allowed pickup to succeed.

10) **Auto-pick behavior**
   - Dropping at the bot’s feet can immediately auto-pick the item if a hand is free.
   - Moving the bot away right after the drop prevents the auto-pick and leaves a stable item entity.
   - A confirmed 12-block walk + drop left the quern on the ground (no auto-pick on return).
