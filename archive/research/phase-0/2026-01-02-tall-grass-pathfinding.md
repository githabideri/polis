# Research: Tall Grass Blocks A* (VS 1.21.x)

## Context

We observed that A* pathfinding fails when a surface has tall grass on top. Without tall grass, the same ground is traversable. The bot uses `WaypointsTraverser` A* in VSEssentials.

## Prompt (deep research)

Find in VS 1.21.6 where A* decides whether a block is traversable and why tall grass blocks the path. Identify the relevant classes, file paths, and any flags/attributes that affect passability (step height, collision box, creature type). Provide code references and patch points.

## Findings (summary)

- A* and waypoint traversal live in VSEssentials:
  - `Entity/Pathfinding/Astar/WaypointsTraverser.cs`
  - `Entity/Pathfinding/Astar/AStar.cs` (traversable checks, DeepWiki noted ~141-302)
  - `Entity/Pathfinding/StraightLineTraverser.cs`
- A* uses a `CollisionTester` for clearance/collision checks.
- Pathfinding task inputs include creature type, step height, max fall height, and collision box. The API class `PathfinderTask` exposes these fields:
  - `CreatureType`, `searchDepth`, `stepHeight`, `maxFallHeight`, `collisionBox`.
- The observed behavior matches a clearance/collision rejection: tall grass likely occupies the "standing volume" and is treated as a collider by `traversable()`.

## Proposed Fix Directions

Option A (preferred): Patch `AStar.traversable()` to treat tall grass as passable during clearance checks, without changing collision for other blocks.

Option B: Patch the `CollisionTester` used by A* to ignore tall grass during path validation.

Both approaches should be scoped narrowly to tall grass (or specific plant codes) rather than all plants.

## Source Links

- WaypointsTraverser:
  - `https://github.com/anegostudios/vsessentialsmod/blob/1dbb5c79/Entity/Pathfinding/Astar/WaypointsTraverser.cs`
- AStar:
  - `https://github.com/anegostudios/vsessentialsmod/blob/1dbb5c79/Entity/Pathfinding/Astar/AStar.cs`
- StraightLineTraverser:
  - `https://github.com/anegostudios/vsessentialsmod/blob/1dbb5c79/Entity/Pathfinding/StraightLineTraverser.cs`

## Notes / Next Step

If the raw method bodies are available (via local decompile), identify the exact `traversable()` rejection branch for tall grass and implement a small Harmony patch that treats that block code as passable.
