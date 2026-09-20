# NPC Attack Patterns (AI Tasks vs OnInteract)

**Date:** 2026-01-06  
**Scope:** How NPCs apply melee damage in vanilla mods; identify non-player attack patterns.

## Summary
NPC melee attacks in vanilla code paths generally **do not** use `Entity.OnInteract(..., Attack)`.  
Instead, AI tasks apply damage directly with `targetEntity.ReceiveDamage(...)`, using
`DamageSource.Source = EnumDamageSource.Entity` and `SourceEntity = attacker`.

This pattern avoids the `EntityPlayer`-only assumptions found in `EntityAgent.OnInteract(Attack)`.

## vsessentialsmod: AiTaskMeleeAttack
**File:** `vsessentialsmod/Entity/AI/Task/TasksImpl/AiTaskMeleeAttack.cs`  
**Method:** `attackTarget()`

- Direct damage call:
  - `targetEntity.ReceiveDamage(new DamageSource() { Source = EnumDamageSource.Entity, SourceEntity = entity, ... }, damage * GlobalConstants.CreatureDamageModifier);`
- Optional callback:
  - `if (entity is IMeleeAttackListener imal) { imal.DidAttack(targetEntity); }`

## vsessentialsmod: AiTaskMeleeAttackR (refactored)
**File:** `vsessentialsmod/Entity/AI/Task/TasksRefactored/AiTaskMeleeAttack.cs`  
**Method:** `AttackTarget()`

- Direct damage call with more config:
  - `targetEntity.ReceiveDamage(new DamageSource() { Source = EnumDamageSource.Entity, SourceEntity = entity, Type = Config.DamageType, ... }, Config.Damage * ...);`
- Same `IMeleeAttackListener` hook and kill handling.

## vssurvivalmod: Flying swoop attack
**File:** `docs/vssurvivalmod/Lore/Devastation/AiTaskFlySwoopAttack.cs`  
**Method:** `attackEntity(...)`

- Damage applied via `ReceiveDamage`:
  - `attackEntity.ReceiveDamage(new DamageSource() { Source = EnumDamageSource.Entity, SourceEntity = entity, ... }, damage * GlobalConstants.CreatureDamageModifier);`
- Uses `IMeleeAttackListener` if present.

## vsvillage: Villager melee attack
**File:** `docs/vsvillage/VSVillage/src/Entity/AITask/AiTaskVillagerMeleeAttack.cs`  
**Class:** `AiTaskVillagerMeleeAttack : AiTaskMeleeAttack`

The villager task extends `AiTaskMeleeAttack` and adjusts:
- damage based on `RightHandItemSlot.Itemstack.Item.AttackPower`
- animation choice (stab/slash)

This implies villager damage still flows through the base AI melee attack task and its
`ReceiveDamage` call, not through `OnInteract(Attack)`.

## Implications
- NPC combat is typically implemented as **AI task → ReceiveDamage**, not `OnInteract(Attack)`.
- Using `Entity.OnInteract(Attack)` for bots will likely keep failing on non-`EntityPlayer` actors.
- If/when we implement bot attacks, mimicking AI task damage application may be the most compatible path.
