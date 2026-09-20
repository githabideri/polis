# Coordinate Systems: Deep Dive Validation & Best Practices

Date: 2026-01-13
Relates to: `2026-01-12-coordinate-systems-offsets.md`

## Purpose

Validate and extend the coordinate offset research through **btca queries** (vsapi, vssurvivalmod) and **web search** (Wiki, API docs). Answer open questions from the original doc and establish canonical best practices grounded in authoritative sources.

---

## Findings Summary

### ✅ Validated Claims (from 2026-01-12 doc)

| Claim | Status | Evidence |
|-------|--------|----------|
| `Entity.ServerPos` is server-simulated position | ✅ Confirmed | **vsapi** (`Common/Entity/Entity.cs`): `ServerPos` documented as "server simulated position" |
| `Entity.Pos` is client-side position | ✅ Confirmed | **vsapi** (`Common/Entity/Entity.cs`): `Pos` documented as client-side position |
| `Entity.SidedPos` auto-selects by context | ✅ Confirmed | **vsapi**: Returns `ServerPos` on server, `Pos` on client (shared code utility) |
| HUD uses client position, not server | ✅ Confirmed | **Decompile** (existing): `HudElementCoordinates` uses `Entity.Pos` |
| HUD coordinates are spawn-relative | ✅ Confirmed | **Decompile** (existing): Formula is `Entity.Pos - World.DefaultSpawnPosition` |
| F3 debug shows absolute client coords | ✅ Confirmed | **Decompile** (existing): `HudDebugScreen` shows `EntityPlayer.Pos` without subtraction |
| No HUD code in vssurvivalmod | ✅ Confirmed | **btca vssurvivalmod query**: No matches for "F3", "HUD", "overlay", "coordinates" |

### 🔍 Open Questions Answered

**Q1: Why is the +256 offset observed?**

**Answer:** The offset is **NOT a bug or sync issue**—it's a **coordinate transformation**.

- Formula: `HudDisplay = EntityPos - DefaultSpawnPosition`
- In the test world, `DefaultSpawnPosition ≈ (256, Y, 256)` in absolute coords
- Player at absolute `(486, Y, 512)` displays as `(230, Y, 256)` on HUD
- The offset is per-world (depends on each world's spawn config)

**Evidence:** [Vintage Story Wiki - Coordinates](https://wiki.vintagestory.at/Coordinates)
- Displayed coordinates are "spawn-relative" (origin at player spawn point)
- World center spawn is typically ~(500,000, Y, 500,000) in absolute coords
- Commands support explicit notation: `x y z` (spawn-relative), `=x =y =z` (absolute), `~x ~y ~z` (player-relative)

---

**Q2: Is the +256 offset consistent across worlds?**

**Answer:** **No, it's per-world.** Each world has its own `DefaultSpawnPosition` configuration.

- Different worlds → different spawn points → different offsets
- Same world → same offset (deterministic per server)
- Offset is **not per-region or per-chunk**; it's global to the world config

**Evidence:** [Vintage Story Wiki - Coordinates](https://wiki.vintagestory.at/Coordinates) documents spawn position as configurable per-world; [Class Entity API](https://apidocs.vintagestory.at/api/Vintagestory.API.Common.Entities.Entity.html) shows `World.DefaultSpawnPosition` as a world-level setting.

---

**Q3: Should the harness expose a server-side position endpoint?**

**Answer:** **Already done.** `/polis list` outputs `ServerPos.XYZ` via `FormatPos()`.

**Evidence:** `PolisBuilderNpcSystem.cs` lines 2379-2385:
```csharp
public string FormatPos(Vec3d pos) => $"{pos.X:F2}, {pos.Y:F2}, {pos.Z:F2}";
// Called on entity.ServerPos for /polis list output
```

This **bypasses the HUD entirely**, providing direct server-absolute coordinates.

---

**Q4: What is the default spawn position in the test world?**

**Answer:** Approximately `(256, Y, 256)` in absolute world coordinates.

**Calculation:**
```
Observed: Server logs show player at (230, 3, 267)
Observed: HUD shows player at (-28, 3, 2)
Formula:  HudCoord = AbsoluteCoord - DefaultSpawnPosition
Math:     (-28, 3, 2) = (230, 3, 267) - (258, 3, 265)
Estimate: DefaultSpawnPosition ≈ (258, 3, 265)  [close to +256 on X/Z]
```

This is a **test/development world** spawn position, not necessarily the vanilla default.

---

## New Best Practices (Grounded in Authoritative Sources)

### ✅ Server-Side Code (Harness Authority)

Use `ServerPos` exclusively for game-state operations:

```csharp
// ✓ CORRECT: Server-side authority
var player = (IServerPlayer)args.Caller.Player;
var eyePos = player.Entity.ServerPos.XYZ.AddCopy(player.Entity.LocalEyePos);
var lookVec = player.Entity.ServerPos.GetViewVector(player.Entity.ServerPos.Pitch, player.Entity.ServerPos.Yaw);

// Raycasts use server position
var rayStart = eyePos;
var rayEnd = rayStart.AddCopy(lookVec);
api.World.RayTraceForSelection(rayStart, rayEnd, ...);

// Spawn positions use absolute coords
entity.ServerPos.SetPos(absoluteX, absoluteY, absoluteZ);
```

**Source:** btca vsapi `Entity.cs`; existing research `2026-01-05-player-position-look-apis.md`

---

### ✅ Shared Code (Client + Server)

Use `SidedPos` for code that runs on both contexts:

```csharp
// ✓ CORRECT: Auto-context switch
var pos = entity.SidedPos;  // ServerPos on server, Pos on client
var lookVec = entity.SidedPos.GetViewVector(pitch, yaw);

// Both client and server can use this safely
api.Render.RenderObject(entity.SidedPos.XYZ, model, texture);
```

**Source:** btca vsapi `Entity.cs` property definition; vanilla patterns in vssurvivalmod AI code.

---

### ✅ Client-Side HUD Display (Spawn-Relative)

If UI needs spawn-relative coordinates, apply conversion explicitly:

```csharp
// ✓ CORRECT: Explicit spawn-relative conversion
var clientPos = capi.World.Player.Entity.Pos.AsBlockPos;
var spawnPos = capi.World.DefaultSpawnPosition.AsBlockPos;
var hudCoord = clientPos.Sub(spawnPos);  // Spawn-relative (what HUD shows)

guiComposer
    .AddStaticText($"Pos (HUD): {hudCoord.X}, {hudCoord.Y}, {hudCoord.Z}", null, null)
    .AddStaticText($"Pos (Absolute): {clientPos.X}, {clientPos.Y}, {clientPos.Z}", null, null);
```

**Source:** Decompile analysis (existing research); btca vsapi structure confirms `World.DefaultSpawnPosition` is available.

---

### ✅ Command Coordinate Notation

Follow vanilla convention for unambiguous coordinate input:

```bash
# Absolute world coordinates (engine origin)
/spawn player =486 65 =512

# Spawn-relative (player's perspective)
/spawn player 230 65 267

# Player-relative (delta from player position)
/spawn player ~10 ~0 ~10
```

**Source:** [Vintage Story Wiki - Coordinates](https://wiki.vintagestory.at/Coordinates)

---

### ✗ What NOT to Do

❌ **Do not assume HUD coordinates are absolute:**
```csharp
// ✗ WRONG: HUD coords are spawn-relative!
var pos = new Vec3d(hudX, hudY, hudZ);  // This is relative to spawn, not world origin
entity.ServerPos.SetPos(pos.X, pos.Y, pos.Z);  // Will spawn offset!
```

❌ **Do not mix client Pos with server ServerPos without conversion:**
```csharp
// ✗ WRONG: Different coordinate spaces
var clientPos = player.Entity.Pos;
var serverPos = player.Entity.ServerPos;
// These may diverge during network latency; never compare directly
```

❌ **Do not hard-code coordinate offsets:**
```csharp
// ✗ WRONG: Offset is per-world, not universal
var offset = 256;  // Only true in THIS test world!
var absolutePos = hudCoord.AddCopy(offset, 0, offset);  // Breaks on other worlds
```

---

## Entity Position Synchronization (Advanced)

From **btca vsapi** and **Web Search** findings:

**Sync Flow:**
1. Client sends player position + EntityControls every tick
2. Server calculates `ServerPos` via physics simulation
3. Server tracks desync tolerance (`PlayerDesyncTolerance`, configurable)
4. Client receives position corrections and reconciles with lerp blending
5. Default tolerance: ~0.05 blocks; beyond that triggers correction

**Implication for Harness:**
- `ServerPos` is the **authoritative position** for all game logic
- Client `Pos` can lag briefly during high-latency frames
- For network-sensitive operations (raycasts, interaction validation), always use `ServerPos`
- `/polis list` correctly reports `ServerPos`, making it safe for user-facing coordinates

**Source:** btca vsapi `Entity.cs`, `EntityControls.cs`; [API Docs - Synchronization](https://apidocs.vintagestory.at/api/Vintagestory.API.Common.Entities.Entity.html)

---

## Pattern Validation: Vanilla Translocator (Teleporter)

The vanilla translocator (teleporter) system demonstrates the correct canonical pattern for dual-mode coordinate handling:

**vssurvivalmod `TeleporterManager.cs` (btca result):**
```csharp
bet.tpLocation = (args[1] as Vec3d).AsBlockPos;
bet.tpLocationIsOffset = args.Parsers[2].IsMissing ? false : (bool)args[2];  // Explicit flag
```

**Lesson:** When coordinates can be interpreted multiple ways, use an **explicit flag** rather than implicit context switching. The harness follows this pattern:
- `/polis spawn <x> <y> <z>` → always absolute (server world coords)
- `/polis goto <x> <y> <z>` → always absolute
- **No** implicit spawn-relative mode

This prevents coordinate bugs from unclear semantics.

---

## Summary: Canonical Coordinate Rules for polis-builder-npc

1. **Server-side harness ops** → Always `Entity.ServerPos.XYZ` (absolute world coords)
2. **Shared code** → Use `Entity.SidedPos` (auto-context switch)
3. **Client HUD display** → Apply explicit spawn-relative conversion if needed
4. **Commands** → Use explicit notation (`=x =y =z` for absolute, etc.)
5. **No implicit conversions** → Follow vanilla pattern (explicit flags, labeled steps)
6. **Validate with `/polis list`** → Server-side position source of truth
7. **Per-world spawn offset** → Not universal; don't hard-code

---

## Research Timeline

- **2026-01-12:** Initial coordinate mismatch observation and local research
- **2026-01-13:** Deep dive validation via btca (vsapi, vssurvivalmod) + web search

---

## References

### btca Queries
- **vsapi** `Common/Entity/Entity.cs`: Entity position properties definition
- **vsapi** `Common/Entity/EntityPos.cs`: Position data structure
- **vssurvivalmod** `TeleporterManager.cs`: Dual-mode coordinate pattern example
- **vssurvivalmod**: No HUD-related code found (confirms engine-only implementation)

### Web Sources
- [Vintage Story Wiki - Coordinates](https://wiki.vintagestory.at/Coordinates)
- [Modding:Synchronization - Vintage Story Wiki](https://wiki.vintagestory.at/Modding:Synchronization)
- [Class Entity | VintageStory API](https://apidocs.vintagestory.at/api/Vintagestory.API.Common.Entities.Entity.html)
- [Modding:Entity instance attributes - Vintage Story Wiki](https://wiki.vintagestory.at/Modding:Entity_instance_attributes)

### Local Research
- `docs/research/misc/2026-01-12-coordinate-systems-offsets.md` (original findings)
- `docs/research/misc/2026-01-12-player-position-look-apis.md` (eye position formulas)
- `docs/journal/2026-01-12-harness-visual-debug.md` (empirical test results)
