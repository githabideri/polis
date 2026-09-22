# Technical Notes (PoC)

This document captures the current architecture and implementation details so work can resume without rebuilding context.

## Layout

- `PolisBuilderNpcSystem.cs`: server-side partial class — persistence, entity lifecycle, bot tracking, action sequencing.
- `PolisBuilderNpcHotkeys.cs`: client-side hotkeys.
- `PolisScreenCapture.cs`: screenshot capture utility (OpenGL + SkiaSharp).
- `PolisScreenCaptureRenderer.cs`: client-side IRenderer for frame capture.
- `PolisNetworkPackets.cs`: network packets and persistent data structures.
- `PolisTestHarness.cs`: HTTP API server for external control.
- `modinfo.json`: mod metadata.

### Source tree (post-refactor)

```
src/
├── Actions/
│   ├── Blocks/          - ActivateBlock, BreakBlock, IgniteBlock, MineBlock, PlaceBlock
│   ├── Entities/        - InteractEntity, ButcherEntity
│   ├── Harvesting/      - HarvestBlock, HarvestCrop
│   ├── Inventory/       - ContainerPut, ContainerTake, DropItem, PickupItem
│   ├── Navigation/      - GotoAction
│   └── Workstations/    - AnvilSmith, ClayForm, GrindBlock, Knap, Press, SealBarrel
├── Commands/
│   └── PolisCommandRegistry.cs   - All /polis command registration
├── Core/
│   ├── PolisConstants.cs         - Shared constants
│   └── PolisValidation.cs        - Range/block/entity validation helpers
├── Harness/
│   └── PolisHarnessCommandHandlers.cs  - HTTP API command handlers (partial class)
└── Helpers/
    ├── PolisAnimationHelpers.cs   - Animation start/stop utilities
    └── PolisInventoryHelpers.cs   - Bot inventory insertion helpers
```

## Repository workflow (agents)

- Default to a task branch unless the user explicitly requests work on `main`.
- Branch naming: `agent/<name>/<task>` (e.g., `agent/codex/activate-los`).
- Mention the active branch in status updates; merge only when instructed.

## Architecture

### Bot tracking

`PolisBuilderNpcSystem` maintains:
- `bots`: `entityId -> BotState` (wraps `EntityAgent` + `EntityActivitySystem`). **In-memory only, for loaded bots.**
- `selectedByPlayer`: `playerUid -> entityId`.
- `globalData`: `PolisGlobalData` - **Persistent registry** stored in world save.

Selection is per-player; if only one bot exists, selection is implied.

### Bot Registry (Persistence)

The mod uses a **Shadow Registry** pattern (inspired by `vsvillage`) to persist bot data across server restarts and chunk unloads.

**Data Structures** (in `PolisNetworkPackets.cs`):
```csharp
[ProtoContract]
public class PolisGlobalData {
    public Dictionary<long, BotRecord> Bots;
}

[ProtoContract]
public class BotRecord {
    public long EntityId;
    public string OwnerUid;
    public string Name;
    public Vec3d LastKnownPos;
    public bool IsLoaded;
    public string EntityCode;
}
```

**Persistence Events**:
- `api.Event.SaveGameLoaded`: Load `PolisGlobalData` from `api.WorldManager.SaveGame.GetData("polis-bots")`.
- `api.Event.GameWorldSave`: Save `PolisGlobalData` to `api.WorldManager.SaveGame.StoreData("polis-bots", ...)`.

**Entity Lifecycle Events**:
- `api.Event.OnEntityLoaded`: When a bot entity loads (chunk load), update `IsLoaded = true` in registry and re-add to `bots` dict.
- `api.Event.OnEntityDespawn`: 
  - If `EnumDespawnReason.Unload`: Set `IsLoaded = false`, keep in registry.
  - If `Death`/`Removed`/`Combusted`: Remove from registry permanently.

**Entity Attributes** (backup for registry recovery):
- `polisOwnerUid`: Owner player UID stored on entity via `WatchedAttributes.SetString()`.
- `polisName`: Bot name stored on entity.
- If registry is lost, bots can be recovered when their entities load.

**Entity Code Defaults:**
- Default bot entity is `polis-builder-npc:polisbot`.
- On load, old records referencing `playerbot` are migrated to `polisbot`.

**UI Behavior**:
- Bot Manager shows ALL bots from registry (loaded and unloaded).
- Unloaded bots appear grayed out with `[FAR]` suffix.
- Selection only allowed for loaded bots.
- Deletion works for both loaded and unloaded bots.

### Command pipeline

Commands create action sequences and run them through `EntityActivitySystem`.

Key methods:
- `StartActionSequence`: cancels current activity, injects a new `EntityActivity` with actions, starts it.
- `StartSingleAction`: convenience wrapper.

### Actions

All actions derive from `EntityActionBase`:

- `PolisGotoAction`
  - Uses `WaypointsTraverser.NavigateTo_Async` for A*.
  - Uses `StraightLineTraverser` when `Astar=false` or fallback is enabled.
  - Logs `start`, `path found`, `no path`, `stuck`, `reached`.
  - Uses `EnumAICreatureType` from entity attributes; defaults to `Humanoid` for `EntityHumanoid` if missing.
  - Keeps engine `PathFindDebug` disabled; uses custom highlights instead.

- `PolisActivateBlockAction`
  - Runs `block.Activate(...)` at target position.
  - Validates range and block existence.

- `PolisBreakBlockAction`
  - Uses `BlockAccessor.BreakBlock(...)` with the invoking player for drops.
  - Validates range.

- `PolisPlaceBlockAction`
  - Calls `block.TryPlaceBlock(...)` with a constructed `BlockSelection`.
  - Validates range, stack, and player.

- `PolisInteractEntityAction`
  - Uses ray-traced `EntitySelection.HitPosition`, normalized to entity-relative coordinates.
  - Supports `interact` and `attack` modes.
  - Validates range before interaction.
  - Reference: `docs/research/phase-2/2026-01-13-hitposition-coordinate-space-resolution.md`.

- `PolisPickupItemAction`
  - Uses `EntityItem.CanCollect` plus explicit slot insertion (hands → backpack/bag contents).
  - Inserts via `ItemSlot.TryPutInto(...)` and persists with `EntityBehaviorSeraphInventory.storeInv()`.
  - Handles partial transfers (item entity kept alive with remaining stack).
  - Despawns item entity when fully collected.
  - **Status:** ✅ Implemented and tested (survival mode verified).

- `PolisDropItemAction`
  - Drops from bot hand slots (0=right, 1=left, -1=auto).
  - Uses `IWorldAccessor.SpawnItemEntity` with slight upward velocity.
  - Persists inventory via `EntityBehaviorSeraphInventory.storeInv()`.
  - **Status:** ✅ Implemented and tested (survival mode verified). Backpack slots deferred.

- `PolisContainerTakeAction`
  - Withdraws items from `IBlockEntityContainer` into bot inventory.
  - Validates range, block existence, container interface, claims (`EnumBlockAccessFlags.Use`).
  - Uses owner player for claims check (bot inherits owner permissions).
  - **Status:** ✅ Implemented and tested.

- `PolisContainerPutAction`
  - Deposits items from bot hand slots into `IBlockEntityContainer`.
  - Same validation flow as TakeAction.
  - Iterates container slots to find space, calls `MarkDirty()` on both slot and block entity.
  - **Status:** ✅ Implemented and tested.

- `PolisGrindBlockAction`
  - Uses `block.OnBlockInteractStart/Step/Stop` with `SelectionBoxIndex=1` for grinding.
  - Validates quern block, `CanGrind()` state, and range.
  - Tracks output slot count to determine items ground.
  - Optional count/duration limits for partial grinding.
  - Plays hit animation during grinding.
  - **Status:** ✅ Implemented and tested.

- `PolisPressAction`
  - Operates fruit presses to extract juice from fruit mash.
  - Uses `BlockEntityFruitPress.OnReceivedClientPacket` to trigger screw animation (server-side packet simulation).
  - Validates fruit press block, `CanScrew` state, mash content, and range.
  - Tracks juice extraction via bucket slot liquid level.
  - Optional duration limit and auto-unscrew when complete.
  - Plays hit animation during pressing.
  - **Status:** ✅ Implemented.

- `PolisClayFormAction`
  - Forms clay into recipe shapes on clayforming surfaces.
  - Places clayform block if needed, consumes clay from bot inventory.
  - Progressive voxel placement with visible animation timing.
  - Uses `BlockEntityClayForm.SetVoxel()` for each voxel, `CheckIfFinished()` to produce output.
  - Plays hit animation during forming.
  - **Status:** ✅ Implemented and tested.

- `PolisKnapAction`
  - Knaps flint/stone on knapping surfaces to create tools.
  - Auto-places material from bot inventory if surface is empty.
  - Progressive voxel removal (opposite of clay forming) with animation.
  - Uses BFS to find connected voxels for removal, `CheckIfFinished()` on completion.
  - Items go to bot inventory via `TryInsertIntoBotInventory()`, overflow spawns on ground.
  - Plays hit animation during knapping.
  - **Status:** ✅ Implemented and tested.

- Held-use primitives (planned)
  - Use `Collectible.OnHeldUseStart/Step/Stop` with `EnumHandInteract` routing.
  - `EnumHandHandling` determines whether default action occurs and whether step/stop run.

- Claims/permissions
  - Use `ILandClaimAPI.TestAccess` / `TryAccess`.
  - `BuildOrBreak` for placement/breaking; `Use` for container/block interactions.
  - **Status:** ✅ Used in container transfer actions.
  - Reference: `docs/research/misc/2026-01-13-claims-enforcement-patterns.md`.

- Pickup/transfer implications (from research)
  - Slot-based insertion uses `ItemSlot.TryPutInto(...)` and should keep item entities alive if stack remains.
  - Container actions must enforce range/LOS/claims explicitly (no default inventory gate).
  - PlayerBot inventory sync requires `slot.MarkDirty()` + `storeInv()`. See `docs/research/phase-2/2026-01-14-bot-inventory-sync-flow.md`.
  - Container transfer call order: `docs/research/phase-2/2026-01-14-container-transfer-correctness.md`.

### Movement target selection

- `/polis goto` uses explicit coords.
- `/polis gotolook` ray-traces from player eye position.
  - If no hit, `TryFindStandPos` scans downward for a solid surface.
  - Tall grass is ignored during ray tracing; if only tall grass is hit, the target snaps to the ground below it.

Approach position:
- If player has a block selection, the bot is moved to the adjacent block on the selected face.

### Harmony patch (tall grass)

- `PolisBuilderNpcHarmony` patches `Vintagestory.Essentials.AStar.traversable` to ignore tall grass collisions during path clearance checks.
- Patch is process-wide while the mod is loaded (affects any A* users in VSEssentials).
- This does not change runtime collision/physics; it only affects pathfinding traversability.

## Debug + Visualization

### Highlights

Highlights are server-side with `IWorldAccessor.HighlightBlocks`:

- `HighlightSlotId`: action targets.
- `PathHighlightSlotId`: path overlay.
- `BotHighlightSlotId`: selected bot location.
- `PreviewPathHighlightSlotId`: preview path overlay.

Slots are cleared after a timeout (2s for action targets, 6s for path).

### Path extraction

`TryExtractPathFromTraverser`:
- Reads path nodes from `WaypointsTraverser` via:
  - Direct enumerable properties (e.g., `Path`, `Waypoints`).
  - A reflection scan that searches for `path/waypoint/node` members up to depth 3.
- Converts nodes to `BlockPos` and reduces list length if too long.

`/polis pathdump` logs traverser members and highlights the path if found.

### Logging

All debug logging is tagged with `[polis]`:
- `server-main.log` contains all action + path events.
- Use `/polis debug on` to enable.

## Hotkeys

Client-side hotkeys are registered with Alt combos:

- Alt+N spawn
- Alt+L selectlook
- Alt+G gotolook
- Alt+Shift+G preview toggle (left click commits, live path while walking)
- Alt+A activate
- Alt+B break
- Alt+H placeheld
- Alt+S stop
- Alt+D debug toggle
- Alt+P pathdump

## Screenshot Capture System

The mod includes a screenshot capture system for LLM/VLM vision and debug logging.

### Architecture

**Files:**
- `PolisScreenCapture.cs` - Core capture utility (OpenGL `glReadPixels`, SkiaSharp PNG encoding)
- `PolisScreenCaptureRenderer.cs` - IRenderer implementation for frame capture
- Network packets in `PolisNetworkPackets.cs`:
  - `PolisScreenshotRequestPacket` - Server → Client
  - `PolisScreenshotResponsePacket` - Client → Server

**Flow:**
1. HTTP request to `/polis/screenshot?playerUid=...`
2. Server sends `PolisScreenshotRequestPacket` to target player's client
3. Client's `PolisScreenCaptureRenderer.OnRenderFrame()` captures framebuffer during `EnumRenderStage.Done`
4. OpenGL `glReadPixels` via OpenTK captures RGBA pixels
5. SkiaSharp encodes to PNG
6. Client sends `PolisScreenshotResponsePacket` with base64 PNG back to server
7. Server returns JSON response to HTTP client

**Dependencies (from VS Lib folder, not bundled):**
- `OpenTK.Graphics.dll` - OpenGL bindings
- `OpenTK.Mathematics.dll` - Math types
- `SkiaSharp.dll` - PNG encoding

### Usage

```bash
# Get player UID
curl http://localhost:8585/polis/players | jq '.players[0].uid'

# Capture screenshot (URL-encode the UID)
curl "http://localhost:8585/polis/screenshot?playerUid=REDACTED-UID"

# Save to file
curl -s "http://localhost:8585/polis/screenshot?playerUid=..." | jq -r '.base64' | base64 -d > screenshot.png
```

**Response:**
```json
{
  "ok": true,
  "width": 1290,
  "height": 756,
  "base64": "iVBORw0KGgo...",
  "captureTimeMs": 129
}
```

### Notes

- Captures current player's view (not bot POV - that would require camera manipulation)
- Typical capture time: 50-150ms depending on resolution
- Add `&save=true` to also save PNG to `~/Pictures/Vintagestory/polis/`

## Player View Direction (Teleport with Camera Sync)

The `teleport` command can set both player position AND camera direction. This requires a server→client network packet since setting `EntityPos.Yaw/Pitch` on the server only affects the third-person model, not the first-person camera (which is client-controlled).

### Architecture

**Network packet** in `PolisNetworkPackets.cs`:
- `PolisSetViewDirectionPacket` - Server → Client, contains `Yaw` and `Pitch` (radians)

**Flow:**
1. HTTP `teleport` command with yaw/pitch parameters
2. Server calls `entity.TeleportTo(EntityPos)` for position
3. Server sends `PolisSetViewDirectionPacket` to player's client
4. Client handler sets `player.CameraYaw` and `player.CameraPitch`

### VS Yaw Convention

To face a target position from current position:
```
yaw = atan2(target.x - pos.x, target.z - pos.z) + π
```

| Direction | Yaw (radians) |
|-----------|---------------|
| North (-Z) | 0 |
| South (+Z) | π (3.14) |
| East (+X) | 3π/2 (4.71) |
| West (-X) | π/2 (1.57) |

**Pitch:** 0 = level, negative = look down, positive = look up

## Current Issues / Open Questions

- Path overlay is block highlights only (no custom renderer).

## Troubleshooting Checklist

- If you see `no path`, verify:
  - Debug is on (to get traverser member output).
  - `aiCreatureType` is set or defaults to `Humanoid`.

- If you see `stuck`, check:
  - Bot's current position in the log.
  - Any steep edges or holes near that position.

## Testing Infrastructure

**Status:** Fully implemented (see `docs/research/misc/2026-01-12-testing-harness-architecture.md`)

### Design Overview

- `/polis teststate [radius]` - Query bot state + nearby items + last action result
- HTTP API on localhost:8585 - External control without timing issues
- Web UI - Visual control panel for manual testing
- Action result tracking in `BotState` - Diagnostic messages + `LastActionId`/`LastActionMs`

### HTTP Test Harness

The mod starts an HTTP server on `localhost:8585` for external control. This enables:
- Agent-driven testing (Claude, scripts, etc.)
- Web UI control panel
- CI/CD integration

Commands can include an optional `context` object (playerUid, useLookTarget, spawnOffset/gotoOffset)
for player-relative actions.

**Endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/polis/status` | Readiness + metadata (worldReady/runPhase) |
| `GET` | `/polis/players` | List online players |
| `GET` | `/polis/player?uid=` | Single player detail |
| `GET` | `/polis/look?uid=&range=` | Server-side raytrace from player look |
| `GET` | `/polis/targets?playerUid=&botId=&radius=&limit=&mode=&q=&codeContains=&requireEntityClass=` | Nearby interactables (blocks/entities) |
| `GET` | `/polis/state?botId=` | Get bot state, inventory, nearby items |
| `GET` | `/polis/bots` | List all bots |
| `POST` | `/polis/command` | Execute command: `{"cmd":"...", "args":[...]}` |
| `POST` | `/polis/servercmd` | Execute raw server/chat command (local only) |
| `GET` | `/` or `/polis` | Health check / endpoint list |

**Available Commands via HTTP:**
- `spawn` - Spawn bot at world spawn (or `spawn [entityCode] [x y z]`)
- `select <botId>` - Select a specific bot
- `selectlook` - Select bot under player look ray
- `despawn` - Despawn selected (or first) bot
- `stop` - Stop current bot activity
- `give <itemCode> [qty]` - Give item to bot's right hand
- `drop [slot] [qty]` - Drop from slot (-1=auto, 0=right, 1=left)
- `pickup [entityId] [range]` - Pick up nearest item or specific entity
- `goto <x> <y> <z>` - Move bot to position
- `gotolook` - Move bot to player look target (server raytrace)
- `activate <x> <y> <z>` - Activate a block (requires `context.playerUid` or look target)
- `interact <entityId> [mode] [range]` - Interact with an entity by id
- `teststate [botId]` - Get full state as JSON
- `bots` - List all registered bots
- `takefrom <x> <y> <z> <slot> [qty]` - Take items from container into bot inventory
- `putinto <x> <y> <z> <slot> [qty]` - Put items from bot hand into container
- `grind <x> <y> <z> [count] [duration]` - Grind items in a quern (count=max items, duration=max seconds)
- `press <x> <y> <z> [duration] [autounscrew]` - Press fruit in a fruit press (duration=max seconds, autounscrew=true/false)
- `clayform <x> <y> <z> <recipe> [speed]` - Form clay into shapes (recipe=output code, speed=voxels/tick)
- `knap <x> <y> <z> <recipe> [speed]` - Knap flint/stone into tools (recipe=output code, speed=voxels/tick)

**Server Command Escape Hatch:**
- `POST /polis/servercmd` executes a raw command line via `ChatCommands.ExecuteUnparsed`.
- Local-only (loopback check) and uses wildcard privileges; intended for development only.
- Command reference snapshot: `docs/SERVER_COMMANDS.md` (wiki list; may be outdated).

**Example (curl):**
```bash
# Spawn a bot
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"spawn"}'

# Give item
curl -X POST http://localhost:8585/polis/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"give","args":["game:stone-granite","5"]}'

# Check state
curl http://localhost:8585/polis/state
```

`/polis/state` includes `LastActionId` and `LastActionMs` for action ordering.

### Web UI

Open `tools/test-ui.html` in a browser while the game server is running. Features:
- Live state polling (every 2 seconds)
- Command buttons: Spawn, Stop, Give, Drop, Pickup, Goto
- Bot inventory display
- Nearby items list with entity IDs
- Action log with success/failure status

### Smoke Test Runner

Use `scripts/polis-http-smoke.py` for a state-driven HTTP smoke test. It spawns
a bot, selects it, runs give/drop/pickup, and optionally validates a goto
target via `/polis/state?botId=...`.

### Key In-Game Commands for Testing

| Command | Purpose |
|---------|---------|
| `/polis teststate` | Dump bot inventory + nearby items + last action |
| `/polis debug on` | Enable detailed logging |
| `/polis give <item> [qty]` | Give item to bot for testing |
| `/polis drop [slot] [qty]` | Drop item to create test scenario |
| `/polis pickup [id] [range]` | Pick up item entity |
| `/polis takefrom <pos> <slot> [qty]` | Take from container |
| `/polis putinto <pos> <slot> [qty]` | Put into container |

### Verification Pattern

Run action, then `/polis teststate` or check via HTTP to verify:
1. **State is correct** (inventory, nearby entities)
2. **LastAction shows expected result** (success/failure + reason)
3. **Mismatch between state and result** indicates a bug

## Useful Files

- `PolisBuilderNpcSystem.cs` - Main mod system (partial class: persistence, entity lifecycle)
- `PolisBuilderNpcHotkeys.cs` - Client-side hotkeys
- `PolisTestHarness.cs` - HTTP server for external control
- `src/Commands/PolisCommandRegistry.cs` - Command registration
- `src/Actions/` - All action classes by category
- `src/Harness/PolisHarnessCommandHandlers.cs` - HTTP command handlers
- `tools/test-ui.html` - Web UI for testing
