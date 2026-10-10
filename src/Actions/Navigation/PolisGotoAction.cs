using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using Vintagestory.API.Common;
using Vintagestory.API.Common.Entities;
using Vintagestory.API.MathTools;
using Vintagestory.Essentials;
using Vintagestory.GameContent;

namespace Polis.Actions.Navigation;

/// <summary>
/// Navigation action that moves an entity to a target position using A* pathfinding
/// or straight-line traversal with fallback support.
/// </summary>
class PolisGotoAction : EntityActionBase
{
    public override string Type => "polis-goto";

    public Vec3d Target = new Vec3d();
    public float AnimSpeed = 1f;
    public float WalkSpeed = 0.02f;
    public string AnimCode = "walk";
    public bool Astar = true;

    /// <summary>
    /// Use custom PolisAStar pathfinder with fence/door awareness.
    /// When false, uses VS's built-in WaypointsTraverser.
    /// </summary>
    public bool UsePolisAStar = true;

    /// <summary>
    /// Automatically open doors/gates along the path.
    /// </summary>
    public bool OpenDoors = true;

    /// <summary>
    /// Close doors after passing through them.
    /// </summary>
    public bool CloseDoors = false;

    readonly Action<string> debugLog;
    readonly Action<List<BlockPos>> debugPath;
    readonly bool debugEnabled;
    readonly bool allowFallback;
    readonly Action<bool, string> onResult;

    bool done;
    bool resultSent;
    Vec3d hereTarget;
    int astarTries;
    bool fallbackTried;
    bool loggedPathIntrospection;

    // Nav stuck-fix (2026-10-10): F1 bounded repath, F2 height-aware
    // arrival, F4 one 4x A* budget retry.
    int stuckTries;
    bool repathPending;
    float repathTimer;
    bool bigBudgetTried;
    bool approached;
    float approachTimer;

    // Custom pathfinding state
    PolisAStar polisAStar;
    DoorInteractionHandler doorHandler;
    List<BlockPos> openedDoors;
    List<PolisPathNode> currentPath;

    public PolisGotoAction(
        EntityActivitySystem vas,
        Vec3d target,
        bool astar,
        string animCode,
        float walkSpeed,
        float animSpeed,
        Action<string> debugLog,
        Action<List<BlockPos>> debugPath,
        bool debugEnabled,
        bool allowFallback,
        Action<bool, string> onResult = null,
        bool usePolisAStar = true,
        bool openDoors = true,
        bool closeDoors = false
    )
    {
        this.vas = vas;
        Target = target;
        Astar = astar;
        AnimCode = animCode;
        WalkSpeed = walkSpeed;
        AnimSpeed = animSpeed;
        this.debugLog = debugLog;
        this.debugPath = debugPath;
        this.debugEnabled = debugEnabled;
        this.allowFallback = allowFallback;
        this.onResult = onResult;
        UsePolisAStar = usePolisAStar;
        OpenDoors = openDoors;
        CloseDoors = closeDoors;
    }

    public override void Start(EntityActivity act)
    {
        done = false;
        ExecutionHasFailed = false;
        fallbackTried = false;
        resultSent = false;
        openedDoors = new List<BlockPos>();
        currentPath = null;
        navPhase = 0;
        phaseElapsed = 0f;

        hereTarget = Target.Clone();
        astarTries = 4;
        stuckTries = 0;
        repathPending = false;
        repathTimer = 0f;
        bigBudgetTried = false;
        approached = false;
        approachTimer = 0f;

        EnsureTraversers();
        InitializeCustomPathfinding();
        LiftIfEmbedded();
        PolisSystem.TrySetTraverserDebug(vas?.wppathTraverser, false, debugLog);
        debugLog?.Invoke($"[goto] start target={PolisSystem.FormatPos(hereTarget)} astar={Astar} usePolisAStar={UsePolisAStar} speed={WalkSpeed.ToString(CultureInfo.InvariantCulture)}");
        navTo(hereTarget);
    }

    /// <summary>
    /// Self-rescue (2026-10-05): if the body's feet cell is solid - the
    /// bot is buried, from any source (a legacy snap, a physics slip) -
    /// lift it up one block at a time until its feet are in a clear cell.
    /// A body inside a solid cannot start any path, so no navigation can
    /// even begin until it is out. Bounded to 4 blocks.
    /// </summary>
    void LiftIfEmbedded()
    {
        var e = vas?.Entity;
        if (e == null) return;
        var ba = e.Api.World.BlockAccessor;
        for (int i = 0; i < 4; i++)
        {
            var feet = e.ServerPos.AsBlockPos;
            var b = ba.GetBlock(feet);
            bool solid = b != null
                && b.CollisionBoxes != null && b.CollisionBoxes.Length > 0
                && !string.IsNullOrEmpty(b.Code?.Path)
                && !b.Code.Path.StartsWith("air");
            if (!solid) break;
            e.ServerPos.Y += 1.0;
            e.Pos.Y += 1.0;
            debugLog?.Invoke($"[goto] self-rescue: feet in solid {b.Code?.Path} at {feet} - lifted to y{e.ServerPos.Y:F1}");
        }
    }

    void InitializeCustomPathfinding()
    {
        if (UsePolisAStar && vas?.Entity?.Api != null)
        {
            var blockAccessor = vas.Entity.Api.World.GetCachingBlockAccessor(true, true);
            polisAStar = new PolisAStar(blockAccessor, debugEnabled ? debugLog : null);
            doorHandler = new DoorInteractionHandler(vas.Entity.Api.World, debugEnabled ? debugLog : null);
        }
    }

    void EnsureTraversers()
    {
        if (vas.linepathTraverser == null) vas.linepathTraverser = new StraightLineTraverser(vas.Entity);
        if (vas.wppathTraverser == null) vas.wppathTraverser = new WaypointsTraverser(vas.Entity);
    }

    /// <summary>
    /// Re-prime the entity's traversers with fresh instances.
    /// 1.22 (measured 2026-10-04 pilot): a traverser whose route state
    /// wedges (async slot left over a save/reload, a half-consumed
    /// route) never recovers — the bot oscillates its heading in a
    /// 3-cycle or freezes with the traverser inactive, while a
    /// brand-new traverser on the same entity walks the same path
    /// fine. Cheap enough to do on every navigation start and ladder
    /// transition, so a wedged entity degrades to one failed attempt
    /// instead of every future one.
    /// </summary>
    void ResetTraversers()
    {
        vas.linepathTraverser?.Stop();
        vas.wppathTraverser?.Stop();
        vas.linepathTraverser = new StraightLineTraverser(vas.Entity);
        vas.wppathTraverser = new WaypointsTraverser(vas.Entity);
    }

    void navTo(Vec3d target)
    {
        ResetTraversers();
        phaseElapsed = 0f;
        EnumAICreatureType ct = EnumAICreatureType.Default;
        var serverAttrs = vas.Entity?.Properties?.Server?.Attributes;
        if (serverAttrs != null)
        {
            var aicreaturetype = serverAttrs.GetString("aiCreatureType", "Humanoid");
            if (Enum.TryParse(aicreaturetype, out EnumAICreatureType ect)) ct = ect;
        }
        else if (vas.Entity is EntityHumanoid)
        {
            ct = EnumAICreatureType.Humanoid;
        }

        // Try custom PolisAStar pathfinding first (fence/door aware)
        if (Astar && UsePolisAStar && polisAStar != null)
        {
            if (TryPolisAStarPath(target, ct))
            {
                return;
            }
            // F3 (2026-10-10): if the straight line to the target crosses
            // a step taller than the physics step height (a 2-block climb),
            // no route exists — the core A* can only return a phantom
            // route that stalls and "stucks". Fail immediately instead of
            // burning the ladder.
            if (CheckUncrossable(target)) return;
            // Fall through to VS pathfinder if PolisAStar fails
            debugLog?.Invoke("[goto] PolisAStar failed, trying VS pathfinder");
        }

        // Use VS's built-in pathfinding
        if (Astar)
        {
            vas.wppathTraverser.OnFoundPath = onFoundPath;
            // Use larger arrival threshold (0.7) so OnDone fires before bot climbs adjacent obstacles
            vas.wppathTraverser.NavigateTo_Async(target, WalkSpeed, 0.7f, OnDone, OnStuck, OnNoPath, 10000, 0, ct);
        }
        else
        {
            vas.linepathTraverser.NavigateTo(target, WalkSpeed, OnDone, OnStuck, null, 0, ct);
            setAnimation();
        }
    }

    /// <summary>
    /// Try to find path using custom PolisAStar with fence/door awareness.
    /// </summary>
    bool TryPolisAStarPath(Vec3d target, EnumAICreatureType ct)
    {
        var startPos = polisAStar.GetStartPos(vas.Entity.ServerPos.XYZ);
        var endPos = target.AsBlockPos;

        debugLog?.Invoke($"[goto] PolisAStar finding path from {startPos} to {endPos}");

        currentPath = polisAStar.FindPath(startPos, endPos);

        // F4 (2026-10-10): first no-path at the 5000-iteration budget:
        // one retry with a 4x budget (20000) before falling through to
        // the core A* — long walkarounds currently die on the search
        // cap (squared heuristic, no g-cost improvement).
        if ((currentPath == null || currentPath.Count < 2) && !bigBudgetTried)
        {
            bigBudgetTried = true;
            debugLog?.Invoke("[goto] PolisAStar no path at 5000 - one 4x retry (20000)");
            currentPath = polisAStar.FindPath(startPos, endPos, 20000);
        }

        if (currentPath == null || currentPath.Count < 2)
        {
            debugLog?.Invoke("[goto] PolisAStar no path found");
            return false;
        }

        debugLog?.Invoke($"[goto] PolisAStar path found: {currentPath.Count} nodes");

        // Handle doors along path
        if (OpenDoors && doorHandler != null)
        {
            var interactionNodes = PolisAStar.GetInteractionNodes(currentPath);
            if (interactionNodes.Count > 0)
            {
                debugLog?.Invoke($"[goto] opening {interactionNodes.Count} doors along path");
                openedDoors = doorHandler.OpenDoorsAlongPath(interactionNodes, vas.Entity);
            }
        }

        // Convert path to waypoints and use VS's traverser to execute
        var waypoints = PolisAStar.ToWaypoints(currentPath);

        // Debug: show path
        if (debugEnabled)
        {
            var blockPositions = currentPath.Select(n => n.BlockPos).ToList();
            debugPath?.Invoke(blockPositions);
            debugLog?.Invoke($"[goto] path nodes: {string.Join(" -> ", blockPositions.Take(10).Select(p => $"({p.X},{p.Y},{p.Z})"))}");
        }

        // Use WaypointsTraverser to walk the path
        if (waypoints != null && waypoints.Count > 0)
        {
            vas.wppathTraverser.OnFoundPath = onFoundPath;
            // FollowRoute takes a list of waypoints and walks through them
            (vas.wppathTraverser as WaypointsTraverser)?.FollowRoute(waypoints, WalkSpeed, 0.7f, OnDone, OnStuck);
            setAnimation();
            return true;
        }

        return false;
    }

    /// <summary>
    /// F3 (2026-10-10): if the straight line bot→target has a step
    /// taller than the physics step height (1.01 — a 2-block climb is
    /// impossible), the target is uncrossable: fail immediately with a
    /// distinct result instead of the 45 s ladder. Returns true if the
    /// action was failed.
    /// </summary>
    bool CheckUncrossable(Vec3d target)
    {
        if (!UsePolisAStar || !Astar || polisAStar == null) return false;
        var start = polisAStar.GetStartPos(vas.Entity.Pos.XYZ);
        if (polisAStar.FindUncrossableStep(start, target.AsBlockPos, 1.01f, out var step, out int stepBlocks))
        {
            string at = PolisSystem.FormatPos(new Vec3d(step.X, step.Y, step.Z));
            debugLog?.Invoke($"[goto] uncrossable: {stepBlocks}-block step at {at} - failing before the ladder");
            ExecutionHasFailed = true;
            ReportResult(false, $"uncrossable: {stepBlocks}-block step at {at}");
            Finish();
            return true;
        }
        return false;
    }

    void setAnimation()
    {
        if (AnimSpeed != 0.02f)
        {
            vas.Entity.AnimManager.StartAnimation(new AnimationMetaData
            {
                Animation = AnimCode,
                Code = AnimCode,
                AnimationSpeed = AnimSpeed,
                BlendMode = EnumAnimationBlendMode.Average
            }.Init());
        }
        else if (!vas.Entity.AnimManager.StartAnimation(AnimCode))
        {
            vas.Entity.AnimManager.StartAnimation(new AnimationMetaData
            {
                Animation = AnimCode,
                Code = AnimCode,
                AnimationSpeed = AnimSpeed,
                BlendMode = EnumAnimationBlendMode.Average
            }.Init());
        }

        vas.Entity.Controls.Sprint = AnimCode == "run" || AnimCode == "sprint";
    }

    void onFoundPath()
    {
        setAnimation();
        if (debugEnabled)
        {
            if (PolisSystem.TryExtractPathFromTraverser(vas?.wppathTraverser, out var blocks, out var rawCount, out var source))
            {
                debugLog?.Invoke($"[goto] path found nodes={rawCount} source={source}");
                debugPath?.Invoke(blocks);
            }
            else
            {
                debugLog?.Invoke("[goto] path found (no path data exposed)");
                if (!loggedPathIntrospection)
                {
                    loggedPathIntrospection = true;
                    debugLog?.Invoke("[goto] traverser members: " + PolisSystem.DescribeTraverserMembers(vas?.wppathTraverser));
                }
            }
        }
    }

    // A bounded navigation ladder. 1.22 gotcha (measured 2026-09-22): if a
    // world is saved/reloaded with an async path search in flight, the
    // traverser's async slot can stay wedged (NavigateTo_Async silently
    // returns false) and every later async navigation for that entity
    // hangs without a single callback. The ladder keeps each attempt
    // time-boxed and degrades to a pathfinder-free straight-line walk, so
    // a goto can never hang the mission forever.
    const float PHASE_TIMEOUT = 15f;
    int navPhase;         // 0: primary (async A* or straight line per Astar)
                          // 1: sync A* retry   2: straight-line retry
    float phaseElapsed;

    float hbAccum;
    public override void OnTick(float dt)
    {
        if (done || ExecutionHasFailed) return;
        hbAccum += dt;
        if (hbAccum >= 1f)
        {
            hbAccum = 0f;
            debugLog?.Invoke($"[goto] action-tick heartbeat: phase={navPhase} elapsed={phaseElapsed:F1} target={PolisSystem.FormatPos(hereTarget)} nav={DescribeNavState()}");
        }
        if (repathPending)
        {
            repathTimer -= dt;
            if (repathTimer <= 0f)
            {
                repathPending = false;
                // Re-issue from our A*; navTo resets the traversers
                // first, so a wedged traverser (a known 1.22 trap) does
                // not carry over into the new attempt.
                navPhase = 0;
                navTo(hereTarget);
            }
            return;
        }
        if (approachTimer > 0f)
        {
            approachTimer -= dt;
            if (approachTimer <= 0f)
            {
                debugLog?.Invoke("[goto] one-step approach bound reached, settling");
                vas.linepathTraverser?.Stop();
                OnDone();
            }
            return;
        }
        phaseElapsed += dt;
        if (phaseElapsed < PHASE_TIMEOUT) return;
        phaseElapsed = 0f;
        debugLog?.Invoke($"[goto] phase {navPhase} timed out, degrading");
        stop();
        ResetTraversers();
        navPhase++;
        if (navPhase == 1 && Astar && vas.wppathTraverser != null)
        {
            vas.wppathTraverser.OnFoundPath = onFoundPath;
            vas.wppathTraverser.NavigateTo(hereTarget, WalkSpeed, 0.7f, OnDone, OnStuck, OnNoPath, false, 500, 0);
        }
        else if (navPhase == 2 && vas.linepathTraverser != null)
        {
            vas.linepathTraverser.NavigateTo(hereTarget, WalkSpeed, OnDone, OnStuck, null, 0, EnumAICreatureType.Humanoid);
            setAnimation();
        }
        else
        {
            ExecutionHasFailed = true;
            ReportResult(false, "stuck: all navigation modes timed out");
            Finish();
        }
    }

    void OnNoPath()
    {
        phaseElapsed = 0f;
        if (Astar && astarTries > 0)
        {
            astarTries--;
            navTo(hereTarget);
            return;
        }

        if (Astar && allowFallback && !fallbackTried)
        {
            fallbackTried = true;
            Astar = false;
            debugLog?.Invoke("[goto] no path, falling back to straight-line");
            navTo(hereTarget);
            return;
        }

        debugLog?.Invoke("[goto] no path");
        ExecutionHasFailed = true;
        ReportResult(false, "no path");
        Finish();
    }

    // F1 (2026-10-10): bounded repath. 1.22 live matrix: the traverser's
    // stuck counter fires after ~1 s on a phantom core-A* route (2-block
    // step), on the knife-edge arrival flake, and on transient wedges
    // (door re-closing, a wedged route state). The old code killed the
    // goto instantly, wasting every one of them; a repath that resets
    // the traversers recovers them. Three tries, then an honest fail.
    const int MAX_STUCK_REPATHS = 3;

    void OnStuck()
    {
        string pos = PolisSystem.FormatPos(vas?.Entity?.Pos?.XYZ);
        debugLog?.Invoke("[goto] stuck pos=" + pos);
        if (approachTimer > 0f)
        {
            // Stuck during the F2 one-step approach: the step-up failed.
            // Settle and evaluate the arrival honestly.
            approachTimer = 0f;
            vas.linepathTraverser?.Stop();
            OnDone();
            return;
        }
        if (stuckTries < MAX_STUCK_REPATHS)
        {
            stuckTries++;
            repathPending = true;
            repathTimer = 1.0f;
            debugLog?.Invoke($"[goto] stuck #{stuckTries}/{MAX_STUCK_REPATHS} - repathing after 1 s (traverser reset)");
            stop();
            return;
        }
        ExecutionHasFailed = true;
        ReportResult(false, $"stuck after {stuckTries} repaths (last {pos})");
        Finish();
    }

    void OnDone()
    {
        vas.Entity.AnimManager.StopAnimation(AnimCode);
        vas.Entity.Controls.StopAllMovement();
        // Stop momentum immediately to prevent overshoot/sliding
        vas.Entity.Pos.Motion.Set(0, 0, 0);

        var epos = vas.Entity.Pos.XYZ;
        double dx = hereTarget.X - epos.X;
        double dy = hereTarget.Y - epos.Y;
        double dz = hereTarget.Z - epos.Z;
        double hdist = Math.Sqrt(dx * dx + dz * dz);
        double dist = Math.Sqrt(hdist * hdist + dy * dy);

        // F2 (2026-10-10): height-aware arrival. The traverser reports
        // "done" when the bot is at the right X/Z but a full block below
        // (or above) the target — the 3-D distance check alone reads
        // that as "done" and the follow-up work action dies out of range
        // (and the core near-test is knife-edge at exactly dy=1, missing
        // by 0.01). One bounded straight-line approach at the target
        // lets physics step-up do the last block; afterwards dy < 0.4
        // means done, anything else is reported honestly.
        if (!approached && hdist <= 3.0 && Math.Abs(dy) >= 0.75)
        {
            debugLog?.Invoke($"[goto] dy={dy:F2} hdist={hdist:F2} - one-step approach at target (5 s bound)");
            approached = true;
            approachTimer = 5.0f;
            vas.linepathTraverser?.Stop();
            vas.linepathTraverser = new StraightLineTraverser(vas.Entity);
            vas.linepathTraverser.NavigateTo(hereTarget, WalkSpeed, OnDone, OnStuck, null, 0, EnumAICreatureType.Humanoid);
            setAnimation();
            return;
        }

        if (approachTimer > 0f) approachTimer = 0f;

        if (approached && Math.Abs(dy) >= 0.4)
        {
            debugLog?.Invoke($"[goto] approach could not close dy={dy:F2}");
            ExecutionHasFailed = true;
            ReportResult(false, "one step short of " + PolisSystem.FormatPos(hereTarget));
            Finish();
            return;
        }

        // Honest arrival (2026-10-04 pilot): a wedged traverser can fire
        // OnDone on a 1-node "direct" path while the bot is still blocks
        // away; snapping would be a teleport dressed as a walk. Only snap
        // when the traverser actually got the bot there.
        if (dist > 1.5)
        {
            debugLog?.Invoke($"[goto] done but {dist:F1} blocks from target (wedged route?) — not snapping");
            ExecutionHasFailed = true;
            ReportResult(false, $"traverser reported done {dist:F1} blocks from target");
            Finish();
            return;
        }

        // Snap to exact target position to prevent landing on adjacent
        // blocks - but NEVER into a solid cell. 2026-10-05 root cause of
        // the dirt-mine wedge: the approach's first candidate IS the solid
        // block being mined; the traverser correctly stops one cell short,
        // but an unconditional snap pulled the bot INTO that solid, and a
        // body inside a block cannot start any path ("stuck" forever).
        // If the target cell is solid, the bot is already in interaction
        // range one cell away - leave it there.
        var targetCell = hereTarget.AsBlockPos;
        var targetBlock = vas.Entity.Api.World.BlockAccessor.GetBlock(targetCell);
        bool targetIsSolid = targetBlock != null
            && targetBlock.CollisionBoxes != null
            && targetBlock.CollisionBoxes.Length > 0
            && !string.IsNullOrEmpty(targetBlock.Code?.Path)
            && !targetBlock.Code.Path.StartsWith("air");
        if (targetIsSolid)
        {
            debugLog?.Invoke($"[goto] target {targetCell} is solid ({targetBlock.Code?.Path}) - not snapping; bot stays one cell short (in range)");
        }
        else
        {
            vas.Entity.ServerPos.SetPos(hereTarget.X, hereTarget.Y, hereTarget.Z);
            vas.Entity.Pos.SetPos(hereTarget.X, hereTarget.Y, hereTarget.Z);
        }

        // Close doors that were opened during navigation
        if (CloseDoors && doorHandler != null && openedDoors != null && openedDoors.Count > 0)
        {
            debugLog?.Invoke($"[goto] closing {openedDoors.Count} doors");
            doorHandler.CloseOpenedDoors(openedDoors, vas.Entity);
            openedDoors.Clear();
        }

        done = true;
        debugLog?.Invoke("[goto] reached destination pos=" + PolisSystem.FormatPos(vas?.Entity?.ServerPos?.XYZ));
        ClearDebugPath();
        ReportResult(true, "done");
    }

    void stop()
    {
        vas.linepathTraverser?.Stop();
        vas.wppathTraverser?.Stop();
        vas.Entity.AnimManager.StopAnimation(AnimCode);
        vas.Entity.Controls.StopAllMovement();
        // Stop momentum immediately to prevent overshoot/sliding
        vas.Entity.ServerPos.Motion.Set(0, 0, 0);
    }

    public override void Cancel()
    {
        Finish();
    }

    public override void Finish()
    {
        stop();
        ClearDebugPath();

        // Close any doors that were opened (on cancel/finish)
        if (CloseDoors && doorHandler != null && openedDoors != null && openedDoors.Count > 0)
        {
            debugLog?.Invoke($"[goto] closing {openedDoors.Count} doors on finish");
            doorHandler.CloseOpenedDoors(openedDoors, vas.Entity);
            openedDoors.Clear();
        }
    }

    public override bool IsFinished()
    {
        return done || ExecutionHasFailed;
    }

    public override IEntityAction Clone()
    {
        return new PolisGotoAction(vas, Target.Clone(), Astar, AnimCode, WalkSpeed, AnimSpeed, debugLog, debugPath, debugEnabled, allowFallback, onResult, UsePolisAStar, OpenDoors, CloseDoors);
    }

    void ClearDebugPath()
    {
        debugPath?.Invoke(null);
    }

    void ReportResult(bool ok, string msg)
    {
        if (resultSent) return;
        resultSent = true;
        onResult?.Invoke(ok, msg);
    }

    /// <summary>
    /// One-line diagnosis of why the entity may not be moving: which traverser
    /// is active, whether the waypoint traverser's async search slot is wedged,
    /// its stuck counter, and the entity's motion/controls at the moment.
    /// (2026-10-04: added to chase mid-walk stalls on flat terrain.)
    /// </summary>
    string DescribeNavState()
    {
        if (vas?.Entity == null) return "(no entity)";
        var e = vas.Entity;
        var wp = vas.wppathTraverser;
        var ln = vas.linepathTraverser;
        string s = $"wp.active={(wp?.Active.ToString() ?? "?")} ln.active={(ln?.Active.ToString() ?? "?")} " +
                  $"yaw={e.Pos.Yaw * 57.2958F:F0} motion=({e.Pos.Motion.X:F2},{e.Pos.Motion.Y:F2},{e.Pos.Motion.Z:F2}) " +
                  $"walk=({e.Controls.WalkVector.X:F2},{e.Controls.WalkVector.Z:F2}) onGround={e.OnGround}";
        if (wp != null)
        {
            var t = wp.GetType();
            var asyncF = t.GetField("asyncSearchObject", System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic);
            var stuckF = t.BaseType?.GetField("stuckCounter", System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic)
                         ?? t.GetField("stuckCounter", System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic);
            object async = asyncF?.GetValue(wp);
            string asyncDesc;
            if (async == null) asyncDesc = "null";
            else asyncDesc = async.GetType().Name + ".finished=" + (async.GetType().GetProperty("Finished")?.GetValue(async) ?? "?");
            s += $" async={asyncDesc}";
            if (stuckF != null) s += $" stuckCnt={stuckF.GetValue(wp)}";
        }
        return s;
    }
}
