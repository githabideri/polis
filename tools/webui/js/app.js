/**
 * Polis Web UI — application
 *
 * Four areas: Stage (live game image), World (entities), Control
 * (movement/view pad + bot actions), Console (log + commands).
 * Design contract: docs/design/webui-design.md
 *
 * Control model: HOLD TO REPEAT. A pressed button (or key) runs a
 * self-paced loop — each tick teleports the player one small delta from
 * the freshest pose we know (shadow pose, resynced from every server
 * poll), then sleeps to the cadence. Release stops the loop. This is
 * what makes "look around" usable: 12°/120 ms turns, 180° one-shot,
 * no click spamming (which used to crash the client, 2026-09-26).
 */

import { api } from './api.js';
import { state, SelectionType } from './state.js';
import { db } from './db.js';
import { CONFIG, getApiBase } from './config.js';

/* ── tunables ─────────────────────────────────────────────────────────── */

const STEP = {
    move:    { ms: 150, blocks: 0.5 },
    turn:    { ms: 120, deg: 12 },
    pitch:   { ms: 110, deg: 8 },
};
const PITCH_LIMIT = Math.PI / 2 - 0.05;   // matches the server clamp (3° short of poles)
const RAD = Math.PI / 180;

/* ── dom refs ─────────────────────────────────────────────────────────── */

const $ = (id) => document.getElementById(id);
const el = {
    conn: $('conn-badge'), connLabel: $('conn-label'),
    worldClock: $('world-clock'),
    currentStep: $('current-step'),
    selectionInfo: $('selection-info'),
    botsList: $('bots-list'), botCount: $('bot-count'),
    playersList: $('players-list'), playerCount: $('player-count'),
    tabs: $('stage-tabs'), toolsVnc: $('tools-vnc'), toolsFrames: $('tools-frames'),
    streamEnabled: $('stream-enabled'), streamStatus: $('stream-status'),
    novnc: $('novnc-frame'),
    framesImg: $('screenshot-img'), btnShot: $('btn-screenshot'),
    framesAuto: $('frames-auto'), shotStatus: $('shot-status'),
    playerMeta: $('player-meta'), btnResync: $('btn-resync'),
    botActions: $('bot-actions'), botIdLabel: $('bot-id-label'),
    advanced: $('advanced-actions'),
    log: $('log-entries'), cmdInput: $('command-input'), cmdSubmit: $('command-submit'),
};

/* ── log / helpers ────────────────────────────────────────────────────── */

function log(message, type = 'info', actor = null) {
    const line = document.createElement('div');
    line.className = `log-line ${type}`;
    const t = new Date().toLocaleTimeString('en-GB', { hour12: false });
    // actor badge (2026-09-27): who issued the line — user / agent / devops
    // / harness. "harness" is shown too: it is the v5 decision loop talking.
    const badge = actor
        ? `<span class="ev-actor ev-actor-${escapeHtml(actor)}">${escapeHtml(actor)}</span>`
        : '';
    line.innerHTML = `<span class="t">${t}</span>${badge}${escapeHtml(message)}`;
    el.log.appendChild(line);
    while (el.log.children.length > CONFIG.LOG_MAX_ENTRIES) el.log.firstChild.remove();
    el.log.scrollTop = el.log.scrollHeight;
}

function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

const wrapAngle = (r) => { let v = r % (2 * Math.PI); return v < 0 ? v + 2 * Math.PI : v; };
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const toBool = (v) => (v ? 'true' : 'false');

/* ── pose: server-authoritative, locally projected between polls ──────── */

let shadow = null;   // {x,y,z,yaw,pitch} in teleport-input space (pitch: 0=level,+up)
let lastCommandTs = 0;

function resyncShadowFromServer() {
    const p = getPrimaryPlayer();
    if (!p || !p.pos || p.pos.length < 3) return;
    const x = +p.pos[0], y = +p.pos[1], z = +p.pos[2];
    if (![x, y, z].every(Number.isFinite)) return;
    const yaw = typeof p.yaw === 'number' ? p.yaw : (shadow ? shadow.yaw : Math.PI);
    const pitchInternal = typeof p.pitch === 'number' ? p.pitch : Math.PI;
    const pitch = clamp(Math.PI - pitchInternal, -PITCH_LIMIT, PITCH_LIMIT);
    // Only adopt the server pose if it moved (or we have no shadow):
    // the server echoes our own teleports, so adopting unconditionally
    // after each step would double-apply latency.
    if (!shadow || dist2d(shadow, { x, z }) > 0.05 || Math.abs(shadow.pitch - pitch) > 0.01) {
        shadow = { x, y, z, yaw, pitch };
    }
}
function dist2d(a, b) { const dx = a.x - b.x, dz = a.z - b.z; return Math.hypot(dx, dz); }

function getPrimaryPlayer() {
    const sel = state.selection;
    if (sel.type === SelectionType.PLAYER) return sel.data || state.players.get(sel.id) || null;
    if (state.players.size === 1) return [...state.players.values()][0];
    return null;
}

async function sendTeleport(pose, logQuiet = true) {
    const now = Date.now();
    const gap = now - lastCommandTs;
    if (gap < 90) await new Promise(r => setTimeout(r, 90 - gap)); // floor; server guards make this safety, not rate limit
    lastCommandTs = Date.now();
    const uid = getPrimaryPlayer()?.uid;
    if (!uid) throw new Error('no player');
    const res = await api.command('teleport', [
        uid,
        pose.x.toFixed(3), pose.y.toFixed(3), pose.z.toFixed(3),
        wrapAngle(pose.yaw).toFixed(6), pose.pitch.toFixed(6),
    ]);
    const ok = res?.Ok ?? res?.ok;
    if (!ok) throw new Error(res?.Message || res?.message || 'teleport rejected');
    if (!logQuiet) log(`teleport → ${pose.x.toFixed(1)}, ${pose.y.toFixed(1)}, ${pose.z.toFixed(1)}`);
    return res;
}

/* ── the hold-to-repeat engine ────────────────────────────────────────── */

const holdKinds = {
    'forward':  (p) => ({ ...p, x: p.x + Math.sin(p.yaw) * STEP.move.blocks, z: p.z + Math.cos(p.yaw) * STEP.move.blocks }),
    'backward': (p) => ({ ...p, x: p.x - Math.sin(p.yaw) * STEP.move.blocks, z: p.z - Math.cos(p.yaw) * STEP.move.blocks }),
    // left/right: measured 2026-09-27 against the game's own keyboard
    // movement (xdotool W/A through the VNC) — left = (cos, -sin) at the
    // reported yaw; these were swapped before, so A walked right.
    'left':     (p) => ({ ...p, x: p.x + Math.cos(p.yaw) * STEP.move.blocks, z: p.z - Math.sin(p.yaw) * STEP.move.blocks }),
    'right':    (p) => ({ ...p, x: p.x - Math.cos(p.yaw) * STEP.move.blocks, z: p.z + Math.sin(p.yaw) * STEP.move.blocks }),
    'up':       (p) => ({ ...p, y: p.y + STEP.move.blocks }),
    'down':     (p) => ({ ...p, y: p.y - STEP.move.blocks }),
    // turn: the GAME's yaw increases when the view turns LEFT (measured
    // 2026-09-29 by before/after screenshots: yaw 177->129 on the
    // turnleft button rotated the view RIGHT - the signs below were
    // assumed at introduction and were inverted all along; the move
    // swap on the line above was the sibling of this one)
    'turnleft':  (p) => ({ ...p, yaw: p.yaw + STEP.turn.deg * RAD }),
    'turnright': (p) => ({ ...p, yaw: p.yaw - STEP.turn.deg * RAD }),
    'lookup':   (p) => ({ ...p, pitch: clamp(p.pitch + STEP.pitch.deg * RAD, -PITCH_LIMIT, PITCH_LIMIT) }),
    'lookdown': (p) => ({ ...p, pitch: clamp(p.pitch - STEP.pitch.deg * RAD, -PITCH_LIMIT, PITCH_LIMIT) }),
};
const kindCadence = (kind) => kind.startsWith('turn') || kind.startsWith('look')
    ? (kind.startsWith('look') ? STEP.pitch.ms : STEP.turn.ms)
    : STEP.move.ms;

const activeHolds = new Set();   // kinds currently held

async function holdLoop(kind) {
    while (activeHolds.has(kind)) {
        const t0 = Date.now();
        const stepFn = holdKinds[kind];
        const pose = shadow ? stepFn(shadow) : null;
        if (pose) {
            try {
                await sendTeleport(pose);
                shadow = pose;      // project locally; next server poll corrects
            } catch (e) {
                if (!String(e.message).startsWith('no player')) {
                    log(`${kind}: ${e.message}`, 'error');
                    break;
                }
            }
        }
        const elapsed = Date.now() - t0;
        if (activeHolds.has(kind)) {
            await new Promise(r => setTimeout(r, Math.max(0, kindCadence(kind) - elapsed)));
        }
    }
}

function startHold(kind) {
    if (activeHolds.has(kind)) return;
    if (!getPrimaryPlayer()) { log('no player online to control', 'error'); return; }
    if (!shadow) { resyncShadowFromServer(); if (!shadow) { log('no valid player pose', 'error'); return; } }
    activeHolds.add(kind);
    setHoldVisual(kind, true);
    holdLoop(kind);
}
function stopHold(kind) {
    if (!activeHolds.has(kind)) return;
    activeHolds.delete(kind);
    setHoldVisual(kind, false);
}
function setHoldVisual(kind, on) {
    document.querySelectorAll(`[data-hold="${kind}"]`).forEach(b => b.classList.toggle('holding', on));
}

/* one-shot actions */
async function oneshot(kind) {
    if (kind === 'turn180') {
        if (!shadow) { resyncShadowFromServer(); }
        if (!shadow) { log('no valid player pose', 'error'); return; }
        const next = { ...shadow, yaw: shadow.yaw + Math.PI };
        try { await sendTeleport(next, false); shadow = next; log('turned 180°', 'success'); }
        catch (e) { log(`turn180: ${e.message}`, 'error'); }
    } else if (kind === 'possess') {
        const botId = getSelectedBotId();
        const p = getPrimaryPlayer();
        if (!botId || !p) { log('select a bot first', 'error'); return; }
        try {
            const ctx = { playerUid: p.uid, botId: Number(botId), actor: 'user' };
            await api.command('select', [String(botId)], ctx);
            const r = await api.command('possess', [], ctx);
            log(`possess #${botId}: ${r?.Message || 'ok'}`, r?.Ok ?? r?.ok ? 'success' : 'error');
        } catch (e) { log(`possess: ${e.message}`, 'error'); }
    } else if (kind === 'unpossess') {
        const p = getPrimaryPlayer();
        if (!p) return;
        const r = await api.command('unpossess', [], { playerUid: p.uid, actor: 'user' }).catch(e => ({ Ok: false, Message: e.message }));
        log(`unpossess: ${r.Message || 'ok'}`, r.Ok ? 'success' : 'error');
    } else if (kind === 'screenshot-obs') {
        await captureFrame();
    } else if (kind === 'scan') {
        // "scan" the SELECTED BOT = its state endpoint (/polis/state?botId=).
        // (The harness `scan` command is a world-REGION scanner taking a
        // cube — 2026-09-27 sweep: calling it with a bot id errors.)
        const botId = getSelectedBotId();
        if (botId == null) { log('select a bot to scan', 'error'); return; }
        try {
            const s = await api.getState(botId);
            const b = s?.Bot ?? s?.bot ?? {};
            const contents = b.BackpackContents ?? b.backpackContents;
            const bp = Array.isArray(contents) ? contents.length
                : (b.Backpack ?? b.backpack ? 'has backpack' : '—');
            log(`bot #${botId}: hp ${b.CurrentHealth ?? b.currentHealth ?? '?'} | right ${b.RightHand ?? b.rightHand ?? '—'} | left ${b.LeftHand ?? b.leftHand ?? '—'} | backpack ${bp}`, 'success');
        } catch (e) { log(`scan #${botId}: ${e.message}`, 'error'); }
    } else if (kind === 'stop') {
        // The always-visible override (webui-mobile.md): stop the selected
        // bot's current action — bot.Activity.CancelAll() server-side.
        const ctx = { actor: 'user' };
        const botId = getSelectedBotId();
        if (botId != null) ctx.botId = Number(botId);
        const r = await api.command('stop', [], ctx).catch(e => ({ Ok: false, Message: e.message }));
        log(`stop: ${r.Message || (r.Ok ? 'ok' : 'failed')}`, r.Ok ? 'success' : 'error');
        setAgentStep(null);
        pollStatus();
    }
}
function getSelectedBotId() {
    const sel = state.selection;
    return sel.type === SelectionType.BOT ? sel.id : state.selectedBotId;
}

/* button wiring: pointer hold */
function wireHolds() {
    document.querySelectorAll('[data-hold]').forEach(btn => {
        const kind = btn.dataset.hold;
        btn.addEventListener('pointerdown', (e) => {
            e.preventDefault();
            try { btn.setPointerCapture?.(e.pointerId); } catch (err) { /* synthetic/invalid id: proceed without capture */ }
            startHold(kind);
        });
        btn.addEventListener('pointerup',    () => stopHold(kind));
        btn.addEventListener('pointercancel',() => stopHold(kind));
        btn.addEventListener('pointerleave', () => stopHold(kind));
        btn.addEventListener('contextmenu',  (e) => e.preventDefault());
    });
    document.querySelectorAll('[data-oneshot]').forEach(btn => {
        btn.addEventListener('click', () => oneshot(btn.dataset.oneshot));
    });
}

/* keyboard: WASD + arrows, same hold semantics. The handler yields to
   EVERY text control (chat box, command line, anything focusable) -
   while you are typing, keys are yours, not the bot's (2026-09-28:
   the Oikistes chat input was not in the guard; typing "w" moved the
   bot and the character was eaten by preventDefault). */
const KEYMAP = {
    KeyW: 'forward', ArrowUp: 'forward',
    KeyS: 'backward', ArrowDown: 'backward',
    KeyA: 'left', ArrowLeft: 'left',
    KeyD: 'right', ArrowRight: 'right',
};
function typingTarget(e) {
    const t = e.target;
    return !!(t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA'
                    || t.isContentEditable));
}
function wireKeys() {
    window.addEventListener('keydown', (e) => {
        if (typingTarget(e)) return;
        const kind = KEYMAP[e.code];
        if (!kind || e.repeat) return;
        e.preventDefault();
        startHold(kind);
    });
    window.addEventListener('keyup', (e) => {
        const kind = KEYMAP[e.code];
        if (kind) stopHold(kind);
    });
    window.addEventListener('blur', () => Object.keys(KEYMAP).forEach(k => stopHold(KEYMAP[k])));
}

/* ── rendering ────────────────────────────────────────────────────────── */

function renderTopbar() {
    const c = state.connection;
    el.conn.classList.toggle('connected', c.connected);
    el.conn.classList.toggle('disconnected', !c.connected);
    el.connLabel.textContent = c.connected ? 'ONLINE' : 'OFFLINE';
    renderSelectionInfo();
}

function renderSelectionInfo() {
    const sel = state.selection;
    if (sel.type === SelectionType.BOT) el.selectionInfo.textContent = `bot #${sel.id}`;
    else if (sel.type === SelectionType.PLAYER) el.selectionInfo.textContent = `player ${sel.data?.name || sel.id}`;
    else el.selectionInfo.textContent = 'no selection';
}

function renderEntityLists() {
    // bots
    const bots = [...state.bots.values()].sort((a, b) => a.id - b.id);
    el.botCount.textContent = String(bots.length);
    el.botIdLabel.textContent = state.selection.type === SelectionType.BOT ? `#${state.selection.id}` : '';
    if (bots.length === 0) {
        el.botsList.innerHTML = '<div class="placeholder">none loaded</div>';
    } else {
        el.botsList.innerHTML = bots.map(b => {
            const sel = state.selection.type === SelectionType.BOT && state.selection.id === b.id;
            const dot = b.loaded ? 'ok' : '';
            const pos = b.pos && b.pos.length === 3 ? `x${b.pos[0].toFixed(0)} y${b.pos[1].toFixed(0)} z${b.pos[2].toFixed(0)}` : '';
            return `<div class="entity-item ${sel ? 'selected' : ''}" data-bot="${b.id}">
                <span class="e-dot ${dot}"></span>
                <span class="e-name mono">#${b.id}</span>
                <span class="e-state">${pos}</span>
            </div>`;
        }).join('');
    }

    // players
    const players = [...state.players.values()];
    el.playerCount.textContent = String(players.length);
    if (players.length === 0) {
        el.playersList.innerHTML = '<div class="placeholder">none online</div>';
    } else {
        el.playersList.innerHTML = players.map(p => {
            const sel = state.selection.type === SelectionType.PLAYER && state.selection.id === p.uid;
            return `<div class="entity-item ${sel ? 'selected' : ''}" data-player="${escapeHtml(p.uid)}">
                <span class="e-dot ok"></span>
                <span class="e-name">${escapeHtml(p.name)}</span>
                <span class="e-state mono">${p.pos?.length === 3 ? `x${(+p.pos[0]).toFixed(0)} z${(+p.pos[2]).toFixed(0)}` : ''}</span>
            </div>`;
        }).join('');
    }

    // selection handlers (delegated once would also do; rebind is cheap at this size)
    el.botsList.querySelectorAll('[data-bot]').forEach(node => {
        node.onclick = () => { state.select(SelectionType.BOT, +node.dataset.bot); renderEntityLists(); renderBotActions(); };
    });
    el.playersList.querySelectorAll('[data-player]').forEach(node => {
        node.onclick = () => { state.select(SelectionType.PLAYER, node.dataset.player); renderEntityLists(); };
    });

    renderPlayerMeta();
}

function renderPlayerMeta() {
    if (shadow) {
        const yawDeg = (wrapAngle(shadow.yaw) * 180 / Math.PI).toFixed(0);
        const pitchDeg = (shadow.pitch * 180 / Math.PI).toFixed(0);
        el.playerMeta.textContent =
            `pos  ${shadow.x.toFixed(1)}, ${shadow.y.toFixed(1)}, ${shadow.z.toFixed(1)}\n` +
            `view yaw ${yawDeg}°  pitch ${pitchDeg}°`;
    } else {
        const p = getPrimaryPlayer();
        el.playerMeta.textContent = p ? 'pose unknown' : 'no player online';
    }
}

function renderBotActions() {
    const botId = getSelectedBotId();
    if (botId == null) {
        el.botActions.innerHTML = '<div class="placeholder">select a bot</div>';
        return;
    }
    el.botActions.innerHTML = `
        <button class="act" data-oneshot="screenshot-obs">observer screenshot</button>
        <button class="act" data-oneshot="scan">scan — dump bot state</button>
        <button class="act danger" data-oneshot="despawn">despawn bot</button>`;
    el.botActions.querySelectorAll('[data-oneshot]').forEach(b =>
        b.addEventListener('click', () => oneshotBotAction(b.dataset.oneshot, botId)));
}

async function oneshotBotAction(kind, botId) {
    if (kind === 'despawn') {
        // explicit botId in context (C# TryGetHarnessBot prefers it over
        // selection); the select-first keeps the game's own selection state
        // in sync for anyone watching in the world.
        const ctx = { botId: Number(botId), actor: 'user' };
        await api.command('select', [String(botId)], ctx).catch(() => null);
        const r = await api.command('despawn', [String(botId)], ctx).catch(e => ({ Ok: false, Message: e.message }));
        log(`despawn #${botId}: ${r.Message || 'ok'}`, r.Ok ? 'success' : 'error');
        renderBotActions();
    } else {
        oneshot(kind);
    }
}

/* ── stage: vnc / frames ──────────────────────────────────────────────── */

let stageView = 'vnc';
let framesTimer = null;

function setStageView(view) {
    stageView = view;
    el.tabs.querySelectorAll('.stage-tab').forEach(t => t.classList.toggle('active', t.dataset.view === view));
    el.toolsVnc.hidden = view !== 'vnc';
    el.toolsFrames.hidden = view !== 'frames';
    el.novnc.hidden = view !== 'vnc';
    el.framesImg.hidden = view !== 'frames';
}

function connectStream() {
    // same-origin through the proxy (see config.js) — the old <host>:6080
    // auto-detect is gone; the 8586 proxy routes /vnc/* to websockify.
    const base = CONFIG.NOVNC_BASE || window.location.origin;
    el.novnc.src = `${base}${CONFIG.NOVNC_PATH}?${CONFIG.NOVNC_PARAMS}`;
    el.streamStatus.textContent = 'connecting';
    el.streamStatus.className = 'stream-status dim';
    el.novnc.onload = () => { el.streamStatus.textContent = 'stream on'; el.streamStatus.className = 'stream-status ok'; };
}
function disconnectStream() {
    el.novnc.src = '';
    el.streamStatus.textContent = 'stream off';
    el.streamStatus.className = 'stream-status dim';
}

// ── Frame rendering (canvas-based, 2026-09-27) ─────────────────────────
// Captured frames are decoded into a pair of canvases (an offscreen
// full-resolution buffer + the visible letterboxed surface) and
// overwritten in place. The old code set a FRESH data: URL on the <img>
// for every frame; Blink keeps every unique data: bitmap in the renderer
// cache until the page dies, so any long-lived monitoring page grew
// without bound (measured: 7.5 GB of bitmaps in one headless page left
// open, 2026-09-27 — it OOM-risked the box running the session daemon).
let frameBuffer = null;        // offscreen canvas at capture resolution
let frameBufferCtx = null;

async function renderFrameImage(base64) {
    const cv = el.framesImg;
    const ctx = cv.getContext('2d');
    const mime = base64.startsWith('/9j/') ? 'image/jpeg' : 'image/png';
    const bytes = Uint8Array.from(atob(base64), c => c.charCodeAt(0));
    let bitmap;
    if (window.createImageBitmap) {
        bitmap = await createImageBitmap(new Blob([bytes], { type: mime }));
    } else {
        // fallback: decode via a one-shot blob URL (revoked after use)
        const u = URL.createObjectURL(new Blob([bytes], { type: mime }));
        bitmap = await new Promise((res, rej) => {
            const im = new Image();
            im.onload = () => { URL.revokeObjectURL(u); res(im); };
            im.onerror = () => { URL.revokeObjectURL(u); rej(new Error('decode failed')); };
            im.src = u;
        });
    }
    if (!frameBuffer || frameBuffer.width !== bitmap.width || frameBuffer.height !== bitmap.height) {
        frameBuffer = document.createElement('canvas');
        frameBuffer.width = bitmap.width;
        frameBuffer.height = bitmap.height;
        frameBufferCtx = frameBuffer.getContext('2d');
    }
    frameBufferCtx.drawImage(bitmap, 0, 0);
    if (bitmap.close) bitmap.close();

    // letterbox-composite into the visible surface (constant size)
    const vw = cv.clientWidth, vh = cv.clientHeight;
    if (vw && vh && (cv.width !== vw || cv.height !== vh)) {
        cv.width = vw; cv.height = vh;
    }
    if (cv.width && cv.height) {
        const s = Math.min(cv.width / frameBuffer.width, cv.height / frameBuffer.height);
        const dw = frameBuffer.width * s, dh = frameBuffer.height * s;
        ctx.fillStyle = '#060708';
        ctx.fillRect(0, 0, cv.width, cv.height);
        ctx.drawImage(frameBuffer, (cv.width - dw) / 2, (cv.height - dh) / 2, dw, dh);
    }
}

async function captureFrame() {
    // Observer screenshot = point-of-view snapshot: the harness sets the
    // player's view to the (current) pose, captures, restores — so passing
    // the player's own pos/orientation is a no-op teleport. See the old
    // js/ui/screenshot.js comment (2026-09-21).
    try {
        el.shotStatus.textContent = 'capturing';
        el.shotStatus.className = 'stream-status dim';
        const base = getApiBase();
        const players = await (await fetch(`${base}/polis/players`)).json();
        const plist = (Array.isArray(players) ? players : (players.players || [])).filter(p => p && p.uid);
        if (!plist.length) throw new Error('no online player');
        const p = plist.find(pp => pp.uid === getPrimaryPlayer()?.uid) || plist[0];
        const me = await (await fetch(`${base}/polis/player?uid=${encodeURIComponent(p.uid)}`)).json();
        if (!me || me.error || !me.pos) throw new Error(me?.error || 'player not loaded');
        const [x, y, z] = me.pos;
        const shot = await (await fetch(`${base}/polis/observer-screenshot?x=${x}&y=${y}&z=${z}&yaw=${me.yaw}&pitch=${me.pitch}&playerUid=${encodeURIComponent(p.uid)}`)).json();
        if (!shot.ok) throw new Error(shot.error || 'screenshot failed');
        await renderFrameImage(shot.base64Png);
        el.shotStatus.textContent = `frame ${new Date().toLocaleTimeString('en-GB', { hour12: false })}`;
        el.shotStatus.className = 'stream-status ok';
        if (stageView !== 'frames') setStageView('frames');
    } catch (e) {
        el.shotStatus.textContent = `error: ${e.message}`;
        el.shotStatus.className = 'stream-status err';
    }
}

function wireStage() {
    el.tabs.querySelectorAll('.stage-tab').forEach(t => t.addEventListener('click', () => setStageView(t.dataset.view)));
    el.streamEnabled.addEventListener('change', () => el.streamEnabled.checked ? connectStream() : disconnectStream());
    el.btnShot.addEventListener('click', captureFrame);
    el.framesAuto.addEventListener('change', () => {
        if (framesTimer) { clearInterval(framesTimer); framesTimer = null; }
        if (el.framesAuto.checked) framesTimer = setInterval(captureFrame, CONFIG.SCREENSHOT_INTERVAL_MS);
    });
    connectStream();
    // The noVNC iframe streams VNC rects for as long as the page is
    // "visible" — and the VNC client inside it accumulates image data in
    // the renderer as it goes (long-lived tabs put real load on the VNC
    // server and the viewing renderer). The stream is a viewing aid only;
    // every other view (state, bots, logs) works without it. So pause it
    // while the tab is hidden and resume when it comes back. (Headless
    // pages report visible forever — this protects human tabs only.)
    document.addEventListener('visibilitychange', () => {
        if (document.hidden) {
            disconnectStream();
        } else if (el.streamEnabled.checked && stageView === 'vnc') {
            connectStream();
        }
    });
}

/* ── polling ──────────────────────────────────────────────────────────── */

let statusTimer = null, eventTimer = null, clockTimer = null, lastEventTs = 0;

async function pollStatus() {
    try {
        const data = await api.getStatus();
        state.updateFromStatus(data);
        const [bots, players, vitals] = await Promise.all([
            api.getBots().catch(() => null),
            api.getPlayers().catch(() => null),
            api.getVitals().catch(() => null),
        ]);
        if (bots) state.updateFromBots(bots);
        if (players) state.updateFromPlayers(players);
        if (vitals) state.updateFromVitals(vitals);
        if (state.selectedBotId) {
            const s = await api.getState(state.selectedBotId).catch(() => null);
            if (s) state.updateFromState(s);
        }
        resyncShadowFromServer();
    } catch (e) {
        state.setConnected(false);
    }
}

async function pollEvents() {
    try {
        const data = await api.getEvents(20);
        if (!data?.ok || !data.events) return;
        const fresh = data.events.filter(e => e.ts > lastEventTs);
        if (fresh.length) {
            lastEventTs = Math.max(...fresh.map(e => e.ts));
            fresh.reverse().forEach(handleEvent);
        }
    } catch (e) { /* silent */ }
}

function handleEvent(ev) {
    const { type, data } = ev;
    const pos = (p) => p ? `(${p.map(n => +n).map(n => n.toFixed(1)).join(', ')})` : '';
    switch (type) {
        // Actor-tagged command event (2026-09-27): the action stream.
        // UI-originated commands are already logged by the button handlers
        // (avoid double lines); everything else — the v5 loop ("harness"),
        // the Oikistes ("agent"), devops — lands here with a badge.
        case 'command': {
            if (data.actor === 'user') break;
            const ok = data.ok;
            const msg = ok ? (data.msg || `cmd ${data.cmd}`) : `${data.cmd} — ${data.msg || 'failed'}`;
            log(msg, ok ? '' : 'error', data.actor);
            if (data.actor === 'agent' || data.actor === 'harness') setAgentStep(`${data.actor} · ${msg}`);
            break;
        }
        case 'action_complete':  log(`[action] ${data.action}: ${data.msg}`, data.ok ? 'success' : 'error'); setAgentStep(`action · ${data.action}`); pollStatus(); break;
        case 'bot_spawned':      log(`[spawn] #${data.botId} ${pos(data.pos)}`); pollStatus(); break;
        case 'bot_died':         log(`[death] #${data.botId} ${data.cause || ''}`, 'error'); pollStatus(); break;
        case 'bot_unloaded':     log(`[unload] #${data.botId}`); pollStatus(); break;
        case 'log':              log(`[${data.category || 'debug'}] ${data.msg}`); break;
        case 'debug_toggled':    log(`[debug] ${data.enabled ? 'on' : 'off'}`); break;
        default:                 log(`[${type}] ${JSON.stringify(data)}`);
    }
}

async function pollClock() {
    // A GET, not the `time` command (2026-10-04): the command recorded an
    // event per poll, flooding the log and the agent's action stream with
    // world-clock heartbeats on long-open pages.
    try {
        const c = await api.getClock();
        if (c?.ok) el.worldClock.textContent = c.date || '';
    } catch (e) { /* clock is decorative */ }
}

/* ── current step (2026-10-04, webui-mobile.md) ────────────────────────
   One line in the top bar: what the autonomous side (the v5 loop =
   "harness", the Oikistes = "agent") is doing right now. Derived from the
   event stream the page already polls — no new endpoint. It is the
   last agent/harness-actor event, never cleared: the most recent thing
   the agent did is still the right thing to show a returning operator. */
function setAgentStep(text) {
    if (!el.currentStep) return;
    el.currentStep.textContent = text || '—';
    el.currentStep.title = text || '';
}


/* ── command bar ──────────────────────────────────────────────────────── */

async function executeCommand(raw) {
    const trimmed = raw.trim();
    if (!trimmed) return;
    const parts = trimmed.split(/\s+/);
    log(`> ${trimmed}`, 'cmd');
    try {
        // actor: "user" (2026-09-27) — the command event carries who did it;
        // the UI suppresses echoing user-tagged events (we log locally).
        const r = await api.command(parts[0], parts.slice(1), { actor: 'user' });
        state.recordAction(parts[0], parts.slice(1), r);
        const msg = r?.Message || r?.message || JSON.stringify(r);
        log(`${parts[0]}: ${msg}`, (r?.Ok ?? r?.ok) ? 'success' : 'error');
        pollStatus();
    } catch (e) {
        log(`${parts[0]}: ${e.message}`, 'error');
    }
}

function wireConsole() {
    el.cmdInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') { executeCommand(el.cmdInput.value); el.cmdInput.value = ''; }
    });
    el.cmdSubmit.addEventListener('click', () => { executeCommand(el.cmdInput.value); el.cmdInput.value = ''; });
    el.btnResync.addEventListener('click', () => {
        shadow = null;
        pollStatus();
        log('pose re-synced from server');
    });
    // Mobile (webui-mobile.md): the command bar is pinned above the tab
    // bar on every page; focusing the input expands a log preview above
    // it, blurring collapses it again.
    el.cmdInput.addEventListener('focus', () => {
        if (document.body.classList.contains('m-nav') && document.body.dataset.mpage !== 'console') {
            document.body.classList.add('m-cmd-expanded');
        }
    });
    el.cmdInput.addEventListener('blur', () => document.body.classList.remove('m-cmd-expanded'));
}

/* ── mobile / field variant (2026-10-04, docs/design/webui-mobile.md) ──
   Below 860 px the single desktop grid becomes five one-at-a-time pages
   (body[data-mpage]), each owning the whole screen — the bottom tab bar
   is the only navigation (always visible, thumb-reachable). The CSS
   (main.css) does the layout; this wires the bar and the m-nav class
   the mobile rules key on. Default page is Stage: the console's center
   of gravity is the live image, and a field operator opens the UI to
   SEE, not to find the video. */
function wireMobile() {
    const mq = matchMedia('(max-width: 859px)');
    const apply = () => document.body.classList.toggle('m-nav', mq.matches);
    apply();
    mq.addEventListener?.('change', apply);
    const tabs = document.querySelectorAll('#mobile-tabs .mtab');
    const setActive = (page) => tabs.forEach(b => b.classList.toggle('active', b.dataset.mpage === page));
    tabs.forEach(b => b.addEventListener('click', () => {
        document.body.dataset.mpage = b.dataset.mpage;
        document.body.classList.remove('m-cmd-expanded');
        setActive(b.dataset.mpage);
    }));
    setActive(document.body.dataset.mpage || 'stage');
}

/* ── Oikistes (2026-09-27 re-scope, inaugurated 2026-09-28) ────────────
   The settlement agent: a 35B-class model with a tool surface over the
   harness. The autonomy control is LIVE (mod-owned world config; the
   agent only reads it, the execution path enforces it). The chat is a
   live loop - the agent observes (state/scan/screenshot/events),
   orders work through the R2 job system (mission tool), and answers in
   plain text. Every actuation it performs carries actor=oikistes and
   lands in the event stream with a badge. */

const oik = {
    log: () => $('oikistesLog'),
    input: () => $('oikistesInput'),
    send: () => $('oikistesSend'),
    select: () => $('autonomySelect'),
    brain: () => $('oikBrain'),
};

function oikLog(text, cls = '') {
    const box = oik.log();
    const line = document.createElement('div');
    line.className = `log-line ${cls}`;
    line.innerHTML = `<span class="t">${new Date().toLocaleTimeString('en-GB', { hour12: false })}</span>${escapeHtml(text)}`;
    box.appendChild(line);
    box.scrollTop = box.scrollHeight;
    return line;
}

async function loadAutonomy() {
    try {
        const r = await api.command('autonomy', ['get']);
        const sel = oik.select();
        if (r?.Ok && r?.Data?.preset) {
            sel.value = r.Data.preset;
        }
    } catch (e) { /* autonomy is mod-owned; quiet if the world is away */ }
}

async function setAutonomy(preset) {
    try {
        const r = await api.command('autonomy', ['set', preset], { actor: 'user' });
        oikLog(r?.Ok ? `autonomy → ${preset} (mod-owned config — the agent reads it every turn)` : `autonomy set failed: ${r?.Message}`, r?.Ok ? 'success' : 'error');
    } catch (e) { oikLog(`autonomy set failed: ${e.message}`, 'error'); }
}

async function oikStatus() {
    try {
        const r = await (await fetch('/polis/oikistes/status')).json();
        const sel = oik.brain();
        if (r.models) {
            for (const [k, id] of Object.entries(r.models)) {
                let opt = [...sel.options].find(o => o.value === k);
                if (!opt) { opt = new Option('', k, false, false); sel.add(opt); }
                opt.textContent = `${k} · ${id}`;
            }
            sel.value = r.brain || 'primary';
        }
        oikLog(`Oikistes ready — brain ${r.brain} (${r.model}), autonomy ${r.autonomy}, body ${r.bot != null ? 'bot ' + r.bot : 'spawning…'}`);
        return r;
    } catch (e) {
        oikLog(`Oikistes service unreachable (${e.message}) — messages will fail until it is back.`, 'error');
        return null;
    }
}

async function oikSetBrain(brain) {
    try {
        const res = await fetch('/polis/oikistes/model', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ brain }),
        });
        const r = await res.json();
        if (r.error) { oikLog(r.error, 'error'); return; }
        oikLog(`brain → ${r.brain} (${r.model})`);
    } catch (e) { oikLog(`brain switch failed: ${e.message}`, 'error'); }
}

async function oikTranscript(n = 24) {
    try {
        const r = await (await fetch(`/polis/oikistes/transcript?n=${n}`)).json();
        for (const rec of r) {
            if (rec.role === 'user') oikLog(`${rec.actor ?? 'user'}: ${rec.text}`);
            else oikLog(rec.text, 'oik');
        }
    } catch (e) { /* fresh install: nothing yet */ }
}

let oikBusy = false;

async function oikSend() {
    const input = oik.input();
    const t = input.value.trim();
    if (!t || oikBusy) return;
    oikBusy = true;
    oik.send().disabled = true;
    oikLog(`you: ${t}`);
    input.value = '';
    const pending = oikLog('…', 'dim');
    try {
        const res = await fetch('/polis/oikistes/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: t, actor: 'user' }),
        });
        pending.remove();
        if (!res.ok) {
            if (res.status === 429) {
                oikLog(`Oikistes is busy (a chat/mission is in flight) - try again in a moment.`, 'error');
                return;
            }
            oikLog(`Oikistes error (HTTP ${res.status})`, 'error');
            return;
        }
        const d = await res.json();
        for (const a of (d.actions || [])) {
            const denied = String(a.observation || '').startsWith('DENIED');
            oikLog(`⚙ ${a.tool} ${JSON.stringify(a.args || {})} → ${String(a.observation || '').slice(0, 160)}`, denied ? 'error' : 'act');
        }
        if (d.error) oikLog(`agent error: ${d.error}`, 'error');
        oikLog(d.reply || '(no reply)', 'oik');
    } catch (e) {
        pending.remove();
        oikLog(`Oikistes unreachable: ${e.message} (the service may be mid-restart)`, 'error');
    } finally {
        oikBusy = false;
        oik.send().disabled = false;
        input.focus();
    }
}

function wireOikistes() {
    oik.select().addEventListener('change', (e) => setAutonomy(e.target.value));
    oik.brain().addEventListener('change', (e) => oikSetBrain(e.target.value));
    oik.send().addEventListener('click', oikSend);
    oik.input().addEventListener('keydown', (e) => { if (e.key === 'Enter') oikSend(); });
    loadAutonomy();
    oikTranscript().then(() => oikStatus());
}

/* ── theme (auto / dark / light; auto follows the OS) ─────────────────── */

const themeEl = $('theme-toggle');
let themePick = (() => {
    const p = localStorage.getItem('polis-theme');
    return (p === 'dark' || p === 'light' || p === 'auto') ? p : 'auto';
})();

function applyTheme() {
    const resolved = themePick === 'auto'
        ? (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
        : themePick;
    document.documentElement.dataset.theme = resolved;
    themeEl.querySelectorAll('button').forEach(b =>
        b.classList.toggle('active', b.dataset.themePick === themePick));
}
function wireTheme() {
    themeEl.querySelectorAll('button').forEach(b => {
        b.addEventListener('click', () => {
            themePick = b.dataset.themePick;
            localStorage.setItem('polis-theme', themePick);
            applyTheme();
        });
    });
    matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
        if (themePick === 'auto') applyTheme();
    });
    applyTheme();
}

/* ── diagnostics: the bug-report artifact ───────────────────────────────
 * Every network call this page makes, every JS error/rejection, the log
 * tail and the current state. One click → JSON file + clipboard. This is
 * what a bug report looks like: an artifact, not a prose guess.          */

const DIAG = { net: [], err: [] };
const _realFetch = window.fetch.bind(window);
function _shortUrl(u) {
    try { return new URL(u, location.href).pathname; } catch (e) { return String(u).slice(0, 120); }
}
window.fetch = async (input, init) => {
    const t0 = performance.now();
    const url = typeof input === 'string' ? input : (input && input.url) || '';
    const method = (init && init.method) || (input && input.method) || 'GET';
    const rec = { t: Date.now(), method, url: _shortUrl(url) };
    try {
        const res = await _realFetch(input, init);
        rec.status = res.status;
        rec.ms = Math.round(performance.now() - t0);
        if (rec.status >= 400) {
            try { rec.body = (await res.clone().text()).slice(0, 300); } catch (e) { /* ignore */ }
        }
        DIAG.net.push(rec);
        if (DIAG.net.length > 400) DIAG.net.shift();
        return res;
    } catch (e) {
        rec.error = String(e && e.message || e);
        rec.ms = Math.round(performance.now() - t0);
        DIAG.net.push(rec);
        if (DIAG.net.length > 400) DIAG.net.shift();
        throw e;
    }
};
window.addEventListener('error', (e) => {
    DIAG.err.push({ t: Date.now(), type: 'error', msg: e.message, at: `${e.filename || ''}:${e.lineno || ''}` });
    if (DIAG.err.length > 200) DIAG.err.shift();
});
window.addEventListener('unhandledrejection', (e) => {
    DIAG.err.push({ t: Date.now(), type: 'unhandledrejection', msg: String(e.reason && e.reason.message || e.reason).slice(0, 400) });
    if (DIAG.err.length > 200) DIAG.err.shift();
});

function exportDiagnostics() {
    const blob = {
        app: 'polis-webui',
        built: '2026-09-27',
        ts: new Date().toISOString(),
        url: location.href,
        viewport: `${innerWidth}x${innerHeight}`,
        theme: { pick: themePick, resolved: document.documentElement.dataset.theme },
        connection: {
            connected: state.connection.connected,
            worldReady: state.connection.worldReady,
            lastCheck: state.connection.lastCheck || null,
        },
        selection: { type: state.selection.type, id: state.selection.id },
        bots: [...state.bots.values()].map(b => ({ id: b.id, loaded: b.loaded, pos: b.pos })),
        players: [...state.players.values()].map(p => ({ uid: p.uid, name: p.name, pos: p.pos, yaw: p.yaw, pitch: p.pitch })),
        jsErrors: DIAG.err,
        network: DIAG.net.slice(-120),
        logTail: [...el.log.children].slice(-40).map(n => n.textContent),
    };
    const s = JSON.stringify(blob, null, 1);
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([s], { type: 'application/json' }));
    a.download = `polis-ui-diag-${new Date().toISOString().replace(/[:.]/g, '-')}.json`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 10000);
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(s).catch(() => {});
    log('diagnostics exported (file + clipboard)', 'success');
}

/* ── init ─────────────────────────────────────────────────────────────── */

async function init() {
    try {
        await db.init();
        await state.loadPersistedState();
    } catch (e) {
        console.warn('persist layer unavailable', e);
    }

    wireHolds();
    wireKeys();
    wireStage();
    wireConsole();
    wireTheme();
    wireMobile();
    $('btn-diag').addEventListener('click', exportDiagnostics);

    state.onChange((type) => {
        if (['bots', 'players', 'selection'].includes(type)) renderEntityLists();
        if (type === 'selection') { renderBotActions(); renderSelectionInfo(); }
        if (type === 'connection') renderTopbar();
    });
    api.onConnectionChange((connected) => state.setConnected(connected));

    lastEventTs = Date.now();
    statusTimer = setInterval(pollStatus, CONFIG.POLL_STATUS_MS);
    eventTimer = setInterval(pollEvents, CONFIG.POLL_EVENTS_MS);
    clockTimer = setInterval(pollClock, 5000);
    wireOikistes();
    pollStatus(); pollEvents(); pollClock();

    renderTopbar();
    renderEntityLists();
    renderBotActions();
    setStageView('vnc');
    log('Polis UI ready', 'success');
}

window.polis = { api, state, log, pollStatus, DIAG, startHold, stopHold };

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
else init();
