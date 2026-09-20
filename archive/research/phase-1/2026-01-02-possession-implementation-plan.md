# Possession Implementation Plan (Refined 2026-01-03)

## Overview
Implement a "Puppeteer" system for NPCs using the engine's `IMountable` logic.

## Technical Architecture (Validated via btca)
- **Pattern:** Remote Control via `IMountable`. Player mounts a "seat" at the NPC's eyes.
- **Base Class:** Implement `IMountable` directly on `PolisPossessableBehavior : EntityBehavior`. (Do not inherit `EntityBehaviorRideable` to avoid `vssurvivalmod` dependency issues, though we mimic its logic).
- **Hiding Player:** Use `IMountableSeat.RenderTransform` with a scale of `(0,0,0)` to hide the player. **No Harmony patches required.**
- **Input Routing:** Map player controls to NPC controls in `SeatsToMotion()`, called from `OnGameTick`.

---

## Phase 0.5: Bot Manager Refactor (BUG FIX)
**Goal:** Fix the "Focus Trap" (mouse jumping, Esc ignored) and the "Visual Overlap".
*Status: Validated. Use Client-Authoritative open and full Re-composition.*

---

## Phase 1: Possession Primitive
**Goal:** The "Head Seat" behavior and Input Routing.

### Class Structure
1.  **`PolisPossessableBehavior : EntityBehavior, IMountable`**
    *   **Properties:** `Seats` (array of 1).
    *   **Methods:**
        *   `OnGameTick(float dt)`: Calls `SeatsToMotion(dt)`.
        *   `SeatsToMotion(float dt)`:
            *   Get passenger from seat.
            *   If passenger is player, copy `player.Controls` (WASD, Jump, Sneak) to `entity.Controls`.
            *   Apply `entity.Pos.Yaw` to match player look (or vice-versa).

2.  **`PolisPossessableSeat : IMountableSeat`**
    *   **Property `RenderTransform`**: Return `new Matrixf().Scale(0, 0, 0)` to hide the passenger.
    *   **Property `SeatPosition`**: Return `entity.Pos.XYZ + new Vec3d(0, entity.LocalEyePos.Y, 0)`.

---

## Phase 2: Smooth Control (Refined)
**Goal:** Prediction-based movement.

### Implementation:
- Since we are using `IMountable`, the client prediction *should* work out of the box if `OnGameTick` applies controls on the client side too.
- `vssurvivalmod` uses `OnRenderFrame` for smoother visual updates, but `OnGameTick` is sufficient for Phase 1.

---

## Phase 3: NPC Equipment HUD
**Goal:** Interact with the NPC's inventory.

### Implementation:
- Custom HUD overlay showing NPC hand slots.
- Scroll-wheel intercept to cycle NPC held items.
