# Container Transfer Test Results

**Date:** 2026-01-14
**Branch:** agent/claude/container-transfer
**Tester:** codex

## Environment
- Harness: http://localhost:8585 - READY
- Player UID: REDACTED-UID
- Bot ID: 322
- Container: game:chest-east at 224, 3, 270

## Results

### PUTINTO (Bot → Container)
- **Result:** FAIL
- **Command Response:** {"Ok": false, "Message": "Unknown command: putinto. Available: spawn, select, selectlook, despawn, stop, give, drop, pickup, goto, gotolook, activate, interact, teststate, bots", "Data": null}
- **State After:**
  - RightHand: {"Code": "game:stone-granite", "Qty": 5}
  - LastAction: null

### TAKEFROM (Container → Bot)
- **Result:** FAIL
- **Command Response:** {"Ok": false, "Message": "Unknown command: takefrom. Available: spawn, select, selectlook, despawn, stop, give, drop, pickup, goto, gotolook, activate, interact, teststate, bots", "Data": null}
- **State After:**
  - RightHand: {"Code": "game:stone-granite", "Qty": 5}
  - LastAction: null

## Summary
- PUTINTO: FAIL
- TAKEFROM: FAIL
- **Overall: 0/2 passed**

## Issues Found
- Harness does not recognize `putinto` and `takefrom` commands; both return Unknown command.
