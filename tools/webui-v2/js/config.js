/**
 * Polis Web UI v2 - Configuration
 */

export const CONFIG = {
    // API settings — null = auto-detect from window.location.origin (works via nginx proxy on :8586)
    API_BASE: null,

    // Polling intervals (milliseconds)
    POLL_STATUS_MS: 5000,      // Connection/status check
    POLL_EVENTS_MS: 1000,      // Event polling
    POLL_BOTS_MS: 5000,        // Bot list refresh

    // IndexedDB settings
    DB_NAME: 'polis-webui-v2',
    DB_VERSION: 1,

    // UI settings
    LOG_MAX_ENTRIES: 100,      // Max log entries to keep
    SCREENSHOT_AUTO_REFRESH: false,
    SCREENSHOT_INTERVAL_MS: 5000,

    // noVNC stream settings
    NOVNC_BASE: null,  // null = auto-detect: http://<current-hostname>:6080
    NOVNC_PATH: '/vnc.html',
    NOVNC_PARAMS: 'autoconnect=true&view_only=true&resize=scale&reconnect=true&reconnect_delay=2000',

    // Feature flags
    ENABLE_SOUND: false,
    ENABLE_NOTIFICATIONS: false,
};

/**
 * Get API base from URL params, localStorage, or default
 */
export function getApiBase() {
    const params = new URLSearchParams(window.location.search);
    const paramBase = params.get('api');
    const stored = localStorage.getItem('polis-api-base');
    return normalizeUrl(paramBase || stored || CONFIG.API_BASE || window.location.origin);
}

/**
 * Save API base to localStorage
 */
export function setApiBase(url) {
    const normalized = normalizeUrl(url);
    localStorage.setItem('polis-api-base', normalized);
    return normalized;
}

/**
 * Normalize URL (remove trailing slashes)
 */
function normalizeUrl(url) {
    if (!url) return window.location.origin;
    return url.replace(/\/+$/, '');
}
