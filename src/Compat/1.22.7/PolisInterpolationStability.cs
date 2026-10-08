using System;
using System.Collections.Generic;
using System.Reflection.Emit;
using HarmonyLib;
using Vintagestory.API.MathTools;

// VS 1.22.7: interpolation speed uses Lerp(speed, target, dt * 4).
// Above dt=0.5 the feedback is unstable; overflow reaches entity positions.
// Clamp only the speed feedback factor, preserving actual elapsed time,
// position queues, remote physics, mounts, and normal-frame behavior.
[HarmonyPatch(typeof(EntityBehaviorInterpolatePosition), "OnRenderFrame")]
internal static class PolisInterpolationStability
{
    internal static float StableSpeedLerp(float current, float target, float amount)
    {
        return GameMath.Lerp(current, target, Math.Clamp(amount, 0f, 1f));
    }

    static IEnumerable<CodeInstruction> Transpiler(IEnumerable<CodeInstruction> instructions)
    {
        var original = AccessTools.Method(typeof(GameMath), "Lerp",
            new[] { typeof(float), typeof(float), typeof(float) });
        var replacement = AccessTools.Method(typeof(PolisInterpolationStability), nameof(StableSpeedLerp));
        var result = new List<CodeInstruction>(instructions);
        int replaced = 0;
        foreach (var instruction in result)
        {
            if (!instruction.Calls(original)) continue;
            instruction.opcode = OpCodes.Call;
            instruction.operand = replacement;
            replaced++;
        }
        if (replaced != 1)
            throw new InvalidOperationException("VS interpolation speed patch expected one float Lerp call; found " + replaced);
        return result;
    }
}
