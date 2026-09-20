# Entity Interaction Constraints (Player-Only Assumptions)

**Date:** 2026-01-06  
**Scope:** Identify interaction paths that assume `EntityPlayer`/`IPlayer` or player input state.

## Summary
Many entity interactions are coded with explicit `EntityPlayer` checks or depend on player-only inputs (selection box index, control keys, right-click hold). This means a generic `EntityAgent` (including `EntityPlayerBot`) may not be sufficient unless it exposes a player context or we simulate the missing inputs.

## Core API: Player assumptions in attack path
**vsapi** `Common/Entity/EntityAgent.cs` → `OnInteract(..., EnumInteractMode.Attack)`  
**Server call chain (engine):** `ServerSystemEntitySimulation.HandleEntityInteraction(...)` → `EntityAgent.OnInteract(...)` → `Entity.ReceiveDamage(...)`.  
- Damage source classification reads `EntityPlayer.Player` without a null check:
  - `Source = (byEntity as EntityPlayer).Player == null ? EnumDamageSource.Entity : EnumDamageSource.Player`
- This path assumes the attacker can be cast to `EntityPlayer`; otherwise it can throw `NullReferenceException`.

## Entity behaviors requiring `EntityPlayer` or player input

### Petting (player input state)
**vssurvivalmod** `Entity/Behavior/BehaviorPettable.cs`  
- Requires `byEntity is EntityPlayer` and `byEntity.Controls.RightMouseDown`:
  - `if (byEntity is EntityPlayer && byEntity.Controls.RightMouseDown && byEntity.RightHandItemSlot.Empty ...) { ... }`
- Bot interactions that do not set `Controls.RightMouseDown` will not trigger petting.

### Conversational / dialog interactions
**vssurvivalmod** `Systems/Dialogue/BehaviorConversable.cs`  
- Early exit if not `EntityPlayer`:
  - `if (mode != EnumInteractMode.Interact || !(byEntity is EntityPlayer)) { ... return; }`
- Uses `IServerPlayer` to open/close dialogs and send packets.

### Seats / mounts (selection box index + control keys)
**vssurvivalmod** `Systems/Boats/EntityBehaviorSeatable.cs`  
- Reads selection box index from `EntityPlayer`:
  - `int seleBox = (byEntity as EntityPlayer).EntitySelection?.SelectionBoxIndex ?? -1;`
- Checks `byEntity.Controls.CtrlKey` and selection boxes to decide mounting.
- Without `EntityPlayer.EntitySelection`, bots cannot target a seat box.

## Implications
- Many interactions implicitly require `EntityPlayer` context and/or live input state.
- A pure `EntityAgent` implementation will miss:
  - `IPlayer`/`IServerPlayer` for UI-driven behaviors.
  - Selection box indices (from player selection).
  - Input state (RightMouseDown, CtrlKey, ShiftKey).

## Compatibility tiers (draft)
These tiers are a planning aid; entries are based on code inspection so far and will be
validated with the manual test matrix later.

| Interaction/Behavior | Tier | Evidence | Notes |
| --- | --- | --- | --- |
| Entity attack via `EntityAgent.OnInteract(Attack)` | Player-only | `vsapi/Common/Entity/EntityAgent.cs` | NRE when `byEntity` is not `EntityPlayer` (uses `EntityPlayer.Player` without null guard). |
| Conversable entities (dialog) | Player-only | `docs/vssurvivalmod/Systems/Dialogue/BehaviorConversable.cs` | Explicit `byEntity is EntityPlayer` check; uses `IServerPlayer` for dialogs. |
| Seats/mounts (`EntityBehaviorSeatable`) | Player-biased | `docs/vssurvivalmod/Systems/Boats/EntityBehaviorSeatable.cs` | Uses `EntityPlayer.EntitySelection.SelectionBoxIndex` + input keys. |
| Petting (`EntityBehaviorPettable`) | Player-biased | `docs/vssurvivalmod/Entity/Behavior/BehaviorPettable.cs` | Requires `EntityPlayer` + `Controls.RightMouseDown`. |
| Generic `OnInteract(Interact)` | Unknown | - | Many entities may be agent-safe, but several behaviors are player-only. |

## Open Questions
- Whether to keep `EntityPlayerBot` (for closer parity with `EntityPlayer`) or create a custom entity and simulate only what we need.
- How to supply/override player input state for bot-triggered interactions without patching core behaviors.
