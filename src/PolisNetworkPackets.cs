using System.Collections.Generic;
using ProtoBuf;
using Vintagestory.API.MathTools;

// ============================================
// Persistent Bot Registry (SaveGame storage)
// ============================================

[ProtoContract]
public class PolisGlobalData
{
    [ProtoMember(1)]
    public Dictionary<long, BotRecord> Bots = new Dictionary<long, BotRecord>();

    [ProtoMember(2)]
    public Dictionary<string, ZoneRecord> Zones = new Dictionary<string, ZoneRecord>();

    [ProtoMember(3)]
    public Dictionary<string, ViewpointRecord> Viewpoints = new Dictionary<string, ViewpointRecord>();

    [ProtoMember(4)]
    public PolisVitalsData Vitals = new PolisVitalsData();
}

[ProtoContract]
public class BotRecord
{
    [ProtoMember(1)] public long EntityId;
    [ProtoMember(2)] public string OwnerUid;
    [ProtoMember(3)] public string Name;
    [ProtoMember(4)] public Vec3d LastKnownPos;
    [ProtoMember(5)] public bool IsLoaded;
    [ProtoMember(6)] public string EntityCode;
    [ProtoMember(7)] public string Profession;
}

// ============================================
// Network Packets
// ============================================

[ProtoContract]
public class PolisBotListRequestPacket { }

[ProtoContract]
public class PolisBotListResponsePacket
{
    [ProtoMember(1)]
    public PolisBotEntry[] Bots;
}

[ProtoContract]
public class PolisBotEntry
{
    [ProtoMember(1)]
    public long EntityId;
    [ProtoMember(2)]
    public string Code;
    // Use primitive doubles instead of Vec3d to avoid network serialization deadlocks
    [ProtoMember(3)]
    public double X;
    [ProtoMember(4)]
    public double Y;
    [ProtoMember(5)]
    public double Z;
    [ProtoMember(6)]
    public bool IsSelected;
    [ProtoMember(7)]
    public bool IsLoaded;
    [ProtoMember(8)]
    public string OwnerUid;
}

[ProtoContract]
public class PolisBotActionPacket
{
    [ProtoMember(1)]
    public long EntityId;
    [ProtoMember(2)]
    public string Action; // "select", "delete", "possession", "spawn"
}

[ProtoContract]
public class PolisPanicPacket { }

[ProtoContract]
public class PolisDebugStatePacket
{
    [ProtoMember(1)]
    public bool DebugEnabled;
}

// ============================================
// Screenshot Packets
// ============================================

/// <summary>
/// Server -> Client: Request a screenshot capture.
/// </summary>
[ProtoContract]
public class PolisScreenshotRequestPacket
{
    /// <summary>Unique request ID for correlation</summary>
    [ProtoMember(1)]
    public string RequestId;

    /// <summary>If true, also save to file on client</summary>
    [ProtoMember(2)]
    public bool SaveToFile;
}

/// <summary>
/// Client -> Server: Screenshot capture result.
/// </summary>
[ProtoContract]
public class PolisScreenshotResponsePacket
{
    /// <summary>Correlation ID from request</summary>
    [ProtoMember(1)]
    public string RequestId;

    /// <summary>True if capture succeeded</summary>
    [ProtoMember(2)]
    public bool Success;

    /// <summary>Image width in pixels</summary>
    [ProtoMember(3)]
    public int Width;

    /// <summary>Image height in pixels</summary>
    [ProtoMember(4)]
    public int Height;

    /// <summary>Base64-encoded PNG data</summary>
    [ProtoMember(5)]
    public string Base64Png;

    /// <summary>Local file path if saved</summary>
    [ProtoMember(6)]
    public string FilePath;

    /// <summary>Error message if failed</summary>
    [ProtoMember(7)]
    public string Error;

    /// <summary>Capture time in milliseconds</summary>
    [ProtoMember(8)]
    public long CaptureTimeMs;
}

// ============================================
// Player View Direction Packet
// ============================================

/// <summary>
/// Server -> Client: Force player camera to look in a specific direction.
/// </summary>
[ProtoContract]
public class PolisSetViewDirectionPacket
{
    /// <summary>Camera yaw in radians</summary>
    [ProtoMember(1)]
    public float Yaw;

    /// <summary>Camera pitch in radians</summary>
    [ProtoMember(2)]
    public float Pitch;
}

// ============================================
// Zone Registry (SaveGame storage)
// ============================================

[ProtoContract]
public class ZoneRecord
{
    [ProtoMember(1)] public string Name;
    [ProtoMember(2)] public Cuboidi Bounds;
}

// ============================================
// Viewpoint Registry (SaveGame storage)
// ============================================

/// <summary>
/// A named camera viewpoint for observer screenshots.
/// Stores position and orientation for capturing screenshots
/// without permanently moving the player.
/// </summary>
[ProtoContract]
public class ViewpointRecord
{
    /// <summary>User-assigned name for this viewpoint</summary>
    [ProtoMember(1)] public string Name;

    /// <summary>Camera X position</summary>
    [ProtoMember(2)] public double X;

    /// <summary>Camera Y position</summary>
    [ProtoMember(3)] public double Y;

    /// <summary>Camera Z position</summary>
    [ProtoMember(4)] public double Z;

    /// <summary>Camera yaw in radians</summary>
    [ProtoMember(5)] public float Yaw;

    /// <summary>Camera pitch in radians</summary>
    [ProtoMember(6)] public float Pitch;

    /// <summary>Optional linked station/zone name</summary>
    [ProtoMember(7)] public string StationName;
}

// ============================================
// Container Registry (SaveGame storage)
// ============================================

/// <summary>
/// Persistent storage for named container references.
/// Saved to world data for cross-session persistence.
/// </summary>
[ProtoContract]
public class PolisContainerRegistry
{
    [ProtoMember(1)]
    public Dictionary<string, ContainerRecord> Containers = new Dictionary<string, ContainerRecord>();
}

/// <summary>
/// A named reference to a storage container in the world.
/// Note: VS block entities have no unique IDs, only coordinates.
/// Registry entries may become stale if containers are moved/destroyed.
/// </summary>
[ProtoContract]
public class ContainerRecord
{
    /// <summary>User-assigned name for this container</summary>
    [ProtoMember(1)]
    public string Name;

    /// <summary>Block X coordinate</summary>
    [ProtoMember(2)]
    public int X;

    /// <summary>Block Y coordinate</summary>
    [ProtoMember(3)]
    public int Y;

    /// <summary>Block Z coordinate</summary>
    [ProtoMember(4)]
    public int Z;

    /// <summary>Block code at registration time (for validation)</summary>
    [ProtoMember(5)]
    public string BlockCode;

    /// <summary>UID of player who registered this container</summary>
    [ProtoMember(6)]
    public string OwnerUid;

    /// <summary>Container type: chest, vessel, barrel, crate, generic</summary>
    [ProtoMember(7)]
    public string ContainerType;

    /// <summary>Unix timestamp (ms) when registered</summary>
    [ProtoMember(8)]
    public long RegisteredAt;

    /// <summary>Optional user description</summary>
    [ProtoMember(9)]
    public string Description;
}

// ============================================
// Vitals (per-world survival telemetry)
// ============================================

/// <summary>
/// A single vitals sample for one entity (bot or player), taken by the
/// 1 Hz sampler. Position + vitals + behavior levels in one record.
/// </summary>
[ProtoContract]
public class VitalsSample
{
    [ProtoMember(1)] public long EntityId;
    [ProtoMember(2)] public string Code;
    [ProtoMember(3)] public string Name;
    [ProtoMember(4)] public float Sat;
    [ProtoMember(5)] public float SatMax;
    [ProtoMember(6)] public float Hp;
    [ProtoMember(7)] public float HpMax;
    [ProtoMember(8)] public double X;
    [ProtoMember(9)] public double Y;
    [ProtoMember(10)] public double Z;
    /// <summary>In-game seconds since world start (day*86400 + hourOfDay*3600)</summary>
    [ProtoMember(11)] public long GameTimeSec;
    [ProtoMember(12)] public long GameDay;
    /// <summary>Behavior levels the entity exposes (1 = present).</summary>
    [ProtoMember(13)] public Dictionary<string, int> Skills;
}

/// <summary>
/// Running per-world vitals record, stored in the world's save data
/// (same StoreData path as the bot registry). Series is downsampled:
/// at most one sample per persistence interval (default 1 in-game hour)
/// per entity, capped at MaxSeriesSamples per entity.
/// </summary>
[ProtoContract]
public class PolisVitalsData
{
    /// <summary>EntityId -> downsampled sample series (oldest first).</summary>
    [ProtoMember(1)]
    public Dictionary<long, List<VitalsSample>> Series = new Dictionary<long, List<VitalsSample>>();

    /// <summary>Cap on stored samples per entity (oldest dropped).</summary>
    [ProtoMember(2)] public int MaxSeriesSamples = 336;
}
