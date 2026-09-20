/**
 * Polis Web UI v2 - State Management
 *
 * In-memory world model with change notifications.
 */

import { db } from './db.js';

/**
 * Selection types
 */
export const SelectionType = {
    NONE: 'none',
    BOT: 'bot',
    PLAYER: 'player',
    BLOCK: 'block',
    ENTITY: 'entity',
};

/**
 * Create the state store
 */
function createState() {
    // Private state
    const _state = {
        // Connection state
        connection: {
            connected: false,
            lastCheck: null,
            worldName: null,
            worldReady: false,
        },

        // Entity collections (Map for O(1) lookup)
        bots: new Map(),       // id -> bot data
        players: new Map(),    // uid -> player data

        // Targets (from scans)
        targets: {
            blocks: [],
            entities: [],
        },

        // Current selection
        selection: {
            type: SelectionType.NONE,
            id: null,
            data: null,
        },

        // Last action result
        lastAction: {
            command: null,
            args: [],
            result: null,
            timestamp: null,
        },

        // Selected bot ID (persisted)
        selectedBotId: null,
    };

    // Listeners
    const _listeners = new Set();

    /**
     * Notify all listeners of state change
     */
    function notifyChange(changeType = 'update') {
        for (const listener of _listeners) {
            try {
                listener(changeType, _state);
            } catch (e) {
                console.error('State listener error:', e);
            }
        }
    }

    return {
        /**
         * Get connection state
         */
        get connection() {
            return { ..._state.connection };
        },

        /**
         * Get bots map
         */
        get bots() {
            return _state.bots;
        },

        /**
         * Get players map
         */
        get players() {
            return _state.players;
        },

        /**
         * Get targets
         */
        get targets() {
            return { ..._state.targets };
        },

        /**
         * Get current selection
         */
        get selection() {
            return { ..._state.selection };
        },

        /**
         * Get last action
         */
        get lastAction() {
            return { ..._state.lastAction };
        },

        /**
         * Get selected bot ID
         */
        get selectedBotId() {
            return _state.selectedBotId;
        },

        /**
         * Subscribe to state changes
         * @param {function(string, object)} callback - Called with (changeType, state)
         * @returns {function} Unsubscribe function
         */
        onChange(callback) {
            _listeners.add(callback);
            return () => _listeners.delete(callback);
        },

        /**
         * Update connection state from status API response
         */
        updateFromStatus(data) {
            _state.connection.lastCheck = Date.now();

            if (data.ok !== undefined) {
                _state.connection.connected = data.ok;
            }

            if (data.server) {
                _state.connection.worldReady = data.server.worldReady ?? false;
                _state.connection.worldName = data.server.worldName ?? null;
            }

            notifyChange('connection');
        },

        /**
         * Update bots from bots API response
         */
        updateFromBots(data) {
            if (!data.Ok && !data.ok) return;

            const botsData = data.Data?.bots || data.bots || [];
            const newBots = new Map();

            for (const bot of botsData) {
                const id = bot.Id ?? bot.id;
                if (id !== undefined) {
                    newBots.set(id, {
                        id,
                        loaded: bot.Loaded ?? bot.loaded ?? false,
                        pos: bot.Pos ?? bot.pos ?? null,
                        code: bot.Code ?? bot.code ?? 'EntityPlayerBot',
                        lastSeen: Date.now(),
                    });

                    // Persist to IndexedDB
                    db.entities.put({
                        id,
                        type: 'bot',
                        ...bot,
                        lastSeen: Date.now(),
                    }).catch(() => {}); // Ignore DB errors
                }
            }

            _state.bots = newBots;
            notifyChange('bots');
        },

        /**
         * Update players from players API response
         */
        updateFromPlayers(data) {
            const playersData = data.players || [];
            const newPlayers = new Map();

            for (const player of playersData) {
                const uid = player.uid;
                if (uid) {
                    newPlayers.set(uid, {
                        uid,
                        name: player.name ?? 'Unknown',
                        pos: player.pos ?? null,
                        eyePos: player.eyePos ?? null,
                        yaw: typeof player.yaw === 'number' ? player.yaw : null,
                        pitch: typeof player.pitch === 'number' ? player.pitch : null,
                        entityId: player.entityId ?? null,
                        lastSeen: Date.now(),
                        ...player,
                    });

                    // Persist to IndexedDB
                    db.entities.put({
                        id: uid,
                        type: 'player',
                        ...player,
                        lastSeen: Date.now(),
                    }).catch(() => {});
                }
            }

            _state.players = newPlayers;
            notifyChange('players');
        },

        /**
         * Update from state API response (selected bot state)
         */
        updateFromState(data) {
            if (data.Error) return;

            const bot = data.Bot;
            if (bot && bot.Id !== undefined) {
                // Update the bot in our collection
                const existing = _state.bots.get(bot.Id) || {};
                _state.bots.set(bot.Id, {
                    ...existing,
                    id: bot.Id,
                    loaded: true,
                    pos: bot.Pos ?? null,
                    health: bot.Health ?? null,
                    rightHand: bot.RightHand ?? null,
                    leftHand: bot.LeftHand ?? null,
                    backpack: bot.Backpack ?? null,
                    lastSeen: Date.now(),
                });

                // If this bot is selected, update selection data
                if (_state.selection.type === SelectionType.BOT &&
                    _state.selection.id === bot.Id) {
                    _state.selection.data = _state.bots.get(bot.Id);
                }
            }

            // Update last action if present
            if (data.LastAction) {
                _state.lastAction = {
                    command: data.LastAction.Name,
                    args: [],
                    result: { ok: data.LastAction.Ok, message: data.LastAction.Msg },
                    timestamp: Date.now(),
                };
            }

            notifyChange('state');
        },

        /**
         * Update from targets API response
         */
        updateFromTargets(data) {
            if (!data.Ok) return;

            _state.targets = {
                blocks: data.Blocks || [],
                entities: data.Entities || [],
            };

            notifyChange('targets');
        },

        /**
         * Select an entity
         */
        select(type, id, data = null) {
            // Look up data if not provided
            if (!data) {
                if (type === SelectionType.BOT) {
                    data = _state.bots.get(id) || null;
                } else if (type === SelectionType.PLAYER) {
                    data = _state.players.get(id) || null;
                }
            }

            _state.selection = { type, id, data };

            // Track selected bot for commands
            if (type === SelectionType.BOT) {
                _state.selectedBotId = id;
                // Persist selection
                db.settings.setValue('selectedBotId', id).catch(() => {});
            }

            notifyChange('selection');
        },

        /**
         * Clear selection
         */
        clearSelection() {
            _state.selection = {
                type: SelectionType.NONE,
                id: null,
                data: null,
            };
            notifyChange('selection');
        },

        /**
         * Set selected bot ID (for commands)
         */
        setSelectedBotId(id) {
            _state.selectedBotId = id;
            db.settings.setValue('selectedBotId', id).catch(() => {});
            notifyChange('selection');
        },

        /**
         * Record an action
         */
        recordAction(command, args, result) {
            _state.lastAction = {
                command,
                args,
                result,
                timestamp: Date.now(),
            };

            // Persist to IndexedDB
            db.actions.logAction(command, args, result).catch(() => {});

            notifyChange('action');
        },

        /**
         * Set connection state directly
         */
        setConnected(connected) {
            _state.connection.connected = connected;
            _state.connection.lastCheck = Date.now();
            notifyChange('connection');
        },

        /**
         * Load persisted state from IndexedDB
         */
        async loadPersistedState() {
            try {
                // Load selected bot ID
                const savedBotId = await db.settings.getValue('selectedBotId');
                if (savedBotId !== null) {
                    _state.selectedBotId = savedBotId;
                }

                // Load recent entities
                const entities = await db.entities.getAll();
                for (const entity of entities) {
                    if (entity.type === 'bot') {
                        _state.bots.set(entity.id, entity);
                    } else if (entity.type === 'player') {
                        _state.players.set(entity.id, entity);
                    }
                }

                notifyChange('loaded');
            } catch (e) {
                console.error('Failed to load persisted state:', e);
            }
        },
    };
}

// Export singleton state instance
export const state = createState();
