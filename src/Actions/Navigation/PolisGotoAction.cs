using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using Vintagestory.API.Common;
using Vintagestory.API.Common.Entities;
using Vintagestory.API.MathTools;
using Vintagestory.Essentials;
using Vintagestory.GameContent;

namespace PolisBuilderNpc.Actions.Navigation;

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

        EnsureTraversers();
        InitializeCustomPathfinding();
        PolisBuilderNpcSystem.TrySetTraverserDebug(vas?.wppathTraverser, false, debugLog);
        debugLog?.Invoke($"[goto] start target={PolisBuilderNpcSystem.FormatPos(hereTarget)} astar={Astar} usePolisAStar={UsePolisAStar} speed={WalkSpeed.ToString(CultureInfo.InvariantCulture)}");
        navTo(hereTarget);
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

    void navTo(Vec3d target)
    {
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
            if (PolisBuilderNpcSystem.TryExtractPathFromTraverser(vas?.wppathTraverser, out var blocks, out var rawCount, out var source))
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
                    debugLog?.Invoke("[goto] traverser members: " + PolisBuilderNpcSystem.DescribeTraverserMembers(vas?.wppathTraverser));
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
            debugLog?.Invoke($"[goto] action-tick heartbeat: phase={navPhase} elapsed={phaseElapsed:F1} target={PolisBuilderNpcSystem.FormatPos(hereTarget)}");
        }
        phaseElapsed += dt;
        if (phaseElapsed < PHASE_TIMEOUT) return;
        phaseElapsed = 0f;
        debugLog?.Invoke($"[goto] phase {navPhase} timed out, degrading");
        stop();
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

    void OnStuck()
    {
        debugLog?.Invoke("[goto] stuck pos=" + PolisBuilderNpcSystem.FormatPos(vas?.Entity?.ServerPos?.XYZ));
        ExecutionHasFailed = true;
        ReportResult(false, "stuck");
        Finish();
    }

    void OnDone()
    {
        vas.Entity.AnimManager.StopAnimation(AnimCode);
        vas.Entity.Controls.StopAllMovement();
        // Stop momentum immediately to prevent overshoot/sliding
        vas.Entity.ServerPos.Motion.Set(0, 0, 0);
        vas.Entity.Pos.Motion.Set(0, 0, 0);
        // Snap to exact target position to prevent landing on adjacent blocks
        // This ensures bot ends up exactly where requested, not on nearby obstacles
        vas.Entity.ServerPos.SetPos(hereTarget.X, hereTarget.Y, hereTarget.Z);
        vas.Entity.Pos.SetPos(hereTarget.X, hereTarget.Y, hereTarget.Z);

        // Close doors that were opened during navigation
        if (CloseDoors && doorHandler != null && openedDoors != null && openedDoors.Count > 0)
        {
            debugLog?.Invoke($"[goto] closing {openedDoors.Count} doors");
            doorHandler.CloseOpenedDoors(openedDoors, vas.Entity);
            openedDoors.Clear();
        }

        done = true;
        debugLog?.Invoke("[goto] reached destination pos=" + PolisBuilderNpcSystem.FormatPos(vas?.Entity?.ServerPos?.XYZ));
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
}
