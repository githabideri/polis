using System;
using System.Collections.Generic;
using Vintagestory.API.MathTools;

namespace Polis.Actions.Navigation;

/// <summary>
/// A path node that tracks door/gate interaction requirements.
/// Used by PolisAStar for fence-aware pathfinding.
/// </summary>
public class PolisPathNode : IEquatable<PolisPathNode>, IComparable<PolisPathNode>
{
    public PolisPathNode Parent;
    public BlockPos BlockPos;

    /// <summary>
    /// True if this node requires door/gate interaction to pass through.
    /// </summary>
    public bool NeedsInteraction;

    /// <summary>
    /// Cost from start to this node (g cost) plus heuristic to target (h cost).
    /// </summary>
    public float Cost;

    /// <summary>
    /// Cost from start to this node.
    /// </summary>
    public float GCost;

    public PolisPathNode(BlockPos blockPos, BlockPos target, bool needsInteraction = false)
    {
        BlockPos = blockPos.Copy();
        GCost = 0;
        // F6 (2026-10-10): admissible LINEAR heuristic (vsvillage's
        // VillagerPathNode: sqrt(DistanceSqTo)). The squared value was
        // non-admissible: f = g + h was dominated by h at distance, so
        // the frontier stopped widening and the search oscillated
        // around obstacles on multi-step terrain (measured 2026-10-10).
        Cost = DistanceTo(target);
        NeedsInteraction = needsInteraction;
    }

    public PolisPathNode(PolisPathNode parent, Cardinal cardinal)
    {
        Parent = parent;
        BlockPos = parent.BlockPos.AddCopy(cardinal.Normali.X, cardinal.Normali.Y, cardinal.Normali.Z);
        GCost = parent.GCost + 1;
    }

    /// <summary>
    /// Initialize cost and interaction flag after determining traversability.
    /// </summary>
    public void Init(BlockPos target, bool needsInteraction)
    {
        // F6 (2026-10-10): admissible linear heuristic, matching the
        // start-node constructor (see F6 comment there). GCost is
        // untouched: F9's slope penalty is applied at neighbor creation
        // and must survive re-Init (TryStepUp / TryFindGround).
        Cost = GCost + DistanceTo(target);
        NeedsInteraction = needsInteraction;
    }

    /// <summary>
    /// F6 (2026-10-10): Euclidean distance to the target in blocks
    /// (admissible for the 1-per-step g-cost).
    /// </summary>
    public float DistanceTo(BlockPos target)
    {
        return (float)Math.Sqrt(BlockPos.DistanceSqTo(target.X, target.Y, target.Z));
    }

    /// <summary>
    /// Convert to waypoint for path traversal (center of block).
    /// </summary>
    public Vec3d ToWaypoint()
    {
        return new Vec3d(BlockPos.X + 0.5, BlockPos.Y, BlockPos.Z + 0.5);
    }

    /// <summary>
    /// Retrace path from this node back to start.
    /// </summary>
    public List<PolisPathNode> RetracePath()
    {
        var current = this;
        var result = new List<PolisPathNode> { current };
        while (current.Parent != null)
        {
            current = current.Parent;
            result.Add(current);
        }
        result.Reverse();
        return result;
    }

    public bool Equals(PolisPathNode other)
    {
        return BlockPos.Equals(other?.BlockPos);
    }

    public override bool Equals(object obj)
    {
        return obj is PolisPathNode other && Equals(other);
    }

    public override int GetHashCode()
    {
        return BlockPos.GetHashCode();
    }

    public int CompareTo(PolisPathNode other)
    {
        return Cost.CompareTo(other.Cost);
    }
}
