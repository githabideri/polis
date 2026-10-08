using System;
using System.Globalization;
using HarmonyLib;

// Observes the actual interpolation writer, not a later render gate.
// Samples are values: no per-frame strings, reflection, or unmanaged pointers.
[HarmonyPatch(typeof(EntityBehaviorInterpolatePosition), "OnRenderFrame")]
internal static class PolisInterpolationAudit
{
    internal struct Sample
    {
        public bool finite;
        public float dt, speed, accum, interval;
        public int queue, wait;
        public double lx, ly, lz, nx, ny, nz;
    }
    static long calls, nonFiniteWrites;
    static float maxDt, maxAbsSpeed;
    static bool Finite(double v) { return !double.IsNaN(v) && !double.IsInfinity(v); }
    internal static object Snapshot()
    {
        return new { calls, nonFiniteWrites, maxDt, maxAbsSpeed };
    }
    static void Prefix(EntityBehaviorInterpolatePosition __instance, float dt, out Sample __state)
    {
        var b = __instance;
        var p = b.entity.Pos;
        calls++;
        maxDt = Math.Max(maxDt, dt);
        maxAbsSpeed = Math.Max(maxAbsSpeed, Math.Abs(b.targetSpeed));
        __state = new Sample {
            finite = Finite(p.X) && Finite(p.Y) && Finite(p.Z),
            dt = dt, speed = b.targetSpeed, accum = b.dtAccum, interval = b.pN.interval,
            queue = b.queueCount, wait = b.wait,
            lx = b.pL.x, ly = b.pL.y, lz = b.pL.z,
            nx = b.pN.x, ny = b.pN.y, nz = b.pN.z
        };
    }
    static void Postfix(EntityBehaviorInterpolatePosition __instance, Sample __state)
    {
        var b = __instance;
        var p = b.entity.Pos;
        if (!__state.finite || (Finite(p.X) && Finite(p.Y) && Finite(p.Z))) return;
        nonFiniteWrites++;
        if (nonFiniteWrites > 32) return;
        var s = __state;
        b.entity.World.Logger.Warning(string.Format(CultureInfo.InvariantCulture,
            "[polis-interpolation-audit] FINITE->NONFINITE id={0} dt={1:R} speed={2:R}->{3:R} accum={4:R}->{5:R} interval={6:R}->{7:R} queue={8}->{9} wait={10}->{11} pL=({12:R},{13:R},{14:R}) pN=({15:R},{16:R},{17:R}) result=({18:R},{19:R},{20:R}) tick={21} tickDiff={22}",
            b.entity.EntityId, s.dt, s.speed, b.targetSpeed, s.accum, b.dtAccum,
            s.interval, b.pN.interval, s.queue, b.queueCount, s.wait, b.wait,
            s.lx, s.ly, s.lz, s.nx, s.ny, s.nz, p.X, p.Y, p.Z,
            b.entity.Attributes.GetInt("tick", -1), b.entity.Attributes.GetInt("tickDiff", -1)));
    }
}
