using System;
using Vintagestory.API.Common;
using Vintagestory.API.Common.Entities;
using Vintagestory.Essentials;
using Vintagestory.GameContent;

namespace Polis.Actions.Inventory
{
    /// <summary>
    /// Action: the bot eats. One action = the shared eat core
    /// (PolisEatService): policy gate (per player), cargo/hand consume,
    /// the engine's ReceiveSaturation path, bookkeeping. It exists so the
    /// forage and feed skills can compose "goto + take/harvest + eat" as
    /// real engine actions — the forage state machine (PolisForageController)
    /// drives one instance per phase.
    ///
    /// count == 0 → eat all carried units of the item (the forage case:
    /// whatever the harvest produced).
    /// </summary>
    public class PolisEatAction : EntityActionBase
    {
        private readonly EntityActivitySystem vas;
        private readonly string itemCode;
        private readonly int count;
        private readonly string player;
        private readonly Action<string> debugLog;
        private readonly Action<bool, string> onResult;
        private bool done;
        private bool resultSent;

        public override string Type => "polis-eat";

        public PolisEatAction(
            EntityActivitySystem vas,
            string itemCode,
            int count,
            string player,
            Action<string> debugLog = null,
            Action<bool, string> onResult = null)
        {
            this.vas = vas;
            this.itemCode = itemCode;
            this.count = count;
            this.player = player;
            this.debugLog = debugLog;
            this.onResult = onResult;
        }

        public override void Start(EntityActivity activity)
        {
            var agent = vas?.Entity as EntityAgent;
            if (agent == null)
            {
                ReportResult(false, "actor is not an agent");
                return;
            }

            // One-tick action: the engine's satiety path is
            // instantaneous, so the whole meal happens in Start and the
            // action reports on the next tick.
            var (ok, reason, before, after, units) = PolisEatService.Eat(
                agent, player, itemCode, count, debugLog);

            if (ok)
            {
                debugLog?.Invoke($"[eat-action] {agent.EntityId}: {reason}");
                ReportResult(true, $"{reason} (sat {before:F0} -> {after:F0}, {units} unit(s))");
            }
            else
            {
                ReportResult(false, reason);
            }
            done = true;
        }

        public override void OnTick(float dt)
        {
        }

        public override void Cancel()
        {
            if (!resultSent) ReportResult(false, "cancelled");
            Finish();
        }

        public override void Finish()
        {
        }

        public override bool IsFinished()
        {
            return done || ExecutionHasFailed;
        }

        public override IEntityAction Clone()
        {
            return new PolisEatAction(vas, itemCode, count, player, debugLog, onResult);
        }

        void ReportResult(bool ok, string msg)
        {
            if (resultSent) return;
            resultSent = true;
            onResult?.Invoke(ok, msg);
        }
    }
}
