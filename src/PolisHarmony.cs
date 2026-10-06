using System;
using System.Collections.Generic;
using System.Reflection.Emit;
using HarmonyLib;
using Vintagestory.API.Client;
using Vintagestory.API.Common;
using Vintagestory.API.Common.Entities;
using Vintagestory.API.MathTools;
using Vintagestory.API.Server;
using Vintagestory.Essentials;
using Vintagestory.GameContent;

internal static class PolisHarmony
{
    private static bool applied;
    private static Harmony harmony;
    private static bool appliedClient;
    private static Harmony harmonyClient;

    public static void Apply(ICoreServerAPI api)
    {
        if (applied)
        {
            return;
        }

        harmony = new Harmony("polis");
        PolisNanPosGuardPatch.logger = api.Logger;
        harmony.PatchAll();
        applied = true;

        api.Logger.Notification("[polis] Harmony patches applied (tall grass pathing).");
    }

    /// <summary>
    /// Client-side patches. The star is PolisPauseGameBlockPatch: it keeps
    /// ClientMain.PauseGame(true) from ever flipping IsPaused, which in a
    /// singleplayer world is what makes ClientProgram suspend the server
    /// tick (the "startup wedge" - any pause dialog, most notoriously the
    /// character-selection dialog that opens when a player joins without
    /// the createCharacter moddata, used to freeze the bots for minutes).
    /// Resume calls (paused: false) still run, so state stays consistent.
    /// </summary>
    public static void ApplyClient(ICoreClientAPI api)
    {
        if (appliedClient)
        {
            return;
        }

        harmonyClient = new Harmony("polis.client");
        PolisPauseGameBlockPatch.logger = api.Logger;
        var pauseGame = AccessTools.Method(
            typeof(Vintagestory.Client.NoObf.ClientMain), "PauseGame", new[] { typeof(bool) });
        if (pauseGame != null)
        {
            harmonyClient.Patch(pauseGame, prefix: new HarmonyMethod(typeof(PolisPauseGameBlockPatch), "Prefix"));
            api.Logger.Notification("[polis] client Harmony patch applied (PauseGame block - server tick stays running through pause dialogs).");
        }
        else
        {
            api.Logger.Warning("[polis] ClientMain.PauseGame not found - PauseGame block NOT applied (game version change?)");
        }

        // Cinematic capture camera (2026-10-25): while a screenshot is armed,
        // a postfix on OnBeforeRenderFrame3D (the Before render stage) forces
        // the exact view matrix from an explicit eye->target, so the
        // Done-stage capture grabs a stable, deterministic frame - immune to
        // the idle-mouse clobber that breaks observer-screenshot. No
        // [HarmonyPatch] attribute on the class; patched explicitly here so
        // the server-side PatchAll does not double-apply it.
        PolisCinematicCamera.SetLogger(api.Logger);
        var onBeforeRender = AccessTools.Method(
            typeof(Vintagestory.Client.NoObf.PlayerCamera), "OnBeforeRenderFrame3D", new[] { typeof(float) });
        if (onBeforeRender != null)
        {
            harmonyClient.Patch(onBeforeRender, prefix: new HarmonyMethod(typeof(PolisCinematicCamera), "OnBeforeRenderFrame3D_Prefix"));
            api.Logger.Notification("[polis] client Harmony patch applied (cinematic capture camera - deterministic screenshots).");
        }
        else
        {
            api.Logger.Warning("[polis] PlayerCamera.OnBeforeRenderFrame3D not found - cinematic camera NOT applied (game version change?)");
        }

        appliedClient = true;
    }

    public static void Unapply(ICoreServerAPI api)
    {
        if (!applied)
        {
            return;
        }

        harmony?.UnpatchAll("polis");
        harmony = null;
        applied = false;

        api?.Logger?.Notification("[polis] Harmony patches removed.");
    }
}

[HarmonyPatch(typeof(AStar), "traversable")]
internal static class PolisAStarTraversablePatch{
    static IEnumerable<CodeInstruction> Transpiler(IEnumerable<CodeInstruction> instructions)
    {
        var isColliding = AccessTools.Method(
            typeof(CollisionTester),
            nameof(CollisionTester.IsColliding),
            new[] { typeof(IBlockAccessor), typeof(Cuboidf), typeof(Vec3d), typeof(bool) }
        );
        var isCollidingAllow = AccessTools.Method(
            typeof(PolisAStarTraversablePatch),
            nameof(IsCollidingAllowTallGrass)
        );
        var getColliding = AccessTools.Method(
            typeof(CollisionTester),
            nameof(CollisionTester.GetCollidingCollisionBox),
            new[] { typeof(IBlockAccessor), typeof(Cuboidf), typeof(Vec3d), typeof(Cuboidd).MakeByRefType(), typeof(bool), typeof(int) }
        );
        var getCollidingAllow = AccessTools.Method(
            typeof(PolisAStarTraversablePatch),
            nameof(GetCollidingCollisionBoxAllowTallGrass)
        );

        foreach (var instruction in instructions)
        {
            if (instruction.Calls(isColliding))
            {
                instruction.operand = isCollidingAllow;
                instruction.opcode = OpCodes.Call;
            }
            else if (instruction.Calls(getColliding))
            {
                instruction.operand = getCollidingAllow;
                instruction.opcode = OpCodes.Call;
            }

            yield return instruction;
        }
    }

    private static bool IsCollidingAllowTallGrass(CollisionTester collTester, IBlockAccessor blockAccessor, Cuboidf entityBoxRel, Vec3d pos, bool alsoCheckTouch)
    {
        var block = collTester.GetCollidingBlock(blockAccessor, entityBoxRel, pos, alsoCheckTouch);
        if (block == null)
        {
            return false;
        }

        return !IsTallGrass(block);
    }

    private static bool GetCollidingCollisionBoxAllowTallGrass(
        CollisionTester collTester,
        IBlockAccessor blockAccessor,
        Cuboidf entityBoxRel,
        Vec3d pos,
        ref Cuboidd intoCuboid,
        bool alsoCheckTouch,
        int dimension
    )
    {
        BlockPos blockPos = new(dimension);
        Vec3d blockPosVec = new();
        Cuboidd entityBox = entityBoxRel.ToDouble().Translate(pos);

        entityBox.Y1 = Math.Round(entityBox.Y1, 5);

        int minX = (int)(entityBoxRel.X1 + pos.X);
        int minY = (int)(entityBoxRel.Y1 + pos.Y - 1);
        int minZ = (int)(entityBoxRel.Z1 + pos.Z);

        int maxX = (int)Math.Ceiling(entityBoxRel.X2 + pos.X);
        int maxY = (int)Math.Ceiling(entityBoxRel.Y2 + pos.Y);
        int maxZ = (int)Math.Ceiling(entityBoxRel.Z2 + pos.Z);

        for (int y = minY; y <= maxY; y++)
        {
            for (int x = minX; x <= maxX; x++)
            {
                blockPos.Set(x, y, minZ);
                blockPosVec.Set(x, y, minZ);
                for (int z = minZ; z <= maxZ; z++)
                {
                    blockPos.Z = z;
                    Block block = blockAccessor.GetBlock(blockPos, BlockLayersAccess.MostSolid);

                    if (IsTallGrass(block))
                    {
                        continue;
                    }

                    Cuboidf[] collisionBoxes = block.GetCollisionBoxes(blockAccessor, blockPos);
                    if (collisionBoxes == null)
                    {
                        continue;
                    }

                    blockPosVec.Z = z;
                    for (int i = 0; i < collisionBoxes.Length; i++)
                    {
                        Cuboidf collBox = collisionBoxes[i];
                        if (collBox == null)
                        {
                            continue;
                        }

                        bool colliding = alsoCheckTouch ? entityBox.IntersectsOrTouches(collBox, blockPosVec) : entityBox.Intersects(collBox, blockPosVec);
                        if (colliding)
                        {
                            intoCuboid.Set(collBox).Translate(blockPos);
                            return true;
                        }
                    }
                }
            }
        }

        return false;
    }

    private static bool IsTallGrass(Block block)
    {
        if (block == null)
        {
            return false;
        }

        // 1.22: BlockTallGrass type removed; code-path check below is sufficient.

        var path = block.Code?.Path;
        if (path == null)
        {
            return false;
        }

        return path.StartsWith("tallgrass", StringComparison.Ordinal) ||
               path.StartsWith("frostedtallgrass", StringComparison.Ordinal);
    }
}

// Crash guard (2026-09-26, extended 2026-09-27): rapid view/teleport commands
// can make the CLIENT'S prediction/interpolation produce a NaN position or
// MOTION (velocity); vanilla then throws ArgumentException ("Given pos
// contained NaN") in the physics step and kills the whole process (the 09/21
// polisbot crash, the 09/26 player crash and the 09/27 crash all died here).
// The vanilla check inspects pos.X/Y/Z AND pos.Motion — but pos.ToString()
// only prints XYZ/YPR/Dim, which is why the 09/27 crash message looked clean
// while its Motion was NaN (the original guard only checked XYZ/YPR). We
// sanitize the incoming pos: restore last known-good position when the
// position itself is NaN, and always zero a NaN motion (worst case: the
// entity stalls for one tick instead of the process dying).
[HarmonyPatch(typeof(EntityBehaviorControlledPhysics), "ApplyTests")]
internal static class PolisNanPosGuardPatch
{
    internal static Vintagestory.API.Common.ILogger logger; // set by PolisHarmony.Apply
    static int sanitizeCount;

    static bool Prefix(EntityBehaviorControlledPhysics __instance, ref EntityPos pos, EntityControls controls, float dt, bool remote)
    {
        bool nanPos = HasNanPos(pos);
        bool nanMotion = HasNanMotion(pos);
        if (!nanPos && !nanMotion)
        {
            return true;
        }
        sanitizeCount++;
        if (nanPos)
        {
            var entity = __instance?.Entity;
            var last = entity != null ? entity.Pos : default;
            if (!HasNanPos(last) && !HasNanMotion(last))
            {
                pos = last;
            }
            else
            {
                pos = new EntityPos(0, 0, 0, 0, 0f);
            }
        }
        if (nanMotion)
        {
            pos.Motion = Vec3d.Zero;
        }
        if (sanitizeCount <= 5 || sanitizeCount % 100 == 0)
        {
            logger?.Notification(
                $"[polis] NaN physics pos sanitized (occurrence {sanitizeCount}); motion-zeroed={nanMotion} pos-restored={nanPos}");
        }
        return true;
    }

    static bool HasNanPos(EntityPos p)
        => double.IsNaN(p.X) || double.IsNaN(p.Y) || double.IsNaN(p.Z)
        || float.IsNaN(p.Yaw) || float.IsNaN(p.Pitch) || float.IsNaN(p.Roll);

    static bool HasNanMotion(EntityPos p)
        => double.IsNaN(p.Motion.X) || double.IsNaN(p.Motion.Y) || double.IsNaN(p.Motion.Z);
}

// "Startup wedge" fix (2026-10-04): in a singleplayer world, ClientProgram
// suspends the embedded server whenever the client's IsPaused flag is set
// (its main loop: Suspend(true) while platform.IsGamePaused). The client
// sets IsPaused via PauseGame(true) whenever a pause-flavor dialog opens -
// the escape menu, the handbooks, and, the killer for unattended runs, the
// character-selection dialog that opens on join when the player lacks the
// createCharacter moddata (the dialog stayed open unattended, so the
// server tick - and with it every game-tick-driven thing: bot navigation,
// the harness command queue, autosaves - froze for minutes at world entry).
//
// This mod runs an unattended bot world where pausing is never wanted: a
// human at the VNC can still open menus (the world keeps running behind
// them, which is the desired pilot behavior), so the PAUSE half of
// PauseGame is blocked here. The RESUME half still runs so the flag and
// world-calendar state stay consistent when dialogs close.
internal static class PolisPauseGameBlockPatch
{
    internal static Vintagestory.API.Common.ILogger logger;
    static int skipCount;

    // No [HarmonyPatch] attribute on purpose: PolisHarmony.ApplyClient
    // patches this explicitly (the server-side PatchAll must not also pick
    // it up and double-apply in the singleplayer process).
    static bool Prefix(Vintagestory.Client.NoObf.ClientMain __instance, bool paused)
    {
        if (!paused)
        {
            return true; // resume: let it run
        }
        skipCount++;
        if (skipCount <= 5 || skipCount % 100 == 0)
        {
            logger?.Notification(
                $"[polis] blocked client PauseGame(true) (occurrence {skipCount}) - server tick keeps running while the pause dialog is open");
        }
        return false; // skip the pause
    }
}
