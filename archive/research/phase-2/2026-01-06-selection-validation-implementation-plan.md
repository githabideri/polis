# Selection + Validation Implementation Plan (Phase 2.0.1)

**Date:** 2026-01-06

## Goal
Introduce a shared selection/validation layer for block actions (activate, break, place) without refactoring existing action classes. Enforce:
- Line of sight (LOS) from the player to the target block.
- Land claim permissions (Use vs BuildOrBreak).
- Consistent approach position based on selection face.

## Decisions
- **LOS source:** player line of sight (ray from player eye to target), not bot line of sight. This avoids false failures when the bot is still far away.
- **Claims:** use `ILandClaimAPI.TryAccess` to mirror vanilla feedback and messaging.

## Implementation Outline
1) Add helper in `PolisBuilderNpcSystem.cs`:
   - `TryValidateBlockTarget(...)`:
     - Inputs: `player`, `bot`, `BlockSelection`, `accessPos`, `EnumBlockAccessFlags`, `debugLog`.
     - Checks:
       - selection validity
       - claims via `TryAccess`
       - LOS via ray trace from player eye to target block center
     - Outputs:
       - `movePos` for `PolisGotoAction`
       - error if validation fails

2) Add LOS helper:
   - `HasLineOfSightToBlock(IServerPlayer player, BlockPos targetPos, out BlockSelection hitSel)`
   - Uses `IWorldAccessor.RayTraceForSelection(fromPos, toPos, ...)` and confirms the hit block matches `targetPos`.

3) Route block commands through validation:
   - `CmdActivate`: access `Use`, accessPos = target block.
   - `CmdBreak`: access `BuildOrBreak`, accessPos = target block.
   - `CmdPlace`: access `BuildOrBreak`, accessPos = placed block (`clickedPos + face`).
   - `CmdPlaceOn` / `CmdPlaceHeld`: access `BuildOrBreak`, accessPos = placed block.

4) Add a `/polis validate` debug command:
   - Inputs: `pos` and optional `access` (`use`/`break`/`build`/`place`/`traverse`).
   - Output: selection source, hit positions, LOS result, claim response, and bot range.

## Test Plan
- **LOS**: place a wall between player and target; run `/polis activate l[]` and `/polis break l[]`; expect failure.
- **Claims**: test in claimed land without permissions; expect denial for Use/BuildOrBreak actions.
- **Placement**: try `/polis place` on a face that is blocked from view; expect LOS failure.

## Notes
- Action classes keep their range checks; validation is only for LOS and claims.
- This step is intentionally minimal to avoid breaking existing primitives.

## Status (Validation)
- Verified: bot can walk to a chest and open it (container UI opens for the player).
- Verified: door activation works when selection face/hitpos is valid.
- Verified: LOS failures are logged and block the command when the target is occluded.

## Current Behavior (Observed)
- LOS uses a ray from the **player eye to the target block center**; it does not require the crosshair to be on the block.
- Block selection uses the player's current block selection **only if it matches the target position**; otherwise it falls back to **center hitpos + north face**.
- `activate` now calls `Block.OnBlockInteractStart(...)` when a player is present (so container blocks open without NREs). This opens the container UI **for the player**; it does not move items into/out of the bot.

## Known Limitations
- Face-sensitive blocks (doors, trapdoors, some multiblocks) may behave incorrectly when fallback face/hitpos is used.
- For those cases, `/polis activate l[]` works better because it uses the live selection face/hitpos.

## Possible Improvements
- **Require crosshair selection**: use player pitch/yaw ray and refuse if it does not hit the target (stricter LOS).
- **Bot-side selection**: ray trace from the bot’s eye at execution time to generate face + hitpos.
- **Explicit flags**: add `/polis activate <pos> [usebotlos|force]` to control selection strategy.
- **Container automation**: keep UI-opening for validation, but use container transfer (Step 2.0.5) for actual item movement and optionally suppress UI.
