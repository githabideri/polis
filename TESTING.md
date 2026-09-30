# TESTING.md — how we verify polis

## Verification vocabulary (binding)

| Term | Meaning |
|------|---------|
| **implemented** | Code written, not yet run |
| **locally verified** | Unit tests / build pass |
| **live verified** | In-game (CT-114 testbed or equivalent) |
| **remotely verified** | Works in a production/real-world context |

Never collapse these into "works". `STATUS.md` records the level per feature.

## The testbed

- Game: a Vintage Story 1.22.7 install on a headless container (paths come
  from `.env`: `VINTAGE_STORY`, `VSDATA`), observable via noVNC. The
  deployment specifics (services, display stack, the TLS front for the UI)
  are operator-specific and live **outside** this repo.
- The game **auto-logs in** from the cached session key in VSDATA
  (`clientsettings.json`) — no password typing needed; the session key must
  be refreshed occasionally by a human at the login screen.
- Mod install dir: the **game directory** `<VINTAGE_STORY>/Mods/polis`
  (VS 1.22 loads user mods from the game dir; `$VSDATA/Mods` is ignored by
  1.22 — `build.sh --deploy` copies to both, game dir authoritative).
- Test world: create a fresh world for mission work and select it in the
  main menu (the curated pristine test world was removed from this repo —
  it carried player data). Missions always run against a fresh copy of a
  world, never a mutated base.
- **Never restart Xvnc while the game runs** (kills the game session).
  Restarting the game (`systemctl restart vsgame`) is fine.

## The harness

The mod runs an HTTP server in-game on loopback by default, and
LAN-reachable when `POLIS_HARNESS_IP` is set in `.env` (no ssh tunnel).
`/polis/servercmd` and `/polis/admin/*` stay loopback-gated:

```sh

```sh
./scripts/poliscli.py status          # worldReady?
./scripts/poliscli.py spawn
./scripts/poliscli.py give game:pickaxe-copper
./scripts/poliscli.py goto 100 64 -200 --wait 10
./scripts/poliscli.py state           # ALWAYS re-read after actions
```

- `GET /polis/status` → `worldReady` gate before any test.
- Actions can **succeed at start and fail later** — every test step must
  end with a `state`/`targets` re-read (the fire-and-verify rule).
- `poliscli.py` supports TOON output (`--toon`) for token-efficient agent
  consumption; env vars `POLIS_PLAYER_UID` / `POLIS_BOT_ID` drive targeting.
- Raw HTTP + WebSocket: `docs/TESTING_HARNESS.md`.
- Web UI (primary surface): `/polis/ui/` on the harness (served from the
  mod folder) —
  status header (Connected / World Ready), entity panels, view + step-move
  controls, noVNC live stream (VNC password once), still-image screenshot
  pane (no password — the agent-loop view).
- `GET /polis/look?uid=...` ray-traces from the player's actual eye +
  orientation and returns the exact block hit (`blockSelection`) — the
  **ground truth** for aim/crosshair questions (pixel heuristics are not).
- `GET /polis/observer-screenshot?x=&y=&z=&yaw=&pitch=&playerUid=` returns
  JSON `{ok, width, height, base64Png, captureTimeMs}` (set view, capture,
  restore — shots are independent).

## Missions

A **mission** is a deterministic script: setup (world state) → steps
(commands with `--wait`) → assertions (state/positions/inventory) →
pass/fail, run by `scripts/polis-test-runner.py`. Rules:

1. Missions run against a **fresh copy** of the test world (create it
   before each run; never mutate the base world).
2. Every assertion is checked against server state, not screenshots,
   except for the explicit visual-verify missions (screen capture via the
   harness).
3. A mission result is one of: `PASS`, `FAIL <step>`, `ERROR <step:reason>`.
   Record the result in `STATUS.md` (or the task note) with the mission id
   and date.
4. Flaky failures get one re-run before being reported; repeated flakes
   are a bug to file, not a fact to paper over.

## Aim verification (tests/view/aim-verify.py)

Deterministic proof that the camera-aim pipeline works — the gate any
"look at X" functionality must pass before it is trusted:

```sh
python3 tests/view/aim-verify.py                # auto: places a solid marker wall 20 blocks ahead
python3 tests/view/aim-verify.py 512029 3 512028 --code rock-granite   # user marker
```

PASS = the crosshair ray (game ray trace) hits the marker for at least one
scanned pitch; reports best pitch vs the analytic prediction and saves an
evidence screenshot. Baked-in lessons: solid markers only (ray trace skips
decorative blocks like `fire`); 1x3x4 wall (1-block targets are a few
degrees of pitch wide and the ray drifts ~1.5 cells in z over 20 blocks —
DDA boundary aliasing); player centered on the marker's z slab; scan is
+-12deg around the prediction in 3deg steps with +-1.5deg refine.

## In-game manual checks (agent-driven via noVNC)

- `agent-browser press <key>` per key (raw `keyboard type` does not fire
  DOM keydown on the noVNC canvas).
- Login-screen coordinates (game→page: +128 x): E-Mail (488,247),
  Password (488,305), Login (~606,376).
- F3 debug overlay + `/polis list` for absolute coordinates (HUD coords can
  be offset).
- Clipboard: noVNC toolbar → Clipboard box → paste; then Ctrl+V in-game.
