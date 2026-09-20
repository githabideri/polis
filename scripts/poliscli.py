#!/usr/bin/env python3
"""
Polis CLI - Command-line interface for the polis-builder-npc HTTP test harness.

Provides ergonomic commands for LLM/agent use with optional TOON output format.
"""
import argparse
import json
import math
import os
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import quote

# Exit codes
EXIT_SUCCESS = 0
EXIT_COMMAND_FAILED = 1
EXIT_USAGE_ERROR = 2
EXIT_CONNECTION_ERROR = 3

# Try to import toon for compact output
try:
    from toon import encode as toon_encode
    TOON_AVAILABLE = True
except ImportError:
    TOON_AVAILABLE = False
    toon_encode = None
_toon_warned = False

# Try to import tiktoken for token counting
try:
    import tiktoken
    _tiktoken_enc = tiktoken.get_encoding("cl100k_base")
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False
    _tiktoken_enc = None


class HarnessClient:
    """HTTP client for the polis test harness."""

    def __init__(self, host: str, port: int, timeout: float = 5.0):
        self.base_url = f"http://{host}:{port}"
        self.timeout = timeout

    def get(self, path: str, params: dict = None):
        """Make a GET request."""
        if params:
            query = "&".join(f"{k}={quote(str(v), safe='')}" for k, v in params.items() if v is not None)
            if query:
                path = f"{path}?{query}"
        return self._request("GET", path)

    def post(self, path: str, payload: dict):
        """Make a POST request with JSON body."""
        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        return self._request("POST", path, data=data, headers=headers)

    def _request(self, method: str, path: str, data=None, headers=None):
        if headers is None:
            headers = {}
        url = self.base_url + path
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8") if exc.fp else ""
            raise ConnectionError(f"HTTP {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise ConnectionError(f"Connection failed: {exc}") from exc

        try:
            return json.loads(raw) if raw else {}
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON: {raw}") from exc


class OutputFormatter:
    """Handles output formatting (TOON, JSON, or quiet)."""

    def __init__(self, use_json: bool = False, quiet: bool = False, verbose: bool = False, show_tokens: bool = False):
        self.use_json = use_json
        self.quiet = quiet
        self.verbose = verbose
        self.show_tokens = show_tokens

    def count_tokens(self, text: str) -> int:
        """Count tokens in text using tiktoken."""
        if TIKTOKEN_AVAILABLE and _tiktoken_enc:
            return len(_tiktoken_enc.encode(text))
        return -1

    def format(self, data, success_msg: str = None) -> str:
        """Format data for output, optionally with token count."""
        if self.quiet:
            if isinstance(data, dict):
                ok = data.get("Ok", data.get("ok", True))
                if ok:
                    return success_msg or "OK"
                else:
                    msg = data.get("Message", data.get("message", "FAIL"))
                    return f"FAIL: {msg}"
            return success_msg or "OK"

        if self.use_json or not TOON_AVAILABLE:
            if not TOON_AVAILABLE and not self.use_json:
                global _toon_warned
                if not _toon_warned:
                    print("(TOON not available, using JSON. Install: pip install python-toon)", file=sys.stderr)
                    _toon_warned = True
            output = json.dumps(data, indent=2, sort_keys=True)
        else:
            output = toon_encode(data)

        # Append token stats if requested
        if self.show_tokens:
            if not TIKTOKEN_AVAILABLE:
                print("(tiktoken not available for token counting. Install: pip install tiktoken)", file=sys.stderr)
            else:
                toon_output = toon_encode(data) if TOON_AVAILABLE else None
                json_output = json.dumps(data, indent=2, sort_keys=True)

                toon_tokens = self.count_tokens(toon_output) if toon_output else -1
                json_tokens = self.count_tokens(json_output)

                if toon_tokens > 0 and json_tokens > 0:
                    savings = ((json_tokens - toon_tokens) / json_tokens) * 100
                    current_fmt = "TOON" if not self.use_json else "JSON"
                    current_tokens = toon_tokens if not self.use_json else json_tokens
                    output += f"\n--- tokens: {current_tokens} ({current_fmt}) | JSON: {json_tokens} | TOON: {toon_tokens} | savings: {savings:.1f}% ---"
                elif json_tokens > 0:
                    output += f"\n--- tokens: {json_tokens} (JSON) ---"

        return output

    def debug(self, msg: str):
        """Print debug message if verbose."""
        if self.verbose:
            print(f"[debug] {msg}", file=sys.stderr)


def build_context(args, client: HarnessClient = None) -> dict:
    """Build context object from args."""
    ctx = {}
    player_uid = get_player_uid(args, client)
    if player_uid:
        ctx["playerUid"] = player_uid
    bot_id = get_bot_id(args)
    if bot_id:
        ctx["botId"] = int(bot_id)
    return ctx if ctx else None


def get_bot_id(args) -> str:
    """Get bot ID from args or environment."""
    return getattr(args, "bot", None) or os.environ.get("POLIS_BOT_ID")


def get_player_uid(args, client: HarnessClient = None, auto_detect: bool = True) -> str:
    """Get player UID from args, env, or auto-detect single online player.

    Resolution order:
    1. --player arg
    2. $POLIS_PLAYER_UID env var
    3. Auto-detect if exactly one player online (requires client)
    """
    # Check explicit arg
    uid = getattr(args, "player", None)
    if uid:
        return uid

    # Check environment
    uid = os.environ.get("POLIS_PLAYER_UID")
    if uid:
        return uid

    # Auto-detect single player
    if auto_detect and client:
        try:
            result = client.get("/polis/players")
            players = result.get("players", [])
            if len(players) == 1:
                return players[0].get("uid")
        except Exception:
            pass  # Fall through to return None

    return None


# ============================================================================
# Query Commands
# ============================================================================

def cmd_status(client: HarnessClient, args, fmt: OutputFormatter) -> int:
    """Check server readiness."""
    fmt.debug("GET /polis/status")
    result = client.get("/polis/status")
    print(fmt.format(result, "Server ready"))

    server = result.get("server", {})
    if server.get("worldReady"):
        return EXIT_SUCCESS
    return EXIT_COMMAND_FAILED


def cmd_players(client: HarnessClient, args, fmt: OutputFormatter) -> int:
    """List online players."""
    fmt.debug("GET /polis/players")
    result = client.get("/polis/players")
    print(fmt.format(result))
    return EXIT_SUCCESS


def cmd_player(client: HarnessClient, args, fmt: OutputFormatter) -> int:
    """Get player info."""
    uid = args.uid or get_player_uid(args, client)
    if not uid:
        print("Error: Player UID required (--uid, --player, $POLIS_PLAYER_UID, or single online player)", file=sys.stderr)
        return EXIT_USAGE_ERROR

    fmt.debug(f"GET /polis/player?uid={uid}")
    result = client.get("/polis/player", {"uid": uid})
    print(fmt.format(result))
    return EXIT_SUCCESS


def cmd_bots(client: HarnessClient, args, fmt: OutputFormatter) -> int:
    """List all bots."""
    fmt.debug("GET /polis/bots")
    result = client.get("/polis/bots")
    print(fmt.format(result))
    return EXIT_SUCCESS


def cmd_state(client: HarnessClient, args, fmt: OutputFormatter) -> int:
    """Get bot state."""
    bot_id = getattr(args, "id", None) or get_bot_id(args)
    params = {}
    if bot_id:
        params["botId"] = bot_id
    if hasattr(args, "radius") and args.radius:
        params["radius"] = args.radius

    fmt.debug(f"GET /polis/state params={params}")
    result = client.get("/polis/state", params if params else None)
    print(fmt.format(result))

    if result.get("Error"):
        return EXIT_COMMAND_FAILED
    return EXIT_SUCCESS


def cmd_targets(client: HarnessClient, args, fmt: OutputFormatter) -> int:
    """Get nearby interactables."""
    params = {}

    bot_id = get_bot_id(args)
    if bot_id:
        params["botId"] = bot_id
    else:
        player_uid = get_player_uid(args, client)
        if player_uid:
            params["playerUid"] = player_uid

    if hasattr(args, "radius") and args.radius:
        params["radius"] = args.radius
    if hasattr(args, "limit") and args.limit:
        params["limit"] = args.limit
    if hasattr(args, "mode") and args.mode:
        params["mode"] = args.mode
    if hasattr(args, "q") and args.q:
        params["q"] = args.q
    if hasattr(args, "query") and args.query:
        params["codeContains"] = args.query
    if hasattr(args, "include_dead") and args.include_dead:
        params["includeDead"] = "true"

    fmt.debug(f"GET /polis/targets params={params}")
    result = client.get("/polis/targets", params if params else None)

    # Client-side filtering
    filter_pattern = getattr(args, "filter", None)
    exclude_natural = getattr(args, "exclude_natural", False)

    # Natural blocks to exclude (common terrain)
    natural_patterns = ["soil", "stone", "gravel", "sand", "clay", "peat", "dirt", "rock"]

    if filter_pattern or exclude_natural:
        # Handle both lowercase and capitalized keys from harness
        blocks_key = "Blocks" if "Blocks" in result else "blocks"
        entities_key = "Entities" if "Entities" in result else "entities"
        blocks = result.get(blocks_key, []) or []
        entities = result.get(entities_key, []) or []

        if blocks:
            filtered_blocks = []
            for b in blocks:
                # Handle both Code and code keys
                code = (b.get("Code") or b.get("code") or "").lower()
                # Exclude natural blocks if requested
                if exclude_natural and any(p in code for p in natural_patterns):
                    continue
                # Include only if matches filter pattern
                if filter_pattern and filter_pattern.lower() not in code:
                    continue
                filtered_blocks.append(b)
            result[blocks_key] = filtered_blocks

        if entities and filter_pattern:
            filtered_entities = []
            for e in entities:
                code = (e.get("Code") or e.get("code") or "").lower()
                if filter_pattern.lower() in code:
                    filtered_entities.append(e)
            result[entities_key] = filtered_entities

    print(fmt.format(result))
    return EXIT_SUCCESS


def cmd_look(client: HarnessClient, args, fmt: OutputFormatter) -> int:
    """Get player look target."""
    uid = get_player_uid(args, client)
    if not uid:
        print("Error: Player UID required (--player, $POLIS_PLAYER_UID, or single online player)", file=sys.stderr)
        return EXIT_USAGE_ERROR

    params = {"uid": uid}
    if hasattr(args, "range") and args.range:
        params["range"] = args.range

    fmt.debug(f"GET /polis/look params={params}")
    result = client.get("/polis/look", params)
    print(fmt.format(result))
    return EXIT_SUCCESS


# ============================================================================
# Action Commands
# ============================================================================

def send_command(client: HarnessClient, cmd: str, cmd_args: list, context: dict, fmt: OutputFormatter) -> dict:
    """Send a command to the harness."""
    payload = {"cmd": cmd, "args": cmd_args}
    if context:
        payload["context"] = context

    fmt.debug(f"POST /polis/command {payload}")
    return client.post("/polis/command", payload)


PROFESSIONS = ["laborer", "miner", "lumberjack", "builder", "farmer", "hunter", "smith", "knapper"]


def cmd_spawn(client: HarnessClient, args, fmt: OutputFormatter) -> int:
    """Spawn a new bot."""
    cmd_args = []

    # Handle entity code (--entity takes precedence, disables profession)
    profession = getattr(args, "profession", None)
    if hasattr(args, "entity") and args.entity:
        cmd_args.append(args.entity)
        profession = None  # explicit entity code skips profession

    # Handle explicit coordinates (overrides player-relative spawn)
    has_coords = hasattr(args, "coords") and args.coords and len(args.coords) == 3
    if has_coords:
        cmd_args.extend([str(c) for c in args.coords])

    context = build_context(args, client)

    # Pass profession via context
    if profession:
        context["profession"] = profession

    # Add spawn offset for player-relative spawning (default: 2 blocks to the side)
    # Only applies when: no explicit coords AND player UID is set AND not --worldspawn
    worldspawn = getattr(args, "worldspawn", False)
    if not has_coords and not worldspawn and context and context.get("playerUid"):
        offset = getattr(args, "offset", None)
        if offset and len(offset) == 3:
            context["spawnOffset"] = [offset[0], offset[1], offset[2]]
        else:
            # Default offset: 2 blocks in X direction (to the side of player)
            context["spawnOffset"] = [2, 0, 0]

    result = send_command(client, "spawn", cmd_args, context, fmt)
    print(fmt.format(result, "Bot spawned"))

    if result.get("Ok"):
        bot_id = (result.get("Data") or {}).get("id")
        if bot_id and fmt.quiet:
            print(f"BOT_ID={bot_id}")
        return EXIT_SUCCESS
    return EXIT_COMMAND_FAILED


def cmd_professions(client: HarnessClient, args, fmt: OutputFormatter) -> int:
    """List available professions."""
    print("Available professions:")
    for p in PROFESSIONS:
        default = " (default)" if p == "laborer" else ""
        print(f"  {p}{default}")
    return EXIT_SUCCESS


def cmd_select(client: HarnessClient, args, fmt: OutputFormatter) -> int:
    """Select a bot by ID."""
    if not args.id:
        print("Error: Bot ID required", file=sys.stderr)
        return EXIT_USAGE_ERROR

    context = build_context(args, client)
    result = send_command(client, "select", [str(args.id)], context, fmt)
    print(fmt.format(result, f"Selected bot {args.id}"))

    if result.get("Ok"):
        # Print export hint for shell integration (stderr to not pollute scripted output)
        print(f"# To persist: export POLIS_BOT_ID={args.id}", file=sys.stderr)

    return EXIT_SUCCESS if result.get("Ok") else EXIT_COMMAND_FAILED


def cmd_despawn(client: HarnessClient, args, fmt: OutputFormatter) -> int:
    """Despawn the selected bot."""
    context = build_context(args, client)
    result = send_command(client, "despawn", [], context, fmt)
    print(fmt.format(result, "Bot despawned"))
    return EXIT_SUCCESS if result.get("Ok") else EXIT_COMMAND_FAILED


def cmd_goto(client: HarnessClient, args, fmt: OutputFormatter) -> int:
    """Move bot to coordinates."""
    if not args.x:
        print("Error: Coordinates required (x y z)", file=sys.stderr)
        return EXIT_USAGE_ERROR

    cmd_args = [str(args.x), str(args.y), str(args.z)]
    context = build_context(args, client)
    result = send_command(client, "goto", cmd_args, context, fmt)
    print(fmt.format(result, f"Moving to ({args.x}, {args.y}, {args.z})"))

    if not result.get("Ok"):
        return EXIT_COMMAND_FAILED

    if getattr(args, "wait", False):
        return wait_for_arrival(client, args, fmt, [args.x, args.y, args.z])

    return EXIT_SUCCESS


def wait_for_arrival(client: HarnessClient, args, fmt: OutputFormatter, target: list) -> int:
    """Wait for bot to arrive at target."""
    import math
    timeout = getattr(args, "timeout", 30)
    threshold = 1.5
    deadline = time.time() + timeout

    fmt.debug(f"Waiting for arrival at {target} (timeout={timeout}s)")

    bot_id = get_bot_id(args)
    params = {"botId": bot_id} if bot_id else {}

    while time.time() < deadline:
        result = client.get("/polis/state", params if params else None)
        bot = result.get("Bot", {})
        pos = bot.get("Pos", [0, 0, 0])

        dist = math.sqrt(sum((a - b) ** 2 for a, b in zip(pos, target)))
        fmt.debug(f"Position: {pos}, distance: {dist:.2f}")

        if dist <= threshold:
            if not fmt.quiet:
                print(fmt.format({"arrived": True, "position": pos}))
            return EXIT_SUCCESS

        time.sleep(0.5)

    print("Timeout waiting for arrival", file=sys.stderr)
    return EXIT_COMMAND_FAILED


def cmd_stop(client: HarnessClient, args, fmt: OutputFormatter) -> int:
    """Stop current bot activity."""
    context = build_context(args, client)
    result = send_command(client, "stop", [], context, fmt)
    print(fmt.format(result, "Stopped"))
    return EXIT_SUCCESS if result.get("Ok") else EXIT_COMMAND_FAILED


def cmd_give(client: HarnessClient, args, fmt: OutputFormatter) -> int:
    """Give item to bot."""
    if not args.item:
        print("Error: Item code required", file=sys.stderr)
        return EXIT_USAGE_ERROR

    cmd_args = [args.item]
    if args.qty:
        cmd_args.append(str(args.qty))

    context = build_context(args, client)
    result = send_command(client, "give", cmd_args, context, fmt)
    print(fmt.format(result, f"Gave {args.qty or 1}x {args.item}"))
    return EXIT_SUCCESS if result.get("Ok") else EXIT_COMMAND_FAILED


def cmd_equip(client: HarnessClient, args, fmt: OutputFormatter) -> int:
    """Equip item to bot slot."""
    if not args.slot:
        print("Error: Slot required (lefthand, righthand, backpack0, backpack1)", file=sys.stderr)
        return EXIT_USAGE_ERROR
    if not args.item:
        print("Error: Item code required", file=sys.stderr)
        return EXIT_USAGE_ERROR

    cmd_args = [args.slot, args.item]
    if args.qty:
        cmd_args.append(str(args.qty))

    context = build_context(args, client)
    result = send_command(client, "equip", cmd_args, context, fmt)
    print(fmt.format(result, f"Equipped {args.qty or 1}x {args.item} on {args.slot}"))
    return EXIT_SUCCESS if result.get("Ok") else EXIT_COMMAND_FAILED


def cmd_drop(client: HarnessClient, args, fmt: OutputFormatter) -> int:
    """Drop items from bot hand."""
    cmd_args = []
    slot = getattr(args, "slot", -1)
    qty = getattr(args, "qty", 0)
    cmd_args = [str(slot), str(qty)]

    context = build_context(args, client)
    result = send_command(client, "drop", cmd_args, context, fmt)
    print(fmt.format(result, "Dropped"))
    return EXIT_SUCCESS if result.get("Ok") else EXIT_COMMAND_FAILED


def cmd_pickup(client: HarnessClient, args, fmt: OutputFormatter) -> int:
    """Pick up nearby item."""
    cmd_args = []
    entity_id = getattr(args, "id", "")
    range_val = getattr(args, "range", 3.0)
    cmd_args = [str(entity_id) if entity_id else "", str(range_val)]

    context = build_context(args, client)
    result = send_command(client, "pickup", cmd_args, context, fmt)
    print(fmt.format(result, "Picked up"))
    return EXIT_SUCCESS if result.get("Ok") else EXIT_COMMAND_FAILED


def cmd_activate(client: HarnessClient, args, fmt: OutputFormatter) -> int:
    """Activate a block."""
    if not hasattr(args, "x") or args.x is None:
        print("Error: Coordinates required (x y z)", file=sys.stderr)
        return EXIT_USAGE_ERROR

    cmd_args = [str(args.x), str(args.y), str(args.z)]
    if getattr(args, "shift", False):
        cmd_args.append("--shift")
    context = build_context(args, client)
    if not context or "playerUid" not in context:
        print("Error: Player UID required for activate (--player, $POLIS_PLAYER_UID, or single online player)", file=sys.stderr)
        return EXIT_USAGE_ERROR

    result = send_command(client, "activate", cmd_args, context, fmt)
    print(fmt.format(result, f"Activated ({args.x}, {args.y}, {args.z})"))
    return EXIT_SUCCESS if result.get("Ok") else EXIT_COMMAND_FAILED


def cmd_ignite(client: HarnessClient, args, fmt: OutputFormatter) -> int:
    """Ignite an IIgnitable block (firepit, torch, etc.)."""
    if not hasattr(args, "x") or args.x is None:
        print("Error: Coordinates required (x y z)", file=sys.stderr)
        return EXIT_USAGE_ERROR

    cmd_args = [str(args.x), str(args.y), str(args.z)]
    context = build_context(args, client)
    if not context or "playerUid" not in context:
        print("Error: Player UID required for ignite (--player, $POLIS_PLAYER_UID, or single online player)", file=sys.stderr)
        return EXIT_USAGE_ERROR

    result = send_command(client, "ignite", cmd_args, context, fmt)
    print(fmt.format(result, f"Igniting ({args.x}, {args.y}, {args.z})"))
    return EXIT_SUCCESS if result.get("Ok") else EXIT_COMMAND_FAILED


def cmd_mine(client: HarnessClient, args, fmt: OutputFormatter) -> int:
    """Mine a block."""
    if not hasattr(args, "x") or args.x is None:
        print("Error: Coordinates required (x y z)", file=sys.stderr)
        return EXIT_USAGE_ERROR

    autocollect = "true" if getattr(args, "autocollect", False) else "false"
    cmd_args = [str(args.x), str(args.y), str(args.z), autocollect]

    context = build_context(args, client)
    if not context or "playerUid" not in context:
        print("Error: Player UID required for mine (--player, $POLIS_PLAYER_UID, or single online player)", file=sys.stderr)
        return EXIT_USAGE_ERROR

    result = send_command(client, "mine", cmd_args, context, fmt)
    print(fmt.format(result, f"Mining ({args.x}, {args.y}, {args.z})"))

    if not result.get("Ok"):
        return EXIT_COMMAND_FAILED

    if getattr(args, "wait", True):  # Default to waiting for mine
        return wait_for_action(client, args, fmt, "mine", "mined")

    return EXIT_SUCCESS


def cmd_place(client: HarnessClient, args, fmt: OutputFormatter) -> int:
    """Place a block at coordinates (survival-like, requires block in inventory)."""
    if not hasattr(args, "blockcode") or not args.blockcode:
        print("Error: Block code required", file=sys.stderr)
        return EXIT_USAGE_ERROR

    if not hasattr(args, "x") or args.x is None:
        print("Error: Coordinates required (x y z)", file=sys.stderr)
        return EXIT_USAGE_ERROR

    cmd_args = [args.blockcode, str(args.x), str(args.y), str(args.z)]
    if getattr(args, "face", None):
        cmd_args.append(args.face)

    context = build_context(args, client)
    if not context or "playerUid" not in context:
        print("Error: Player UID required for place (--player, $POLIS_PLAYER_UID, or single online player)", file=sys.stderr)
        return EXIT_USAGE_ERROR

    result = send_command(client, "place", cmd_args, context, fmt)
    print(fmt.format(result, f"Placing {args.blockcode} at ({args.x}, {args.y}, {args.z})"))

    if not result.get("Ok"):
        return EXIT_COMMAND_FAILED

    if getattr(args, "wait", True):  # Default to waiting for place
        return wait_for_action(client, args, fmt, "place", "placed")

    return EXIT_SUCCESS


def cmd_setblock(client: HarnessClient, args, fmt: OutputFormatter) -> int:
    """Directly set a block in the world (creative/admin, no bot needed)."""
    if not hasattr(args, "blockcode") or not args.blockcode:
        print("Error: Block code required", file=sys.stderr)
        return EXIT_USAGE_ERROR

    if not hasattr(args, "x") or args.x is None:
        print("Error: Coordinates required (x y z)", file=sys.stderr)
        return EXIT_USAGE_ERROR

    cmd_args = [args.blockcode, str(args.x), str(args.y), str(args.z)]

    # setblock doesn't need player context - it's admin-level
    result = send_command(client, "setblock", cmd_args, {}, fmt)
    print(fmt.format(result, f"Set {args.blockcode} at ({args.x}, {args.y}, {args.z})"))
    return EXIT_SUCCESS if result.get("Ok") else EXIT_COMMAND_FAILED


def cmd_harvest(client: HarnessClient, args, fmt: OutputFormatter) -> int:
    """Harvest a block (berries, resin)."""
    if not hasattr(args, "x") or args.x is None:
        print("Error: Coordinates required (x y z)", file=sys.stderr)
        return EXIT_USAGE_ERROR

    autocollect = "true" if getattr(args, "autocollect", False) else "false"
    validate = "true" if getattr(args, "validate", True) else "false"
    cmd_args = [str(args.x), str(args.y), str(args.z), autocollect, validate]

    context = build_context(args, client)
    if not context or "playerUid" not in context:
        print("Error: Player UID required for harvest (--player, $POLIS_PLAYER_UID, or single online player)", file=sys.stderr)
        return EXIT_USAGE_ERROR

    result = send_command(client, "harvest", cmd_args, context, fmt)
    print(fmt.format(result, f"Harvesting ({args.x}, {args.y}, {args.z})"))

    if not result.get("Ok"):
        return EXIT_COMMAND_FAILED

    if getattr(args, "wait", True):  # Default to waiting
        return wait_for_action(client, args, fmt, "harvest", "harvested")

    return EXIT_SUCCESS


def cmd_harvestcrop(client: HarnessClient, args, fmt: OutputFormatter) -> int:
    """Harvest a farmland crop."""
    if not hasattr(args, "x") or args.x is None:
        print("Error: Coordinates required (x y z)", file=sys.stderr)
        return EXIT_USAGE_ERROR

    autocollect = "true" if getattr(args, "autocollect", False) else "false"
    cmd_args = [str(args.x), str(args.y), str(args.z), autocollect]

    context = build_context(args, client)
    if not context or "playerUid" not in context:
        print("Error: Player UID required for harvestcrop (--player, $POLIS_PLAYER_UID, or single online player)", file=sys.stderr)
        return EXIT_USAGE_ERROR

    result = send_command(client, "harvestcrop", cmd_args, context, fmt)
    print(fmt.format(result, f"Harvesting crop ({args.x}, {args.y}, {args.z})"))

    if not result.get("Ok"):
        return EXIT_COMMAND_FAILED

    if getattr(args, "wait", True):  # Default to waiting
        return wait_for_action(client, args, fmt, "harvestcrop", "harvested")

    return EXIT_SUCCESS


def cmd_forge_heat(client: HarnessClient, args, fmt: OutputFormatter) -> int:
    """Wait for firepit input to reach working temperature."""
    if not hasattr(args, "x") or args.x is None:
        print("Error: Coordinates required (x y z)", file=sys.stderr)
        return EXIT_USAGE_ERROR

    duration = getattr(args, "duration", 120) or 120
    cmd_args = [str(args.x), str(args.y), str(args.z), str(duration)]

    context = build_context(args, client)
    if not context or "playerUid" not in context:
        print("Error: Player UID required for forge-heat (--player, $POLIS_PLAYER_UID, or single online player)", file=sys.stderr)
        return EXIT_USAGE_ERROR

    result = send_command(client, "forge-heat", cmd_args, context, fmt)
    print(fmt.format(result, f"Waiting for heat at ({args.x}, {args.y}, {args.z}), timeout={duration}s"))

    if not result.get("Ok"):
        return EXIT_COMMAND_FAILED

    if getattr(args, "wait", True):
        return wait_for_action(client, args, fmt, "forge-heat", "heated")

    return EXIT_SUCCESS


def cmd_grind(client: HarnessClient, args, fmt: OutputFormatter) -> int:
    """Grind items in a quern."""
    if not hasattr(args, "x") or args.x is None:
        print("Error: Coordinates required (x y z)", file=sys.stderr)
        return EXIT_USAGE_ERROR

    count = getattr(args, "count", 0) or 0
    duration = getattr(args, "duration", 0) or 0
    cmd_args = [str(args.x), str(args.y), str(args.z), str(count), str(duration)]

    context = build_context(args, client)
    if not context or "playerUid" not in context:
        print("Error: Player UID required for grind (--player, $POLIS_PLAYER_UID, or single online player)", file=sys.stderr)
        return EXIT_USAGE_ERROR

    result = send_command(client, "grind", cmd_args, context, fmt)
    limits = []
    if count > 0:
        limits.append(f"count={count}")
    if duration > 0:
        limits.append(f"duration={duration}s")
    limit_str = f" ({', '.join(limits)})" if limits else ""
    print(fmt.format(result, f"Grinding at ({args.x}, {args.y}, {args.z}){limit_str}"))

    if not result.get("Ok"):
        return EXIT_COMMAND_FAILED

    if getattr(args, "wait", True):  # Default to waiting
        return wait_for_action(client, args, fmt, "grind", "ground")

    return EXIT_SUCCESS


def cmd_press(client: HarnessClient, args, fmt: OutputFormatter) -> int:
    """Press fruit in a fruit press."""
    if not hasattr(args, "x") or args.x is None:
        print("Error: Coordinates required (x y z)", file=sys.stderr)
        return EXIT_USAGE_ERROR

    duration = getattr(args, "duration", 0) or 0
    autounscrew = getattr(args, "autounscrew", True)
    cmd_args = [str(args.x), str(args.y), str(args.z), str(duration), str(autounscrew).lower()]

    context = build_context(args, client)
    if not context or "playerUid" not in context:
        print("Error: Player UID required for press (--player, $POLIS_PLAYER_UID, or single online player)", file=sys.stderr)
        return EXIT_USAGE_ERROR

    result = send_command(client, "press", cmd_args, context, fmt)
    options = []
    if duration > 0:
        options.append(f"duration={duration}s")
    if not autounscrew:
        options.append("autounscrew=false")
    option_str = f" ({', '.join(options)})" if options else ""
    print(fmt.format(result, f"Pressing at ({args.x}, {args.y}, {args.z}){option_str}"))

    if not result.get("Ok"):
        return EXIT_COMMAND_FAILED

    if getattr(args, "wait", True):  # Default to waiting
        return wait_for_action(client, args, fmt, "press", "pressed")

    return EXIT_SUCCESS


def cmd_clayform(client: HarnessClient, args, fmt: OutputFormatter) -> int:
    """Form clay into a recipe shape.

    The bot will progressively place voxels according to the recipe pattern.
    Requires clay in bot inventory.

    Examples:
        clayform 233 3 257 bowl-raw                 # Form a bowl
        clayform 233 3 257 toolmold-fire-raw-anvil  # Form an anvil mold
        clayform 233 3 257 bowl-raw --speed 8       # Faster forming (8 voxels/tick)
    """
    if not hasattr(args, "x") or args.x is None:
        print("Error: Coordinates required (x y z recipe)", file=sys.stderr)
        return EXIT_USAGE_ERROR

    recipe = getattr(args, "recipe", None)
    if not recipe:
        print("Error: Recipe name required", file=sys.stderr)
        return EXIT_USAGE_ERROR

    speed = getattr(args, "speed", 4) or 4
    cmd_args = [str(args.x), str(args.y), str(args.z), recipe, str(speed)]

    context = build_context(args, client)
    if not context or "playerUid" not in context:
        print("Error: Player UID required for clayform (--player, $POLIS_PLAYER_UID, or single online player)", file=sys.stderr)
        return EXIT_USAGE_ERROR

    result = send_command(client, "clayform", cmd_args, context, fmt)
    print(fmt.format(result, f"Forming clay at ({args.x}, {args.y}, {args.z}): {recipe}"))

    if not result.get("Ok"):
        return EXIT_COMMAND_FAILED

    if getattr(args, "wait", True):  # Default to waiting
        return wait_for_action(client, args, fmt, "clayform", "formed")

    return EXIT_SUCCESS


def cmd_knap(client: HarnessClient, args, fmt: OutputFormatter) -> int:
    """Knap flint/stone into tools.

    The bot will progressively remove voxels according to the recipe pattern.
    Requires a knapping surface with material already placed.

    Examples:
        knap 233 3 257 arrowhead-flint              # Knap an arrowhead
        knap 233 3 257 knife-blade-flint            # Knap a knife blade
        knap 233 3 257 axehead-flint --speed 8      # Faster knapping (8 voxels/tick)
    """
    if not hasattr(args, "x") or args.x is None:
        print("Error: Coordinates required (x y z recipe)", file=sys.stderr)
        return EXIT_USAGE_ERROR

    recipe = getattr(args, "recipe", None)
    if not recipe:
        print("Error: Recipe name required", file=sys.stderr)
        return EXIT_USAGE_ERROR

    speed = getattr(args, "speed", 4) or 4
    cmd_args = [str(args.x), str(args.y), str(args.z), recipe, str(speed)]

    context = build_context(args, client)
    # Note: knap command no longer requires player UID since output goes to bot inventory

    result = send_command(client, "knap", cmd_args, context, fmt)
    print(fmt.format(result, f"Knapping at ({args.x}, {args.y}, {args.z}): {recipe}"))

    if not result.get("Ok"):
        return EXIT_COMMAND_FAILED

    if getattr(args, "wait", True):  # Default to waiting
        return wait_for_action(client, args, fmt, "knap", "knapped")

    return EXIT_SUCCESS


def cmd_seal(client: HarnessClient, args, fmt: OutputFormatter) -> int:
    """Seal a barrel for fermentation/pickling.

    The barrel must contain items and liquid matching a valid sealing recipe.
    Once sealed, the barrel will ferment over time (e.g., pickling vegetables,
    fermenting alcohol).

    Examples:
        seal 233 3 257              # Seal barrel at coordinates
    """
    if not hasattr(args, "x") or args.x is None:
        print("Error: Coordinates required (x y z)", file=sys.stderr)
        return EXIT_USAGE_ERROR

    cmd_args = [str(args.x), str(args.y), str(args.z)]

    context = build_context(args, client)
    if not context or "playerUid" not in context:
        print("Error: Player UID required for seal (--player, $POLIS_PLAYER_UID, or single online player)", file=sys.stderr)
        return EXIT_USAGE_ERROR

    result = send_command(client, "seal", cmd_args, context, fmt)
    print(fmt.format(result, f"Sealing barrel at ({args.x}, {args.y}, {args.z})"))

    if not result.get("Ok"):
        return EXIT_COMMAND_FAILED

    # Seal is instant, no need to wait
    return EXIT_SUCCESS


def cmd_anvil_smith(client: HarnessClient, args, fmt: OutputFormatter) -> int:
    """Smith a work item on an anvil.

    Uses direct voxel manipulation to shape the work item according to the
    recipe pattern. This works for all recipes including tools, weapons, etc.
    (unlike helve hammer which only works for iron bloom and plate recipes).

    The anvil must have a hot work item placed on it. The bot will automatically
    select the recipe and shape the metal.

    Examples:
        anvil-smith 100 65 200 pickaxehead-copper     # Smith a copper pickaxe head
        anvil-smith 100 65 200 metalplate-iron        # Smith an iron plate
        anvil-smith 100 65 200 knifeblade-copper 8    # Smith faster (8 voxels/tick)
    """
    if not hasattr(args, "x") or args.x is None:
        print("Error: Coordinates required (x y z recipe)", file=sys.stderr)
        return EXIT_USAGE_ERROR

    if not hasattr(args, "recipe") or not args.recipe:
        print("Error: Recipe code required", file=sys.stderr)
        return EXIT_USAGE_ERROR

    cmd_args = [str(args.x), str(args.y), str(args.z), args.recipe]

    if hasattr(args, "speed") and args.speed:
        cmd_args.append(str(args.speed))

    context = build_context(args, client)
    if not context or "playerUid" not in context:
        print("Error: Player UID required for anvil-smith (--player, $POLIS_PLAYER_UID, or single online player)", file=sys.stderr)
        return EXIT_USAGE_ERROR

    result = send_command(client, "anvil-smith", cmd_args, context, fmt)
    print(fmt.format(result, f"Smithing {args.recipe} at ({args.x}, {args.y}, {args.z})"))

    if not result.get("Ok"):
        return EXIT_COMMAND_FAILED

    # Smithing is a timed action, use wait if specified
    if getattr(args, "wait", False):
        return wait_for_action(client, args, fmt, "anvil-smith", "smithed")

    return EXIT_SUCCESS


def wait_for_action_result(client, args, fmt, action_name, timeout=60):
    """Wait for an action and return (ok, msg) instead of an exit code."""
    deadline = time.time() + timeout
    bot_id = get_bot_id(args)
    params = {"botId": bot_id} if bot_id else {}

    while time.time() < deadline:
        result = client.get("/polis/state", params if params else None)
        last_action = result.get("LastAction") or {}
        if last_action.get("Name") == action_name:
            msg = last_action.get("Msg", "")
            ok = last_action.get("Ok", False)
            return ok, msg
        time.sleep(0.5)

    return False, "timeout"


def cmd_smith_loop(client: HarnessClient, args, fmt: OutputFormatter) -> int:
    """Complete smithing loop: fuel forge, heat ingot, smith on anvil with reheat support.

    Uses a forge (not firepit) for heating ingots. The forge interaction model:
    - shift+activate with coal in hand → adds fuel (each piece adds 1/16 fuel level)
    - shift+activate with ingot in hand → places ingot on forge
    - activate (no shift) → takes contents out
    - ignite → lights the forge
    """
    fg = [str(c) for c in args.forge_coords]
    av = [str(c) for c in args.anvil_coords]
    max_reheats = getattr(args, "max_reheats", 3) or 3
    fuel_qty = getattr(args, "fuel_qty", 4) or 4
    context = build_context(args, client)

    if not context or "playerUid" not in context:
        print("Error: Player UID required", file=sys.stderr)
        return EXIT_USAGE_ERROR

    def step(label, cmd, cmd_args, wait_action=None, wait_msg=None, wait_timeout=120):
        """Run a step; returns (ok, msg)."""
        print(f"[smith-loop] {label}", file=sys.stderr)
        r = send_command(client, cmd, cmd_args, context, fmt)
        if not r.get("Ok"):
            return False, r.get("Msg", "command rejected")
        if wait_action:
            return wait_for_action_result(client, args, fmt, wait_action, wait_timeout)
        return True, ""

    def load_fuel():
        """Load fuel into forge one piece at a time via shift+activate."""
        for i in range(fuel_qty):
            ok, msg = step(f"equip fuel ({i+1}/{fuel_qty})", "equip", ["righthand", args.fuel])
            if not ok: return False, f"equip fuel: {msg}"
            ok, msg = step(f"add fuel to forge ({i+1}/{fuel_qty})", "activate", fg + ["--shift"])
            if not ok: return False, f"add fuel: {msg}"
        return True, ""

    def heat_on_forge(item_label="ingot"):
        """Place item on forge (must be in right hand), ignite, wait for heat."""
        ok, msg = step(f"place {item_label} on forge", "activate", fg + ["--shift"])
        if not ok: return False, f"place on forge: {msg}"
        ok, msg = step("ignite forge", "ignite", fg)
        if not ok: return False, f"ignite: {msg}"
        ok, msg = step("waiting for heat", "forge-heat", fg + ["120"], "forge-heat", "heated", 180)
        if not ok: return False, f"forge-heat: {msg}"
        return True, ""

    def take_from_forge():
        """Take contents from forge (activate without shift)."""
        return step("take from forge", "activate", fg)

    # 1. Load fuel into forge
    ok, msg = load_fuel()
    if not ok: print(f"[smith-loop] FAILED {msg}", file=sys.stderr); return EXIT_COMMAND_FAILED

    # 2. Equip ingot and heat on forge
    ok, msg = step("equip ingot", "equip", ["righthand", args.ingot])
    if not ok: print(f"[smith-loop] FAILED equip ingot: {msg}", file=sys.stderr); return EXIT_COMMAND_FAILED
    ok, msg = heat_on_forge()
    if not ok: print(f"[smith-loop] FAILED {msg}", file=sys.stderr); return EXIT_COMMAND_FAILED

    # 3. Take hot ingot from forge
    ok, msg = take_from_forge()
    if not ok: print(f"[smith-loop] FAILED take from forge: {msg}", file=sys.stderr); return EXIT_COMMAND_FAILED

    # 4. Place on anvil (shift-activate)
    ok, msg = step("place on anvil", "activate", av + ["--shift"])
    if not ok: print(f"[smith-loop] FAILED place on anvil: {msg}", file=sys.stderr); return EXIT_COMMAND_FAILED

    # 5. Smith with reheat loop
    for attempt in range(max_reheats + 1):
        ok, msg = step(f"smithing (attempt {attempt+1})", "anvil-smith",
                       av + [args.recipe], "anvil-smith", "smithed", 60)
        if ok:
            break

        if "cooled" not in msg.lower():
            print(f"[smith-loop] FAILED anvil-smith: {msg}", file=sys.stderr)
            return EXIT_COMMAND_FAILED

        if attempt >= max_reheats:
            print(f"[smith-loop] FAILED: max reheats ({max_reheats}) exceeded", file=sys.stderr)
            return EXIT_COMMAND_FAILED

        # Reheat cycle: take work item from anvil, reheat on forge, put back
        print(f"[smith-loop] work item cooled, reheating (reheat {attempt+1}/{max_reheats})", file=sys.stderr)
        ok, msg = step("take cooled item from anvil", "takefrom", av + ["0"])
        if not ok: print(f"[smith-loop] FAILED take from anvil: {msg}", file=sys.stderr); return EXIT_COMMAND_FAILED
        ok, msg = heat_on_forge("work item")
        if not ok: print(f"[smith-loop] FAILED reheat: {msg}", file=sys.stderr); return EXIT_COMMAND_FAILED
        ok, msg = take_from_forge()
        if not ok: print(f"[smith-loop] FAILED take reheated: {msg}", file=sys.stderr); return EXIT_COMMAND_FAILED
        ok, msg = step("place reheated item on anvil", "activate", av + ["--shift"])
        if not ok: print(f"[smith-loop] FAILED re-place on anvil: {msg}", file=sys.stderr); return EXIT_COMMAND_FAILED

    # 6. Pick up finished item
    ok, msg = step("pickup finished item", "pickup", [])
    if not ok:
        print(f"[smith-loop] warning: pickup failed ({msg}), item may be on ground", file=sys.stderr)

    print("[smith-loop] SUCCESS: smithing complete", file=sys.stderr)
    return EXIT_SUCCESS


def cmd_anvil_state(client: HarnessClient, args, fmt: OutputFormatter) -> int:
    """Get the current state of an anvil.

    Returns information about the anvil including:
    - Whether it has a work item
    - Work item code and temperature
    - Selected recipe
    - Voxel counts (metal, slag, empty)

    Examples:
        anvil-state 100 65 200    # Check anvil state at coordinates
    """
    if not hasattr(args, "x") or args.x is None:
        print("Error: Coordinates required (x y z)", file=sys.stderr)
        return EXIT_USAGE_ERROR

    cmd_args = [str(args.x), str(args.y), str(args.z)]

    context = build_context(args, client)
    result = send_command(client, "anvil-state", cmd_args, context, fmt)
    print(fmt.format(result))

    return EXIT_SUCCESS if result.get("Ok") else EXIT_COMMAND_FAILED


def cmd_takefrom(client: HarnessClient, args, fmt: OutputFormatter) -> int:
    """Take items from container.
    Usage: takefrom x y z slot [qty]        - using coordinates
           takefrom -c name slot [qty]      - using registered name
    """
    container_name = getattr(args, "container", None)
    positional = getattr(args, "args", [])

    if container_name:
        # Using container name: args = [slot, qty?]
        if len(positional) < 1:
            print("Error: slot required. Usage: takefrom -c <name> <slot> [qty]", file=sys.stderr)
            return EXIT_USAGE_ERROR
        cmd_args = [container_name, positional[0]]
        if len(positional) > 1:
            cmd_args.append(positional[1])
    else:
        # Using coordinates: args = [x, y, z, slot, qty?]
        if len(positional) < 4:
            print("Error: x y z slot required. Usage: takefrom <x> <y> <z> <slot> [qty]", file=sys.stderr)
            return EXIT_USAGE_ERROR
        cmd_args = positional[:4]
        if len(positional) > 4:
            cmd_args.append(positional[4])

    context = build_context(args, client)
    if not context or "playerUid" not in context:
        print("Error: Player UID required for takefrom (--player, $POLIS_PLAYER_UID, or single online player)", file=sys.stderr)
        return EXIT_USAGE_ERROR

    result = send_command(client, "takefrom", cmd_args, context, fmt)
    print(fmt.format(result, "Took from container"))
    return EXIT_SUCCESS if result.get("Ok") else EXIT_COMMAND_FAILED


def cmd_putinto(client: HarnessClient, args, fmt: OutputFormatter) -> int:
    """Put items from bot's right hand into a specific container slot.
    Usage: putinto x y z <container-slot> [qty]    - using coordinates
           putinto -c name <container-slot> [qty]  - using registered name
    The container-slot is the target slot index (e.g. firepit: 0=fuel, 1=input, 2=output).
    Bot always puts from right hand (use 'equip righthand' first).
    """
    container_name = getattr(args, "container", None)
    positional = getattr(args, "args", [])

    if container_name:
        # Using container name: args = [slot, qty?]
        if len(positional) < 1:
            print("Error: slot required. Usage: putinto -c <name> <slot> [qty]", file=sys.stderr)
            return EXIT_USAGE_ERROR
        cmd_args = [container_name, positional[0]]
        if len(positional) > 1:
            cmd_args.append(positional[1])
    else:
        # Using coordinates: args = [x, y, z, slot, qty?]
        if len(positional) < 4:
            print("Error: x y z slot required. Usage: putinto <x> <y> <z> <slot> [qty]", file=sys.stderr)
            return EXIT_USAGE_ERROR
        cmd_args = positional[:4]
        if len(positional) > 4:
            cmd_args.append(positional[4])

    context = build_context(args, client)
    if not context or "playerUid" not in context:
        print("Error: Player UID required for putinto (--player, $POLIS_PLAYER_UID, or single online player)", file=sys.stderr)
        return EXIT_USAGE_ERROR

    result = send_command(client, "putinto", cmd_args, context, fmt)
    print(fmt.format(result, "Put into container"))
    return EXIT_SUCCESS if result.get("Ok") else EXIT_COMMAND_FAILED


def cmd_butcher(client: HarnessClient, args, fmt: OutputFormatter) -> int:
    """Butcher a dead entity."""
    if not args.id:
        print("Error: Entity ID required", file=sys.stderr)
        return EXIT_USAGE_ERROR

    autocollect = "true" if getattr(args, "autocollect", True) else "false"
    cmd_args = [str(args.id), autocollect]

    context = build_context(args, client)
    if not context or "playerUid" not in context:
        print("Error: Player UID required for butcher (--player, $POLIS_PLAYER_UID, or single online player)", file=sys.stderr)
        return EXIT_USAGE_ERROR

    result = send_command(client, "butcher", cmd_args, context, fmt)
    print(fmt.format(result, "Butchered"))
    return EXIT_SUCCESS if result.get("Ok") else EXIT_COMMAND_FAILED


def cmd_loot(client: HarnessClient, args, fmt: OutputFormatter) -> int:
    """Loot items from a dead entity's inventory."""
    if not args.id:
        print("Error: Entity ID required", file=sys.stderr)
        return EXIT_USAGE_ERROR

    cmd_args = [str(args.id)]

    context = build_context(args, client)
    if not context or "playerUid" not in context:
        print("Error: Player UID required for loot (--player, $POLIS_PLAYER_UID, or single online player)", file=sys.stderr)
        return EXIT_USAGE_ERROR

    result = send_command(client, "loot", cmd_args, context, fmt)
    print(fmt.format(result, "Looted"))
    return EXIT_SUCCESS if result.get("Ok") else EXIT_COMMAND_FAILED


def cmd_interact(client: HarnessClient, args, fmt: OutputFormatter) -> int:
    """Interact with an entity (feed, shear, etc.)."""
    if not args.id:
        print("Error: Entity ID required", file=sys.stderr)
        return EXIT_USAGE_ERROR

    cmd_args = [str(args.id)]
    if getattr(args, "mode", None):
        cmd_args.append(args.mode)

    context = build_context(args, client)
    if not context or "playerUid" not in context:
        print("Error: Player UID required for interact (--player, $POLIS_PLAYER_UID, or single online player)", file=sys.stderr)
        return EXIT_USAGE_ERROR

    result = send_command(client, "interact", cmd_args, context, fmt)
    print(fmt.format(result, f"Interacting with entity {args.id}"))

    if not result.get("Ok"):
        return EXIT_COMMAND_FAILED

    if getattr(args, "wait", True):
        return wait_for_action(client, args, fmt, "interact", "interacted")

    return EXIT_SUCCESS


def cmd_break(client: HarnessClient, args, fmt: OutputFormatter) -> int:
    """[DEBUG] Instantly break a block (no mining time)."""
    if not hasattr(args, "x") or args.x is None:
        print("Error: Coordinates required (x y z)", file=sys.stderr)
        return EXIT_USAGE_ERROR

    dropmult = str(getattr(args, "dropmult", 1.0))
    cmd_args = [str(args.x), str(args.y), str(args.z), dropmult]

    context = build_context(args, client)
    if not context or "playerUid" not in context:
        print("Error: Player UID required for break (--player, $POLIS_PLAYER_UID, or single online player)", file=sys.stderr)
        return EXIT_USAGE_ERROR

    result = send_command(client, "break", cmd_args, context, fmt)
    print(fmt.format(result, f"Breaking block at ({args.x}, {args.y}, {args.z})"))
    return EXIT_SUCCESS if result.get("Ok") else EXIT_COMMAND_FAILED


def cmd_possess(client: HarnessClient, args, fmt: OutputFormatter) -> int:
    """Mount player onto bot."""
    context = build_context(args, client)
    if not context or "playerUid" not in context:
        print("Error: Player UID required for possess (--player, $POLIS_PLAYER_UID, or single online player)", file=sys.stderr)
        return EXIT_USAGE_ERROR

    result = send_command(client, "possess", [], context, fmt)
    print(fmt.format(result, "Possessing bot"))
    return EXIT_SUCCESS if result.get("Ok") else EXIT_COMMAND_FAILED


def cmd_unpossess(client: HarnessClient, args, fmt: OutputFormatter) -> int:
    """Unmount player from bot."""
    context = build_context(args, client)
    if not context or "playerUid" not in context:
        print("Error: Player UID required for unpossess (--player, $POLIS_PLAYER_UID, or single online player)", file=sys.stderr)
        return EXIT_USAGE_ERROR

    result = send_command(client, "unpossess", [], context, fmt)
    print(fmt.format(result, "Unpossessed"))
    return EXIT_SUCCESS if result.get("Ok") else EXIT_COMMAND_FAILED


def cmd_controls(client: HarnessClient, args, fmt: OutputFormatter) -> int:
    """Set movement controls while possessing."""
    # Parse control flags
    fwd = "true" if getattr(args, "fwd", False) else "false"
    back = "true" if getattr(args, "back", False) else "false"
    left = "true" if getattr(args, "left", False) else "false"
    right = "true" if getattr(args, "right", False) else "false"
    sprint = "true" if getattr(args, "sprint", False) else "false"
    jump = "true" if getattr(args, "jump", False) else "false"

    cmd_args = [fwd, back, left, right, sprint, jump]

    context = build_context(args, client)
    if not context or "playerUid" not in context:
        print("Error: Player UID required for controls (--player, $POLIS_PLAYER_UID, or single online player)", file=sys.stderr)
        return EXIT_USAGE_ERROR

    result = send_command(client, "setcontrols", cmd_args, context, fmt)
    print(fmt.format(result, "Controls set"))
    return EXIT_SUCCESS if result.get("Ok") else EXIT_COMMAND_FAILED


def cmd_exec(client: HarnessClient, args, fmt: OutputFormatter) -> int:
    """Execute raw server command."""
    if not args.cmd:
        print("Error: Command required", file=sys.stderr)
        return EXIT_USAGE_ERROR

    payload = {"cmd": args.cmd}
    player_uid = getattr(args, "player", None) or os.environ.get("POLIS_PLAYER_UID")
    if player_uid:
        payload["playerUid"] = player_uid

    fmt.debug(f"POST /polis/servercmd {payload}")
    result = client.post("/polis/servercmd", payload)
    print(fmt.format(result))
    return EXIT_SUCCESS if result.get("ok") else EXIT_COMMAND_FAILED


def cmd_spawnkill(client: HarnessClient, args, fmt: OutputFormatter) -> int:
    """Spawn an entity and immediately kill it (for butcher testing)."""
    entity_code = args.entity

    # Get spawn position - use bot position + offset, or explicit coords
    bot_id = get_bot_id(args)
    if args.coords and len(args.coords) == 3:
        x, y, z = args.coords
    elif bot_id:
        # Get bot position and spawn 1 block away
        params = {"botId": bot_id}
        state = client.get("/polis/state", params)
        if not state.get("Bot"):
            print("Error: Could not get bot position", file=sys.stderr)
            return EXIT_COMMAND_FAILED
        pos = state["Bot"]["Pos"]
        x, y, z = pos[0] + 1, pos[1], pos[2]
    else:
        print("Error: Need --bot or coordinates to determine spawn location", file=sys.stderr)
        return EXIT_USAGE_ERROR

    # Spawn entity
    spawn_args = [entity_code, str(x), str(y), str(z)]
    context = build_context(args, client)
    spawn_result = send_command(client, "spawnentity", spawn_args, context, fmt)

    if not spawn_result.get("Ok"):
        print(fmt.format(spawn_result, "Spawn failed"))
        return EXIT_COMMAND_FAILED

    entity_id = spawn_result.get("Data", {}).get("id")
    if not entity_id:
        print("Error: No entity ID returned from spawn", file=sys.stderr)
        return EXIT_COMMAND_FAILED

    fmt.debug(f"Spawned {entity_code} as #{entity_id} at ({x}, {y}, {z})")

    # Kill immediately
    kill_result = send_command(client, "killentity", [str(entity_id)], context, fmt)

    if not kill_result.get("Ok"):
        print(fmt.format(kill_result, "Kill failed"))
        return EXIT_COMMAND_FAILED

    # Return combined result
    result = {
        "Ok": True,
        "Message": f"Spawned and killed {entity_code} (#{entity_id}) at ({x:.1f}, {y:.1f}, {z:.1f})",
        "Data": {"id": entity_id, "code": entity_code, "pos": [x, y, z]}
    }
    print(fmt.format(result, "Spawn+kill"))

    if fmt.quiet:
        print(f"ENTITY_ID={entity_id}")

    return EXIT_SUCCESS


def cmd_spawnentity(client: HarnessClient, args, fmt: OutputFormatter) -> int:
    """Spawn a live entity at a location."""
    entity_code = args.entity

    # Get spawn position - use bot position + offset, or explicit coords
    bot_id = get_bot_id(args)
    if args.coords and len(args.coords) == 3:
        x, y, z = args.coords
    elif bot_id:
        # Get bot position and spawn 1 block away
        params = {"botId": bot_id}
        state = client.get("/polis/state", params)
        if not state.get("Bot"):
            print("Error: Could not get bot position", file=sys.stderr)
            return EXIT_COMMAND_FAILED
        pos = state["Bot"]["Pos"]
        x, y, z = pos[0] + 1, pos[1], pos[2]
    else:
        print("Error: Need --bot or coordinates to determine spawn location", file=sys.stderr)
        return EXIT_USAGE_ERROR

    # Spawn entity
    spawn_args = [entity_code, str(x), str(y), str(z)]
    context = build_context(args, client)
    spawn_result = send_command(client, "spawnentity", spawn_args, context, fmt)

    if not spawn_result.get("Ok"):
        print(fmt.format(spawn_result, "Spawn failed"))
        return EXIT_COMMAND_FAILED

    entity_id = spawn_result.get("Data", {}).get("id")
    if not entity_id:
        print("Error: No entity ID returned from spawn", file=sys.stderr)
        return EXIT_COMMAND_FAILED

    # Return result (no kill step)
    result = {
        "Ok": True,
        "Message": f"Spawned {entity_code} (#{entity_id}) at ({x:.1f}, {y:.1f}, {z:.1f})",
        "Data": {"id": entity_id, "code": entity_code, "pos": [x, y, z]}
    }
    print(fmt.format(result, "Spawn entity"))

    if fmt.quiet:
        print(f"ENTITY_ID={entity_id}")

    return EXIT_SUCCESS


def cmd_animate(client: HarnessClient, args, fmt: OutputFormatter) -> int:
    """Play or stop animations on selected bot."""
    cmd_args = list(args.anim_args) if args.anim_args else []

    # Don't add speed/loop for stop command
    if not (cmd_args and cmd_args[0].lower() == 'stop'):
        if hasattr(args, 'speed') and args.speed is not None:
            cmd_args.append(str(args.speed))
        if hasattr(args, 'loop') and args.loop:
            cmd_args.append('loop')

    context = build_context(args, client)
    result = send_command(client, 'animate', cmd_args, context, fmt)

    # Format output message based on operation
    if cmd_args and cmd_args[0].lower() == 'stop':
        success_msg = "Animation stopped"
    else:
        anim_code = cmd_args[0] if cmd_args else "unknown"
        success_msg = f"Playing animation '{anim_code}'"

    print(fmt.format(result, success_msg))
    return EXIT_SUCCESS if result.get("Ok") else EXIT_COMMAND_FAILED


# ============================================================================
# Scan/Verify/Build Commands
# ============================================================================

def cmd_scan(client: HarnessClient, args, fmt: OutputFormatter) -> int:
    """Scan a region and return blocks."""
    x1, y1, z1 = args.from_coords
    x2, y2, z2 = args.to_coords

    cmd_args = [str(int(x1)), str(int(y1)), str(int(z1)),
                str(int(x2)), str(int(y2)), str(int(z2))]

    if getattr(args, "include_air", False):
        cmd_args.append("--include-air")

    fmt.debug(f"POST /polis/command scan {cmd_args}")
    result = send_command(client, "scan", cmd_args, None, fmt)

    if not result.get("Ok"):
        print(fmt.format(result))
        return EXIT_COMMAND_FAILED

    data = result.get("Data", {})
    blocks = data.get("blocks", [])

    # Client-side filtering (reduce noise from natural terrain)
    filter_pattern = getattr(args, "filter", None)
    exclude_natural = getattr(args, "exclude_natural", False)

    # Natural blocks to exclude - common terrain that clutters blueprint output
    natural_patterns = ["soil", "stone", "gravel", "sand", "clay", "peat", "dirt", "rock",
                        "rawite", "andesite", "basalt", "granite", "chalk", "shale", "slate"]

    if filter_pattern or exclude_natural:
        filtered_blocks = []
        for b in blocks:
            code = (b.get("code") or "").lower()
            # Exclude natural blocks if requested
            if exclude_natural and any(p in code for p in natural_patterns):
                continue
            # Include only if matches filter pattern
            if filter_pattern and filter_pattern.lower() not in code:
                continue
            filtered_blocks.append(b)

        original_count = len(blocks)
        blocks = filtered_blocks
        data["blocks"] = blocks
        data["blockCount"] = len(blocks)
        if not fmt.quiet:
            print(f"Filtered: {original_count} -> {len(blocks)} blocks", file=sys.stderr)

    # Apply origin offset for output (convert to relative coords) - do this AFTER filtering
    if getattr(args, "relative", False):
        origin_x, origin_y, origin_z = min(x1, x2), min(y1, y2), min(z1, z2)
        for block in blocks:
            pos = block.get("pos", [0, 0, 0])
            block["pos"] = [pos[0] - origin_x, pos[1] - origin_y, pos[2] - origin_z]

    # Save to file if requested
    if getattr(args, "output", None):
        blueprint = {"name": f"scan_{int(x1)}_{int(y1)}_{int(z1)}", "blocks": blocks}
        with open(args.output, "w") as f:
            json.dump(blueprint, f, indent=2)
        print(f"Saved {len(blocks)} blocks to {args.output}", file=sys.stderr)
    else:
        # Only print full output if not saving to file
        print(fmt.format(result))
    return EXIT_SUCCESS


def cmd_verify(client: HarnessClient, args, fmt: OutputFormatter) -> int:
    """Verify a blueprint against world state."""
    # Load blueprint from file
    blueprint_path = args.blueprint
    try:
        with open(blueprint_path, "r") as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Error: Blueprint file not found: {blueprint_path}", file=sys.stderr)
        return EXIT_USAGE_ERROR
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in blueprint: {e}", file=sys.stderr)
        return EXIT_USAGE_ERROR

    # Handle both raw array and {name, blocks} format
    if isinstance(data, list):
        blocks = data
    else:
        blocks = data.get("blocks", [])

    if not blocks:
        print("Error: Blueprint has no blocks", file=sys.stderr)
        return EXIT_USAGE_ERROR

    # Apply origin offset if specified
    if getattr(args, "origin", None) and len(args.origin) == 3:
        ox, oy, oz = args.origin
        blocks = [
            {"pos": [b["pos"][0] + int(ox), b["pos"][1] + int(oy), b["pos"][2] + int(oz)], "code": b["code"]}
            for b in blocks
        ]

    # Send verify command with JSON blueprint
    blueprint_json = json.dumps(blocks)
    cmd_args = [blueprint_json]

    fmt.debug(f"POST /polis/command verify (blueprint: {len(blocks)} blocks)")
    result = send_command(client, "verify", cmd_args, None, fmt)

    if not result.get("Ok"):
        print(fmt.format(result))
        return EXIT_COMMAND_FAILED

    data = result.get("Data", {})
    completion = data.get("completionPct", 0)

    # Show summary
    print(fmt.format(result))

    # Show missing/wrong blocks in verbose mode
    if fmt.verbose:
        missing = data.get("missingBlocks", [])
        wrong = data.get("wrongBlocks", [])
        if missing:
            print(f"\nMissing blocks ({len(missing)}):", file=sys.stderr)
            for b in missing[:10]:
                print(f"  {b['pos']}: expected {b['expected']}", file=sys.stderr)
            if len(missing) > 10:
                print(f"  ... and {len(missing) - 10} more", file=sys.stderr)
        if wrong:
            print(f"\nWrong blocks ({len(wrong)}):", file=sys.stderr)
            for b in wrong[:10]:
                print(f"  {b['pos']}: expected {b['expected']}, got {b['actual']}", file=sys.stderr)
            if len(wrong) > 10:
                print(f"  ... and {len(wrong) - 10} more", file=sys.stderr)

    return EXIT_SUCCESS if completion == 100 else EXIT_COMMAND_FAILED


def wait_for_place_action(client: HarnessClient, args, fmt: "OutputFormatter", timeout: float = 5.0) -> int:
    """Wait for place action to complete via polling.

    Returns EXIT_SUCCESS when action completes or times out (timeout is OK since action may complete
    without a state update), or EXIT_COMMAND_FAILED if action explicitly failed.
    """
    deadline = time.time() + timeout
    bot_id = get_bot_id(args)
    params = {"botId": bot_id} if bot_id else {}

    while time.time() < deadline:
        result = client.get("/polis/state", params if params else None)
        last_action = result.get("LastAction") or {}

        if last_action.get("Name") == "place":
            if last_action.get("Ok") or "placed" in (last_action.get("Msg", "") or "").lower():
                return EXIT_SUCCESS
            if last_action.get("Ok") is False:
                return EXIT_COMMAND_FAILED

        time.sleep(0.2)

    return EXIT_SUCCESS  # Timeout OK - action may have completed


def cmd_build(client: HarnessClient, args, fmt: OutputFormatter) -> int:
    """Build from a blueprint with verification."""
    # Load blueprint
    blueprint_path = args.blueprint
    try:
        with open(blueprint_path, "r") as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Error: Blueprint file not found: {blueprint_path}", file=sys.stderr)
        return EXIT_USAGE_ERROR
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in blueprint: {e}", file=sys.stderr)
        return EXIT_USAGE_ERROR

    # Handle both raw array and {name, blocks} format
    if isinstance(data, list):
        blocks = data
        name = "unnamed"
    else:
        blocks = data.get("blocks", [])
        name = data.get("name", "unnamed")

    if not blocks:
        print("Error: Blueprint has no blocks", file=sys.stderr)
        return EXIT_USAGE_ERROR

    # Apply origin offset if specified
    origin = getattr(args, "origin", None)
    if origin and len(origin) == 3:
        ox, oy, oz = origin
        blocks = [
            {"pos": [b["pos"][0] + int(ox), b["pos"][1] + int(oy), b["pos"][2] + int(oz)], "code": b["code"]}
            for b in blocks
        ]

    context = build_context(args, client)
    if not context or "playerUid" not in context:
        print("Error: Player UID required for build (--player, $POLIS_PLAYER_UID, or single online player)", file=sys.stderr)
        return EXIT_USAGE_ERROR

    print(f"Building '{name}': {len(blocks)} blocks", file=sys.stderr)

    # Pre-flight: Check bot is selected
    bot_id = get_bot_id(args)
    if not bot_id:
        print("Error: Bot ID required (--bot or $POLIS_BOT_ID)", file=sys.stderr)
        return EXIT_USAGE_ERROR

    # Get bot state for inventory check
    state_result = client.get("/polis/state", {"botId": bot_id})
    if state_result.get("Error"):
        print(f"Error: {state_result.get('Error')}", file=sys.stderr)
        return EXIT_COMMAND_FAILED

    # Count blocks needed by type
    block_counts = {}
    for b in blocks:
        code = b["code"]
        block_counts[code] = block_counts.get(code, 0) + 1

    print(f"Blocks needed: {dict(list(block_counts.items())[:5])}{'...' if len(block_counts) > 5 else ''}", file=sys.stderr)

    # Build loop
    placed = 0
    skipped = 0
    failed = 0
    verify = getattr(args, "verify", True)
    dry_run = getattr(args, "dry_run", False)

    for i, block in enumerate(blocks):
        pos = block["pos"]
        code = block["code"]
        x, y, z = pos[0], pos[1], pos[2]

        # Check if already placed (if verify enabled)
        if verify:
            verify_result = send_command(client, "verify", [json.dumps([block])], None, fmt)
            verify_data = verify_result.get("Data", {})
            if verify_data.get("matched", 0) == 1:
                skipped += 1
                fmt.debug(f"Skipping {code} at ({x},{y},{z}) - already placed")
                continue

        if dry_run:
            print(f"[dry-run] Would place {code} at ({x}, {y}, {z})")
            continue

        # Place the block
        place_args = [code, str(x), str(y), str(z), "up"]
        place_result = send_command(client, "place", place_args, context, fmt)
        fmt.debug(f"place response for ({x},{y},{z}): {place_result}")

        if not place_result.get("Ok"):
            failed += 1
            msg = place_result.get("Message", "unknown error")
            print(f"Failed to place {code} at ({x},{y},{z}): {msg}", file=sys.stderr)
            if not getattr(args, "continue_on_error", False):
                break
        else:
            placed += 1

            # Wait for placement action to complete via polling
            wait_result = wait_for_place_action(client, args, fmt)
            if wait_result != EXIT_SUCCESS:
                fmt.debug("Placement action did not complete cleanly")

            # Verify if requested
            if verify:
                verify_result = send_command(client, "verify", [json.dumps([block])], None, fmt)
                verify_data = verify_result.get("Data", {})
                if verify_data.get("matched", 0) != 1:
                    print(f"Warning: Verification failed for {code} at ({x},{y},{z})", file=sys.stderr)

        # Progress update every 10 blocks or at end
        if (i + 1) % 10 == 0 or i == len(blocks) - 1:
            pct = ((placed + skipped + failed) / len(blocks)) * 100
            print(f"Progress: {placed + skipped + failed}/{len(blocks)} ({pct:.0f}%) - placed: {placed}, skipped: {skipped}, failed: {failed}", file=sys.stderr)

    # Final verification
    if verify and not dry_run and placed > 0:
        print("Running final verification...", file=sys.stderr)
        blueprint_json = json.dumps(blocks)
        final_result = send_command(client, "verify", [blueprint_json], None, fmt)
        final_data = final_result.get("Data", {})
        completion = final_data.get("completionPct", 0)
        print(f"Build complete: {completion}% verified ({final_data.get('matched', 0)}/{len(blocks)})", file=sys.stderr)

    result = {
        "Ok": failed == 0,
        "Message": f"Build complete: {placed} placed, {skipped} skipped, {failed} failed",
        "Data": {
            "total": len(blocks),
            "placed": placed,
            "skipped": skipped,
            "failed": failed
        }
    }
    print(fmt.format(result))
    return EXIT_SUCCESS if failed == 0 else EXIT_COMMAND_FAILED


# ============================================================================
# Viewpoint / Observer Camera Commands
# ============================================================================

def cmd_viewpoint_define(client: HarnessClient, args, fmt: OutputFormatter) -> int:
    """Define a named viewpoint for observer screenshots."""
    name = args.name
    x, y, z = args.x, args.y, args.z
    yaw, pitch = args.yaw, args.pitch
    station = getattr(args, "station", None)

    cmd_args = [name, str(x), str(y), str(z), str(yaw), str(pitch)]
    if station:
        cmd_args.append(station)

    result = send_command(client, "viewpoint-define", cmd_args, None, fmt)
    print(fmt.format(result, f"Defined viewpoint '{name}'"))
    return EXIT_SUCCESS if result.get("Ok") else EXIT_COMMAND_FAILED


def cmd_viewpoint_list(client: HarnessClient, args, fmt: OutputFormatter) -> int:
    """List all viewpoints."""
    result = send_command(client, "viewpoint-list", [], None, fmt)
    if result.get("Ok"):
        data = result.get("Data", {})
        viewpoints = data.get("viewpoints", [])
        if fmt.quiet:
            for v in viewpoints:
                station = f" -> {v.get('station')}" if v.get('station') else ""
                print(f"{v['name']}: ({v['x']:.1f}, {v['y']:.1f}, {v['z']:.1f}) yaw={v['yaw']:.2f} pitch={v['pitch']:.2f}{station}")
        else:
            print(fmt.format(result))
    else:
        print(fmt.format(result))
    return EXIT_SUCCESS if result.get("Ok") else EXIT_COMMAND_FAILED


def cmd_viewpoint_remove(client: HarnessClient, args, fmt: OutputFormatter) -> int:
    """Remove a named viewpoint."""
    name = args.name
    result = send_command(client, "viewpoint-remove", [name], None, fmt)
    print(fmt.format(result, f"Removed viewpoint '{name}'"))
    return EXIT_SUCCESS if result.get("Ok") else EXIT_COMMAND_FAILED


def cmd_observer_screenshot(client: HarnessClient, args, fmt: OutputFormatter) -> int:
    """Take screenshot from arbitrary position (player restored after)."""
    x, y, z = args.x, args.y, args.z
    yaw, pitch = args.yaw, args.pitch
    save = getattr(args, "save", False)

    # Get player UID
    player_uid = get_player_uid(args, client)
    if not player_uid:
        print("Error: Player UID required (--player, $POLIS_PLAYER_UID, or single online player)", file=sys.stderr)
        return EXIT_USAGE_ERROR

    params = {
        "playerUid": player_uid,
        "x": str(x),
        "y": str(y),
        "z": str(z),
        "yaw": str(yaw),
        "pitch": str(pitch),
        "save": "true" if save else "false"
    }

    fmt.debug(f"GET /polis/observer-screenshot params={params}")
    result = client.get("/polis/observer-screenshot", params)

    if result.get("ok"):
        # Remove base64 from output for readability
        output = dict(result)
        if "base64Png" in output and output["base64Png"]:
            b64_len = len(output["base64Png"])
            output["base64Png"] = f"<{b64_len} chars>"
        print(fmt.format(output, f"Observer screenshot: {result.get('width')}x{result.get('height')}"))
    else:
        print(fmt.format(result))

    return EXIT_SUCCESS if result.get("ok") else EXIT_COMMAND_FAILED


def cmd_viewpoint_screenshot(client: HarnessClient, args, fmt: OutputFormatter) -> int:
    """Take screenshot from named viewpoint (player restored after)."""
    name = args.name
    save = getattr(args, "save", False)

    # Get player UID
    player_uid = get_player_uid(args, client)
    if not player_uid:
        print("Error: Player UID required (--player, $POLIS_PLAYER_UID, or single online player)", file=sys.stderr)
        return EXIT_USAGE_ERROR

    # First lookup the viewpoint
    vp_result = send_command(client, "viewpoint-list", [], None, fmt)
    if not vp_result.get("Ok"):
        print(f"Error: Failed to get viewpoint list: {vp_result.get('Message', 'unknown error')}", file=sys.stderr)
        return EXIT_COMMAND_FAILED

    data = vp_result.get("Data", {})
    viewpoints = data.get("viewpoints", [])
    viewpoint = None
    for v in viewpoints:
        if v.get("name") == name:
            viewpoint = v
            break

    if not viewpoint:
        print(f"Error: Viewpoint '{name}' not found", file=sys.stderr)
        return EXIT_COMMAND_FAILED

    # Call observer-screenshot with viewpoint coordinates
    params = {
        "playerUid": player_uid,
        "x": str(viewpoint["x"]),
        "y": str(viewpoint["y"]),
        "z": str(viewpoint["z"]),
        "yaw": str(viewpoint["yaw"]),
        "pitch": str(viewpoint["pitch"]),
        "save": "true" if save else "false"
    }

    fmt.debug(f"GET /polis/observer-screenshot params={params} (viewpoint: {name})")
    result = client.get("/polis/observer-screenshot", params)

    if result.get("ok"):
        # Remove base64 from output for readability
        output = dict(result)
        if "base64Png" in output and output["base64Png"]:
            b64_len = len(output["base64Png"])
            output["base64Png"] = f"<{b64_len} chars>"
        print(fmt.format(output, f"Viewpoint '{name}' screenshot: {result.get('width')}x{result.get('height')}"))
    else:
        print(fmt.format(result))

    return EXIT_SUCCESS if result.get("ok") else EXIT_COMMAND_FAILED


# ============================================================================
# Container Registry Commands
# ============================================================================

def cmd_zone_define(client: HarnessClient, args, fmt: OutputFormatter) -> int:
    """Define a named AABB zone."""
    name = args.name
    x1, y1, z1 = int(args.x1), int(args.y1), int(args.z1)
    x2, y2, z2 = int(args.x2), int(args.y2), int(args.z2)
    result = send_command(client, "zone-define", [name, str(x1), str(y1), str(z1), str(x2), str(y2), str(z2)], None, fmt)
    print(fmt.format(result, f"Defined zone '{name}'"))
    return EXIT_SUCCESS if result.get("Ok") else EXIT_COMMAND_FAILED


def cmd_zone_remove(client: HarnessClient, args, fmt: OutputFormatter) -> int:
    """Remove a named zone."""
    name = args.name
    result = send_command(client, "zone-remove", [name], None, fmt)
    print(fmt.format(result, f"Removed zone '{name}'"))
    return EXIT_SUCCESS if result.get("Ok") else EXIT_COMMAND_FAILED


def cmd_zone_list(client: HarnessClient, args, fmt: OutputFormatter) -> int:
    """List all zones."""
    result = client.get("/polis/zones")
    if result.get("Ok"):
        data = result.get("Data", {})
        zones = data.get("zones", [])
        if fmt.quiet:
            for z in zones:
                b = z.get("bounds", {})
                print(f"{z['name']}: ({b.get('x1')},{b.get('y1')},{b.get('z1')}) to ({b.get('x2')},{b.get('y2')},{b.get('z2')})")
        else:
            print(fmt.format(result))
    else:
        print(fmt.format(result))
    return EXIT_SUCCESS if result.get("Ok") else EXIT_COMMAND_FAILED


def cmd_zone_check(client: HarnessClient, args, fmt: OutputFormatter) -> int:
    """Check which zones a bot is in."""
    bot_id = get_bot_id(args)
    params = {"botId": bot_id} if bot_id else {}
    result = client.get("/polis/zone-check", params)
    print(fmt.format(result))
    return EXIT_SUCCESS if result.get("Ok") else EXIT_COMMAND_FAILED


def cmd_zone_show(client: HarnessClient, args, fmt: OutputFormatter) -> int:
    """Highlight a zone's boundaries."""
    name = args.name
    result = send_command(client, "zone-show", [name], None, fmt)
    print(fmt.format(result, f"Highlighting zone '{name}'"))
    return EXIT_SUCCESS if result.get("Ok") else EXIT_COMMAND_FAILED


def cmd_container_register(client: HarnessClient, args, fmt: OutputFormatter) -> int:
    """Register a named container."""
    name = args.name
    x, y, z = args.x, args.y, args.z
    container_type = getattr(args, "type", None)
    description = getattr(args, "desc", None)

    cmd_args = [name, str(int(x)), str(int(y)), str(int(z))]
    if container_type:
        cmd_args.append(container_type)
    if description:
        cmd_args.append(description)

    context = build_context(args, client)
    if not context or "playerUid" not in context:
        print("Error: Player UID required (--player, $POLIS_PLAYER_UID, or single online player)", file=sys.stderr)
        return EXIT_USAGE_ERROR

    result = send_command(client, "container-register", cmd_args, context, fmt)
    print(fmt.format(result, f"Registered container '{name}'"))
    return EXIT_SUCCESS if result.get("Ok") else EXIT_COMMAND_FAILED


def cmd_container_list(client: HarnessClient, args, fmt: OutputFormatter) -> int:
    """List registered containers."""
    container_type = getattr(args, "type", None)
    cmd_args = [container_type] if container_type else []

    result = send_command(client, "container-list", cmd_args, None, fmt)

    if result.get("Ok"):
        data = result.get("Data", {})
        containers = data.get("containers", [])
        if fmt.quiet:
            for c in containers:
                valid_mark = "✓" if c.get("valid") else "✗"
                print(f"{valid_mark} {c['name']}: ({c['pos'][0]}, {c['pos'][1]}, {c['pos'][2]}) [{c.get('containerType', 'generic')}]")
        else:
            print(fmt.format(result))
    else:
        print(fmt.format(result))

    return EXIT_SUCCESS if result.get("Ok") else EXIT_COMMAND_FAILED


def cmd_container_remove(client: HarnessClient, args, fmt: OutputFormatter) -> int:
    """Remove a container from registry."""
    name = args.name
    result = send_command(client, "container-remove", [name], None, fmt)
    print(fmt.format(result, f"Removed container '{name}'"))
    return EXIT_SUCCESS if result.get("Ok") else EXIT_COMMAND_FAILED


def cmd_container_contents(client: HarnessClient, args, fmt: OutputFormatter) -> int:
    """Get container contents."""
    include_empty = getattr(args, "include_empty", False)
    container_name = getattr(args, "container", None)
    positional = getattr(args, "coords", [])

    if container_name:
        params = {"name": container_name}
    elif positional and len(positional) == 3:
        x, y, z = positional
        params = {"x": str(int(x)), "y": str(int(y)), "z": str(int(z))}
    else:
        print("Error: Either -c <name> or x y z coordinates required", file=sys.stderr)
        return EXIT_USAGE_ERROR

    if include_empty:
        params["includeEmpty"] = "true"

    result = client.get("/polis/container-contents", params)

    if result.get("Ok"):
        data = result.get("Data", {})
        slots = data.get("slots", [])
        if fmt.quiet:
            if data.get("isEmpty"):
                print(f"EMPTY ({data.get('slotCount', 0)} slots)")
            else:
                for s in slots:
                    print(f"[{s['slot']}] {s['code']} x{s['qty']}")
        else:
            print(fmt.format(result))
    else:
        print(fmt.format(result))

    return EXIT_SUCCESS if result.get("Ok") else EXIT_COMMAND_FAILED


def cmd_container_set(client: HarnessClient, args, fmt: OutputFormatter) -> int:
    """Set a specific container slot to an item directly (no bot needed)."""
    positional = getattr(args, "args", [])

    # Usage: container-set <x> <y> <z> <slot> <itemCode> [qty]
    if len(positional) < 5:
        print("Usage: container-set <x> <y> <z> <slot> <itemCode> [qty]", file=sys.stderr)
        return EXIT_USAGE_ERROR

    cmd_args = positional[:6] if len(positional) >= 6 else positional[:5]

    result = send_command(client, "container-set", cmd_args, None, fmt)
    print(fmt.format(result, "Container set"))
    return EXIT_SUCCESS if result.get("Ok") else EXIT_COMMAND_FAILED


# ============================================================================
# Yaw/Direction Helpers
# ============================================================================

def calculate_yaw_to_face(from_x: float, from_z: float, to_x: float, to_z: float) -> float:
    """Calculate yaw (radians) to face from one position to another.

    VS yaw convention: yaw = atan2(dx, dz) + π
    """
    dx = to_x - from_x
    dz = to_z - from_z
    return math.atan2(dx, dz) + math.pi


# Cardinal direction yaw values (radians)
# Calculated using: yaw = atan2(dx, dz) + π for each direction
CARDINAL_YAWS = {
    'n': 0.0,                      # North (-Z)
    's': math.pi,                  # South (+Z)
    'e': 3 * math.pi / 2,          # East (+X)
    'w': math.pi / 2,              # West (-X)
    'ne': 2 * math.pi - math.pi/4, # Northeast
    'nw': math.pi / 4,             # Northwest
    'se': math.pi + math.pi/4,     # Southeast
    'sw': 3 * math.pi / 4,         # Southwest
    'north': 0.0,
    'south': math.pi,
    'east': 3 * math.pi / 2,
    'west': math.pi / 2,
}


def parse_yaw(yaw_str: str, player_pos: tuple = None, client: HarnessClient = None,
              args=None, fmt: OutputFormatter = None) -> float:
    """Parse yaw from string - can be radians, cardinal direction, or 'bot'.

    Args:
        yaw_str: Yaw value as string (number, cardinal, or 'bot')
        player_pos: (x, z) tuple of player position for relative calculations
        client: HarnessClient for bot lookup
        args: Command args for bot ID
        fmt: OutputFormatter for debug

    Returns:
        Yaw in radians
    """
    yaw_lower = yaw_str.lower()

    # Cardinal direction
    if yaw_lower in CARDINAL_YAWS:
        return CARDINAL_YAWS[yaw_lower]

    # Face the selected bot
    if yaw_lower == 'bot' and player_pos and client:
        bot_id = get_bot_id(args) if args else None
        params = {"botId": bot_id} if bot_id else {}
        result = client.get("/polis/state", params if params else None)
        bot = result.get("Bot", {})
        bot_pos = bot.get("Pos", [0, 0, 0])
        if fmt:
            fmt.debug(f"Bot position: {bot_pos}")
        return calculate_yaw_to_face(player_pos[0], player_pos[1], bot_pos[0], bot_pos[2])

    # Try parsing as number (radians)
    try:
        return float(yaw_str)
    except ValueError:
        raise ValueError(f"Invalid yaw: '{yaw_str}'. Use radians, cardinal (n/s/e/w/ne/nw/se/sw), or 'bot'")


def cmd_teleport(client: HarnessClient, args, fmt: OutputFormatter) -> int:
    """Teleport player to position with optional view direction."""
    player_uid = get_player_uid(args, client)
    if not player_uid:
        print("Error: Player UID required (--player, $POLIS_PLAYER_UID, or single online player)", file=sys.stderr)
        return EXIT_USAGE_ERROR

    x, y, z = args.x, args.y, args.z

    # Build command args
    cmd_args = [player_uid, str(x), str(y), str(z)]

    # Handle yaw
    yaw = None
    if hasattr(args, "yaw") and args.yaw is not None:
        try:
            yaw = parse_yaw(args.yaw, (x, z), client, args, fmt)
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            return EXIT_USAGE_ERROR
    elif hasattr(args, "face") and args.face:
        # Face specific coordinates
        fx, fz = args.face
        yaw = calculate_yaw_to_face(x, z, fx, fz)
        fmt.debug(f"Facing ({fx}, {fz}), yaw = {yaw:.4f}")
    elif hasattr(args, "face_bot") and args.face_bot:
        # Face the selected bot
        try:
            yaw = parse_yaw("bot", (x, z), client, args, fmt)
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            return EXIT_USAGE_ERROR

    # Handle pitch
    pitch = getattr(args, "pitch", 0.0) or 0.0

    # Add yaw/pitch if specified
    if yaw is not None:
        cmd_args.append(str(yaw))
        cmd_args.append(str(pitch))

    fmt.debug(f"POST /polis/command teleport {cmd_args}")
    result = send_command(client, "teleport", cmd_args, None, fmt)

    yaw_info = f" facing yaw={yaw:.2f}" if yaw is not None else ""
    print(fmt.format(result, f"Teleported to ({x}, {y}, {z}){yaw_info}"))
    return EXIT_SUCCESS if result.get("Ok") else EXIT_COMMAND_FAILED


def cmd_setup_view(client: HarnessClient, args, fmt: OutputFormatter) -> int:
    """Position player camera to view selected bot."""
    bot_id = get_bot_id(args)
    player_uid = get_player_uid(args, client)

    if not bot_id:
        print("Error: Bot ID required (--bot or $POLIS_BOT_ID)", file=sys.stderr)
        return EXIT_USAGE_ERROR

    if not player_uid:
        print("Error: Player UID required (--player, $POLIS_PLAYER_UID, or single online player)", file=sys.stderr)
        return EXIT_USAGE_ERROR

    # Get bot position
    params = {"botId": bot_id}
    fmt.debug(f"GET /polis/state params={params}")
    state = client.get("/polis/state", params)

    if state.get("Error"):
        print(f"Error: {state.get('Error')}", file=sys.stderr)
        return EXIT_COMMAND_FAILED

    bot = state.get("Bot", {})
    bot_pos = bot.get("Pos", [0, 0, 0])
    if len(bot_pos) < 3:
        print("Error: Could not get bot position", file=sys.stderr)
        return EXIT_COMMAND_FAILED

    # Calculate viewing position (distance blocks away, slightly elevated)
    distance = getattr(args, "distance", 3.0)
    # Position player to the south (+Z) of bot, facing north toward bot
    view_x = bot_pos[0]
    view_y = bot_pos[1] + 1.0  # Slight elevation for better view
    view_z = bot_pos[2] + distance

    # Calculate yaw to face the bot
    yaw = calculate_yaw_to_face(view_x, view_z, bot_pos[0], bot_pos[2])
    pitch = 0.0  # Look straight ahead

    fmt.debug(f"Bot at ({bot_pos[0]:.1f}, {bot_pos[1]:.1f}, {bot_pos[2]:.1f})")
    fmt.debug(f"Positioning player at ({view_x:.1f}, {view_y:.1f}, {view_z:.1f}) facing yaw={yaw:.2f}")

    # Teleport player
    cmd_args = [player_uid, str(view_x), str(view_y), str(view_z), str(yaw), str(pitch)]
    result = send_command(client, "teleport", cmd_args, None, fmt)

    if not result.get("Ok"):
        print(fmt.format(result, "Teleport failed"))
        return EXIT_COMMAND_FAILED

    print(fmt.format(result, f"Positioned to view bot #{bot_id} from {distance:.1f}m"))

    # Optional screenshot
    if getattr(args, "screenshot", False):
        time.sleep(0.3)  # Brief delay for render
        save = "true" if getattr(args, "save", False) else "false"
        ss_params = {"playerUid": player_uid, "save": save}
        fmt.debug(f"GET /polis/screenshot params={ss_params}")
        ss_result = client.get("/polis/screenshot", ss_params)

        if ss_result.get("ok"):
            saved_path = ss_result.get("filePath")
            if saved_path:
                print(f"Screenshot saved: {saved_path}", file=sys.stderr)
            else:
                print(f"Screenshot captured: {ss_result.get('width')}x{ss_result.get('height')}", file=sys.stderr)
        else:
            print(f"Screenshot failed: {ss_result.get('error', 'unknown')}", file=sys.stderr)

    return EXIT_SUCCESS


def cmd_screenshot(client: HarnessClient, args, fmt: OutputFormatter) -> int:
    """Capture screenshot from player's view."""
    player_uid = get_player_uid(args, client)
    if not player_uid:
        print("Error: Player UID required (--player, $POLIS_PLAYER_UID, or single online player)", file=sys.stderr)
        return EXIT_USAGE_ERROR

    save = "true" if getattr(args, "save", False) else "false"
    params = {"playerUid": player_uid, "save": save}

    fmt.debug(f"GET /polis/screenshot params={params}")
    result = client.get("/polis/screenshot", params)

    # For quiet mode, just return success/fail
    if fmt.quiet:
        if result.get("ok"):
            print(f"OK {result.get('width')}x{result.get('height')}")
            return EXIT_SUCCESS
        else:
            print(f"FAIL: {result.get('error', 'Unknown error')}")
            return EXIT_COMMAND_FAILED

    # Remove base64 data from output for readability (it's huge)
    output = dict(result)
    for key in ["base64Png", "base64"]:
        if key in output and output[key]:
            b64_len = len(output[key])
            output[key] = f"<{b64_len} chars>"

    print(fmt.format(output))
    return EXIT_SUCCESS if result.get("ok") else EXIT_COMMAND_FAILED


def wait_for_action(client: HarnessClient, args, fmt: OutputFormatter, action_name: str, done_msg: str) -> int:
    """Wait for a timed action to complete."""
    timeout = getattr(args, "timeout", 30)
    deadline = time.time() + timeout

    fmt.debug(f"Waiting for action '{action_name}' to complete (timeout={timeout}s)")

    bot_id = get_bot_id(args)
    params = {"botId": bot_id} if bot_id else {}

    while time.time() < deadline:
        result = client.get("/polis/state", params if params else None)
        last_action = result.get("LastAction") or {}

        if last_action.get("Name") == action_name:
            msg = last_action.get("Msg", "")
            if done_msg in msg.lower() or last_action.get("Ok"):
                if not fmt.quiet:
                    print(fmt.format({"completed": True, "action": last_action}))
                return EXIT_SUCCESS

        time.sleep(0.5)

    print(f"Timeout waiting for {action_name} to complete", file=sys.stderr)
    return EXIT_COMMAND_FAILED


# ============================================================================
# Main Entry Point
# ============================================================================

def create_global_parser():
    """Create parent parser with global arguments."""
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument("--host", default="localhost", help="Harness host (default: localhost)")
    parent.add_argument("--port", type=int, default=8585, help="Harness port (default: 8585)")
    parent.add_argument("--player", metavar="UID", help="Player UID (overrides $POLIS_PLAYER_UID)")
    parent.add_argument("--bot", metavar="ID", help="Bot ID (overrides $POLIS_BOT_ID)")
    parent.add_argument("--json", action="store_true", dest="use_json", help="Force JSON output")
    parent.add_argument("--quiet", "-q", action="store_true", help="Minimal output")
    parent.add_argument("--verbose", "-v", action="store_true", help="Debug output")
    parent.add_argument("--tokens", "-t", action="store_true", help="Show token count comparison (TOON vs JSON)")
    parent.add_argument("--timeout", type=float, default=30, help="Wait timeout seconds (default: 30)")
    return parent




def main():
    # Create parent parser with global args that all subcommands inherit
    global_parent = create_global_parser()

    parser = argparse.ArgumentParser(
        prog="polis",
        description="CLI for polis-builder-npc HTTP test harness",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Global options (use after subcommand, e.g., 'polis look --player UID'):
  --host HOST         Harness host (default: localhost)
  --port PORT         Harness port (default: 8585)
  --player UID        Player UID (overrides $POLIS_PLAYER_UID)
  --bot ID            Bot ID (overrides $POLIS_BOT_ID)
  --json              Force JSON output
  -q, --quiet         Minimal output
  -v, --verbose       Debug output
  -t, --tokens        Show token count comparison
  --timeout SECONDS   Wait timeout (default: 30)

Environment variables:
  POLIS_PLAYER_UID    Default player UID for commands
  POLIS_BOT_ID        Default bot ID for state/commands

Examples:
  polis status                    # Check server ready
  polis spawn                     # Spawn bot at world spawn
  polis spawn 100 65 -200         # Spawn at coordinates
  polis bots                      # List all bots
  polis select 12345              # Select bot
  polis state                     # Get bot state
  polis goto 100 65 -200          # Move bot
  polis give game:pickaxe-copper  # Give item
  polis mine 100 65 -200          # Mine block
"""
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # status
    p = subparsers.add_parser("status", help="Check server readiness", parents=[global_parent])
    p.set_defaults(func=cmd_status)

    # players
    p = subparsers.add_parser("players", help="List online players", parents=[global_parent])
    p.set_defaults(func=cmd_players)

    # player
    p = subparsers.add_parser("player", help="Get player info", parents=[global_parent])
    p.add_argument("uid", nargs="?", help="Player UID (uses $POLIS_PLAYER_UID if omitted)")
    p.set_defaults(func=cmd_player)

    # bots
    p = subparsers.add_parser("bots", help="List all bots", parents=[global_parent])
    p.set_defaults(func=cmd_bots)

    # state
    p = subparsers.add_parser("state", help="Get bot state", parents=[global_parent])
    p.add_argument("id", nargs="?", help="Bot ID (uses $POLIS_BOT_ID if omitted)")
    p.add_argument("--radius", type=float, help="Scan radius for nearby items")
    p.set_defaults(func=cmd_state)

    # targets
    p = subparsers.add_parser("targets", help="Get nearby interactables", parents=[global_parent])
    p.add_argument("--radius", type=float, default=8, help="Search radius (default: 8)")
    p.add_argument("--limit", type=int, help="Max results")
    p.add_argument("--mode", choices=["blocks", "entities", "all"], help="Filter mode")
    p.add_argument("--search", "-s", dest="q", help="Search blocks/entities by code substring")
    p.add_argument("--query", "-Q", help="Filter by code substring (server-side codeContains)")
    p.add_argument("--filter", help="Filter results by code pattern (client-side, e.g., 'door', 'chest')")
    p.add_argument("--exclude-natural", action="store_true", dest="exclude_natural",
                   help="Exclude natural blocks (soil, stone, gravel, etc.)")
    p.add_argument("--include-dead", action="store_true", dest="include_dead",
                   help="Include dead entities (corpses) when mode=entities")
    p.set_defaults(func=cmd_targets)

    # look
    p = subparsers.add_parser("look", help="Get player look target", parents=[global_parent])
    p.add_argument("--range", type=float, default=48, help="Raytrace range (default: 48)")
    p.set_defaults(func=cmd_look)

    # spawn
    p = subparsers.add_parser("spawn", help="Spawn a new bot", parents=[global_parent])
    p.add_argument("coords", nargs="*", type=float, help="Optional: x y z coordinates (overrides player-relative)")
    p.add_argument("--entity", help="Entity code (bypasses profession loadout)")
    p.add_argument("--profession", "-p", default="laborer", choices=PROFESSIONS,
                   help="Profession loadout (default: laborer)")
    p.add_argument("--offset", nargs=3, type=float, metavar=("X", "Y", "Z"),
                   help="Offset from player (default: 2 0 0)")
    p.add_argument("--worldspawn", action="store_true",
                   help="Spawn at world spawn instead of near player")
    p.set_defaults(func=cmd_spawn)

    # professions
    p = subparsers.add_parser("professions", help="List available professions", parents=[global_parent])
    p.set_defaults(func=cmd_professions)

    # select
    p = subparsers.add_parser("select", help="Select a bot by ID", parents=[global_parent])
    p.add_argument("id", type=int, help="Bot ID")
    p.set_defaults(func=cmd_select)

    # despawn
    p = subparsers.add_parser("despawn", help="Despawn selected bot", parents=[global_parent])
    p.set_defaults(func=cmd_despawn)

    # goto
    p = subparsers.add_parser("goto", help="Move bot to coordinates", parents=[global_parent])
    p.add_argument("x", type=float, help="X coordinate")
    p.add_argument("y", type=float, help="Y coordinate")
    p.add_argument("z", type=float, help="Z coordinate")
    p.add_argument("--wait", action="store_true", help="Wait for arrival")
    p.set_defaults(func=cmd_goto)

    # stop
    p = subparsers.add_parser("stop", help="Stop current bot activity", parents=[global_parent])
    p.set_defaults(func=cmd_stop)

    # give
    p = subparsers.add_parser("give", help="Give item to bot", parents=[global_parent])
    p.add_argument("item", help="Item code (e.g., game:pickaxe-copper)")
    p.add_argument("qty", nargs="?", type=int, default=1, help="Quantity (default: 1)")
    p.set_defaults(func=cmd_give)

    # equip
    p = subparsers.add_parser("equip", help="Equip item to bot slot", parents=[global_parent])
    p.add_argument("slot", choices=["lefthand", "righthand", "backpack0", "backpack1"],
                   help="Slot: lefthand, righthand, backpack0, backpack1")
    p.add_argument("item", help="Item code (e.g., game:linen-sack)")
    p.add_argument("qty", nargs="?", type=int, default=1, help="Quantity (default: 1)")
    p.set_defaults(func=cmd_equip)

    # drop
    p = subparsers.add_parser("drop", help="Drop items from bot hand", parents=[global_parent])
    p.add_argument("slot", nargs="?", type=int, default=-1, help="Slot: -1=auto, 0=right, 1=left (default: -1)")
    p.add_argument("qty", nargs="?", type=int, default=0, help="Quantity (0=all, default: 0)")
    p.set_defaults(func=cmd_drop)

    # pickup
    p = subparsers.add_parser("pickup", help="Pick up nearby item", parents=[global_parent])
    p.add_argument("id", nargs="?", help="Entity ID (optional, picks nearest if omitted)")
    p.add_argument("--range", type=float, default=3.0, help="Pickup range (default: 3.0)")
    p.set_defaults(func=cmd_pickup)

    # activate
    p = subparsers.add_parser("activate", help="Activate a block (door, chest, etc.)", parents=[global_parent])
    p.add_argument("x", type=float, help="X coordinate")
    p.add_argument("y", type=float, help="Y coordinate")
    p.add_argument("z", type=float, help="Z coordinate")
    p.add_argument("--shift", "-s", action="store_true", help="Hold shift during activation (e.g. place ingot on anvil)")
    p.set_defaults(func=cmd_activate)

    # ignite
    p = subparsers.add_parser("ignite", help="Ignite an IIgnitable block (firepit, torch, etc.)", parents=[global_parent])
    p.add_argument("x", type=float, help="X coordinate")
    p.add_argument("y", type=float, help="Y coordinate")
    p.add_argument("z", type=float, help="Z coordinate")
    p.set_defaults(func=cmd_ignite)

    # mine
    p = subparsers.add_parser("mine", help="Mine a block", parents=[global_parent])
    p.add_argument("x", type=float, help="X coordinate")
    p.add_argument("y", type=float, help="Y coordinate")
    p.add_argument("z", type=float, help="Z coordinate")
    p.add_argument("--autocollect", action="store_true", help="Auto-pickup drops")
    p.add_argument("--no-wait", dest="wait", action="store_false", help="Don't wait for completion")
    p.set_defaults(func=cmd_mine)

    # break (debug)
    p = subparsers.add_parser("break", help="[DEBUG] Instantly break a block (no mining time)", parents=[global_parent])
    p.add_argument("x", type=float, help="X coordinate")
    p.add_argument("y", type=float, help="Y coordinate")
    p.add_argument("z", type=float, help="Z coordinate")
    p.add_argument("--dropmult", type=float, default=1.0, help="Drop multiplier (default: 1.0)")
    p.set_defaults(func=cmd_break)

    # place
    p = subparsers.add_parser("place", help="Place a block (requires item in inventory)", parents=[global_parent])
    p.add_argument("blockcode", help="Block code (e.g., game:cobblestone)")
    p.add_argument("x", type=float, help="X coordinate")
    p.add_argument("y", type=float, help="Y coordinate")
    p.add_argument("z", type=float, help="Z coordinate")
    p.add_argument("--face", choices=["up", "down", "north", "south", "east", "west"],
                   default="up", help="Face direction (default: up)")
    p.add_argument("--no-wait", dest="wait", action="store_false", help="Don't wait for completion")
    p.set_defaults(func=cmd_place)

    # setblock
    p = subparsers.add_parser("setblock", help="Directly set block in world (admin, no bot needed)", parents=[global_parent])
    p.add_argument("blockcode", help="Block code (e.g., game:cobblestone) or 'air'")
    p.add_argument("x", type=float, help="X coordinate")
    p.add_argument("y", type=float, help="Y coordinate")
    p.add_argument("z", type=float, help="Z coordinate")
    p.set_defaults(func=cmd_setblock)

    # harvest
    p = subparsers.add_parser("harvest", help="Harvest a block (berries, resin)", parents=[global_parent])
    p.add_argument("x", type=float, help="X coordinate")
    p.add_argument("y", type=float, help="Y coordinate")
    p.add_argument("z", type=float, help="Z coordinate")
    p.add_argument("--autocollect", action="store_true", help="Auto-pickup drops")
    p.add_argument("--no-validate", dest="validate", action="store_false", help="Skip ripeness check")
    p.add_argument("--no-wait", dest="wait", action="store_false", help="Don't wait for completion")
    p.set_defaults(func=cmd_harvest)

    # harvestcrop
    p = subparsers.add_parser("harvestcrop", help="Harvest a farmland crop", parents=[global_parent])
    p.add_argument("x", type=float, help="X coordinate")
    p.add_argument("y", type=float, help="Y coordinate")
    p.add_argument("z", type=float, help="Z coordinate")
    p.add_argument("--autocollect", action="store_true", help="Auto-pickup drops")
    p.add_argument("--no-wait", dest="wait", action="store_false", help="Don't wait for completion")
    p.set_defaults(func=cmd_harvestcrop)

    # grind
    # forge-heat
    p = subparsers.add_parser("forge-heat", help="Wait for firepit input to reach temperature", parents=[global_parent])
    p.add_argument("x", type=float, help="X coordinate")
    p.add_argument("y", type=float, help="Y coordinate")
    p.add_argument("z", type=float, help="Z coordinate")
    p.add_argument("--duration", "-d", type=float, default=120, help="Max wait time in seconds (default 120)")
    p.add_argument("--no-wait", dest="wait", action="store_false", help="Don't wait for completion")
    p.set_defaults(func=cmd_forge_heat)

    p = subparsers.add_parser("grind", help="Grind items in a quern", parents=[global_parent])
    p.add_argument("x", type=float, help="X coordinate")
    p.add_argument("y", type=float, help="Y coordinate")
    p.add_argument("z", type=float, help="Z coordinate")
    p.add_argument("--count", "-c", type=int, default=0, help="Max items to grind (0=unlimited)")
    p.add_argument("--duration", "-d", type=float, default=0, help="Max grinding time in seconds (0=unlimited)")
    p.add_argument("--no-wait", dest="wait", action="store_false", help="Don't wait for completion")
    p.set_defaults(func=cmd_grind)

    # press
    p = subparsers.add_parser("press", help="Press fruit in a fruit press", parents=[global_parent])
    p.add_argument("x", type=float, help="X coordinate")
    p.add_argument("y", type=float, help="Y coordinate")
    p.add_argument("z", type=float, help="Z coordinate")
    p.add_argument("--duration", "-d", type=float, default=0, help="Max pressing time in seconds (0=unlimited)")
    p.add_argument("--no-autounscrew", dest="autounscrew", action="store_false", help="Don't auto-unscrew when complete")
    p.add_argument("--no-wait", dest="wait", action="store_false", help="Don't wait for completion")
    p.set_defaults(func=cmd_press)

    # clayform
    p = subparsers.add_parser("clayform", help="Form clay into a recipe shape", parents=[global_parent])
    p.add_argument("x", type=float, help="X coordinate")
    p.add_argument("y", type=float, help="Y coordinate")
    p.add_argument("z", type=float, help="Z coordinate")
    p.add_argument("recipe", help="Output recipe code (e.g., bowl-raw, toolmold-fire-raw-anvil)")
    p.add_argument("--speed", "-s", type=int, default=4, help="Voxels per tick (default: 4, higher = faster)")
    p.add_argument("--no-wait", dest="wait", action="store_false", help="Don't wait for completion")
    p.set_defaults(func=cmd_clayform)

    # knap
    p = subparsers.add_parser("knap", help="Knap flint/stone into tools", parents=[global_parent])
    p.add_argument("x", type=float, help="X coordinate")
    p.add_argument("y", type=float, help="Y coordinate")
    p.add_argument("z", type=float, help="Z coordinate")
    p.add_argument("recipe", help="Output recipe code (e.g., arrowhead-flint, knife-blade-flint)")
    p.add_argument("--speed", "-s", type=int, default=4, help="Voxels per tick (default: 4, higher = faster)")
    p.add_argument("--no-wait", dest="wait", action="store_false", help="Don't wait for completion")
    p.set_defaults(func=cmd_knap)

    # seal
    p = subparsers.add_parser("seal", help="Seal a barrel for fermentation/pickling", parents=[global_parent])
    p.add_argument("x", type=float, help="X coordinate")
    p.add_argument("y", type=float, help="Y coordinate")
    p.add_argument("z", type=float, help="Z coordinate")
    p.set_defaults(func=cmd_seal)

    # anvil-smith
    p = subparsers.add_parser("anvil-smith", help="Smith a work item on an anvil", parents=[global_parent])
    p.add_argument("x", type=float, help="X coordinate")
    p.add_argument("y", type=float, help="Y coordinate")
    p.add_argument("z", type=float, help="Z coordinate")
    p.add_argument("recipe", help="Output recipe code (e.g., pickaxehead-copper, metalplate-iron)")
    p.add_argument("--speed", "-s", type=int, default=4, help="Voxels per tick (default: 4, higher = faster)")
    p.add_argument("--wait", "-w", action="store_true", help="Wait for smithing to complete")
    p.set_defaults(func=cmd_anvil_smith)

    # anvil-state
    p = subparsers.add_parser("anvil-state", help="Get anvil state (work item, recipe, voxels)", parents=[global_parent])
    p.add_argument("x", type=float, help="X coordinate")
    p.add_argument("y", type=float, help="Y coordinate")
    p.add_argument("z", type=float, help="Z coordinate")
    p.set_defaults(func=cmd_anvil_state)

    # smith-loop
    p = subparsers.add_parser("smith-loop", help="Complete smithing loop: fuel forge, heat, smith with reheat", parents=[global_parent])
    p.add_argument("--forge", nargs=3, metavar=("FX", "FY", "FZ"), required=True, type=float,
                   dest="forge_coords", help="Forge coordinates")
    p.add_argument("--anvil", nargs=3, metavar=("AX", "AY", "AZ"), required=True, type=float,
                   dest="anvil_coords", help="Anvil coordinates")
    p.add_argument("--recipe", required=True, help="Smithing recipe code (e.g., pickaxehead-copper)")
    p.add_argument("--fuel", default="game:charcoal", help="Fuel item code (default: game:charcoal)")
    p.add_argument("--fuel-qty", type=int, default=4, help="Fuel pieces to add (default: 4, each adds 1/16 level)")
    p.add_argument("--ingot", required=True, help="Ingot item code (e.g., game:ingot-copper)")
    p.add_argument("--max-reheats", type=int, default=3, help="Max reheat attempts (default: 3)")
    p.set_defaults(func=cmd_smith_loop)

    # takefrom - supports either coordinates or container name
    p = subparsers.add_parser("takefrom", help="Take items from container (x y z slot [qty] OR -c name slot [qty])", parents=[global_parent])
    p.add_argument("args", nargs="*", help="x y z slot [qty] OR slot [qty] (with -c)")
    p.add_argument("--container", "-c", help="Registered container name (use instead of x y z)")
    p.set_defaults(func=cmd_takefrom)

    # putinto - supports either coordinates or container name
    p = subparsers.add_parser("putinto", help="Put items into container (x y z slot [qty] OR -c name slot [qty])", parents=[global_parent])
    p.add_argument("args", nargs="*", help="x y z slot [qty] OR slot [qty] (with -c)")
    p.add_argument("--container", "-c", help="Registered container name (use instead of x y z)")
    p.set_defaults(func=cmd_putinto)

    # butcher
    p = subparsers.add_parser("butcher", help="Butcher a dead entity", parents=[global_parent])
    p.add_argument("id", type=int, help="Entity ID")
    p.add_argument("--no-autocollect", dest="autocollect", action="store_false", help="Don't auto-pickup drops")
    p.set_defaults(func=cmd_butcher)

    # loot
    p = subparsers.add_parser("loot", help="Loot items from dead entity inventory", parents=[global_parent])
    p.add_argument("id", type=int, help="Entity ID")
    p.set_defaults(func=cmd_loot)

    # interact
    p = subparsers.add_parser("interact", help="Interact with an entity (feed, shear, etc.)", parents=[global_parent])
    p.add_argument("id", type=int, help="Entity ID")
    p.add_argument("--mode", choices=["interact", "attack"], default="interact",
                   help="Interaction mode (default: interact)")
    p.add_argument("--no-wait", dest="wait", action="store_false", help="Don't wait for completion")
    p.set_defaults(func=cmd_interact)

    # possess
    p = subparsers.add_parser("possess", help="Mount player onto bot", parents=[global_parent])
    p.set_defaults(func=cmd_possess)

    # unpossess
    p = subparsers.add_parser("unpossess", help="Unmount player from bot", parents=[global_parent])
    p.set_defaults(func=cmd_unpossess)

    # controls
    p = subparsers.add_parser("controls", help="Set movement controls while possessing", parents=[global_parent])
    p.add_argument("--fwd", action="store_true", help="Move forward")
    p.add_argument("--back", action="store_true", help="Move backward")
    p.add_argument("--left", action="store_true", help="Strafe left")
    p.add_argument("--right", action="store_true", help="Strafe right")
    p.add_argument("--sprint", action="store_true", help="Sprint")
    p.add_argument("--jump", action="store_true", help="Jump")
    p.set_defaults(func=cmd_controls)

    # exec
    p = subparsers.add_parser("exec", help="Execute raw server command (local only)", parents=[global_parent])
    p.add_argument("cmd", help="Server command (e.g., '/time set 0')")
    p.set_defaults(func=cmd_exec)

    # spawnkill - spawn and immediately kill an entity (for butcher testing)
    p = subparsers.add_parser("spawnkill", help="Spawn entity and kill immediately (butcher prep)", parents=[global_parent])
    p.add_argument("entity", help="Entity code (e.g., game:sheep-bighorn-adult-male)")
    p.add_argument("coords", nargs="*", type=float, help="Optional: x y z coordinates (default: 1 block from bot)")
    p.set_defaults(func=cmd_spawnkill)

    # spawnentity - spawn a live entity
    p = subparsers.add_parser("spawnentity", help="Spawn a live entity", parents=[global_parent])
    p.add_argument("entity", help="Entity code (e.g., game:chicken-hen)")
    p.add_argument("coords", nargs="*", type=float, help="Optional: x y z coordinates (default: 1 block from bot)")
    p.set_defaults(func=cmd_spawnentity)

    # animate
    p = subparsers.add_parser("animate", help="Play or stop animations on selected bot", parents=[global_parent])
    p.add_argument("anim_args", nargs="*", help="Animation code, or 'stop [animCode]'")
    p.add_argument("--speed", "-s", type=float, help="Animation speed multiplier (default: 1.0)")
    p.add_argument("--loop", "-l", action="store_true", help="Loop animation until stopped")
    p.set_defaults(func=cmd_animate)

    # teleport
    p = subparsers.add_parser("teleport", help="Teleport player with optional view direction", parents=[global_parent])
    p.add_argument("x", type=float, help="X coordinate")
    p.add_argument("y", type=float, help="Y coordinate")
    p.add_argument("z", type=float, help="Z coordinate")
    p.add_argument("--yaw", help="View yaw: radians, cardinal (n/s/e/w/ne/nw/se/sw), or 'bot'")
    p.add_argument("--pitch", type=float, default=0.0, help="View pitch in radians (default: 0)")
    p.add_argument("--face", nargs=2, type=float, metavar=("X", "Z"),
                   help="Face coordinates (calculates yaw automatically)")
    p.add_argument("--face-bot", action="store_true", help="Face the selected bot")
    p.set_defaults(func=cmd_teleport)

    # screenshot
    p = subparsers.add_parser("screenshot", help="Capture screenshot from player view", parents=[global_parent])
    p.add_argument("--save", action="store_true", help="Save to file on client")
    p.set_defaults(func=cmd_screenshot)

    # setup-view
    p = subparsers.add_parser("setup-view", help="Position player to view selected bot", parents=[global_parent])
    p.add_argument("--distance", "-d", type=float, default=3.0, help="Distance from bot (default: 3.0)")
    p.add_argument("--screenshot", "-s", action="store_true", help="Take screenshot after positioning")
    p.add_argument("--save", action="store_true", help="Save screenshot to file (requires --screenshot)")
    p.set_defaults(func=cmd_setup_view)

    # scan - scan a region for blocks
    p = subparsers.add_parser("scan", help="Scan a region and return block data", parents=[global_parent])
    p.add_argument("from_coords", nargs=3, type=float, metavar=("X1", "Y1", "Z1"),
                   help="From corner coordinates")
    p.add_argument("to_coords", nargs=3, type=float, metavar=("X2", "Y2", "Z2"),
                   help="To corner coordinates")
    p.add_argument("--output", "-o", metavar="FILE", help="Save blocks to JSON file (blueprint format)")
    p.add_argument("--include-air", action="store_true", help="Include air blocks in output")
    p.add_argument("--relative", "-r", action="store_true",
                   help="Output positions relative to min corner (for blueprints)")
    p.add_argument("--filter", help="Filter results by code pattern (e.g., 'cobble', 'planks')")
    p.add_argument("--exclude-natural", action="store_true", dest="exclude_natural",
                   help="Exclude natural blocks (soil, stone, gravel, sand, clay, rock)")
    p.set_defaults(func=cmd_scan)

    # verify - verify a blueprint against world state
    p = subparsers.add_parser("verify", help="Verify a blueprint against world state", parents=[global_parent])
    p.add_argument("blueprint", help="Path to blueprint JSON file")
    p.add_argument("--origin", nargs=3, type=float, metavar=("X", "Y", "Z"),
                   help="Apply origin offset to blueprint positions")
    p.set_defaults(func=cmd_verify)

    # build - build from a blueprint
    p = subparsers.add_parser("build", help="Build from a blueprint with verification", parents=[global_parent])
    p.add_argument("blueprint", help="Path to blueprint JSON file")
    p.add_argument("--origin", nargs=3, type=float, metavar=("X", "Y", "Z"),
                   help="Apply origin offset to blueprint positions")
    p.add_argument("--no-verify", dest="verify", action="store_false",
                   help="Skip verification (faster but no progress tracking)")
    p.add_argument("--dry-run", action="store_true", help="Show what would be placed without placing")
    p.add_argument("--continue-on-error", action="store_true",
                   help="Continue building even if some blocks fail")
    p.set_defaults(func=cmd_build)

    # container-register - register a named container
    # zone-define - define a named zone
    p = subparsers.add_parser("zone-define", help="Define a named AABB zone", parents=[global_parent])
    p.add_argument("name", help="Zone name")
    p.add_argument("x1", type=int, help="First corner X")
    p.add_argument("y1", type=int, help="First corner Y")
    p.add_argument("z1", type=int, help="First corner Z")
    p.add_argument("x2", type=int, help="Second corner X")
    p.add_argument("y2", type=int, help="Second corner Y")
    p.add_argument("z2", type=int, help="Second corner Z")
    p.set_defaults(func=cmd_zone_define)

    # zone-remove - remove a named zone
    p = subparsers.add_parser("zone-remove", help="Remove a named zone", parents=[global_parent])
    p.add_argument("name", help="Zone name to remove")
    p.set_defaults(func=cmd_zone_remove)

    # zone-list - list all zones
    p = subparsers.add_parser("zone-list", help="List all named zones", parents=[global_parent])
    p.set_defaults(func=cmd_zone_list)

    # zone-check - check which zones bot is in
    p = subparsers.add_parser("zone-check", help="Check which zones a bot is in", parents=[global_parent])
    p.set_defaults(func=cmd_zone_check)

    # zone-show - highlight zone boundaries
    p = subparsers.add_parser("zone-show", help="Highlight a zone's boundaries", parents=[global_parent])
    p.add_argument("name", help="Zone name to highlight")
    p.set_defaults(func=cmd_zone_show)

    # viewpoint-define - define a named viewpoint
    p = subparsers.add_parser("viewpoint-define", help="Define a named viewpoint for observer screenshots", parents=[global_parent])
    p.add_argument("name", help="Viewpoint name")
    p.add_argument("x", type=float, help="Camera X coordinate")
    p.add_argument("y", type=float, help="Camera Y coordinate")
    p.add_argument("z", type=float, help="Camera Z coordinate")
    p.add_argument("yaw", type=float, help="Camera yaw in radians")
    p.add_argument("pitch", type=float, help="Camera pitch in radians")
    p.add_argument("--station", help="Optional linked station/zone name")
    p.set_defaults(func=cmd_viewpoint_define)

    # viewpoint-list - list all viewpoints
    p = subparsers.add_parser("viewpoint-list", help="List all named viewpoints", parents=[global_parent])
    p.set_defaults(func=cmd_viewpoint_list)

    # viewpoint-remove - remove a viewpoint
    p = subparsers.add_parser("viewpoint-remove", help="Remove a named viewpoint", parents=[global_parent])
    p.add_argument("name", help="Viewpoint name to remove")
    p.set_defaults(func=cmd_viewpoint_remove)

    # observer-screenshot - screenshot from arbitrary position
    p = subparsers.add_parser("observer-screenshot", help="Screenshot from arbitrary position (player restored after)", parents=[global_parent])
    p.add_argument("x", type=float, help="Camera X coordinate")
    p.add_argument("y", type=float, help="Camera Y coordinate")
    p.add_argument("z", type=float, help="Camera Z coordinate")
    p.add_argument("yaw", type=float, help="Camera yaw in radians")
    p.add_argument("pitch", type=float, help="Camera pitch in radians")
    p.add_argument("--save", action="store_true", help="Save screenshot to file")
    p.set_defaults(func=cmd_observer_screenshot)

    # viewpoint-screenshot - screenshot from named viewpoint
    p = subparsers.add_parser("viewpoint-screenshot", help="Screenshot from named viewpoint (player restored after)", parents=[global_parent])
    p.add_argument("name", help="Viewpoint name")
    p.add_argument("--save", action="store_true", help="Save screenshot to file")
    p.set_defaults(func=cmd_viewpoint_screenshot)

    p = subparsers.add_parser("container-register", help="Register a named container", parents=[global_parent])
    p.add_argument("name", help="Container name")
    p.add_argument("x", type=float, help="Container X coordinate")
    p.add_argument("y", type=float, help="Container Y coordinate")
    p.add_argument("z", type=float, help="Container Z coordinate")
    p.add_argument("--type", help="Container type (chest, vessel, barrel, crate)")
    p.add_argument("--desc", help="Optional description")
    p.set_defaults(func=cmd_container_register)

    # container-list - list registered containers
    p = subparsers.add_parser("container-list", help="List registered containers", parents=[global_parent])
    p.add_argument("--type", help="Filter by container type")
    p.set_defaults(func=cmd_container_list)

    # container-remove - remove a container from registry
    p = subparsers.add_parser("container-remove", help="Remove container from registry", parents=[global_parent])
    p.add_argument("name", help="Container name to remove")
    p.set_defaults(func=cmd_container_remove)

    # container-contents - get container contents
    p = subparsers.add_parser("container-contents", help="Get container contents", parents=[global_parent])
    p.add_argument("coords", nargs="*", type=float, metavar="X Y Z",
                   help="Container coordinates (x y z)")
    p.add_argument("--container", "-c", help="Registered container name")
    p.add_argument("--include-empty", action="store_true", help="Include empty slots in output")
    p.set_defaults(func=cmd_container_contents)

    # container-set - set container slot directly (no bot needed)
    p = subparsers.add_parser("container-set", help="Set container slot directly (x y z slot itemCode [qty])", parents=[global_parent])
    p.add_argument("args", nargs="*", help="x y z slot itemCode [qty]")
    p.set_defaults(func=cmd_container_set)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return EXIT_USAGE_ERROR

    # Create client and formatter
    client = HarnessClient(args.host, args.port)
    fmt = OutputFormatter(
        use_json=getattr(args, "use_json", False),
        quiet=args.quiet,
        verbose=args.verbose,
        show_tokens=getattr(args, "tokens", False)
    )

    # Test connectivity
    try:
        client.get("/polis")
    except ConnectionError as exc:
        print(f"Error: Cannot connect to harness at {client.base_url}: {exc}", file=sys.stderr)
        return EXIT_CONNECTION_ERROR

    # Execute command
    try:
        return args.func(client, args, fmt)
    except ConnectionError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_CONNECTION_ERROR
    except Exception as exc:
        if args.verbose:
            import traceback
            traceback.print_exc()
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_COMMAND_FAILED


if __name__ == "__main__":
    sys.exit(main())
