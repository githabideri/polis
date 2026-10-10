using System;
using System.Linq;
using Vintagestory.API.Common;
using Vintagestory.API.Common.Entities;
using Vintagestory.API.MathTools;
using Vintagestory.GameContent;

/// <summary>
/// Firepit interaction as BOT actions (2026-10-10, from the firepit
/// investigation - the 1.22 firepit GUI has NO buttons at all, the
/// only packet is close: slot writes are the whole interaction
/// surface, so these are the endogenous equivalents of the player
/// clicking slots):
///
///   firepit-fuel &lt;x&gt; &lt;y&gt; &lt;z&gt; [itemCode] [count]
///       firepit-put targeting the fuel slot (slot 0). No ignition
///       state is touched: an ARMED firepit (canIgniteFuel - the state
///       that survives lit -&gt; fuel-out -&gt; extinct for up to 2
///       hours) auto-ignites on the engine's next burn tick (~100 ms)
///       purely from this fuel write. A FRESH firepit (canIgniteFuel
///       false - it is false at spawn; FromTreeAttributes is not run
///       on fresh spawns; only the firestarter resets it) stays unlit
///       until firepit-light.
///
///   firepit-put &lt;x&gt; &lt;y&gt; &lt;z&gt; &lt;slot&gt; [itemCode] [n]
///       Take the item out of the selected bot's cargo into the
///       firepit's slot (0 fuel, 1 input, 2 output, 3-6 cooking).
///       The 1.22 firepit cooks the input slot through the item's own
///       DoSmelt while burning - no pot needed for single-ingredient
///       food.
///
///   firepit-light &lt;x&gt; &lt;y&gt; &lt;z&gt;
///       Deterministic firestarter equivalent: mirrors
///       BlockFirepit.OnTryIgniteBlockOver (the engine's own
///       firestarter completion path) - sets canIgniteFuel = true and
///       resets the 2 h cold timer. The engine's real firestarter has
///       a 25 % per-completion success roll on the ITEM side and 20
///       durability; this action skips the roll (it is the item's,
///       not the block's). Claims-checked against the context player
///       (flag 2), like the firestarter's.
///
/// The old `crucible-fuel` no longer re-arms (the unconditional
/// canIgniteFuel flip was removed 2026-10-10: arming is the
/// firestarter's job, not fueling's).
/// </summary>
public partial class PolisSystem
{
    PolisTestHarness.CommandResult _FirepitPut(BotState bot, PolisTestHarness.CommandContext context, string[] args, int slot, string cmdName)
    {
        if (!double.TryParse(args[0], out var fx) || !double.TryParse(args[1], out var fy) || !double.TryParse(args[2], out var fz))
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Invalid coordinates" };
        var pos = new Vec3d(fx, fy, fz).AsBlockPos;

        string itemCode = (args.Length > 3 && !string.IsNullOrEmpty(args[3])) ? args[3] : "";
        int count = 1;
        if (slot == 0 && string.IsNullOrEmpty(itemCode)) itemCode = "charcoal";
        if (string.IsNullOrEmpty(itemCode))
            return new PolisTestHarness.CommandResult { Ok = false, Message = "itemCode required (slot " + slot + ")" };
        if (args.Length > (slot == 0 ? 4 : 4) && int.TryParse(args[4], out var c))
            count = Math.Max(1, Math.Min(64, c));
        if (!itemCode.StartsWith("game:")) itemCode = "game:" + itemCode;

        if (!CrucibleInRange(bot, pos, out _, out var rangeErr))
            return new PolisTestHarness.CommandResult { Ok = false, Message = rangeErr };

        var firepit = sapi.World.BlockAccessor.GetBlockEntity(pos) as BlockEntityFirepit;
        if (firepit == null)
            return new PolisTestHarness.CommandResult { Ok = false, Message = "no firepit BE at " + pos + " (block: " + sapi.World.BlockAccessor.GetBlock(pos).Code + ")" };

        var slotRef = firepit.Inventory[slot];
        var agent = bot.Entity as EntityAgent;
        if (slotRef == null || slotRef.Empty)
        {
            var src = FindItemInCargoDirect(agent, itemCode);
            if (src == null)
                return new PolisTestHarness.CommandResult { Ok = false, Message = "bot " + bot.Entity.EntityId + " carries no '" + itemCode + "'" };
            var taken = src.TakeOut(Math.Min(count, src.Itemstack.StackSize));
            if (taken == null || taken.StackSize <= 0)
                return new PolisTestHarness.CommandResult { Ok = false, Message = "could not take " + itemCode + " out of the bot's cargo" };
            slotRef.Itemstack = taken;
            slotRef.MarkDirty();
        }
        else if (CodeMatchesLenient(slotRef.Itemstack.Collectible?.Code?.ToString(), itemCode))
        {
            var src2 = FindItemInCargoDirect(agent, itemCode);
            if (src2 == null)
                return new PolisTestHarness.CommandResult { Ok = false, Message = "slot " + slot + " holds " + itemCode + " but the bot carries none more" };
            MoveStackToSlot(src2, slotRef, count);
        }
        else
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "slot " + slot + " holds " + slotRef.Itemstack.Collectible?.Code + "; clear it first" };
        }

        var owner = ResolveCommandOwner(bot, context);
        firepit.MarkDirty(true, owner);
        bot.RecordActionResult(cmdName, true, "+" + count + "x " + itemCode + " to firepit " + pos + " slot " + slot, sapi.World.ElapsedMilliseconds);
        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = itemCode + " x" + slotRef.Itemstack.StackSize + " in firepit " + pos + " slot " + slot + "; burning=" + firepit.IsBurning + " armed=" + firepit.canIgniteFuel,
            Data = new
            {
                pos = new { x = pos.X, y = pos.Y, z = pos.Z },
                slot,
                code = slotRef.Itemstack?.Collectible?.Code?.ToString(),
                qty = slotRef.Itemstack?.StackSize,
                burning = firepit.IsBurning,
                canIgniteFuel = firepit.canIgniteFuel,
                bot = bot.Entity.EntityId
            }
        };
    }

    PolisTestHarness.CommandResult ExecuteFirepitFuelCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        if (args.Length < 3)
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Usage: firepit-fuel <x> <y> <z> [itemCode] [count]" };
        if (!TryGetHarnessBot(context, out var bot, out var err))
            return new PolisTestHarness.CommandResult { Ok = false, Message = err };
        return _FirepitPut(bot, context, args, 0, "firepit-fuel");
    }

    PolisTestHarness.CommandResult ExecuteFirepitPutCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        if (args.Length < 4)
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Usage: firepit-put <x> <y> <z> <slot> [itemCode] [n]" };
        int slot;
        if (!int.TryParse(args[3], out slot) || slot < 0 || slot > 6)
            return new PolisTestHarness.CommandResult { Ok = false, Message = "slot must be 0..6 (0 fuel, 1 input, 2 output, 3-6 cooking)" };
        if (!TryGetHarnessBot(context, out var bot, out var err))
            return new PolisTestHarness.CommandResult { Ok = false, Message = err };
        return _FirepitPut(bot, context, args, slot, "firepit-put");
    }

    PolisTestHarness.CommandResult ExecuteFirepitLightCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        if (args.Length < 3)
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Usage: firepit-light <x> <y> <z>" };
        if (!TryGetHarnessBot(context, out var bot, out var err))
            return new PolisTestHarness.CommandResult { Ok = false, Message = err };
        if (!double.TryParse(args[0], out var fx) || !double.TryParse(args[1], out var fy) || !double.TryParse(args[2], out var fz))
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Invalid coordinates" };
        var pos = new Vec3d(fx, fy, fz).AsBlockPos;

        if (!CrucibleInRange(bot, pos, out _, out var rangeErr))
            return new PolisTestHarness.CommandResult { Ok = false, Message = rangeErr };
        if (!TryGetContextPlayer(context, out var player, out var perr))
            return new PolisTestHarness.CommandResult { Ok = false, Message = perr };
        if (!sapi.World.Claims.TryAccess(player, pos, (EnumBlockAccessFlags)2))
            return new PolisTestHarness.CommandResult { Ok = false, Message = "claims: no ignition access at " + pos };

        var firepit = sapi.World.BlockAccessor.GetBlockEntity(pos) as BlockEntityFirepit;
        if (firepit == null)
            return new PolisTestHarness.CommandResult { Ok = false, Message = "no firepit BE at " + pos };
        if (firepit.IsBurning)
            return new PolisTestHarness.CommandResult { Ok = false, Message = "firepit is already burning" };
        if (firepit.canIgniteFuel)
            return new PolisTestHarness.CommandResult
            {
                Ok = true,
                Message = "firepit already armed (canIgniteFuel) - fueling will ignite it",
                Data = new { pos = new { x = pos.X, y = pos.Y, z = pos.Z }, canIgniteFuel = true }
            };

        // Mirror of BlockFirepit.OnTryIgniteBlockOver (the engine's own
        // firestarter completion): arm + reset the 2 h cold timer.
        firepit.canIgniteFuel = true;
        firepit.extinguishedTotalHours = sapi.World.Calendar.TotalHours;
        var owner = ResolveCommandOwner(bot, context);
        firepit.MarkDirty(true, owner);
        bot.RecordActionResult("firepit-light", true, "lit (re-armed) firepit " + pos, sapi.World.ElapsedMilliseconds);
        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = "firepit " + pos + " re-armed (deterministic firestarter; 2 h cold timer reset) - fueling will now auto-ignite",
            Data = new { pos = new { x = pos.X, y = pos.Y, z = pos.Z }, canIgniteFuel = true }
        };
    }
}
