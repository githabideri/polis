using System;
using System.Reflection;
using Vintagestory.API.Common;
using Vintagestory.Client.NoObf;

// "Cinematic capture" camera (2026-10-25): deterministic screenshots of a
// built structure, immune to the idle-mouse clobber that breaks the old
// observer-screenshot.
//
// The whole Vintage Story view is driven by ClientMain.mouseYaw / mousePitch:
//   MainRenderLoop -> UpdateCameraYawPitch(dt) [idle reset]
//                 -> TriggerRenderStage(Before) -> PlayerCamera.OnBeforeRenderFrame3D:
//                      Yaw = game.mouseYaw; Pitch = game.mousePitch; Update()  // builds CameraMatrix
//                 -> GlLoadMatrix(MainCamera.CameraMatrix)  // world + shadow + gui
// So the ONLY reliable place to pin the view is to write game.mouseYaw /
// mousePitch AFTER the idle reset but BEFORE the body reads them - i.e. a
// Harmony PREFIX on OnBeforeRenderFrame3D. That feeds the game's own
// Update()->CameraMatrix path, so the world, the player-relative offset
// (shUniforms.PlayerPos) and every render pass stay mutually consistent.
//
// (Writing CameraMatrix directly in a postfix was tried and does NOT change
// the rendered frame - the pipeline rebuilds/reloads the matrix through this
// mouse-driven path, which is why the view stayed put.)
//
// The eye stays at the player's own position (the caller teleports the player
// to a vantage first for a raised/wide view); we only pin the look direction.
// No teleport, no packet, no mouse: deterministic, and it sidesteps the
// NaN-teleport crash family.
//
// Singleplayer: one client per process, so the armed state is static and is
// shared between the main-thread code that arms it and the client render
// thread that reads it.
internal static class PolisCinematicCamera
{
    private const string LogPrefix = "[polis-cine-cam]";
    private static ILogger logger;

    private static bool active;
    private static double yaw;
    private static double pitch;
    private static int framesLeft;

    // PlayerCamera keeps its ClientMain in a private `game` field.
    private static readonly FieldInfo GameField = typeof(PlayerCamera)
        .GetField("game", BindingFlags.NonPublic | BindingFlags.Instance);

    public static bool IsActive => active;

    public static void SetLogger(ILogger l)
    {
        logger = l;
    }

    /// <summary>
    /// Arm the cinematic camera to a fixed yaw/pitch (radians) for the next
    /// holdFrames render frames. Call on the main thread, then request a
    /// capture; the Done-stage screenshot falls inside the armed window and
    /// the world reverts to normal camera once the window ends.
    /// </summary>
    public static void Arm(double yaw, double pitch, int holdFrames)
    {
        PolisCinematicCamera.yaw = yaw;
        PolisCinematicCamera.pitch = pitch;
        framesLeft = Math.Max(1, holdFrames);
        active = true;
        logger?.Notification($"{LogPrefix} armed: yaw={yaw:F3} pitch={pitch:F3} hold={framesLeft}f");
    }

    public static void Disarm()
    {
        active = false;
    }

    // Harmony PREFIX on PlayerCamera.OnBeforeRenderFrame3D(float dt). Runs
    // before the body reads game.mouseYaw / mousePitch into Yaw / Pitch, so
    // the matrices the body builds (and every pass that consumes them) use
    // our pinned direction.
    internal static void OnBeforeRenderFrame3D_Prefix(Vintagestory.Client.NoObf.PlayerCamera __instance)
    {
        if (!active || __instance == null)
        {
            return;
        }

        try
        {
            var game = GameField?.GetValue(__instance) as ClientMain;
            if (game != null)
            {
                game.mouseYaw = (float)yaw;
                game.mousePitch = (float)pitch;
            }
            else
            {
                logger?.Warning($"{LogPrefix} no ClientMain on PlayerCamera (field 'game'?); view not pinned this frame");
            }
        }
        catch (Exception ex)
        {
            logger?.Warning($"{LogPrefix} prefix error (disarming): {ex.Message}");
            active = false;
        }

        if (--framesLeft <= 0)
        {
            active = false;
            logger?.Notification($"{LogPrefix} disarmed (held {framesLeft + 1} frame(s))");
        }
    }
}
