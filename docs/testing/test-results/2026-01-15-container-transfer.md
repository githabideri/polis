# Container Transfer Test Results

**Date:** 2026-01-15
**Branch:** agent/claude/container-transfer
**Tester:** codex

## Environment
- Harness: http://localhost:8585 - READY
- Player UID: REDACTED-UID
- Bot ID: 331
- Container: game:chest-east at [224, 3, 270]
- Movement target: east of container at [225, 3, 270]

## Results

### PUTINTO (Bot -> Container)
- **Result:** PASS
- **Command Response:** {"Ok":true,"Message":"Bot #331 putting into container at (224, 3, 270) from slot 0","Data":null}
- **State After:**
  - RightHand: null
  - LastAction: {"Name":"putinto","Ok":true,"Msg":"transferred 5 items from bot to container"}

### TAKEFROM (Container -> Bot)
- **Result:** PASS
- **Command Response:** {"Ok":true,"Message":"Bot #331 taking from container at (224, 3, 270) slot 0","Data":null}
- **State After:**
  - RightHand: {"Code":"game:stone-granite","Qty":5}
  - LastAction: {"Name":"takefrom","Ok":true,"Msg":"transferred 5 items from container to bot"}

## Post-Test Item Check
- **Action:** Extra putinto after TAKEFROM to leave items in chest
- **Response:** {"Ok":true,"Message":"Bot #331 putting into container at (224, 3, 270) from slot 0","Data":null}
- **State After:** RightHand=null; LastAction=putinto (Ok=true)

## Summary
- PUTINTO: PASS
- TAKEFROM: PASS
- **Overall: 2/2 passed**

## Notes
- `give` spawns items directly into the bot's hand; `putinto`/`takefrom` perform actual inventory transfers between the bot and container.

## Issues Found
- None observed in command execution; bot pathing completed to offset target.
