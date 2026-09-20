using Vintagestory.API.Common;
using Vintagestory.API.Common.Entities;
using Vintagestory.API.Datastructures;
using Vintagestory.GameContent;

public class EntityPolisBot : EntityHumanoid
{
    EntityBehaviorSeraphInventory invbh;

    public override bool StoreWithChunk => true;

    public override ItemSlot RightHandItemSlot => invbh?.Inventory[15] ?? base.RightHandItemSlot;
    public override ItemSlot LeftHandItemSlot => invbh?.Inventory[16] ?? base.LeftHandItemSlot;

    public override void Initialize(EntityProperties properties, ICoreAPI api, long chunkindex3d)
    {
        base.Initialize(properties, api, chunkindex3d);
        invbh = GetBehavior<EntityBehaviorSeraphInventory>();
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
