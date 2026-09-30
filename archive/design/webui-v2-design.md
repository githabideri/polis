# Web UI v2 Design Document

**Date:** 2026-01-19
**Status:** Design phase

## 1. Vision

The current `test-ui.html` is a minimal control panel that covers a fraction of harness capabilities. Adding more features ad-hoc will create a mess.

**New vision:** The web UI becomes an **observation and analysis platform** for Vintage Story + LLM agent development, not just a test harness UI.

Goals:
- **Complete capability coverage** - All poliscli/harness commands accessible
- **Context-driven interaction** - Show relevant actions based on selection
- **Structured world representation** - LLM-friendly view of game state
- **Visual verification** - Screenshot + structured view side-by-side
- **Agent integration** - LLM/agent can connect and send commands
- **Historical analysis** - Action history, state replay, debugging

## 2. Three-Layer World View

The core innovation: represent the game world at three levels simultaneously.

```
┌─────────────────────────────────────────────────────────────┐
│  LAYER 1: SCREENSHOT         │  LAYER 2: STRUCTURED 3D     │
│  (pixel truth from game)     │  (same FOV, data-driven)    │
│                              │                              │
│  [actual rendered image]     │  [simplified 3D rendering   │
│                              │   from block/entity data,   │
│                              │   matching camera FOV]      │
├──────────────────────────────┴──────────────────────────────┤
│  LAYER 3: LLM TEXT VIEW                                     │
│                                                             │
│  "You are at (102, 65, -200) facing north.                  │
│   Ahead: flat grassland (12 blocks), stone outcrop at 8m.   │
│   Left: oak tree (3m). Right: wooden chest (2m, closed).    │
│   Behind: your cabin.                                       │
│   Right hand: copper pickaxe. Left hand: empty."            │
└─────────────────────────────────────────────────────────────┘
```

### Layer 1: Screenshot (Pixel Truth)

- Captured via `/polis/screenshot` endpoint
- Shows exactly what the game renders
- Ground truth for visual verification
- Refresh strategies: on-demand, after-action, timed polling

### Layer 2: Structured 3D View (Data-Driven)

- Same camera position/FOV as screenshot
- Rendered from API data (blocks, entities), not game engine
- Simplified representation:
  - Blocks as colored cubes or labeled regions
  - Similar blocks grouped ("flat land" vs 144 grass blocks)
  - Entities as markers with labels/icons
- Enables verification: does structured data match visual?

**Implementation phases:**
1. **Phase A (MVP):** JSON tree view of visible blocks/entities
2. **Phase B:** 2D top-down grid with block colors and entity markers
3. **Phase C:** 2.5D isometric view
4. **Phase D:** Full 3D view with Three.js, matching camera FOV

### Layer 3: LLM Text View (Natural Language)

- Human/LLM readable description of current state
- Generated from structured data via templates/rules
- Enables "text adventure" style interaction
- Components:
  - Position and orientation
  - Visible objects by direction (ahead, left, right, behind)
  - Distances and object types
  - Current inventory/equipment
  - Active status effects or conditions

**Description generation approach:**
- Spatial binning: group objects by direction (N/S/E/W or relative)
- Distance bands: immediate (0-2m), near (2-5m), far (5-15m), distant (15m+)
- Object grouping: "3 oak trees" not "tree, tree, tree"
- Salience filtering: important objects first, mundane terrain summarized

### Verification Chain

```
Game State → API → Structured Data → 3D Replica
                                   → Text Description → LLM
                 ↓
            Screenshot ← Visual comparison
```

When LLM says "go to the chest", verify:
1. Structured data shows chest at expected position
2. Screenshot shows chest visually
3. Text description mentioned the chest

## 3. Database / State Architecture

### Requirements

1. **Live world model** - Current known state of blocks/entities
2. **Spatial queries** - What's in FOV cone? Within radius?
3. **Historical replay** - Reconstruct state at timestamp T
4. **Screenshot storage** - Binary blobs with metadata
5. **Action log** - Commands, results, state deltas

### Storage Choice: IndexedDB

**Rationale:**
- Native browser API, no dependencies
- Good for blobs (screenshots)
- Sufficient for spatial queries with client-side math
- Persistent across sessions
- Can export to SQLite/JSON for offline analysis

**Rejected alternatives:**
- localStorage: Size limits, no good blob support
- SQLite (sql.js): Better queries but added complexity
- External DB: Overkill, requires server

### Schema

```javascript
// IndexedDB stores

const DB_SCHEMA = {
  version: 1,
  stores: {

    // Block data from scans and targets queries
    blocks: {
      keyPath: 'key',  // "x,y,z" string
      indexes: ['chunk', 'lastSeen', 'code'],
      // value: {
      //   key: "102,65,-200",
      //   x: 102, y: 65, z: -200,
      //   code: "game:stone-granite",
      //   behaviors: ["BlockBehaviorUnstableFalling"],
      //   entityClass: null,
      //   lastSeen: 1705678900000,
      //   chunk: "6,-13"  // chunkX, chunkZ for spatial indexing
      // }
    },

    // Entity data (bots, players, mobs, items)
    entities: {
      keyPath: 'id',
      indexes: ['class', 'code', 'lastSeen', 'isBot', 'isPlayer'],
      // value: {
      //   id: 12345,
      //   code: "game:sheep-bighorn-adult-male",
      //   class: "EntityAgent",
      //   pos: [102.5, 65.0, -199.3],
      //   health: 15,
      //   maxHealth: 15,
      //   inventory: [...],  // for bots
      //   state: "idle",
      //   isBot: false,
      //   isPlayer: false,
      //   lastSeen: 1705678900000
      // }
    },

    // Camera snapshots with optional screenshot
    snapshots: {
      keyPath: 'id',  // auto-increment
      indexes: ['timestamp', 'hasScreenshot'],
      // value: {
      //   id: 1,
      //   timestamp: 1705678900000,
      //   cameraPos: [100, 66, -195],
      //   cameraYaw: 3.14,
      //   cameraPitch: 0,
      //   cameraFov: 70,
      //   visibleBlockKeys: ["102,65,-200", ...],
      //   visibleEntityIds: [12345, ...],
      //   screenshotBlob: Blob | null,
      //   screenshotWidth: 1290,
      //   screenshotHeight: 756,
      //   generatedDescription: "You are at...",
      //   source: "after_action" | "manual" | "polling"
      // }
    },

    // Command/action history
    actions: {
      keyPath: 'id',  // auto-increment
      indexes: ['timestamp', 'command', 'success'],
      // value: {
      //   id: 1,
      //   timestamp: 1705678900000,
      //   command: "mine",
      //   args: ["102", "65", "-200"],
      //   context: { playerUid: "...", ... },
      //   result: { Ok: true, Message: "mined stone-granite" },
      //   snapshotBeforeId: null,
      //   snapshotAfterId: 1,
      //   source: "ui" | "command_bar" | "agent"
      // }
    },

    // Chunk scan index for knowing what areas are explored
    chunks: {
      keyPath: 'key',  // "chunkX,chunkZ"
      indexes: ['lastScan'],
      // value: {
      //   key: "6,-13",
      //   chunkX: 6,
      //   chunkZ: -13,
      //   lastScan: 1705678900000,
      //   blockCount: 4096,
      //   entityCount: 3
      // }
    },

    // Settings and preferences
    settings: {
      keyPath: 'key',
      // value: {
      //   key: "screenshot_polling",
      //   value: { enabled: false, intervalMs: 10000 }
      // }
    }
  }
};
```

### Spatial Query Approach

For "what's in this FOV cone?" queries:

1. **Chunk-based filtering:** Get chunks that might intersect the view frustum
2. **Block iteration:** For each block in those chunks, check if in frustum
3. **Client-side math:** Frustum culling is well-understood, fast in JS

```javascript
function getBlocksInFOV(cameraPos, cameraYaw, cameraPitch, fov, maxDist) {
  // 1. Calculate view frustum planes
  // 2. Get nearby chunks (simple bounding box)
  // 3. For each block, test against frustum
  // 4. Return sorted by distance
}
```

This is fast enough for typical view distances (32 blocks).

### Data Flow

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│ API Request │ ──▶ │ Response    │ ──▶ │ Store in    │
│ /targets    │     │ Parser      │     │ IndexedDB   │
│ /state      │     │             │     │             │
│ /scan       │     │             │     │             │
└─────────────┘     └─────────────┘     └─────────────┘
                                               │
                                               ▼
                                        ┌─────────────┐
                                        │ World Model │
                                        │ (in-memory  │
                                        │  cache)     │
                                        └─────────────┘
                                               │
                    ┌──────────────────────────┼──────────────────────────┐
                    ▼                          ▼                          ▼
             ┌─────────────┐           ┌─────────────┐           ┌─────────────┐
             │ Entity List │           │ Structured  │           │ LLM Text    │
             │ UI          │           │ 3D View     │           │ View        │
             └─────────────┘           └─────────────┘           └─────────────┘
```

## 4. UI Layout

### Desktop Layout (Primary)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ STATUS BAR                                                                  │
│ ● Connected │ World: test-lands │ Bot: #1234 │ Player: Alice │ 🔴 Recording │
├───────────────┬─────────────────────────────────────────────────────────────┤
│               │ VIEW TABS: [Screenshot] [Structured] [Side-by-Side] [LLM]   │
│  ENTITY       ├─────────────────────────────────────────────────────────────┤
│  PANEL        │                                                             │
│               │                                                             │
│  ▾ Bots       │                    MAIN VIEW AREA                           │
│    #1234 ●    │                                                             │
│    #5678 ○    │              (content based on selected tab)                │
│               │                                                             │
│  ▾ Players    │                                                             │
│    Alice      │                                                             │
│               │                                                             │
│  ▾ Nearby     ├─────────────────────────────────────────────────────────────┤
│    Chest 2m   │ CONTEXT PANEL                                               │
│    Sheep 5m   │                                                             │
│    Stone...   │ [Selected: Bot #1234]                                       │
│               │ Pos: 102.3, 65.0, -199.8  │  Health: 15/15                  │
│  [Refresh]    │ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐                 │
│               │ │ R.Hand │ │ L.Hand │ │ Back 0 │ │ Back 1 │                 │
│  ▾ Filters    │ │pickaxe │ │ empty  │ │ sack   │ │ empty  │                 │
│    □ Items    │ └────────┘ └────────┘ └────────┘ └────────┘                 │
│    □ Mobs     │                                                             │
│    □ Blocks   │ ACTIONS: [Goto...] [Give...] [Mine...] [Place...] [More ▾] │
│               │ QUICK:   [Stop] [Pickup nearest] [Face bot] [Screenshot]    │
├───────────────┴─────────────────────────────────────────────────────────────┤
│ COMMAND BAR                                                        [Agent ▾]│
│ > mine 102 65 -200 --autocollect                              [Run] [Clear] │
├─────────────────────────────────────────────────────────────────────────────┤
│ EVENT LOG                                                    [Clear] [Pause]│
│ 12:34:05 mine 102 65 -200: OK - mined game:stone-granite                    │
│ 12:34:02 goto 100 65 -198: OK - arrived                                     │
│ 12:34:00 [event] bot_spawned #1234 at (100, 65, -200)                       │
└─────────────────────────────────────────────────────────────────────────────┘
```

### View Tabs

| Tab | Content |
|-----|---------|
| **Screenshot** | Live/cached screenshot from game, refresh controls |
| **Structured** | 3D/2D structured view from block data (phased implementation) |
| **Side-by-Side** | Screenshot left, Structured right, for comparison |
| **LLM** | Text description view, copy button for pasting to LLM |

### Mobile/Compact Layout

```
┌─────────────────────────────────┐
│ ● Connected │ #1234 │ Alice    │
├─────────────────────────────────┤
│ [Entities ▾] [View ▾] [Actions]│
├─────────────────────────────────┤
│                                 │
│      MAIN VIEW AREA             │
│   (full width, swipeable)       │
│                                 │
├─────────────────────────────────┤
│ ▾ Context: Bot #1234           │
│   Pos: 102, 65, -200            │
│   [R: pickaxe] [L: empty]       │
│   [Goto] [Give] [Mine] [More]   │
├─────────────────────────────────┤
│ > command...              [Run] │
├─────────────────────────────────┤
│ ▾ Log (3 new)                   │
│   12:34 mine: OK                │
└─────────────────────────────────┘
```

**Compact mode features:**
- Collapsible sections (▾ headers)
- Abbreviated labels
- Horizontal scroll for inventory slots
- Swipe between view tabs

### Panel Details

#### Entity Panel

Lists all known entities grouped by type:
- **Bots:** From `/polis/bots`, show loaded/unloaded status
- **Players:** From `/polis/players`
- **Nearby:** From `/polis/targets`, filtered by type

Click to select, which updates Context Panel.

Filter controls:
- Checkboxes for entity types
- Search/filter text input
- Radius slider for "nearby" queries

#### Context Panel

Shows details and actions for selected entity.

**Context types:**

| Selection | Shows | Actions |
|-----------|-------|---------|
| None | Global actions | spawn, status |
| Bot | Position, health, inventory | goto, stop, give, equip, drop, pickup, mine, place, activate, harvest, takefrom, putinto, despawn, possess |
| Player | Position, view direction | teleport, setup-view, screenshot |
| Block | Code, position, behaviors | mine, activate, place adjacent |
| Entity (mob) | Code, position, health | interact, butcher (if dead) |
| Entity (item) | Code, quantity, position | pickup |

#### Command Bar

Unified input for all commands:
- Text input with autocomplete
- Command history (up/down arrows)
- Source indicator (human typing, button click, agent)
- Syntax highlighting / validation

Autocomplete sources:
- Command names
- Entity IDs from current state
- Block codes from recent scans
- Recent command history
- Argument hints per command

#### Event Log

Scrolling log of:
- Command executions (with success/fail)
- Events from `/polis/events` (action_complete, bot_spawned, etc.)
- System messages (connection status, errors)

Controls:
- Clear: Empty log
- Pause: Stop auto-scroll (for reading history)
- Filter: Show only errors, only events, etc.

## 5. Command / Context Matrix

Full mapping of commands to contexts where they're available.

### Global Commands (always available)

| Command | Description |
|---------|-------------|
| status | Server readiness check |
| players | List online players |
| bots | List all bots |
| spawn | Create new bot |
| exec | Raw server command |

### Bot Commands (requires bot selected)

| Command | Args | Description |
|---------|------|-------------|
| select | id | Select this bot |
| despawn | | Remove bot |
| state | | Get detailed state |
| goto | x y z | Move to position |
| stop | | Cancel current action |
| give | item [qty] | Add item to inventory |
| equip | slot item [qty] | Equip to specific slot |
| drop | [slot] [qty] | Drop from inventory |
| pickup | [entityId] | Pick up nearby item |
| mine | x y z | Break block |
| place | code x y z [face] | Place block |
| activate | x y z | Interact with block |
| harvest | x y z | Harvest berries/resin |
| harvestcrop | x y z | Harvest farm crop |
| takefrom | x y z slot [qty] | Take from container |
| putinto | x y z slot [qty] | Put into container |
| butcher | entityId | Butcher dead entity |
| animate | code [speed] [loop] | Play animation |
| possess | | Mount player onto bot |

### Player Commands (requires player context)

| Command | Args | Description |
|---------|------|-------------|
| player | [uid] | Get player info |
| look | | Get look target |
| teleport | x y z [yaw] [pitch] | Move player |
| setup-view | | Position to view bot |
| screenshot | [--save] | Capture view |

### Possession Commands (requires possessed state)

| Command | Args | Description |
|---------|------|-------------|
| unpossess | | Unmount from bot |
| controls | flags... | Set movement inputs |

### Building Commands (special mode)

| Command | Args | Description |
|---------|------|-------------|
| scan | from to | Capture region |
| verify | blueprint | Check against world |
| build | blueprint | Construct from file |
| setblock | code x y z | Direct block set |

### Block Context Commands (requires block selected)

When a block is selected from targets list:
- **mine** - Pre-fill coordinates
- **activate** - Pre-fill coordinates
- **place adjacent** - Calculate adjacent position

### Entity Context Commands (requires entity selected)

When an entity is selected from targets list:
- **interact** - Pre-fill entity ID
- **butcher** - Pre-fill entity ID (if dead)
- **pickup** - Pre-fill entity ID (if item)
- **goto** - Pre-fill entity position

## 6. Agent Integration

### Connection Modes

The web UI supports three input sources:

1. **Human typing** - Direct keyboard input to command bar
2. **Human clicking** - Buttons generate commands
3. **Agent streaming** - External LLM/agent sends commands

### Agent WebSocket Protocol

Separate from the event stream WebSocket.

```javascript
// Agent connects to: ws://localhost:8585/polis/agent
// (New endpoint to add to harness)

// Agent → UI: Execute command
{
  "type": "command",
  "id": "cmd-123",
  "command": "mine",
  "args": ["102", "65", "-200"],
  "context": { "playerUid": "..." }
}

// UI → Agent: Command result
{
  "type": "result",
  "id": "cmd-123",
  "success": true,
  "result": { "Ok": true, "Message": "mined stone-granite" }
}

// UI → Agent: State update (subscribed)
{
  "type": "state",
  "snapshot": { ... }
}

// UI → Agent: Screenshot (on request or subscription)
{
  "type": "screenshot",
  "base64": "...",
  "width": 1290,
  "height": 756
}

// Agent → UI: Request state/screenshot
{
  "type": "request",
  "what": "state" | "screenshot" | "description"
}
```

### Agent UI Indicator

When agent is connected:
- Status bar shows "Agent: connected"
- Command bar shows "[Agent]" prefix for agent commands
- Commands from agent appear in log with agent icon
- Optional: "Agent mode" that shows what agent "sees" (LLM view)

### Observation Mode

Agent can connect as observer only:
- Receives events and state updates
- Does not execute commands
- Useful for monitoring / training data collection

## 7. Implementation Phases

### Phase 1: Foundation (MVP)

**Goal:** Replace current UI with new architecture, basic functionality.

- [ ] IndexedDB setup with schema
- [ ] State management layer (world model cache)
- [ ] New layout structure (panels, command bar, log)
- [ ] Entity list with bot/player/targets
- [ ] Context panel with bot details
- [ ] Basic actions via buttons
- [ ] Command bar with history (no autocomplete yet)
- [ ] Event log from `/polis/events`
- [ ] Screenshot display (manual refresh)

### Phase 2: Full Command Coverage

**Goal:** All poliscli commands accessible.

- [ ] Complete context panel for all entity types
- [ ] All action buttons wired up
- [ ] Command bar autocomplete
- [ ] Argument dialogs for complex commands
- [ ] Building mode (scan/verify/build)
- [ ] Settings panel

### Phase 3: Structured View

**Goal:** LLM-friendly world representation.

- [ ] JSON tree view of visible blocks/entities
- [ ] LLM text description generator
- [ ] 2D grid view (top-down with block colors)
- [ ] FOV cone calculation and display
- [ ] Side-by-side screenshot + structured view

### Phase 4: Agent Integration

**Goal:** LLM/agent can connect and operate.

- [ ] Agent WebSocket endpoint (harness side)
- [ ] Agent connection UI
- [ ] Command routing from agent
- [ ] State/screenshot streaming to agent
- [ ] Observation mode

### Phase 5: 3D Structured View

**Goal:** Full 3D replica matching game camera.

- [ ] Three.js integration
- [ ] Block rendering from cached data
- [ ] Entity markers
- [ ] Camera sync with screenshot
- [ ] Object grouping and labels

### Phase 6: Polish

- [ ] Mobile/compact mode refinement
- [ ] Keyboard shortcuts
- [ ] Data export (SQLite, JSON)
- [ ] Historical replay
- [ ] Performance optimization

## 8. Technical Decisions

### Framework

**Decision:** Vanilla JavaScript with modules

**Rationale:**
- No build step required
- Easy to understand and modify
- Sufficient for this scale of UI
- Can import libraries via ESM (Three.js, etc.)

**Structure:**
```
tools/
  webui/
    index.html           # Main entry point
    css/
      main.css           # Styles
      mobile.css         # Compact mode overrides
    js/
      app.js             # Entry, initialization
      state.js           # State management, world model
      db.js              # IndexedDB operations
      api.js             # Harness API client
      ui/
        layout.js        # Panel management
        entities.js      # Entity list panel
        context.js       # Context panel
        views.js         # Screenshot/structured views
        commandbar.js    # Command input
        log.js           # Event log
      utils/
        spatial.js       # FOV, distance calculations
        descriptions.js  # LLM text generation
```

### Screenshot Handling

- Store as Blob in IndexedDB
- Display via `URL.createObjectURL()`
- Revoke URLs when no longer needed
- Compress older screenshots or discard

### Responsive Approach

- CSS Grid for main layout
- Breakpoint at 768px for mobile
- `prefers-reduced-motion` respected
- Compact mode toggle stored in settings

## 9. Open Questions

1. **Screenshot polling performance** - Need to test impact on game
2. **3D view library** - Three.js vs Babylon.js vs custom WebGL
3. **Description templates** - Hardcoded vs configurable
4. **Agent protocol** - Via web UI or direct to harness?
5. **Multi-agent support** - Multiple agents observing/acting?

## 10. References

- Current UI: `tools/test-ui.html`
- CLI: `scripts/poliscli.py`
- Harness: `PolisTestHarness.cs`
- API docs: `docs/TECHNICAL.md` (HTTP Test Harness section)
