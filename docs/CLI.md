# Polis CLI reference

`scripts/poliscli.py` — the command-line interface to the in-game harness.
Pure Python stdlib, no dependencies; the ergonomic front for agents and
humans alike (the raw HTTP surface is documented in `harness.md`).

The command table below mirrors the argparse of the script (65 subcommands
as of the R2 pass) — when in doubt, `poliscli.py <cmd> --help` is exact.

## Usage

```sh
python3 scripts/poliscli.py status          # or an alias: polis
```

## Environment variables

```bash
export POLIS_PLAYER_UID="abc+123YourPlayerUidHere"  # your player UID
export POLIS_BOT_ID="12345"                          # selected bot ID
```

**Player UIDs contain `+`** — the harness parses raw queries (keeps `+`),
but any *form-encoded* path must URL-encode it as `%2B` (form-decoding
turns `+` into a space and every UID lookup silently fails).

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Command failed (action error from harness) |
| 2 | Usage error (bad args, missing required params) |
| 3 | Connection error (harness unreachable) |

## Global flags

All commands accept:

```
--host HOST        Harness host (default: localhost)
--port PORT        Harness port (default: 8585)
--player UID       Player UID (overrides $POLIS_PLAYER_UID)
--bot ID           Bot ID (overrides $POLIS_BOT_ID)
--json             Force JSON output (default: TOON if available)
--quiet, -q        Minimal output (OK/FAIL + essential info)
--verbose, -v      Debug output
--tokens, -t       Show token count comparison (TOON vs JSON)
--timeout SEC      Wait timeout in seconds (default: 30)
```

TOON output is the default when the `toon` module is present — it is the
token-efficient format the agent loops consume.

## Commands

### Read

| Command | What |
|---------|------|
| `status` | Check server readiness |
| `players` | List online players |
| `player` | Get player info |
| `bots` | List all bots |
| `state` | Get bot state |
| `targets` | Get nearby interactables |
| `look` | Get player look target |
| `professions` | List available professions |
| `scan` | Scan a region and return block data |
| `verify` | Verify a blueprint against world state |
| `vitals` | Latest vitals samples (saturation, health, position, skills) for all bots + the player, or one by uid: `vitals [uid]` — the 1 Hz sampler's snapshot (`PolisVitalsSampler`; per-world persistence + `GET /polis/vitals` see `docs/harness.md`) |
| `zone-list` | List all named zones |
| `zone-check` | Check which zones a bot is in |
| `zone-show` | Highlight a zone's boundaries |
| `viewpoint-list` | List all named viewpoints |
| `container-list` | List registered containers |
| `container-contents` | Get container contents |

### Bot lifecycle & movement

| Command | What |
|---------|------|
| `spawn` | Spawn a new bot |
| `select` | Select a bot by ID |
| `despawn` | Despawn selected bot |
| `goto` | Move bot to coordinates |
| `stop` | Stop current bot activity |
| `possess` | Mount player onto bot |
| `unpossess` | Unmount player from bot |
| `controls` | Set movement controls while possessing |
| `spawnkill` | Spawn entity and kill immediately (butcher prep) |
| `spawnentity` | Spawn a live entity |
| `animate` | Play or stop animations on selected bot |
| `teleport` | Teleport player with optional view direction |

### Inventory & items

| Command | What |
|---------|------|
| `give` | Give item to bot |
| `equip` | Equip item to bot slot |
| `drop` | Drop items from bot hand |
| `pickup` | Pick up nearby item |
| `pick` | Pick a forageable plant (e.g. a ripe berry bush) at `x y z` (up to `[count]` pick rounds) — the bot must be adjacent; the same action path the food-pressure forage interrupt uses (`PolisPickBushAction`) |
| `takefrom` | Take items from container (x y z slot [qty] OR -c name |
| `putinto` | Put items into container (x y z slot [qty] OR -c name |
| `loot` | Loot items from dead entity inventory |

### Block & world actions

| Command | What |
|---------|------|
| `activate` | Activate a block (door, chest, etc.) |
| `ignite` | Ignite an IIgnitable block (firepit, torch, etc.) |
| `mine` | Mine a block |
| `break` | [DEBUG] Instantly break a block (no mining time) |
| `place` | Place a block (requires item in inventory) |
| `setblock` | Directly set block in world (admin, no bot needed) |
| `harvest` | Harvest a block (berries, resin) |
| `harvestcrop` | Harvest a farmland crop |
| `interact` | Interact with an entity (feed, shear, etc.) |
| `build` | Build from a blueprint with verification |

### Workstations (crafting)

| Command | What |
|---------|------|
| `forge-heat` | Wait for firepit input to reach temperature |
| `grind` | Grind items in a quern |
| `press` | Press fruit in a fruit press |
| `clayform` | Form clay into a recipe shape |
| `knap` | Knap flint/stone into tools |
| `seal` | Seal a barrel for fermentation/pickling |
| `anvil-smith` | Smith a work item on an anvil |
| `anvil-state` | Get anvil state (work item, recipe, voxels) |
| `smith-loop` | Complete smithing loop: fuel forge, heat, smith with |

### Butchery & containers

| Command | What |
|---------|------|
| `butcher` | Butcher a dead entity |
| `container-register` | Register a named container |
| `container-remove` | Remove container from registry |
| `container-set` | Set container slot directly (x y z slot itemCode |

### Food & satiety

| Command | What |
|---------|------|
| `hunger` | Read the engine's `hunger` tree (saturation 0-1500, 5 nutrition levels, delays, health) for all bots + the player, or one bot by id: `hunger [botId]` |
| `eat` | Engine satiety path: `eat <itemCode> [count=1]` — gives the item if missing, calls `ReceiveSaturation` with the item's per-variant `FoodNutritionProperties` (clamping, nutrition levels, sync), applies Health, maintains the 1.22 intoxication/psychedelic floats, consumes the stack, hands back `EatenStack`. Verified: `eat game:fruit-blueberry 3` = exactly +240 saturation |
| `hungerpause` | `hungerpause [on|off]` (selected bot) — toggles the bot-level gate of the polis hunger behavior (parked bots: no active mission ⇒ no drain). The world-level gate is a file, not a command: `<VSDATA>/Saves/<world>/polis/hunger.json` with `{"hungerMode":"off"}` suspends the drain for the whole world (dev/creative/debug worlds). Both verified 2026-10-04: flat saturation while set, drain resumes on release. See `docs/design/food-hunger-skills-policies.md` (creative/dev world decision) and `src/EntityBehaviorPolisHunger.cs` |
| `policy` | Policy layer (the interaction rules): no args → dump the live `polis-policies.json` (path + mtime + content); `policy <domain> <itemCode>` → verdict (`allow`/`deny` + reason + resolved food category). The file is committed at `assets/polis/polis-policies.json` and hot-reloaded on change (no restart) — the `eat` command is gated by it (denial = `Ok:false` with the reason, no items given) |

### Crucible (the smelting pot — pot work)

The 1.22 crucible is a clayformed vessel that goes *into* the firepit
(ground-storable → firepit → the engine's smelting-container engine),
not a standalone block: clayform the block (`clayforming/crucible` recipe,
input `clay-<color>`, output `crucible-<color>-raw` — colors fire/blue/
red), place it into a firepit, load ore + fuel, the engine smelts, then
take/pour. The same base serves the food cooking pot later.

| Command | What |
|---------|------|
| `crucible-fire` | `crucible-fire [color] [x y z]` — places a `crucible-<color>-raw` block from the bot's cargo into a firepit (nearest from the bot, or the given cell) and ignites it |
| `crucible-insert` | `crucible-insert <itemCode> [count] [x y z]` — move item stacks from the bot's cargo into the firepit's 4 cooking (smelt) slots |
| `crucible-fuel` | `crucible-fuel [itemCode=charcoal] [count=8] [x y z]` — fuel into the firepit's fuel slot; re-asserts ignition |
| `crucible-take` | `crucible-take [x y z]` — take the smelted output from the nearest fired crucible; reports `hot`/`hasTongs` (advisory — in 1.22.7 tongs are a wear mechanic, not a hard gate) |
| `crucible-pour` | `crucible-pour <x y z> [units]` — pour the melt over a mold at a ground position (the engine's solidification gate; the crucible reverts to its fired-empty block when emptied) |

### View & capture

| Command | What |
|---------|------|
| `screenshot` | Capture screenshot from player view |
| `setup-view` | Position player to view selected bot |
| `viewpoint-define` | Define a named viewpoint for observer screenshots |
| `viewpoint-remove` | Remove a named viewpoint |

### Admin & zones

| Command | What |
|---------|------|
| `exec` | Execute raw server command (local only) |
| `zone-define` | Define a named AABB zone |
| `zone-rename` | `zone-rename <oldName> <newName>` — rename a zone in place (bounds preserved, persisted) — storage areas and the like change names with the plan |
| `zone-remove` | Remove a named zone |

## Missions

Multi-step test runs are driven by `scripts/polis-test-runner.py` (missions
= setup → steps with waits → assertions → PASS/FAIL/ERROR); see
`TESTING.md` for the protocol.
