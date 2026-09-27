/**
 * Polis Web UI - Layout Manager
 *
 * Panel management and responsive handling.
 */

/**
 * Panel IDs
 */
export const Panels = {
    STATUSBAR: 'statusbar',
    ENTITY_PANEL: 'entity-panel',
    MAIN_VIEW: 'main-view',
    CONTEXT_PANEL: 'context-panel',
    COMMAND_BAR: 'command-bar',
    EVENT_LOG: 'event-log',
};

/**
 * Layout breakpoints
 */
const Breakpoints = {
    MOBILE: 480,
    TABLET: 768,
    DESKTOP: 900,
};

/**
 * Layout manager
 */
class LayoutManager {
    constructor() {
        this._compactMode = false;
        this._collapsedPanels = new Set();
        this._listeners = new Set();
    }

    /**
     * Initialize layout
     */
    init() {
        // Set up resize observer
        this._setupResizeHandler();

        // Load saved preferences
        this._loadPreferences();

        // Apply initial layout
        this._applyLayout();
    }

    /**
     * Check if in compact mode
     */
    get compactMode() {
        return this._compactMode;
    }

    /**
     * Set compact mode
     */
    set compactMode(value) {
        this._compactMode = value;
        this._savePreferences();
        this._applyLayout();
        this._notifyChange('compactMode');
    }

    /**
     * Toggle compact mode
     */
    toggleCompactMode() {
        this.compactMode = !this._compactMode;
    }

    /**
     * Check if a panel is collapsed
     */
    isPanelCollapsed(panelId) {
        return this._collapsedPanels.has(panelId);
    }

    /**
     * Collapse a panel
     */
    collapsePanel(panelId) {
        this._collapsedPanels.add(panelId);
        this._updatePanelVisibility(panelId, false);
        this._savePreferences();
        this._notifyChange('panelCollapsed', panelId);
    }

    /**
     * Expand a panel
     */
    expandPanel(panelId) {
        this._collapsedPanels.delete(panelId);
        this._updatePanelVisibility(panelId, true);
        this._savePreferences();
        this._notifyChange('panelExpanded', panelId);
    }

    /**
     * Toggle panel collapse state
     */
    togglePanel(panelId) {
        if (this.isPanelCollapsed(panelId)) {
            this.expandPanel(panelId);
        } else {
            this.collapsePanel(panelId);
        }
    }

    /**
     * Get current viewport size category
     */
    getViewportSize() {
        const width = window.innerWidth;
        if (width < Breakpoints.MOBILE) return 'mobile';
        if (width < Breakpoints.TABLET) return 'tablet';
        if (width < Breakpoints.DESKTOP) return 'desktop-small';
        return 'desktop';
    }

    /**
     * Subscribe to layout changes
     */
    onChange(callback) {
        this._listeners.add(callback);
        return () => this._listeners.delete(callback);
    }

    /**
     * Set up resize handler
     */
    _setupResizeHandler() {
        let resizeTimeout;
        window.addEventListener('resize', () => {
            clearTimeout(resizeTimeout);
            resizeTimeout = setTimeout(() => {
                this._applyLayout();
                this._notifyChange('resize');
            }, 100);
        });
    }

    /**
     * Apply layout based on current state
     */
    _applyLayout() {
        const root = document.documentElement;
        const viewport = this.getViewportSize();

        // Apply compact mode class
        document.body.classList.toggle('compact-mode', this._compactMode);

        // Apply viewport class
        document.body.classList.remove('viewport-mobile', 'viewport-tablet', 'viewport-desktop-small', 'viewport-desktop');
        document.body.classList.add(`viewport-${viewport}`);

        // Apply collapsed panel states
        for (const panelId of Object.values(Panels)) {
            this._updatePanelVisibility(panelId, !this._collapsedPanels.has(panelId));
        }
    }

    /**
     * Update panel visibility
     */
    _updatePanelVisibility(panelId, visible) {
        const panel = document.getElementById(panelId);
        if (panel) {
            panel.classList.toggle('collapsed', !visible);
            panel.style.display = visible ? '' : 'none';
        }
    }

    /**
     * Load preferences from localStorage
     */
    _loadPreferences() {
        try {
            const prefs = JSON.parse(localStorage.getItem('polis-layout-prefs') || '{}');
            this._compactMode = prefs.compactMode ?? false;
            this._collapsedPanels = new Set(prefs.collapsedPanels || []);
        } catch (e) {
            // Ignore parse errors
        }
    }

    /**
     * Save preferences to localStorage
     */
    _savePreferences() {
        try {
            localStorage.setItem('polis-layout-prefs', JSON.stringify({
                compactMode: this._compactMode,
                collapsedPanels: [...this._collapsedPanels],
            }));
        } catch (e) {
            // Ignore storage errors
        }
    }

    /**
     * Notify listeners of changes
     */
    _notifyChange(type, data = null) {
        for (const listener of this._listeners) {
            try {
                listener(type, data);
            } catch (e) {
                console.error('Layout listener error:', e);
            }
        }
    }
}

// Export singleton instance
export const layout = new LayoutManager();
