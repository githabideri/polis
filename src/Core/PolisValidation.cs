using Vintagestory.API.Common;
using Vintagestory.API.Common.Entities;
using Vintagestory.API.MathTools;
using Vintagestory.API.Server;

namespace Polis.Core;

/// <summary>
/// Shared validation helpers for Polis actions.
/// Eliminates duplicated validation logic across action classes.
/// </summary>
public static class PolisValidation
{
    /// <summary>
    /// Check if entity is within range of a block position.
    /// </summary>
    public static bool IsInRange(Entity entity, BlockPos pos, float range, out string error)
    {
        error = null;
        if (entity == null)
        {
            error = "Entity is null";
            return false;
        }

        var entityPos = entity.ServerPos?.XYZ ?? entity.Pos?.XYZ;
        if (entityPos == null)
        {
            error = "Entity position is null";
            return false;
        }

        var targetCenter = pos.ToVec3d().Add(0.5, 0.5, 0.5);
        var dist = entityPos.DistanceTo(targetCenter);

        if (dist > range)
        {
            error = $"Too far from target ({dist:F1} > {range})";
            return false;
        }
        return true;
    }

    /// <summary>
    /// Try to get a block entity of specific type at position.
    /// </summary>
    public static bool TryGetBlockEntity<T>(IWorldAccessor world, BlockPos pos,
        out T blockEntity, out string error) where T : class
    {
        error = null;
        blockEntity = null;

        if (world == null)
        {
            error = "World is null";
            return false;
        }

        if (pos == null)
        {
            error = "Position is null";
            return false;
        }

        blockEntity = world.BlockAccessor.GetBlockEntity(pos) as T;
        if (blockEntity == null)
        {
            var block = world.BlockAccessor.GetBlock(pos);
            var blockCode = block?.Code?.ToString() ?? "unknown";
            error = $"No {typeof(T).Name} at position (block is {blockCode})";
            return false;
        }
        return true;
    }

    /// <summary>
    /// Check if player has access to block via land claims system.
    /// </summary>
    public static bool HasClaimsAccess(IServerPlayer player, BlockPos pos,
        EnumBlockAccessFlags flags, IWorldAccessor world, out string error)
    {
        error = null;

        if (player == null)
        {
            // No player means no claims check needed
            return true;
        }

        if (world == null)
        {
            error = "World is null";
            return false;
        }

        var claims = world.Claims;
        if (claims == null)
        {
            // No claims system means access granted
            return true;
        }

        var response = claims.TestAccess(player, pos, flags);
        if (response != EnumWorldAccessResponse.Granted)
        {
            error = "No permission (land claims)";
            return false;
        }
        return true;
    }

    /// <summary>
    /// Validate that a block exists and is not air at the given position.
    /// </summary>
    public static bool BlockExists(IWorldAccessor world, BlockPos pos, out string error)
    {
        error = null;

        if (world == null)
        {
            error = "World is null";
            return false;
        }

        if (pos == null)
        {
            error = "Position is null";
            return false;
        }

        var block = world.BlockAccessor.GetBlock(pos);
        if (block == null || block.Id == 0)
        {
            error = "No block at target position";
            return false;
        }
        return true;
    }
}
