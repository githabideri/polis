# R1 Player Position and Look Direction APIs

**Date:** 2026-01-12

## Purpose
Identify server-safe APIs for player position, yaw/pitch, and raycast targets to support the agentic harness.

## Summary
- Player position/rotation lives on `IServerPlayer.Entity.ServerPos` (`EntityPos`) with `X/Y/Z`, `Yaw`, `Pitch` in radians; `Entity.SidedPos` returns `ServerPos` on server for shared code.
- Eye origin should be `player.Entity.ServerPos.XYZ + player.Entity.LocalEyePos` (server-safe) before raycasting.
- Look direction vector can be derived with `EntityPos.GetViewVector(pitch, yaw)` or by projecting a point using `Vec3d.AheadCopy(offset, pitch, yaw)`.
- Raycast target uses `IWorldAccessor.RayTraceForSelection(fromPos, pitch, yaw, range, ref BlockSelection, ref EntitySelection, ...)`, which is already used in `/polis interact` and `/polis gotolook`.
- `IPlayer.CurrentBlockSelection` / `CurrentEntitySelection` expose the client crosshair target but are client-driven; prefer server-side raytrace for harness determinism or headless contexts.
- Verified via `btca` (`vsapi`) on 2026-01-12.
- `btca` (`vssurvivalmod`) shows server-side aiming patterns that use `ServerPos` + `LocalEyePos`, and rideable movement using `SidedPos`.
- `btca` (`vscreativemod`) uses `CurrentBlockSelection` plus `Entity.SidedPos.GetViewVector()` for "look"-driven tools and selection workflows.

Minimal code sketch (no changes):
```csharp
var player = args.Caller.Player as IServerPlayer;
var eyePos = player.Entity.ServerPos.XYZ.AddCopy(player.Entity.LocalEyePos);
BlockSelection blockSel = null;
EntitySelection entSel = null;
sapi.World.RayTraceForSelection(
    eyePos,
    player.Entity.ServerPos.Pitch,
    player.Entity.ServerPos.Yaw,
    range,
    ref blockSel,
    ref entSel
);
var lookVec = EntityPos.GetViewVector(player.Entity.ServerPos.Pitch, player.Entity.ServerPos.Yaw);
```

## Evidence
- `PolisBuilderNpcSystem.cs` uses server yaw/pitch + eye position for raytrace in `/polis interact`. `PolisBuilderNpcSystem.cs:2056-2066`.
- `/polis gotolook` raytrace uses `player.Entity.ServerPos.Pitch/Yaw` and falls back to `eyePos.AheadCopy(...)`. `PolisBuilderNpcSystem.cs:2537-2578`.
- `EntityPos` defines `Yaw`, `Pitch`, `HeadYaw`, `HeadPitch` (radians): "`The rotation around the Y axis, in radians.`" and "`The rotation around the Z axis, in radians.`" `../vsapi/Common/Entity/EntityPos.cs:101-126`.
- `EntityPos.GetViewVector(pitch, yaw)` formula: "`return new Vec3f(-cosPitch * sinYaw, sinPitch, -cosPitch * cosYaw);`" `../vsapi/Common/Entity/EntityPos.cs:589-602`.
- `EntityPos.AheadCopy` formula: "`new EntityPos(x - cosPitch * sinYaw * offset, y + sinPitch * offset, z - cosPitch * cosYaw * offset, ...);`" `../vsapi/Common/Entity/EntityPos.cs:604-618`.
- `Entity.LocalEyePos` and `Entity.SidedPos` are available server-side. `../vsapi/Common/Entity/Entity.cs:428-438`.
- `Vec3d.AheadCopy(offset, Pitch, Yaw)` projects a point along look direction. `../vsapi/Math/Vector/Vec3d.cs:613-632`.
- `IWorldAccessor.RayTraceForSelection(...)` overloads for pitch/yaw/range and from/to. `../vsapi/Common/API/IWorldAccessor.cs:520-565`.
- `IPlayer.CurrentBlockSelection` / `CurrentEntitySelection` are defined as: "`The block the player is currently aiming at`" and "`The entity the player is currently aiming at`." `../vsapi/Common/Entity/Player/IPlayer.cs:48-56`.
- `BlockSelection` and `EntitySelection` carry hit position, face, and entity/block info. `../vsapi/Common/Collectible/Block/BlockSelection.cs:10-58`, `../vsapi/Common/Entity/EntitySelection.cs:8-33`.
- `vssurvivalmod` AI aiming uses `entity.ServerPos.XYZ.Add(0, entity.LocalEyePos.Y, 0)` (server-side position + eye height). `/home/mf/.local/share/btca/resources/vssurvivalmod/Entity/AITask/AiTaskTurretMode.cs:336`.
- `vssurvivalmod` uses `entity.Pos.AsBlockPos` for chunk lookup (non-look system; illustrates `Pos` usage). `/home/mf/.local/share/btca/resources/vssurvivalmod/Entity/AITask/AiTaskTurretMode.cs:313`.
- `vssurvivalmod` rideable behavior uses `entity.SidedPos` for seat position and yaw updates. `/home/mf/.local/share/btca/resources/vssurvivalmod/Entity/Behavior/BehaviorRideable.cs:29`, `/home/mf/.local/share/btca/resources/vssurvivalmod/Entity/Behavior/BehaviorRideable.cs:349-350`.
- `vscreativemod` uses `CurrentBlockSelection` for in-world tool actions, sending the selection in a packet. `/home/mf/.local/share/btca/resources/vscreativemod/WorldEditClientHandler.cs:155`.
- `vscreativemod` uses look direction from `Entity.SidedPos.GetViewVector()` to derive facing in tools/commands. `/home/mf/.local/share/btca/resources/vscreativemod/Tool/RepeatTool.cs:96-100`, `/home/mf/.local/share/btca/resources/vscreativemod/Tool/MoveTool.cs:60-67`, `/home/mf/.local/share/btca/resources/vscreativemod/Tool/ImportTool.cs:123-127`, `/home/mf/.local/share/btca/resources/vscreativemod/WorldEditCommands.cs:839-842`.
- `vscreativemod` uses `EntityPos.GetViewVector()` and `pos.Yaw` to resolve facing. `/home/mf/.local/share/btca/resources/vscreativemod/Workspace.cs:519-548`.
- `vscreativemod` falls back to `fromPlayer.Entity.Pos.AsBlockPos` when no selection is present. `/home/mf/.local/share/btca/resources/vscreativemod/WorldEdit.cs:211`.
- `vscreativemod` relies on `player.CurrentBlockSelection.Position` for command center positions. `/home/mf/.local/share/btca/resources/vscreativemod/WorldEdit.cs:429`.

## Open questions
- In `ResolveGotoLookTarget`, eye origin uses `player.Entity.Pos` (not `ServerPos`). Should this be normalized to `ServerPos`/`SidedPos` for server-only harness calls?
- How fresh are `CurrentBlockSelection` / `CurrentEntitySelection` on the server for remote players, and do they update when no client view exists (headless automation)?
- For player look direction, is `ServerPos.Yaw/Pitch` always equivalent to camera yaw/pitch, or do any modes require `HeadYaw/HeadPitch` instead?

## Implications for harness design
- Prefer server-side raytrace using `ServerPos` + `LocalEyePos` to avoid client-driven selection drift and to work with headless agent flows.
- Return both `BlockSelection` and `EntitySelection` fields (block pos, face, hit position, entity id) to make action verification explicit.
- Normalize all angles as radians and document that look vectors come from `GetViewVector` or `AheadCopy` with `ServerPos` yaw/pitch.
- Given vanilla AI aiming uses `ServerPos` + `LocalEyePos` and rideables rely on `SidedPos`, align harness look origin with `ServerPos`/`SidedPos` rather than `Entity.Pos` in server-only paths.
