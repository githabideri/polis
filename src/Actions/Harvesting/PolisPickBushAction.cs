using System;
using Vintagestory.API.Common;
using Vintagestory.API.Common.Entities;
using Vintagestory.API.Datastructures;
using Vintagestory.API.MathTools;
using Vintagestory.API.Server;
using Vintagestory.GameContent;
using Polis.Helpers;

namespace Polis.Actions.Harvesting;

/// <summary>
/// Picks berries from a ripe fruiting bush (BEBehaviorFruitingBush).
///
/// Fruiting bushes are NOT BlockBehaviorHarvestable (the harvest-block
/// action fails on them with "not harvestable"): the berry drop is the
/// block ENTITY's long-interact. Engine ground truth (1.22.7,
/// VSSurvivalMod decompiled):
///
///   * OnBlockInteractStart returns true only while BState.Growthstate
///     is Ripe (and plays the leafy-picking sound).
///   * OnBlockInteractStep returns true while secondsUsed <
///     harvestTime * mul — the "hold" of the pick.
///   * OnBlockInteractStop (server side, after the hold) computes the
///     drops (GetRipeDrops: per harvestedStack, scaled by the bush
///     health-state dropRates), gives them to the INTERACTING PLAYER,
///     audits, pushes the onitemcollected event, and advances the bush
///     to Mature (it regrows Flowering -> Ripening -> Ripe again, each
///     stage a fraction of an in-game month).
///
/// This action drives the vanilla Start/Step for the claims gate, the
/// ripeness re-check and the sound, but performs the completion itself:
/// the public GetRipeDrops() computes the stacks, they go into the bot's
/// cargo (overflow drops in-world), the onitemcollected event + audit
/// line are mirrored, and the growth state advances exactly like vanilla
/// setGrowthState(Mature) (Growthstate first, then TransitionHoursLeft
/// from GetHoursForNextStage() reading the new state, then MarkDirty).
///
/// Wild bush lifecycle (EnumFruitingBushGrowthState):
///   Young=0 Mature=1 Flowering=2 Ripening=3 Ripe=4 Dormant=5
/// A placed wild bush starts in a random Mature..Ripe state (murmur
/// hash of its position) and the cycle repeats after each pick.
/// </summary>
class PolisPickBushAction : EntityActionBase
{
    // === Constructor Parameters ===
    readonly BlockPos targetPos;
    readonly IServerPlayer player;
    readonly float maxRange;
    readonly Action<string> debugLog;
    readonly Action<bool, string> onResult;

    // === Runtime State ===
    BlockEntity blockEntity;
    BEBehaviorFruitingBush bush;
    Block block;
    float harvestTime;
    float elapsedTime;
    BlockSelection blockSel;
    bool validated;
    bool done;
    bool resultSent;

    // === Constants ===
    const float DEFAULT_MAX_RANGE = 4.5f;
    const float DEFAULT_HARVEST_TIME = 0.5f;

    public override string Type => "polis-pickbush";

    public PolisPickBushAction(
        BlockPos targetPos,
        IServerPlayer player,
        float maxRange = DEFAULT_MAX_RANGE,
        Action<string> debugLog = null,
        Action<bool, string> onResult = null
    )
    {
        this.targetPos = targetPos;
        this.player = player;
        this.maxRange = maxRange;
        this.debugLog = debugLog;
        this.onResult = onResult;
    }

    public override void Start(EntityActivity entityActivity)
    {
        done = false;
        resultSent = false;
        ExecutionHasFailed = false;
        elapsedTime = 0f;
        validated = false;

        var world = vas.Entity.Api.World;

        // --- Range Check ---
        var center = new Vec3d(targetPos.X + 0.5, targetPos.Y + 0.5, targetPos.Z + 0.5);
        double dist = vas.Entity.ServerPos.XYZ.DistanceTo(center);
        if (dist > maxRange)
        {
            Fail($"out of range: {dist:F1} > {maxRange}");
            return;
        }

        if (player == null)
        {
            Fail("missing player");
            return;
        }

        // --- Block / bush validation ---
        block = world.BlockAccessor.GetBlock(targetPos);
        if (block == null || block.Id == 0)
        {
            Fail("no block at target");
            return;
        }

        var bushBehavior = block.GetBehavior<BlockBehaviorFruitingBush>();
        if (bushBehavior == null)
        {
            Fail($"block {block.Code} is not a fruiting bush");
            return;
        }

        blockEntity = world.BlockAccessor.GetBlockEntity(targetPos);
        bush = blockEntity?.GetBehavior<BEBehaviorFruitingBush>();
        if (bush == null)
        {
            Fail($"bush at {targetPos} has no block-entity state");
            return;
        }

        if (bush.BState.Growthstate != EnumFruitingBushGrowthState.Ripe)
        {
            Fail($"bush not ripe (growth state: {bush.BState.Growthstate})");
            return;
        }

        harvestTime = bushBehavior.harvestTime > 0 ? bushBehavior.harvestTime : DEFAULT_HARVEST_TIME;

        blockSel = new BlockSelection
        {
            Position = targetPos,
            Face = BlockFacing.UP,
            HitPosition = new Vec3d(0.5, 0.5, 0.5),
            Block = block
        };

        // --- Vanilla claims/state gate + start sound ---
        EnumHandling handling = EnumHandling.None;
        if (!bush.OnBlockInteractStart(world, player, blockSel, ref handling))
        {
            Fail("interaction blocked (bush state or claims)");
            return;
        }

        validated = true;
        debugLog?.Invoke($"[pickbush] started: {block.Code} at {targetPos} harvestTime={harvestTime:F2}s (health: {bush.GetHealthState()})");
    }

    public override void OnTick(float dt)
    {
        if (!validated || done) return;

        var world = vas.Entity.Api.World;

        // The bush must still be the ripe one we started picking.
        var cur = world.BlockAccessor.GetBlock(targetPos);
        if (cur == null || cur.Id != block.Id || bush.BState.Growthstate != EnumFruitingBushGrowthState.Ripe)
        {
            debugLog?.Invoke("[pickbush] bush no longer ripe during pick");
            Report(true, "bush changed during pick (no drop)");
            Finish();
            done = true;
            return;
        }

        // --- Accumulate the hold, driving the vanilla step (effects) ---
        elapsedTime += dt;
        EnumHandling handling = EnumHandling.None;
        bool cont = bush.OnBlockInteractStep(elapsedTime, world, player, blockSel, ref handling);

        if (!cont || elapsedTime >= harvestTime)
        {
            CompletePickToBot(world);
        }
    }

    /// <summary>
    /// Completion the way the engine does it, minus the player handoff:
    /// drops computed by the bush itself, delivered to the bot's cargo,
    /// bush advanced to Mature (regrows to Ripe later).
    /// </summary>
    void CompletePickToBot(IWorldAccessor world)
    {
        var agent = vas.Entity as EntityAgent;
        int total = 0;

        var drops = bush.GetRipeDrops(player);
        if (drops != null)
        {
            foreach (var stack in drops)
            {
                if (stack == null || stack.StackSize <= 0 || stack.Collectible == null) continue;

                int originalSize = stack.StackSize;
                bool inserted = agent != null
                    && PolisInventoryHelpers.TryInsertIntoBotInventory(agent, stack, out int pickedUp, out string err, debugLog);

                if (inserted)
                {
                    total += pickedUp;
                    debugLog?.Invoke($"[pickbush] gave {pickedUp}x {stack.Collectible.Code} to bot");

                    if (pickedUp < originalSize)
                    {
                        var overflow = stack.Clone();
                        overflow.StackSize = originalSize - pickedUp;
                        world.SpawnItemEntity(overflow, blockSel.Position);
                        debugLog?.Invoke($"[pickbush] dropped overflow {overflow.StackSize}x {stack.Collectible.Code}");
                    }

                    world.Logger.Audit("{0} picked {1}x{2} from {3} at {4}.",
                        player.PlayerName, pickedUp, stack.Collectible.Code, block.Code, blockSel.Position);

                    var evt = new TreeAttribute();
                    evt["itemstack"] = (IAttribute)new ItemstackAttribute(stack.Clone());
                    if (agent != null)
                        evt["byentityid"] = (IAttribute)new LongAttribute(agent.EntityId);
                    world.Api.Event.PushEvent("onitemcollected", evt);
                }
                else
                {
                    world.SpawnItemEntity(stack, blockSel.Position);
                    debugLog?.Invoke($"[pickbush] bot inventory full, dropped {stack.StackSize}x {stack.Collectible.Code}");
                }
            }
        }

        // Advance the bush exactly like vanilla setGrowthState(Mature):
        // state first (the setter also flags the mesh dirty), then the
        // transition timer computed from the NEW state.
        bush.BState.Growthstate = EnumFruitingBushGrowthState.Mature;
        bush.BState.TransitionHoursLeft = bush.GetHoursForNextStage();
        bush.Blockentity.MarkDirty(true, player);

        var sound = block.GetBehavior<BlockBehaviorFruitingBush>()?.HarvestingSound;
        if (sound != null)
            world.PlaySoundAt(sound, blockSel.Position, 0.0f, player, true, 32f, 1f);

        done = true;
        debugLog?.Invoke($"[pickbush] picked {total}x berries, {block.Code} now Mature (regrowing)");
        Report(true, $"picked {total}x berries");
        Finish();
    }

    public override void Cancel()
    {
        // An interrupted pick leaves the berries on the bush — it stays
        // Ripe and can be picked later.
        if (!done)
        {
            debugLog?.Invoke("[pickbush] cancelled (bush stays ripe)");
            Report(false, "cancelled");
        }
        done = true;
        base.Cancel();
    }

    public override bool IsFinished() => done;

    public override IEntityAction Clone()
    {
        return new PolisPickBushAction(targetPos, player, maxRange, debugLog, onResult);
    }

    void Fail(string msg)
    {
        debugLog?.Invoke($"[pickbush] failed: {msg}");
        ExecutionHasFailed = true;
        Report(false, msg);
        done = true;
        Finish();
    }

    void Report(bool ok, string msg)
    {
        if (resultSent) return;
        resultSent = true;
        onResult?.Invoke(ok, msg);
    }
}
