# Coordinate Systems and HUD Offsets (Harness)

Date: 2026-01-12

## Purpose
Document the observed coordinate mismatch between player HUD coordinates and server world coordinates, and define the canonical coordinate system for harness inputs/outputs.

## Summary
- The harness and server-side commands operate in absolute server world coordinates (entity.ServerPos.XYZ); no conversion layer exists in the mod.
- vsapi defines `Entity.ServerPos` as the server-simulated position and `Entity.Pos` as the client position, with `Entity.SidedPos` switching based on side; this reinforces server-absolute coords as the harness canonical.
- In the current test environment, the player HUD reported coordinates offset by about +256 on X/Z compared to server logs and harness state.
- The offset is an observed mismatch, not a confirmed engine rule; treat HUD coordinates as unreliable for harness actions unless verified against server-side output.
- vssurvivalmod does not appear to contain HUD/F3 coordinate rendering; the debug overlay likely lives in the core client/engine code rather than the survival mod.
- Engine decompile confirms two different coordinate displays: `HudElementCoordinates` shows spawn-relative coords (player pos minus default spawn), while `HudDebugScreen` shows absolute client position via `EntityPlayer.Pos`.

## Evidence
- `docs/journal/2026-01-12-harness-visual-debug.md`: server log places player around `230,3,267` while HUD reads around `-28,3,2`, implying a +256 X/Z offset; `/polis/bots` reports positions near the server values.
- `docs/KNOWN_ISSUES.md`: warns that player HUD coordinates can be offset from server world coordinates (observed ~+256 X/Z).
- `docs/TESTING_HARNESS.md`: repeats the HUD offset warning and advises using `/polis list` or F3 for absolute coordinates.
- `PolisBuilderNpcSystem.cs`: harness state uses `entity.ServerPos.XYZ` for bot positions, and spawn/goto commands interpret args as absolute world coordinates (no offset or conversion).
- `PolisBuilderNpcSystem.cs`: `/polis list` prints `entity.ServerPos.XYZ` via `FormatPos`, providing server-absolute positions for players.
- `~/.local/share/btca/collections/vsapi/vsapi/Common/Entity/Entity.cs`: `Entity.Pos` is documented as client position; `Entity.ServerPos` is documented as server simulated position; `Entity.SidedPos` returns ServerPos on server, Pos on client.
- `~/.local/share/btca/collections/vssurvivalmod`: no matches for `F3`, `Hud`, `HUD`, `overlay`, or `coord` in the repo, suggesting HUD coordinate rendering is not implemented in survival mod sources.
- `/home/mf/.local/share/flatpak/app/at.vintagestory.VintageStory/x86_64/stable/active/files/extra/vintagestory/VintagestoryLib.dll` (decompile `Vintagestory.Client.NoObf.HudElementCoordinates`): uses `capi.World.Player.Entity.Pos.AsBlockPos` and subtracts `capi.World.DefaultSpawnPosition.AsBlockPos` before display, making the coordinate HUD spawn-relative.
- `/home/mf/.local/share/flatpak/app/at.vintagestory.VintageStory/x86_64/stable/active/files/extra/vintagestory/VintagestoryLib.dll` (decompile `Vintagestory.Client.NoObf.HudDebugScreen`): displays `clientMain.EntityPlayer.Pos` via `pos.OnlyPosToString()` and does not subtract spawn, implying absolute client world coordinates on the F3/debug overlay.

## Open questions
- What specific HUD or camera/observer mod (if any) is providing offset coordinates, and is this configurable?
- Is the +256 X/Z offset consistent across worlds, dimensions, and server restarts, or does it vary by region/chunk?
- Should the harness expose a server-side player position endpoint to eliminate reliance on client HUD coords?
- What is the default spawn position in the test world, and does it match the observed +256 X/Z offset shown in the coordinate HUD?

## Implications for harness design
- Canonical coordinate system: absolute server world coordinates (Vec3d from `Entity.ServerPos.XYZ`).
- Harness inputs and outputs should be treated as server-absolute; avoid using client HUD coordinates unless validated against `/polis list` or F3 debug overlay.
- If a UI needs player-relative coordinates, add an explicit, optional conversion step and label it as client-side only (do not bake into harness protocol).
