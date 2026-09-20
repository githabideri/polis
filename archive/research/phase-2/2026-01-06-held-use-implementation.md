# Held-Use Implementation Plan (Phase 2)

**Date:** 2026-01-06  
**Status:** Draft plan

## Purpose
Define how bots should perform held-item use (attack/interact) to match VS engine semantics.

## Known Engine Semantics (vsapi)

**Routing:**
- `Collectible.OnHeldUseStart(...)` routes to `OnHeldAttackStart` or `OnHeldInteractStart` based on `EnumHandInteract`.
- `Collectible.OnHeldUseStep(...)` routes to `OnHeldAttackStep` or `OnHeldInteractStep`.
- `Collectible.OnHeldUseStop(...)` routes to `OnHeldAttackStop` or `OnHeldInteractStop`.

**Interaction vs attack:**
- `EnumHandInteract` values: `None`, `HeldItemAttack`, `HeldItemInteract`, `BlockInteract`.
- `OnHeldInteractStart` receives `firstEvent` (true on initial mouse down, false on subsequent calls).

**Handling flags:**
- `EnumHandHandling` controls default behavior and whether server runs step/stop:
  - `NotHandled` uses default actions and *does not* run step/stop.
  - `Handled` / `PreventDefault*` notify server and allow step/stop.

## Open Questions (Need Verification)
1) How client triggers held-use for blocks vs items (`SystemMouseInWorldInteractions` flow).
2) Whether bots should simulate `BlockInteract` vs `HeldItemInteract` for block use (depends on tool/item).
3) How long `OnHeldUseStep` should tick for timed actions (e.g., quern, pit kiln).

## Proposed Bot Held-Use Flow (Server)

1) **Determine use type**
   - `HeldItemAttack` for attack actions.
   - `HeldItemInteract` for item use.
   - `BlockInteract` when using block (if we emulate block use pipeline).

2) **Start**
   - Call `Collectible.OnHeldUseStart(...)` with `firstEvent = true`.
   - Record returned `EnumHandHandling` to decide whether to continue.

3) **Step**
   - On subsequent ticks, call `OnHeldUseStep(...)` with elapsed time.
   - Stop when it returns `EnumHandInteract.None`.

4) **Stop**
   - Call `OnHeldUseStop(...)` with total elapsed time and final `useType`.

## Implementation Steps (Polis)
1) Add a generic `PolisHeldUseAction` with:
   - Start: `OnHeldUseStart(...)` and set initial state.
   - Step: `OnHeldUseStep(...)` each tick until finished.
   - Stop: `OnHeldUseStop(...)`.
2) Expose via `/polis use` or integrate into task actions (e.g., quern use).
3) Add debug logs: start/step/stop, handling flags, elapsed time.

## References
- `vsapi/Common/Collectible/Collectible.cs`
- `vsapi/Common/Entity/Player/EnumHandHandling.cs`
- `docs/research/phase-2/2026-01-05-vintagestorylib-decompile-notes.md`
