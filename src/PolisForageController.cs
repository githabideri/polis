using System;
using System.Collections.Generic;
using System.Linq;
using Vintagestory.API.Common;
using Vintagestory.API.Common.Entities;
using Vintagestory.API.MathTools;
using Vintagestory.API.Server;
using Vintagestory.Essentials;
using Vintagestory.GameContent;
using Polis.Actions.Blocks;
using Polis.Actions.Harvesting;
using Polis.Actions.Inventory;
using Polis.Actions.Navigation;
using Polis.Core;

// ---------------------------------------------------------------------
// The food-pressure interrupt + the forage/feed skills (mod side).
//
// Design: docs/design/food-hunger-skills-policies.md (section A).
//
// The engine already implements the hunger drain (the 1.22
// EntityBehaviorHunger, driven by the item's SaturationLossDelay) and
// the satiety effect of food (ReceiveSaturation). What the polis adds
// on top:
//
//   1. THE INTERRUPT — a 1 Hz per-bot check of the synced saturation
//      tree. Below `trigger * maxsaturation` (a policy value, data not
//      code) the bot's current job is preempted at a SAFE POINT and a
//      forage episode starts. Preemption policy (the policy file's
//      `preempt` section): navigation-type jobs are cancelled
//      immediately (a stopped walk has no side effects), side-effect
//      jobs (waitTypes: harvest/mine) are only preempted at their
//      finish. The preempted action is recorded as a FAILURE with the
//      reason "preempted:food_pressure" — the mission layer (r2) sees
//      that in LastAction and re-runs the job; while the episode runs,
//      new job actions for that bot are refused ("refused:foraging"),
//      so the retry simply waits out the meal.
//
//   2. THE FORAGE SKILL — a per-bot state machine (one episode at a
//      time per bot):
//         scanning  -> expand square rings from the bot's position and
//                      query blocks for a wild fruiting bush (the
//                      pattern list is policy data; chunked across
//                      ticks, no hitch)
//         goto      -> walk to a walkable neighbour of the bush
//         harvest   -> PolisHarvestBlockAction (autoCollectDrops: the
//                      fruit lands in the bot's cargo)
//         eat       -> PolisEatAction on the harvested fruit (the
//                      policy gate applies here: the bot only eats
//                      what the interaction-rules layer allows)
//      After each eat the episode re-checks saturation: above `rearm *
//      max` it is a success (hysteresis prevents on/off oscillation);
//      otherwise it takes the next target (up to `maxTargets`).
//      Everything is reported on the /polis/events stream and in the
//      bot's LastAction ("forage"/"feed"), so an observer sees the
//      whole survival loop without any special plumbing.
//
//   3. THE FEED SKILL — the same machine with a known storage
//      container (a storage vessel) instead of the discovery scan:
//      pick a policy-allowed, edible stack from the container, walk to
//      it, take it, eat it. Harness command `feed`.
//
// All thresholds/radii/patterns come from the per-player policy
// profile (PolisPolicyEngine) — the code has no food knowledge of its
// own.
// ---------------------------------------------------------------------

public partial class PolisSystem
{
    // ----- forage episode state (per bot, one at a time) -----

    internal class ForageScan
    {
        public int Ring;                    // outer shell radius of the current ring
        public List<BlockPos> ShellCells = new();   // (x, z) cells of the current shell
        public int Cursor;
        public List<BlockPos> RingCandidates = new();
    }

    internal class ForageEpisode
    {
        public long BotId;
        public string OwnerUid;
        public string Source = "wild";       // "wild" (forage) | "container" (feed)
        public string Phase = "scanning";    // scanning|pickslot|goto|harvest|eat
        public ForageScan Scan = new ForageScan();
        public ForageParams Params;
        public float Trigger;
        public float Rearm;
        public int Attempt = 1;
        public int MaxTargets;
        public int MaxRadius;
        public int RingWidth;
        public BlockPos Target;
        public Vec3d GotoCell;
        public string TargetCode;
        public string FruitCode;
        public int ContainerSlot = -1;
        public int TakeQty = 1;
        public int? FeedCount;   // explicit user-requested quantity (feed command)
        public Dictionary<string, int> InvBefore = new();
        public long StartedMs;
        public long PhaseStartMs;
        public HashSet<long> UsedTargets = new();   // packed x/z keys
        public bool Done;
        public string Outcome;
        public string Detail;

        static public long CellKey(BlockPos p) => ((long)p.X << 32) ^ (uint)p.Z;
    }

    internal readonly Dictionary<long, ForageEpisode> forageEpisodes = new();
    bool forageBypassGuard;                 // set while the controller starts its own actions
    float forageTriggerAccum;
    readonly Dictionary<long, long> forageNextRetryMs = new();

    static long NowMs() => DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();

    internal bool IsForaging(long botId) => forageEpisodes.ContainsKey(botId);

    void LogForage(string msg) => sapi?.Logger?.Debug($"[forage] {msg}");

    void ForageQueueEvent(string type, object data)
    {
        try { testHarness?.Broadcaster?.QueueEvent(new PolisEvent(type, PolisLogLevel.Info, data)); }
        catch (Exception ex) { LogForage($"event queue failed: {ex.Message}"); }
    }

    // ----- called from PolisSystem.OnTick (game thread) -----

    void ForageOnTick(float dt)
    {
        var toRemove = new List<long>();
        foreach (var kv in forageEpisodes)
        {
            var id = kv.Key;
            var ep = kv.Value;
            if (!bots.TryGetValue(id, out var bot) || bot?.Entity == null || !bot.Entity.Alive)
            {
                toRemove.Add(id);
                continue;
            }
            StepEpisode(bot, ep);
            if (ep.Done) toRemove.Add(id);
        }
        for (int i = 0; i < toRemove.Count; i++)
        {
            forageEpisodes.Remove(toRemove[i]);
            forageNextRetryMs.Remove(toRemove[i]);
        }

        forageTriggerAccum += dt;
        if (forageTriggerAccum >= 1f)
        {
            forageTriggerAccum = 0f;
            CheckTriggers();
        }
    }

    void CheckTriggers()
    {
        foreach (var kv in bots)
        {
            var bot = kv.Value;
            if (bot?.Entity == null || !bot.Entity.Alive) continue;
            if (bot.Entity is not EntityPolisBot pb) continue;

            // Parked bots (HungerSuspended) are not draining — the
            // pressure question does not apply to them.
            if (pb.HungerSuspended) continue;
            if (forageEpisodes.ContainsKey(bot.Entity.EntityId)) continue;

            float max = PolisEatService.MaxSaturationOf(bot.Entity);
            if (max <= 0f) continue;
            float sat = PolisEatService.SaturationOf(bot.Entity);

            if (!globalData.Bots.TryGetValue(bot.Entity.EntityId, out var rec)) continue;
            string player = rec.OwnerUid;
            var (trigger, rearm) = PolisPolicyEngine.Instance.GetFoodPressure(player);

            long now = NowMs();
            if (forageNextRetryMs.TryGetValue(bot.Entity.EntityId, out var nr) && now < nr) continue;

            if (sat < trigger * max)
            {
                StartForageEpisode(bot, "wild", player, trigger, rearm, "interrupt");
            }
        }
    }

    // ----- episode entry -----

    /// <summary>
    /// Manual entry point (harness `forage` / `feed` commands) —
    /// bypasses the saturation check, same machine.
    /// </summary>
    internal bool StartForageEpisode(BotState bot, string source, string player,
        float trigger, float rearm, string cause, BlockPos containerPos = null,
        string feedItemCode = null)
    {
        if (bot?.Entity == null || !bot.Entity.Alive) return false;
        if (forageEpisodes.ContainsKey(bot.Entity.EntityId))
            return false;

        var forage = PolisPolicyEngine.Instance.GetForageConfig(player);
        var ep = new ForageEpisode
        {
            BotId = bot.Entity.EntityId,
            OwnerUid = player,
            Source = source,
            Params = forage,
            Trigger = trigger,
            Rearm = rearm,
            MaxTargets = forage.maxTargets > 0 ? forage.maxTargets : 3,
            MaxRadius = forage.maxRadius > 0 ? forage.maxRadius : 192,
            RingWidth = forage.ringWidth > 0 ? forage.ringWidth : 32,
            StartedMs = NowMs(),
        };

        if (source == "container")
        {
            if (containerPos == null) return false;
            ep.Target = containerPos;
            ep.Phase = "pickslot";
            if (feedItemCode != null) ep.FruitCode = feedItemCode;
        }
        else
        {
            var sp = bot.Entity.ServerPos.XYZ;
            ep.Scan.Ring = ep.RingWidth;
            if (!BuildShell(ep))
            {
                CompleteEpisode(bot, ep, false, $"no scan ring (maxRadius={ep.MaxRadius})");
                return false;
            }
            ep.Phase = "scanning";
            LogForage($"bot#{bot.Entity.EntityId}: forage scan start around ({sp.X:F0},{sp.Z:F0}) rings={ep.RingWidth}..{ep.MaxRadius}");
        }

        forageEpisodes[bot.Entity.EntityId] = ep;
        LogForage($"bot#{bot.Entity.EntityId}: episode start ({cause}, source={source}, sat={PolisEatService.SaturationOf(bot.Entity):F0}/{PolisEatService.MaxSaturationOf(bot.Entity):F0})");
        ForageQueueEvent("forage_started", new
        {
            bot = bot.Entity.EntityId,
            cause,
            source = ep.Source,
            sat = Math.Round(PolisEatService.SaturationOf(bot.Entity), 1),
            max = Math.Round(PolisEatService.MaxSaturationOf(bot.Entity), 1),
            trigger,
            rearm,
            maxTargets = ep.MaxTargets,
        });

        // Preempt the current job (if any) at the policy's safe point.
        PreemptCurrentJob(bot, ep);
        BeginPhase(bot, ep);
        return true;
    }

    void PreemptCurrentJob(BotState bot, ForageEpisode ep)
    {
        if (!bot.JobRunning) return;

        var preempt = PolisPolicyEngine.Instance.GetPreemptConfig(ep.OwnerUid);
        string curType = bot.LastActionType ?? "";

        bool wait = preempt.mode == "finish"
            || (preempt.mode != "immediate" && preempt.waitTypes != null && preempt.waitTypes.Contains(curType));

        if (wait)
        {
            // Safe point: the side-effect job runs to its finish; the
            // episode starts when JobRunning clears (BeginEpisodeWhenIdle).
            foragePendingStart[bot.Entity.EntityId] = (ep, "finish");
            LogForage($"bot#{bot.Entity.EntityId}: forage deferred — job {curType} runs to its safe point");
            return;
        }

        string jobName = bot.LastActionName ?? "job";
        bot.Activity.CancelAll();
        // The action's own cancel callback may have recorded a plain
        // "cancelled" — overwrite it with the real reason so the
        // mission layer (r2) can retry the job on this signature.
        bot.RecordActionResult(jobName, false, "preempted:food_pressure");
        bot.JobRunning = false;
        LogForage($"bot#{bot.Entity.EntityId}: preempted job '{jobName}' ({curType}) for food pressure");
    }

    // deferred (safe-point) starts: botId -> (episode, reason)
    readonly Dictionary<long, (ForageEpisode, string)> foragePendingStart = new();

    void BeginEpisodeWhenIdle(BotState bot, string reason)
    {
        if (!foragePendingStart.TryGetValue(bot.Entity.EntityId, out var ps) || ps.Item1 == null) return;
        if (bot.JobRunning || forageEpisodes.ContainsKey(bot.Entity.EntityId)) return;
        foragePendingStart.Remove(bot.Entity.EntityId);
        var ep = ps.Item1;
        // saturation may have recovered while the job ran out
        float max = PolisEatService.MaxSaturationOf(bot.Entity);
        float sat = PolisEatService.SaturationOf(bot.Entity);
        if (reason == "finish" && max > 0f && sat >= ep.Trigger * max)
        {
            LogForage($"bot#{bot.Entity.EntityId}: forage cancelled — saturation recovered to {sat:F0} while the job finished");
            return;
        }
        LogForage($"bot#{bot.Entity.EntityId}: forage starting at safe point ({reason})");
        BeginPhase(bot, ep);
    }

    // ----- phase machine -----

    void StepEpisode(BotState bot, ForageEpisode ep)
    {
        // Watchdog: a phase stuck for 4 minutes (lost callback, path
        // wedge that never reports) ends the episode honestly.
        if (ep.PhaseStartMs > 0 && NowMs() - ep.PhaseStartMs > 240_000)
        {
            CompleteEpisode(bot, ep, false, $"phase '{ep.Phase}' stuck ({(NowMs() - ep.PhaseStartMs) / 1000}s)");
            return;
        }

        if (ep.Phase == "scanning")
            StepScan(bot, ep);
        // goto/harvest/eat phases are driven by their action callbacks
        // (BeginPhase started the action); nothing to poll here.
    }

    void StepScan(BotState bot, ForageEpisode ep)
    {
        var ba = sapi.World.BlockAccessor;
        int budget = Math.Max(64, ep.Params.blocksPerTick);
        int patterns = ep.Params.blockPatterns == null || ep.Params.blockPatterns.Count == 0 ? 0 : ep.Params.blockPatterns.Count;

        while (budget > 0)
        {
            if (ep.Cursor >= ep.Scan.ShellCells.Count)
            {
                // Ring done: keep the nearest candidate (not yet used),
                // else move to the next ring.
                if (ep.Scan.RingCandidates.Count > 0)
                {
                    var center = bot.Entity.ServerPos.XYZ.AsBlockPos;
                    var best = ep.Scan.RingCandidates
                        .Where(c => !ep.UsedTargets.Contains(ForageEpisode.CellKey(c)))
                        .OrderBy(c => Math.Max(Math.Abs(c.X - center.X), Math.Abs(c.Z - center.Z)))
                        .FirstOrDefault();
                    if (best != null)
                    {
                        var b = ba.GetBlock(best);
                        if (b != null && b.Id != 0 && MatchesPatterns(b.Code?.ToString(), ep.Params.blockPatterns))
                        {
                            StartTarget(bot, ep, best, b.Code.ToString());
                            return;
                        }
                    }
                    // ring had only used/stale candidates — next ring
                }
                ep.Scan.RingCandidates.Clear();
                int nextRing = ep.Scan.Ring + ep.RingWidth;
                if (nextRing > ep.MaxRadius)
                {
                    CompleteEpisode(bot, ep, false,
                        $"no forageable block within {ep.MaxRadius} blocks (patterns: {string.Join(", ", ep.Params.blockPatterns ?? new List<string>())})");
                    return;
                }
                ep.Scan.Ring = nextRing;
                ep.Scan.ShellCells.Clear();
                ep.Cursor = 0;
                if (!BuildShell(ep))
                {
                    CompleteEpisode(bot, ep, false, "scan ring exhausted");
                    return;
                }
                continue;
            }

            var cell = ep.Scan.ShellCells[ep.Scan.Cursor++];
            budget--;
            for (int y = 0; y <= 16; y++)
            {
                var b = ba.GetBlock(new BlockPos(cell.X, y, cell.Z));
                if (b == null || b.Id == 0) continue;
                if (MatchesPatterns(b.Code?.ToString(), ep.Params.blockPatterns))
                {
                    ep.Scan.RingCandidates.Add(new BlockPos(cell.X, y, cell.Z));
                    break;   // one candidate per column is enough
                }
            }
        }
    }

    static bool MatchesPatterns(string code, List<string> patterns)
    {
        if (code == null || patterns == null) return false;
        foreach (var p in patterns)
            if (PolisPolicyEngine.WildcardMatchPublic(p, code)) return true;
        return false;
    }

    bool BuildShell(ForageEpisode ep)
    {
        var center = bots[ep.BotId].Entity.ServerPos.XYZ.AsBlockPos;
        int r = ep.Scan.Ring;
        var cells = new List<BlockPos>();
        // outer shell of the square: max(|dx|, |dz|) == r
        for (int dx = -r; dx <= r; dx++)
            for (int dz = -r; dz <= r; dz++)
                if (Math.Max(Math.Abs(dx), Math.Abs(dz)) == r)
                    cells.Add(new BlockPos(center.X + dx, 0, center.Z + dz));
        if (cells.Count == 0) return false;
        ep.Scan.ShellCells = cells;
        ep.Cursor = 0;
        return true;
    }

    // ----- one target: goto -> harvest/take -> eat -----

    void StartTarget(BotState bot, ForageEpisode ep, BlockPos target, string code)
    {
        ep.Target = target;
        ep.TargetCode = code;
        ep.UsedTargets.Add(ForageEpisode.CellKey(target));

        // Walkable neighbour of the target cell (the bush/vessel itself
        // is not a standable cell). Deterministic order; flat pilot
        // world: the first non-solid neighbour works.
        var solid = sapi.World.BlockAccessor;
        Vec3d gotoCell = null;
        var nbs = new[]
        {
            new BlockPos(target.X + 1, target.Y, target.Z),
            new BlockPos(target.X - 1, target.Y, target.Z),
            new BlockPos(target.X, target.Y, target.Z + 1),
            new BlockPos(target.X, target.Y, target.Z - 1),
        };
        foreach (var nb in nbs)
        {
            var b = solid.GetBlock(nb);
            bool standable = b == null || b.Id == 0 || !b.IsSolid();
            if (standable)
            {
                gotoCell = new Vec3d(nb.X, nb.Y, nb.Z);
                break;
            }
        }
        if (gotoCell == null)
            gotoCell = new Vec3d(target.X + 1, target.Y, target.Z);

        ep.GotoCell = gotoCell;
        ep.Phase = "goto";
        ep.PhaseStartMs = NowMs();

        LogForage($"bot#{ep.BotId}: target {code} at ({target.X},{target.Y},{target.Z}), goto ({gotoCell.X:F0},{gotoCell.Z:F0}) attempt {ep.Attempt}/{ep.MaxTargets}");
        ForageQueueEvent("forage_target", new
        {
            bot = ep.BotId,
            attempt = ep.Attempt,
            code,
            pos = new[] { target.X, target.Y, target.Z },
        });

        StartForageAction(bot, "forage-goto",
            new PolisGotoAction(
                bot.Activity, gotoCell, true, "walk", 1f, 1f,
                LogForage, _ => { }, true, true,
                null, true, false,
                (ok, msg) => OnForageGotoResult(bot, ep, ok, msg)));
    }

    void OnForageGotoResult(BotState bot, ForageEpisode ep, bool ok, string msg)
    {
        // Stale callback: the episode was replaced/finished meanwhile.
        if (!ReferenceEquals(forageEpisodes.TryGetValue(ep.BotId, out var cur) ? cur : null, ep)) return;

        if (ok)
        {
            BeginHarvestOrTake(bot, ep);
        }
        else
        {
            LogForage($"bot#{ep.BotId}: forage-goto failed: {msg}");
            NextTargetOrComplete(bot, ep, $"goto failed: {msg}");
        }
    }

    void BeginHarvestOrTake(BotState bot, ForageEpisode ep)
    {
        if (ep.Source == "container")
        {
            BeginContainerTake(bot, ep);
            return;
        }

        var owner = sapi.World.PlayerByUid(ep.OwnerUid) as IServerPlayer;
        if (owner == null)
        {
            CompleteEpisode(bot, ep, false, "owner offline — cannot harvest (claims)");
            return;
        }

        // Snapshot the carried inventory: the harvest's drops are what
        // the cargo diff shows once the auto-collect ran.
        ep.InvBefore = SnapshotCarried(bot);

        ep.Phase = "harvest";
        ep.PhaseStartMs = NowMs();
        StartForageAction(bot, "forage-harvest",
            new PolisHarvestBlockAction(
                ep.Target, owner, 4.5f, true, 3f, true,
                LogForage,
                (ok, msg) => OnForageHarvestResult(bot, ep, ok, msg)));
    }

    void OnForageHarvestResult(BotState bot, ForageEpisode ep, bool ok, string msg)
    {
        if (!ReferenceEquals(forageEpisodes.TryGetValue(ep.BotId, out var cur) ? cur : null, ep)) return;

        if (!ok)
        {
            LogForage($"bot#{ep.BotId}: forage-harvest failed: {msg}");
            NextTargetOrComplete(bot, ep, $"harvest failed: {msg}");
            return;
        }

        var after = SnapshotCarried(bot);
        string fruit = null;
        int qty = 0;
        foreach (var kv in after)
        {
            int before = ep.InvBefore.TryGetValue(kv.Key, out var b2) ? b2 : 0;
            if (kv.Value > before)
            {
                fruit = kv.Key;
                qty = kv.Value - before;
            }
        }
        if (fruit == null)
        {
            LogForage($"bot#{ep.BotId}: harvest of {ep.TargetCode} produced no collectible drop");
            NextTargetOrComplete(bot, ep, $"harvest produced no drop ({ep.TargetCode})");
            return;
        }

        ep.FruitCode = fruit;
        LogForage($"bot#{ep.BotId}: harvested {qty}x {fruit}");
        ForageQueueEvent("forage_harvested", new { bot = ep.BotId, attempt = ep.Attempt, item = fruit, qty });

        BeginEat(bot, ep, fruit);
    }

    void BeginContainerTake(BotState bot, ForageEpisode ep)
    {
        var owner = sapi.World.PlayerByUid(ep.OwnerUid) as IServerPlayer;
        if (owner == null)
        {
            CompleteEpisode(bot, ep, false, "owner offline — cannot take from container");
            return;
        }

        var be = sapi.World.BlockAccessor.GetBlockEntity(ep.Target) as IBlockEntityContainer;
        if (be == null)
        {
            CompleteEpisode(bot, ep, false, $"no container at ({ep.Target.X},{ep.Target.Y},{ep.Target.Z})");
            return;
        }

        int slot = -1;
        int qty = 1;
        if (ep.ContainerSlot >= 0)
        {
            slot = ep.ContainerSlot;
        }
        else
        {
            // pick a policy-allowed edible stack
            for (int i = 0; i < be.Inventory.Count; i++)
            {
                var st = be.Inventory[i].Itemstack;
                if (st == null || st.StackSize <= 0 || st.Collectible == null) continue;
                string code = st.Collectible.Code.ToString();
                if (ep.FruitCode != null && code != ep.FruitCode) continue;
                var nut = st.Collectible.GetNutritionProperties(sapi.World, st, bot.Entity);
                if (nut == null) continue;
                if (!PolisPolicyEngine.Instance.Evaluate(ep.OwnerUid, "food", code, nut.FoodCategory.ToString()).Allow) continue;
                slot = i;
                qty = Math.Min(st.StackSize, 4);
                break;
            }
        }
        if (slot < 0 || slot >= be.Inventory.Count)
        {
            CompleteEpisode(bot, ep, false, "container holds no policy-allowed food");
            return;
        }

        ep.ContainerSlot = slot;
        var stack = be.Inventory[slot].Itemstack;
        ep.FruitCode = stack?.Collectible?.Code?.ToString();
        ep.TakeQty = Math.Min(ep.FeedCount > 0 ? ep.FeedCount.Value : qty, stack?.StackSize ?? 1);
        ep.Phase = "harvest";      // reuse the phase: "take" for containers
        ep.PhaseStartMs = NowMs();
        LogForage($"bot#{ep.BotId}: taking {ep.TakeQty}x {ep.FruitCode} from slot {slot}");

        StartForageAction(bot, "forage-take",
            new PolisContainerTakeAction(
                bot.Activity, ep.Target, slot, ep.TakeQty, owner, 4.5f,
                LogForage,
                (ok, msg) => OnForageTakeResult(bot, ep, ok, msg)));
    }

    void OnForageTakeResult(BotState bot, ForageEpisode ep, bool ok, string msg)
    {
        if (!ReferenceEquals(forageEpisodes.TryGetValue(ep.BotId, out var cur) ? cur : null, ep)) return;
        if (!ok)
        {
            CompleteEpisode(bot, ep, false, $"take failed: {msg}");
            return;
        }
        LogForage($"bot#{ep.BotId}: took {ep.TakeQty}x {ep.FruitCode}");
        ForageQueueEvent("forage_harvested", new { bot = ep.BotId, attempt = ep.Attempt, item = ep.FruitCode, qty = ep.TakeQty });
        BeginEat(bot, ep, ep.FruitCode);
    }

    void BeginEat(BotState bot, ForageEpisode ep, string code)
    {
        float before = PolisEatService.SaturationOf(bot.Entity);
        ep.Phase = "eat";
        ep.PhaseStartMs = NowMs();
        StartForageAction(bot, "forage-eat",
            new PolisEatAction(
                bot.Activity, code, 0, ep.OwnerUid,
                LogForage,
                (ok, msg) => OnForageEatResult(bot, ep, ok, msg, before)));
    }

    void OnForageEatResult(BotState bot, ForageEpisode ep, bool ok, string msg, float satBefore)
    {
        if (!ReferenceEquals(forageEpisodes.TryGetValue(ep.BotId, out var cur) ? cur : null, ep)) return;

        float after = PolisEatService.SaturationOf(bot.Entity);
        float max = PolisEatService.MaxSaturationOf(bot.Entity);
        string eatOutcome = ok ? "ok" : "fail";
        LogForage($"bot#{ep.BotId}: forage-eat {eatOutcome} ({msg}) sat {satBefore:F0} -> {after:F0}");
        ForageQueueEvent("forage_eat", new
        {
            bot = ep.BotId,
            attempt = ep.Attempt,
            item = ep.FruitCode,
            ok,
            before = Math.Round(satBefore, 1),
            after = Math.Round(after, 1),
        });

        if (!ok)
        {
            NextTargetOrComplete(bot, ep, $"eat failed: {msg}");
            return;
        }

        if (max > 0f && after > ep.Rearm * max)
        {
            CompleteEpisode(bot, ep, true,
                $"satiated: {satBefore:F0} -> {after:F0} (>{ep.Rearm * max:F0} rearm) after {ep.Attempt} target(s) in {(NowMs() - ep.StartedMs) / 1000}s");
            return;
        }

        NextTargetOrComplete(bot, ep, null);
    }

    void NextTargetOrComplete(BotState bot, ForageEpisode ep, string failReason)
    {
        if (failReason != null)
        {
            LogForage($"bot#{ep.BotId}: target attempt {ep.Attempt} failed: {failReason}");
        }
        if (ep.Attempt >= ep.MaxTargets)
        {
            float sat = PolisEatService.SaturationOf(bot.Entity);
            float max = PolisEatService.MaxSaturationOf(bot.Entity);
            bool partial = max > 0f && sat > ep.Trigger * max;
            CompleteEpisode(bot, ep, false,
                partial
                    ? $"partially fed ({sat:F0}/{max:F0}) but not over rearm after {ep.Attempt} targets — retrying later"
                    : $"unfed after {ep.Attempt} targets ({failReason ?? "no targets"}) — retrying later");
            return;
        }

        ep.Attempt++;
        if (ep.Source == "container")
        {
            // a container holds what it holds — no retry loop
            CompleteEpisode(bot, ep, false, failReason ?? "container feed did not satiate");
            return;
        }
        ep.Phase = "scanning";
        ep.PhaseStartMs = NowMs();
        ep.Scan.Ring = ep.RingWidth;
        ep.Scan.RingCandidates.Clear();
        if (!BuildShell(ep))
            CompleteEpisode(bot, ep, false, "scan ring exhausted");
    }

    void CompleteEpisode(BotState bot, ForageEpisode ep, bool ok, string detail)
    {
        ep.Done = true;
        ep.Outcome = ok ? "success" : "fail";
        ep.Detail = detail;
        forageEpisodes.Remove(ep.BotId);
        foragePendingStart.Remove(ep.BotId);
        forageNextRetryMs[ep.BotId] = ok ? 0 : NowMs() + 90_000;   // backoff on failure
        bot.JobRunning = false;
        bot.RecordActionResult(ep.Source == "container" ? "feed" : "forage", ok, detail, sapi.World.ElapsedMilliseconds);
        string episodeOutcome = ok ? "SUCCESS" : "FAILED";
        LogForage($"bot#{ep.BotId}: episode {episodeOutcome}: {detail} (sat now {PolisEatService.SaturationOf(bot.Entity):F0})");
        ForageQueueEvent("forage_episode", new
        {
            bot = ep.BotId,
            outcome = ep.Outcome,
            detail,
            attempt = ep.Attempt,
            source = ep.Source,
            sat = Math.Round(PolisEatService.SaturationOf(bot.Entity), 1),
            durationMs = NowMs() - ep.StartedMs,
        });
    }

    // ----- action plumbing -----

    /// <summary>
    /// Start one of the controller's own actions, bypassing the
    /// foraging refusal guard in StartSingleAction.
    /// </summary>
    void StartForageAction(BotState bot, string name, IEntityAction action)
    {
        forageBypassGuard = true;
        try { StartSingleAction(bot, name, action); }
        finally { forageBypassGuard = false; }
    }

    static Dictionary<string, int> SnapshotCarried(BotState bot)
    {
        var inv = new Dictionary<string, int>();
        var cargo = PolisInventoryHelpers.BotCargo(bot.Entity);
        void Add(ItemStack st)
        {
            if (st == null || st.StackSize <= 0 || st.Collectible == null) return;
            string c = st.Collectible.Code.ToString();
            inv[c] = (inv.TryGetValue(c, out var n) ? n : 0) + st.StackSize;
        }
        if (cargo != null)
            for (int i = 0; i < cargo.Count; i++) Add(cargo[i].Itemstack);
        Add(bot.Entity.RightHandItemSlot?.Itemstack);
        Add(bot.Entity.LeftHandItemSlot?.Itemstack);
        return inv;
    }
}
