using System;
using Vintagestory.API.Common;
using Vintagestory.API.Common.Entities;
using Vintagestory.API.MathTools;
using Vintagestory.GameContent;
using Polis.Helpers;

namespace Polis.Core
{
    /// <summary>
    /// The shared "consume food" core: the one place where a bot eats.
    /// Both the harness `eat` command and the engine action (PolisEatAction,
    /// used by the forage and feed skills) call this, so the policy gate,
    /// the engine nutrition path and the bookkeeping can never diverge.
    ///
    /// The flow (design: docs/design/food-hunger-skills-policies.md):
    ///   1. resolve the item and its engine nutrition (1.22 seam:
    ///      GetNutritionProperties(world, stack, entity));
    ///   2. policy gate — the interaction-rules layer decides whether THIS
    ///      player may consume this food, before anything is consumed
    ///      (denials are rejection data: the reason is returned, callers
    ///      log/report it);
    ///   3. consume from the bot's cargo + hands (the service never gives
    ///      items — that is a harness privilege);
    ///   4. per unit: ReceiveSaturation (the engine's satiety path with
    ///      the item's SaturationLossDelay), the health delta as a
    ///      negative hunger damage, the 1.22 intoxication/psychedelic
    ///      floats, and the EatenStack leftover (e.g. a bone).
    ///
    /// count == 0 means "all carried units of this item".
    /// </summary>
    public static class PolisEatService
    {
        public static (bool Ok, string Reason, float Before, float After, int Units) Eat(
            EntityAgent agent, string player, string code, int count,
            Action<string> log = null)
        {
            if (agent == null) return (false, "agent is null", 0f, 0f, 0);
            if (code == null) return (false, "no item code", 0f, 0f, 0);

            var world = agent.World;
            var item = world.GetItem(new AssetLocation(code));
            if (item == null) return (false, $"item '{code}' not found", 0f, 0f, 0);

            var unit = new ItemStack(item, 1);
            var nut = item.GetNutritionProperties(world, unit, agent) ?? item.NutritionProps;
            if (nut == null)
                return (false, $"{code} is not edible (no nutrition properties)", 0f, 0f, 0);

            var (allowed, reason) = PolisPolicyEngine.Instance.Evaluate(player, "food", code, nut.FoodCategory.ToString());
            if (!allowed)
                return (false, $"policy denied: {reason}", 0f, 0f, 0);

            int have = PolisInventoryHelpers.CountBotItems(agent, code);
            int toEat = count == 0 ? have : count;
            if (toEat <= 0) return (false, $"bot carries no {code}", 0f, 0f, 0);
            if (have < toEat) return (false, $"bot carries {have}x {code} (< {toEat})", 0f, 0f, 0);

            float before = SaturationOf(agent);
            int eaten = 0;
            for (int i = 0; i < toEat; i++)
            {
                if (!PolisInventoryHelpers.ConsumeOneFromBotInventory(agent, code))
                    return (false, $"consume failed partway (ate {eaten}/{toEat})", before, SaturationOf(agent), eaten);

                // The engine's satiety path: ReceiveSaturation with the
                // item's own SaturationLossDelay — the 1.22 way, not the
                // deprecated AddSaturation.
                agent.ReceiveSaturation(nut.Satiety, nut.FoodCategory, nut.SaturationLossDelay, 1f);

                if (Math.Abs(nut.Health) > 1e-4f)
                {
                    agent.ReceiveDamage(new DamageSource
                    {
                        Type = EnumDamageType.Hunger,
                        Source = EnumDamageSource.Internal,
                    }, -nut.Health);
                }

                if (Math.Abs(nut.Intoxication) > 1e-4f)
                {
                    float cur = agent.WatchedAttributes.GetFloat("intoxication", 0f);
                    agent.WatchedAttributes.SetFloat("intoxication", Math.Min(1.1f, cur + nut.Intoxication));
                }
                if (Math.Abs(nut.Psychedelic) > 1e-4f)
                {
                    float cur2 = agent.WatchedAttributes.GetFloat("psychedelic", 0f);
                    agent.WatchedAttributes.SetFloat("psychedelic", Math.Min(2f, cur2 + nut.Psychedelic));
                }

                if (nut.EatenStack != null && nut.EatenStack.Code != null && nut.EatenStack.StackSize > 0)
                {
                    var leftover = world.GetItem(nut.EatenStack.Code);
                    if (leftover != null)
                        PolisInventoryHelpers.TryInsertIntoBotInventory(agent, new ItemStack(leftover, nut.EatenStack.StackSize), out _, out _);
                }

                eaten++;
            }

            float after = SaturationOf(agent);
            log?.Invoke($"[eat] {agent.EntityId}: {eaten}x {code} ({nut.FoodCategory}) {before:F1} -> {after:F1} saturation");
            return (true, $"ate {eaten}x {code}: {before:F1} -> {after:F1} saturation", before, after, eaten);
        }

        public static float SaturationOf(EntityAgent agent)
            => agent?.WatchedAttributes?.GetTreeAttribute("hunger")?.GetFloat("currentsaturation", 0f) ?? 0f;

        public static float MaxSaturationOf(EntityAgent agent)
            => agent?.WatchedAttributes?.GetTreeAttribute("hunger")?.GetFloat("maxsaturation", 1500f) ?? 1500f;
    }
}
