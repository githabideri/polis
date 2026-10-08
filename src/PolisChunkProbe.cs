using System;
using System.Text;
using System.Collections.Generic;
using System.Reflection;
using System.Threading;
using Vintagestory.API.Client;
using Vintagestory.API.Common;
using Vintagestory.Client;
using Vintagestory.Client.NoObf;

// Chunk and entity diagnostics for terrain rendering while entities disappear.
// Reads chunk queues, render gates, NaN positions, and interpolation telemetry.
// In VS 1.22.7 low-FPS interpolation can write NaN into otherwise healthy client
// entities; see Compat/1.22.7/PolisInterpolationStability.cs. A failed chunk
// gate is therefore not by itself evidence of a broken chunk pipeline.
//
// Harness requests are consumed on the client render thread (Done stage).
// Server position repair uses snapshots captured separately on the server
// thread; the client's Pos and ServerPos alias the same object.
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
    private static volatile bool repairRequested;
    private static string repairReport;
    // optional frustum test point (harness arms it; the client evaluates it
    // against the LIVE frustum culler on the next frame)
    private static volatile bool hasTestPoint;
    private static double testX, testY, testZ, testR; // written before hasTestPoint is set
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
        Arm(null, null, null, 0);
    }

    public static void Arm(double? x, double? y, double? z, double r)
    {
        lock (resultLock) { lastResult = null; }
        if (x != null && y != null && z != null)
        {
            testX = x.Value; testY = y.Value; testZ = z.Value; testR = r;
            hasTestPoint = true;
        }
        else
        {
            hasTestPoint = false;
        }
        armed = true;
    }

    // server-sourced positions (id -> [x, y, z]) applied by DoRepair.
    // NOTE: the base Entity class aliases ServerPos to Pos, so the client
    // mirror's own "server" copy is the corrupted object itself - the only
    // authoritative source is the server-side entity objects (harness sapi world).
    private static System.Collections.Generic.Dictionary<long, double[]> repairMap;

    /// <summary>Request a NaN-position repair on the next render frame,
    /// using server-side positions for the given entity ids.</summary>
    public static void RequestRepair(System.Collections.Generic.Dictionary<long, double[]> serverPositions)
    {
        repairMap = serverPositions;
        lock (resultLock) { lastResult = null; }
        repairRequested = true;
        armed = true; // collect runs too, so the report lands in the result
    }

    private static void DoRepair(ClientMain g)
    {
        var sb = new StringBuilder();
        int fixedCount = 0;
        var erField = g.GetType().GetField("EntityRenderers", BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
        var erDict = erField?.GetValue(g) as System.Collections.IDictionary;
        if (erDict == null)
        {
            repairReport = "no EntityRenderers field";
            return;
        }
        foreach (System.Collections.DictionaryEntry kv in erDict)
        {
            try
            {
                if (!(kv.Key is long)) continue;
                object erVal = kv.Value;
                if (erVal == null) continue;
                object ent = erVal.GetType().GetField("entity")?.GetValue(erVal);
                if (ent == null) continue;
                object posObj = ent.GetType().GetProperty("Pos", BindingFlags.Public | BindingFlags.Instance)?.GetValue(ent);
                if (posObj == null) continue;
                var posType = posObj.GetType();
                var posFields = posType.GetFields(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
                bool anyNan = false;
                foreach (var f in posFields)
                {
                    var v = f.GetValue(posObj);
                    if (v is double dv && double.IsNaN(dv)) anyNan = true;
                    if (v is float fv && float.IsNaN(fv)) anyNan = true;
                }
                if (!anyNan) continue;
                long eid = (long)kv.Key;
                if (repairMap == null || !repairMap.ContainsKey(eid)) continue;
                double[] sp = repairMap[eid];
                if (sp == null || sp.Length < 3) continue;
                // set x/y/z via the public properties (they write the
                // protected fields) and zero the motion just in case
                posObj.GetType().GetProperty("X").SetValue(posObj, sp[0]);
                posObj.GetType().GetProperty("Y").SetValue(posObj, sp[1]);
                posObj.GetType().GetProperty("Z").SetValue(posObj, sp[2]);
                var mot = posObj.GetType().GetProperty("Motion")?.GetValue(posObj);
                if (mot != null)
                {
                    var mt = mot.GetType();
                    mt.GetProperty("X")?.SetValue(mot, 0d);
                    mt.GetProperty("Y")?.SetValue(mot, 0d);
                    mt.GetProperty("Z")?.SetValue(mot, 0d);
                }
                fixedCount++;
                sb.Append(" " + kv.Key);
            }
            catch
            {
                // per-entity safety; continue with the rest
            }
        }
        repairReport = fixedCount == 0 ? "no NaN positions found" : ("fixed " + fixedCount + ":" + sb.ToString().Trim());
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

        if (repairRequested)
        {
            repairRequested = false;
            try
            {
                DoRepair(game);
                logger?.Notification(LogPrefix + " " + repairReport);
            }
            catch (Exception ex)
            {
                repairReport = "repair failed: " + ex.Message;
                logger?.Warning(LogPrefix + repairReport);
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

        // GL-readback vs CPU camera-matrix divergence. ClientMain copies the
        // GL-context matrices into PerspectiveProjectionMat/PerspectiveViewMat
        // each frame and builds the frustum culler FROM THOSE, while the
        // actual camera matrix lives CPU-side on MainCamera. If the GL context
        // has degraded, the readback drifts from the camera truth -> the
        // frustum planes go wrong in a VIEW-DIRECTION-DEPENDENT way -> the
        // per-entity SphereInFrustum gate rejects entities (the player is at
        // the frustum origin, so it always survives: renderedEntities never
        // drops below 1). This is the cine-vs-VNC asymmetry: a cine sweep
        // rotates through yaw/pitch directions, some of which still fall
        // inside the broken frustum; the user's fixed noVNC view direction
        // does not.
        int matNan = 0;
        double viewMaxDiff = -1;
        double projMaxDiff = -1;
        bool camMatOk = false;
        double[] vmArr = null;
        double[] cmArr = null;
        try
        {
            var pm = game.PerspectiveProjectionMat;
            var vm = game.PerspectiveViewMat;
            vmArr = (double[])vm?.Clone();
            for (int i = 0; i < 16; i++)
            {
                if (pm != null && double.IsNaN(pm[i])) matNan++;
                if (vm != null && double.IsNaN(vm[i])) matNan++;
            }
            // the camera's own matrix, CPU-side (contains the raw world
            // position in the translation part; the GL view matrix is a
            // rebased/derived form, so an ABSOLUTE diff is a systematic
            // offset - what matters is DRIFT of the readback over time and
            // NaN/garbage elements)
            var camObj = (object)game.MainCamera;
            var cmf = camObj.GetType().GetField("CameraMatrixOrigin", BindingFlags.Public | BindingFlags.Instance);
            if (cmf?.GetValue(camObj) is double[] cm && cm.Length == 16 && vm != null)
            {
                camMatOk = true;
                cmArr = (double[])cm.Clone();
                for (int i = 0; i < 16; i++)
                {
                    double d = Math.Abs(cm[i] - vm[i]);
                    if (double.IsNaN(d)) { matNan++; continue; }
                    if (d > viewMaxDiff) viewMaxDiff = d;
                }
            }
            // projection matrix only depends on FoV/aspect: [10] should be
            // the perspective z term (~ -1); anything wild means the GL
            // context is not holding state correctly
            if (pm != null)
            {
                double s11 = pm[10];
                if (double.IsNaN(s11) || Math.Abs(s11) > 10 || s11 == 0) projMaxDiff = s11;
            }
        }
        catch (Exception ex)
        {
            matNan = -1;
        }

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
    // The render loop iterates game.EntityRenderers (internal dict on
    // ClientMain). RemoveEntityRenderer (client-side, fired by
    // SystemUnloadChunks / ClientSystemEntities on chunk unload) disposes the
    // renderer, removes the dict entry and nulls Properties.Client.Renderer.
    // If the remove side fires and the add side (fresh spawn/load) does not
    // re-fire for an existing entity, the entity exists in the world data
    // but is never drawn again - in-place, until re-instantiation. This
    // counter is the missing piece: it should track renderedEntities in a
    // healthy state and collapse to ~1 when entities drop out.
    int erCount = -1;
    var erIds = new List<long>();
    try
    {
        var erProp = game.GetType().GetField("EntityRenderers", BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
        var er = erProp?.GetValue(game) as System.Collections.IDictionary; // GetField->FieldInfo.GetValue(object)
        if (er != null)
        {
            erCount = er.Count;
            foreach (System.Collections.DictionaryEntry kv in er)
            {
                if (kv.Key is long l) erIds.Add(l);
            }
        }
    }
    catch (Exception ex)
    {
        erCount = -1;
    }

        // PER-GATE TABLE: for every entity in the renderer dict, evaluate
        // exactly the three gates the render loop applies (line 33 of
        // SystemRenderEntities): frustum sphere test at the entity's OWN
        // position, dimension match, and WorldMap.IsChunkRendered(entity.Pos)
        // (the EntityPos overload - a different lookup path than my
        // int-coordinate chunk check). In the dead state the bots are still
        // in the dict, so one of these gates is failing for them; this table
        // says which one, with the exact values the gate sees.
        var gates = new List<object>();
        try
        {
            var erField = game.GetType().GetField("EntityRenderers", BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
            var erDict = erField?.GetValue(game) as System.Collections.IDictionary;
            if (erDict != null)
            {
                foreach (System.Collections.DictionaryEntry kv in erDict)
                {
                    try
                    {
                        if (!(kv.Key is long)) continue;
                        object erVal = kv.Value;
                        if (erVal == null) continue;
                        object ent = erVal.GetType().GetField("entity")?.GetValue(erVal);
                        if (ent == null) continue;
                        object posObj = ent.GetType().GetProperty("Pos", BindingFlags.Public | BindingFlags.Instance)?.GetValue(ent);
                        if (posObj == null) continue;
                        var pt = posObj.GetType();
                        object GetVal(Type t, string name)
                        {
                            var p = t.GetProperty(name, BindingFlags.Public | BindingFlags.Instance);
                            if (p != null) return p.GetValue(t.IsInstanceOfType(posObj) ? posObj : null);
                            var fld = t.GetField(name, BindingFlags.Public | BindingFlags.Instance | BindingFlags.NonPublic);
                            if (fld != null) return fld.GetValue(posObj);
                            return null;
                        }
                        double px = (double)GetVal(pt, "X");
                        double pyi = (double)GetVal(pt, "InternalY");
                        double pz = (double)GetVal(pt, "Z");
                        int dim = (int)GetVal(pt, "Dimension");
                        object radObj = ent.GetType().GetProperty("FrustumSphereRadius", BindingFlags.Public | BindingFlags.Instance)?.GetValue(ent)
                            ?? ent.GetType().GetField("FrustumSphereRadius", BindingFlags.Public | BindingFlags.Instance | BindingFlags.NonPublic)?.GetValue(ent);
                        float radius = radObj != null ? Convert.ToSingle(radObj) : 2f;
                        bool inF = game.frustumCuller.SphereInFrustum((float)px, (float)pyi, (float)pz, radius);
                        bool chunkOk = game.WorldMap.IsChunkRendered((Vintagestory.API.Common.Entities.EntityPos)posObj);
                        var pp = game.EntityPlayer?.Pos;
                        bool near = pp != null && Math.Abs(px - (double)pp.X) < 64 && Math.Abs(pz - (double)pp.Z) < 64;
                        gates.Add(new
                        {
                            id = (long)kv.Key,
                            xInt = (int)px,
                            yInt = (int)pyi,
                            zInt = (int)pz,
                            dim,
                            inF,
                            chunkOk,
                            near,
                            nan = double.IsNaN(px) || double.IsNaN(pyi) || double.IsNaN(pz)
                        });
                    }
                    catch (Exception ex)
                    {
                        gates.Add(new { id = kv.Key, error = ex.GetType().Name + ": " + ex.Message });
                    }
                }
            }
        }
        catch (Exception ex)
        {
            gates.Add(new { error = ex.Message });
        }

        // live frustum-culler verdict for a requested point (the per-entity
        // gate uses exactly this test)
        object frustumTest = null;
        if (hasTestPoint)
        {
            hasTestPoint = false;
            try
            {
                bool inF = game.frustumCuller.SphereInFrustum((float)testX, (float)testY, (float)testZ, (float)testR);
                frustumTest = new { x = testX, y = testY, z = testZ, r = testR, inside = inF };
            }
            catch (Exception ex)
            {
                frustumTest = new { x = testX, y = testY, z = testZ, r = testR, error = ex.Message };
            }
        }

        return new
        {
            ok = true,
            gameCaptured,
            playerPos = pos != null ? new { x = (double)pos.X, y = (double)pos.Y, z = (double)pos.Z } : null,
            glReadback = new { camMatOk, matNan, viewMaxDiff, projMaxDiff, vmArr, cmArr },
            entityRenderers = new { count = erCount, ids = erIds },
            gates,
            gateNanCount = CountNanGates(gates),
            interpolation = PolisInterpolationAudit.Snapshot(),
            nanTriage = CountNanGates(gates) > 0 ? NanTriage(game) : null,
            repair = repairReport,
            frustumTest,
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
    private static int CountNanGates(List<object> gates)
    {
        int n = 0;
        foreach (var g2 in gates)
        {
            try
            {
                var p = g2.GetType().GetProperty("nan");
                if (p != null && (bool)p.GetValue(g2)) n++;
            }
            catch
            {
                // error-shaped entries have no nan field
            }
        }
        return n;
    }

    // Read packet tick metadata directly: Entity.Attributes is a field, and
    // GetInt has a default-value argument. Reflection errors must not masquerade
    // as missing packets. The interpolation audit identifies the position writer.
    private static List<object> NanTriage(ClientMain g)
    {
        var outList = new List<object>();
        try
        {
            var erField = g.GetType().GetField("EntityRenderers", BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
            var erDict = erField?.GetValue(g) as System.Collections.IDictionary;
            if (erDict == null) return outList;
            foreach (System.Collections.DictionaryEntry kv in erDict)
            {
                if (!(kv.Key is long)) continue;
                object erVal = kv.Value;
                if (erVal == null) continue;
                object ent = erVal.GetType().GetField("entity")?.GetValue(erVal);
                if (ent == null) continue;
                object posObj = ent.GetType().GetProperty("Pos", BindingFlags.Public | BindingFlags.Instance)?.GetValue(ent);
                if (posObj == null) continue;
                var pt = posObj.GetType();
                object D(Type t, object o, string name)
                {
                    var p = t.GetProperty(name, BindingFlags.Public | BindingFlags.Instance);
                    if (p != null) return p.GetValue(o);
                    var f = t.GetField(name, BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
                    return f?.GetValue(o);
                }
                double vx = (double)D(pt, posObj, "X");
                double vy = (double)D(pt, posObj, "Y");
                double vz = (double)D(pt, posObj, "Z");
                if (!double.IsNaN(vx) && !double.IsNaN(vy) && !double.IsNaN(vz)) continue;
                object motion = D(pt, posObj, "Motion");
                double mx = 0, my = 0, mz = 0;
                bool motionNan = false;
                if (motion != null)
                {
                    try { mx = (double)D(motion.GetType(), motion, "X"); my = (double)D(motion.GetType(), motion, "Y"); mz = (double)D(motion.GetType(), motion, "Z"); motionNan = double.IsNaN(mx) || double.IsNaN(my) || double.IsNaN(mz); } catch { }
                }
                var typedEntity = ent as Vintagestory.API.Common.Entities.Entity;
                int tick = typedEntity == null ? -1 : typedEntity.Attributes.GetInt("tick", -1);
                int tickDiff = typedEntity == null ? -1 : typedEntity.Attributes.GetInt("tickDiff", -1);
                outList.Add(new
                {
                    id = (long)kv.Key,
                    x = double.IsNaN(vx) ? (double?)null : vx,
                    y = double.IsNaN(vy) ? (double?)null : vy,
                    z = double.IsNaN(vz) ? (double?)null : vz,
                    motion = new
                    {
                        mx = double.IsNaN(mx) ? (double?)null : mx,
                        my = double.IsNaN(my) ? (double?)null : my,
                        mz = double.IsNaN(mz) ? (double?)null : mz,
                        motionNan
                    },
                    tick,
                    tickDiff
                });
                if (outList.Count >= 8) break;
            }
        }
        catch
        {
            // triage is best-effort
        }
        return outList;
    }

}
