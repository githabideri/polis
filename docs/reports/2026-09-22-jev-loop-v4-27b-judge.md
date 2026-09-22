# Jev-loop v4: 27B per-step judge + Laya pre-filter — measurement & the inventory blocker

Date: 2026-09-22 · Environment: the game container (<polis-container-ip>:8585), Laya 421M (openjev openjev-host:8781), Qwen3.8-27B dual-3090 (llm-host:8080, thinking OFF)

## Architecture

v3 measured that at 421M the noul veto is a conservative safety net (fault and
false alarm at the same p; 27B-as-veto stalled correct actions). v4 inverts
the tiers:

    policy proposes  ->  Laya noul pre-filter
                            p >= 0.60 -> execute directly (cheap path, ~1.9 s)
                            p <  0.60 -> 27B judge (full state + proposal,
                                          thinking off, 4-action choice,
                                          ~0.2-0.7 s) -> execute its choice
                                          (fallback: the proposal)

Faults injected at steps 3 (skip-goal: goto_base during travel) and 6
(tool-drop + mine). Script: scripts/jev-loop-v4.py.

## Measured (two runs, 8 steps each)

| metric | run 1 | run 2 |
|---|---|---|
| reflex short-circuits (no 27B call) | 5/8 | 3/8 |
| judge calls | 3 | 5 |
| judge oracle match | 2/3 | 3/5 |
| exec oracle match (final vs phase-correct) | 7/8 | 6/8 |
| false waits on judge path | 0 | 2 (after visible mine failures) |
| avg Laya / avg 27B latency | 1.9 s / 0.21 s | 2.1 s / 0.74 s |
| faults corrected | 1/2 (tool) | 0/2 |
| exec success | 2/8 | 3/8 |

**The v3 stall failure mode is gone at this placement.** In run 1 the judge
never waited on a correct proposal. In run 2 it waited twice - but only
*after* the mine steps had visibly failed (facts showed "No block at target
position"), i.e. reacting to failure evidence rather than the undiscriminating
v3 stall. The 27B is a *reasoning* conservative, not a *reflexive* one.

Its answers are single words ("wait", "mine_target", "goto_target") - the
`enable_thinking:false` contract holds at 206-738 ms.

## The real blocker: the bot cannot hold items

Run 2 showed the mine action *does work* (block mined in ~5 s,
`Ok=True, "mined, collected 0/2, overflow: 1x game:rock-granite"`) - but the
item **overflows onto the ground** because the polisbot inventory is unusable:

- `give <any item>` fails with "inventory full or no valid slots", even
  though the seraph inventory is nominally 17 slots with only 1 occupied
  (verified with pickaxe and stick).
- `EntityPolisBot : EntityHumanoid` with the `seraphinventory` behavior;
  `PolisInventoryHelpers.TryInsertIntoBotInventory` tries right-hand ->
  left-hand -> backpack via `TryPutIntoSlot`; every attempt fails silently
  (no log) - a black box.

Consequences: the bot can never carry a pickaxe, mined items drop on the
ground, and any "item in backpack" completion check can never pass. This is
the **harvest-pipeline backlog item**, now root-caused to the entity inventory
behavior. A clean end-to-end v4 run requires the mod to give the bot a
working inventory.

## Harness / 1.22 quirks found

- `drop` removes the **held** item, not the named one (v3's tool fault
  dropped the linen sack).
- `teleport` takes a **player uid**, not a bot id.
- Freshly spawned bots 404 on `/polis/state` for a few seconds until the
  client system sees them.
- Bot ids increment monotonically (16, 17, 20, 21, 22, ...) - never assume.
- Goto stops one cell short of a solid target block (never enters it; the
  block survives). The loop should target the adjacent cell.
- Marker rocks placed via `setblock` vanished between runs twice without a
  visible cause (they survive goto and 30 s idle). v4.1 verifies the marker
  before every mine step and re-places if missing; if it recurs, the re-place
  stamp dates the disappearance.

## Verdict

The two-tier loop works as designed on the decision side: the cheap reflex
carries the common case, the 27B is consulted only when the reflex is unsure,
and its conservatism is *informed*. Remaining work is execution-layer: the
bot inventory (mod change + rebuild + redeploy), after which a clean 8-step
mission run is expected. Next: fix EntityPolisBot inventory (proper player-
style `inventory` behavior + slot refs), re-run v4 to completion, then the
plant/harvest pipeline.
