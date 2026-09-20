using System;
using System.Collections.Generic;
using Vintagestory.API.MathTools;

namespace PolisBuilderNpc.Actions.Navigation;

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
        Cost = blockPos.DistanceSqTo(target.X, target.Y, target.Z);
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
        Cost = GCost + BlockPos.DistanceSqTo(target.X, target.Y, target.Z);
        NeedsInteraction = needsInteraction;
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
