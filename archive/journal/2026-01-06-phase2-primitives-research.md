# Journal: Phase 2 Primitives Research (2026-01-06)

Focus: interaction primitives research and decompile verification for pickup/held-use/container/claims.

## Highlights
- Decompile confirmed entity interaction hit position is passed through unchanged from ray trace (client → packet → server `OnInteract`).
- Pickup/drop plan refined with partial transfer semantics via `TryGiveItemstack`.
- Container transfer patterns validated (slot dirty + block entity dirty; claims use `Use` flag).
- Held-use routing documented (`OnHeldUseStart/Step/Stop`, `EnumHandInteract`, `EnumHandHandling`).

## Artifacts
- `docs/research/phase-2/2026-01-06-pickup-drop-implementation.md`
- `docs/research/phase-2/2026-01-06-held-use-implementation.md`
- `docs/research/phase-2/2026-01-06-container-transfer-implementation.md`
- `docs/research/phase-2/interaction-primitives-checklist.md`
- `docs/research/phase-2/2026-01-05-vintagestorylib-decompile-notes.md`

## Open Threads
- BehaviorCollectEntities not found in decompiled assemblies; collector logic still opaque.
