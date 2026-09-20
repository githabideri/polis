# Bot Tracking & Ownership Analysis

## 1. Current State (`polis-builder-npc`)
*   **Tracking:** Purely in-memory via `Dictionary<long, BotState> bots` in `PolisBuilderNpcSystem`.
*   **Persistence:** **None.** The list is wiped on server restart.
*   **Unloading:** Bots are explicitly removed from the tracking list in `OnTick` if `bot.Entity == null` (which happens when their chunk unloads).
*   **Ownership:** "Selection" is tracked per-session in `selectedByPlayer`. No permanent ownership data is stored on the entity or in the world save.
*   **Consequence:** Bots effectively revert to "feral" vanilla entities if you walk away (unload chunk) or restart the server. You lose the ability to recall/command them remotely.

## 2. Vanilla Engine Capabilities
*   **Entity Lookup:** `api.World.GetEntityById(long id)` **only returns loaded entities**. It returns `null` if the entity is in an unloaded chunk.
*   **Global Search:** There is no engine-level "Global Entity Registry". Entities are strictly partitioned by chunks.
*   **Persistence:** The engine saves entities with their chunks. It does not maintain a global list of "special" entities.

## 3. Reference Implementation (`vsvillage`)
`vsvillage` solves this using a **Shadow Registry** pattern.

### Architecture:
1.  **Central Manager (`VillageManager : ModSystem`):**
    *   Maintains a persistent `ConcurrentDictionary` of data objects (`Village`, `VillagerData`).
    *   Uses `api.WorldManager.SaveGame.StoreData()` to serialize this list to the world save file (separate from chunks).
    *   **Crucial:** This list persists even when entities are unloaded/despawned.

2.  **Lightweight Data (`VillagerData`):**
    *   Stores `ID`, `Name`, `Profession`, `HomePosition`.
    *   Does *not* store the `Entity` object directly (to avoid leaks).

3.  **Linkage (`EntityBehaviorVillager`):**
    *   When a villager entity loads/spawns, its behavior looks up its record in the `VillageManager`.
    *   It updates the "live" reference if needed, but the Manager is the source of truth.

## 4. Recommendation for Polis
To support remote commands ("Come here") and ownership ("My bot"), we must implement a **Bot Registry System**.

### Proposed Data Structure (ProtoBuf):
```csharp
[ProtoContract]
public class PolisGlobalData {
    [ProtoMember(1)] public Dictionary<long, BotRecord> Bots = new Dictionary<long, BotRecord>();
}

[ProtoContract]
public class BotRecord {
    [ProtoMember(1)] public long EntityId;
    [ProtoMember(2)] public string OwnerUid;
    [ProtoMember(3)] public string Name;
    [ProtoMember(4)] public Vec3d LastKnownPos; // Verified safe for ProtoBuf
    [ProtoMember(5)] public bool IsLoaded; 
}
```

### Implementation Steps:
1.  **Persistence:** Register save/load events in `StartServerSide`:
    ```csharp
    api.Event.SaveGameLoaded += OnSaveGameLoaded;
    api.Event.GameWorldSave += OnGameWorldSave;

    private void OnSaveGameLoaded() {
        byte[] data = api.WorldManager.SaveGame.GetData("polis-bots");
        globalData = data == null ? new PolisGlobalData()
                    : SerializerUtil.Deserialize<PolisGlobalData>(data);
    }

    private void OnGameWorldSave() {
        api.WorldManager.SaveGame.StoreData("polis-bots", SerializerUtil.Serialize(globalData));
    }
    ```
2.  **Ownership Attribute:** Add an `ownerUid` string attribute to the bot entity itself (so if the registry is lost, we can rebuild it from the entities).
    ```csharp
    // When bot is spawned/claimed
    entity.WatchedAttributes.SetString("ownerUid", playerUid);
    entity.WatchedAttributes.MarkPathDirty("ownerUid");
    ```

3.  **Entity Lifecycle Events:**
    *   `OnEntityLoaded`: Update `IsLoaded = true` and `LastKnownPos`.
    *   `OnEntityDespawn`: Check reason. If `Unload`, set `IsLoaded = false` and update `LastKnownPos`.
    ```csharp
    private void OnEntityDespawn(Entity entity, EntityDespawnData reason) {
        if (reason.Reason == EnumDespawnReason.Unload) {
            // Update registry: IsLoaded = false
        }
    }
    ```

4.  **UI Update:** The Bot Manager UI should show *all* bots from the Registry.
    *   Bots with `IsLoaded = false` should be grayed out or marked "Far Away".
    *   Clicking them could trigger a "Summon" (teleport to player) or "Wake" (load chunk) command in the future.

## 5. Verification (btca Research)
All claims in this document have been verified via btca research of reference repos:

| Claim | Verified By | Evidence |
|--------|-------------|----------|
| Pure in-memory tracking | Code inspection | PolisBuilderNpcSystem.cs:35 |
| No persistence mechanism | Code inspection | No SaveGame events registered |
| vsvillage Shadow Registry pattern | vsvillage | VillageManager.cs uses SaveGame.StoreData/GetData |
| SaveGame events: SaveGameLoaded, GameWorldSave | vsapi | IServerEventAPI.cs |
| EntityDespawnData.Reason (Unload) | vsapi | EntityDespawnData.cs |
| Vec3d ProtoBuf safety | vsapi | Vec3d.cs has [ProtoContract] |
| WatchedAttributes for ownership | vssurvivalmod | EntityBehaviorOwnable.cs:61 |
| 5-second delayed init for chunk loading | vsvillage | EntityBehaviorVillager.cs:Initialize |

**Reference:** `btca_usage.md` for query methodology