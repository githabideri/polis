using System;
using System.Collections.Generic;
using System.Reflection.Emit;
using HarmonyLib;
using Vintagestory.API.Common;
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
internal static class PolisBuilderNpcAStarTraversablePatch
{
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
