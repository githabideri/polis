using System;
using Vintagestory.API.Client;
using Vintagestory.API.Common;
using Vintagestory.API.Common.Entities;
using Vintagestory.API.Datastructures;
using Vintagestory.API.MathTools;
using Vintagestory.GameContent;

/// <summary>
/// Minimal IMountable implementation that wraps a single seat.
/// VS requires MountSupplier to return a valid IMountable with Seats array.
/// </summary>
public class PolisPossessionMountable : IMountable
{
    private readonly PolisPossessableSeat seat;
    private readonly IMountableSeat[] seats;

    public PolisPossessionMountable(PolisPossessableSeat seat)
    {
        this.seat = seat;
        this.seats = new IMountableSeat[] { seat };
    }

    public IMountableSeat[] Seats => seats;
    public EntityPos Position => seat.SeatPosition;
    public double StepPitch => 0;
    public Entity Controller => seat.Passenger;
    public Entity OnEntity => seat.Entity;
    public EntityControls ControllingControls => seat.Controls;

    public bool AnyMounted() => seat.Passenger != null;
}

/// <summary>
/// A custom IMountableSeat implementation that enables "possession" of NPCs.
/// When a player mounts this seat, they see through the NPC's eyes and their
/// controls are routed to the NPC's movement instead of their own.
/// </summary>
public class PolisPossessableSeat : IMountableSeat
{
    // The NPC entity being possessed
    private readonly EntityAgent npcEntity;

    // The player currently possessing this NPC (null if not possessed)
    private EntityAgent passenger;

    // Cached seat position - updated each tick to follow NPC
    private EntityPos seatPos;

    // Transform matrix that hides the player model (scale to 0)
    private readonly Matrixf hideTransform;

    // Controls object - receives player input
    private readonly EntityControls controls = new EntityControls();

    // The mountable wrapper (required by VS)
    private readonly PolisPossessionMountable mountable;

    // Callback when possession starts
    public Action<EntityAgent> OnPossessionStart;

    // Callback when possession ends
    public Action<EntityAgent> OnPossessionEnd;

    // Unique identifier for this seat type (used for network sync)
    public const string MountableClassName = "polispossession";

    // Debug flag - enables diagnostic logging
    private bool debugEnabled;

    public PolisPossessableSeat(EntityAgent npcEntity, bool debugEnabled = false)
    {
        this.npcEntity = npcEntity ?? throw new ArgumentNullException(nameof(npcEntity));
        this.debugEnabled = debugEnabled;

        // Initialize seat position at NPC location
        seatPos = new EntityPos();
        UpdateSeatPosition();

        // Create a transform matrix that scales to 0 to hide the player model
        hideTransform = new Matrixf().Identity().Scale(0, 0, 0);

        // Create the mountable wrapper
        mountable = new PolisPossessionMountable(this);
    }

    /// <summary>
    /// Updates the seat position to match the NPC's current position.
    /// Call this from the tick handler to keep the "seat" following the NPC.
    /// </summary>
    public void UpdateSeatPosition()
    {
        if (npcEntity?.ServerPos != null)
        {
            seatPos.SetFrom(npcEntity.ServerPos);
        }
        else if (npcEntity?.Pos != null)
        {
            seatPos.SetFrom(npcEntity.Pos);
        }
    }

    #region IMountableSeat Implementation

    // Config is not used for possession seats
    public SeatConfig Config { get; set; } = new SeatConfig();

    // Unique seat ID
    public string SeatId { get; set; } = "possession";

    // Entity ID for network initialization
    public long PassengerEntityIdForInit { get; set; }

    // Don't teleport player on unmount - they should stay where the NPC is
    public bool DoTeleportOnUnmount { get; set; } = false;

    // The NPC entity being possessed
    public Entity Entity => npcEntity;

    // The player currently possessing
    public Entity Passenger => passenger;

    // Mount supplier - required by VS for seat management
    public IMountable MountSupplier => mountable;

    // Player can control the NPC
    public bool CanControl => true;

    // Player's camera follows their look direction (unaffected by NPC rotation)
    public EnumMountAngleMode AngleMode => EnumMountAngleMode.Unaffected;

    // No animation override - let the NPC's current animation play
    public AnimationMetaData SuggestedAnimation => null;

    // Skip idle animation on the player (they're invisible anyway)
    public bool SkipIdleAnimation => true;

    // No first-person hand pitch follow needed
    public float FpHandPitchFollow => 0f;

    /// <summary>
    /// Camera position - at the NPC's eye level for true first-person possession
    /// </summary>
    // Track if we've logged diagnostics this possession session
    private bool diagnosticLogged = false;

    public Vec3f LocalEyePos
    {
        get
        {
            // EXPERIMENT: Try 1.95 (above head but below 2m ceilings)
            // NPC head top ~1.8m, need >1.9m to clear geometry
            // Room ceilings typically 2.0m, so 1.95m = 5cm clearance
            float testValue = 1.95f;

            // DIAGNOSTIC: Log ONCE per possession session with full camera calc info
            if (debugEnabled && !diagnosticLogged && npcEntity?.World?.Logger != null && Passenger != null)
            {
                diagnosticLogged = true;

                float npcLocalEyeY = (float)(npcEntity?.LocalEyePos?.Y ?? 0);
                float npcPropsEyeHeight = (float)(npcEntity?.Properties?.EyeHeight ?? 0);

                // Log NPC and player positions for camera calc verification
                var npcPos = npcEntity.ServerPos;
                var playerEntity = Passenger as EntityPlayer;

                npcEntity.World.Logger.Notification($"[polis-diag] === Camera Diagnostic ===");
                npcEntity.World.Logger.Notification($"[polis-diag] NPC.LocalEyePos.Y: {npcLocalEyeY:F3}");
                npcEntity.World.Logger.Notification($"[polis-diag] NPC.Properties.EyeHeight: {npcPropsEyeHeight:F3}");
                npcEntity.World.Logger.Notification($"[polis-diag] NPC.ServerPos: ({npcPos.X:F2}, {npcPos.Y:F2}, {npcPos.Z:F2})");
                npcEntity.World.Logger.Notification($"[polis-diag] Seat returning: (0, {testValue:F3}, 0)");
                npcEntity.World.Logger.Notification($"[polis-diag] Expected camera Y: {npcPos.Y + testValue:F3}");
                npcEntity.World.Logger.Notification($"[polis-diag] Camera = NPC.Pos + LocalEyePos formula");
            }

            return new Vec3f(0, testValue, 0);
        }
    }

    /// <summary>
    /// Seat position - matches NPC position
    /// </summary>
    public EntityPos SeatPosition
    {
        get
        {
            UpdateSeatPosition();
            return seatPos;
        }
    }

    /// <summary>
    /// Transform that hides the player model by scaling to 0
    /// </summary>
    public Matrixf RenderTransform => hideTransform;

    /// <summary>
    /// Controls - player input gets copied here by the mounting system
    /// </summary>
    public EntityControls Controls => controls;

    /// <summary>
    /// Check if the entity can mount this seat (must be a player)
    /// </summary>
    public bool CanMount(EntityAgent entityAgent)
    {
        // Only players can possess NPCs
        if (entityAgent == null || !(entityAgent is EntityPlayer)) return false;

        // Can't possess if already possessed
        if (passenger != null) return false;

        // Can't possess dead NPCs
        if (npcEntity == null || !npcEntity.Alive) return false;

        return true;
    }

    /// <summary>
    /// Check if the entity can unmount
    /// </summary>
    public bool CanUnmount(EntityAgent entityAgent)
    {
        // Always allow unmounting
        return true;
    }

    /// <summary>
    /// Called when a player mounts this seat (starts possession)
    /// </summary>
    public void DidMount(EntityAgent entityAgent)
    {
        passenger = entityAgent;
        PassengerEntityIdForInit = entityAgent?.EntityId ?? 0;

        // Notify listeners that possession has started
        OnPossessionStart?.Invoke(entityAgent);
    }

    /// <summary>
    /// Called when a player unmounts this seat (ends possession)
    /// </summary>
    public void DidUnmount(EntityAgent entityAgent)
    {
        var previousPassenger = passenger;
        passenger = null;
        PassengerEntityIdForInit = 0;

        // Reset diagnostic flag for next possession
        diagnosticLogged = false;

        // Notify listeners that possession has ended
        OnPossessionEnd?.Invoke(previousPassenger);
    }

    /// <summary>
    /// Serialize seat info for network sync.
    /// Uses a unique class name so VS can reconstruct the seat on clients.
    /// </summary>
    public void MountableToTreeAttributes(TreeAttribute tree)
    {
        tree.SetString("className", MountableClassName);
        tree.SetLong("npcEntityId", npcEntity?.EntityId ?? 0);
        tree.SetString("seatId", SeatId);
    }

    #endregion

    /// <summary>
    /// Factory method to create a seat from tree attributes (network deserialization).
    /// Register this with ICoreAPI.RegisterMountable().
    /// </summary>
    public static IMountableSeat CreateFromTree(IWorldAccessor world, TreeAttribute tree)
    {
        long npcEntityId = tree.GetLong("npcEntityId", 0);
        if (npcEntityId == 0) return null;

        var npc = world.GetEntityById(npcEntityId) as EntityAgent;
        if (npc == null) 
        {
            // Silent failure is common on client if entity isn't loaded yet,
            // but let's log it for debugging if it happens.
            world.Logger.Warning($"[polis] CreateFromTree: NPC {npcEntityId} not found.");
            return null;
        }

        world.Logger.Notification($"[polis] CreateFromTree: Reconstructing seat for NPC {npcEntityId}");

        var seat = new PolisPossessableSeat(npc);
        seat.SeatId = tree.GetString("seatId", "possession");
        return seat;
    }
}
