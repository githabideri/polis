# HitPosition Quick Reference (Entity Interactions)

**TL;DR:** EntitySelection.HitPosition is **entity-relative**, not world-space. Pass it directly to Entity.OnInteract().

---

## What is HitPosition?

The **exact 3D point where an interaction hit** the entity's collision/selection box, expressed as **an offset from the entity's center position**.

```
World Space:        Entity Position:    HitPosition (Relative):
(485.5, 64.2, 512)  (485.0, 64.0, 512) = (0.5, 0.2, 0.0)
         ↓
      Entity center
                                  Hit point
```

---

## API Contract (vsapi)

```csharp
public virtual void OnInteract(
    EntityAgent byEntity,
    ItemSlot itemslot,
    Vec3d hitPosition,  // ← Entity-relative coordinates
    EnumInteractMode mode
)
```

From documentation:
> "Relative position on the entities hitbox where the entity interacted at"

---

## Usage: Raycast-Based Interactions

When using `RayTraceForSelection`, the HitPosition is **already relative**:

```csharp
// Perform raycast from bot eye
EntitySelection entitySel = null;
world.RayTraceForSelection(rayStart, rayEnd, ref blockSel, ref entitySel);

if (entitySel != null && entitySel.Entity != null) {
    // HitPosition is already relative! Use directly.
    entitySel.Entity.OnInteract(
        bot,                           // byEntity
        bot.ActiveHandItemSlot,        // itemslot
        entitySel.HitPosition,         // Already relative!
        EnumInteractMode.Interact
    );
}
```

---

## Usage: Manual Construction

If you manually construct interaction parameters without ray casting:

```csharp
// Calculate world-space hit point
Vec3d worldHitPos = target.ServerPos.XYZ.AddCopy(0.2, 0.5, 0.0);  // World coords

// Convert to entity-relative
Vec3d relativeHitPos = worldHitPos.SubCopy(target.ServerPos.XYZ);

// Pass to OnInteract
target.OnInteract(actor, slot, relativeHitPos, mode);
```

---

## Why Relative?

**Consistency:** If the entity moves, the interaction behavior stays the same.

- Hit at entity center: `(0, 0, 0)` (always triggers center behavior)
- Hit at head: `(0, 0.8, 0)` (always triggers head behavior, regardless of entity's world position)

This mirrors the block system: HitPosition is relative to block position, not world space.

---

## Common Issues

### ❌ Passing World Coordinates

```csharp
// WRONG: HitPosition should be relative, not world space
target.OnInteract(actor, slot, new Vec3d(485.5, 64.2, 512), mode);
```

### ✅ Convert World to Relative

```csharp
// CORRECT: Convert world coords to entity-relative
var worldHit = new Vec3d(485.5, 64.2, 512);
var relativeHit = worldHit.SubCopy(target.ServerPos.XYZ);
target.OnInteract(actor, slot, relativeHit, mode);
```

### ✅ Use Raycast Results Directly

```csharp
// CORRECT: Raycast results are already relative
world.RayTraceForSelection(rayStart, rayEnd, ref blockSel, ref entitySel);
target.OnInteract(actor, slot, entitySel.HitPosition, mode);
```

---

## Your Code (PolisInteractEntityAction.cs)

Your normalization logic is correct:

```csharp
var useHitPos = NormalizeHitPos(target, hitPos, debugLog) ?? GetDefaultRelativeHitPos(target);
target.OnInteract(agent, slot, useHitPos, mode);
```

**Why it works:**
- If HitPosition came from raycast, it's already relative (passes through)
- If HitPosition is suspected to be world-space, `NormalizeHitPos` subtracts target position (converts to relative)
- Fallback to entity center if HitPosition is missing

---

## Testing Your Implementation

### Test 1: Trader Interaction (Simple)
```
/polis interact <trader-id>
→ Expected: Trader nods, dialog/interaction works
```

### Test 2: Animal Hit Zones (Advanced)
```
/polis interact <animal-id>
→ Hit head → animal reacts as if hit on head
→ Hit body → animal reacts as if hit on body
→ Same interaction point should always produce same reaction
```

### Test 3: Manual vs Raycast (Validation)
```
Raycasted interaction (using RayTraceForSelection):
/polis interact <entity-id>

Manual interaction (constructed hit pos):
/polis manualinteract <entity-id> <x-offset> <y-offset> <z-offset>

→ Both should produce identical behavior
```

---

## Reference

**Source:** vsapi documentation for `Entity.OnInteract`
**btca Query:** `Entity OnInteract method signature hitposition parameters documentation`
**Evidence:** "Relative position on the entities hitbox where the entity interacted at"

For detailed analysis, see: `2026-01-13-hitposition-coordinate-space-resolution.md`
