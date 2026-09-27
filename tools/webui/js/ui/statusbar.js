/**
 * Polis Web UI - Status Bar
 *
 * Connection status indicator and selection display.
 */

import { state, SelectionType } from '../state.js';

/**
 * Status bar component
 */
class StatusBar {
    constructor() {
        this._elements = {
            indicator: null,
            worldName: null,
            selectedEntity: null,
        };
        this._unsubscribe = null;
    }

    /**
     * Initialize the status bar
     */
    init() {
        // Get DOM elements
        this._elements.indicator = document.getElementById('connection-indicator');
        this._elements.worldName = document.getElementById('world-name');
        this._elements.selectedEntity = document.getElementById('selected-entity');

        // Subscribe to state changes
        this._unsubscribe = state.onChange((type, s) => {
            this._handleStateChange(type, s);
        });

        // Initial render
        this._render();
    }

    /**
     * Destroy the status bar (cleanup)
     */
    destroy() {
        if (this._unsubscribe) {
            this._unsubscribe();
            this._unsubscribe = null;
        }
    }

    /**
     * Handle state changes
     */
    _handleStateChange(changeType) {
        switch (changeType) {
            case 'connection':
                this._renderConnection();
                break;
            case 'selection':
            case 'bots':
            case 'players':
                this._renderSelection();
                break;
            default:
                // For other changes, do a full render
                this._render();
        }
    }

    /**
     * Render the entire status bar
     */
    _render() {
        this._renderConnection();
        this._renderSelection();
    }

    /**
     * Render connection status
     */
    _renderConnection() {
        const { indicator, worldName } = this._elements;
        const conn = state.connection;

        if (indicator) {
            indicator.textContent = conn.connected ? 'Connected' : 'Disconnected';
            indicator.className = 'indicator ' + (conn.connected ? 'connected' : 'disconnected');
        }

        if (worldName) {
            if (conn.connected && conn.worldName) {
                worldName.textContent = conn.worldName;
            } else if (conn.connected) {
                worldName.textContent = conn.worldReady ? 'World Ready' : 'Loading...';
            } else {
                worldName.textContent = '-';
            }
        }
    }

    /**
     * Render selection status
     */
    _renderSelection() {
        const { selectedEntity } = this._elements;
        if (!selectedEntity) return;

        const sel = state.selection;

        switch (sel.type) {
            case SelectionType.BOT:
                selectedEntity.textContent = `Bot #${sel.id}`;
                if (sel.data?.pos) {
                    const [x, y, z] = sel.data.pos;
                    selectedEntity.title = `Position: ${x.toFixed(1)}, ${y.toFixed(1)}, ${z.toFixed(1)}`;
                }
                break;

            case SelectionType.PLAYER:
                const name = sel.data?.name || sel.id;
                selectedEntity.textContent = `Player: ${name}`;
                break;

            case SelectionType.BLOCK:
                if (sel.data) {
                    const code = sel.data.code || sel.data.Code || 'block';
                    const pos = sel.data.pos || sel.data.Pos;
                    selectedEntity.textContent = `Block: ${code}`;
                    if (pos) {
                        selectedEntity.title = `Position: ${pos[0]}, ${pos[1]}, ${pos[2]}`;
                    }
                } else {
                    selectedEntity.textContent = 'Block selected';
                }
                break;

            case SelectionType.ENTITY:
                const entityCode = sel.data?.code || sel.data?.Code || 'entity';
                selectedEntity.textContent = `Entity: ${entityCode} #${sel.id}`;
                break;

            default:
                selectedEntity.textContent = 'No selection';
                selectedEntity.title = '';
        }
    }

    /**
     * Update connection status directly (for API callbacks)
     */
    setConnected(connected) {
        state.setConnected(connected);
    }
}

// Export singleton instance
export const statusBar = new StatusBar();
