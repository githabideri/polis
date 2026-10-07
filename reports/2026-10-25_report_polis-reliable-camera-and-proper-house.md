---
title: Reliable screenshots + the proper-house build (findings & plan)
date: 2026-10-25
tags: [polis, harness, camera, camera-patch, proper-house, build, last-cell, door]
status: draft
---

# Reliable screenshots + the proper-house build

Answering two questions from the 2026-10-25 session: (1) can we get a
RELIABLE screenshot of a built structure, and (2) what does it take — workflow
and harness-wise — to get from the current "hollow hut" to a proper building
(5×5×3 or elongated 5×3, a roof, one door opening, one crude door)? The camera
is called out as the **big prize**; the screenshot is the real *visual*
verification, distinct from the geometric scan-assert.

## 1. Why the screenshot is unreliable (root cause, confirmed)

The harness `observer-screenshot` places the observer at a computed position
(behind + above the structure, looking down at it) and captures on the next
`EnumRenderStage.Done`. The **position** works (the photo frames the hut) but the
**camera orientation** is wrong / rotates:

- The `setViewDirection` packet only sets `PlayerCamera.Yaw/Pitch` at
  **`EnumGameStep.PostUpdate`** (`PlayerCamera.HandleInput`), and **only when no
  input is queued**. The idle-mouse / view-reset path (the mod's
  `PolisViewResetTimer` — reset to spawn after ~20 s of inactivity — and any
  client-side look smoothing) writes the transform **every render frame** in
  `PlayerCamera.OnBeforeRenderFrame`, which runs *later* than the PostUpdate
  packet apply. So the packet's yaw/pitch gets **clobbered** before the
  `Done`-stage `RenderTexture.Capture()` grabs the frame.
- `gotolook` works because it drives the *actual player's* input over several
  ticks (the camera follows input each tick). The observer packet path is a
  one-shot write that loses the race.

Confirmed in source: `src/Harness/PolisScreenCaptureRenderer.cs`
(`EnumRenderStage.Done` → `RenderTexture.Capture`),
`src/Harness/PolisObserverSpectator.cs` (`PolisSetViewDirectionPacket`),
`src/Harness/PolisViewResetTimer.cs`, `src/Harness/PolisAutonomyClient.cs`
(`SetViewDirection`).

## 2. Reliable-screenshot approaches (researched 2026-10-25)

The whole VS camera mod scene runs on the same primitive: **force the
`PlayerCamera` transform on the render path** and/or **patch
`PlayerCamera.OnBeforeRenderFrame`** so input stops overwriting it.

- **Free Look** (Mist1117/SaltysFreeLook) — patches
  `PlayerCamera.OnBeforeRenderFrame` (v1.0.1). Note: **crashed on 1.21.1** with a
  `ModelTransformNoDefaults.Rotation` field-mismatch — its 1.22.7 port is
  unverified; the *technique* (patch OnBeforeRenderFrame) is what we want.
- **Steady Cam** (v3.0.0, **1.22.0** — closest to our 1.22.7): a "Spectator
  Camera Mod." Patches `OnBeforeRenderFrame` + `Camera.RenderCamera` +
  `Player.UpdateGameStep` + `ClientMain.OnKeyInput`, adds a **spectator game
  mode** (a "fly" that doesn't need to be an actual spectator) and an
  **independent camera system** that moves independently of the player. This is
  the most feature-complete, most version-current, most reliable option.
- **Cinematic Camera** (DoomedDolphin, v1.0.0, **1.22.0**): a "camera that is
  not affected by player movement." **File-driven**: a `.cam` file with
  `@name`, `@duration`, and per-frame `@pos x y z pitch yaw` /
  `@look x y z` entries, driven by a **spectator** + `camera load <file>`,
  `camerapreview`, `camerareverse`. The `.cam` format is exactly the kind of
  **declarative, scriptable camera** a harness wants — and it can load
  `game:creative` (the spectator).
- **Cinematics Mod** (Kam, v2.4.6, **1.22.5**): a "full cinematics system"
  (cutscene scripting, keyframes, camera control). Heavier.
- **Starry Sky Camera** (v2.1.2, 1.22.0): "set your camera position" +
  "toggle to use camera" + auto-return to first-person — simpler than the
  cinematic ones.
- **VS native**: `F3+V` (toggle view rotation), `F3+J` (lock rotation),
  `F3+S` (spectate). Useful for a human, but the harness is headless and the
  idle-reset would still fight a one-shot packet.

**Recommendation.** Prefer a **native Harmony patch in the Polis mod** over
installing a third-party camera mod: it's the same primitive the mods use, it
keeps the mod self-contained, and it avoids version-mismatch breakage
(SaltysFreeLook's crash shows the risk). Concretely — a **"cinematic capture"**
mode:

1. Add a capture request that sets a flag on the client (`PolisCameraCapture`):
   freeze + set the exact `PlayerCamera.Transformation` (position + yaw + pitch)
   for a couple of frames, **and prefix `PlayerCamera.OnBeforeRenderFrame`
   (Harmony) to skip the input/rotation update while the flag is set** so the
   idle-mouse/view-reset can't clobber it.
2. The existing `PolisScreenCaptureRenderer` (already hooks `EnumRenderStage.Done`)
   grabs the now-stable frame; the flag clears automatically after the capture.

This makes the observer's view a **deterministic, scriptable** placement — the
same capability the `.cam` format offers, without a third-party dependency.
**Fallback** (if the native patch fights us): install **Steady Cam** or
**Cinematic Camera** (both 1.22.x, spectator-based) and drive their
spectator/camera command from the harness.

## 3. From "hollow hut" to a proper house

The current `builds/hut-hollow.json` *is already the right shell geometry*:
5×5 footprint, 3-high (dy=1,2,3) perimeter walls, a 1×2 front door opening
(`entry: [2,0,2]`, cells (2,1,0)+(2,2,0)), a 3-high central support post, and a
roof at dy=4 (24 blocks + a center skylight that doubles as the last-cell
stand). Sequencer-proven `ok=True`. So "a proper building" needs these
**additions**, not a new shape:

1. **Flush the site (the real defect).** The run's "floating pad" was a
   self-inflicted bug: we flushed only the *inside* of the footprint (the floor
   area) to ground_y, so the 25-block ring walls + walk-ring sat on their old
   terrain → the structure looked elevated. Fix (harness-side, in the build
   driver): **scan the footprint + a 1-ring walk-ring *outside* it** (never the
   footprint itself — scanning inside is the "look at own pad" footgun), take
   the **modal ground height**, and flush the footprint **and** the walk-ring
   to that level via `setblock` before building. The build then sits flush on
   the terrain (terrain is the floor, per the floorless plan).
2. **Install the crude door (post-build).** The sequencer **reserves** the door
   cells (keeps the 1×2 gap open — `_reserved_cells`/`_door_cells` in
   `r2/sequencer.py`); the door is deliberately NOT part of the placement
   sequence. So the door is a **post-build install step**: after the shell
   passes the gate, `setblock survival:door-crude` at the two gap cells
   ((2,1,0),(2,2,0) → absolute site coords). **Verified on CT 114
   (2026-10-25):** `setblock survival:door-crude <x> <y> <z>` succeeds
   (`Ok:true`, places a `game:door-crude` block) and a throwaway test
   placed/removed cleanly. A crude door is a **single-cell thin slab**
   (`survival:door-crude`, a `Door`-behavior block entity; there are also
   `1x3gate`/`2x2gate` variants if a taller/wider opening is wanted). **No new
   harness primitive is needed** for a crude door — `setblock` suffices. (If we
   ever want a hinged, correctly-oriented door, that's the `place` *bot action*
   path, which sets orientation from the bot's facing — a later refinement.)
3. **Reliable screenshot (the big prize)** — §2. Once in place, the build gets a
   real visual gate: a framed, stable photo of the finished house (door, roof,
   flush-to-terrain) instead of the current mis-oriented one.

**Verification stays dual:** scan-assert (geometric: perimeter even, interior
hollow, roof closed, door present) as the always-reliable gate, plus the
(suddenly reliable) camera for the visual.

## 4. Concrete next steps (the run)

1. **Flush-site fix** in the build driver (`scripts/r2-live-mission.py`):
   scan footprint + outer walk-ring → modal ground height → level both before
   build (never a raised pad).
2. **Door-install step**: after the shell gate, `setblock survival:door-crude`
   at the 1×2 gap (absolute coords from the plan origin + entry).
3. **Camera patch** (§2): native Harmony "cinematic capture" (freeze +
   prefix-`OnBeforeRenderFrame`) in the Polis mod; rebuild + redeploy to CT 114.
4. **Rebuild** the hut (flush → walls → gate → roof → gate → door →
   screenshot). Verify hollow via scan-assert **and** via the new stable photo.

## Sources (2026-10-25, websearch SearXNG)

- GitHub Mist1117/SaltysFreeLook (Free Look, v1.0.1) — patches
  `PlayerCamera.OnBeforeRenderFrame`; **1.21.1 crash** on
  `ModelTransformNoDefaults.Rotation` (version-mismatch risk for third-party
  camera mods).
- VS Mod Database — **Steady Cam v3.0.0 (1.22.0)** spectator camera (patch
  list + independent camera system + spectator fly mode); **Cinematic Camera
  v1.0.0 (1.22.0)** (`.cam` file format, `camera load`, spectator/
  `game:creative`); **Cinematics Mod v2.4.6 (1.22.5)** (cutscene/keyframe
  scripting); **Starry Sky Camera v2.1.2 (1.22.0)** (set camera position +
  toggle).
- VS Wiki "Controls" — F3+V (toggle view rotation), F3+J (lock rotation),
  F3+S (spectate).
