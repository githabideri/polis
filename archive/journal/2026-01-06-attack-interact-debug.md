# 2026-01-06: /polis interact attack debug

## Context
- Command: /polis interact attack
- Actor: selected bot (survival:playerbot)
- Targets: vsvillage:villager-male-trader, game:playerbot
- Debug: /polis debug on
- Build: PolisBuilderNpc.dll (Release) deployed to vsdata/Mods/polis-builder-npc
- Logs: ../vsdata/Logs/server-main.log

## Repro
1. Spawn/select bot.
2. Look at target entity within ~4.5 blocks.
3. Run /polis interact attack.
4. Observe server log.

## Observed
- [polis] [interact] target=... mode=Attack ... (logs show hitRel computed).
- Immediate exception:
  NullReferenceException at Vintagestory.API.Common.EntityAgent.OnInteract(...):line 403
  called from PolisInteractEntityAction.Start(...).
- Server ticks suspended after repeated exceptions.

Log sample (server-main.log):
- 6.1.2026 23:03:20 [Notification] [polis] [interact] target=vsvillage:villager-male-trader id=151 mode=Attack item=game:blade-blackguard-iron hitRel=0.25,1.17,-0.02
- 6.1.2026 23:03:20 [Error] Exception: Object reference not set to an instance of an object.
  at Vintagestory.API.Common.EntityAgent.OnInteract(...):line 403
- 6.1.2026 23:03:47 [Notification] [polis] [interact] target=game:playerbot id=7 mode=Attack item=game:blade-blackguard-iron hitRel=-0.07,1.51,-0.30
- 6.1.2026 23:03:47 [Error] Exception: Object reference not set to an instance of an object.
  at Vintagestory.API.Common.EntityAgent.OnInteract(...):line 403

## Analysis
- EntityAgent.OnInteract Attack path uses (byEntity as EntityPlayer).Player without null guard.
- Our bot actor is EntityPlayerBot (EntityAnimalBot), not EntityPlayer, so byEntity as EntityPlayer is null.
- This causes NRE before damage can apply.

## Impact
- /polis interact attack currently fails and can suspend server ticks.
- Interact (non-attack) still works.

## Decision
- No fix applied yet. We will research existing NPC attack implementations in other mods before choosing an approach.

## Interact (non-attack) status

### Observed (user testing)
- /polis interact (default mode) on a trader works: bot walks up and the entities nod to each other repeatedly (interaction loop visible).
- /polis interact on a seat does not work.
- /polis interact attack on a trader or another bot fails (see above).

### How it works (current implementation)
- Command raytraces from the player view (pitch/yaw) to select an entity.
- Bot goes to the entity position, then calls Entity.OnInteract(byEntity=bot, slot=bot.ActiveHandItemSlot, hitPos, mode=Interact).
- hitPos normalization:
  - If raytrace provides a world-space hitPos (near entity position), it is converted to relative space.
  - If hitPos is missing, we use the entity selection box center as a relative fallback.

### Constraints and likely limitations
- Some entities expect byEntity to be EntityPlayer (not just EntityAgent). Those interactions may not work for bots.
- Some interactions depend on player selection box index or input states (sneak, right-click held), which bots do not provide.
- Seat interactions often inspect the selecting player or selection box index, so they can fail with bots.

### Suggested manual checks (later)
- /polis interact on a trader should trigger visible nodding.
- /polis interact on a rideable or seat likely fails (confirm expected).
- /polis interact on pettable or harvestable entities may depend on player inputs.
