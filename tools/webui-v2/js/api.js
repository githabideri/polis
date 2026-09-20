/**
 * Polis Web UI v2 - API Client
 *
 * HTTP client for communicating with the polis harness.
 */

import { getApiBase, setApiBase } from './config.js';

/**
 * API Error with status and response data
 */
export class ApiError extends Error {
    constructor(message, status = 0, data = null) {
        super(message);
        this.name = 'ApiError';
        this.status = status;
        this.data = data;
    }
}

/**
 * Harness API Client
 */
class HarnessClient {
    constructor() {
        this._baseUrl = getApiBase();
        this._connected = false;
        this._listeners = new Set();
    }

    /**
     * Get current API base URL
     */
    get baseUrl() {
        return this._baseUrl;
    }

    /**
     * Set API base URL
     */
    set baseUrl(url) {
        this._baseUrl = setApiBase(url);
    }

    /**
     * Check if currently connected
     */
    get connected() {
        return this._connected;
    }

    /**
     * Subscribe to connection state changes
     * @param {function(boolean)} callback
     * @returns {function} Unsubscribe function
     */
    onConnectionChange(callback) {
        this._listeners.add(callback);
        return () => this._listeners.delete(callback);
    }

    /**
     * Set connection state and notify listeners
     */
    _setConnected(connected) {
        if (this._connected !== connected) {
            this._connected = connected;
            for (const listener of this._listeners) {
                try {
                    listener(connected);
                } catch (e) {
                    console.error('Connection listener error:', e);
                }
            }
        }
    }

    /**
     * Make a GET request
     * @param {string} path - API path (e.g., '/polis/status')
     * @param {Object} params - Query parameters
     * @returns {Promise<any>} Response data
     */
    async get(path, params = {}) {
        const url = new URL(this._baseUrl + path);
        for (const [key, value] of Object.entries(params)) {
            if (value !== undefined && value !== null) {
                url.searchParams.set(key, String(value));
            }
        }

        try {
            const response = await fetch(url.toString(), {
                method: 'GET',
                headers: {
                    'Accept': 'application/json',
                },
            });

            const data = await response.json();
            this._setConnected(true);

            if (!response.ok) {
                throw new ApiError(
                    data.message || data.Message || `HTTP ${response.status}`,
                    response.status,
                    data
                );
            }

            return data;
        } catch (e) {
            if (e instanceof ApiError) {
                throw e;
            }
            this._setConnected(false);
            throw new ApiError(e.message || 'Network error', 0, null);
        }
    }

    /**
     * Make a POST request
     * @param {string} path - API path
     * @param {Object} body - Request body
     * @returns {Promise<any>} Response data
     */
    async post(path, body = {}) {
        try {
            const response = await fetch(this._baseUrl + path, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                },
                body: JSON.stringify(body),
            });

            const data = await response.json();
            this._setConnected(true);

            if (!response.ok) {
                throw new ApiError(
                    data.message || data.Message || `HTTP ${response.status}`,
                    response.status,
                    data
                );
            }

            return data;
        } catch (e) {
            if (e instanceof ApiError) {
                throw e;
            }
            this._setConnected(false);
            throw new ApiError(e.message || 'Network error', 0, null);
        }
    }

    /**
     * Execute a command via the harness
     * @param {string} cmd - Command name
     * @param {string[]} args - Command arguments
     * @param {object|null} context - Optional command context (e.g. { playerUid })
     * @returns {Promise<any>} Command result
     */
    async command(cmd, args = [], context = null) {
        const body = { cmd, args };
        if (context && typeof context === 'object') {
            body.context = context;
        }
        return this.post('/polis/command', body);
    }

    /**
     * Get harness status
     */
    async getStatus() {
        return this.get('/polis/status');
    }

    /**
     * Get bot list
     */
    async getBots() {
        return this.get('/polis/bots');
    }

    /**
     * Get player list
     */
    async getPlayers() {
        return this.get('/polis/players');
    }

    /**
     * Get bot state
     * @param {number} botId - Optional bot ID
     */
    async getState(botId = null) {
        const params = botId ? { botId } : {};
        return this.get('/polis/state', params);
    }

    /**
     * Get recent events
     * @param {number} limit - Max events to return
     */
    async getEvents(limit = 20) {
        return this.get('/polis/events', { limit });
    }

    /**
     * Get targets near a bot
     * @param {number} botId
     * @param {number} radius
     * @param {string} mode - 'all', 'blocks', 'entities'
     */
    async getTargets(botId, radius = 16, mode = 'all') {
        return this.get('/polis/targets', { botId, radius, mode });
    }
}

// Export singleton instance
export const api = new HarnessClient();

// Also export the class for testing
export { HarnessClient };
