# Radar Map Implementation Plan

## Goal Description
Implement a **Radar Map** in the `test-ui.html` Web UI. This feature will visualize the bot's surroundings (blocks, entities, items) on a 2D canvas, improving spatial awareness and interaction.

## Proposed Changes

### Web UI (`tools/test-ui.html`)
- **Add Canvas Element**: Create a `<canvas id="radar" width="300" height="300">` in the "Bot State" panel.
- **Implement Radar Logic**:
    - Poll `/polis/targets?botId=...&radius=15&mode=all` regularly.
    - Parse the JSON response.
    - **Render**:
        - Draw the Bot (Center) as a Blue Triangle (facing yaw direction if available, otherwise Circle).
        - Draw **Blocks** as Gray squares.
        - Draw **Entities** as Red dots.
        - Draw **Items** as Green dots (with tooltips or small icons).
        - **Scale**: Map world coordinates to canvas coordinates relative to the bot's position.
    - **Interaction**:
        - **Clicking** a dot on the radar sends a command (e.g., `lookAt` or `goto`). For now, we will implement `goto` on click (hold Shift to `lookAt`).

## Verification Plan

### Automated Tests
- **Browser Subagent**:
    - Open the UI.
    - Ensure `<canvas id="radar">` exists.
    - Parse the canvas pixel data (advanced) OR simply verify that the `/polis/targets` API is being called (via network logs or side effect).
    - Since checking canvas pixels is hard, I will verify the *presence* of the radar and the *successful API calls* in the Action Log (if we add debug logs) or via the status indicator.

### Manual Verification
- **Visual Check**:
    - Open UI.
    - Spawn an item.
    - Verify a Green Dot appears on the radar relative to the bot.
    - Move the bot.
    - Verify the Green Dot moves relative to the center.
