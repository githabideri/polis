# Entity NaN root-cause report

## Finding

The NaN writer is the managed engine method
`EntityBehaviorInterpolatePosition.OnRenderFrame` in Vintage Story 1.22.7.
Its interpolation-speed feedback becomes unstable at sustained frame times
above 0.5 seconds. This investigation captured finite coordinates becoming
NaN inside that method, with finite queued positions and valid packet ticks.

This supersedes the handoff's hardware-memory-corruption diagnosis. A
headless regression invoking the installed engine method reproduces the
failure without a running game, X server, or graphics calls. No host reboot,
driver change, bot respawn watchdog, or memory-address shim was needed.

## Exact chain

The engine adjusts speed with:

```csharp
targetSpeed = GameMath.Lerp(targetSpeed, queueCount * 0.2f + 0.8f, dt * 4f);
```

For a constant target, the error multiplier is `1 - 4*dt`. At one second
per frame its magnitude is three, so alternating errors grow exponentially.
The engine also accumulates `dt * targetSpeed`, then computes the
single-precision ratio `dtAccum / pN.interval`. That ratio can overflow
before targetSpeed itself reaches infinity. Coordinate interpolation is
`v0 + (v1 - v0) * ratio`; stationary snapshots therefore produce
`0 * Infinity = NaN`.

Those NaN coordinates subsequently fail the existing chunk/render gates.
Position packets continue arriving and can temporarily restore finite
coordinates, but the poisoned interpolation state writes NaN again.
A one-shot coordinate repair does not correct that state.

## Live writer evidence

Diagnostic-only Harmony prefix/postfix instrumentation observed the original
method without changing its inputs. First captured transition:
2026-10-08 20:07:38 UTC, entity 169437.

| Value | Before | After |
|---|---:|---:|
| dt | 1.0046005 | unchanged |
| targetSpeed | -5.045717E+37 | 1.5230002E+38 |
| dtAccum | 0 | -5.0689296E+37 |
| snapshot interval | 0.06666667 | unchanged |
| queue count | 11 | 11 |
| wait | 0 | 0 |
| packet tick / tickDiff | 1452 / 1 | 1452 / 1 |
| entity position | finite | NaN on all three axes |

Both pL and pN were identical finite coordinates
(512128.50286865234, 46, 511939.46154785156). Dividing the resulting float
accumulator by the interval overflows, and all three zero coordinate
differences multiply infinity. Other entities followed at 20:07:38–39.

The diagnostic probe subsequently counted 42 NaN client entries. Corrected
tick readings were populated, contradicting the earlier missing-packet claim.

## Corrections to earlier evidence

- `Entity.Attributes` is a field. The old probe looked for a property and
  silently swallowed reflection failures; its -1 tick values were not proof
  of absent tick attributes. It also supplied too few reflection arguments
  for `GetInt`. The probe now reads the typed field directly.
- The repair route called `GetEntitiesAround(center, 0f, 256f, ...)`.
  The first range is horizontal. Its callback visited a narrow chunk column,
  not a 256-m-radius neighborhood. A small callback count did not prove
  server-side loss. The query now uses 256 for both ranges.
- A new server-thread `/polis/entityhealth` diagnostic enumerates the loaded
  entity dictionary directly, independently of spatial indexing.
- Deserialization from fixed-point integers cannot directly produce NaN,
  but it is not the only position writer. Render interpolation was omitted.
- Host dependence was not established causally. Low-FPS arithmetic explains
  this captured event; the historical boot-to-boot timing differences were
  not independently reconstructed.

## Fix

`src/Compat/1.22.7/PolisInterpolationStability.cs` replaces the single
float Lerp call in the engine render method with the same calculation using
a factor clamped to [0,1]. It preserves the actual frame dt, queue handling,
remote physics, mount handling, and fast-frame speed arithmetic.

The transpiler requires exactly one matching call and fails explicitly on an
unexpected engine shape. The game restart cleared preexisting poisoned
interpolation state. The patch prevents recurrence; it is not a watchdog
that silently teleports or recreates entities.

`PolisInterpolationAudit` retains per-call value snapshots without string formatting,
aggregate counters, and a bounded log of future finite-to-nonfinite writes.
The chunk probe exposes those counters.

## Verification

- Build and deployment: succeeded, zero compilation errors.
- Installed engine regression: the original method produced a non-finite
  position at frame 81 with dt=1 second and finite packet inputs.
- Patched installed engine regression: 280,000 frames passed across stationary
  and moving entities, 60 to 0.2 FPS, mixed frame times including 10-second
  stalls and zero dt. Fast-frame speed arithmetic matched the original.
- Test command: `python3 tests/interpolation/run.py --game "$VINTAGE_STORY"`.
- Live monitoring: 15 minutes live verified: 31 samples at 30-second intervals, 2026-10-08T20:18:19.236602+00:00 through 2026-10-08T20:33:19.240533+00:00; zero failed requests, zero client NaN positions, zero non-finite server positions, and zero invalid interpolation writes. Client render entries ranged 41-57, loaded server entities 122-150, and rendered entities 8-11. The audit recorded 47257 calls, max dt 1.8443693 seconds, and max absolute speed 4.6.
- Screenshot: captured after deployment; entities visibly render.
- Deployment DLL SHA-256:
  `c124c6b8e5d2240320ffee7f77cd778981d394758e3af537092edbccf13b3b2a`.

The user explicitly shortened the original hours-long acceptance window to
15 minutes. This report does not claim an hours-long live soak. The isolated
regression's frame count is simulated execution, not wall-clock game uptime.

Related upstream symptoms: https://github.com/anegostudios/VintageStory-Issues/issues/6946
