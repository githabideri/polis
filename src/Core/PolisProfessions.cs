using System.Collections.Generic;

namespace PolisBuilderNpc.Core;

public class ProfessionLoadout
{
    public string Name { get; }
    public List<(string SlotName, string ItemCode, int Qty)> Items { get; }

    public ProfessionLoadout(string name, List<(string, string, int)> items)
    {
        Name = name;
        Items = items;
    }
}

public static class PolisProfessions
{
    public const string DefaultProfession = "laborer";

    public static readonly Dictionary<string, ProfessionLoadout> All = new()
    {
        ["laborer"] = new ProfessionLoadout("laborer", new()
        {
            ("backpack0", "linensack", 1),
        }),

        ["miner"] = new ProfessionLoadout("miner", new()
        {
            ("righthand", "pickaxe-copper", 1),
            ("backpack0", "miningbag", 1),
        }),

        ["lumberjack"] = new ProfessionLoadout("lumberjack", new()
        {
            ("righthand", "axe-felling-copper", 1),
            ("backpack0", "backpack-normal", 1),
        }),

        ["builder"] = new ProfessionLoadout("builder", new()
        {
            ("backpack0", "backpack-sturdy", 1),
            ("backpack1", "linensack", 1),
        }),

        ["farmer"] = new ProfessionLoadout("farmer", new()
        {
            ("righthand", "hoe-copper", 1),
            ("lefthand", "scythe-copper", 1),
            ("backpack0", "linensack", 1),
        }),

        ["hunter"] = new ProfessionLoadout("hunter", new()
        {
            ("righthand", "spear-generic-copper", 1),
            ("lefthand", "knife-generic-copper", 1),
            ("backpack0", "hunterbackpack", 1),
        }),

        ["smith"] = new ProfessionLoadout("smith", new()
        {
            ("righthand", "hammer-copper", 1),
            ("lefthand", "tongs", 1),
            ("backpack0", "backpack-normal", 1),
        }),

        ["knapper"] = new ProfessionLoadout("knapper", new()
        {
            ("righthand", "flint", 1),
            ("backpack0", "linensack", 1),
        }),
    };
}
