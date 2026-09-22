namespace PolisBuilderNpc.Core;

/// <summary>
/// Centralized constants for the Polis Builder NPC mod.
/// Eliminates scattered magic numbers across the codebase.
/// </summary>
public static class PolisConstants
{
    // Bot identity
    public const string DefaultBotCode = "polis-builder-npc:polisbot";

    // Highlight slot IDs (unique IDs to avoid conflicts with other mods)
    public const int HighlightSlotId = 48521;
    public const int PathHighlightSlotId = 48522;
    public const int BotHighlightSlotId = 48523;
    public const int PreviewPathHighlightSlotId = 48524;
    public const int EnginePathDebugHighlightSlotId = 2;
    public const int ZoneHighlightSlotId = 48525;

    // Action ranges
    public const float DefaultActionRange = 4.5f;
    public const float MaxGotoLookRange = 256f;
    public const float PreviewDefaultRange = 256f;

    // Path preview
    public const int MaxPathHighlights = 200;
    public const int PreviewPathIntervalMs = 250;
    public const int PreviewPathSearchDepth = 3000;

    // Mining/harvesting
    public const float CollectDelay = 1.2f;
    public const float DefaultCollectRadius = 3f;
    public const float MinMiningSpeed = 0.1f;
    public const float DefaultHarvestTime = 1.0f;

    // Tick intervals
    public const float TickInterval = 0.1f;
    public const float SoundInterval = 0.25f;
    public const int DefaultVoxelsPerTick = 4;

    // Butcher
    public const float DefaultDropMultiplier = 1.0f;

    // Press packet IDs
    public const int PacketIdScrewStart = 1002;
    public const int PacketIdUnscrew = 1003;

    // Test harness
    public const int DefaultPort = 8585;
    public const int WsPingIntervalMs = 30000;

    // Inventory slots
    public const int BackpackSlotId0 = 17;
    public const int BackpackSlotId1 = 18;

    // Cargo inventory (EntityPolisBot.Cargo, 1.22): [0]=right hand, [1]=left
    // hand, [2..15]=grid; slots 2/3 are reported as "backpack0"/"backpack1".
    public const int CargoSlots = 16;
    public const int CargoBackpackSlot0 = 2;
    public const int CargoBackpackSlot1 = 3;
}
