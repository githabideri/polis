using System;
using System.Collections.Generic;
using System.Reflection.Emit;
using HarmonyLib;
using Vintagestory.API.Common;
using Vintagestory.API.Common.Entities;
using Vintagestory.API.MathTools;
using Vintagestory.API.Server;
using Vintagestory.Essentials;
using Vintagestory.GameContent;

internal static class PolisBuilderNpcHarmony
{
    private static bool applied;
    private static Harmony harmony;

    public static void Apply(ICoreServerAPI api)
    {
        if (applied)
        {
            return;
        }

        harmony = new Harmony("polis-builder-npc");
        harmony.PatchAll();
        applied = true;

        api.Logger.Notification("[polis] Harmony patches applied (tall grass pathing).");
    }

    public static void Unapply(ICoreServerAPI api)
    {
        if (!applied)
        {
            return;
        }

        harmony?.UnpatchAll("polis-builder-npc");
        harmony = null;
        applied = false;

        api?.Logger?.Notification("[polis] Harmony patches removed.");
    }
}

[HarmonyPatch(typeof(AStar), "traversable")]
internal static class PolisBuilderNpcAStarTraversablePatch{
    static IEnumerable<CodeInstruction> Transpiler(IEnumerable<CodeInstruction> instructions)
    {
        var isColliding = AccessTools.Method(
            typeof(CollisionTester),
            nameof(CollisionTester.IsColliding),
            new[] { typeof(IBlockAccessor), typeof(Cuboidf), typeof(Vec3d), typeof(bool) }
        );
        var isCollidingAllow = AccessTools.Method(
            typeof(PolisBuilderNpcAStarTraversablePatch),
            nameof(IsCollidingAllowTallGrass)
        );
        var getColliding = AccessTools.Method(
            typeof(CollisionTester),
            nameof(CollisionTester.GetCollidingCollisionBox),
            new[] { typeof(IBlockAccessor), typeof(Cuboidf), typeof(Vec3d), typeof(Cuboidd).MakeByRefType(), typeof(bool), typeof(int) }
        );
        var getCollidingAllow = AccessTools.Method(
            typeof(PolisBuilderNpcAStarTraversablePatch),
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

// Crash guard (2026-09-26): rapid view/teleport commands can make the CLIENT'S
// prediction/interpolation produce a NaN position; vanilla then throws
// ArgumentException ("Given pos contained NaN") in the physics step and kills
// the whole process (the 09/21 polisbot crash and the 09/26 player crash both
// died here). Sanitize the incoming pos instead: restore the entity's last
// known-good position (or zero) so the throw never happens.
[HarmonyPatch(typeof(EntityBehaviorControlledPhysics), "ApplyTests")]
internal static class PolisNanPosGuardPatch
{
    static int sanitizeCount;

    static bool Prefix(EntityBehaviorControlledPhysics __instance, ref EntityPos pos, EntityControls controls, float dt, bool remote)
    {
        if (!HasNan(pos))
        {
            return true;
        }
        sanitizeCount++;
        var entity = __instance?.Entity;
        var last = entity != null ? entity.Pos : default;
        if (!HasNan(last))
        {
            pos = last;
        }
        else
        {
            pos = new EntityPos(0, 0, 0, 0, 0f);
        }
        if (sanitizeCount <= 5 || sanitizeCount % 100 == 0)
        {
            entity?.Log($"[polis] NaN physics pos sanitized (occurrence {sanitizeCount}); restored last known pos", LogLevel.Warning);
        }
        return true;
    }

    static bool HasNan(EntityPos p)
        => float.IsNaN(p.Pos.X) || float.IsNaN(p.Pos.Y) || float.IsNaN(p.Pos.Z)
        || float.IsNaN(p.YPR.Yaw) || float.IsNaN(p.YPR.Pitch) || float.IsNaN(p.YPR.Roll);
}
