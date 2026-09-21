/**
 * Polis Web UI v2 - Main Application
 *
 * Initialization, polling loops, and coordination.
 */

import { CONFIG } from './config.js';
import { api } from './api.js';
import { db } from './db.js';
import { state, SelectionType } from './state.js';
import { layout } from './ui/layout.js';
import { statusBar } from './ui/statusbar.js';
import { screenshotPane } from './ui/screenshot.js';

/**
 * Polling state
 */
let statusPollTimer = null;
let eventPollTimer = null;
let lastEventTs = 0;

// Step-control tuning
const MOVE_STEP_BLOCKS = 0.5;
const TURN_STEP_RAD = (15 * Math.PI) / 180;
const LOOK_STEP_RAD = (10 * Math.PI) / 180;
const VERTICAL_STEP_BLOCKS = 0.5;
const CONTROL_PULSE_MS = 160;
const RAD_TO_DEG = 180 / Math.PI;

// Best-effort possession state cache (for UI hints)
const possessionByPlayer = new Map();

/**
 * Log an entry to the event log panel
 */
function log(message, type = 'info') {
    const logEntries = document.getElementById('log-entries');
    if (!logEntries) return;

    const entry = document.createElement('div');
    entry.className = `log-entry ${type}`;

    const time = new Date().toLocaleTimeString();
    entry.innerHTML = `<span class="log-time">${time}</span><span class="log-msg">${escapeHtml(message)}</span>`;

    // Insert at top
    logEntries.insertBefore(entry, logEntries.firstChild);

    // Trim old entries
    while (logEntries.children.length > CONFIG.LOG_MAX_ENTRIES) {
        logEntries.removeChild(logEntries.lastChild);
    }
}

/**
 * Escape HTML entities
 */
function escapeHtml(str) {
    return String(str).replace(/[&<>"']/g, m => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    })[m]);
}

/**
 * Poll status endpoint
 */
async function pollStatus() {
    try {
        const data = await api.getStatus();
        state.updateFromStatus(data);

        // Also fetch bots and players
        const [botsData, playersData] = await Promise.all([
            api.getBots().catch(() => null),
            api.getPlayers().catch(() => null),
        ]);

        if (botsData) state.updateFromBots(botsData);
        if (playersData) state.updateFromPlayers(playersData);

        // If we have a selected bot, get its state
        if (state.selectedBotId) {
            const stateData = await api.getState(state.selectedBotId).catch(() => null);
            if (stateData) state.updateFromState(stateData);
        }
    } catch (e) {
        state.setConnected(false);
    }
}

/**
 * Poll events endpoint
 */
async function pollEvents() {
    try {
        const data = await api.getEvents(20);
        if (!data.ok || !data.events) return;

        // Process events newer than lastEventTs
        const newEvents = data.events.filter(e => e.ts > lastEventTs);
        if (newEvents.length > 0) {
            lastEventTs = Math.max(...newEvents.map(e => e.ts));

            // Process oldest-first for correct log order
            newEvents.reverse().forEach(handleEvent);
        }
    } catch (e) {
        // Silent fail during polling
    }
}

/**
 * Handle an incoming event
 */
function handleEvent(event) {
    const { type, data } = event;

    switch (type) {
        case 'action_complete':
            log(`[action] ${data.action}: ${data.msg}`, data.ok ? 'success' : 'error');
            // Refresh state after action
            pollStatus();
            break;

        case 'bot_spawned':
            log(`[spawn] Bot #${data.botId} spawned at ${formatPos(data.pos)} (${data.source})`);
            pollStatus();
            break;

        case 'bot_died':
            log(`[death] Bot #${data.botId} died (${data.cause})`, 'error');
            pollStatus();
            break;

        case 'bot_unloaded':
            log(`[unload] Bot #${data.botId} unloaded`);
            break;

        case 'debug_toggled':
            log(`[debug] Debug mode ${data.enabled ? 'enabled' : 'disabled'}`);
            break;

        case 'log':
            log(`[${data.category || 'debug'}] ${data.msg}`);
            break;

        default:
            log(`[${type}] ${JSON.stringify(data)}`);
    }
}

/**
 * Format position array for display
 */
function formatPos(pos) {
    if (!pos || !Array.isArray(pos)) return '?';
    return pos.map(p => typeof p === 'number' ? p.toFixed(1) : p).join(', ');
}

function wrapAngle(rad) {
    const twoPi = Math.PI * 2;
    let v = rad % twoPi;
    if (v < 0) v += twoPi;
    return v;
}

function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
}

function toBoolArg(v) {
    return v ? 'true' : 'false';
}

function getPrimaryPlayer() {
    const selected = state.selection;
    if (selected.type === SelectionType.PLAYER) {
        return selected.data || state.players.get(selected.id) || null;
    }

    // Single-player convenience fallback
    if (state.players.size === 1) {
        return [...state.players.values()][0];
    }

    return null;
}

function getSelectedBotId() {
    if (state.selection.type === SelectionType.BOT && state.selection.id != null) {
        return state.selection.id;
    }
    return state.selectedBotId;
}

function getPlayerPose(player) {
    if (!player?.pos || player.pos.length < 3) return null;

    const x = Number(player.pos[0]);
    const y = Number(player.pos[1]);
    const z = Number(player.pos[2]);
    if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(z)) return null;

    const yaw = Number.isFinite(player.yaw) ? Number(player.yaw) : Math.PI;
    // Harness reports VS internal pitch: π = level, π/2 up, 3π/2 down
    const pitchInternal = Number.isFinite(player.pitch) ? Number(player.pitch) : Math.PI;
    // Teleport command expects intuitive pitch: 0 = level, +up, -down
    const pitchInput = clamp(Math.PI - pitchInternal, -Math.PI / 2, Math.PI / 2);

    return { x, y, z, yaw, pitchInput };
}

async function runHarnessCommand(cmd, args = [], context = null, opts = {}) {
    const { quiet = false, successLabel = null } = opts;

    const result = await api.command(cmd, args, context);
    const ok = result?.Ok ?? result?.ok;
    const message = result?.Message || result?.message || JSON.stringify(result);

    if (!quiet) {
        const label = successLabel || cmd;
        log(`${label}: ${message}`, ok ? 'success' : 'error');
    }

    state.recordAction(cmd, args, result);
    await pollStatus();

    if (!ok) {
        throw new Error(message || `Command failed: ${cmd}`);
    }

    return result;
}

async function teleportPlayer(uid, x, y, z, yaw, pitchInput) {
    const args = [
        String(uid),
        x.toFixed(3),
        y.toFixed(3),
        z.toFixed(3),
        wrapAngle(yaw).toFixed(6),
        pitchInput.toFixed(6),
    ];

    return runHarnessCommand('teleport', args, null, { quiet: true });
}

async function movePlayerStep(direction) {
    const player = getPrimaryPlayer();
    if (!player) {
        log('Select a player first (or keep exactly one online player)', 'error');
        return;
    }

    const pose = getPlayerPose(player);
    if (!pose) {
        log('Selected player has no valid position', 'error');
        return;
    }

    // VS yaw in our harness maps forward to +sin(yaw), +cos(yaw)
    const forwardX = Math.sin(pose.yaw);
    const forwardZ = Math.cos(pose.yaw);
    const rightX = Math.cos(pose.yaw);
    const rightZ = -Math.sin(pose.yaw);

    let dx = 0;
    let dy = 0;
    let dz = 0;

    switch (direction) {
        case 'forward':
            dx = forwardX * MOVE_STEP_BLOCKS;
            dz = forwardZ * MOVE_STEP_BLOCKS;
            break;
        case 'backward':
            dx = -forwardX * MOVE_STEP_BLOCKS;
            dz = -forwardZ * MOVE_STEP_BLOCKS;
            break;
        case 'left':
            dx = -rightX * MOVE_STEP_BLOCKS;
            dz = -rightZ * MOVE_STEP_BLOCKS;
            break;
        case 'right':
            dx = rightX * MOVE_STEP_BLOCKS;
            dz = rightZ * MOVE_STEP_BLOCKS;
            break;
        case 'up':
            dy = VERTICAL_STEP_BLOCKS;
            break;
        case 'down':
            dy = -VERTICAL_STEP_BLOCKS;
            break;
        default:
            return;
    }

    try {
        await teleportPlayer(
            player.uid,
            pose.x + dx,
            pose.y + dy,
            pose.z + dz,
            pose.yaw,
            pose.pitchInput,
        );
        log(`Moved ${direction} (${MOVE_STEP_BLOCKS}b step)`);
    } catch (e) {
        log(`Move failed: ${e.message}`, 'error');
    }
}

async function rotateView(direction) {
    const player = getPrimaryPlayer();
    if (!player) {
        log('Select a player first', 'error');
        return;
    }

    const pose = getPlayerPose(player);
    if (!pose) {
        log('Selected player has no valid pose', 'error');
        return;
    }

    const delta = direction === 'left' ? -TURN_STEP_RAD : TURN_STEP_RAD;
    try {
        await teleportPlayer(player.uid, pose.x, pose.y, pose.z, pose.yaw + delta, pose.pitchInput);
        log(`Turned ${direction} (15°)`);
    } catch (e) {
        log(`Turn failed: ${e.message}`, 'error');
    }
}

async function tiltView(direction) {
    const player = getPrimaryPlayer();
    if (!player) {
        log('Select a player first', 'error');
        return;
    }

    const pose = getPlayerPose(player);
    if (!pose) {
        log('Selected player has no valid pose', 'error');
        return;
    }

    const delta = direction === 'up' ? LOOK_STEP_RAD : -LOOK_STEP_RAD;
    const nextPitchInput = clamp(pose.pitchInput + delta, -Math.PI / 2, Math.PI / 2);

    try {
        await teleportPlayer(player.uid, pose.x, pose.y, pose.z, pose.yaw, nextPitchInput);
        log(`Look ${direction} (10°)`);
    } catch (e) {
        log(`Look failed: ${e.message}`, 'error');
    }
}

function selectedContextForPlayer(player) {
    return { playerUid: player.uid };
}

async function possessSelectedBot() {
    const player = getPrimaryPlayer();
    if (!player) {
        log('Select a player first', 'error');
        return;
    }

    const botId = getSelectedBotId();
    if (botId == null) {
        log('Select a bot first for possession', 'error');
        return;
    }

    const context = selectedContextForPlayer(player);

    try {
        await runHarnessCommand('select', [String(botId)], context, { quiet: true });
        await runHarnessCommand('possess', [], context, { quiet: true });
        possessionByPlayer.set(player.uid, true);
        log(`Possession started (player ${player.name} -> bot #${botId})`, 'success');
    } catch (e) {
        log(`Possess failed: ${e.message}`, 'error');
    }
}

async function unpossessPlayer() {
    const player = getPrimaryPlayer();
    if (!player) {
        log('Select a player first', 'error');
        return;
    }

    try {
        await runHarnessCommand('unpossess', [], selectedContextForPlayer(player), { quiet: true });
        possessionByPlayer.set(player.uid, false);
        log('Exited possession mode', 'success');
    } catch (e) {
        log(`Unpossess failed: ${e.message}`, 'error');
    }
}

async function pulsePossessionControl(flags) {
    const player = getPrimaryPlayer();
    if (!player) {
        log('Select a player first', 'error');
        return;
    }

    const context = selectedContextForPlayer(player);
    const args = [
        toBoolArg(!!flags.forward),
        toBoolArg(!!flags.backward),
        toBoolArg(!!flags.left),
        toBoolArg(!!flags.right),
        toBoolArg(!!flags.sprint),
        toBoolArg(!!flags.jump),
    ];

    try {
        await runHarnessCommand('setcontrols', args, context, { quiet: true });
        await new Promise(resolve => setTimeout(resolve, CONTROL_PULSE_MS));
        await runHarnessCommand('setcontrols', ['false', 'false', 'false', 'false', 'false', 'false'], context, { quiet: true });
        possessionByPlayer.set(player.uid, true);
        log('Possession movement pulse sent', 'success');
    } catch (e) {
        if (String(e.message).includes('Not currently possessing')) {
            possessionByPlayer.set(player.uid, false);
        }
        log(`Possession control failed: ${e.message}`, 'error');
    }
}

function renderContextPanel() {
    const detailsEl = document.getElementById('context-details');
    const actionsEl = document.getElementById('context-actions');
    if (!detailsEl || !actionsEl) return;

    const player = getPrimaryPlayer();
    const botId = getSelectedBotId();

    if (!player) {
        detailsEl.innerHTML = `
            <div class="placeholder">Select a player (or keep one online) to enable control buttons.</div>
        `;
        actionsEl.innerHTML = '';
        return;
    }

    const pose = getPlayerPose(player);
    const yawDeg = pose ? (wrapAngle(pose.yaw) * RAD_TO_DEG) : null;
    const pitchDeg = pose ? (pose.pitchInput * RAD_TO_DEG) : null;
    const possessionHint = possessionByPlayer.get(player.uid) ? 'Possessing (cached)' : 'Not possessing (cached)';

    detailsEl.innerHTML = `
        <div><strong>Player:</strong> ${escapeHtml(player.name || player.uid)}</div>
        <div><strong>UID:</strong> <span class="mono">${escapeHtml(player.uid)}</span></div>
        <div><strong>Pos:</strong> ${pose ? `${pose.x.toFixed(2)}, ${pose.y.toFixed(2)}, ${pose.z.toFixed(2)}` : 'n/a'}</div>
        <div><strong>View:</strong> yaw ${yawDeg !== null ? yawDeg.toFixed(1) + '°' : 'n/a'}, pitch ${pitchDeg !== null ? pitchDeg.toFixed(1) + '°' : 'n/a'}</div>
        <div><strong>Bot:</strong> ${botId != null ? `#${botId}` : 'none selected'} | <strong>Possession:</strong> ${possessionHint}</div>
    `;

    actionsEl.innerHTML = `
        <div class="control-section">
            <div class="control-title">Step Move (0.5 block)</div>
            <div class="control-grid control-grid-3">
                <button data-action="move-up">Up +Y</button>
                <button data-action="move-forward" class="primary">Forward</button>
                <button data-action="move-down">Down -Y</button>
                <button data-action="move-left">Left</button>
                <button data-action="move-backward">Back</button>
                <button data-action="move-right">Right</button>
            </div>
        </div>

        <div class="control-section">
            <div class="control-title">View</div>
            <div class="control-grid control-grid-2">
                <button data-action="turn-left">Turn -15°</button>
                <button data-action="turn-right">Turn +15°</button>
                <button data-action="look-up">Look +10°</button>
                <button data-action="look-down">Look -10°</button>
            </div>
        </div>

        <div class="control-section">
            <div class="control-title">Possession</div>
            <div class="control-grid control-grid-2">
                <button data-action="possess" ${botId == null ? 'disabled' : ''}>Possess Bot</button>
                <button data-action="unpossess">Unpossess</button>
                <button data-action="poss-forward">Step Forward</button>
                <button data-action="poss-back">Step Back</button>
                <button data-action="poss-left">Step Left</button>
                <button data-action="poss-right">Step Right</button>
            </div>
            <div class="control-note">Deterministic 0.5-block teleport steps (works while mounted).</div>
        </div>
    `;
}

async function handleControlAction(action) {
    switch (action) {
        case 'move-forward':
            return movePlayerStep('forward');
        case 'move-backward':
            return movePlayerStep('backward');
        case 'move-left':
            return movePlayerStep('left');
        case 'move-right':
            return movePlayerStep('right');
        case 'move-up':
            return movePlayerStep('up');
        case 'move-down':
            return movePlayerStep('down');
        case 'turn-left':
            return rotateView('left');
        case 'turn-right':
            return rotateView('right');
        case 'look-up':
            return tiltView('up');
        case 'look-down':
            return tiltView('down');
        case 'possess':
            return possessSelectedBot();
        case 'unpossess':
            return unpossessPlayer();
        case 'poss-forward':
            return movePlayerStep('forward');
        case 'poss-back':
            return movePlayerStep('backward');
        case 'poss-left':
            return movePlayerStep('left');
        case 'poss-right':
            return movePlayerStep('right');
        default:
            return;
    }
}

function setupContextControls() {
    const actionsEl = document.getElementById('context-actions');
    if (!actionsEl) return;

    actionsEl.addEventListener('click', async (event) => {
        const button = event.target.closest('button[data-action]');
        if (!button || button.disabled) return;

        const { action } = button.dataset;
        if (!action) return;

        button.disabled = true;
        try {
            await handleControlAction(action);
        } finally {
            button.disabled = false;
            renderContextPanel();
        }
    });
}

/**
 * Start polling loops
 */
function startPolling() {
    // Initialize lastEventTs to now so we only see new events
    lastEventTs = Date.now();

    // Status polling
    statusPollTimer = setInterval(pollStatus, CONFIG.POLL_STATUS_MS);
    pollStatus(); // Initial poll

    // Event polling
    eventPollTimer = setInterval(pollEvents, CONFIG.POLL_EVENTS_MS);
    pollEvents(); // Initial poll

    log('Polling started');
}

/**
 * Stop polling loops
 */
function stopPolling() {
    if (statusPollTimer) {
        clearInterval(statusPollTimer);
        statusPollTimer = null;
    }
    if (eventPollTimer) {
        clearInterval(eventPollTimer);
        eventPollTimer = null;
    }
    log('Polling stopped');
}

/**
 * Render entity lists
 */
function renderEntityLists() {
    renderBotsList();
    renderPlayersList();
}

/**
 * Render bots list
 */
function renderBotsList() {
    const container = document.getElementById('bots-list');
    if (!container) return;

    const bots = [...state.bots.values()];

    if (bots.length === 0) {
        container.innerHTML = '<div class="placeholder">No bots</div>';
        return;
    }

    container.innerHTML = bots.map(bot => {
        const isSelected = state.selection.type === SelectionType.BOT && state.selection.id === bot.id;
        const statusClass = bot.loaded ? '' : 'unloaded';
        return `
            <div class="entity-item ${isSelected ? 'selected' : ''} ${statusClass}" data-type="bot" data-id="${bot.id}">
                <div class="entity-id">#${bot.id}</div>
                <div class="entity-status">${bot.loaded ? 'Loaded' : 'Unloaded'}</div>
            </div>
        `;
    }).join('');

    // Add click handlers
    container.querySelectorAll('.entity-item').forEach(el => {
        el.addEventListener('click', () => {
            const id = parseInt(el.dataset.id, 10);
            state.select(SelectionType.BOT, id);
            renderEntityLists(); // Re-render to update selection
        });
    });
}

/**
 * Render players list
 */
function renderPlayersList() {
    const container = document.getElementById('players-list');
    if (!container) return;

    const players = [...state.players.values()];

    if (players.length === 0) {
        container.innerHTML = '<div class="placeholder">No players</div>';
        return;
    }

    container.innerHTML = players.map(player => {
        const isSelected = state.selection.type === SelectionType.PLAYER && state.selection.id === player.uid;
        return `
            <div class="entity-item ${isSelected ? 'selected' : ''}" data-type="player" data-id="${player.uid}">
                <div class="entity-name">${escapeHtml(player.name)}</div>
                <div class="entity-status">Online</div>
            </div>
        `;
    }).join('');

    // Add click handlers
    container.querySelectorAll('.entity-item').forEach(el => {
        el.addEventListener('click', () => {
            const uid = el.dataset.id;
            state.select(SelectionType.PLAYER, uid);
            renderEntityLists();
        });
    });
}

/**
 * Set up command bar handlers
 */
function setupCommandBar() {
    const input = document.getElementById('command-input');
    const submitBtn = document.getElementById('command-submit');

    if (!input || !submitBtn) return;

    // Handle Enter key
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            executeCommand(input.value);
            input.value = '';
        }
    });

    // Handle submit button
    submitBtn.addEventListener('click', () => {
        executeCommand(input.value);
        input.value = '';
    });
}

/**
 * Execute a command from the command bar
 */
async function executeCommand(cmdString) {
    const trimmed = cmdString.trim();
    if (!trimmed) return;

    // Parse command and args
    const parts = trimmed.split(/\s+/);
    const cmd = parts[0];
    const args = parts.slice(1);

    log(`> ${trimmed}`);

    try {
        const result = await api.command(cmd, args);
        state.recordAction(cmd, args, result);

        const message = result.Message || result.message || JSON.stringify(result);
        log(`${cmd}: ${message}`, result.Ok ? 'success' : 'error');

        // Refresh state after command
        pollStatus();
    } catch (e) {
        log(`${cmd}: ${e.message}`, 'error');
        state.recordAction(cmd, args, { Ok: false, Message: e.message });
    }
}

/**
 * Set up log controls
 */
function setupLogControls() {
    const clearBtn = document.getElementById('log-clear');
    const pauseBtn = document.getElementById('log-pause');

    if (clearBtn) {
        clearBtn.addEventListener('click', () => {
            const logEntries = document.getElementById('log-entries');
            if (logEntries) {
                logEntries.innerHTML = '';
                log('Log cleared');
            }
        });
    }

    // Pause button is a placeholder for now
    if (pauseBtn) {
        let paused = false;
        pauseBtn.addEventListener('click', () => {
            paused = !paused;
            pauseBtn.textContent = paused ? '\u25b6' : '\u23f8';
            pauseBtn.title = paused ? 'Resume auto-scroll' : 'Pause auto-scroll';
        });
    }
}

/**
 * Set up refresh button
 */
function setupRefreshButton() {
    const refreshBtn = document.getElementById('refresh-entities');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', () => {
            log('Refreshing...');
            pollStatus();
        });
    }
}

function initStream() {
    const frame = document.getElementById('novnc-frame');
    const toggle = document.getElementById('stream-enabled');
    const statusEl = document.getElementById('stream-status');
    if (!frame || !toggle) return;
    function connectStream() {
        const base = CONFIG.NOVNC_BASE || `http://${window.location.hostname}:6080`;
        frame.src = `${base}${CONFIG.NOVNC_PATH}?${CONFIG.NOVNC_PARAMS}`;
        statusEl.textContent = 'Connecting...';
        frame.onload = () => { statusEl.textContent = 'Connected'; };
    }
    function disconnectStream() {
        frame.src = '';
        statusEl.textContent = 'Disconnected';
    }
    toggle.addEventListener('change', () => {
        if (toggle.checked) connectStream();
        else disconnectStream();
    });
    connectStream();
}

/**
 * Main initialization
 */
async function init() {
    console.log('Polis Web UI v2 initializing...');

    try {
        // Initialize IndexedDB
        await db.init();
        console.log('IndexedDB initialized');

        // Load persisted state
        await state.loadPersistedState();
        console.log('Persisted state loaded');

        // Initialize UI components
        layout.init();
        statusBar.init();
        screenshotPane.init();

        // Set up event handlers
        setupCommandBar();
        setupLogControls();
        setupRefreshButton();
        setupContextControls();

        // Initial render before polling fills live data
        renderEntityLists();
        renderContextPanel();

        // Subscribe to state changes for entity list + context control updates
        state.onChange((type) => {
            if (type === 'bots' || type === 'players' || type === 'selection') {
                renderEntityLists();
                renderContextPanel();
            }

            if (type === 'state' || type === 'connection' || type === 'action') {
                renderContextPanel();
            }
        });

        // Wire up API connection changes
        api.onConnectionChange((connected) => {
            state.setConnected(connected);
        });

        // Start polling
        startPolling();
        initStream();

        log('Web UI v2 initialized');
        console.log('Initialization complete');

    } catch (e) {
        console.error('Initialization error:', e);
        log(`Initialization error: ${e.message}`, 'error');
    }
}

// Export for console access during development
window.polis = {
    api,
    db,
    state,
    layout,
    log,
    pollStatus,
    pollEvents,
    startPolling,
    stopPolling,
};

// Initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}
