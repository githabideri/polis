using System;
using Vintagestory.API.Common;
using Vintagestory.API.MathTools;
using Vintagestory.API.Server;
using Vintagestory.Essentials;
using Vintagestory.GameContent;

namespace PolisBuilderNpc.Actions.Workstations;

/// <summary>
/// Polling action that waits for a forge or firepit's input item to reach working temperature.
/// Supports both BlockEntityForge (for ingot heating) and BlockEntityFirepit (for smelting).
/// </summary>
class PolisForgeHeatAction : EntityActionBase
{
    // === Constructor Parameters ===
    readonly BlockPos targetPos;
    readonly IServerPlayer player;
    readonly float targetTemp;
    readonly float maxDuration;
    readonly float maxRange;
    readonly Action<string> debugLog;
    readonly Action<bool, string> onResult;

    // === Runtime State ===
    BlockEntityFirepit firepitEntity;
    BlockEntityForge forgeEntity;
    bool isForge;
    float tickAccumulator;
    float elapsedTime;
    bool done;
    bool validated;
    int fuelGraceTicks;

    // === Constants ===
    const float TICK_INTERVAL = 0.5f;
    const int FUEL_CHECK_GRACE_TICKS = 6; // ~3s before failing on fuel exhaustion
    const float DEFAULT_MAX_RANGE = 4.5f;
    const float DEFAULT_MAX_DURATION = 120f;

    public override string Type => "polis-forge-heat";

    public PolisForgeHeatAction(
        BlockPos targetPos,
        IServerPlayer player,
        float targetTemp,
        float maxDuration = DEFAULT_MAX_DURATION,
        float maxRange = DEFAULT_MAX_RANGE,
        Action<string> debugLog = null,
        Action<bool, string> onResult = null
    )
    {
        this.targetPos = targetPos;
        this.player = player;
        this.targetTemp = targetTemp;
        this.maxDuration = maxDuration;
        this.maxRange = maxRange;
        this.debugLog = debugLog;
        this.onResult = onResult;
    }

    float GetCurrentTemp()
    {
        if (isForge)
        {
            var workItem = forgeEntity?.WorkItemStack;
            if (workItem == null) return 0;
            return workItem.Collectible.GetTemperature(vas.Entity.Api.World, workItem);
        }
        return firepitEntity?.InputStackTemp ?? 0;
    }

    bool HasContents()
    {
        if (isForge) return forgeEntity?.WorkItemStack != null;
        return firepitEntity != null && !firepitEntity.inputSlot.Empty;
    }

    bool IsBurning()
    {
        if (isForge) return forgeEntity?.IsBurning ?? false;
        return firepitEntity?.IsBurning ?? false;
    }

    bool RefreshEntity(IWorldAccessor world)
    {
        if (isForge)
        {
            forgeEntity = world.BlockAccessor.GetBlockEntity(targetPos) as BlockEntityForge;
            return forgeEntity != null;
        }
        firepitEntity = world.BlockAccessor.GetBlockEntity(targetPos) as BlockEntityFirepit;
        return firepitEntity != null;
    }

    public override void Start(EntityActivity entityActivity)
    {
        done = false;
        tickAccumulator = 0f;
        elapsedTime = 0f;
        fuelGraceTicks = 0;
        var world = vas.Entity.Api.World;

        // --- Range Check ---
        var center = new Vec3d(targetPos.X + 0.5, targetPos.Y + 0.5, targetPos.Z + 0.5);
        double dist = vas.Entity.ServerPos.XYZ.DistanceTo(center);
        if (dist > maxRange)
        {
            debugLog?.Invoke($"[forge-heat] failed: out of range dist={dist:F1} > {maxRange}");
            ReportResult(false, $"out of range: {dist:F1} > {maxRange}");
            ExecutionHasFailed = true;
            done = true;
            return;
        }

        // --- Player Validation ---
        if (player == null)
        {
            debugLog?.Invoke("[forge-heat] failed: missing player");
            ReportResult(false, "missing player");
            ExecutionHasFailed = true;
            done = true;
            return;
        }

        // --- Try BlockEntityForge first, then BlockEntityFirepit ---
        forgeEntity = world.BlockAccessor.GetBlockEntity(targetPos) as BlockEntityForge;
        if (forgeEntity != null)
        {
            isForge = true;
        }
        else
        {
            firepitEntity = world.BlockAccessor.GetBlockEntity(targetPos) as BlockEntityFirepit;
            if (firepitEntity == null)
            {
                debugLog?.Invoke("[forge-heat] failed: no forge or firepit block entity at target");
                ReportResult(false, "no forge or firepit block entity at target");
                ExecutionHasFailed = true;
                done = true;
                return;
            }
            isForge = false;
        }

        string blockType = isForge ? "forge" : "firepit";

        // --- Check contents ---
        if (!HasContents())
        {
            debugLog?.Invoke($"[forge-heat] failed: {blockType} has no contents to heat");
            ReportResult(false, $"{blockType} has no contents to heat");
            ExecutionHasFailed = true;
            done = true;
            return;
        }

        // --- Check burning ---
        if (!IsBurning())
        {
            debugLog?.Invoke($"[forge-heat] failed: {blockType} is not burning");
            ReportResult(false, $"{blockType} is not burning");
            ExecutionHasFailed = true;
            done = true;
            return;
        }

        // --- Check if already at temp ---
        float currentTemp = GetCurrentTemp();
        if (currentTemp >= targetTemp)
        {
            debugLog?.Invoke($"[forge-heat] already at temperature: {currentTemp:F0}°C >= {targetTemp:F0}°C");
            ReportResult(true, $"already at temperature: {currentTemp:F0}°C >= {targetTemp:F0}°C");
            done = true;
            return;
        }

        validated = true;
        debugLog?.Invoke($"[forge-heat] started: waiting for {targetTemp:F0}°C at {targetPos} ({blockType}), current={currentTemp:F0}°C, maxDuration={maxDuration:F0}s");
    }

    public override void OnTick(float dt)
    {
        if (!validated || done) return;

        elapsedTime += dt;

        // --- Timeout check ---
        if (elapsedTime >= maxDuration)
        {
            float currentTemp = GetCurrentTemp();
            debugLog?.Invoke($"[forge-heat] timeout after {elapsedTime:F1}s, temp={currentTemp:F0}°C / {targetTemp:F0}°C");
            ReportResult(false, $"timeout after {elapsedTime:F1}s (temp={currentTemp:F0}°C, target={targetTemp:F0}°C)");
            ExecutionHasFailed = true;
            done = true;
            return;
        }

        tickAccumulator += dt;
        if (tickAccumulator < TICK_INTERVAL) return;
        tickAccumulator = 0f;

        var world = vas.Entity.Api.World;

        // --- Refresh block entity ---
        if (!RefreshEntity(world))
        {
            debugLog?.Invoke("[forge-heat] block entity gone");
            ReportResult(false, "block entity gone");
            ExecutionHasFailed = true;
            done = true;
            return;
        }

        // --- Check contents still present ---
        if (!HasContents())
        {
            debugLog?.Invoke("[forge-heat] contents became empty (item melted or removed)");
            ReportResult(false, "contents became empty");
            ExecutionHasFailed = true;
            done = true;
            return;
        }

        // --- Read temperature ---
        float temp = GetCurrentTemp();
        debugLog?.Invoke($"[forge-heat] temp={temp:F0}°C / {targetTemp:F0}°C ({elapsedTime:F1}s)");

        // --- Success check ---
        if (temp >= targetTemp)
        {
            debugLog?.Invoke($"[forge-heat] target reached: {temp:F0}°C >= {targetTemp:F0}°C in {elapsedTime:F1}s");
            ReportResult(true, $"heated to {temp:F0}°C in {elapsedTime:F1}s");
            done = true;
            return;
        }

        // --- Fuel exhaustion check with grace period ---
        if (!IsBurning())
        {
            fuelGraceTicks++;
            if (fuelGraceTicks >= FUEL_CHECK_GRACE_TICKS)
            {
                debugLog?.Invoke($"[forge-heat] fuel exhausted, temp={temp:F0}°C / {targetTemp:F0}°C");
                ReportResult(false, $"fuel exhausted (temp={temp:F0}°C, target={targetTemp:F0}°C)");
                ExecutionHasFailed = true;
                done = true;
            }
        }
        else
        {
            fuelGraceTicks = 0;
        }
    }

    public override void Cancel()
    {
        float temp = GetCurrentTemp();
        debugLog?.Invoke($"[forge-heat] cancelled at {elapsedTime:F1}s, temp={temp:F0}°C");
        ReportResult(false, $"cancelled (temp={temp:F0}°C)");
        done = true;
        base.Cancel();
    }

    public override bool IsFinished() => done;

    public override IEntityAction Clone()
    {
        return new PolisForgeHeatAction(targetPos, player, targetTemp, maxDuration, maxRange, debugLog, onResult);
    }

    void ReportResult(bool ok, string msg)
    {
        onResult?.Invoke(ok, msg);
    }
}
