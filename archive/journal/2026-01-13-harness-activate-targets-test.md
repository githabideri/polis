# 2026-01-13: Harness activate + targets test

## Context
Implemented harness `activate` command and `/polis/targets` endpoint. Ran a live
smoke test against the running game server to validate API behavior and action
result tracking.

## Test steps
1) `GET /polis/status` (worldReady=true)
2) `GET /polis/players` (playerUid resolved)
3) `GET /polis/targets?mode=blocks` (radius 6, then 16)
4) `GET /polis/targets?mode=entities` (radius 6)
5) `GET /polis/look` (raytrace to block)
6) `POST /polis/command` `activate` by absolute coords
7) `GET /polis/state` (verify LastAction)

## Findings
- `/polis/targets` returns block candidates with reasons and behavior names.
  In this area, soil blocks surfaced because they carry BlockBehaviors
  (`BlockBehaviorMyceliumHost`, `BlockBehaviorReinforcable`).
- A chair (`game:chair-plain` at 224,3,267) and a solid oak door
  (`game:door-solid-oak` at 223,3,268) were found within radius 6.
- A chest (`game:chest-east` at 224,3,270) was found within radius 6.
- `/polis/targets` entity mode returns nearby non-player entities (playerbot).
- Added filter params (`q`, `codeContains`, `requireEntityClass`) and bot-anchored
  scans (`botId`) to reduce noise and allow agent-driven target selection.
- Item entities now include `ItemCode` and `ItemQty` in targets output.
- `activate` via absolute coordinates succeeded and recorded
  `LastAction = activate ok=true msg=activated`.
- Activating the door at 223,3,268 succeeded and returned `LastAction` with
  `msg=handled`.
- Look-based activation hit the chair at 224,3,267 and returned
  `LastAction msg=activated`.
- Activating the chest at 224,3,270 returned `LastAction msg=handled`.
- Look-based activation still needs an explicit door/chest target in view
  for a visual confirmation run.

## Addendum: berry bush harvest attempt
- Bot-anchored scan (`botId=191`, `q=bush`) found ripe redcurrant bushes at
  229,3,274 / 229,3,276 / 229,3,278.
- Ran `activate` on 229,3,274. Harness reported `LastAction ok=true msg=handled`.
- A follow-up scan still shows the bushes as `...-ripe`, and no item entities
  appeared near the bot. Open question: berry harvest may require a closer
  player, different caller context, or another action (not confirmed yet).
- Player observed no visual change after activation in creative mode.

## Addendum: corpse interaction
- `/polis/targets` entity scan shows the player corpse as
  `playercorpse:playercorpse` (EntityPlayerCorpse), id 197 near 227.5,3,267.5.
- `/polis interact` (player aiming at corpse) returned "Interact started" and
  the bot walked to the corpse, but no inventory UI appeared for the player.
- No `LastAction` update is recorded for interact actions (expected with current code).

## Follow-up: bot LOS + entity interact (2026-01-13)
Test steps:
1) `GET /polis/status` (worldReady=true)
2) `GET /polis/players` (playerUid resolved)
3) `POST /polis/command` `select` bot 191
4) `POST /polis/command` `activate` door at 223,3,268 (explicit coords)
5) `POST /polis/command` `goto` 224,3,269 then `activate` chest at 224,3,270
6) `GET /polis/targets?mode=entities` (corpse id 197)
7) `POST /polis/command` `interact 197 interact 4.5`
8) `GET /polis/state?botId=191` (verify last action)

Findings:
- `activate` now uses bot LOS; when the bot is not aligned on the target, the
  command returns `No line of sight to target.` even if the player is nearby.
- Door activation still returns `No line of sight` even after moving the bot
  close (likely due to door collision/open-state raytrace behavior).
- Chest activation succeeds once the bot is moved into position.
- Entity-id `interact` returns Ok and moves the bot to the target, but
  `LastAction` remains unchanged (no completion record yet).

## Evidence
- Example outputs recorded in `docs/TESTING_HARNESS_OUTPUTS.md`.

## Follow-up: survival pickup + bot-anchored activates (2026-01-14)
Test steps:
1) `/gamemode survival`
2) `give` -> `drop` -> `pickup` with granite
3) `GET /polis/targets?botId=<id>&codeContains=door|gate|chest`
4) `activate` by absolute coords (playerUid context)

Findings:
- Survival mode: pickup succeeds after a short delay (`picked 2x game:stone-granite from #299`).
- Bot-anchored targets found `game:door-solid-oak` at 223,3,268 and a trapdoor nearby.
- Door activation still fails with `No line of sight to target.` from bot perspective.
- Gate activation succeeds (`game:wattlegate-sticks-n-opened-left-free` at 227,3,265).
- Chest activation succeeds (`game:chest-east` at 224,3,270).
