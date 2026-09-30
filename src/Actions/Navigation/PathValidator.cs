using System;
using System.Collections.Generic;
using Vintagestory.API.Common;
using Vintagestory.API.MathTools;

namespace Polis.Actions.Navigation;

/// <summary>
/// Validates paths and line-of-sight for navigation.
/// Catches cases where the bot might try to walk through fences or walls.
/// </summary>
public class PathValidator
{
    /// <summary>
    /// Block codes that block LOS and movement.
    /// </summary>
    public List<string> BlockingCodes { get; set; } = new() { "fence", "wall", "palisade" };

    /// <summary>
    /// Block codes that are passable (doors, gates).
    /// </summary>
    public List<string> PassableCodes { get; set; } = new() { "door", "gate", "trapdoor", "ladder" };

    readonly ICachingBlockAccessor blockAccessor;
    readonly Action<string> debugLog;

    public PathValidator(ICachingBlockAccessor blockAccessor, Action<string> debugLog = null)
    {
        this.blockAccessor = blockAccessor;
        this.debugLog = debugLog;
    }

    /// <summary>
    /// Check if there's a clear line-of-sight between two positions.
    /// Uses Bresenham's line algorithm to check all blocks along the path.
    /// </summary>
    /// <param name="from">Starting position</param>
    /// <param name="to">Target position</param>
    /// <returns>True if LOS is clear, false if blocked</returns>
    public bool HasClearLOS(Vec3d from, Vec3d to)
    {
        blockAccessor.Begin();

        var fromBlock = from.AsBlockPos;
        var toBlock = to.AsBlockPos;

        // Same block = clear
        if (fromBlock.Equals(toBlock)) return true;

        // Walk the line
        foreach (var pos in BresenhamLine3D(fromBlock, toBlock))
        {
            if (pos.Equals(fromBlock) || pos.Equals(toBlock)) continue;

            // Check both foot level and head level
            if (IsBlockBlocking(pos) || IsBlockBlocking(pos.UpCopy()))
            {
                debugLog?.Invoke($"[PathValidator] LOS blocked at {pos}");
                return false;
            }
        }

        return true;
    }

    /// <summary>
    /// Validate that a path doesn't pass through blocking terrain.
    /// </summary>
    /// <param name="waypoints">List of waypoints in the path</param>
    /// <returns>True if path is valid, false if it crosses blocking terrain</returns>
    public bool ValidatePath(List<Vec3d> waypoints)
    {
        if (waypoints == null || waypoints.Count < 2) return true;

        blockAccessor.Begin();

        for (int i = 0; i < waypoints.Count - 1; i++)
        {
            if (!ValidateSegment(waypoints[i], waypoints[i + 1]))
            {
                debugLog?.Invoke($"[PathValidator] path segment {i} invalid: {waypoints[i]} -> {waypoints[i + 1]}");
                return false;
            }
        }

        return true;
    }

    /// <summary>
    /// Validate a single path segment between two waypoints.
    /// </summary>
    bool ValidateSegment(Vec3d from, Vec3d to)
    {
        var fromBlock = from.AsBlockPos;
        var toBlock = to.AsBlockPos;

        // Adjacent blocks don't need full line check
        if (Math.Abs(fromBlock.X - toBlock.X) <= 1 &&
            Math.Abs(fromBlock.Y - toBlock.Y) <= 1 &&
            Math.Abs(fromBlock.Z - toBlock.Z) <= 1)
        {
            // Just check the target position
            return !IsBlockBlocking(toBlock) && !IsBlockBlocking(toBlock.UpCopy());
        }

        // Check all blocks along the line
        foreach (var pos in BresenhamLine3D(fromBlock, toBlock))
        {
            if (IsBlockBlocking(pos) || IsBlockBlocking(pos.UpCopy()))
            {
                return false;
            }
        }

        return true;
    }

    /// <summary>
    /// Check if a block is blocking (fence, wall, etc.).
    /// </summary>
    bool IsBlockBlocking(BlockPos pos)
    {
        var block = blockAccessor.GetBlock(pos);
        if (block == null) return false;

        var path = block.Code?.Path;
        if (path == null) return false;

        // Passable blocks are not blocking
        if (PassableCodes.Exists(code => path.Contains(code)))
        {
            return false;
        }

        // Explicit blocking codes
        if (BlockingCodes.Exists(code => path.Contains(code)))
        {
            return true;
        }

        // Blocks with collision boxes block movement
        if (block.CollisionBoxes != null && block.CollisionBoxes.Length > 0)
        {
            // Full solid block
            if (block.SideSolid[BlockFacing.UP.Index] &&
                block.SideSolid[BlockFacing.DOWN.Index])
            {
                return true;
            }
        }

        return false;
    }

    /// <summary>
    /// Find the first blocking position along a line.
    /// </summary>
    /// <param name="from">Starting position</param>
    /// <param name="to">Target position</param>
    /// <returns>Blocking position, or null if clear</returns>
    public BlockPos FindBlockingPosition(Vec3d from, Vec3d to)
    {
        blockAccessor.Begin();

        var fromBlock = from.AsBlockPos;
        var toBlock = to.AsBlockPos;

        foreach (var pos in BresenhamLine3D(fromBlock, toBlock))
        {
            if (pos.Equals(fromBlock)) continue;

            if (IsBlockBlocking(pos) || IsBlockBlocking(pos.UpCopy()))
            {
                return pos;
            }
        }

        return null;
    }

    /// <summary>
    /// 3D Bresenham line algorithm - returns all block positions along a line.
    /// </summary>
    static IEnumerable<BlockPos> BresenhamLine3D(BlockPos from, BlockPos to)
    {
        int x0 = from.X, y0 = from.Y, z0 = from.Z;
        int x1 = to.X, y1 = to.Y, z1 = to.Z;

        int dx = Math.Abs(x1 - x0), sx = x0 < x1 ? 1 : -1;
        int dy = Math.Abs(y1 - y0), sy = y0 < y1 ? 1 : -1;
        int dz = Math.Abs(z1 - z0), sz = z0 < z1 ? 1 : -1;

        int dm = Math.Max(dx, Math.Max(dy, dz));

        int i = dm;
        x1 = y1 = z1 = dm / 2;

        while (true)
        {
            yield return new BlockPos(x0, y0, z0, from.dimension);

            if (i-- == 0) break;

            x1 -= dx; if (x1 < 0) { x1 += dm; x0 += sx; }
            y1 -= dy; if (y1 < 0) { y1 += dm; y0 += sy; }
            z1 -= dz; if (z1 < 0) { z1 += dm; z0 += sz; }
        }
    }
}
