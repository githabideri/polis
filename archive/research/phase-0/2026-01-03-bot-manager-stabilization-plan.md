# Bot Manager Stabilization Plan (2026-01-03)

## Objective
Fix the persistent "Focus Trap" (mouse jumping, Esc ignored) and UI regressions in the Bot Manager. This phase moves from "guessing fixes" to "imitating proven engine patterns."

## 1. Architectural Shift: Client-Authoritative Commands
- **Change:** Register `/polis manage` chat command on the client side (`PolisBuilderNpcHotkeys.cs`).
- **Goal:** Window opens instantly. The client dialog then requests data from the server.
- **Why:** More stable UI lifecycle; eliminates the risky server-to-client "signal to open" packet.

## 2. Stability Strategy: Full Re-composition
- **Change:** Discard `ReloadCells` and manual `SingleComposer.Dispose()`. Re-run the entire `Compose()` method on every data update.
- **Goal:** Ensure "Interactive Boundaries" (hitboxes) are always 100% synchronized with visual elements.
- **Why:** This is the pattern used by `VSQuest` and `VSVillage`. It is the only confirmed way to prevent the engine's focus logic from "falling through" to the game world.

## 3. Focus Anchoring: The "Safe Empty State"
- **Change:** Ensure the GUI never contains zero interactive elements.
- **Goal:** If the bot list is empty, a prominent **[Close Manager]** button will be rendered in the center.
- **Why:** Hypothesized fix for the focus hang when the list is empty. A button gives the engine a focus "anchor."

## 4. Standardized Layout (VSQuest Imitation)
- **Dimensions:** Use a fixed **400x500** content area.
- **Why:** Known-working dimensions in the VS API. Eliminates "0-size surface" crashes from the Cairo drawing library.

## 5. Telemetry & Debugging
- **Add:** A status line at the bottom corner showing `Focus: {Focused} | GUI Stack: {Count}`.
- **Panic Hotkey:** Keep `Alt + Shift + P` as a hard-coded bypass to clear the UI stack.
- **Why:** Provides objective proof of engine state during failures, ending the need for narrated guesses.
