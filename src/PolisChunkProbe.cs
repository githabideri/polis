using System;
using System.Collections.Generic;
using System.Reflection;
using System.Threading;
using Vintagestory.API.Client;
using Vintagestory.API.Common;
using Vintagestory.Client;
using Vintagestory.Client.NoObf;

// Chunk / entity-rendering probe (2026-10-08).
//
// Diagnostic for the "bots disappear after hours of runtime" failure
// (the entity pass goes silent while terrain keeps drawing; a full
// chunk unload + reload - or a process restart - restores it).
//
// The decompiled engine shows the per-frame entity gate:
//   SystemRenderEntities.OnBeforeRender draws an entity only if
//   WorldMap.IsChunkRendered(entity.Pos) is true, and
//   ClientWorldMap.IsChunkRendered == (chunk.quantityDrawn > 0).
// quantityDrawn is a per-ClientChunk-instance counter that is only ever
// incremented (on tesselation); a NEW chunk instance (installed when the
// server pushes updated chunk data - the overload path) starts at 0 and
// only becomes drawable once the tesselation pipeline processes it.
//
// So "terrain drawn but entity invisible" implies the chunk instance that
// is CURRENT in the world map has quantityDrawn == 0 (or is missing),
// i.e. the tesselation pipeline has stopped (re)marking current instances.
// This probe reads that state live, from the client main thread, without
// touching the GL context:
//
//   - the current instance's internal flags for the player's 3x3 chunks
//     (quantityDrawn / loadedFromServer / enquedForRedraw / ...),
//   - the dirty-chunk queue depths on ClientMain,
//   - the engine's own RuntimeStats (awaiting tesselation/pooling,
//     renderedEntities, triangle budget).
//
// It also exposes two recovery primitives for live testing:
//   - RedrawAll: ClientMain.RedrawAllBlocks() (the engine's own
//     /debug-redraw path: re-queue every loaded chunk for tesselation)
//   - Kick: priority SetChunkDirty on the player's surrounding chunks
//
// Threading: the arm/result flags are statics shared between the
// harness HTTP thread (arms) and the client render thread (a Done-stage
// IRenderer executes the read and writes the result). Singleplayer runs
// both in one process, which is the only deployment the harness targets.
public class PolisChunkProbe : IRenderer
{
    private const string LogPrefix = "[polis-chunk-probe]";

    private static ILogger logger;
    private static ClientMain game;
    private static bool gameCaptured;

    private static readonly object resultLock = new object();
    private static object lastResult;
    private static long lastResultMs;
    private static volatile bool armed;
    private static volatile bool redrawRequested;
    private static volatile bool kickRequested;
    private ICoreClientAPI capi;

    // Reflection handles into the engine's internal chunk state.
    private static FieldInfo fiQuantityDrawn;
    private static FieldInfo fiLoadedFromServer;
    private static FieldInfo fiEnquedForRedraw;
    private static FieldInfo fiQueuedForUpload;
    private static FieldInfo fiLastTesselationMs;
    private static FieldInfo fiQuantityOverloads;
    private static FieldInfo fiDirtyPriority;
    private static FieldInfo fiDirty;
    private static FieldInfo fiDirtyLast;

    private static FieldInfo GetField(Type t, string name)
    {
        return t?.GetField(name, BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Public);
    }

    private static object FieldVal(object o, string name)
    {
        if (o == null) return null;
        var f = GetField(o.GetType(), name);
        return f?.GetValue(o);
    }

    private static int CountOf(object q)
    {
        if (q == null) return -1;
        var p = q.GetType().GetProperty("Count");
        if (p != null)
        {
            var v = p.GetValue(q);
            return v is int ? (int)v : -1;
        }
        var f = GetField(q.GetType(), "Count");
        if (f != null) return f.GetValue(q) is int ? (int)f.GetValue(q) : -1;
        return -1;
    }

    /// <summary>Called by the cinematic-camera Harmony prefix (which sees
    /// the ClientMain on every render frame) until we have it.</summary>
    public static void CaptureGame(ClientMain g)
    {
        if (game == null && g != null)
        {
            game = g;
            gameCaptured = true;
            var cc = typeof(ClientChunk);
            fiQuantityDrawn = GetField(cc, "quantityDrawn");
            fiLoadedFromServer = GetField(cc, "loadedFromServer");
            fiEnquedForRedraw = GetField(cc, "enquedForRedraw");
            fiQueuedForUpload = GetField(cc, "queuedForUpload");
            fiLastTesselationMs = GetField(cc, "lastTesselationMs");
            fiQuantityOverloads = GetField(cc, "quantityOverloads");
            var cm = typeof(ClientMain);
            fiDirtyPriority = GetField(cm, "dirtyChunksPriority");
            fiDirty = GetField(cm, "dirtyChunks");
            fiDirtyLast = GetField(cm, "dirtyChunksLast");
            logger?.Notification(LogPrefix + " ClientMain captured (chunk fields: "
                + (fiQuantityDrawn != null ? "ok" : "MISSING") + ")");
        }
    }

    public static bool GameCaptured => gameCaptured;

    public static void SetLogger(ILogger l) { logger = l; }

    public void Register(ICoreClientAPI capi)
    {
        this.capi = capi;
        capi.Event.RegisterRenderer(this, EnumRenderStage.Done, "polis-chunk-probe");
        capi.Logger.Notification(LogPrefix + " renderer registered");
    }

    public void Dispose()
    {
        if (capi != null)
        {
            capi.Event.UnregisterRenderer(this, EnumRenderStage.Done);
        }
    }

    // --- harness-facing controls (any thread) --------------------------

    public static void Arm()
    {
        lock (resultLock) { lastResult = null; }
        armed = true;
    }

    public static void RequestRedrawAll() { redrawRequested = true; }
    public static void RequestKickPlayerChunks() { kickRequested = true; }

    /// <summary>Result of the last completed probe, or null if none yet.
    /// The harness polls this after Arm() until it is non-null.</summary>
    public static object PollResult()
    {
        lock (resultLock) return lastResult;
    }

    // --- IRenderer (client main thread, every frame) --------------------

    public double RenderOrder => 0.5;
    public int RenderRange => 0;

    public void OnRenderFrame(float dt, EnumRenderStage stage)
    {
        if (stage != EnumRenderStage.Done || game == null) return;

        if (redrawRequested)
        {
            redrawRequested = false;
            try
            {
                game.RedrawAllBlocks();
                logger?.Notification(LogPrefix + " RedrawAllBlocks() executed");
            }
            catch (Exception ex)
            {
                logger?.Warning(LogPrefix + " redraw failed: " + ex.Message);
            }
        }

        if (kickRequested)
        {
            kickRequested = false;
            try
            {
                KickAroundPlayer();
            }
            catch (Exception ex)
            {
                logger?.Warning(LogPrefix + " kick failed: " + ex.Message);
            }
        }

        if (!armed) return;
        armed = false;
        try
        {
            var r = Collect();
            lock (resultLock)
            {
                lastResult = r;
                lastResultMs = DateTime.UtcNow.Ticks;
            }
        }
        catch (Exception ex)
        {
            lock (resultLock)
            {
                lastResult = new { ok = false, error = "probe failed: " + ex.Message };
            }
        }
    }

    void KickAroundPlayer()
    {
        var pos = game.EntityPlayer?.Pos;
        if (pos == null) return;
        var wm = game.WorldMap;
        int cx = (int)(pos.X / 32);
        int cy = (int)(pos.Y / 32);
        int cz = (int)(pos.Z / 32);
        int kicked = 0;
        for (int dx = -1; dx <= 1; dx++)
        {
            for (int dz = -1; dz <= 1; dz++)
            {
                try
                {
                    wm.MarkChunkDirty(cx + dx, cy, cz + dz, priority: true, sunRelight: false, null, true, edgeOnly: false);
                    kicked++;
                }
                catch { }
            }
        }
        logger?.Notification(LogPrefix + " kicked " + kicked + " chunks (priority, player around " + cx + "," + cy + "," + cz + ")");
    }

    object Collect()
    {
        var wm = game.WorldMap;
        var pos = game.EntityPlayer?.Pos;

        // Client-side entity scene: what the CLIENT thinks exists (vs the
        // server's list from /polis/bots). If the server has bots the
        // client never instantiated, this count stays at 1 (the player).
        int clientTotal = -1, clientNear = 0;
        var nearCodes = new List<string>();
        try
        {
            // Preferred: the public API accessor (IClientWorldAccessor.
            // LoadedEntities). Fallback: reflect the concrete world's
            // "Entities" member (name varies between engine versions).
            object list = null;
            var la = (object)capi?.World;
            if (la != null)
            {
                var p = la.GetType().GetProperty("LoadedEntities", BindingFlags.Public | BindingFlags.Instance);
                if (p != null) list = p.GetValue(la);
            }
            if (list == null)
            {
                var wobj = (object)game.World;
                MemberInfo member = null;
                var pp = wobj.GetType().GetProperty("Entities", BindingFlags.Public | BindingFlags.Instance);
                if (pp != null) member = pp;
                else
                {
                    var ff = wobj.GetType().GetField("Entities", BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
                    if (ff != null) member = ff;
                }
                if (member != null)
                {
                    list = member is PropertyInfo ? ((PropertyInfo)member).GetValue(wobj) : ((FieldInfo)member).GetValue(wobj);
                }
            }
            if (list is System.Collections.IList il)
            {
                clientTotal = il.Count;
                if (pos != null)
                {
                    foreach (var o in il)
                    {
                        if (o == null) continue;
                        var pt = o.GetType().GetProperty("Pos");
                        if (pt == null) continue;
                        var pobj = pt.GetValue(o);
                        if (pobj == null) continue;
                        var px = pobj.GetType().GetProperty("X")?.GetValue(pobj) as double?
                            ?? (pobj.GetType().GetField("X")?.GetValue(pobj) is double d ? d : (double?)null);
                        var pz = pobj.GetType().GetProperty("Z")?.GetValue(pobj) as double?
                            ?? (pobj.GetType().GetField("Z")?.GetValue(pobj) is double d2 ? d2 : (double?)null);
                        if (px == null || pz == null) continue;
                        double dx = px.Value - pos.X;
                        double dz = pz.Value - pos.Z;
                        if (dx * dx + dz * dz < 64 * 64)
                        {
                            clientNear++;
                            if (nearCodes.Count < 20)
                            {
                                var code = o.GetType().GetProperty("Code")?.GetValue(o);
                                nearCodes.Add(code != null ? code.ToString() : "?");
                            }
                        }
                    }
                }
            }
            else if (clientTotal == -1)
            {
                // one-shot diagnostic: what are we actually looking at?
                var w = (object)game;
                var le = w.GetType().GetProperty("LoadedEntities", BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
                string leinfo = "LoadedEntities: n/a";
                if (le != null)
                {
                    var lv = le.GetValue(w);
                    leinfo = "LoadedEntities: " + (lv == null ? "null" : lv.GetType().Name);
                }
                var names = new List<string>();
                foreach (var pm in w.GetType().GetProperties(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance))
                {
                    names.Add(pm.Name);
                }
                nearCodes.Add("diag:" + leinfo + ";allProps=[" + string.Join(",", names) + "]");
            }
        }
        catch (Exception ex)
        {
            clientTotal = -2; // read failed
            nearCodes.Add("error:" + ex.Message);
        }

        var chunks = new List<object>();
        if (pos != null)
        {
            int cx = (int)(pos.X / 32);
            int cy = (int)(pos.Y / 32);
            int cz = (int)(pos.Z / 32);
            for (int dx = -1; dx <= 1; dx++)
            {
                for (int dz = -1; dz <= 1; dz++)
                {
                    int x = cx + dx, y = cy, z = cz + dz;
                    bool rendered = false;
                    try { rendered = wm.IsChunkRendered(x, y, z); } catch { }
                    var c = wm.GetChunk(x, y, z);
                    if (c == null)
                    {
                        chunks.Add(new { x, y, z, rendered, loaded = false });
                        continue;
                    }
                    chunks.Add(new
                    {
                        x, y, z,
                        rendered,
                        loaded = true,
                        quantityDrawn = ToInt(fiQuantityDrawn, c),
                        loadedFromServer = ToBool(fiLoadedFromServer, c),
                        enquedForRedraw = ToBool(fiEnquedForRedraw, c),
                        queuedForUpload = ToBool(fiQueuedForUpload, c),
                        lastTesselationMs = ToLong(fiLastTesselationMs, c),
                        quantityOverloads = ToInt(fiQuantityOverloads, c),
                        empty = ToBoolProp(c, "Empty"),
                        packed = ToBoolMethod(c, "IsPacked")
                    });
                }
            }
        }

        object queues;
        try
        {
            queues = new
            {
                dirtyPriority = CountOf(fiDirtyPriority?.GetValue(game)),
                dirty = CountOf(fiDirty?.GetValue(game)),
                dirtyLast = CountOf(fiDirtyLast?.GetValue(game))
            };
        }
        catch
        {
            queues = new { error = "queue read failed" };
        }

        var stats = new
        {
            awaitingTesselation = RuntimeStats.chunksAwaitingTesselation,
            awaitingPooling = RuntimeStats.chunksAwaitingPooling,
            tesselatedTotal = RuntimeStats.chunksTesselatedTotal,
            tesselatedPerSecond = RuntimeStats.chunksTesselatedPerSecond,
            renderedEntities = RuntimeStats.renderedEntities,
            renderedTriangles = RuntimeStats.renderedTriangles,
            availableTriangles = RuntimeStats.availableTriangles,
            chunksReceived = RuntimeStats.chunksReceived,
            chunksUnloaded = RuntimeStats.chunksUnloaded
        };

        return new
        {
            ok = true,
            gameCaptured,
            playerPos = pos != null ? new { x = (double)pos.X, y = (double)pos.Y, z = (double)pos.Z } : null,
            clientTotal,
            clientNear,
            nearCodes,
            probeWallMs = DateTime.UtcNow.Ticks / TimeSpan.TicksPerMillisecond,
            queues,
            stats,
            chunks
        };
    }

    private static int ToInt(FieldInfo f, object o)
    {
        if (f == null || o == null) return -1;
        var v = f.GetValue(o);
        return v is int ? (int)v : -1;
    }

    private static long ToLong(FieldInfo f, object o)
    {
        if (f == null || o == null) return -1;
        var v = f.GetValue(o);
        return v is long ? (long)v : -1;
    }

    private static bool ToBool(FieldInfo f, object o)
    {
        if (f == null || o == null) return false;
        var v = f.GetValue(o);
        return v is bool && (bool)v;
    }

    private static bool ToBoolProp(object o, string name)
    {
        if (o == null) return false;
        var p = o.GetType().GetProperty(name, BindingFlags.Public | BindingFlags.Instance);
        if (p != null && p.GetValue(o) is bool) return (bool)p.GetValue(o);
        var f = GetField(o.GetType(), name);
        return f != null && f.GetValue(o) is bool && (bool)f.GetValue(o);
    }

    private static bool ToBoolMethod(object o, string name)
    {
        if (o == null) return false;
        var m = o.GetType().GetMethod(name, BindingFlags.Public | BindingFlags.Instance);
        if (m != null && m.Invoke(o, null) is bool) return (bool)m.Invoke(o, null);
        return false;
    }
}
