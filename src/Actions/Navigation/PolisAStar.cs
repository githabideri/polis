using System;
using System.Collections.Generic;
using System.Linq;
using Vintagestory.API.Common;
using Vintagestory.API.MathTools;

namespace Polis.Actions.Navigation;

/// <summary>
/// Custom A* pathfinder with fence and door awareness.
/// Based on vsvillage's VillagerAStarNew but with explicit fence blocking.
/// </summary>
public class PolisAStar
{
    /// <summary>
    /// Block codes treated as passable (can walk through when open/interacted with).
    /// </summary>
    public List<string> TraversableCodes { get; set; } = new() { "door", "gate", "ladder", "trapdoor" };

    /// <summary>
    /// Block codes that need interaction (open/close) to pass through.
    /// </summary>
    public List<string> InteractableCodes { get; set; } = new() { "door", "gate", "trapdoor" };

    /// <summary>
    /// Block codes that can be stepped on (even if not full blocks).
    /// </summary>
    public List<string> SteppableCodes { get; set; } = new() { "stair", "path", "bed-", "farmland", "slab" };

    /// <summary>
    /// Block codes that ALWAYS block movement, even if collision box seems small.
    /// Fences have small collision boxes but should still block.
    /// </summary>
    public List<string> BlockingCodes { get; set; } = new() { "fence" };

    /// <summary>
    /// Maximum height an entity can step up.
    /// </summary>
    public float StepHeight { get; set; } = 1.5f;

    /// <summary>
    /// Maximum height an entity can fall.
    /// </summary>
    public int MaxFallHeight { get; set; } = 5;

    readonly ICachingBlockAccessor blockAccessor;
    readonly Action<string> debugLog;

    public PolisAStar(ICachingBlockAccessor blockAccessor, Action<string> debugLog = null)
    {
        this.blockAccessor = blockAccessor;
        this.debugLog = debugLog;
    }

    /// <summary>
    /// Find a path from start to end position.
    /// </summary>
    /// <param name="start">Starting block position</param>
    /// <param name="end">Target block position</param>
    /// <param name="searchDepth">Maximum nodes to search</param>
    /// <returns>List of path nodes, or null if no path found</returns>
    public List<PolisPathNode> FindPath(BlockPos start, BlockPos end, int searchDepth = 5000)
    {
        if (start == null || end == null) return null;

        blockAccessor.Begin();

        var startNode = new PolisPathNode(start, end, NeedsInteraction(blockAccessor.GetBlock(start)));
        var reachableNodes = new SortedSet<PolisPathNode>(new PolisPathNodeComparer()) { startNode };
        var visitedNodes = new HashSet<PolisPathNode>();

        for (int i = 0; i < searchDepth && reachableNodes.Count > 0; i++)
        {
            var currentNode = reachableNodes.Min;

            if (currentNode.BlockPos.Equals(end))
            {
                debugLog?.Invoke($"[PolisAStar] path found in {i} iterations, {visitedNodes.Count} nodes visited");
                return currentNode.RetracePath();
            }

            reachableNodes.Remove(currentNode);
            visitedNodes.Add(currentNode);

            foreach (var neighbor in FindValidNeighborNodes(currentNode))
            {
                if (!visitedNodes.Contains(neighbor) && IsTraversable(neighbor, end))
                {
                    reachableNodes.Add(neighbor);
                }
            }
        }

        debugLog?.Invoke($"[PolisAStar] no path found after {searchDepth} iterations");
        return null;
    }

    /// <summary>
    /// Get valid neighbor positions from a node.
    /// </summary>
    IEnumerable<PolisPathNode> FindValidNeighborNodes(PolisPathNode current)
    {
        var neighbors = new[]
        {
            new PolisPathNode(current, Cardinal.North),
            new PolisPathNode(current, Cardinal.East),
            new PolisPathNode(current, Cardinal.South),
            new PolisPathNode(current, Cardinal.West)
        };

        // Handle climbable blocks (ladders)
        var currentBlock = blockAccessor.GetBlock(current.BlockPos);
        if (IsClimbable(currentBlock))
        {
            HandleClimbable(current, currentBlock, neighbors);
        }

        return neighbors;
    }

    /// <summary>
    /// Adjust neighbor node for climbing if on a climbable block.
    /// </summary>
    void HandleClimbable(PolisPathNode current, Block currentBlock, PolisPathNode[] neighbors)
    {
        var variant = currentBlock.Variant?["side"];
        if (variant == null) return;

        int climbIndex = variant switch
        {
            "north" => 0,
            "east" => 1,
            "south" => 2,
            _ => 3
        };

        // Find how high the ladder goes
        int height = 1;
        while (TraversableCodes.Exists(code => blockAccessor.GetBlock(current.BlockPos.UpCopy(height)).Code?.Path?.Contains(code) == true))
        {
            height++;
        }

        if (height > 1)
        {
            neighbors[climbIndex].BlockPos.Y += height;
        }
    }

    /// <summary>
    /// Check if a node is traversable (can be walked through or on).
    /// </summary>
    bool IsTraversable(PolisPathNode node, BlockPos target)
    {
        // Target is always reachable
        if (target.Equals(node.BlockPos)) return true;

        var blockAtNode = blockAccessor.GetBlock(node.BlockPos);
        var blockAbove = blockAccessor.GetBlock(node.BlockPos.UpCopy());

        // Check if we can stand in this position (2 block tall space)
        if (!IsBlockTraversable(blockAtNode) || !IsBlockTraversable(blockAbove))
        {
            // Try stepping up
            return TryStepUp(node, target);
        }

        // Find ground level (handle falling)
        return TryFindGround(node, target);
    }

    /// <summary>
    /// Try to step up onto higher terrain.
    /// </summary>
    bool TryStepUp(PolisPathNode node, BlockPos target)
    {
        for (float stepLeft = StepHeight; stepLeft > 1f; stepLeft--)
        {
            node.BlockPos.Y++;
            var below = blockAccessor.GetBlock(node.BlockPos.DownCopy());
            var atNode = blockAccessor.GetBlock(node.BlockPos);
            var above = blockAccessor.GetBlock(node.BlockPos.UpCopy());

            if (CanStep(below) && IsBlockTraversable(atNode) && IsBlockTraversable(above))
            {
                node.Init(target, NeedsInteraction(atNode));
                return true;
            }
        }
        return false;
    }

    /// <summary>
    /// Find ground level, handling falls and climbables.
    /// </summary>
    bool TryFindGround(PolisPathNode node, BlockPos target)
    {
        // Try falling
        for (int fallLeft = MaxFallHeight; fallLeft >= 0; fallLeft--)
        {
            var below = blockAccessor.GetBlock(node.BlockPos.DownCopy());

            if (CanStep(below))
            {
                node.Init(target, NeedsInteraction(blockAccessor.GetBlock(node.BlockPos)));
                return true;
            }

            if (!IsBlockTraversable(below))
            {
                return false;
            }

            node.BlockPos.Y--;
        }

        // Try climbing down
        while (IsClimbable(blockAccessor.GetBlock(node.BlockPos)))
        {
            var below = blockAccessor.GetBlock(node.BlockPos.DownCopy());
            if (CanStep(below))
            {
                node.Init(target, NeedsInteraction(blockAccessor.GetBlock(node.BlockPos)));
                return true;
            }
            node.BlockPos.Y--;
        }

        return false;
    }

    /// <summary>
    /// Check if a block can be walked through.
    /// </summary>
    bool IsBlockTraversable(Block block)
    {
        if (block == null) return false;

        var path = block.Code?.Path;
        if (path == null) return false;

        // Explicit blocking codes (fences) - always block
        if (BlockingCodes.Exists(code => path.Contains(code)))
        {
            // Exception: fence gates can be passed through
            if (path.Contains("fencegate") || path.Contains("gate"))
            {
                return true; // Gates are traversable (will be opened)
            }
            return false;
        }

        // No collision = passable
        if (block.CollisionBoxes == null || block.CollisionBoxes.Length == 0)
        {
            return true;
        }

        // Traversable codes (doors, gates, ladders) = passable
        if (TraversableCodes.Exists(code => path.Contains(code)))
        {
            return true;
        }

        return false;
    }

    /// <summary>
    /// Check if a block can be stepped on (stood upon).
    /// </summary>
    bool CanStep(Block block)
    {
        if (block == null) return false;

        // Solid top = steppable
        if (block.SideSolid[BlockFacing.UP.Index])
        {
            return true;
        }

        // Steppable codes (stairs, slabs, paths)
        var path = block.Code?.Path;
        if (path != null && SteppableCodes.Exists(code => path.Contains(code)))
        {
            return true;
        }

        return false;
    }

    /// <summary>
    /// Check if a block is climbable (ladder).
    /// </summary>
    bool IsClimbable(Block block)
    {
        var path = block?.Code?.Path;
        return path != null && path.Contains("ladder");
    }

    /// <summary>
    /// Check if a block requires interaction (door/gate) to pass.
    /// </summary>
    bool NeedsInteraction(Block block)
    {
        var path = block?.Code?.Path;
        return path != null && InteractableCodes.Exists(code => path.Contains(code));
    }

    /// <summary>
    /// Get a valid start position near the given position.
    /// Handles cases where entity is slightly inside a block: the escape
    /// is UP (the cell above a sunk body is air/plant), not horizontal -
    /// a body buried in a flat soil layer has solid neighbours on every
    /// side at the same level, so only the cell above is open.
    /// </summary>
    public BlockPos GetStartPos(Vec3d startPos)
    {
        blockAccessor.Begin();
        var result = startPos.AsBlockPos;
        var startBlock = blockAccessor.GetBlock(result);

        if (IsBlockTraversable(startBlock))
        {
            return result;
        }

        // Sunk one block: the cell above the feet is the valid stand
        // position (air/plant), with air/plant above that too.
        var above = result.UpCopy();
        if (IsBlockTraversable(blockAccessor.GetBlock(above))
            && IsBlockTraversable(blockAccessor.GetBlock(above.UpCopy())))
        {
            return above;
        }

        // Try adjacent positions
        var offsets = new[]
        {
            (0, 0, -1), // North
            (0, 0, 1),  // South
            (-1, 0, 0), // West
            (1, 0, 0),  // East
        };

        foreach (var (dx, dy, dz) in offsets)
        {
            var adjacent = result.AddCopy(dx, dy, dz);
            if (IsBlockTraversable(blockAccessor.GetBlock(adjacent)))
            {
                return adjacent;
            }
        }

        return result;
    }

    /// <summary>
    /// Convert path nodes to waypoints for traversal.
    /// </summary>
    public static List<Vec3d> ToWaypoints(List<PolisPathNode> path)
    {
        if (path == null) return null;

        var waypoints = new List<Vec3d>(path.Count);
        // Skip first node (current position)
        for (int i = 1; i < path.Count; i++)
        {
            waypoints.Add(path[i].ToWaypoint());
        }
        return waypoints;
    }

    /// <summary>
    /// Get path nodes that require interaction (doors/gates).
    /// </summary>
    public static List<PolisPathNode> GetInteractionNodes(List<PolisPathNode> path)
    {
        if (path == null) return new List<PolisPathNode>();
        return path.Where(n => n.NeedsInteraction).ToList();
    }
}

/// <summary>
/// Comparer for PolisPathNode to handle equal costs properly in SortedSet.
/// </summary>
class PolisPathNodeComparer : IComparer<PolisPathNode>
{
    public int Compare(PolisPathNode x, PolisPathNode y)
    {
        if (x == null || y == null) return 0;

        int costCompare = x.Cost.CompareTo(y.Cost);
        if (costCompare != 0) return costCompare;

        // Tie-breaker using position to ensure uniqueness
        int xCompare = x.BlockPos.X.CompareTo(y.BlockPos.X);
        if (xCompare != 0) return xCompare;

        int yCompare = x.BlockPos.Y.CompareTo(y.BlockPos.Y);
        if (yCompare != 0) return yCompare;

        return x.BlockPos.Z.CompareTo(y.BlockPos.Z);
    }
}
