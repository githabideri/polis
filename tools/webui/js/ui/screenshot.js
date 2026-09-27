/**
 * Polis Web UI - Screenshot Pane
 *
 * Still-image view via /polis/observer-screenshot. The harness sets the
 * player's view, captures, and restores; passing the player's CURRENT
 * pos/orientation makes the "teleport" a no-op, so this is a plain
 * point-of-view snapshot without disturbing the player.
 */

import { getApiBase } from '../config.js';

async function getJson(path) {
    const r = await fetch(getApiBase() + '/polis' + path);
    if (!r.ok) throw new Error(`HTTP ${r.status} on ${path}`);
    return r.json();
}

export const screenshotPane = {
    timer: null,

    async capture() {
        const img = document.getElementById('shot-img');
        const status = document.getElementById('shot-status');
        if (!img) return;
        try {
            status.textContent = 'Capturing...';
            const players = await getJson('/players');
            const plist = (Array.isArray(players) ? players : (players.players || []))
                .filter(p => p && p.uid);
            if (!plist.length) throw new Error('no online player');
            const q = encodeURIComponent(plist[0].uid);
            const me = await getJson(`/player?uid=${q}`);
            if (!me || me.error || !me.pos) throw new Error(me && me.error ? me.error : 'player not loaded');
            const [x, y, z] = me.pos;
            const shot = await getJson(`/observer-screenshot?x=${x}&y=${y}&z=${z}` +
                `&yaw=${me.yaw}&pitch=${me.pitch}&playerUid=${q}`);
            if (!shot.ok) throw new Error(shot.error || 'screenshot failed');
            img.src = `data:image/png;base64,${shot.base64Png}`;
            status.textContent = `OK ${new Date().toLocaleTimeString()}`;
        } catch (e) {
            status.textContent = `Error: ${e.message}`;
        }
    },

    init() {
        const take = document.getElementById('shot-take');
        const auto = document.getElementById('shot-auto');
        if (!take) return;
        take.addEventListener('click', () => this.capture());
        if (auto) auto.addEventListener('change', () => {
            if (auto.checked) {
                this.capture();
                this.timer = setInterval(() => this.capture(), 5000);
            } else if (this.timer) {
                clearInterval(this.timer);
                this.timer = null;
            }
        });
    }
};
