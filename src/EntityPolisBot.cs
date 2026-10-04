using Vintagestory.API.Common;
using Vintagestory.API.Common.Entities;
using Vintagestory.API.Datastructures;
using Vintagestory.GameContent;
using Polis.Core;

public class EntityPolisBot : EntityHumanoid
{
    EntityBehaviorSeraphInventory invbh;

    /// <summary>
    /// Cargo inventory: 16 generic slots. [0]=right hand, [1]=left hand,
    /// [2..15]=grid (grid slot 2 = "backpack0", 3 = "backpack1").
    ///
    /// 1.22: the "seraphinventory" behavior became an InventoryGear
    /// (equipment/clothing only - rejects non-wearable items, and the old
    /// 19-slot layout with hands at [15]/[16] is gone), which is why
    /// give/mine-loot overflowed onto the ground. All bot cargo lives here.
    /// Not persisted to entity attributes: bots are ephemeral (respawned
    /// per mission; the harness repopulates on demand).
    /// </summary>
    public InventoryGeneric Cargo;

    /// <summary>
    /// True while the bot is parked (no active mission): the polis hunger
    /// behavior (EntityBehaviorPolisHunger) suspends the engine's drain so
    /// idle bots don't starve in ~4 in-game hours. The policy engine /
    /// mission system owns this flag; `harness: hungerpause` toggles it.
    /// </summary>
    public bool HungerSuspended;

    public override bool StoreWithChunk => true;

    public override ItemSlot RightHandItemSlot => Cargo?[0] ?? base.RightHandItemSlot;
    public override ItemSlot LeftHandItemSlot => Cargo?[1] ?? base.LeftHandItemSlot;

    public override void Initialize(EntityProperties properties, ICoreAPI api, long chunkindex3d)
    {
        base.Initialize(properties, api, chunkindex3d);
        invbh = GetBehavior<EntityBehaviorSeraphInventory>();
        Cargo = new InventoryGeneric(PolisConstants.CargoSlots, "polisbot-cargo-" + EntityId, api);
    }

    public override void OnEntitySpawn()
    {
        base.OnEntitySpawn();

        if (World.Side != EnumAppSide.Client) return;
        if (Properties?.Client?.Renderer is EntityShapeRenderer renderer)
        {
            renderer.DoRenderHeldItem = true;
        }
    }
}
