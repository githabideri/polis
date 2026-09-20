# NPC Physics & Behavior Investigation

**Date:** 2026-01-06
**Researcher:** Codex
**Task:** TASK-npc-physics-investigation.md

---

## Summary

The NPC being possessed is the Survival mod `playerbot` entity (`survival:playerbot`, class `EntityPlayerBot`), which inherits from `EntityAnimalBot` (and ultimately `EntityAgent`). Its entity JSON explicitly adds `controlledphysics` and `interpolateposition` behaviors on both client and server. This means movement is governed by `EntityBehaviorControlledPhysics`, not player-specific physics modules, and there is no `EntityBehaviorRideable` present by default. On the server, `UpdatePossessions()` writes to `npc.ServerControls` and calls `CalcMovementVectors`, and those controls are consumed by `EntityBehaviorControlledPhysics.OnPhysicsTick()` (which uses `EntityAgent.Controls`, aliased to server controls on the server). On the client, however, `PredictNpcMovement()` directly sets `possessedNpc.Pos.Motion` to the computed WalkVector, bypassing the controlled physics pipeline and fighting `EntityBehaviorInterpolatePosition`’s interpolation.

---

## Investigation Step 1: NPC Entity Type

### Findings
- **Entity Class:** `Vintagestory.GameContent.EntityPlayerBot`
- **Entity Code:** `survival:playerbot`
- **Entity Properties:** `assets/survival/entities/humanoid/playerbot.json` (class: `EntityPlayerBot`)

### Evidence
- `polis-builder-npc/PolisBuilderNpcSystem.cs` (DefaultBotCode and spawn path)
- `docs/vssurvivalmod/Entities/EntityPlayerBot.cs`
- `~/.local/share/flatpak/app/at.vintagestory.VintageStory/x86_64/stable/active/files/extra/vintagestory/assets/survival/entities/humanoid/playerbot.json`

---

## Investigation Step 2: Entity Behaviors

### Findings
- **All Behaviors (server):** `repulseagents`, `nametag`, `controlledphysics`, `collectitems`, `health`, `breathe`, `extraskinnable`, `seraphinventory`, `nametag`
- **All Behaviors (client):** `repulseagents`, `nametag`, `controlledphysics`, `interpolateposition`, `aimingaccuracy`, `extraskinnable`, `seraphinventory`, `nametag`
- **Physics Behaviors:** `controlledphysics` (EntityBehaviorControlledPhysics) and `interpolateposition` (EntityBehaviorInterpolatePosition on client)
- **Rideable Behavior:** Not present in playerbot JSON; no `EntityBehaviorRideable` listed

### Evidence
- `~/.local/share/flatpak/app/at.vintagestory.VintageStory/x86_64/stable/active/files/extra/vintagestory/assets/survival/entities/humanoid/playerbot.json` (client/server behaviors arrays)
- `vsessentialsmod/Entity/Behavior/BehaviorControlledPhysics.cs` (registered for `controlledphysics`)
- `vsessentialsmod/Entity/Behavior/BehaviorInterpolatePosition.cs` (registered for `interpolateposition`)

### Analysis
The NPC uses `EntityBehaviorControlledPhysics` (generic physics modules) rather than `EntityBehaviorPlayerPhysics` (player-specific modules), so movement feel may differ in air/liquid states. No evidence of rideable behavior is present in the entity definition; mount-style gait/tilt is unlikely to be coming from `EntityBehaviorRideable` for this entity.

---

## Investigation Step 3: WalkVector Consumption

### Findings
- **Where WalkVector is read:** `EntityBehaviorControlledPhysics.MotionAndCollision()` applies physics modules that read `controls.WalkVector`.
- **Where Motion is updated:** `EntityBehaviorControlledPhysics` applies PModules (OnGround/InLiquid/InAir/Gravity/MotionDrag/Knockback), which update `pos.Motion` and perform collision.
- **Automatic vs Explicit:** Automatic via physics tick (`EntityBehaviorControlledPhysics.OnPhysicsTick`) when the entity is active.

### Evidence
- `polis-builder-npc/PolisBuilderNpcSystem.cs` (`UpdatePossessions()` writes `npc.ServerControls` and calls `CalcMovementVectors`)
- `vsessentialsmod/Entity/Behavior/BehaviorControlledPhysics.cs` (`OnPhysicsTick` → `MotionAndCollision` → `PModule.DoApply`)
- `vsessentialsmod/Entity/Behavior/BehaviorControlledPhysics.cs` (`MotionAndCollision` uses `EntityAgent.Controls`)
- `vsapi/Common/Entity/EntityAgent.cs` (server sets `servercontrols = controls` in `Initialize`)

### Analysis
On the server, `npc.ServerControls` and `npc.Controls` reference the same object (server assigns `servercontrols = controls`), so `UpdatePossessions()` effectively feeds the physics pipeline. The physics pipeline should therefore consume the WalkVector unless movement is short-circuited by other logic (e.g., mounted entity handling).

---

## Investigation Step 4: Mount Angle Mode

### Findings
- **Angle Mode Setting:** `EnumMountAngleMode.Unaffected`
- **Is it respected?:** No runtime verification (no diagnostics run)
- **Yaw behavior:** Server explicitly sets NPC yaw to player yaw each tick in `UpdatePossessions()`

### Evidence
- `polis-builder-npc/PolisPossessableSeat.cs` (AngleMode)
- `polis-builder-npc/PolisBuilderNpcSystem.cs` (server yaw lock in `UpdatePossessions()`)

---

## Investigation Step 5: Gait/Seat Motion

### Findings
- **SeatsToMotion calls:** No evidence in playerbot entity setup; no rideable behavior in JSON.
- **Gait system active:** Unlikely for `playerbot` entity.
- **Mount motion override:** Not detected in entity definition; mount system used only for seat controls.

### Evidence
- `playerbot.json` behaviors (no rideable behavior)
- `vsessentialsmod/Entity/Behavior/BehaviorControlledPhysics.cs` (mountableSupplier only affects passengers/mounted entities)

---

## Conclusions

### Physics Pipeline Identified
1. **Server:** `PolisBuilderNpcSystem.UpdatePossessions()` copies seat controls → `npc.ServerControls`, then `CalcMovementVectors()`.
2. **Server physics:** `EntityBehaviorControlledPhysics.OnPhysicsTick()` reads `EntityAgent.Controls` (same as server controls) → applies PModules → updates `ServerPos.Motion`/collisions.
3. **Client rendering:** `EntityBehaviorInterpolatePosition` lerps server positions and uses an `IRemotePhysics` behavior (controlledphysics) for motion updates.
4. **Client prediction (current code):** `PredictNpcMovement()` computes WalkVector and directly sets `possessedNpc.Pos.Motion`, bypassing controlledphysics modules.

### Root Cause Confirmed/Refined
- There is **no rideable behavior** on the playerbot entity; mount/gait motion likely isn’t the source of the horse-like feel.
- The **client prediction path bypasses physics** by directly setting motion to WalkVector. This likely produces smooth, continuous motion and conflicts with interpolation.
- NPC physics uses **generic controlled physics** (PModuleInAir/PModuleInLiquid) rather than player-specific modules; this may contribute to feel differences but not the “mount tilt.”

### Player Physics vs NPC Physics
- Player entities use `EntityBehaviorPlayerPhysics` with `PModulePlayerInAir` and `PModulePlayerInLiquid`.
- Playerbot uses `EntityBehaviorControlledPhysics` with `PModuleInAir` and `PModuleInLiquid` (generic).
- Ground movement modules appear shared, but air/liquid and input handling differ.

---

## Recommendations

### Option A: Manual Physics Implementation
**Description:** Reimplement player-like movement by applying drag/accel manually after `CalcMovementVectors`.
**Feasibility:** Medium (known math, but risk of edge cases)
**Complexity:** Medium
**Reasoning:** Avoids fighting interpolation and avoids reliance on existing physics modules during possession.

### Option B: Use NPC Physics Modules
**Description:** Use the existing `EntityBehaviorControlledPhysics` pipeline for both server and client prediction instead of direct `Pos.Motion` writes.
**Feasibility:** High on server, Medium on client
**Complexity:** Medium
**Reasoning:** ControlledPhysics already consumes `WalkVector`; prediction should respect its drag/accel to match server motion.

### Option C: Disable Mount Physics
**Description:** Ensure no rideable behavior is used during possession.
**Feasibility:** Already true for `playerbot`
**Complexity:** Low
**Reasoning:** Evidence indicates rideable behavior is not present; unlikely to be the root cause.

### Recommended Approach
Option B is the best fit to current evidence: keep `controlledphysics` as the movement pipeline and remove the client-side direct motion assignment. If prediction remains necessary, simulate the same PModule pipeline or let interpolation handle it without prediction.

---

## Code References

**Files examined:**
- `polis-builder-npc/PolisBuilderNpcSystem.cs`
- `polis-builder-npc/PolisClientPossessionHandler.cs`
- `polis-builder-npc/PolisPossessableSeat.cs`
- `docs/vssurvivalmod/Entities/EntityPlayerBot.cs`
- `docs/vssurvivalmod/Entities/EntityAnimalBot.cs`
- `vsessentialsmod/Entity/Behavior/BehaviorControlledPhysics.cs`
- `vsessentialsmod/Entity/Behavior/BehaviorInterpolatePosition.cs`
- `vsapi/Common/Entity/EntityAgent.cs`
- `~/.local/share/flatpak/app/at.vintagestory.VintageStory/x86_64/stable/active/files/extra/vintagestory/assets/survival/entities/humanoid/playerbot.json`

**Key code locations:**
- Entity type resolution: `polis-builder-npc/PolisBuilderNpcSystem.cs:764` (spawn), `polis-builder-npc/PolisBuilderNpcSystem.cs:1965` (resolve)
- Behavior registration: `vsessentialsmod/Core.cs:148` (controlledphysics), `vsessentialsmod/Core.cs:152` (interpolateposition)
- Physics tick: `vsessentialsmod/Entity/Behavior/BehaviorControlledPhysics.cs:493`
- Motion update pipeline: `vsessentialsmod/Entity/Behavior/BehaviorControlledPhysics.cs:247`

---

## Diagnostic Code Added

No diagnostic logging was added in this pass (research-only per instruction). If needed, here are the proposed snippets:

```csharp
// In PolisBuilderNpcSystem.cs:UpdatePossessions() after npc assignment
sapi.Logger.Notification($"[polis-diag] NPC Entity Type: {npc?.GetType().FullName}");
sapi.Logger.Notification($"[polis-diag] NPC Code: {npc?.Code}");
sapi.Logger.Notification($"[polis-diag] NPC Properties.Code: {npc?.Properties?.Code}");

if (npc?.SidedProperties?.Behaviors != null)
{
    sapi.Logger.Notification("[polis-diag] NPC Behaviors:");
    foreach (var behavior in npc.SidedProperties.Behaviors)
    {
        sapi.Logger.Notification($"  - {behavior.GetType().FullName}");
    }
}

var rideableBehavior = npc?.GetBehavior<EntityBehaviorRideable>();
sapi.Logger.Notification($"[polis-diag] Has EntityBehaviorRideable: {rideableBehavior != null}");

var physicsBehavior = npc?.GetBehavior("controlledphysics");
sapi.Logger.Notification($"[polis-diag] Has ControlledPhysics: {physicsBehavior != null}");

sapi.Logger.Notification($"[polis-diag] Before: Motion=({npc.ServerPos.Motion.X:F3},{npc.ServerPos.Motion.Z:F3})");
sapi.Logger.Notification($"[polis-diag] WalkVector=({npcControls.WalkVector.X:F3},{npcControls.WalkVector.Z:F3})");
```

---

## Testing Notes

No in-game testing performed in this investigation (research-only). Expected log verification steps:
- Possess a bot, observe behavior list and confirm `controlledphysics` / `interpolateposition` presence.
- Confirm `EntityBehaviorRideable` is absent.
- Compare motion deltas before/after physics tick using log timestamps.

---

## Open Questions

- How closely does `EntityBehaviorControlledPhysics` ground movement match player ground movement for `playerbot` in practice?
- Does client-side interpolation alone (without prediction) feel responsive enough for possession?
- Are there any hidden engine-side behaviors attached to `EntityPlayerBot` that modify `WalkVector` or motion outside ControlledPhysics?

---

## Verification Needed (Why These Conclusions Are Likely, Not Final)

### Why the Conclusions Are Strongly Supported
- **No rideable behavior on playerbot:** `playerbot.json` contains `controlledphysics` and `interpolateposition`, and does not list `rideable`.
- **Server physics consumes possession input:** `UpdatePossessions()` writes to `npc.ServerControls`, and `EntityBehaviorControlledPhysics.OnPhysicsTick()` reads `EntityAgent.Controls` (server assigns `servercontrols = controls`).
- **Client prediction bypasses physics:** `PredictNpcMovement()` sets `possessedNpc.Pos.Motion` directly, skipping controlled physics and competing with interpolation.

### What Still Needs Runtime Confirmation
- **Behavior list at runtime:** confirm no injected `EntityBehaviorRideable` or other unexpected behaviors.
- **Client motion authority:** confirm interpolation drives motion when direct motion writes are removed.
- **Movement feel:** verify whether controlled physics vs player physics modules are the primary cause of “horse-like” feel.

### Minimal Verification Steps
1. Log `npc.SidedProperties.Behaviors` during possession to confirm active behaviors.
2. Temporarily disable direct `Pos.Motion` writes in `PredictNpcMovement()` and compare feel.
3. Log `WalkVector` and `Pos.Motion` deltas before/after physics ticks to validate motion source.
