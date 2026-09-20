# TESTING.md — how we verify polis

## Verification vocabulary (binding)

| Term | Meaning |
|------|---------|
| **implemented** | Code written, not yet run |
| **locally verified** | Unit tests / build pass |
| **live verified** | In-game (CT-114 testbed or equivalent) |
| **remotely verified** | Works in a production/real-world context |

Never collapse these into "works". `STATUS.md` records the level per feature.

## The testbed (the game testbed "polis", )

- Game: `/opt/vintagestory` (native install, 1.22.7), display via
  noVNC `http://the game testbed:6080/vnc.html`. Full ops notes: `ops/CT114-VNC.md`.
- The game **auto-logs in** from the cached session key
  (`/root/.config/VintagestoryData/clientsettings.json`) — no password
  typing needed; the session key must be refreshed occasionally by a human
  at the login screen.
- Mod install dir: `<VSDATA>/Mods/polis-builder-npc` (see `.env`).
- Test world: copy `tests/world/<name>/*.vcdbs` into
  `<VSDATA>/Worlds/<name>/` and select it in the main menu.
  `polis-testbed-pristine` is the canonical empty testbed.
- **Never restart Xvnc while the game runs** (kills the game session).
  Restarting the game (`systemctl restart vsgame`) is fine.

## The harness

The mod runs an HTTP server in-game on `localhost:8585`:

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
- Raw HTTP + WebSocket: `docs/TESTING_HARNESS.md`; Web UI at
  `http://localhost:8585/polis/ui`.

## Missions

A **mission** is a deterministic script: setup (world state) → steps
(commands with `--wait`) → assertions (state/positions/inventory) →
pass/fail, run by `scripts/polis-test-runner.py`. Rules:

1. Missions run against a **fresh copy** of the testbed world (restore the
   pristine `.vcdbs` before each run; never mutate the pristine file).
2. Every assertion is checked against server state, not screenshots,
   except for the explicit visual-verify missions (screen capture via the
   harness).
3. A mission result is one of: `PASS`, `FAIL <step>`, `ERROR <step:reason>`.
   Record the result in `STATUS.md` (or the task note) with the mission id
   and date.
4. Flaky failures get one re-run before being reported; repeated flakes
   are a bug to file, not a fact to paper over.

## In-game manual checks (agent-driven via noVNC)

- `agent-browser press <key>` per key (raw `keyboard type` does not fire
  DOM keydown on the noVNC canvas).
- Login-screen coordinates (game→page: +128 x): E-Mail (488,247),
  Password (488,305), Login (~606,376).
- F3 debug overlay + `/polis list` for absolute coordinates (HUD coords can
  be offset).
- Clipboard: noVNC toolbar → Clipboard box → paste; then Ctrl+V in-game.
