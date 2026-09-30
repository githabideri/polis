# Web UI v2 Implementation Plan

**Date:** 2026-01-19
**Scope:** Phase 1 (Foundation/MVP) + Phase 2 partial (full command coverage)
**Reference:** `docs/design/webui-v2-design.md`

## Progress

| Step | Description | Status |
|------|-------------|--------|
| 1 | Project Scaffolding | Done |
| 2 | API Client | Done |
| 3 | IndexedDB Layer | Done |
| 4 | State Management | Done |
| 5 | Core UI Layout | Done |
| 6 | Status Bar | Done |
| 7 | Entity Panel | Pending |
| 8 | Context Panel | Pending |
| 9 | Screenshot View | Pending |
| 10 | Command Bar | Pending |
| 11 | Event Log | Pending |
| 12 | Action Dialogs | Pending |
| 13 | Full Command Integration | Pending |
| 14 | Polish & Edge Cases | Pending |

**2026-01-20:** Steps 1-6 implemented. Basic skeleton loads, polling and state management in place. Entity rendering and command execution wired up but not visually verified. Fixed syntax error in app.js.

## Overview

This plan implements the foundation of Web UI v2:
- New file structure with modular JS
- IndexedDB state layer
- Core UI layout (panels, command bar, log)
- Full command coverage via context-aware actions
- Screenshot display with refresh controls

**Not in scope (later phases):**
- Structured 3D view (Phase 3)
- Agent WebSocket integration (Phase 4)
- Three.js rendering (Phase 5)

## Prerequisites

- VS game running with polis mod loaded
- HTTP harness reachable at `localhost:8585`
- Bot spawned and selectable for testing

## File Structure

```
tools/
  webui-v2/
    index.html              # Entry point
    css/
      main.css              # Core styles
      panels.css            # Panel-specific styles
      mobile.css            # Compact mode overrides
    js/
      app.js                # Initialization, main loop
      config.js             # Constants, settings
      db.js                 # IndexedDB operations
      api.js                # Harness HTTP client
      state.js              # World model, in-memory cache
      ui/
        layout.js           # Panel management, responsive
        statusbar.js        # Connection status, indicators
        entities.js         # Entity list panel
        context.js          # Context panel (selection details + actions)
        views.js            # Screenshot display, view tabs
        commandbar.js       # Command input, autocomplete, history
        log.js              # Event log panel
      utils/
        format.js           # Data formatting helpers
        spatial.js          # Distance, direction calculations
```

---

## Implementation Steps

### Step 1: Project Scaffolding

**Tasks:**
1. Create directory structure
2. Create `index.html` with basic layout skeleton
3. Create empty JS modules with exports
4. Create basic CSS with layout grid
5. Verify page loads without errors

**Files to create:**
- `tools/webui-v2/index.html`
- `tools/webui-v2/css/main.css`
- `tools/webui-v2/js/app.js`
- `tools/webui-v2/js/config.js`

**Test checkpoint 1.1:**
```bash
# Start a local server (VS harness serves static files but we need CORS)
# Or just open file directly - ES modules need a server
cd tools/webui-v2
python3 -m http.server 8080

# Open http://localhost:8080 in browser
# Expected: Page loads with placeholder panels, no console errors
```

---

### Step 2: API Client

**Tasks:**
1. Implement `api.js` with HTTP client class
2. Methods: `get(path, params)`, `post(path, body)`
3. Automatic JSON parsing
4. Error handling with typed errors
5. Connection status tracking

**File: `js/api.js`**
```javascript
// Exports:
// - class HarnessClient
// - Methods: get, post, isConnected
// - Events: onConnectionChange
```

**Test checkpoint 2.1:**
```javascript
// In browser console after loading page:
import { api } from './js/api.js';

// Test connection
await api.get('/polis/status');
// Expected: {ok: true, server: {worldReady: true, ...}}

await api.get('/polis/bots');
// Expected: {Ok: true, Data: {bots: [...]}}

await api.post('/polis/command', {cmd: 'bots', args: []});
// Expected: {Ok: true, Message: "...", Data: {...}}
```

---

### Step 3: IndexedDB Layer

**Tasks:**
1. Implement `db.js` with schema from design doc
2. Database initialization and versioning
3. CRUD operations for each store
4. Query helpers (get by key, get all, filter)

**Stores:**
- `blocks` - Block data from scans
- `entities` - Entity data (bots, players, mobs, items)
- `snapshots` - Camera snapshots with optional screenshots
- `actions` - Command history
- `settings` - User preferences

**File: `js/db.js`**
```javascript
// Exports:
// - initDB() -> Promise<IDBDatabase>
// - blocks.put(block), blocks.get(key), blocks.getInChunk(chunkKey)
// - entities.put(entity), entities.get(id), entities.getAll()
// - snapshots.add(snapshot), snapshots.getRecent(limit)
// - actions.add(action), actions.getRecent(limit)
// - settings.get(key), settings.set(key, value)
```

**Test checkpoint 3.1:**
```javascript
// In browser console:
import { db } from './js/db.js';

// Initialize
await db.init();
// Expected: No errors, database created

// Test entity storage
await db.entities.put({id: 12345, code: 'test:entity', pos: [0,0,0], lastSeen: Date.now()});
const entity = await db.entities.get(12345);
console.log(entity);
// Expected: {id: 12345, code: 'test:entity', ...}

// Test action logging
await db.actions.add({timestamp: Date.now(), command: 'test', args: [], result: {Ok: true}});
const actions = await db.actions.getRecent(10);
console.log(actions);
// Expected: Array with test action
```

---

### Step 4: State Management

**Tasks:**
1. Implement `state.js` with in-memory world model
2. Sync from API responses to both memory and IndexedDB
3. Selection state (current bot, player, target)
4. Event emitter for UI updates

**File: `js/state.js`**
```javascript
// Exports:
// - state object with:
//   - connection: {connected, lastCheck}
//   - bots: Map<id, botData>
//   - players: Map<uid, playerData>
//   - targets: {blocks: [], entities: []}
//   - selection: {type, id, data}
//   - lastAction: {command, result, timestamp}
// - Methods:
//   - updateFromStatus(data)
//   - updateFromBots(data)
//   - updateFromState(data)
//   - updateFromTargets(data)
//   - select(type, id)
//   - clearSelection()
// - Events:
//   - onChange(callback) - called on any state change
```

**Test checkpoint 4.1:**
```javascript
// In browser console:
import { state } from './js/state.js';
import { api } from './js/api.js';

// Fetch and update
const status = await api.get('/polis/status');
state.updateFromStatus(status);
console.log(state.connection);
// Expected: {connected: true, ...}

const bots = await api.get('/polis/bots');
state.updateFromBots(bots);
console.log([...state.bots.values()]);
// Expected: Array of bot objects

// Test selection
state.select('bot', 12345);
console.log(state.selection);
// Expected: {type: 'bot', id: 12345, data: {...}}
```

---

### Step 5: Core UI Layout

**Tasks:**
1. Implement `layout.js` with panel management
2. CSS Grid layout matching design wireframe
3. Responsive breakpoint handling
4. Compact mode toggle
5. Panel resize/collapse

**Layout structure:**
```
┌─────────────────────────────────────────────────────────────┐
│ #statusbar                                                  │
├──────────────┬──────────────────────────────────────────────┤
│ #entity-panel│ #main-view                                   │
│              ├──────────────────────────────────────────────┤
│              │ #context-panel                               │
├──────────────┴──────────────────────────────────────────────┤
│ #command-bar                                                │
├─────────────────────────────────────────────────────────────┤
│ #event-log                                                  │
└─────────────────────────────────────────────────────────────┘
```

**Test checkpoint 5.1:**
```
Manual verification:
1. Open page at desktop width (>1024px)
   - Expected: Side-by-side panels, all visible
2. Resize to tablet width (768-1024px)
   - Expected: Panels adjust, still usable
3. Resize to mobile width (<768px)
   - Expected: Stacked layout, collapsible sections
4. Toggle compact mode button
   - Expected: Denser layout, smaller fonts
```

---

### Step 6: Status Bar

**Tasks:**
1. Implement `statusbar.js`
2. Show connection status indicator
3. Show world name, selected bot, player
4. Auto-refresh status every 5s

**Test checkpoint 6.1:**
```
Manual verification:
1. Load page with harness running
   - Expected: Green "Connected" indicator
2. Stop harness (or block port)
   - Expected: Red "Disconnected" indicator within 5s
3. Restart harness
   - Expected: Green indicator returns
4. Select a bot
   - Expected: Bot ID shown in status bar
```

---

### Step 7: Entity Panel

**Tasks:**
1. Implement `entities.js`
2. Collapsible sections: Bots, Players, Nearby
3. Click to select entity
4. Visual indicator for selected entity
5. Refresh button
6. Filter controls (type checkboxes, search)

**Test checkpoint 7.1:**
```
Prerequisite: Bot spawned, player online

Manual verification:
1. Bots section shows spawned bots
   - Expected: Bot IDs listed with loaded/unloaded status
2. Players section shows online players
   - Expected: Player names listed
3. Click on a bot
   - Expected: Bot highlighted, context panel updates
4. Click "Refresh" or wait for auto-refresh
   - Expected: List updates with current data
5. Use search filter
   - Expected: List filtered by search term
```

**Automated test:**
```javascript
// Run after page loaded
import { api } from './js/api.js';
import { state } from './js/state.js';

// Spawn bot if needed
const spawnResult = await api.post('/polis/command', {cmd: 'spawn', args: []});
console.log('Spawn:', spawnResult);

// Wait for refresh
await new Promise(r => setTimeout(r, 2000));

// Verify bot appears in state
console.log('Bots in state:', state.bots.size);
// Expected: >= 1

// Verify UI shows bot (check DOM)
const botItems = document.querySelectorAll('#entity-panel .bot-item');
console.log('Bot items in DOM:', botItems.length);
// Expected: >= 1
```

---

### Step 8: Context Panel

**Tasks:**
1. Implement `context.js`
2. Show details based on selection type
3. Bot context: position, health, inventory slots
4. Player context: position, view direction
5. Block context: code, position, behaviors
6. Entity context: code, position, health
7. Action buttons based on context

**Context → Actions mapping (from design doc):**

| Selection | Actions |
|-----------|---------|
| None | spawn, status |
| Bot | goto, stop, give, equip, drop, pickup, mine, place, activate, harvest, takefrom, putinto, despawn, possess |
| Player | teleport, setup-view, screenshot |
| Block | mine, activate |
| Entity (mob) | interact, butcher |
| Entity (item) | pickup |

**Test checkpoint 8.1:**
```
Prerequisite: Bot spawned and selected

Manual verification:
1. With bot selected, context panel shows:
   - Bot ID and position
   - Health bar
   - Inventory slots (R.Hand, L.Hand, Backpack)
   - Action buttons: Goto, Stop, Give, Mine, etc.
2. Click "Give" button
   - Expected: Dialog/input for item code and quantity
3. Click "Goto" button
   - Expected: Dialog/input for coordinates
```

**Automated test:**
```javascript
// With bot selected
const botId = [...state.bots.keys()][0];
state.select('bot', botId);

// Verify context panel updated
await new Promise(r => setTimeout(r, 100));
const contextType = document.querySelector('#context-panel .context-type')?.textContent;
console.log('Context type:', contextType);
// Expected: "Bot #12345" or similar

const actionButtons = document.querySelectorAll('#context-panel .action-btn');
console.log('Action buttons:', [...actionButtons].map(b => b.textContent));
// Expected: ['Goto', 'Stop', 'Give', 'Mine', ...]
```

---

### Step 9: Screenshot View

**Tasks:**
1. Implement screenshot display in `views.js`
2. Manual refresh button
3. After-action auto-refresh (configurable)
4. Timed polling (configurable, default off)
5. Display capture timestamp and dimensions

**Test checkpoint 9.1:**
```
Prerequisite: Player online, harness running

Manual verification:
1. Click "Refresh Screenshot" button
   - Expected: Screenshot appears, timestamp shown
2. Execute a bot action (e.g., goto)
   - Expected: Screenshot auto-refreshes after action completes
3. Enable "Auto-refresh" with 5s interval
   - Expected: Screenshot updates every 5s
4. Disable auto-refresh
   - Expected: Screenshot stops updating
```

**Automated test:**
```javascript
// Get player UID
const players = await api.get('/polis/players');
const playerUid = players.players[0]?.uid;
console.log('Player UID:', playerUid);

// Request screenshot
const screenshot = await api.get('/polis/screenshot', {playerUid, save: 'false'});
console.log('Screenshot:', screenshot.ok, screenshot.width, screenshot.height);
// Expected: true, 1290, 756 (or similar)

// Verify displayed in UI
const img = document.querySelector('#main-view .screenshot-img');
console.log('Screenshot img src set:', !!img?.src);
// Expected: true
```

---

### Step 10: Command Bar

**Tasks:**
1. Implement `commandbar.js`
2. Text input with Enter to execute
3. Command history (up/down arrows)
4. Basic autocomplete (command names)
5. Parse command string to {cmd, args}
6. Execute via API and show result
7. Log command to actions store

**Test checkpoint 10.1:**
```
Manual verification:
1. Type "status" and press Enter
   - Expected: Command executes, result shown in log
2. Type "bots" and press Enter
   - Expected: Bot list returned
3. Type "give game:stone-granite 5" and press Enter
   - Expected: Item given to selected bot
4. Press Up arrow
   - Expected: Previous command recalled
5. Start typing "gi"
   - Expected: Autocomplete suggests "give"
```

**Automated test:**
```javascript
// Simulate command execution
const input = document.querySelector('#command-bar input');
input.value = 'bots';
input.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter'}));

await new Promise(r => setTimeout(r, 500));

// Check log for result
const logEntries = document.querySelectorAll('#event-log .log-entry');
const lastEntry = logEntries[0]?.textContent;
console.log('Last log entry:', lastEntry);
// Expected: Contains "bots" and "OK" or bot list
```

---

### Step 11: Event Log

**Tasks:**
1. Implement `log.js`
2. Display command results
3. Display events from `/polis/events` polling
4. Color coding (success green, error red)
5. Timestamp for each entry
6. Clear button
7. Pause auto-scroll button
8. Store to IndexedDB for history

**Test checkpoint 11.1:**
```
Manual verification:
1. Execute commands via command bar
   - Expected: Results appear in log with timestamps
2. Trigger game events (spawn bot, bot death)
   - Expected: Events appear in log
3. Click "Clear" button
   - Expected: Log cleared
4. Click "Pause" button
   - Expected: Log stops scrolling on new entries
5. Scroll up in log, new entry arrives
   - Expected: Log doesn't jump to bottom (when paused)
```

---

### Step 12: Action Dialogs

**Tasks:**
1. Create modal dialog component
2. Dialogs for commands needing input:
   - Goto: x, y, z coordinates
   - Give: item code, quantity
   - Mine/Activate: x, y, z coordinates
   - Place: block code, x, y, z, face
   - Takefrom/Putinto: x, y, z, slot, quantity
3. Pre-fill from selection when available

**Test checkpoint 12.1:**
```
Prerequisite: Bot selected, nearby block from targets

Manual verification:
1. Click "Goto" action button
   - Expected: Dialog opens with coordinate inputs
2. Enter coordinates, click Execute
   - Expected: Bot moves, dialog closes
3. Select a block from targets list
4. Click "Mine" action
   - Expected: Dialog opens with coordinates pre-filled
5. Click Execute
   - Expected: Block mined
```

---

### Step 13: Full Command Integration

**Tasks:**
1. Wire up all commands from poliscli
2. Verify each command works via UI
3. Handle command-specific requirements (playerUid context, etc.)

**Command checklist:**

| Command | Button | Dialog | Test |
|---------|--------|--------|------|
| status | - | - | Status bar |
| players | - | - | Entity panel |
| bots | - | - | Entity panel |
| state | - | - | Context panel |
| spawn | Yes | Optional coords | ✓ |
| select | Click entity | - | ✓ |
| despawn | Yes | Confirm | ✓ |
| goto | Yes | Coords | ✓ |
| stop | Yes | - | ✓ |
| give | Yes | Item, qty | ✓ |
| equip | Yes | Slot, item, qty | ✓ |
| drop | Yes | Slot, qty | ✓ |
| pickup | Yes | Optional ID | ✓ |
| mine | Yes | Coords | ✓ |
| place | Yes | Code, coords, face | ✓ |
| activate | Yes | Coords | ✓ |
| harvest | Yes | Coords | ✓ |
| harvestcrop | Yes | Coords | ✓ |
| takefrom | Yes | Coords, slot, qty | ✓ |
| putinto | Yes | Coords, slot, qty | ✓ |
| butcher | Yes | Entity ID | ✓ |
| teleport | Yes | Coords, yaw, pitch | ✓ |
| screenshot | Yes | Save option | ✓ |
| setup-view | Yes | Distance | ✓ |
| possess | Yes | - | ✓ |
| unpossess | Yes | - | ✓ |
| exec | Command bar | - | ✓ |

**Test checkpoint 13.1:**
```bash
# Full integration test script
# Run in browser console or as test file

const tests = [
  async () => {
    // Spawn bot
    const r = await api.post('/polis/command', {cmd: 'spawn', args: []});
    console.assert(r.Ok, 'spawn failed');
    return r.Data?.id;
  },
  async (botId) => {
    // Select bot
    state.select('bot', botId);
    console.assert(state.selection.id === botId, 'select failed');
    return botId;
  },
  async (botId) => {
    // Give item
    const r = await api.post('/polis/command', {cmd: 'give', args: ['game:stone-granite', '5']});
    console.assert(r.Ok, 'give failed');
    return botId;
  },
  async (botId) => {
    // Drop item
    const r = await api.post('/polis/command', {cmd: 'drop', args: ['-1', '0']});
    console.assert(r.Ok, 'drop failed');
    return botId;
  },
  async (botId) => {
    // Pickup item
    await new Promise(r => setTimeout(r, 1000)); // Wait for item to be pickable
    const r = await api.post('/polis/command', {cmd: 'pickup', args: []});
    console.assert(r.Ok, 'pickup failed');
    return botId;
  },
  async (botId) => {
    // Despawn
    const r = await api.post('/polis/command', {cmd: 'despawn', args: []});
    console.assert(r.Ok, 'despawn failed');
  }
];

// Run tests sequentially
let ctx;
for (const test of tests) {
  ctx = await test(ctx);
}
console.log('All tests passed!');
```

---

### Step 14: Polish & Edge Cases

**Tasks:**
1. Error handling for all API calls
2. Loading states for async operations
3. Empty states (no bots, no targets, etc.)
4. Connection lost recovery
5. Mobile touch interactions
6. Keyboard navigation

**Test checkpoint 14.1:**
```
Manual verification:
1. Disconnect harness, verify UI shows disconnected state
2. Reconnect harness, verify UI recovers
3. Try actions with no bot selected, verify helpful error
4. Try invalid coordinates, verify error message
5. Test on mobile/touch device
6. Tab through UI elements, verify focus handling
```

---

## Verification Summary

After completing all steps, run this final verification:

### Pre-flight
```bash
# Ensure VS running with mod
./scripts/vsctl.py status
# Expected: world_ready: true, client_ready: true

# Ensure harness reachable
curl http://localhost:8585/polis/status | jq .
# Expected: {"ok":true,"server":{"worldReady":true,...}}
```

### Full UI Test
```
1. Open http://localhost:8080 (or harness /polis/ui endpoint)
2. Verify status bar shows "Connected"
3. Spawn a bot via UI or command bar
4. Verify bot appears in entity list
5. Select the bot
6. Verify context panel shows bot details
7. Click "Screenshot" to capture view
8. Use "Give" to add item to bot
9. Use "Drop" to drop item
10. Use "Pickup" to retrieve item
11. Use "Goto" to move bot
12. Verify screenshot updates after action
13. Check event log shows all actions
14. Use command bar for "bots" command
15. Verify autocomplete works
16. Test on mobile viewport
17. Despawn bot via UI
18. Verify entity list updates
```

### Performance Check
```javascript
// Measure UI responsiveness
const start = performance.now();
await api.get('/polis/state');
console.log('API latency:', performance.now() - start, 'ms');
// Expected: < 100ms

// Check IndexedDB size
const estimate = await navigator.storage.estimate();
console.log('Storage used:', estimate.usage, 'bytes');
// Expected: < 1MB for typical session
```

---

## Notes

- Keep old `test-ui.html` functional during development
- New UI at `tools/webui-v2/index.html`
- Can be served via harness at `/polis/ui-v2` once integrated
- Mobile testing with Chrome DevTools device mode is sufficient initially
