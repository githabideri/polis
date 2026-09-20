# Agentic Harness Implementation Spec (Draft)

**Date:** 2026-01-12  
**Status:** Implemented (pending test)  
**Phase Fit:** Phase 2 enablement; testing infrastructure

## Purpose
Define the concrete HTTP API extensions and verification signals needed for
agentic testing (player-relative actions, server-side look targeting, and
reliable readiness).

## Decisions (resolved)
- Add a status endpoint for readiness (no log polling required).
- Keep commands safe/minimal; defer destructive actions until permissions are defined.
- Use server-absolute coordinates as canonical; optional spawn-relative is labeled only.

## Scope
- Extend the HTTP harness API and response schemas.
- Add server-side player/lookup helpers.
- Document intended usage flow for agents and humans.
- Update the smoke script to use readiness endpoints.

Out of scope for this spec: activate/break/place via HTTP, permission gates,
and land-claim enforcement for playerless commands.

## API Additions

### GET /polis/status
Return readiness and basic metadata.

Response (example):
```json
{
  "ok": true,
  "harness": { "running": true, "port": 8585 },
  "server": { "runPhase": "WorldReady", "worldReady": true },
  "timeMs": 12345678,
  "modVersion": "0.0.0"
}
```

### GET /polis/players
List online players with server-absolute positions and look data.

Response (example):
```json
{
  "ok": true,
  "players": [
    {
      "uid": "player-uid",
      "name": "Player",
      "pos": [230.1, 3.0, 267.9],
      "yaw": 1.57,
      "pitch": 0.1,
      "eyePos": [230.1, 4.62, 267.9],
      "dimension": 0
    }
  ]
}
```

### GET /polis/player?uid=<uid>
Single-player detail. Returns `error` if not found.

### GET /polis/look?uid=<uid>&range=<float>
Server-side raytrace from player eye position using server yaw/pitch.
Returns both block and entity selection if present.

Response (example):
```json
{
  "ok": true,
  "lookVec": [0.0, -0.1, 1.0],
  "blockSelection": {
    "pos": [228, 3, 270],
    "face": "north",
    "hit": [228.4, 3.2, 270.1],
    "code": "game:soil"
  },
  "entitySelection": {
    "id": 160,
    "code": "survival:playerbot",
    "pos": [228.3, 3.0, 260.3]
  }
}
```

### POST /polis/command (extended)
Add a `context` object:
```json
{
  "cmd": "gotolook",
  "args": [],
  "context": {
    "playerUid": "player-uid",
    "useLookTarget": true,
    "spawnOffset": [0, 0, 2],
    "gotoOffset": [0, 0, 1]
  }
}
```

Context rules:
- `playerUid` selects the player anchor for offsets and look.
- `useLookTarget` uses server raytrace for target position.
- Offsets are applied in world axes (server-absolute).

### New harness commands
- `despawn` (remove selected or first bot).
- `selectlook` (select bot under player look ray).
- `gotolook` (move bot to look-derived target).

## State/Result Extensions

### /polis/state
Add timing and sequencing:
```json
{
  "LastAction": { "Name": "goto", "Ok": true, "Msg": "done" },
  "LastActionMs": 12345678,
  "LastActionId": 42
}
```

### /polis/bots
Include `lastAction` timing fields for each bot.

## Implementation Notes
- Track readiness using `IServerAPI.CurrentRunPhase` and/or
  `IServerEventAPI.ServerRunPhase(EnumServerRunPhase.WorldReady, ...)`.
- Use server-side raytrace (`IWorldAccessor.RayTraceForSelection`) from
  `player.Entity.ServerPos.XYZ + player.Entity.LocalEyePos`.
- Avoid client-only selections (`CurrentBlockSelection`) for harness endpoints.
- Use `Entity.ServerPos` as canonical coordinates in all outputs.

## Touchpoints
- `PolisTestHarness.cs`: add routes for status/players/player/look and parse
  command context.
- `PolisBuilderNpcSystem.cs`: add player lookup helpers and harness commands;
  record `LastAction` for goto outcomes.
- `docs/TESTING_HARNESS.md`: document intended usage flow and planned endpoints.
- `scripts/polis-http-smoke.py`: use `/polis/status` readiness gate.

## Acceptance Criteria
- `/polis/status` returns `worldReady=true` once ready; never blocks.
- `/polis/players` lists online players with server-absolute positions.
- `/polis/look` returns valid selection info when a player is looking at a block/entity.
- `gotolook` works via server raytrace with `playerUid` context.
- `/polis/state` exposes action timing fields for goto and pickup/drop.
