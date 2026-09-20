# Harness Extension: Activate + Targets (Implementation Plan)

Date: 2026-01-13  
Status: Planned (awaiting approval)  
Phase Fit: Phase 2 enablement (testing infrastructure)

## Purpose
Extend the HTTP harness so agents can:
1) **Activate** blocks via the same server-side path as in-game `/polis activate`.
2) **Discover nearby interactables** (blocks/entities) with structured metadata for verification.

This removes reliance on chat parsing, avoids coordinate ambiguity, and gives
deterministic, machine-readable outputs for automated tests.

## Context + Constraints
- All harness actions are **server-authoritative** and must use absolute coords.
- Do **not** rely on `CurrentBlockSelection` or chat selectors (`l[]`); those are client-side or stale server-side.
- Use server raytrace (`ResolveGotoLookTarget`) with a real `IServerPlayer`.
- Coordinate handling follows `docs/research/misc/2026-01-13-coordinate-systems-deep-dive-validation.md`.

## API Additions

### 1) Command: `activate`
**POST** `/polis/command` with:
```json
{"cmd":"activate","args":["x","y","z"]}
```
or look-based:
```json
{"cmd":"activate","context":{"playerUid":"...","useLookTarget":true}}
```

**Rules:**
- If 3 args are provided, treat them as **absolute server coords**.
- Always require `context.playerUid` (for claims + LOS validation).
- Otherwise require `context.useLookTarget`.
- Resolve target block via server raytrace, validate, then run
  `PolisGotoAction` + `PolisActivateBlockAction`.
- Record `LastAction` as `activate`.

### 2) Endpoint: `GET /polis/targets`
**Query params:**
- `playerUid` (required)
- `radius` (default 6, clamp to a sane max like 16)
- `limit` (default 20)
- `mode` = `blocks` | `entities` | `all` (default `blocks`)

**Response (shape):**
```json
{
  "ok": true,
  "center": [x, y, z],
  "radius": 6,
  "blocks": [
    {
      "pos": [x, y, z],
      "code": "game:chest-east",
      "dist": 2.4,
      "entityClass": "chest",
      "placedPriorityInteract": true,
      "behaviors": ["BlockBehaviorContainer", "BlockBehaviorInteract"],
      "reasons": ["EntityClass", "BlockBehaviors", "PlacedPriorityInteract"]
    }
  ],
  "entities": [
    {
      "id": 12345,
      "code": "game:item-wood",
      "class": "EntityItem",
      "pos": [x, y, z],
      "dist": 3.2
    }
  ]
}
```

## Interaction Heuristics (blocks)
Include a block in `/polis/targets` if **any** of:
- `Block.EntityClass` is not empty
- `Block.BlockBehaviors` contains entries
- `Block.PlacedPriorityInteract == true`

These are **heuristics**, not guarantees. They map to real interaction hooks:
- `Block.OnBlockInteractStart/Step/Stop` (Block.cs)
- `BlockBehavior.OnBlockInteractStart/Step/Stop` (BlockBehavior.cs)
- `PlacedPriorityInteract` only affects ordering, but is a useful signal.

## Implementation Steps

### A) `PolisBuilderNpcSystem.cs`
1) Add `activate` to `ExecuteHarnessCommand` switch and error message.
2) Implement `ExecuteActivateCommand(...)`:
   - Resolve target:
     - If 3 args, parse as absolute `Vec3d`.
     - Else: require `context.playerUid` and `context.useLookTarget`, then
       call `ResolveGotoLookTarget`.
   - Build `BlockSelection` using `ResolveSelection`.
   - Validate with `TryValidateBlockTarget(..., EnumBlockAccessFlags.Use)`.
   - Start `PolisGotoAction` + `PolisActivateBlockAction`.
   - Call `bot.RecordActionResult("activate", ok, msg, timeMs)` via callback.

### B) `PolisTestHarness.cs`
1) Add `GET /polis/targets` route:
   - Validate `playerUid`.
   - Compute center from player `ServerPos`.
   - Scan blocks/entities within `radius`.
2) Add serialization DTOs or anonymous objects for response.
3) Add `/polis/targets` to the root endpoint listing.

## Testing + Verification Plan (with reasons)

1) **Readiness + player context**
   - `GET /polis/status` and `GET /polis/players`
   - Reason: ensures world ready and provides valid `playerUid`.

2) **Targets scan (blocks)**
   - `GET /polis/targets?playerUid=...&radius=6&limit=10&mode=blocks`
   - Reason: confirm interactables surface with explicit `reasons[]`.

3) **Raytrace cross-check**
   - `GET /polis/look?uid=...` while aiming at door/chest.
   - Reason: confirm server raytrace and targets list align.

4) **Activate via look target**
   - `POST /polis/command` with `activate` + `useLookTarget`.
   - Reason: primary agentic path; should visibly toggle door/chest.

5) **Activate via absolute coords**
   - Use coordinates from `/polis/targets` to activate the same block.
   - Reason: secondary path; proves coordinate path works without selection.

6) **Negative cases**
   - Missing `playerUid` + no coords → usage error.
   - Invalid coords → `No block at target position`.
   - Claimed blocks → permission error (if claims are active).
   - Reason: verify guard rails + error messaging.

7) **Targets scan (entities)**
   - Drop an item near the player; call `mode=entities`.
   - Reason: confirm entity listing works (for future interact/pickup flows).

8) **Logs + harness output**
   - Check `../vsdata/Logs/server-main.log` for `[polis]` entries.
   - Capture JSON outputs for `docs/TESTING_HARNESS_OUTPUTS.md`.
   - Reason: cross-validate harness signals vs actual action execution.

## Documentation Updates (after implementation)
- `docs/TESTING_HARNESS.md`: add `/polis/targets` and `activate` command.
- `docs/TECHNICAL.md`: update endpoints + command list.
- `docs/TESTING_HARNESS_OUTPUTS.md`: add example outputs for new endpoints.
- `docs/journal/YYYY-MM-DD-...md`: record test run findings.

## Open Questions / Risks
- **False positives:** some blocks expose behaviors but are not meaningfully interactive.
  Mitigation: return `reasons[]` so consumers can decide.
- **Scan cost:** block scans grow quickly with radius; cap radius to avoid lag.
- **Claims/permissions:** `TryValidateBlockTarget` should enforce `Use` access.
- **Selection reliability:** only rely on server raytrace, never client selection.
