using System;
using Vintagestory.API.Client;
using Vintagestory.API.Common;
using Vintagestory.API.Common.Entities;
using Vintagestory.API.MathTools;

/// <summary>
/// Phase 1.5: Client-side handler for smooth possession movement prediction.
/// Runs on render frame (~60 FPS) to predict NPC motion and reconcile with server.
///
/// This eliminates the "choppy" feeling by:
/// 1. Predicting NPC movement locally using same logic as server (CalcMovementVectors)
/// 2. Running on render frame for smooth interpolation
/// 3. Reconciling to server snapshots via smooth Lerp (not hard-snap)
/// </summary>
public class PolisClientPossessionHandler : IRenderer
{
    private ICoreClientAPI capi;

    // Tracking
    private EntityAgent possessedNpc;
    private PolisPossessableSeat possessionSeat;

    // Interpolation state
    private Vec3d lastServerPos;

    // Diagnostic counters (Phase 1.5 testing)
    private int frameCount = 0;
    private double frameTime = 0;
    private bool loggedFirstCall = false;
    private bool loggedPredictionDisabled = false;

    public double RenderOrder => 0.5;
    public int RenderRange => 10000;

    public void Register(ICoreClientAPI capi)
    {
        this.capi = capi;
        capi.Event.RegisterRenderer(this, EnumRenderStage.Before, "polis-possession-smoothing");
    }

    public void OnRenderFrame(float dt, EnumRenderStage stage)
    {
        // DIAGNOSTIC: Log once to verify handler is being called at all
        if (!loggedFirstCall)
        {
            capi.Logger.Notification("[polis] OnRenderFrame: Handler registered and called!");
            loggedFirstCall = true;
        }

        // DIAGNOSTIC: Count frames and log FPS every second
        frameCount++;
        frameTime += dt;
        if (frameTime > 1.0)
        {
            capi.Logger.Notification($"[polis] OnRenderFrame FPS: {frameCount} frames in last {frameTime:F2}s");
            frameCount = 0;
            frameTime = 0;
        }

        // Check if local player is mounted on a possession seat
        var player = capi.World.Player?.Entity;
        if (player == null) return;

        // DIAGNOSTIC: Log mount status and type
        if (player.MountedOn != null)
        {
            capi.Logger.Notification($"[polis] OnRenderFrame: Player mounted on {player.MountedOn.GetType().Name}");
        }

        if (!(player.MountedOn is PolisPossessableSeat seat)) return;

        possessedNpc = seat.Entity as EntityAgent;
        possessionSeat = seat;

        if (possessedNpc == null || !possessedNpc.Alive) return;

        // PREDICTION: Mirror server-side control routing
        PredictNpcMovement(dt, seat);

        // RECONCILIATION: Smooth blend to server position
        ReconcileWithServer(dt);
    }

    private void PredictNpcMovement(float dt, PolisPossessableSeat seat)
    {
        // Disabled: Prediction variants (raw and physics-style) did not change movement feel.
        // Keep client motion driven by server physics + interpolation until a better model exists.
        if (!loggedPredictionDisabled)
        {
            capi.Logger.Notification("[polis] PredictNpcMovement: DISABLED (no improvement observed)");
            loggedPredictionDisabled = true;
        }
        return;
    }

    private void ReconcileWithServer(float dt)
    {
        var sp = possessedNpc.ServerPos;
        if (sp == null || double.IsNaN(sp.X) || double.IsNaN(sp.Y) || double.IsNaN(sp.Z))
        {
            // Server pos not available/valid on the client yet - skip reconciliation.
            // (Lerping toward a NaN would poison the client pos forever and crash
            //  the physics tick with ArgumentException.)
            if (possessedNpc.Pos != null &&
                (double.IsNaN(possessedNpc.Pos.X) || double.IsNaN(possessedNpc.Pos.Y) || double.IsNaN(possessedNpc.Pos.Z)) &&
                sp != null)
            {
                // self-heal: server pos valid, render pos NaN -> snap
                possessedNpc.Pos.SetFrom(sp);
            }
            return;
        }

        // Self-heal a NaN render pos (e.g. set before the first sync)
        if (double.IsNaN(possessedNpc.Pos.X) || double.IsNaN(possessedNpc.Pos.Y) || double.IsNaN(possessedNpc.Pos.Z))
        {
            possessedNpc.Pos.SetFrom(sp);
            lastServerPos = sp.XYZ.Clone();
            return;
        }

        // Initialize last server position on first call
        if (lastServerPos == null)
        {
            lastServerPos = sp.XYZ.Clone();
        }

        // CHECK: If server position diverged significantly from predicted, blend
        double distSq =
            Math.Pow(sp.X - possessedNpc.Pos.X, 2) +
            Math.Pow(sp.Y - possessedNpc.Pos.Y, 2) +
            Math.Pow(sp.Z - possessedNpc.Pos.Z, 2);

        // DIAGNOSTIC: Log divergence (only if moving to reduce spam)
        if (distSq > 0.0001)  // Only log if there's actual movement
        {
            capi.Logger.Notification($"[polis] Divergence: {Math.Sqrt(distSq):F3} blocks");
        }

        // If prediction drifted > 0.5 blocks, blend toward server
        if (distSq > 0.25)
        {
            float blendFactor = 0.15f;  // Smooth blend, not instant snap
            possessedNpc.Pos.X = GameMath.Lerp(possessedNpc.Pos.X, sp.X, blendFactor);
            possessedNpc.Pos.Y = GameMath.Lerp(possessedNpc.Pos.Y, sp.Y, blendFactor);
            possessedNpc.Pos.Z = GameMath.Lerp(possessedNpc.Pos.Z, sp.Z, blendFactor);
            capi.Logger.Notification($"[polis] Reconciling: Applied Lerp blend (distSq={distSq:F3})");
        }

        lastServerPos = sp.XYZ.Clone();
    }

    public void Dispose() { }
}
