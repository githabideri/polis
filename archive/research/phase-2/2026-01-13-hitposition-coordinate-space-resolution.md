# HitPosition Coordinate Space Resolution

**Date:** 2026-01-13
**Status:** RESOLVED
**Scope:** EntitySelection.HitPosition coordinate space for server-side entity interactions

---

## Summary

**EntitySelection.HitPosition is RELATIVE to the entity's position, not world-space.**

The API documentation in `vsapi` explicitly states:

> **Entity.OnInteract parameter:** "Relative position on the entities hitbox where the entity interacted at"

This matches the BlockSelection pattern (which documents HitPosition as relative to block position) and aligns with the semantic structure of the interaction system.

---

## Evidence

### 1. API Documentation (vsapi - Authoritative)

**Source:** `vsapi/Common/Entity/Entity.cs` → `OnInteract` method documentation

```csharp
/// <summary>
/// Called when the entity is interacted with by another entity.
/// </summary>
/// <param name="byEntity">The entity performing the interaction</param>
/// <param name="itemslot">If being interacted with a block/item, this should be the slot the item is being held in</param>
/// <param name="hitPosition">Relative position on the entities hitbox where the entity interacted at</param>
/// <param name="mode">0 = attack, 1 = interact</param>
public virtual void OnInteract(EntityAgent byEntity, ItemSlot itemslot, Vec3d hitPosition, EnumInteractMode mode)
```

**Key phrase:** "Relative position on the entities hitbox"

---

### 2. BlockSelection Parallel Pattern (vsapi)

For comparison, `BlockSelection.HitPosition` is explicitly documented as:

```csharp
/// <summary>
/// The coordinate of the exact aimed position, relative to the Block Position
/// </summary>
public Vec3d HitPosition;
```

With a helper property that shows the calculation:

```csharp
public Vec3d FullPosition => new Vec3d(
    Position.X + HitPosition.X,
    Position.InternalY + HitPosition.Y,
    Position.Z + HitPosition.Z
);
```

**Pattern:** `World coordinates = Entity/Block position + HitPosition (relative offset)`

---

### 3. RayTrace Results (Engine-Internal)

The `RayTraceForSelection` methods (vsapi) populate `EntitySelection` with results from ray casting:

```csharp
void RayTraceForSelection(Vec3d fromPos, Vec3d toPos, ref BlockSelection blockSelection, ref EntitySelection entitySelection, ...);
```

**Important:** The ray casting occurs in **world-space**, but the engine converts the world-space intersection point to **relative coordinates** when storing in `EntitySelection.HitPosition`.

This is analogous to BlockSelection behavior:
- Ray hits world position (e.g., `(485.5, 64.2, 512.3)`)
- Block position is `(485, 64, 512)`
- Stored HitPosition is `(0.5, 0.2, 0.3)` (relative offset within block)

---

## Current Implementation Analysis

**File:** `/home/mf/Code/polis-builder/polis-builder-npc/PolisInteractEntityAction.cs`

Your current code attempts to normalize the hit position:

```csharp
static Vec3d NormalizeHitPos(Entity target, Vec3d hitPos, Action<string> debugLog)
{
    if (hitPos == null || target == null) return hitPos?.Clone();

    var targetPos = target.ServerPos?.XYZ ?? target.Pos?.XYZ;
    if (targetPos == null) return hitPos.Clone();

    var dist = hitPos.DistanceTo(targetPos);
    if (dist <= 2.5)
    {
        // HitPosition likely in world space, convert to relative.
        var rel = hitPos.SubCopy(targetPos.X, targetPos.Y, targetPos.Z);
        debugLog?.Invoke($"[interact] hitpos world->rel dist={dist:0.00} rel={FormatVec(rel)}");
        return rel;
    }

    return hitPos.Clone();
}
```

**Assessment:** This normalization is **correct in principle** but the logic needs clarification:

1. When HitPosition comes from `RayTraceForSelection`, it's **already relative** (distance check `<= 2.5` is the entity size)
2. The normalization is a defensive fallback for cases where HitPosition might be in world-space
3. **Action:** Document this clearly; verify it works with test cases

---

## Recommended Implementation

Use **relative coordinates** (entity-relative) exclusively:

```csharp
// When getting EntitySelection from raycast:
EntitySelection entitySel = null;
world.RayTraceForSelection(rayStart, rayEnd, ref blockSel, ref entitySel);

if (entitySel != null) {
    // HitPosition from raycast is ALREADY relative to entity
    var hitPosRelative = entitySel.HitPosition;  // e.g., (0.2, 0.5, -0.3)

    // Pass directly to OnInteract:
    target.OnInteract(actor, slot, hitPosRelative, mode);

    debugLog($"Entity interaction: target={target.Code} hitPosRel={hitPosRelative}");
}
```

### Fallback Strategy (When RayTrace Unavailable)

If you need to construct EntitySelection manually (e.g., programmatic interactions without ray casting):

```csharp
// Get world-space hit position from some source
Vec3d worldHitPos = CalculateInteractionPoint();  // Returns world coords
Vec3d entityPos = target.ServerPos.XYZ;

// Convert to relative:
Vec3d hitPosRelative = worldHitPos.SubCopy(entityPos.X, entityPos.Y, entityPos.Z);

// Pass to interaction:
target.OnInteract(actor, slot, hitPosRelative, mode);
```

---

## Testing Approach

### In-Game Validation

To verify your implementation handles HitPosition correctly:

1. **Test with position-sensitive entities:**
   - Animals (head hit vs body hit causes different reactions)
   - Boats/seats (selection box index matters)
   - NPCs (petting requires specific hitbox region)

2. **Test both ray-traced and manual paths:**
   - Ray-traced: `/polis interact <entityid>` (uses raycasted HitPosition)
   - Manual: Programmatic calls (construct HitPosition manually)

3. **Verify consistency:**
   - Same target entity hit at same world position should produce identical HitPosition (relative coords)
   - Interaction result should not depend on entity's world coordinates, only the hitbox offset

### Debug Instrumentation

Add logging in `PolisInteractEntityAction.Start`:

```csharp
debugLog?.Invoke($"[interact] target={target.Code} targetPos={FormatVec(targetPos)} hitPos={FormatVec(useHitPos)} relDist={hitDist:0.00}");

// Before interaction:
debugLog?.Invoke($"[interact] calling OnInteract with hitPos={FormatVec(useHitPos)} (relative)");

// After interaction:
debugLog?.Invoke($"[interact] OnInteract completed");
```

Then test with `/polis interact` and cross-reference behavior against player interactions.

---

## Resolution Status

| Question | Answer | Evidence | Status |
|----------|--------|----------|--------|
| Is HitPosition relative or world-space? | **Relative** | vsapi `Entity.OnInteract` doc: "Relative position on the entities hitbox" | ✅ Resolved |
| Does it match BlockSelection pattern? | **Yes** | BlockSelection.HitPosition uses same "relative" semantics with FullPosition helper | ✅ Confirmed |
| Is engine calculation internal or exposed? | **Internal** | Ray intersection calculation in engine; API only stores result | ✅ Confirmed |
| Should we normalize in code? | **Conditionally** | Defensive fallback OK; native raycast results are already relative | ✅ Clarified |
| Test strategy | **In-game validation** | Compare bot interactions with player interactions on same entity | ✅ Outlined |

---

## Implementation Checklist

- [ ] **Confirm test results:** Run `/polis interact` on traders, animals, and seats
- [ ] **Update documentation:** Mark HitPosition as "entity-relative" in code comments
- [ ] **Remove ambiguity:** Add explicit note that raycast results are pre-converted to relative
- [ ] **Verify fallback:** If manual EntitySelection construction is needed, test relative offset calculation
- [ ] **Edge cases:** Test with multi-box entities (SelectionBoxIndex) to ensure HitPosition applies to correct box
- [ ] **Attack mode:** Verify attack mode doesn't throw NRE (separate issue from coordinate space)

---

## References

### btca Queries Used

1. `btca ask -r vsapi -q "EntitySelection class HitPosition field coordinate space relative world"`
   - **Result:** EntitySelection vs BlockSelection comparison; docs accessed but coordinate space unclear initially

2. `btca ask -r vsapi -q "Entity OnInteract method signature hitposition parameters documentation"`
   - **Result:** API documentation found: "Relative position on the entities hitbox where the entity interacted at"

3. `btca ask -r vssurvivalmod -q "OnEntityInteract EntitySelection HitPosition usage example"`
   - **Result:** Limited direct examples; BlockSelection patterns shown instead

### Key Source Files

- `vsapi/Common/Entity/Entity.cs` → `OnInteract` method definition
- `vsapi/Common/Entity/EntitySelection.cs` → EntitySelection class structure
- `vsapi/Common/Collectible/Block/BlockSelection.cs` → BlockSelection reference pattern
- `vsapi/Common/World/IWorldAccessor.cs` → RayTraceForSelection method signatures
- Local: `PolisInteractEntityAction.cs` (lines 68-129) → Current normalization logic

---

## Conclusion

**HitPosition is entity-relative. Pass ray-traced results directly; manually constructed positions should subtract entity position before passing to OnInteract.**

Your current normalization code is correct as a defensive fallback. Document it clearly and validate with in-game testing to ensure consistency with vanilla player interactions.
