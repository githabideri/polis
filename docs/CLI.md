# Polis CLI Reference

Command-line interface for the polis HTTP test harness. Designed for ergonomic LLM/agent use.

## Installation

The CLI is a standalone Python script with no external dependencies (stdlib only).

```bash
# Run directly
./scripts/poliscli.py status

# Or create an alias
alias polis='./scripts/poliscli.py'
polis status
```

### Optional: TOON Output

For 26% token savings vs JSON, install `python-toon`:

```bash
pip install python-toon
```

The CLI falls back to JSON if TOON is not available.

## Environment Variables

Set these to avoid repeating common arguments:

```bash
export POLIS_PLAYER_UID="abc+123YourPlayerUidHere"  # Your player UID
export POLIS_BOT_ID="12345"                          # Selected bot ID
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Command failed (action error from harness) |
| 2 | Usage error (bad args, missing required params) |
| 3 | Connection error (harness unreachable) |

## Global Flags

All commands accept these flags:

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

## Query Commands

### status

Check server readiness.

```bash
polis status
```

Returns exit code 0 if `worldReady=true`, exit code 1 otherwise.

### players

List online players with positions.

```bash
polis players
```

### player

Get detailed player info.

```bash
polis player                     # Uses $POLIS_PLAYER_UID
polis player "abc+123YourPlayerUidHere"
```

### bots

List all bots.

```bash
polis bots
```

### state

Get bot state including inventory and nearby items.

```bash
polis state                      # Uses $POLIS_BOT_ID
polis state 12345                # Specific bot
polis state --radius 10          # Expand item scan radius
```

### targets

Get nearby interactable blocks and entities.

```bash
polis targets                    # Default radius 8
polis targets --radius 16
polis targets --mode blocks      # Only blocks
polis targets --mode entities    # Only entities
polis targets --query "chest"    # Search filter
```

### look

Get what a player is looking at (server-side raytrace).

```bash
polis look                       # Uses $POLIS_PLAYER_UID
polis look --range 64            # Extended range
```

## Action Commands

### spawn

Spawn a new bot.

```bash
polis spawn                      # At world spawn
polis spawn 100 65 -200          # At coordinates
polis spawn --entity game:wolf-male   # Specific entity type
```

On success with `--quiet`, prints `BOT_ID=<id>` for easy capture:

```bash
BOT_ID=$(polis spawn -q | grep BOT_ID | cut -d= -f2)
export POLIS_BOT_ID=$BOT_ID
```

### select

Select a bot for subsequent commands.

```bash
polis select 12345
export POLIS_BOT_ID=12345        # Persist selection
```

### despawn

Despawn the selected bot.

```bash
polis despawn
```

### goto

Move bot to coordinates.

```bash
polis goto 100 65 -200           # Start moving (returns immediately)
polis goto 100 65 -200 --wait    # Wait for arrival
```

### stop

Cancel current bot activity.

```bash
polis stop
```

### give

Give an item to the bot's inventory.

```bash
polis give game:pickaxe-copper
polis give game:stone-granite 10
```

### equip

Equip an item directly to a specific slot.

```bash
polis equip righthand game:pickaxe-copper
polis equip lefthand game:torch-basic 5
polis equip backpack0 game:linensack
polis equip backpack1 game:linensack
```

Slots: `lefthand`, `righthand`, `backpack0`, `backpack1`

### drop

Drop items from bot's hand.

```bash
polis drop                       # Auto-select hand, drop all
polis drop 0                     # From right hand
polis drop 1 5                   # 5 items from left hand
```

Slots: -1=auto, 0=right hand, 1=left hand

### pickup

Pick up a nearby item.

```bash
polis pickup                     # Nearest item within 3 blocks
polis pickup 67890               # Specific entity ID
polis pickup --range 5           # Extended range
```

### activate

Activate a block (door, chest, lever, etc.).

```bash
polis activate 100 65 -200
```

Requires `--player` or `$POLIS_PLAYER_UID`.

### mine

Mine a block. Waits for completion by default.

```bash
polis mine 100 65 -200
polis mine 100 65 -200 --autocollect    # Auto-pickup drops
polis mine 100 65 -200 --no-wait        # Don't wait for completion
```

Requires `--player` or `$POLIS_PLAYER_UID`. Bot must have appropriate tool equipped.

### place

Place a block from bot's inventory. Waits for completion by default.

```bash
polis place game:cobblestone-granite 100 65 -200
polis place game:cobblestone-granite 100 65 -200 --face north
polis place game:cobblestone-granite 100 65 -200 --no-wait
```

Coordinates specify where the block will be placed (target position). Face options: `up`, `down`, `north`, `south`, `east`, `west`.

Requires `--player` or `$POLIS_PLAYER_UID`. Bot must have the block in inventory.

### setblock

Directly set a block in the world (admin/debug, no bot needed).

```bash
polis setblock game:cobblestone-granite 100 65 -200
polis setblock air 100 65 -200          # Clear block
```

Argument order matters: `setblock <blockcode> <x> <y> <z>`.

### harvest

Harvest a harvestable block (berries, resin).

```bash
polis harvest 100 65 -200
polis harvest 100 65 -200 --autocollect
polis harvest 100 65 -200 --no-validate  # Skip ripeness check
```

### harvestcrop

Harvest a farmland crop.

```bash
polis harvestcrop 100 65 -200
polis harvestcrop 100 65 -200 --autocollect
```

### grind

Grind items in a quern. Waits for completion by default.

```bash
polis grind 100 65 -200              # Grind until input exhausted
polis grind 100 65 -200 --count 5    # Grind at most 5 items
polis grind 100 65 -200 --duration 10  # Grind for at most 10 seconds
polis grind 100 65 -200 --no-wait    # Don't wait for completion
```

Options:
- `--count, -c INT`: Maximum items to grind (0 = unlimited)
- `--duration, -d FLOAT`: Maximum grinding time in seconds (0 = unlimited)
- `--no-wait`: Don't wait for grinding to complete

The quern must have grindable items (grain, etc.) in its input slot.

### press

Press fruit in a fruit press to extract juice. Waits for completion by default.

```bash
polis press 100 65 -200               # Press until complete
polis press 100 65 -200 --duration 15 # Press for at most 15 seconds
polis press 100 65 -200 --no-autounscrew  # Don't auto-unscrew when complete
polis press 100 65 -200 --no-wait     # Don't wait for completion
```

Options:
- `--duration, -d FLOAT`: Maximum pressing time in seconds (0 = unlimited)
- `--no-autounscrew`: Don't automatically unscrew when pressing completes
- `--no-wait`: Don't wait for pressing to complete

The fruit press must have fruit mash loaded and a bucket in position.

### clayform

Form clay into a recipe shape. Places voxels progressively with animation.
Bot must have clay in inventory. Waits for completion by default.

```bash
polis clayform 100 65 -200 bowl-raw                 # Form a clay bowl
polis clayform 100 65 -200 toolmold-fire-raw-anvil  # Form an anvil toolmold
polis clayform 100 65 -200 bowl-raw --speed 8       # Faster forming
polis clayform 100 65 -200 bowl-raw --no-wait       # Don't wait for completion
```

Options:
- `--speed, -s INT`: Voxels per tick (default: 4, higher = faster animation)
- `--no-wait`: Don't wait for forming to complete

The recipe name is typically the output item code (e.g., `bowl-raw`, `crock-raw`,
`toolmold-fire-raw-anvil`). Complex recipes (like anvil toolmold with ~750 voxels)
take longer to form - the animation speed can be increased with `--speed`.

### knap

Knap flint or stone into tools. Removes voxels progressively with animation.
Bot must have knapping material in inventory. If the knapping surface is empty,
the bot will automatically place material from inventory. Waits for completion by default.

```bash
polis knap 100 65 -200 arrowhead-flint           # Knap a flint arrowhead
polis knap 100 65 -200 knifeblade-flint          # Knap a flint knife blade
polis knap 100 65 -200 axehead-flint --speed 8   # Faster knapping
polis knap 100 65 -200 hoehead-flint --no-wait   # Don't wait for completion
```

Options:
- `--speed, -s INT`: Voxels per tick (default: 4, higher = faster animation)
- `--no-wait`: Don't wait for knapping to complete

The recipe name is the output item code (e.g., `arrowhead-flint`, `knifeblade-flint`,
`axehead-flint`, `hoehead-flint`). Different materials have different recipes
(e.g., `arrowhead-obsidian` for obsidian arrowheads).

**Note:** Requires a `knappingsurface` block at the target position. The surface
can be empty (bot will initialize it with material) or already have matching material.

### seal

Seal a barrel for fermentation/pickling. The barrel must contain items and liquid
matching a valid sealing recipe (e.g., vegetables + brine for pickling).

```bash
polis seal 100 65 -200              # Seal barrel at coordinates
```

Once sealed, the barrel contents will ferment over time. Barrels auto-unseal when
fermentation completes - there is no manual unseal command.

**Note:** The barrel must contain a valid combination of items + liquid that matches
a sealing recipe. Empty barrels or barrels without matching recipes cannot be sealed.

### takefrom

Take items from a container.

```bash
polis takefrom 100 65 -200 0             # All from slot 0
polis takefrom 100 65 -200 2 5           # 5 items from slot 2
```

### putinto

Put items into a container.

```bash
polis putinto 100 65 -200 0              # Bot's right hand into container
polis putinto 100 65 -200 1 3            # 3 from left hand
```

Bot slots: 0=right hand, 1=left hand, 2+=backpack

### butcher

Butcher a dead entity.

```bash
polis butcher 12345
polis butcher 12345 --no-autocollect
```

Bot must have a knife equipped. Entity must be dead.

### possess

Mount player onto the selected bot for direct control.

```bash
polis select 12345
polis possess
```

### unpossess

Unmount player from bot.

```bash
polis unpossess
```

### controls

Set movement controls while possessing.

```bash
polis controls --fwd                     # Move forward
polis controls --fwd --sprint            # Sprint forward
polis controls --fwd --right --jump      # Diagonal jump
polis controls                           # Stop all movement
```

Flags: `--fwd`, `--back`, `--left`, `--right`, `--sprint`, `--jump`

### animate

Play or stop animations on the selected bot.

```bash
polis animate hit                        # Play one-shot animation
polis animate hit --speed 1.5            # With speed modifier
polis animate interact --loop            # Loop until stopped
polis animate stop                       # Stop all animations
polis animate stop hit                   # Stop specific animation
```

Options:
- `--speed, -s FLOAT`: Animation speed multiplier (0.1-10.0, default: 1.0)
- `--loop, -l`: Loop animation until explicitly stopped

Standard humanoid animation codes: `walk`, `run`, `idle`, `hit`, `attack`, `interact`, `dig`, `chop`

### teleport

Teleport a player to coordinates with optional view direction (yaw/pitch).

```bash
polis teleport 100 65 -200                       # Position only
polis teleport 100 65 -200 --yaw east            # Face East
polis teleport 100 65 -200 --yaw n               # Face North
polis teleport 100 65 -200 --yaw 1.57            # Yaw in radians
polis teleport 100 65 -200 --yaw bot             # Face the selected bot
polis teleport 100 65 -200 --face 105 -195       # Face specific X Z coordinates
polis teleport 100 65 -200 --face-bot            # Shorthand for --yaw bot
polis teleport 100 65 -200 --yaw e --pitch -0.3  # Look slightly down
```

Requires `--player` or `$POLIS_PLAYER_UID`.

**Yaw options:**
- Cardinal directions: `n`, `s`, `e`, `w`, `ne`, `nw`, `se`, `sw` (or full names like `north`)
- Radians: any numeric value
- `bot`: automatically calculate yaw to face the selected bot

**Pitch:** Radians. 0 = level, negative = look down, positive = look up.

**VS Yaw Convention:** `yaw = atan2(dx, dz) + π` where dx = target.x - player.x, dz = target.z - player.z

### screenshot

Capture a screenshot from a player's game client.

```bash
polis screenshot                         # Capture and return base64
polis screenshot --save                  # Also save to file on client
polis screenshot -q                      # Quiet: just show OK/FAIL + dimensions
```

Requires `--player` or `$POLIS_PLAYER_UID`.

Screenshots are saved to `~/Pictures/Vintagestory/polis/` when `--save` is used.

## Dev/Debug Commands

### exec

Execute a raw server command (local only).

```bash
polis exec "/time set 0"
polis exec "/weather setprecip 0"
```

### spawnkill

Spawn an entity and immediately kill it (useful for butcher testing).

```bash
polis spawnkill game:sheep-bighorn-adult-male           # 1 block from bot
polis spawnkill game:chicken-hen 100 65 200             # At specific coords
```

Entity code format: `game:{animal}-{variant}-{age}-{gender}`
- `game:sheep-bighorn-adult-male`
- `game:chicken-hen` (chickens don't have age/gender variants)

## Example Workflows

### Basic Bot Control

```bash
export POLIS_PLAYER_UID="<your-uid>"

# Check server ready
polis status

# Spawn and select bot
polis spawn
polis bots                           # Note the bot ID
export POLIS_BOT_ID=<id>
polis select $POLIS_BOT_ID

# Give item and verify
polis give game:stone-granite 5
polis state

# Move bot
polis goto 100 65 -200 --wait
```

### Mining Workflow

```bash
# Give pickaxe
polis give game:pickaxe-copper

# Find ore
polis targets --mode blocks -q "ore"

# Mine it (waits for completion)
polis mine 218 3 263 --autocollect

# Check inventory
polis state
```

### Butcher Workflow

```bash
# Give knife (note: format is knife-{type}-{material})
polis give game:knife-generic-copper

# Spawn and kill animal for testing
polis spawnkill game:sheep-bighorn-adult-male
# Note the entity ID from output

# Butcher the corpse
polis butcher <entity-id>

# Check inventory for drops
polis state

# Store in chest
polis putinto <chest-x> <chest-y> <chest-z> 1
```

**Note:** After butchering, if corpse is fully emptied, it becomes a `game:carcass-*` block. Use `polis mine` to break it for bones.

### Container Interaction

```bash
# Find chest
polis targets --mode blocks -q "chest"

# Take from slot 0
polis takefrom 224 3 270 0

# Check inventory
polis state

# Put back
polis putinto 224 3 270 0
```

## Visual Testing Workflow

Pattern for capturing screenshots of bot animations or actions with reliable timing.

### Setup: Position Player to View Bot

```bash
export POLIS_PLAYER_UID="<your-uid>"

# 1. Spawn bot near player (3 blocks offset on X axis)
polis spawn
export POLIS_BOT_ID=<id-from-output>
polis select $POLIS_BOT_ID

# 2. Get bot position
polis state   # Note the Pos values

# 3. Teleport player 2 blocks away facing the bot
# If bot is at (223, 3, 272), position player at (221, 3, 272) facing East
polis teleport 221 3 272 --yaw e

# Or use --face-bot to auto-calculate yaw
polis teleport 221 3 272 --face-bot
```

### Capturing Animations

**Key insight:** Token generation takes longer than short animations. Chain commands in a single bash invocation to capture mid-animation frames.

```bash
# One-shot animation: use slow speed to catch it
polis animate hit --speed 0.3 && polis screenshot --save

# Looping animation: start, wait briefly, capture
polis animate walk --loop && sleep 0.3 && polis screenshot --save

# Multiple frames of looping animation
polis animate walk --loop && \
  sleep 0.3 && polis screenshot --save && \
  sleep 0.3 && polis screenshot --save && \
  sleep 0.3 && polis screenshot --save

# Stop and verify return to idle
polis animate stop && sleep 0.2 && polis screenshot --save
```

### Verifying Animation State

The `animate stop` command reports how many animations were actually running:

```bash
polis animate stop
# "Stopped 1 animation(s)" = animation was running
# "Stopped 0 animation(s)" = animation wasn't actually playing (code may not exist)
```

### Working Animation Codes (polisbot entity)

Tested and confirmed working:
- `hit` - arm swing, one-shot
- `walk` - leg movement, works looping

Not working (API returns success but no visual, stop returns 0):
- `interact`, `sit`, `run` - may not exist in polisbot shape file

### Complete Visual Test Sequence

```bash
export POLIS_PLAYER_UID="<your-uid>"

# Setup
polis spawn && export POLIS_BOT_ID=$(polis bots -q | tail -1 | cut -d: -f1)
polis select $POLIS_BOT_ID
BOT_POS=$(polis state -q | grep Pos | head -1)
# Manually position player 2 blocks from bot, facing it

# Test one-shot with slow speed
polis animate hit --speed 0.3 && polis screenshot --save
# Check screenshot for arm extended

# Test looping
polis animate walk --loop && sleep 0.3 && polis screenshot --save
polis animate stop  # Should report "Stopped 1"

# Cleanup
polis despawn
```

## Output Formats

### TOON (Default)

Compact format optimized for LLM token usage:

```
{Bot:{Id:12345,Pos:[100.5,65,200.3],RightHand:{Code:"game:stone",Qty:5}}}
```

### JSON (--json)

Standard JSON for debugging/scripting:

```json
{
  "Bot": {
    "Id": 12345,
    "Pos": [100.5, 65, 200.3],
    "RightHand": {"Code": "game:stone", "Qty": 5}
  }
}
```

### Quiet (--quiet)

Minimal output for scripting:

```
OK
BOT_ID=12345
```

Or on failure:

```
FAIL: out of range dist=8.5 range=3.0
```

### Token Count (--tokens)

Shows token comparison between TOON and JSON formats:

```bash
polis state --tokens
```

Output includes a footer with token stats:
```
Bot:
  Id: 365
  Pos[3]: 219.68,3.0,268.05
  ...
--- tokens: 92 (TOON) | JSON: 123 | TOON: 92 | savings: 25.2% ---
```

Useful for measuring actual LLM token savings.
