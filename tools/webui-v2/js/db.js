/**
 * Polis Web UI v2 - IndexedDB Layer
 *
 * Persistent storage for entities, blocks, actions, and settings.
 */

import { CONFIG } from './config.js';

let dbInstance = null;

/**
 * Initialize the database
 * @returns {Promise<IDBDatabase>}
 */
async function initDatabase() {
    if (dbInstance) return dbInstance;

    return new Promise((resolve, reject) => {
        const request = indexedDB.open(CONFIG.DB_NAME, CONFIG.DB_VERSION);

        request.onerror = () => {
            reject(new Error('Failed to open IndexedDB: ' + request.error?.message));
        };

        request.onsuccess = () => {
            dbInstance = request.result;
            resolve(dbInstance);
        };

        request.onupgradeneeded = (event) => {
            const db = event.target.result;

            // Entities store: bots, players, mobs, items
            if (!db.objectStoreNames.contains('entities')) {
                const entityStore = db.createObjectStore('entities', { keyPath: 'id' });
                entityStore.createIndex('type', 'type', { unique: false });
                entityStore.createIndex('lastSeen', 'lastSeen', { unique: false });
            }

            // Blocks store: block data from scans
            if (!db.objectStoreNames.contains('blocks')) {
                const blockStore = db.createObjectStore('blocks', { keyPath: 'key' });
                blockStore.createIndex('chunkKey', 'chunkKey', { unique: false });
                blockStore.createIndex('code', 'code', { unique: false });
            }

            // Snapshots store: camera snapshots
            if (!db.objectStoreNames.contains('snapshots')) {
                const snapshotStore = db.createObjectStore('snapshots', {
                    keyPath: 'id',
                    autoIncrement: true
                });
                snapshotStore.createIndex('timestamp', 'timestamp', { unique: false });
            }

            // Actions store: command history
            if (!db.objectStoreNames.contains('actions')) {
                const actionStore = db.createObjectStore('actions', {
                    keyPath: 'id',
                    autoIncrement: true
                });
                actionStore.createIndex('timestamp', 'timestamp', { unique: false });
                actionStore.createIndex('command', 'command', { unique: false });
            }

            // Settings store: user preferences
            if (!db.objectStoreNames.contains('settings')) {
                db.createObjectStore('settings', { keyPath: 'key' });
            }
        };
    });
}

/**
 * Generic store wrapper with CRUD operations
 */
class StoreWrapper {
    constructor(storeName, keyPath = 'id') {
        this.storeName = storeName;
        this.keyPath = keyPath;
    }

    async _getStore(mode = 'readonly') {
        const db = await initDatabase();
        return db.transaction(this.storeName, mode).objectStore(this.storeName);
    }

    /**
     * Get a single record by key
     */
    async get(key) {
        const store = await this._getStore();
        return new Promise((resolve, reject) => {
            const request = store.get(key);
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });
    }

    /**
     * Get all records
     */
    async getAll() {
        const store = await this._getStore();
        return new Promise((resolve, reject) => {
            const request = store.getAll();
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });
    }

    /**
     * Put (insert or update) a record
     */
    async put(data) {
        const store = await this._getStore('readwrite');
        return new Promise((resolve, reject) => {
            const request = store.put(data);
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });
    }

    /**
     * Add a new record (fails if key exists)
     */
    async add(data) {
        const store = await this._getStore('readwrite');
        return new Promise((resolve, reject) => {
            const request = store.add(data);
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });
    }

    /**
     * Delete a record by key
     */
    async delete(key) {
        const store = await this._getStore('readwrite');
        return new Promise((resolve, reject) => {
            const request = store.delete(key);
            request.onsuccess = () => resolve();
            request.onerror = () => reject(request.error);
        });
    }

    /**
     * Clear all records
     */
    async clear() {
        const store = await this._getStore('readwrite');
        return new Promise((resolve, reject) => {
            const request = store.clear();
            request.onsuccess = () => resolve();
            request.onerror = () => reject(request.error);
        });
    }

    /**
     * Get records by index value
     */
    async getByIndex(indexName, value) {
        const store = await this._getStore();
        return new Promise((resolve, reject) => {
            const index = store.index(indexName);
            const request = index.getAll(value);
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });
    }

    /**
     * Count records
     */
    async count() {
        const store = await this._getStore();
        return new Promise((resolve, reject) => {
            const request = store.count();
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });
    }
}

/**
 * Entities store with type-specific helpers
 */
class EntitiesStore extends StoreWrapper {
    constructor() {
        super('entities', 'id');
    }

    async getByType(type) {
        return this.getByIndex('type', type);
    }

    async getBots() {
        return this.getByType('bot');
    }

    async getPlayers() {
        return this.getByType('player');
    }
}

/**
 * Blocks store with spatial helpers
 */
class BlocksStore extends StoreWrapper {
    constructor() {
        super('blocks', 'key');
    }

    /**
     * Create a block key from position
     */
    static makeKey(x, y, z) {
        return `${Math.floor(x)},${Math.floor(y)},${Math.floor(z)}`;
    }

    /**
     * Create a chunk key from position
     */
    static makeChunkKey(x, z, chunkSize = 32) {
        return `${Math.floor(x / chunkSize)},${Math.floor(z / chunkSize)}`;
    }

    async getInChunk(chunkKey) {
        return this.getByIndex('chunkKey', chunkKey);
    }

    async putBlock(x, y, z, code, data = {}) {
        const key = BlocksStore.makeKey(x, y, z);
        const chunkKey = BlocksStore.makeChunkKey(x, z);
        return this.put({
            key,
            chunkKey,
            x, y, z,
            code,
            lastSeen: Date.now(),
            ...data
        });
    }
}

/**
 * Actions store with history helpers
 */
class ActionsStore extends StoreWrapper {
    constructor() {
        super('actions');
    }

    /**
     * Add an action to history
     */
    async logAction(command, args, result) {
        return this.add({
            timestamp: Date.now(),
            command,
            args,
            result,
            ok: result?.Ok ?? result?.ok ?? false
        });
    }

    /**
     * Get recent actions
     */
    async getRecent(limit = 50) {
        const all = await this.getAll();
        return all
            .sort((a, b) => b.timestamp - a.timestamp)
            .slice(0, limit);
    }
}

/**
 * Snapshots store
 */
class SnapshotsStore extends StoreWrapper {
    constructor() {
        super('snapshots');
    }

    /**
     * Add a snapshot
     */
    async addSnapshot(data) {
        return this.add({
            timestamp: Date.now(),
            ...data
        });
    }

    /**
     * Get recent snapshots
     */
    async getRecent(limit = 10) {
        const all = await this.getAll();
        return all
            .sort((a, b) => b.timestamp - a.timestamp)
            .slice(0, limit);
    }
}

/**
 * Settings store (key-value)
 */
class SettingsStore extends StoreWrapper {
    constructor() {
        super('settings', 'key');
    }

    /**
     * Get a setting value
     */
    async getValue(key, defaultValue = null) {
        const record = await this.get(key);
        return record?.value ?? defaultValue;
    }

    /**
     * Set a setting value
     */
    async setValue(key, value) {
        return this.put({ key, value });
    }
}

/**
 * Database facade
 */
export const db = {
    /**
     * Initialize the database
     */
    init: initDatabase,

    /**
     * Store accessors
     */
    entities: new EntitiesStore(),
    blocks: new BlocksStore(),
    actions: new ActionsStore(),
    snapshots: new SnapshotsStore(),
    settings: new SettingsStore(),

    /**
     * Clear all data
     */
    async clearAll() {
        await this.entities.clear();
        await this.blocks.clear();
        await this.actions.clear();
        await this.snapshots.clear();
        // Don't clear settings
    },

    /**
     * Get database instance (for advanced use)
     */
    getInstance: () => dbInstance,
};

// Also export block key helpers
export const BlockKey = {
    make: BlocksStore.makeKey,
    makeChunk: BlocksStore.makeChunkKey,
};
