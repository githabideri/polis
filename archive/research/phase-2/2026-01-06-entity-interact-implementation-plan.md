# Entity Interaction Implementation Plan (Phase 2.0.2)

**Date:** 2026-01-06

## Goal
Expose a `/polis interact` command that performs a proper entity interaction using
the ray-traced hit position, and ensure the bot moves into range before interact.

## Implementation Outline
1) Add `/polis interact [mode] [range]`:
   - `mode`: `interact` (default) or `attack`
   - `range`: optional, defaults to `DefaultActionRange`
   - Uses `RayTraceForSelection` to get `EntitySelection` and `HitPosition`.
2) Update `PolisInteractEntityAction`:
   - Accept `hitPos` + `range`.
   - Range check before interacting.
   - Normalize ray hit position to relative if it appears to be world-space; fallback to entity center if missing.
3) Run goto + interact as a sequence:
   - `PolisGotoAction` to the entity’s current server position.
   - `PolisInteractEntityAction` for the actual call.

## Test Plan
- **Right-click action**: interact with a trader/boat/animal using `/polis interact`.
- **Range**: attempt interaction from too far; expect out-of-range failure.
- **Angle**: interact from a side angle and verify it still triggers.

## Notes
- This does not handle container transfer; it only mirrors a player-like interact.
- Some entity interactions may still require player-only context or a valid item slot.

## Status (Validation)
- `/polis interact` on a trader works (visible nodding interaction loop).
- `/polis interact` on a seat does not work (likely requires EntityPlayer selection box or player-only context).
- `/polis interact attack` throws NRE in `EntityAgent.OnInteract` when actor is not `EntityPlayer`, and can suspend server ticks.

## Open Question: HitPosition semantics
- API docs describe `hitPosition` as **relative to the entity hitbox**.
- Our current implementation normalizes the hit position if it appears world-space.
- External research suggests we should pass **relative** coordinates (`worldHitPos - entityPos`).
- **Action:** verify in engine code or a targeted test before changing semantics.
