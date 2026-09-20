using System.Collections.Generic;
using System.Linq;
using Vintagestory.API.MathTools;

namespace PolisBuilderNpc.Core;

/// <summary>
/// Named AABB zone registry. Wraps a dictionary from PolisGlobalData.
/// </summary>
public class PolisZoneRegistry
{
    private readonly Dictionary<string, ZoneRecord> zones;

    public PolisZoneRegistry(Dictionary<string, ZoneRecord> zones)
    {
        this.zones = zones;
    }

    public int Count => zones.Count;

    public void RegisterZone(string name, Cuboidi bounds)
    {
        zones[name] = new ZoneRecord { Name = name, Bounds = bounds };
    }

    public bool RemoveZone(string name)
    {
        return zones.Remove(name);
    }

    public ZoneRecord GetZone(string name)
    {
        return zones.TryGetValue(name, out var record) ? record : null;
    }

    public List<string> GetZonesAt(BlockPos pos)
    {
        var result = new List<string>();
        foreach (var kvp in zones)
        {
            if (kvp.Value.Bounds.Contains(pos.X, pos.Y, pos.Z))
            {
                result.Add(kvp.Key);
            }
        }
        return result;
    }

    public bool IsInZone(BlockPos pos, string name)
    {
        return zones.TryGetValue(name, out var record) && record.Bounds.Contains(pos.X, pos.Y, pos.Z);
    }

    public Dictionary<string, ZoneRecord> GetAllZones()
    {
        return zones;
    }
}
