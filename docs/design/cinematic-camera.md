# Cinematic capture camera — deterministic screenshots in a headless bot

*Design note, Vintage Story 1.22. This documents the mechanism in
`src/PolisCinematicCamera.cs` + the `/polis/cine-screenshot` harness
endpoint, for reuse in any mod that needs deterministic world capture.*

## Problem

A bot-driven headless game needs **deterministic** screenshots (verify a build,
feed a vision model, document state). The naive approaches fail:

- **Teleport the player to a vantage and set the view via a packet** — the
  packet is applied on a *game tick*, but the frame is captured on the next
  *render frame*. When the player is idle, the game's mouse/view path rewrites
  the look direction between the tick and the frame, so the capture comes out as
  the default first-person, not the pinned view.
- **Free-fly the camera origin** — see the eye constraint below.

## Why the view works the way it does (1.22)

The entire view is driven by two **public fields** on `ClientMain`:
`mouseYaw` / `mousePitch`, read once per frame:

```
ClientMain.MainRenderLoop(dt):
  UpdateCameraYawPitch(dt)                       # idle view-reset
  TriggerRenderStage(EnumRenderStage.Before):
     PlayerCamera.OnBeforeRenderFrame3D(dt):
        Yaw   = game.mouseYaw
        Pitch = game.mousePitch
        Update(dt, intersectionTester)           # builds CameraMatrix + CameraMatrixOrigin
  ... GlLoadMatrix(MainCamera.CameraMatrix)       # world + shadow + GUI consume it
```

Two consequences:

1. The one place that reliably pins the look direction is a **Harmony PREFIX on
   `PlayerCamera.OnBeforeRenderFrame3D`** that writes `mouseYaw`/`mousePitch`
   *after* `UpdateCameraYawPitch` (the reset) and *before* the body's read. The
   body then builds the matrix through the game's own `Update()`, so the world,
   the player-relative shader offset, and the shadow pass all stay consistent —
   no hand-rolled matrix, no shadow desync.
   - **Not a POSTFIX**: `MainRenderLoop` reloads the matrix *after* the `Before`
     stage, so a postfix write is overwritten.
   - The `ClientMain` is reached via the `PlayerCamera`'s private `game` field
     (reflection).
2. **The eye stays at the player's own position.** The world is rendered relative
   to `PlayerPos`, not the camera origin; moving the origin to an arbitrary
   point away from the player yields an empty skybox. For a raised/wide vantage,
   **move the player** (a teleport), then pin the look direction.

## The yaw/pitch convention

`PlayerCamera.Update` builds the forward vector as
`ToVectorInFixedSystem(0,0,1, pitch, -yaw + π)`; with
`ToVectorInFixedSystem(dx,dy,dz, ox,oy)`:

```
forward = ( -cos(pitch)·sin(yaw),  sin(pitch),  -cos(pitch)·cos(yaw) )
```

To aim from an eye `(ex,ey,ez)` at a target `(tx,ty,z)`:

```
d = target - eye ;  len = |d|
pitch = asin( dy / len )        # negative = look down, positive = up
yaw   = atan2( -dx , -dz )      # yaw increases turning left
```

The physics NaN-guard (this mod also ships one) clamps teleport pitch ~3° short
of the poles, so request ±90° for straight up/down without fear of an
exact-pole degenerate.

## The patch

`PolisCinematicCamera` holds `active / yaw / pitch / framesLeft` and a cached
`FieldInfo` for the private `game` field. `Arm(yaw, pitch, holdFrames)` (call on
the main thread) sets them; a Harmony PREFIX (wired in `PolisHarmony.
ApplyClient`) writes `game.mouseYaw`/`mousePitch` each armed frame and disarms
after `holdFrames`. A harness endpoint arms it and fires the existing
`Done`-stage frame renderer (`PolisScreenCaptureRenderer` → `CaptureFrameRgba` →
PNG) inside the armed window:

```
GET /polis/cine-screenshot?playerUid=&yaw=&pitch=[&frames=N][&save=true]
```

## Version caveat

The field/method names are **version-specific** (`OnBeforeRenderFrame3D`,
`CameraMatrixOrigin`, `mouseYaw`, the private `game` field — these have changed
between 1.21 and 1.22). If you move game versions, re-decompile
`VintagestoryLib.dll` (ILMerge `-decompile`) and re-derive; confirm the patch
applied in the client log.
