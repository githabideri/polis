# [1.22.7] Low-FPS entity interpolation overflows and writes NaN to entity positions

## Environment

Vintage Story 1.22.7, .NET 10, Linux singleplayer with the embedded server.
Client rendering approximately 1–1.5 FPS. Custom mod used for instrumentation
and the workaround; the failure also reproduces by invoking the installed
engine interpolation method in an isolated console regression.

Related symptoms: [#6946](https://github.com/anegostudios/VintageStory-Issues/issues/6946).
This report identifies a specific low-FPS arithmetic failure; it does not
establish that every symptom in that issue has the same cause.

## Observed behavior

Entities disappear while terrain and chunk queues remain healthy.
Their client Pos.X/Y/Z become NaN, then fail the chunk/render gate.
Finite packet snapshots continue arriving during the failure. Direct post-fix
loaded-entity inspection finds finite server positions. Repairing client
coordinates alone is temporary.

## Identified writer

A prefix/postfix around
`EntityBehaviorInterpolatePosition.OnRenderFrame(float dt, EnumRenderStage stage)`
captured a finite-to-NaN write with finite pL/pN snapshots.

One transition had dt=1.0046005, targetSpeed=-5.045717E+37,
pN.interval=0.06666667, dtAccum initially 0, queueCount=11, wait=0.
The method left dtAccum=-5.0689296E+37 and all coordinates NaN.
The float dtAccum/interval division overflows; identical finite snapshots
then multiply zero by infinity in the double-coordinate Lerp.

The preceding speed update is an unclamped
`Lerp(targetSpeed, queueCount * 0.2f + 0.8f, dt * 4f)`.
Its error multiplier at constant target is `1 - 4*dt`, unstable for dt>0.5s.

## Reproduction

1. Initialize interpolation with a finite entity position and snapshot interval
   1/15 second.
2. Before each render, supply a finite server position and call
   OnReceivedServerPos(false), with tickDiff=1.
3. Call the real OnRenderFrame with dt=1 second repeatedly.
4. In our fixture, the original engine writes a non-finite position at frame 81.

The attached fixture uses the actual installed VSEssentials method and minimal
client-interface stubs. It does not execute graphics calls or start a game.
Running the game at similarly low frame rates reproduced the same writer.

## Proposed fix

Clamp the speed-feedback interpolation factor:

```csharp
targetSpeed = GameMath.Lerp(
    targetSpeed, queueCount * 0.2f + 0.8f,
    Math.Clamp(dt * 4f, 0f, 1f));
```

Keep elapsed dt intact for the rest of the method. Our mod workaround replaces
only this float Lerp call, with a match-count check for this engine version.

## Verification

The unpatched engine fails the regression. The patched engine passes 280,000
frames with stationary/moving entities, 60–0.2 FPS, irregular stalls up to
10 seconds, and zero dt. Normal fast-frame speed arithmetic is unchanged.

15 minutes live verified: 31 samples at 30-second intervals, 2026-10-08T20:18:19.236602+00:00 through 2026-10-08T20:33:19.240533+00:00; zero failed requests, zero client NaN positions, zero non-finite server positions, and zero invalid interpolation writes. Client render entries ranged 41-57, loaded server entities 122-150, and rendered entities 8-11. The audit recorded 47257 calls, max dt 1.8443693 seconds, and max absolute speed 4.6.

No host reboot, graphics-driver change, or periodic entity repair was used
during the patched run. The live verification window is 15 minutes by operator
request; no hours-long live result is claimed.
