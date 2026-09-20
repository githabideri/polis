# Follow-up Research Questions

**Date:** 2026-01-04
**Project:** Polis Builder NPC - Vintage Story mod
**Status:** Most questions answered - only btca gaps remain

---

## ✅ Fully Answered by Deep Research

### Multi-Select UI ✅
**Research:** `2026-01-04-ext-multi-select-ui-rendering.md`
- EnumRenderStage.Ortho + Render2DTexture for selection box
- RayTraceForSelection + GetEntitiesAround for picking
- Full implementation sketch provided

### Blueprint/Ghost Blocks ✅
**Research:** `2026-01-04-ext-blueprint-ghost-blocks.md`
- EnumRenderStage.OIT + PreparedStandardShader + ColorMul
- RenderMeshInstanced for batching
- [Beta]Schematica mod as reference

### NPC Survival Integration ✅
**Research:** `2026-01-04-ext-npc-survival-integration.md`
- EntityBehaviorHunger is reusable
- vs-farmlife demonstrates autonomous eating
- reviveondeath for important NPCs

### Performance Budgets ✅
**Research:** `2026-01-04-ext-performance-budgets.md`
- VS runs at ~30 ticks/sec
- Multi-rate architecture: 30Hz/5Hz/0.5Hz
- Central scheduler + token bucket for paths

### Procedural Animation ✅
**Research:** `2026-01-04-ext-procedural-animation-lookat.md`
- EntityPos.HeadYaw/Pitch built-in
- EntityHeadController for bone work

### Task Visualization ✅
**Research:** `2026-01-04-ext-inworld-task-visualization.md`
- Pattern B: IRenderer + Render2DTexture recommended
- HealthBar mods as reference

### IMountable/IMountableSeat ✅
**Research:** `2026-01-04-vintage-story-mounting-analysis.md`
- Complete API documented
- LocalEyePos, RenderTransform, Controls, SeatPosition

---

## 🔍 Remaining Gaps (for btca)

These are VS-specific implementation details not covered by internet research:

### 1. Possession Mount Lifecycle
**Question:** How to programmatically mount a player onto a custom seat? What's the TryMount flow?

### 2. SeatsToMotion Input Routing
**Question:** How does EntityBoat.SeatsToMotion() convert passenger controls to entity movement?

### 3. Mount/Unmount Triggering
**Question:** How to trigger mounting without player right-click interaction?

---

## Notes

- All major design questions are now answered
- Remaining gaps are narrow VS API details
- Can proceed with implementation after btca fills these gaps
