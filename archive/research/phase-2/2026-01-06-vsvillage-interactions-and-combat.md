# vsvillage Interaction + Combat Patterns

**Date:** 2026-01-06  
**Scope:** How vsvillage villagers interact/attack without player context.

## Summary
vsvillage villagers do **not** use `Entity.OnInteract(Attack)` for combat.  
They rely on AI tasks that either call `ReceiveDamage(...)` directly or spawn projectiles.
Most “interactions” are implemented as task-specific world changes rather than player-style interact calls.

## Combat patterns

### Melee (AI task, non-player)
**File:** `docs/vsvillage/VSVillage/src/Entity/AITask/AiTaskVillagerMeleeAttack.cs`  
**Notes:** Extends `AiTaskMeleeAttack`. Adjusts damage and animation based on right-hand item, but uses base melee attack flow.
- Damage is applied in the base task (from `AiTaskMeleeAttack`) via `targetEntity.ReceiveDamage(...)`.
- No `EntityPlayer` context required.

### Ranged (projectile, non-player)
**File:** `docs/vsvillage/VSVillage/src/Entity/AITask/AiTaskVillagerRangedAttack.cs`  
**Notes:**
- Spawns `EntityProjectile` and sets `FiredBy = entity`.
- Sets `projectile.Damage = damage`, spawns with velocity toward target.
- Uses `RayTraceForSelection` to ensure line of sight (`entityInTheWay()`).
- No `IPlayer` required.

## Interaction patterns (non-player)

### Base “goto + interact” task
**File:** `docs/vsvillage/VSVillage/src/Entity/AITask/AiTaskGotoAndInteract.cs`  
**Pattern:**
- Navigate to target position.
- Play `"interact"` animation.
- Call `ApplyInteractionEffect()` (task-specific logic).
- No player-style `OnInteract` call required.

### Examples of task-specific effects
- **Fill trough:** `AiTaskVillagerFillTrough` uses `DummySlot`, `ItemSlot.TryPutInto`, `MarkDirty`, and particle effects.  
  **File:** `docs/vsvillage/VSVillage/src/Entity/AITask/AiTaskVillagerFillTrough.cs`
- **Cultivate crops:** `AiTaskVillagerCultivateCrops` calls `BlockEntityFarmland.TryGrowCrop(...)` and spawns particles.  
  **File:** `docs/vsvillage/VSVillage/src/Entity/AITask/AiTaskVillagerCultivateCrops.cs`
- **Heal wounded:** `AiTaskHealWounded` uses `ReceiveDamage` with `EnumDamageType.Heal` and `SourceEntity = null` to avoid retaliation.  
  **File:** `docs/vsvillage/VSVillage/src/Entity/AITask/AiTaskHealWounded.cs`
- **Socialize:** `AiTaskVillagerSocialize` broadcasts a talk packet when close enough; can target other villagers or players.  
  **File:** `docs/vsvillage/VSVillage/src/Entity/AITask/AiTaskVillagerSocialize.cs`

## Player-only entry points (not NPC tasks)
- **Mayor workstation UI:** `BlockMayorWorkstation.OnBlockInteractStart(IPlayer byPlayer, ...)` uses `IServerPlayer` to open management UI.  
  **File:** `docs/vsvillage/VSVillage/src/Block/BlockMayorWorkstation.cs`
- **Villager horn item:** `ItemVillagerHorn.OnHeldInteractStart(...)` checks `byEntity is EntityPlayer` and game mode to consume item.  
  **File:** `docs/vsvillage/VSVillage/src/Item/ItemVillagerHorn.cs`

## Implications for polis-builder-npc
- vsvillage NPCs avoid player-only APIs by using **AI tasks + direct world/BE calls**.
- This supports a bot approach that mirrors AI tasks rather than calling `Entity.OnInteract(Attack)`.
- Player-only UI interactions (management, dialogs) still require `IPlayer`/`IServerPlayer`.
