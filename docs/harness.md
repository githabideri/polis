# The in-game harness (API reference)

The mod runs an HTTP server inside the game process on port **8585**:
loopback by default, LAN-reachable when `POLIS_HARNESS_IP` is set in `.env`
(the web UI needs this). Every endpoint is JSON; the web UI is served from
the mod folder under `/polis/ui/` (per-request, no-cache).

**Two contracts govern all use:**

1. **`worldReady` first.** `GET /polis/status` gates everything — no
   command runs before the server is in `WorldReady`.
2. **Fire-and-verify.** A command can report `ok: true` at *issuance* and
   fail later (async engine work). Every action ends with a re-read —
   `state` (and for placement, the oracle: a `targets`/`scan` over the
   affected cells). The `ok` flag is a receipt, not a verdict.

## The command channel

```
POST /polis/command
  { "cmd": "goto", "args": [100, 65, -200],
    "context": { "playerUid": "...", "botId": 232, "actor": "user|agent|devops|harness" } }
```

This is the *only* door to the engine's action system; the full command
surface (65 subcommands) is documented in `CLI.md` — the CLI is a thin
wrapper over this endpoint. `/polis/servercmd` (raw in-game chat command,
e.g. `/time set 0`) and `/polis/admin/*` are **loopback-gated**.

## Read endpoints

| Endpoint | What |
|----------|------|
| `GET /polis/status` | `harness{running, port}`, `server{runPhase, worldReady}`, `websocket{connections}` |
| `GET /polis/state?botId=&radius=10` | The bot's full state (position, last action, inventory, health) + world context within `radius` |
| `GET /polis/players` / `/polis/player?uid=` | Online players / one player (UIDs contain `+` — URL-encode as `%2B` in query strings) |
| `GET /polis/bots` | All polisbots (id, name, pos, activity) |
| `GET /polis/look?uid=&range=48` | Ray-traces from the player's *actual* eye + orientation; returns the exact block hit (`blockSelection`) — the ground truth for aim questions |
| `GET /polis/targets` | Nearby interactables (below) — the discovery workhorse |
| `GET /polis/vitals?uid=` | The vitals sampler's latest samples (saturation/health/position/skills per bot + player) + the world clock; the per-world persistence behind the stats panel (see `docs/design/food-hunger-skills-policies.md`) |
| `GET /polis/zones` / `/polis/zone-check?botId=` | Named zone registry / which zones a bot is in |
| `GET /polis/container-contents?name=\|x=&y=&z=` | Container inventory (by name or coordinates) |
| `GET /polis/events?limit=20` | Recent event-stream history (the same feed the WebSocket pushes) |
| `GET /polis/screenshot?playerUid=&save=` | Player-POV screenshot (base64 PNG in response; `--save` writes a file) |
| `GET /polis/observer-screenshot?playerUid=&x=&y=&z=&yaw=&pitch=` | Screenshot from an *arbitrary* viewpoint: sets the player's view, captures, restores. One capture in flight at a time (concurrent requests get `ok:false`). This is the visual-verification tool the agent loops use |
| `GET /polis/debug/charsel`, `POST /polis/admin/moddata` | First-run-dialog rescue (the dialog is unconfirmable headless; moddata is set via the game's own `SetModData`) |

## `/polis/targets` (discovery)

```
GET /polis/targets?playerUid=<uid>&botId=<id>&radius=6&limit=20
            &mode=blocks|entities|all&q=<text>&codeContains=<substr>&requireEntityClass=<class>
            &zone=<name>
```

Anchor: `botId` (preferred once a bot exists) or `playerUid`. `radius`
clamps 1..32, `limit` caps the response (keep it small — this endpoint is
the token-budget killer by default). `q` matches block code *and* item
code; `codeContains` is a substring filter. `zone=<name>` constrains the
scan to a named zone's AABB from the zone registry (radius still applies
inside it; the response gains a `Zone` field) — this is how "what is
stored in storage1" works: ground items are entities, so they appear in
the `entities` results with their item codes.

Block entry: `{ X, Y, Z, Code, ... }` (integer cell coords, `game:`-domain
code). Entity entry: `{ Id, Code, Pos, ItemCode, ... }` (`ItemCode` set
for carried items — how you find "the bot holding the rye"). Dead entities
excluded by default (`includeDead=` to override).

## Event stream (WebSocket)

```
ws://<host>:8585/polis/ws     subscribe: { "subscribe": { "level": "normal|info|debug" } }
```

Game events (spawn/despawn, actions started/finished, **`command` events
with `actor`** — the who-did-what backbone of the action stream, world
changes, errors). `GET /polis/events` gives the recent history for
re-join. The web UI's console pane is this stream.

## Web UI

`GET /polis/ui/` — the instrument panel (state, commands, live view,
Oikistes chat; design contract in `design/webui-design.md`). Served from
the mod folder per request — a file copy into the deployed mod dir is a
deploy; the pre-deploy gate is `tools/webui/syntax-check.sh` (acorn ESM
parse — `node --check` is *not* a module gate).
