# Roadmap / Next Steps

This is a small, actionable plan so a new session can pick up immediately.

## Immediate Next Step

**Test verifiable building system** - New scan/verify/build commands need in-game testing. See `docs/research/misc/2026-01-19-verifiable-building-test-plan.md` for step-by-step test procedure.

## Recent Additions

- **Knapping Action** (2026-01-22): Bot can knap flint/stone on knapping surfaces to create tools.
  - `knap <x> <y> <z> <recipe> [speed]` command
  - Progressive voxel removal with animation (opposite of clay forming)
  - Auto-places material from bot inventory if surface is empty
  - Items go to bot inventory (or ground if full)
  - Recipes: `arrowhead-flint`, `knifeblade-flint`, `axehead-flint`, `hoehead-flint`, etc.

- **Fruit Press Action** (2026-01-22): Bot can operate fruit presses to extract juice.
  - `press <x> <y> <z>` command with `--duration` and `--no-autounscrew` options
  - Uses screw interaction to compress fruit mash
  - Auto-unscrew option for continuous operation
  - Reports liters extracted on completion

- **Clay Forming Action** (2026-01-22): Bot can form clay into shapes on clayforming surfaces.
  - `clayform <x> <y> <z> <recipe> [speed]` command
  - Progressive voxel placement with visible animation
  - Consumes clay from bot inventory
  - Recipes: `bowl-raw`, `crock-raw`, `toolmold-fire-raw-anvil`, etc.
  - Test report: `docs/journal/2026-01-22-clayform-progressive-animation.md`

- **Quern Grind Action** (2026-01-22): Bot can grind items in querns (grain → flour).
  - `grind <x> <y> <z>` command with `--count` and `--duration` limits
  - Uses held-use block interaction pattern (OnBlockInteractStart/Step/Stop)
  - SelectionBoxIndex=1 triggers grinding (index 0 opens GUI)
  - Plays hit animation during grinding
  - Test report: `docs/journal/2026-01-22-grind-action-testing.md`

- **Web UI v2 Design** (2026-01-19): Comprehensive design for observation platform. Three-layer world view (screenshot + structured 3D + LLM text), context-driven UI, IndexedDB state layer, agent WebSocket integration. Design doc: `docs/design/webui-v2-design.md`.

- **Verifiable Building System** (2026-01-19): Blueprint-driven construction with verification.
  - `scan` command: Capture world blocks as blueprints
  - `verify` command: Compare blueprints against world state (match %, missing/wrong lists)
  - `build` command: Construct from blueprints with per-block verification
  - CLI support: `poliscli.py scan/verify/build` with `--origin`, `--dry-run`, `--relative`
  - Enables deterministic, resumable builds with progress tracking
  - Test plan: `docs/research/misc/2026-01-19-verifiable-building-test-plan.md`

- **vsctl Game Controller** (2026-01-18): Python tool for automated VS lifecycle control. Enables fully agentic development loop. See `docs/journal/2026-01-18-vsctl-game-controller.md`.
  - Commands: `vsctl start --wait`, `vsctl stop`, `vsctl restart`, `vsctl status`
  - Three-stage ready detection: server ready → client render signal → post-delay
  - Clean shutdown via `/stop` command (saves world before kill)
  - Discovered ~25s gap between `worldReady=true` and client visually ready

- **Event History Endpoint** (2026-01-17): Added `/polis/events` endpoint for querying recent events. Web UI now uses 1-second polling instead of WebSocket for reliable event display. Also added `websocket.connections` to `/polis/status`.

- **Butcher Harvest Transfer Fix** (2026-01-17): Fixed incomplete harvest transfer bug. The original code created a LOCAL copy of the harvest inventory from tree attributes but never cleared the actual inventory slots. Now accesses `EntityBehaviorHarvestable.Inventory` directly and clears each slot after transfer so VS properly detects the corpse is empty and despawns it to carcass.

- **CLI Testing Session** (2026-01-17): Comprehensive testing of CLI and bot actions. See `docs/journal/2026-01-17-cli-testing-session.md`.
  - Tested: status, players, bots, state, spawn, select, give, drop, pickup, goto --wait, butcher, mine, putinto, targets, look
  - New command: `spawnkill` - spawn entity and kill immediately (for butcher testing)
  - Fixed: spawn offset now uses array format, default 2-block offset from player
  - **Bug found**: Butcher transfers incomplete harvest inventory (needs investigation)

- **VS Two-Stage Harvest Documented**:
  1. Dead animal (entity) → butcher with knife → meat, fat, hide
  2. Carcass (block) → mine/break → bones
  - Carcass is a BLOCK (`game:carcass-medium`), not entity - use `mine` not `butcher`

- **Polis CLI Tool** (2026-01-17): Python CLI wrapper for HTTP harness. 27 commands, TOON output (25-32% token savings). See `docs/CLI.md`.

- **PolisButcherEntityAction** (2026-01-17): Butcher dead entities using `EntityBehaviorHarvestable.SetHarvested()`. Requires knife in right hand.
  - **Resolved**: Correct knife format is `game:knife-generic-copper`
  - **Fixed**: Incomplete harvest transfer - now clears slots in actual inventory after transfer

## Follow-ups

- **Web UI v2** - Redesigned observation platform with three-layer world view (screenshot, structured 3D, LLM text), context-driven actions, IndexedDB state layer, and agent integration. See `docs/design/webui-v2-design.md`.
- **Fix mine autocollect** - `--autocollect` flag not picking up dropped items.
- **Container registry** - Shadow registry for containers/workstations so bots can reference storage locations.
- **Spawn forward direction** - Support spawning in player's look direction using yaw.
- Improve path visualization (line renderer instead of block highlights).
- Add a compact debug HUD: current target, path length, stuck reason.
