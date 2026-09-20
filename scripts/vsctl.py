#!/usr/bin/env python3
"""
vsctl - Vintage Story process controller for agentic development loop.

Controls the VS game lifecycle for automated testing:
  - start: Launch VS with test-lands world
  - stop: Clean shutdown (server /stop → kill client)
  - restart: stop + start + wait
  - wait: Poll until world is ready
  - status: Check if running and ready
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

# Exit codes
EXIT_SUCCESS = 0
EXIT_ERROR = 1
EXIT_TIMEOUT = 2

# Defaults
DEFAULT_WORLD = "polis-testbed"
DEFAULT_HARNESS_URL = "http://localhost:8585"
DEFAULT_WAIT_TIMEOUT = 180  # seconds (game can take 2+ mins to load)
DEFAULT_STOP_TIMEOUT = 30   # seconds
DEFAULT_POST_READY_DELAY = 5  # seconds after client ready signal
FLATPAK_APP_ID = "at.vintagestory.VintageStory"

# Paths for WAL flush verification
SCRIPT_DIR = Path(__file__).parent.resolve()
PROJECT_DIR = SCRIPT_DIR.parent
SAVES_DIR = PROJECT_DIR / "refs" / "vsdata" / "Saves"

# Window positioning defaults (for --window option)
# These are machine-specific - override via env vars or CLI args
DEFAULT_WINDOW_SIZE = (1290, 756)  # width, height
DEFAULT_WINDOW_CORNER = "br"  # bottom-right: br, bl, tr, tl, center
DEFAULT_PANEL_HEIGHT = 44  # Desktop panel/taskbar height (Cinnamon default)
VS_WINDOW_TITLE = "Vintage Story"

# Environment variable overrides for window settings
# VSCTL_WINDOW_SIZE="1290x756"
# VSCTL_WINDOW_CORNER="br"
# VSCTL_PANEL_HEIGHT="44"

# Paths
DATA_DIR_DEFAULT = os.path.expanduser(
    "~/.var/app/at.vintagestory.VintageStory/config/VintagestoryData"
)
LOG_DIR_DEFAULT = os.path.join(DATA_DIR_DEFAULT, "Logs")
CLIENT_LOG_PATH = os.path.join(LOG_DIR_DEFAULT, "client-main.log")

# Client ready signal - emitted by polis mod when rendering starts
CLIENT_READY_SIGNAL = "[polis] OnRenderFrame: Handler registered and called!"


def log(msg: str, verbose: bool = True):
    """Print status message."""
    if verbose:
        print(f"[vsctl] {msg}")


def harness_request(path: str, method: str = "GET", data: dict = None, timeout: float = 5.0) -> dict:
    """Make HTTP request to harness."""
    url = f"{DEFAULT_HARNESS_URL}{path}"
    headers = {"Content-Type": "application/json"} if data else {}
    body = json.dumps(data).encode() if data else None

    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.URLError:
        return None
    except json.JSONDecodeError:
        return {}


def is_harness_ready() -> bool:
    """Check if harness is running and world is ready."""
    result = harness_request("/polis/status")
    if result is None:
        return False
    return result.get("server", {}).get("worldReady", False)


def is_harness_reachable() -> bool:
    """Check if harness HTTP server is reachable (even if world not ready)."""
    result = harness_request("/polis")
    return result is not None


def is_vs_running() -> bool:
    """Check if Vintage Story process is running."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "Vintagestory"],
            capture_output=True,
            text=True
        )
        return result.returncode == 0
    except Exception:
        return False


def get_active_world_path() -> Optional[Path]:
    """Find the active world by checking for SQLite WAL files.

    Returns the world with the most recently modified WAL file,
    as that's most likely the currently active world.
    """
    if not SAVES_DIR.exists():
        return None

    candidates = []
    for wal_file in SAVES_DIR.glob("*.vcdbs-wal"):
        # foo.vcdbs-wal -> foo.vcdbs (strip last 4 chars)
        db_file = Path(str(wal_file)[:-4])
        if db_file.exists():
            mtime = wal_file.stat().st_mtime
            candidates.append((mtime, db_file))

    if not candidates:
        return None

    # Return the world with the most recently modified WAL
    candidates.sort(reverse=True)
    return candidates[0][1]


def is_wal_flushed(world_path: Path, timeout: float = 15.0) -> bool:
    """Wait for SQLite WAL file to be flushed (deleted or zeroed)."""
    wal_path = Path(str(world_path) + "-wal")
    shm_path = Path(str(world_path) + "-shm")

    deadline = time.time() + timeout
    while time.time() < deadline:
        # WAL is flushed when file doesn't exist or is empty/minimal
        wal_gone = not wal_path.exists() or wal_path.stat().st_size < 1024
        shm_gone = not shm_path.exists() or shm_path.stat().st_size < 1024
        if wal_gone and shm_gone:
            return True
        time.sleep(0.5)
    return False


def get_log_line_count(log_path: str) -> int:
    """Get current line count of a log file."""
    try:
        with open(log_path, 'rb') as f:
            return sum(1 for _ in f)
    except (FileNotFoundError, IOError):
        return 0


def get_screen_size() -> tuple:
    """Get primary screen dimensions using xrandr."""
    try:
        result = subprocess.run(
            ["xrandr", "--query"],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.split('\n'):
            if ' connected primary ' in line:
                # Format: "eDP connected primary 2580x1720+0+0 ..."
                parts = line.split()
                for part in parts:
                    if 'x' in part and '+' in part:
                        res = part.split('+')[0]
                        w, h = res.split('x')
                        return (int(w), int(h))
    except Exception:
        pass
    return (1920, 1080)  # fallback


def position_window(width: int, height: int, corner: str, panel_height: int = None, verbose: bool = True) -> bool:
    """Position VS window using wmctrl.

    Args:
        width, height: Window dimensions
        corner: Position - 'br' (bottom-right), 'bl', 'tr', 'tl', or 'center'
        panel_height: Desktop panel/taskbar height in pixels (machine-specific)
        verbose: Print status messages

    Returns:
        True if successful, False otherwise

    Note: Window positioning is machine-specific. Configure via:
        - CLI: --panel-height 44
        - Env: VSCTL_PANEL_HEIGHT=44
    """
    # Check if wmctrl is available
    if subprocess.run(["which", "wmctrl"], capture_output=True).returncode != 0:
        log("wmctrl not found, skipping window positioning", verbose)
        return False

    # Wait for window to appear (with retries)
    max_retries = 20
    for i in range(max_retries):
        result = subprocess.run(
            ["wmctrl", "-l"],
            capture_output=True, text=True
        )
        if VS_WINDOW_TITLE in result.stdout:
            break
        time.sleep(0.5)
    else:
        log(f"Window '{VS_WINDOW_TITLE}' not found after {max_retries * 0.5}s", verbose)
        return False

    # Get screen size
    screen_w, screen_h = get_screen_size()

    # Get panel height from env var or default
    if panel_height is None:
        panel_height = int(os.environ.get("VSCTL_PANEL_HEIGHT", DEFAULT_PANEL_HEIGHT))

    if corner == "br":  # bottom-right
        x = screen_w - width
        y = screen_h - height - panel_height
    elif corner == "bl":  # bottom-left
        x = 0
        y = screen_h - height - panel_height
    elif corner == "tr":  # top-right
        x = screen_w - width
        y = 0
    elif corner == "tl":  # top-left
        x = 0
        y = 0
    elif corner == "center":
        x = (screen_w - width) // 2
        y = (screen_h - height - panel_height) // 2
    else:
        log(f"Unknown corner '{corner}', using bottom-right", verbose)
        x = screen_w - width
        y = screen_h - height - panel_height

    # Remove maximized state first
    subprocess.run([
        "wmctrl", "-r", VS_WINDOW_TITLE,
        "-b", "remove,maximized_vert,maximized_horz"
    ], capture_output=True)
    time.sleep(0.2)

    # Resize and move: -e gravity,x,y,width,height (gravity 0 = use default)
    result = subprocess.run([
        "wmctrl", "-r", VS_WINDOW_TITLE,
        "-e", f"0,{x},{y},{width},{height}"
    ], capture_output=True)

    if result.returncode == 0:
        log(f"Window positioned: {width}x{height} at ({x},{y}) [{corner}]", verbose)
        return True
    else:
        log(f"Failed to position window: {result.stderr.decode()}", verbose)
        return False


def check_client_ready_signal(log_path: str, start_line: int) -> bool:
    """Check if client ready signal appeared in log since start_line.

    Searches for: [polis] OnRenderFrame: Handler registered and called!
    This signal fires when the client transitions from loading screen to rendering.
    """
    try:
        with open(log_path, 'rb') as f:
            for i, line in enumerate(f):
                if i < start_line:
                    continue
                # Handle binary log file
                try:
                    line_str = line.decode('utf-8', errors='ignore')
                    if CLIENT_READY_SIGNAL in line_str:
                        return True
                except Exception:
                    continue
        return False
    except (FileNotFoundError, IOError):
        return False


def cmd_status(args) -> int:
    """Show current status."""
    process_running = is_vs_running()
    harness_reachable = is_harness_reachable()
    world_ready = is_harness_ready() if harness_reachable else False

    # Check if client log has ready signal (check last 1000 lines)
    log_lines = get_log_line_count(CLIENT_LOG_PATH)
    start_line = max(0, log_lines - 1000)
    client_ready = check_client_ready_signal(CLIENT_LOG_PATH, start_line) if process_running else False

    print(f"process_running: {process_running}")
    print(f"harness_reachable: {harness_reachable}")
    print(f"world_ready: {world_ready}")
    print(f"client_ready: {client_ready}")

    if world_ready:
        result = harness_request("/polis/status")
        if result:
            print(f"run_phase: {result.get('server', {}).get('runPhase', 'unknown')}")
            print(f"mod_version: {result.get('modVersion', 'unknown')}")

    return EXIT_SUCCESS


def cmd_start(args) -> int:
    """Start Vintage Story with test world."""
    if is_vs_running():
        log("VS already running", args.verbose)
        # Still try to position window if requested
        if getattr(args, 'window', False):
            _apply_window_positioning(args)
        if args.wait:
            return cmd_wait(args)
        return EXIT_SUCCESS

    world = args.world or DEFAULT_WORLD
    log(f"Starting VS with world '{world}'...", args.verbose)

    cmd = ["flatpak", "run", FLATPAK_APP_ID, "--openWorld", world]

    try:
        # Start in background
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
        log("VS process launched", args.verbose)

        # Position window if requested (needs window to appear first)
        if getattr(args, 'window', False):
            log("Waiting for window to appear...", args.verbose)
            time.sleep(3)  # Give window time to appear
            _apply_window_positioning(args)

        if args.wait:
            # Give process time to spawn before checking
            if not getattr(args, 'window', False):
                time.sleep(3)
            return cmd_wait(args)

        return EXIT_SUCCESS
    except Exception as e:
        log(f"Failed to start VS: {e}", args.verbose)
        return EXIT_ERROR


def _apply_window_positioning(args) -> bool:
    """Apply window positioning based on args."""
    # Get size from args or env or default
    if hasattr(args, 'window_size') and args.window_size:
        try:
            w, h = args.window_size.lower().split('x')
            width, height = int(w), int(h)
        except ValueError:
            log(f"Invalid window size '{args.window_size}', using default", args.verbose)
            width, height = DEFAULT_WINDOW_SIZE
    else:
        env_size = os.environ.get("VSCTL_WINDOW_SIZE", "")
        if env_size and 'x' in env_size:
            try:
                w, h = env_size.lower().split('x')
                width, height = int(w), int(h)
            except ValueError:
                width, height = DEFAULT_WINDOW_SIZE
        else:
            width, height = DEFAULT_WINDOW_SIZE

    # Get corner from args or env or default
    corner = getattr(args, 'window_corner', None)
    if not corner:
        corner = os.environ.get("VSCTL_WINDOW_CORNER", DEFAULT_WINDOW_CORNER)

    # Get panel height from args or env or default
    panel_height = getattr(args, 'panel_height', None)
    if panel_height is None:
        panel_height = int(os.environ.get("VSCTL_PANEL_HEIGHT", DEFAULT_PANEL_HEIGHT))

    return position_window(width, height, corner, panel_height, args.verbose)


def cmd_stop(args) -> int:
    """Stop Vintage Story cleanly."""
    if not is_vs_running():
        log("VS not running", args.verbose)
        return EXIT_SUCCESS

    # Try clean shutdown via harness first
    if is_harness_reachable():
        log("Sending /stop to server...", args.verbose)
        try:
            # This will likely timeout as server shuts down
            harness_request("/polis/servercmd", method="POST", data={"cmd": "/stop"}, timeout=10.0)
        except Exception:
            pass  # Expected - server dies mid-request

        # Wait for harness to become unreachable
        log("Waiting for server to stop...", args.verbose)
        deadline = time.time() + args.stop_timeout
        while time.time() < deadline:
            if not is_harness_reachable():
                log("Server stopped", args.verbose)
                break
            time.sleep(0.5)

    # Verify world save is flushed before killing client
    world_path = get_active_world_path()
    if world_path:
        log(f"Waiting for {world_path.name} to flush...", args.verbose)
        if is_wal_flushed(world_path, timeout=15.0):
            log("World save flushed", args.verbose)
        else:
            log("WARNING: WAL not flushed after 15s, proceeding anyway", args.verbose)

    # Kill the client process
    if is_vs_running():
        log("Killing VS client...", args.verbose)
        try:
            subprocess.run(
                ["flatpak", "kill", FLATPAK_APP_ID],
                capture_output=True,
                timeout=10
            )
        except subprocess.TimeoutExpired:
            log("flatpak kill timed out, using pkill", args.verbose)
            subprocess.run(["pkill", "-f", "Vintagestory"], capture_output=True)

        # Verify stopped
        time.sleep(1)
        if is_vs_running():
            log("Warning: VS still running after kill", args.verbose)
            return EXIT_ERROR

    log("VS stopped", args.verbose)
    return EXIT_SUCCESS


def cmd_wait(args) -> int:
    """Wait for game to be fully ready (server + client rendering).

    Three stages:
    1. Wait for server worldReady=true (harness reports ready)
    2. Wait for client ready signal in log (rendering started)
    3. Wait post-ready delay for final settling
    """
    post_delay = getattr(args, 'post_ready_delay', DEFAULT_POST_READY_DELAY)
    log(f"Waiting for game ready (timeout: {args.timeout}s, post-delay: {post_delay}s)...", args.verbose)

    deadline = time.time() + args.timeout
    last_status = None

    # Record log position before we start (to detect new signals)
    log_start_line = get_log_line_count(CLIENT_LOG_PATH)

    # Stage 1: Wait for server ready (worldReady=true)
    server_ready = False
    while time.time() < deadline and not server_ready:
        if is_harness_ready():
            log("Server ready (worldReady=true)", args.verbose)
            server_ready = True
            break

        # Show progress
        if is_harness_reachable():
            result = harness_request("/polis/status")
            if result:
                status = result.get("server", {}).get("runPhase", "unknown")
                if status != last_status:
                    log(f"Run phase: {status}", args.verbose)
                    last_status = status
        elif is_vs_running():
            if last_status != "starting":
                log("VS starting, waiting for harness...", args.verbose)
                last_status = "starting"
        else:
            log("VS not running", args.verbose)
            return EXIT_ERROR

        time.sleep(1)

    if not server_ready:
        log(f"Timeout waiting for server ready after {args.timeout}s", args.verbose)
        return EXIT_TIMEOUT

    # Stage 2: Wait for client ready signal in log
    log("Waiting for client ready signal...", args.verbose)
    client_ready = False
    while time.time() < deadline and not client_ready:
        if check_client_ready_signal(CLIENT_LOG_PATH, log_start_line):
            log("Client ready (render handler registered)", args.verbose)
            client_ready = True
            break

        if not is_vs_running():
            log("VS process died while waiting for client ready", args.verbose)
            return EXIT_ERROR

        time.sleep(0.5)

    if not client_ready:
        log(f"Timeout waiting for client ready signal after {args.timeout}s", args.verbose)
        return EXIT_TIMEOUT

    # Stage 3: Post-ready delay for final settling
    if post_delay > 0:
        log(f"Waiting {post_delay}s for final settling...", args.verbose)
        time.sleep(post_delay)

    log("Game fully ready!", args.verbose)
    return EXIT_SUCCESS


def cmd_restart(args) -> int:
    """Restart VS (stop + start + wait)."""
    log("Restarting VS...", args.verbose)

    result = cmd_stop(args)
    if result != EXIT_SUCCESS:
        return result

    # Brief pause between stop and start
    time.sleep(2)

    args.wait = True  # Always wait after restart
    return cmd_start(args)


def main():
    parser = argparse.ArgumentParser(
        prog="vsctl",
        description="Vintage Story process controller for agentic development",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  vsctl status              # Check if VS is running and world ready
  vsctl start               # Start VS with test-lands world
  vsctl start --wait        # Start and wait for game fully ready
  vsctl start --window      # Start with window positioned (bottom-right)
  vsctl start --wait --window --window-size 1290x756
  vsctl stop                # Clean shutdown (saves world)
  vsctl restart             # Stop, start, and wait for ready
  vsctl restart --window    # Restart with window positioning
  vsctl wait                # Wait for game to become fully ready
  vsctl wait --timeout 180  # Wait with custom timeout
  vsctl wait -d 10          # Wait with 10s post-ready delay

Ready detection stages:
  1. Server ready: harness reports worldReady=true
  2. Client ready: polis render handler signal in client log
  3. Post-delay: configurable settling time (default 5s)

Window positioning (--window):
  Uses wmctrl to resize and position window after launch.
  Machine-specific settings can be set via environment variables:
    VSCTL_WINDOW_SIZE=1290x756    # Window dimensions
    VSCTL_WINDOW_CORNER=br        # br=bottom-right, tl=top-left, etc.
    VSCTL_PANEL_HEIGHT=44         # Desktop taskbar height in pixels
"""
    )

    parser.add_argument("-v", "--verbose", action="store_true", default=True,
                        help="Verbose output (default: true)")
    parser.add_argument("-q", "--quiet", action="store_true",
                        help="Suppress status messages")

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # status
    p = subparsers.add_parser("status", help="Show current status")
    p.set_defaults(func=cmd_status)

    # start
    p = subparsers.add_parser("start", help="Start VS with test world")
    p.add_argument("--world", "-w", default=DEFAULT_WORLD,
                   help=f"World name (default: {DEFAULT_WORLD})")
    p.add_argument("--wait", action="store_true",
                   help="Wait for world ready after start")
    p.add_argument("--timeout", "-t", type=int, default=DEFAULT_WAIT_TIMEOUT,
                   help=f"Wait timeout in seconds (default: {DEFAULT_WAIT_TIMEOUT})")
    p.add_argument("--post-ready-delay", "-d", type=int, default=DEFAULT_POST_READY_DELAY,
                   help=f"Delay after client ready signal (default: {DEFAULT_POST_READY_DELAY})")
    # Window positioning (machine-specific, use env vars for defaults)
    p.add_argument("--window", action="store_true",
                   help="Position window after launch (uses wmctrl)")
    p.add_argument("--window-size", metavar="WxH",
                   help=f"Window size (default: {DEFAULT_WINDOW_SIZE[0]}x{DEFAULT_WINDOW_SIZE[1]}, env: VSCTL_WINDOW_SIZE)")
    p.add_argument("--window-corner", choices=["br", "bl", "tr", "tl", "center"],
                   help=f"Window corner (default: {DEFAULT_WINDOW_CORNER}, env: VSCTL_WINDOW_CORNER)")
    p.add_argument("--panel-height", type=int,
                   help=f"Desktop panel height in px (default: {DEFAULT_PANEL_HEIGHT}, env: VSCTL_PANEL_HEIGHT)")
    p.set_defaults(func=cmd_start)

    # stop
    p = subparsers.add_parser("stop", help="Stop VS cleanly")
    p.add_argument("--stop-timeout", type=int, default=DEFAULT_STOP_TIMEOUT,
                   help=f"Server stop timeout (default: {DEFAULT_STOP_TIMEOUT})")
    p.set_defaults(func=cmd_stop)

    # wait
    p = subparsers.add_parser("wait", help="Wait for game fully ready")
    p.add_argument("--timeout", "-t", type=int, default=DEFAULT_WAIT_TIMEOUT,
                   help=f"Timeout in seconds (default: {DEFAULT_WAIT_TIMEOUT})")
    p.add_argument("--post-ready-delay", "-d", type=int, default=DEFAULT_POST_READY_DELAY,
                   help=f"Delay after client ready signal (default: {DEFAULT_POST_READY_DELAY})")
    p.set_defaults(func=cmd_wait)

    # restart
    p = subparsers.add_parser("restart", help="Restart VS (stop + start + wait)")
    p.add_argument("--world", "-w", default=DEFAULT_WORLD,
                   help=f"World name (default: {DEFAULT_WORLD})")
    p.add_argument("--timeout", "-t", type=int, default=DEFAULT_WAIT_TIMEOUT,
                   help=f"Wait timeout in seconds (default: {DEFAULT_WAIT_TIMEOUT})")
    p.add_argument("--stop-timeout", type=int, default=DEFAULT_STOP_TIMEOUT,
                   help=f"Server stop timeout (default: {DEFAULT_STOP_TIMEOUT})")
    p.add_argument("--post-ready-delay", "-d", type=int, default=DEFAULT_POST_READY_DELAY,
                   help=f"Delay after client ready signal (default: {DEFAULT_POST_READY_DELAY})")
    # Window positioning (same as start)
    p.add_argument("--window", action="store_true",
                   help="Position window after launch (uses wmctrl)")
    p.add_argument("--window-size", metavar="WxH",
                   help=f"Window size (default: {DEFAULT_WINDOW_SIZE[0]}x{DEFAULT_WINDOW_SIZE[1]})")
    p.add_argument("--window-corner", choices=["br", "bl", "tr", "tl", "center"],
                   help=f"Window corner (default: {DEFAULT_WINDOW_CORNER})")
    p.add_argument("--panel-height", type=int,
                   help=f"Desktop panel height in px (default: {DEFAULT_PANEL_HEIGHT})")
    p.set_defaults(func=cmd_restart)

    args = parser.parse_args()

    if args.quiet:
        args.verbose = False

    if not args.command:
        parser.print_help()
        return EXIT_ERROR

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
