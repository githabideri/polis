using System;
using Vintagestory.API.Common;
using Vintagestory.API.Common.Entities;
using Vintagestory.API.Server;
using Vintagestory.Essentials;
using Vintagestory.GameContent;
using PolisBuilderNpc.Helpers;

namespace PolisBuilderNpc.Actions.Entities;

/// <summary>
/// Timed action to butcher dead entities (animals) using a knife.
/// Plays a looping hit animation for ~1s, then calls SetHarvested() and transfers drops to bot inventory.
/// </summary>
class PolisButcherEntityAction : EntityActionBase
{
    // === Constructor Parameters ===
    readonly long targetEntityId;
    readonly IServerPlayer player;
    readonly float maxRange;
    readonly bool autoCollectDrops;
    readonly float dropQuantityMultiplier;
    readonly Action<string> debugLog;
    readonly Action<bool, string> onResult;

    // === Runtime State ===
    bool done;
    bool validated;
    float butcherTime;
    PolisAnimationHelpers.LoopingAnimationState animState;
    EntityAgent validatedAgent;
    Entity validatedTarget;
    EntityBehaviorHarvestable validatedHarvestBehavior;

    // === Constants ===
    const float DEFAULT_MAX_RANGE = 4.5f;
    const float DEFAULT_DROP_MULTIPLIER = 1.0f;
    const float BUTCHER_DURATION = 1.0f;

    public override string Type => "polis-butcher";

    public PolisButcherEntityAction(
        long targetEntityId,
        IServerPlayer player,
        float maxRange = DEFAULT_MAX_RANGE,
        bool autoCollectDrops = true,
        float dropQuantityMultiplier = DEFAULT_DROP_MULTIPLIER,
        Action<string> debugLog = null,
        Action<bool, string> onResult = null
    )
    {
        this.targetEntityId = targetEntityId;
        this.player = player;
        this.maxRange = maxRange;
        this.autoCollectDrops = autoCollectDrops;
        this.dropQuantityMultiplier = dropQuantityMultiplier;
        this.debugLog = debugLog;
        this.onResult = onResult;
    }

    public override void Start(EntityActivity entityActivity)
    {
        done = false;
        var world = vas.Entity.Api.World;
        var agent = vas.Entity as EntityAgent;

        // --- Find Target Entity ---
        var targetEntity = world.GetEntityById(targetEntityId);
        if (targetEntity == null)
        {
            debugLog?.Invoke($"[butcher] failed: entity {targetEntityId} not found");
            ReportResult(false, $"Entity {targetEntityId} not found");
            ExecutionHasFailed = true;
            done = true;
            return;
        }

        // --- Range Check ---
        double dist = vas.Entity.ServerPos.XYZ.DistanceTo(targetEntity.ServerPos.XYZ);
        if (dist > maxRange)
        {
            debugLog?.Invoke($"[butcher] failed: out of range dist={dist:F1} > {maxRange}");
            ReportResult(false, $"Target too far: {dist:F1} > {maxRange}");
            ExecutionHasFailed = true;
            done = true;
            return;
        }

        // --- Player Validation ---
        if (player == null)
        {
            debugLog?.Invoke("[butcher] failed: missing player");
            ReportResult(false, "missing player");
            ExecutionHasFailed = true;
            done = true;
            return;
        }

        // --- Get Harvestable Behavior ---
        var harvestBehavior = targetEntity.GetBehavior<EntityBehaviorHarvestable>();
        if (harvestBehavior == null)
        {
            debugLog?.Invoke($"[butcher] failed: entity {targetEntity.Code} is not harvestable");
            ReportResult(false, $"Entity {targetEntity.Code} is not harvestable");
            ExecutionHasFailed = true;
            done = true;
            return;
        }

        // --- Check if Already Harvested ---
        if (harvestBehavior.IsHarvested)
        {
            debugLog?.Invoke("[butcher] failed: entity already harvested");
            ReportResult(false, "Entity already harvested");
            ExecutionHasFailed = true;
            done = true;
            return;
        }

        // --- Check if harvestable (dead and not harvested) ---
        // 1.22: IHarvestable has IsHarvested, not Harvestable
        if (targetEntity.Alive || harvestBehavior.IsHarvested)
        {
            if (targetEntity.Alive)
            {
                debugLog?.Invoke("[butcher] failed: entity is still alive");
                ReportResult(false, "Entity is still alive - kill it first");
            }
            else
            {
                debugLog?.Invoke("[butcher] failed: entity not harvestable (unknown reason)");
                ReportResult(false, "Entity not harvestable (unknown reason)");
            }
            ExecutionHasFailed = true;
            done = true;
            return;
        }

        // --- Validate Knife Equipped ---
        if (agent == null)
        {
            debugLog?.Invoke("[butcher] failed: bot is not an EntityAgent");
            ReportResult(false, "Bot is not an EntityAgent");
            ExecutionHasFailed = true;
            done = true;
            return;
        }

        var invbh = PolisInventoryHelpers.BotCargo(agent);
        if (invbh == null)
        {
            debugLog?.Invoke("[butcher] failed: bot has no inventory behavior");
            ReportResult(false, "Bot has no inventory behavior");
            ExecutionHasFailed = true;
            done = true;
            return;
        }

        var toolSlot = invbh[0]; // Right hand (cargo slot 0)
        if (toolSlot?.Itemstack?.Collectible?.Tool != EnumTool.Knife)
        {
            debugLog?.Invoke("[butcher] failed: knife required in right hand");
            ReportResult(false, "Knife required in right hand for butchering");
            ExecutionHasFailed = true;
            done = true;
            return;
        }

        // --- Begin Butchering (timed with animation) ---
        validatedAgent = agent;
        validatedTarget = targetEntity;
        validatedHarvestBehavior = harvestBehavior;
        animState = new PolisAnimationHelpers.LoopingAnimationState("hit", 1.0f, 0.3f);
        PolisAnimationHelpers.StartLoopingAnimation(agent, animState, debugLog);
        butcherTime = 0f;
        validated = true;
        debugLog?.Invoke($"[butcher] butchering {targetEntity.Code} (id={targetEntityId}), duration={BUTCHER_DURATION}s");
    }

    void TransferHarvestInventory(EntityAgent agent, Entity targetEntity)
    {
        // Access the harvestable behavior's inventory directly (not a copy from tree attributes)
        // This ensures clearing slots affects the actual inventory VS uses for despawn logic
        var harvestBehavior = targetEntity.GetBehavior<EntityBehaviorHarvestable>();
        if (harvestBehavior?.Inventory == null)
        {
            debugLog?.Invoke("[butcher] no harvest inventory found after butchering");
            return;
        }

        var harvestInv = harvestBehavior.Inventory;

        // Transfer each slot to bot and clear from harvest inventory
        int stacksTransferred = 0;
        int itemsTransferred = 0;

        for (int i = 0; i < harvestInv.Count; i++)
        {
            var slot = harvestInv[i];
            if (slot?.Itemstack == null) continue;

            int stackSize = slot.Itemstack.StackSize;
            // Clone the stack and try to insert into bot inventory
            ItemStack stack = slot.Itemstack.Clone();
            if (PolisInventoryHelpers.TryInsertIntoBotInventory(agent, stack, out int moved, out string _, debugLog))
            {
                stacksTransferred++;
                itemsTransferred += moved;
                debugLog?.Invoke($"[butcher] transferred: {moved}x {stack.Collectible?.Code}");

                // Clear the slot in the actual harvest inventory so VS knows items were taken
                if (moved >= stackSize)
                {
                    // Fully transferred - clear the slot
                    slot.Itemstack = null;
                }
                else
                {
                    // Partial transfer - reduce stack size
                    slot.Itemstack.StackSize -= moved;
                }
                slot.MarkDirty();
            }
            else
            {
                debugLog?.Invoke($"[butcher] could not transfer: {stack.StackSize}x {stack.Collectible?.Code} (inventory full?)");
            }
        }

        // Persist bot inventory
        PolisInventoryHelpers.StoreSeraphInventory(agent);

        debugLog?.Invoke($"[butcher] transfer complete: {stacksTransferred} stack(s), {itemsTransferred} total items");
    }

    public override void OnTick(float dt)
    {
        if (!validated || done) return;

        butcherTime += dt;
        PolisAnimationHelpers.UpdateLoopingAnimation(validatedAgent, animState, dt, debugLog);

        if (butcherTime >= BUTCHER_DURATION)
        {
            PolisAnimationHelpers.StopLoopingAnimation(validatedAgent, animState, debugLog);
            PerformHarvest();
        }
    }

    public override void Cancel()
    {
        PolisAnimationHelpers.StopLoopingAnimation(vas.Entity as EntityAgent, animState, debugLog);
        ReportResult(false, "cancelled");
        done = true;
        base.Cancel();
    }

    public override bool IsFinished() => done;

    public override IEntityAction Clone()
    {
        return new PolisButcherEntityAction(targetEntityId, player, maxRange, autoCollectDrops, dropQuantityMultiplier, debugLog, onResult);
    }

    void PerformHarvest()
    {
        validatedHarvestBehavior.SetHarvested(player, dropQuantityMultiplier);

        if (autoCollectDrops)
        {
            TransferHarvestInventory(validatedAgent, validatedTarget);
        }

        debugLog?.Invoke($"[butcher] complete: {validatedTarget.Code}");
        ReportResult(true, $"Butchered {validatedTarget.Code}");
        done = true;
    }

    void ReportResult(bool ok, string msg)
    {
        onResult?.Invoke(ok, msg);
    }
}
