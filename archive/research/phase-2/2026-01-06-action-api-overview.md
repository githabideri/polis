# Action API Overview (Player vs AI Paths)

**Date:** 2026-01-06  
**Purpose:** Snapshot of action categories, best-fit API paths, and current mod status.

## Summary
Player-style APIs often require `EntityPlayer`/`IPlayer` context and input state.
AI-style patterns in vanilla mods (vsvillage/vsessentials) avoid these by calling
server-side methods directly (e.g., `ReceiveDamage`, block entity methods, inventory ops).

## Action categories and best-fit API paths

### 1) Entity combat
- **Player-style:** `Entity.OnInteract(..., Attack)`  
  - **Risk:** player-only assumptions (`EntityPlayer.Player`), NRE for bots.
- **AI-style:** `target.ReceiveDamage(new DamageSource { Source = Entity, SourceEntity = bot, ... }, damage)`  
  - **Evidence:** `AiTaskMeleeAttack` in vsessentials; vsvillage melee/ranged tasks.
  - **Best-fit for bots:** AI-style.

### 2) Entity interact (non-combat)
- **Player-style:** `Entity.OnInteract(..., Interact)`  
  - **Risk:** many behaviors require `EntityPlayer` or selection box index or input state.
- **AI-style:** task-specific logic (direct world/BE effects).  
  - **Evidence:** vsvillage `AiTaskGotoAndInteract` tasks.
  - **Best-fit for bots:** AI-style when a direct method exists.

### 3) Block activate/use (doors, chests, levers)
- **Player-style:** `Block.OnBlockInteractStart(world, IPlayer, BlockSelection)`  
  - **Needed for:** UI-driven container access or player-only checks.
- **AI-style:** direct block entity method if available.  
  - **Best-fit for bots:** AI-style when automation is desired, player-style only when a player context is required.

### 4) Inventory transfer (bot <-> container)
- **Player-style:** open GUI + player inventory manager.
- **AI-style:** `ItemSlot.TryPutInto`, `TakeOut`, `MarkDirty`, `BlockEntity.MarkDirty`.  
  - **Best-fit for bots:** AI-style.

### 5) Workstations / crafting
- **Player-style:** GUI + packets (anvil, clayforming, etc.).  
  - **Risk:** requires `IServerPlayer` + UI.
- **AI-style:** direct BE methods where possible (quern, trough, farmland).  
  - **Best-fit for bots:** AI-style or custom automation.

### 6) Seats / mounts / rideables
- **Player-style:** `EntityBehaviorSeatable.OnInteract` relies on `EntityPlayer` selection box index and input keys.  
  - **Risk:** often fails for bots.
- **AI-style:** direct mount API (`TryMount`) with explicit seat selection.  
  - **Best-fit for bots:** AI-style (explicit seat selection).

## Current mod status (snapshot)
- **Entity interact (Interact mode):** works on some entities (trader nodding).  
- **Entity attack (Attack mode):** fails for non-`EntityPlayer` (NRE in `EntityAgent.OnInteract`).
- **Block activate:** works with player context, but only opens container for player (not bot inventory transfer).
- **Inventory transfer:** not implemented yet (planned via AI-style inventory ops).

## Open questions
- Confirm `EntitySelection.HitPosition` semantics (relative vs world); see checklist item 1.5.
- Decide where we want player-like behavior vs AI-style automation for each action.
