using System;
using System.Linq;
using System.Reflection;
using Vintagestory.API.Common;
using Vintagestory.API.Common.Entities;
using Vintagestory.API.Datastructures;
using Vintagestory.API.MathTools;
using Vintagestory.GameContent;
using Polis.Helpers;

/// <summary>
/// Farm commands (1.22 decompile-verified):
///
///   till &lt;x&gt; &lt;y&gt; &lt;z&gt;
///       Turn the soil block at pos into farmland, mirroring the engine's
///       ItemHoe.DoTill: the farmland variant is derived from the soil
///       code's last part (soil-low-none -&gt; farmland-dry-none), the
///       soil-nutrition BE attributes are carried over, and the claims
///       check runs against the context player (the engine only allows
///       a player's IPlayer there; bots mirror that path).
///
///   farmland &lt;x&gt; &lt;y&gt; &lt;z&gt;
///       Probe the farmland BE: crop, stage, ripe, moisture, hours to
///       next stage, and the block sitting above (the crop's block).
///       Growth is gated on moistureLevel &gt;= 0.1 (rain or a watering
///       can); the probe reports whether the cell qualifies.
///
///   sow &lt;x&gt; &lt;y&gt; &lt;z&gt; [seedCode]
///       Plant through the engine's own BlockEntityFarmland.TryPlant:
///       the seed is taken from the bot's cargo (any slot), the crop
///       block is derived from the seed code (seeds-rye -&gt;
///       crop-rye-2, the first growth stage). This is the real
///       planting path (seed consumed via the crop's OnPlanted
///       behaviors) - the Python sow composite (setblock) stays as
///       fallback for worlds where the BE is not plantable.
/// </summary>
public partial class PolisSystem
{
    PolisTestHarness.CommandResult ExecuteTillCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        if (args.Length < 3)
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Usage: till <x> <y> <z>" };
        if (!TryGetHarnessBot(context, out var bot, out var selErr))
            return new PolisTestHarness.CommandResult { Ok = false, Message = selErr };
        if (!double.TryParse(args[0], out var fx) || !double.TryParse(args[1], out var fy) || !double.TryParse(args[2], out var fz))
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Invalid coordinates" };
        var pos = new Vec3d(fx, fy, fz).AsBlockPos;
        var ba = sapi.World.BlockAccessor;
        var block = ba.GetBlock(pos);
        if (block == null || block.Code == null || !block.Code.PathStartsWith("soil"))
            return new PolisTestHarness.CommandResult { Ok = false, Message = "not a soil block: " + (block == null ? "air" : block.Code.ToString()) };
        if (ba.GetBlock(pos.UpCopy()) != null && ba.GetBlock(pos.UpCopy()).BlockId != 0)
            return new PolisTestHarness.CommandResult { Ok = false, Message = "cell above not clear" };
        if (!TryGetContextPlayer(context, out var player, out var perr))
            return new PolisTestHarness.CommandResult { Ok = false, Message = perr };
        if (!sapi.World.Claims.TryAccess(player, pos, (EnumBlockAccessFlags)1))
            return new PolisTestHarness.CommandResult { Ok = false, Message = "claims: no access at " + pos };

        string soilCode = block.Code.ToString();
        string part = soilCode.Contains("-") ? soilCode.Substring(soilCode.LastIndexOf("-")) : soilCode;
        var farmland = sapi.World.GetBlock(new AssetLocation("farmland-dry-" + part));
        if (farmland == null)
            return new PolisTestHarness.CommandResult { Ok = false, Message = "no farmland-dry-" + part + " block in this version" };

        TreeAttribute carried = null;
        var soilBe = ba.GetBlockEntity(pos) as BlockEntitySoilNutrition;
        if (soilBe != null)
        {
            carried = new TreeAttribute();
            soilBe.ToTreeAttributes(carried);
        }
        ba.SetBlock(farmland.BlockId, pos);
        var flBe = ba.GetBlockEntity(pos) as BlockEntityFarmland;
        if (flBe != null)
            flBe.OnCreatedFromSoil(block, carried);
        ba.MarkBlockDirty(pos, (IPlayer)null);
        bot.RecordActionResult("till", true, "tilled " + block.Code + " at " + pos, sapi.World.ElapsedMilliseconds);

        string state = null;
        try { state = (flBe != null && flBe.IsVisiblyMoist) ? "moist" : "dry"; } catch { }
        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = "tilled: " + block.Code + " -> " + ba.GetBlock(pos).Code + " (" + state + ")",
            Data = new { pos = new { x = (int)pos.X, y = (int)pos.Y, z = (int)pos.Z }, soil = block.Code.ToString(), farmland = ba.GetBlock(pos).Code.ToString(), state }
        };
    }

    PolisTestHarness.CommandResult ExecuteFarmlandCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        if (args.Length < 3)
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Usage: farmland <x> <y> <z>" };
        if (!double.TryParse(args[0], out var fx) || !double.TryParse(args[1], out var fy) || !double.TryParse(args[2], out var fz))
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Invalid coordinates" };
        var pos = new Vec3d(fx, fy, fz).AsBlockPos;
        var ba = sapi.World.BlockAccessor;
        var be = ba.GetBlockEntity(pos) as BlockEntityFarmland;
        if (be == null)
            return new PolisTestHarness.CommandResult { Ok = false, Message = "no farmland BE at " + pos + " (block: " + ba.GetBlock(pos).Code + ")" };

        object cropObj = null;
        int stage = -1;
        int stages = 0;
        bool ripe = false;
        try
        {
            var crop = be.GetCrop();
            if (crop != null)
            {
                cropObj = crop.Code.ToString();
                stage = be.GetCropStage(crop);
                stages = crop.CropProps.GrowthStages;
                ripe = be.HasRipeCrop();
            }
        }
        catch (Exception e)
        {
            cropObj = "err:" + e.Message;
        }

        double moisture = -1;
        var f = typeof(BlockEntityFarmland).GetField("moistureLevel", BindingFlags.NonPublic | BindingFlags.Public | BindingFlags.Instance);
        if (f != null)
        {
            var v = f.GetValue(be);
            if (v is double d) moisture = d;
            else if (v != null) moisture = Convert.ToDouble(v);
        }

        string above = ba.GetBlock(pos.UpCopy()) == null ? "air" : ba.GetBlock(pos.UpCopy()).Code.ToString();
        double hoursNext = 0;
        try { hoursNext = be.TotalHoursForNextStage; } catch { }

        bool moistOk = moisture >= 0.1;
        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = "farmland " + pos + ": " + above + " stage " + stage + "/" + stages + (ripe ? " (ripe)" : "") + " moisture " + (moisture >= 0 ? moisture.ToString("0.##") : "?") + (moistOk ? "" : " (below 0.1 - not growing)"),
            Data = new
            {
                pos = new { x = (int)pos.X, y = (int)pos.Y, z = (int)pos.Z },
                crop = cropObj,
                stage,
                stages,
                ripe,
                moisture,
                moistOk,
                hoursToNext = hoursNext,
                above
            }
        };
    }

    PolisTestHarness.CommandResult ExecuteSowCommand(string[] args, PolisTestHarness.CommandContext context)
    {
        if (args.Length < 3)
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Usage: sow <x> <y> <z> [seedCode] (seedCode defaults to game:seeds-rye)" };
        if (!TryGetHarnessBot(context, out var bot, out var selErr))
            return new PolisTestHarness.CommandResult { Ok = false, Message = selErr };
        if (!double.TryParse(args[0], out var fx) || !double.TryParse(args[1], out var fy) || !double.TryParse(args[2], out var fz))
            return new PolisTestHarness.CommandResult { Ok = false, Message = "Invalid coordinates" };
        var pos = new Vec3d(fx, fy, fz).AsBlockPos;
        var ba = sapi.World.BlockAccessor;
        var be = ba.GetBlockEntity(pos) as BlockEntityFarmland;
        if (be == null)
            return new PolisTestHarness.CommandResult { Ok = false, Message = "no farmland BE at " + pos + " (block: " + ba.GetBlock(pos).Code + ")" };

        string seedCode = (args.Length >= 4 && !string.IsNullOrEmpty(args[3])) ? args[3] : "game:seeds-rye";
        if (!seedCode.StartsWith("game:")) seedCode = "game:" + seedCode;
        var cargo = PolisInventoryHelpers.BotCargo(bot.Entity);
        if (cargo == null)
            return new PolisTestHarness.CommandResult { Ok = false, Message = "bot " + bot.Entity.EntityId + " has no cargo" };
        ItemSlot seedSlot = null;
        int seedSlotIdx = -1;
        for (int i = 0; i < cargo.Count; i++)
        {
            var s = cargo[i];
            if (s == null || s.Itemstack == null || s.Itemstack.Collectible == null) continue;
            string c = s.Itemstack.Collectible.Code.ToString();
            if (c == seedCode || c == seedCode.Substring(5))
            {
                seedSlot = s;
                seedSlotIdx = i;
                break;
            }
        }
        if (seedSlot == null)
            return new PolisTestHarness.CommandResult { Ok = false, Message = "bot " + bot.Entity.EntityId + " has no " + seedCode };

        string seedPart = seedCode.Substring("game:seeds-".Length);
        var crop = sapi.World.GetBlock(new AssetLocation("game:crop-" + seedPart + "-2"));
        if (crop == null || crop.CropProps == null)
            return new PolisTestHarness.CommandResult { Ok = false, Message = "no crop-" + seedPart + "-2 block (seed: " + seedCode + ")" };

        if (!be.CanPlant())
            return new PolisTestHarness.CommandResult { Ok = false, Message = "farmland cell above not empty: " + ba.GetBlock(pos.UpCopy()).Code };

        bool ok;
        try
        {
            ok = be.TryPlant(crop, seedSlot, bot.Entity, default(BlockSelection));
        }
        catch (Exception e)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "TryPlant threw: " + e.Message };
        }
        if (!ok)
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = "TryPlant refused (CanPlant/CropProps gate)" };
        }
        int left = -1;
        try { left = (seedSlot.Itemstack != null) ? seedSlot.Itemstack.StackSize : 0; } catch { }
        string above = ba.GetBlock(pos.UpCopy()) == null ? "air" : ba.GetBlock(pos.UpCopy()).Code.ToString();
        bot.RecordActionResult("sow", true, seedCode + " at " + pos + " -> " + above, sapi.World.ElapsedMilliseconds);
        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = "planted " + above + " at " + pos + " from slot " + seedSlotIdx + " (" + seedCode + "; " + left + " left)",
            Data = new { pos = new { x = (int)pos.X, y = (int)pos.Y, z = (int)pos.Z }, seed = seedCode, seedLeft = left, above, slot = seedSlotIdx }
        };
    }
}
