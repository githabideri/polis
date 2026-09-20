using System;
using System.Collections.Generic;
using Vintagestory.API.Common;
using Vintagestory.API.Common.Entities;
using Vintagestory.API.Datastructures;
using Vintagestory.API.MathTools;
using Vintagestory.GameContent;

namespace PolisBuilderNpc.Actions.Navigation;

/// <summary>
/// Handles door and gate interactions for pathfinding.
/// Allows bots to open/close doors and gates along their path.
/// </summary>
public class DoorInteractionHandler
{
    /// <summary>
    /// Block codes that can be interacted with (opened/closed).
    /// </summary>
    public List<string> InteractableCodes { get; set; } = new() { "door", "gate", "trapdoor" };

    readonly IWorldAccessor world;
    readonly Action<string> debugLog;

    public DoorInteractionHandler(IWorldAccessor world, Action<string> debugLog = null)
    {
        this.world = world;
        this.debugLog = debugLog;
    }

    /// <summary>
    /// Check if there's a door/gate at the given position.
    /// </summary>
    public bool IsDoorOrGate(BlockPos pos)
    {
        var block = world.BlockAccessor.GetBlock(pos);
        return IsDoorOrGateBlock(block);
    }

    /// <summary>
    /// Check if a block is a door or gate.
    /// </summary>
    public bool IsDoorOrGateBlock(Block block)
    {
        if (block == null) return false;
        var path = block.Code?.Path;
        return path != null && InteractableCodes.Exists(code => path.Contains(code));
    }

    /// <summary>
    /// Check if a door/gate at the given position is currently open.
    /// </summary>
    public bool IsOpen(BlockPos pos)
    {
        var block = world.BlockAccessor.GetBlock(pos);
        if (block == null) return false;

        // Check for BlockBaseDoor (fence gates, trapdoors, old doors)
        if (block is BlockBaseDoor baseDoor)
        {
            return baseDoor.IsOpened();
        }

        // Check for new door system with BEBehaviorDoor
        var doorBehavior = world.BlockAccessor.GetBlockEntity(pos)?.GetBehavior<BEBehaviorDoor>();
        if (doorBehavior != null)
        {
            return doorBehavior.Opened;
        }

        // Fallback: check block variant
        var state = block.Variant?["state"];
        return state == "opened" || state == "open";
    }

    /// <summary>
    /// Open a door/gate at the given position.
    /// </summary>
    /// <param name="pos">Position of the door/gate</param>
    /// <param name="caller">The entity opening the door (for sounds and permissions)</param>
    /// <returns>True if successfully opened or already open</returns>
    public bool OpenDoor(BlockPos pos, Entity caller = null)
    {
        if (IsOpen(pos))
        {
            debugLog?.Invoke($"[DoorHandler] door at {pos} already open");
            return true;
        }

        return SetDoorState(pos, true, caller);
    }

    /// <summary>
    /// Close a door/gate at the given position.
    /// </summary>
    /// <param name="pos">Position of the door/gate</param>
    /// <param name="caller">The entity closing the door</param>
    /// <returns>True if successfully closed or already closed</returns>
    public bool CloseDoor(BlockPos pos, Entity caller = null)
    {
        if (!IsOpen(pos))
        {
            debugLog?.Invoke($"[DoorHandler] door at {pos} already closed");
            return true;
        }

        return SetDoorState(pos, false, caller);
    }

    /// <summary>
    /// Toggle a door/gate state.
    /// </summary>
    public bool ToggleDoor(BlockPos pos, Entity caller = null)
    {
        bool currentlyOpen = IsOpen(pos);
        return SetDoorState(pos, !currentlyOpen, caller);
    }

    /// <summary>
    /// Set door state to open or closed.
    /// </summary>
    bool SetDoorState(BlockPos pos, bool open, Entity caller)
    {
        var block = world.BlockAccessor.GetBlock(pos);
        if (block == null)
        {
            debugLog?.Invoke($"[DoorHandler] no block at {pos}");
            return false;
        }

        // Try using the block's Activate method with activation args
        try
        {
            var activationArgs = new TreeAttribute();
            activationArgs.SetBool("opened", open);

            // Create a Caller object
            var callerObj = new Caller
            {
                Entity = caller
            };

            // Create block selection
            var blockSel = new BlockSelection
            {
                Position = pos,
                Face = BlockFacing.NORTH
            };

            block.Activate(world, callerObj, blockSel, activationArgs);

            debugLog?.Invoke($"[DoorHandler] {(open ? "opened" : "closed")} door at {pos}");
            return true;
        }
        catch (Exception ex)
        {
            debugLog?.Invoke($"[DoorHandler] failed to activate door at {pos}: {ex.Message}");
        }

        // Fallback: try BEBehaviorDoor directly
        var doorBehavior = world.BlockAccessor.GetBlockEntity(pos)?.GetBehavior<BEBehaviorDoor>();
        if (doorBehavior != null)
        {
            try
            {
                doorBehavior.ToggleDoorState(null, open);
                debugLog?.Invoke($"[DoorHandler] {(open ? "opened" : "closed")} door via BEBehaviorDoor at {pos}");
                return true;
            }
            catch (Exception ex)
            {
                debugLog?.Invoke($"[DoorHandler] failed to toggle door via behavior at {pos}: {ex.Message}");
            }
        }

        return false;
    }

    /// <summary>
    /// Find the door/gate position in a 2-block tall column (foot and head level).
    /// </summary>
    public BlockPos FindDoorInColumn(BlockPos footPos)
    {
        // Check foot level
        if (IsDoorOrGate(footPos))
        {
            return footPos;
        }

        // Check head level
        var headPos = footPos.UpCopy();
        if (IsDoorOrGate(headPos))
        {
            return headPos;
        }

        return null;
    }

    /// <summary>
    /// Open all doors along a path that need interaction.
    /// </summary>
    /// <param name="interactionNodes">Path nodes that need door interaction</param>
    /// <param name="caller">Entity doing the opening</param>
    /// <returns>List of positions that were opened</returns>
    public List<BlockPos> OpenDoorsAlongPath(IEnumerable<PolisPathNode> interactionNodes, Entity caller = null)
    {
        var openedPositions = new List<BlockPos>();

        foreach (var node in interactionNodes)
        {
            var doorPos = FindDoorInColumn(node.BlockPos);
            if (doorPos != null && !IsOpen(doorPos))
            {
                if (OpenDoor(doorPos, caller))
                {
                    openedPositions.Add(doorPos);
                }
            }
        }

        return openedPositions;
    }

    /// <summary>
    /// Close all doors that were opened.
    /// </summary>
    /// <param name="openedPositions">Positions of doors that were opened</param>
    /// <param name="caller">Entity doing the closing</param>
    public void CloseOpenedDoors(List<BlockPos> openedPositions, Entity caller = null)
    {
        foreach (var pos in openedPositions)
        {
            CloseDoor(pos, caller);
        }
    }
}
