#!/usr/bin/env python3
"""
Polis Test Runner - Executes JSON test manifests against polis-testbed.

Supports:
- Zone compliance checking (fail/warn/ignore)
- Screenshot-on-failure
- CI-friendly JSON reporting
"""
import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

# Import from poliscli
script_dir = Path(__file__).parent
sys.path.insert(0, str(script_dir))

from poliscli import (
    HarnessClient,
    OutputFormatter,
    send_command,
    wait_for_action_result,
    get_bot_id,
    get_player_uid,
    build_context,
    EXIT_SUCCESS,
    EXIT_COMMAND_FAILED,
    EXIT_USAGE_ERROR,
    EXIT_CONNECTION_ERROR,
)

# Exit codes
EXIT_TEST_FAILED = 1
EXIT_RUNNER_ERROR = 2

# Default paths
MANIFESTS_DIR = Path(__file__).parent.parent / "tests" / "world" / "manifests"

# Colors for terminal output
class Colors:
    PASS = "\033[92m"  # Green
    FAIL = "\033[91m"  # Red
    WARN = "\033[93m"  # Yellow
    INFO = "\033[94m"  # Blue
    RESET = "\033[0m"
    BOLD = "\033[1m"

    @classmethod
    def disable(cls):
        cls.PASS = cls.FAIL = cls.WARN = cls.INFO = cls.RESET = cls.BOLD = ""


# ============================================================================
# Result Data Classes
# ============================================================================

@dataclass
class AssertionResult:
    name: str
    expected: any
    actual: any = None
    passed: bool = False
    error: Optional[str] = None


@dataclass
class StepResult:
    name: str
    status: str  # "pass", "fail", "skip"
    duration: float = 0.0
    error: Optional[str] = None
    assertions: list = field(default_factory=list)
    screenshot: Optional[str] = None


@dataclass
class StationResult:
    name: str
    status: str  # "pass", "fail", "skip"
    steps: list = field(default_factory=list)
    zone_violations: int = 0
    duration: float = 0.0
    error: Optional[str] = None


@dataclass
class TestReport:
    summary: dict = field(default_factory=dict)
    stations: list = field(default_factory=list)
    started_at: str = ""
    finished_at: str = ""


# ============================================================================
# Test Runner
# ============================================================================

class TestRunner:
    """Executes test manifests against the polis harness."""

    def __init__(self, client: HarnessClient, args):
        self.client = client
        self.args = args
        self.verbose = args.verbose
        self.fail_fast = args.fail_fast
        self.screenshot_on_failure = args.screenshot_on_failure
        self.fmt = OutputFormatter(use_json=False, quiet=True, verbose=args.verbose)

        # Create args-like object for poliscli compatibility
        self._bot_id = None
        self._player_uid = None
        self._current_camera = None  # Store camera from manifest for failure screenshots

    def log(self, msg: str, level: str = "info"):
        """Log a message."""
        if level == "debug" and not self.verbose:
            return
        prefix = {
            "debug": f"{Colors.INFO}[DEBUG]{Colors.RESET}",
            "info": f"{Colors.INFO}[INFO]{Colors.RESET}",
            "pass": f"{Colors.PASS}[PASS]{Colors.RESET}",
            "fail": f"{Colors.FAIL}[FAIL]{Colors.RESET}",
            "warn": f"{Colors.WARN}[WARN]{Colors.RESET}",
        }.get(level, "[???]")
        print(f"{prefix} {msg}", file=sys.stderr)

    def run_manifest(self, path: Path) -> StationResult:
        """Execute a single manifest and return results."""
        start_time = time.time()
        station_name = path.stem

        try:
            with open(path) as f:
                manifest = json.load(f)
        except Exception as e:
            return StationResult(
                name=station_name,
                status="fail",
                error=f"Failed to load manifest: {e}",
                duration=time.time() - start_time
            )

        station_name = manifest.get("station", station_name)
        zone_name = manifest.get("zone")
        zone_mode = manifest.get("zoneViolation", "warn")
        description = manifest.get("description", "")

        self.log(f"Station: {Colors.BOLD}{station_name}{Colors.RESET} - {description}", "info")

        result = StationResult(name=station_name, status="pass")

        # Run setup
        setup = manifest.get("setup", {})
        if setup:
            setup_error = self._run_setup(setup)
            if setup_error:
                result.status = "fail"
                result.error = f"Setup failed: {setup_error}"
                result.duration = time.time() - start_time
                return result

        # Run steps
        steps = manifest.get("steps", [])
        for i, step in enumerate(steps):
            step_name = step.get("name", f"step-{i+1}")
            self.log(f"  Step {i+1}/{len(steps)}: {step_name}", "debug")

            step_result = self._run_step(step, zone_name, zone_mode)
            result.steps.append(step_result)

            if step_result.status == "fail":
                result.status = "fail"
                self.log(f"  Step '{step_name}': {Colors.FAIL}FAIL{Colors.RESET} - {step_result.error}", "fail")

                if self.screenshot_on_failure:
                    screenshot_path = self._capture_failure_screenshot(station_name, step_name)
                    if screenshot_path:
                        step_result.screenshot = screenshot_path
                        self.log(f"    Screenshot saved: {screenshot_path}", "info")

                if self.fail_fast:
                    break
            else:
                self.log(f"  Step '{step_name}': {Colors.PASS}PASS{Colors.RESET}", "pass")

        # Count zone violations
        result.zone_violations = sum(
            1 for s in result.steps
            if any(a.name == "zoneContains" and not a.passed for a in s.assertions)
        )

        result.duration = time.time() - start_time
        return result

    def _run_setup(self, setup: dict) -> Optional[str]:
        """Run setup phase. Returns error string if failed, None if success."""
        # Teleport bot if position specified
        bot_pos = setup.get("botPosition")
        if bot_pos and len(bot_pos) == 3:
            result = self._send_command("goto", [str(c) for c in bot_pos])
            # goto returns {arrived, position} (no Ok field); other commands return Ok
            if not result.get("Ok") and result.get("arrived") is not True:
                return f"Failed to move bot to {bot_pos}: {result.get('Message', 'unknown')}"

            # Wait for arrival
            self.log(f"  Moving bot to {bot_pos}...", "debug")
            timeout = setup.get("gotoTimeout", 15)
            if not self._wait_for_arrival(bot_pos, timeout):
                return f"Bot did not arrive at {bot_pos} within {timeout}s"

        # Set camera position
        camera = setup.get("camera")
        if camera:
            cam_pos = camera.get("position", [])
            yaw = camera.get("yaw", 0)
            pitch = camera.get("pitch", 0)
            if len(cam_pos) == 3:
                player_uid = self._get_player_uid()
                if player_uid:
                    cmd_args = [player_uid, str(cam_pos[0]), str(cam_pos[1]), str(cam_pos[2]), str(yaw), str(pitch)]
                    result = self._send_command("teleport", cmd_args)
                    if not result.get("Ok"):
                        self.log(f"  Warning: Failed to position camera: {result.get('Message')}", "warn")
                    else:
                        # Store camera for failure screenshots
                        self._current_camera = camera
                        time.sleep(0.3)  # Allow render to settle

        # Give items
        give_items = setup.get("giveItems", [])
        for item in give_items:
            if isinstance(item, str):
                code, qty = item, 1
            else:
                code = item.get("code", item.get("item"))
                qty = item.get("qty", 1)

            result = self._send_command("give", [code, str(qty)])
            if not result.get("Ok"):
                return f"Failed to give item {code}: {result.get('Message', 'unknown')}"

        # Equip item in right hand
        equip = setup.get("equipRightHand")
        if equip:
            result = self._send_command("equip", [equip])
            if not result.get("Ok"):
                self.log(f"  Warning: Failed to equip {equip}: {result.get('Message')}", "warn")

        return None

    def _run_step(self, step: dict, zone_name: str, zone_mode: str) -> StepResult:
        """Execute a single test step."""
        start_time = time.time()
        step_name = step.get("name", "unnamed")
        action = step.get("action")
        args = step.get("args", {})
        timeout = step.get("timeout", 30)
        expect = step.get("expect", {})

        result = StepResult(name=step_name, status="pass")

        # Build command args
        cmd_args = self._build_cmd_args(action, args)

        # Send command
        cmd_result = self._send_command(action, cmd_args)

        if not cmd_result.get("Ok"):
            # Some actions may fail intentionally, check expectations
            pass

        # Wait for action completion if needed
        if action in ("mine", "harvest", "harvestcrop", "grind", "press", "forge-heat", "anvil-smith", "knap", "clayform", "seal"):
            ok, msg = self._wait_for_action(action, timeout)
            if not ok and expect.get("lastActionOk", True):
                result.status = "fail"
                result.error = f"Action '{action}' failed: {msg}"
                result.duration = time.time() - start_time
                return result

        # Brief pause for state to settle
        time.sleep(0.1)

        # Verify expectations
        for assert_name, assert_value in expect.items():
            assertion = self._verify_assertion(assert_name, assert_value, args)
            result.assertions.append(assertion)

            if not assertion.passed:
                result.status = "fail"
                result.error = f"Assertion '{assert_name}' failed: expected {assertion.expected}, got {assertion.actual}"
                if assertion.error:
                    result.error += f" ({assertion.error})"

        # Check zone compliance
        if zone_name and zone_mode != "ignore":
            zone_assertion = self._check_zone(zone_name)
            result.assertions.append(zone_assertion)

            if not zone_assertion.passed:
                if zone_mode == "fail":
                    result.status = "fail"
                    result.error = f"Zone violation: bot not in '{zone_name}'"
                else:
                    self.log(f"    Zone warning: bot not in '{zone_name}'", "warn")

        result.duration = time.time() - start_time
        return result

    def _build_cmd_args(self, action: str, args: dict) -> list:
        """Build command arguments from action and args dict."""
        cmd_args = []

        # Handle common coordinate patterns
        if "x" in args and "y" in args and "z" in args:
            cmd_args.extend([str(args["x"]), str(args["y"]), str(args["z"])])

        # Handle specific actions
        if action == "place":
            block_code = args.get("blockCode", args.get("code", ""))
            if block_code:
                cmd_args.insert(0, block_code)

        elif action == "give":
            item_code = args.get("itemCode", args.get("code", ""))
            qty = args.get("qty", 1)
            cmd_args = [item_code, str(qty)]

        elif action == "drop":
            item_code = args.get("itemCode", args.get("code", ""))
            qty = args.get("qty", 1)
            cmd_args = [item_code, str(qty)]

        elif action == "pickup":
            entity_id = args.get("entityId")
            if entity_id:
                cmd_args = [str(entity_id)]
            # If no entity ID, pickup is positional

        elif action in ("putinto", "takefrom"):
            slot = args.get("slot", 0)
            item_code = args.get("itemCode", args.get("code", ""))
            qty = args.get("qty", 1)
            # cmd format: x y z slot [itemCode] [qty]
            cmd_args.extend([str(slot)])
            if item_code:
                cmd_args.append(item_code)
                cmd_args.append(str(qty))

        elif action == "activate":
            # Just coordinates, already handled
            pass

        elif action in ("harvest", "harvestcrop", "mine", "break"):
            # Just coordinates, already handled
            pass

        return cmd_args

    def _send_command(self, cmd: str, cmd_args: list) -> dict:
        """Send a command to the harness."""
        context = {"playerUid": self._get_player_uid()}
        bot_id = self._get_bot_id()
        if bot_id:
            try:
                context["botId"] = int(bot_id)  # harness expects a number
            except (TypeError, ValueError):
                context["botId"] = bot_id

        payload = {"cmd": cmd, "args": cmd_args}
        if context:
            payload["context"] = context

        self.log(f"    Command: {cmd} {cmd_args}", "debug")
        return self.client.post("/polis/command", payload)

    def _wait_for_action(self, action_name: str, timeout: int = 60) -> tuple:
        """Wait for action to complete. Returns (ok, message)."""
        deadline = time.time() + timeout
        bot_id = self._get_bot_id()
        params = {"botId": bot_id} if bot_id else {}

        while time.time() < deadline:
            result = self.client.get("/polis/state", params if params else None)
            last_action = result.get("LastAction") or {}
            if last_action.get("Name") == action_name:
                msg = last_action.get("Msg", "")
                ok = last_action.get("Ok", False)
                return ok, msg
            time.sleep(0.5)

        return False, "timeout"

    def _wait_for_arrival(self, target: list, timeout: int = 15) -> bool:
        """Wait for bot to arrive at target position."""
        import math
        threshold = 1.5
        deadline = time.time() + timeout
        bot_id = self._get_bot_id()
        params = {"botId": bot_id} if bot_id else {}

        while time.time() < deadline:
            result = self.client.get("/polis/state", params if params else None)
            bot = result.get("Bot", {})
            pos = bot.get("Pos", [0, 0, 0])

            dist = math.sqrt(sum((a - b) ** 2 for a, b in zip(pos, target)))
            if dist <= threshold:
                return True
            time.sleep(0.3)

        return False

    # ========================================================================
    # Assertion Verifiers
    # ========================================================================

    def _verify_assertion(self, name: str, value: any, step_args: dict = None) -> AssertionResult:
        """Verify a single assertion."""
        if name == "lastActionOk":
            return self._assert_last_action_ok(value)
        elif name == "blockGone":
            return self._assert_block_gone(value)
        elif name == "blockPresent":
            return self._assert_block_present(value, step_args)
        elif name == "inventoryContains":
            return self._assert_inventory_contains(value)
        elif name == "inventoryNotContains":
            return self._assert_inventory_not_contains(value)
        elif name == "containerContains":
            return self._assert_container_contains(value)
        elif name == "zoneContains":
            return self._check_zone(value)
        else:
            return AssertionResult(
                name=name,
                expected=value,
                passed=False,
                error=f"Unknown assertion type: {name}"
            )

    def _assert_last_action_ok(self, expected: bool) -> AssertionResult:
        """Check LastAction.Ok status."""
        bot_id = self._get_bot_id()
        params = {"botId": bot_id} if bot_id else {}
        result = self.client.get("/polis/state", params if params else None)

        last_action = result.get("LastAction") or {}
        actual = last_action.get("Ok", False)

        return AssertionResult(
            name="lastActionOk",
            expected=expected,
            actual=actual,
            passed=(actual == expected)
        )

    def _assert_block_gone(self, pos: list) -> AssertionResult:
        """Check that block at position is gone (air)."""
        if len(pos) != 3:
            return AssertionResult(
                name="blockGone",
                expected=pos,
                passed=False,
                error="Position must be [x, y, z]"
            )

        # Use targets endpoint to check if block exists
        params = {
            "x": str(pos[0]),
            "y": str(pos[1]),
            "z": str(pos[2]),
            "radius": "1",
            "mode": "blocks"
        }

        bot_id = self._get_bot_id()
        if bot_id:
            params["botId"] = bot_id

        result = self.client.get("/polis/targets", params)
        blocks = result.get("Blocks", result.get("blocks", [])) or []

        # Check if any block at exact position
        block_at_pos = None
        for b in blocks:
            b_pos = b.get("Pos", b.get("pos", []))
            if len(b_pos) >= 3 and int(b_pos[0]) == int(pos[0]) and int(b_pos[1]) == int(pos[1]) and int(b_pos[2]) == int(pos[2]):
                code = b.get("Code", b.get("code", ""))
                if code and "air" not in code.lower():
                    block_at_pos = code
                    break

        return AssertionResult(
            name="blockGone",
            expected=f"no block at {pos}",
            actual=f"block '{block_at_pos}' at {pos}" if block_at_pos else "air",
            passed=(block_at_pos is None)
        )

    def _assert_block_present(self, spec: any, step_args: dict = None) -> AssertionResult:
        """Check that a block with given code exists at position."""
        # spec can be: "blockCode" (use step args for pos) or {"code": "...", "pos": [...]}
        if isinstance(spec, str):
            expected_code = spec
            pos = [step_args.get("x"), step_args.get("y"), step_args.get("z")] if step_args else None
        else:
            expected_code = spec.get("code", "")
            pos = spec.get("pos", [])

        if not pos or len(pos) != 3:
            return AssertionResult(
                name="blockPresent",
                expected=spec,
                passed=False,
                error="Position required"
            )

        params = {
            "x": str(pos[0]),
            "y": str(pos[1]),
            "z": str(pos[2]),
            "radius": "1",
            "mode": "blocks"
        }

        bot_id = self._get_bot_id()
        if bot_id:
            params["botId"] = bot_id

        result = self.client.get("/polis/targets", params)
        blocks = result.get("Blocks", result.get("blocks", [])) or []

        # Check if block with matching code at position
        found_code = None
        for b in blocks:
            b_pos = b.get("Pos", b.get("pos", []))
            if len(b_pos) >= 3 and int(b_pos[0]) == int(pos[0]) and int(b_pos[1]) == int(pos[1]) and int(b_pos[2]) == int(pos[2]):
                found_code = b.get("Code", b.get("code", ""))
                break

        passed = found_code is not None and expected_code.lower() in found_code.lower()

        return AssertionResult(
            name="blockPresent",
            expected=f"'{expected_code}' at {pos}",
            actual=f"'{found_code}' at {pos}" if found_code else f"no block at {pos}",
            passed=passed
        )

    def _assert_inventory_contains(self, item_code: str) -> AssertionResult:
        """Check that bot inventory contains item."""
        bot_id = self._get_bot_id()
        params = {"botId": bot_id} if bot_id else {}
        result = self.client.get("/polis/state", params if params else None)

        bot = result.get("Bot", {})

        # Check all inventory locations
        inventory_codes = []

        # Right hand
        right_hand = bot.get("RightHand", {})
        if right_hand:
            code = right_hand.get("Code", right_hand.get("code", ""))
            if code:
                inventory_codes.append(code)

        # Backpack slots
        backpacks = bot.get("Backpacks", []) or []
        for slot in backpacks:
            if slot:
                code = slot.get("Code", slot.get("code", ""))
                if code:
                    inventory_codes.append(code)

        # Check if item present
        found = any(item_code.lower() in code.lower() for code in inventory_codes)

        return AssertionResult(
            name="inventoryContains",
            expected=item_code,
            actual=inventory_codes if inventory_codes else "empty",
            passed=found
        )

    def _assert_inventory_not_contains(self, item_code: str) -> AssertionResult:
        """Check that bot inventory does NOT contain item."""
        contains_result = self._assert_inventory_contains(item_code)
        return AssertionResult(
            name="inventoryNotContains",
            expected=f"not {item_code}",
            actual=contains_result.actual,
            passed=not contains_result.passed
        )

    def _assert_container_contains(self, spec: dict) -> AssertionResult:
        """Check container contents at position."""
        pos = spec.get("pos", [])
        expected_code = spec.get("code", spec.get("itemCode", ""))
        slot = spec.get("slot")

        if len(pos) != 3:
            return AssertionResult(
                name="containerContains",
                expected=spec,
                passed=False,
                error="Position must be [x, y, z]"
            )

        params = {
            "x": str(int(pos[0])),
            "y": str(int(pos[1])),
            "z": str(int(pos[2]))
        }

        result = self.client.get("/polis/container-contents", params)

        if not result.get("Ok"):
            return AssertionResult(
                name="containerContains",
                expected=spec,
                actual=result.get("Message", "error"),
                passed=False,
                error=result.get("Message")
            )

        data = result.get("Data", {})
        slots = data.get("slots", [])

        # Check for expected item
        if slot is not None:
            # Check specific slot
            slot_data = next((s for s in slots if s.get("slot") == slot), None)
            if slot_data:
                found_code = slot_data.get("code", "")
                passed = expected_code.lower() in found_code.lower()
                actual = f"slot {slot}: {found_code}"
            else:
                passed = False
                actual = f"slot {slot}: empty"
        else:
            # Check any slot
            all_codes = [s.get("code", "") for s in slots]
            found = any(expected_code.lower() in code.lower() for code in all_codes)
            passed = found
            actual = all_codes if all_codes else "empty container"

        return AssertionResult(
            name="containerContains",
            expected=f"'{expected_code}' in container at {pos}",
            actual=actual,
            passed=passed
        )

    def _check_zone(self, expected_zone: str) -> AssertionResult:
        """Check if bot is in expected zone."""
        bot_id = self._get_bot_id()
        params = {"botId": bot_id} if bot_id else {}

        result = self.client.get("/polis/zone-check", params)

        zones = []
        if result.get("Ok"):
            data = result.get("Data", {})
            zones = data.get("zones", [])

        in_zone = expected_zone in zones

        return AssertionResult(
            name="zoneContains",
            expected=expected_zone,
            actual=zones if zones else "no zones",
            passed=in_zone
        )

    # ========================================================================
    # Helper Methods
    # ========================================================================

    def _get_bot_id(self) -> Optional[str]:
        """Get current bot ID."""
        if self._bot_id:
            return self._bot_id
        return os.environ.get("POLIS_BOT_ID")

    def _get_player_uid(self) -> Optional[str]:
        """Get current player UID."""
        if self._player_uid:
            return self._player_uid

        uid = os.environ.get("POLIS_PLAYER_UID")
        if uid:
            return uid

        # Auto-detect single player
        try:
            result = self.client.get("/polis/players")
            players = result.get("players", [])
            if len(players) == 1:
                return players[0].get("uid")
        except Exception:
            pass

        return None

    def _capture_failure_screenshot(self, station: str, step: str) -> Optional[str]:
        """Capture screenshot on failure using manifest camera position."""
        player_uid = self._get_player_uid()
        if not player_uid:
            return None

        # Use observer-screenshot with stored camera position if available
        if self._current_camera:
            cam_pos = self._current_camera.get("position", [])
            if len(cam_pos) == 3:
                params = {
                    "playerUid": player_uid,
                    "x": str(cam_pos[0]),
                    "y": str(cam_pos[1]),
                    "z": str(cam_pos[2]),
                    "yaw": str(self._current_camera.get("yaw", 0)),
                    "pitch": str(self._current_camera.get("pitch", 0)),
                    "save": "true"
                }
                self.log(f"    Capturing from camera position: {cam_pos}", "debug")
                result = self.client.get("/polis/observer-screenshot", params)
                if result.get("ok"):
                    return result.get("filePath")
                # Fall through to basic screenshot if observer-screenshot fails
                self.log(f"    Observer screenshot failed, using fallback", "debug")

        # Fallback to current player view
        params = {"playerUid": player_uid, "save": "true"}
        result = self.client.get("/polis/screenshot", params)

        if result.get("ok"):
            return result.get("filePath")
        return None


# ============================================================================
# Report Generation
# ============================================================================

def generate_report(results: list, start_time: datetime, end_time: datetime) -> TestReport:
    """Generate test report from results."""
    passed = sum(1 for r in results if r.status == "pass")
    failed = sum(1 for r in results if r.status == "fail")
    skipped = sum(1 for r in results if r.status == "skip")
    total_zone_violations = sum(r.zone_violations for r in results)

    return TestReport(
        summary={
            "total": len(results),
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "zone_violations": total_zone_violations,
            "success": failed == 0
        },
        stations=[asdict(r) for r in results],
        started_at=start_time.isoformat(),
        finished_at=end_time.isoformat()
    )


def print_summary(report: TestReport):
    """Print summary to terminal."""
    s = report.summary
    print()
    print(f"{Colors.BOLD}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}Test Summary{Colors.RESET}")
    print(f"{'='*60}")
    print(f"Total:   {s['total']}")
    print(f"Passed:  {Colors.PASS}{s['passed']}{Colors.RESET}")
    print(f"Failed:  {Colors.FAIL}{s['failed']}{Colors.RESET}")
    if s['skipped']:
        print(f"Skipped: {Colors.WARN}{s['skipped']}{Colors.RESET}")
    if s['zone_violations']:
        print(f"Zone violations: {Colors.WARN}{s['zone_violations']}{Colors.RESET}")
    print(f"{'='*60}")

    if s['success']:
        print(f"{Colors.PASS}{Colors.BOLD}ALL TESTS PASSED{Colors.RESET}")
    else:
        print(f"{Colors.FAIL}{Colors.BOLD}TESTS FAILED{Colors.RESET}")


# ============================================================================
# CLI
# ============================================================================

def discover_manifests(directory: Path) -> list:
    """Discover all manifest files in directory."""
    if not directory.exists():
        return []
    return sorted(directory.glob("*.json"))


def main():
    parser = argparse.ArgumentParser(
        description="Polis Test Runner - Execute JSON test manifests",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --list                    List available manifests
  %(prog)s inventory -v              Run inventory tests with verbose output
  %(prog)s --reset --report out.json Reset world, run all, save report
  %(prog)s block-ops containers      Run specific stations
        """
    )

    parser.add_argument(
        "stations",
        nargs="*",
        help="Station names to run (default: all)"
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Reset world before running (requires game not running)"
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop on first failure"
    )
    parser.add_argument(
        "--screenshot-on-failure",
        action="store_true",
        help="Capture screenshot on test failure"
    )
    parser.add_argument(
        "--report",
        metavar="PATH",
        help="Write JSON report to file"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available manifests and exit"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose output"
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable colored output"
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("POLIS_HOST", "127.0.0.1"),
        help="Harness host (default: $POLIS_HOST or 127.0.0.1)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("POLIS_PORT", "8585")),
        help="Harness port (default: $POLIS_PORT or 8585)"
    )
    parser.add_argument(
        "--manifests-dir",
        type=Path,
        default=MANIFESTS_DIR,
        help=f"Manifests directory (default: {MANIFESTS_DIR})"
    )

    args = parser.parse_args()

    if args.no_color:
        Colors.disable()

    # List manifests
    manifests = discover_manifests(args.manifests_dir)
    if args.list:
        if not manifests:
            print(f"No manifests found in {args.manifests_dir}")
            return EXIT_SUCCESS
        print(f"Available manifests ({len(manifests)}):")
        for m in manifests:
            print(f"  {m.stem}")
        return EXIT_SUCCESS

    # Filter manifests by station name
    if args.stations:
        manifests = [m for m in manifests if m.stem in args.stations]
        if not manifests:
            print(f"No manifests found matching: {args.stations}", file=sys.stderr)
            return EXIT_USAGE_ERROR

    if not manifests:
        print(f"No manifests found in {args.manifests_dir}", file=sys.stderr)
        print("Create manifests in tests/world/manifests/ or use --manifests-dir", file=sys.stderr)
        return EXIT_RUNNER_ERROR

    # Reset world if requested
    if args.reset:
        reset_script = Path(__file__).parent.parent / "tests" / "world" / "reset-testbed.sh"
        if reset_script.exists():
            import subprocess
            print(f"{Colors.INFO}[INFO]{Colors.RESET} Resetting testbed...")
            result = subprocess.run([str(reset_script)], capture_output=True, text=True)
            if result.returncode != 0:
                print(f"{Colors.FAIL}[FAIL]{Colors.RESET} Reset failed: {result.stderr}", file=sys.stderr)
                return EXIT_RUNNER_ERROR
        else:
            print(f"Reset script not found: {reset_script}", file=sys.stderr)
            return EXIT_RUNNER_ERROR

    # Connect to harness
    client = HarnessClient(args.host, args.port)

    try:
        status = client.get("/polis/status")
        if not status.get("server", {}).get("worldReady"):
            print(f"{Colors.FAIL}[ERROR]{Colors.RESET} Server not ready. Start the game first.", file=sys.stderr)
            return EXIT_CONNECTION_ERROR
    except Exception as e:
        print(f"{Colors.FAIL}[ERROR]{Colors.RESET} Failed to connect to harness: {e}", file=sys.stderr)
        return EXIT_CONNECTION_ERROR

    # Run tests
    runner = TestRunner(client, args)
    results = []
    start_time = datetime.now()

    print(f"\n{Colors.BOLD}Running {len(manifests)} test station(s){Colors.RESET}\n")

    for manifest in manifests:
        result = runner.run_manifest(manifest)
        results.append(result)

        status_color = Colors.PASS if result.status == "pass" else Colors.FAIL
        print(f"{status_color}[{result.status.upper()}]{Colors.RESET} {result.name} ({result.duration:.2f}s)")

        if result.status == "fail" and args.fail_fast:
            break

    end_time = datetime.now()

    # Generate report
    report = generate_report(results, start_time, end_time)
    print_summary(report)

    # Write JSON report
    if args.report:
        report_path = Path(args.report)
        with open(report_path, "w") as f:
            json.dump(asdict(report), f, indent=2)
        print(f"\nReport written to: {report_path}")

    # Return exit code
    return EXIT_SUCCESS if report.summary["success"] else EXIT_TEST_FAILED


if __name__ == "__main__":
    sys.exit(main())
