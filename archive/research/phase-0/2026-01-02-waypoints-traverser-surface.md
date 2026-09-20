# Research: WaypointsTraverser Surface (VS 1.21.x)

## Context

We needed to locate the public surface of `WaypointsTraverser` / `PathTraverserBase` and any built-in path debug output for VS 1.21.x. The goal was to visualize paths and enable debug without relying on private fields.

## Prompt (deep research)

Find the 1.21.x source for `WaypointsTraverser`, `PathTraverserBase`, and `PathFindDebug`, document any exposed path node lists, and identify how debug/path rendering is enabled. Also identify how task AI holds the traverser and which methods are used in vanilla tasks.

## Findings (summary)

- Local sources exist in `vsessentialsmod/Entity/Pathfinding/Astar/WaypointsTraverser.cs` and `vsessentialsmod/Entity/Pathfinding/PathFindDebug.cs`.
- `PathFindDebug` renders highlights into slot `2` and does not clear them on completion; use custom highlights instead and disable it.
- `EntityBehaviorTaskAI` in VSEssentials owns a `WaypointsTraverser` reference:
  - `entity.GetBehavior<EntityBehaviorTaskAI>()?.PathTraverser`
  - The traverser is ticked via `OnGameTick()`.
- Vanilla tasks (e.g., `AiTaskStayCloseToEntity`) use:
  - `NavigateTo_Async(...)`
  - `Ready` / `Active`
  - `CurrentTarget` (mutated live)
  - `Retarget()` and `Stop()`
- Path nodes are not exposed in the obvious task-level surface; reflection is a practical fallback.
- `PathFindDebug` exists (VSEssentials) and draws gradients per node plus a final target marker.
- No obvious built-in path rendering API was found in the task code.

## TaskAI Attributes (from public sources)

`EntityBehaviorTaskAI` reads:
- `shuffle` (bool)
- `aiCreatureType` (string)
- `aitasks` (array of task configs)

Example task-level keys (from `AiTaskStayCloseToEntity`):
- `movespeed`, `searchRange`, `maxDistance`
- `minSeekSeconds`, `onlyIfLowerId`
- `entityCode`, `allowTeleport`, `teleportAfterRange`, `teleportToRange`, `teleportMaxRange`

## Proposed Debug Pipeline

- Server: extract nodes from traverser via reflection or internal list.
- Network: send to client (custom packet).
- Client: render as line segments + markers.

## Source Links (from research)

- BehaviorTaskAI:
  - `https://github.com/anegostudios/vsessentialsmod/blob/master/Entity/AI/Task/BehaviorTaskAI.cs`
- AiTaskStayCloseToEntity:
  - `https://github.com/anegostudios/vsessentialsmod/blob/master/Entity/AI/Task/TasksImpl/AiTaskStayCloseToEntity.cs`

## Next Step

Decompile local 1.21.6 assemblies to capture:
- `WaypointsTraverser` internal path list member names.
- `PathFindDebug` behavior and enable toggle.
