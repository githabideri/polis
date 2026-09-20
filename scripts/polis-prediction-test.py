#!/usr/bin/env python3
"""
Phase 1.5 Prediction Test Suite for polis-builder-npc.

Tests possession control and measures movement quality metrics
to validate smoothing improvements.

Usage:
  python3 scripts/polis-prediction-test.py                    # Run all tests
  python3 scripts/polis-prediction-test.py --test possession  # Run specific test
  python3 scripts/polis-prediction-test.py --label baseline   # Tag results
  python3 scripts/polis-prediction-test.py --json             # Output JSON only
"""

import argparse
import json
import math
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, asdict
from typing import List, Tuple, Optional, Dict, Any


class HarnessClient:
    """HTTP client for the polis test harness."""

    def __init__(self, base_url: str, request_timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.request_timeout = request_timeout

    def get(self, path: str) -> dict:
        return self._request("GET", path)

    def post(self, path: str, payload: dict) -> dict:
        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        return self._request("POST", path, data=data, headers=headers)

    def _request(self, method: str, path: str, data=None, headers=None) -> dict:
        if headers is None:
            headers = {}
        url = self.base_url + path
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.request_timeout) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8") if exc.fp else ""
            raise RuntimeError(f"HTTP {exc.code} {method} {path}: {body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"HTTP request failed {method} {path}: {exc}") from exc

        try:
            return json.loads(raw) if raw else {}
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid JSON from {method} {path}: {raw}") from exc


@dataclass
class TestResult:
    """Result of a single test."""
    name: str
    passed: bool
    message: str
    metrics: Dict[str, Any]


class PredictionTestSuite:
    """Test suite for Phase 1.5 prediction validation."""

    def __init__(self, host: str = "localhost", port: int = 8585, verbose: bool = False):
        self.base_url = f"http://{host}:{port}"
        self.client = HarnessClient(self.base_url, request_timeout=10.0)
        self.verbose = verbose
        self.player_uid: Optional[str] = None
        self.bot_id: Optional[int] = None
        self.results: List[TestResult] = []

    def log(self, msg: str):
        if self.verbose:
            print(f"  {msg}")

    def wait_for_ready(self, timeout: float = 120.0):
        """Wait for server to be ready."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                status = self.client.get("/polis/status")
                server = status.get("server") if isinstance(status, dict) else None
                if server and server.get("worldReady") is True:
                    return
            except Exception:
                pass
            time.sleep(1)
        raise RuntimeError("Timeout waiting for world ready")

    def get_player_uid(self) -> str:
        """Get the first online player's UID."""
        players = self.client.get("/polis/players")
        player_list = players.get("players", [])
        if not player_list:
            raise RuntimeError("No players online. Start the game client first.")
        return player_list[0]["uid"]

    def spawn_bot(self) -> int:
        """Spawn a bot and return its ID."""
        result = self.client.post("/polis/command", {"cmd": "spawn"})
        if not result.get("Ok"):
            raise RuntimeError(f"spawn failed: {result}")
        bot_id = result.get("Data", {}).get("id")
        if bot_id is None:
            raise RuntimeError(f"spawn returned no bot id: {result}")

        # Select the bot
        self.client.post("/polis/command", {"cmd": "select", "args": [str(bot_id)]})
        return bot_id

    def despawn_bot(self):
        """Despawn the current bot."""
        self.client.post("/polis/command", {"cmd": "despawn"})

    def possess(self) -> bool:
        """Possess the selected bot."""
        result = self.client.post("/polis/command", {
            "cmd": "possess",
            "context": {"playerUid": self.player_uid}
        })
        return result.get("Ok", False)

    def unpossess(self) -> bool:
        """Exit possession."""
        result = self.client.post("/polis/command", {
            "cmd": "unpossess",
            "context": {"playerUid": self.player_uid}
        })
        return result.get("Ok", False)

    def set_controls(self, forward=False, backward=False, left=False, right=False, sprint=False, jump=False) -> bool:
        """Set movement controls."""
        args = [
            "true" if forward else "false",
            "true" if backward else "false",
            "true" if left else "false",
            "true" if right else "false",
            "true" if sprint else "false",
            "true" if jump else "false",
        ]
        result = self.client.post("/polis/command", {
            "cmd": "setcontrols",
            "args": args,
            "context": {"playerUid": self.player_uid}
        })
        return result.get("Ok", False)

    def get_bot_position(self) -> Tuple[float, float, float]:
        """Get current bot position."""
        state = self.client.get(f"/polis/state?botId={self.bot_id}")
        pos = state.get("Bot", {}).get("Pos", [0, 0, 0])
        return tuple(pos)

    def sample_positions(self, duration: float, interval: float = 0.1) -> List[Tuple[float, float, float, float]]:
        """Sample positions over time. Returns list of (time, x, y, z)."""
        positions = []
        start = time.time()
        while time.time() - start < duration:
            t = time.time() - start
            pos = self.get_bot_position()
            positions.append((t, pos[0], pos[1], pos[2]))
            time.sleep(interval)
        return positions

    def calculate_velocities(self, positions: List[Tuple[float, float, float, float]]) -> List[float]:
        """Calculate velocities from position samples."""
        velocities = []
        for i in range(len(positions) - 1):
            t0, x0, y0, z0 = positions[i]
            t1, x1, y1, z1 = positions[i + 1]
            dt = t1 - t0
            if dt > 0:
                dist = math.sqrt((x1 - x0) ** 2 + (z1 - z0) ** 2)  # XZ plane
                vel = dist / dt
                velocities.append(vel)
        return velocities

    def calculate_consistency(self, velocities: List[float]) -> float:
        """Calculate velocity consistency (1.0 = perfect, lower = jittery)."""
        if not velocities:
            return 0.0
        avg = sum(velocities) / len(velocities)
        if avg == 0:
            return 0.0
        variance = sum((v - avg) ** 2 for v in velocities) / len(velocities)
        stddev = math.sqrt(variance)
        # Consistency: 1 - (stddev / avg), clamped to [0, 1]
        return max(0.0, min(1.0, 1.0 - stddev / avg))

    # =========================================================================
    # Test Cases
    # =========================================================================

    def test_possession_cycle(self) -> TestResult:
        """Test: Can we possess and unpossess via HTTP?"""
        self.log("Spawning bot...")
        self.bot_id = self.spawn_bot()

        self.log("Possessing...")
        possessed = self.possess()
        if not possessed:
            self.despawn_bot()
            return TestResult(
                name="possession_cycle",
                passed=False,
                message="Failed to possess bot",
                metrics={}
            )

        time.sleep(0.5)

        self.log("Unpossessing...")
        unpossessed = self.unpossess()

        self.log("Cleaning up...")
        self.despawn_bot()

        return TestResult(
            name="possession_cycle",
            passed=possessed and unpossessed,
            message="Mount/unmount cycle successful" if (possessed and unpossessed) else "Cycle failed",
            metrics={"possessed": possessed, "unpossessed": unpossessed}
        )

    def test_controlled_movement(self) -> TestResult:
        """Test: Does injecting controls cause NPC movement?"""
        self.log("Spawning bot...")
        self.bot_id = self.spawn_bot()

        self.log("Possessing...")
        if not self.possess():
            self.despawn_bot()
            return TestResult(
                name="controlled_movement",
                passed=False,
                message="Failed to possess",
                metrics={}
            )

        time.sleep(0.5)

        # Record start position
        start_pos = self.get_bot_position()
        self.log(f"Start position: {start_pos}")

        # Inject forward movement
        self.log("Setting forward controls...")
        self.set_controls(forward=True)

        time.sleep(3.0)  # Move for 3 seconds

        # Stop movement
        self.set_controls()  # All false

        # Record end position
        end_pos = self.get_bot_position()
        self.log(f"End position: {end_pos}")

        # Calculate distance moved (XZ plane)
        dist = math.sqrt(
            (end_pos[0] - start_pos[0]) ** 2 +
            (end_pos[2] - start_pos[2]) ** 2
        )
        self.log(f"Distance moved: {dist:.3f} blocks")

        # Cleanup
        self.unpossess()
        self.despawn_bot()

        # Should have moved at least 1 block in 3 seconds
        passed = dist > 1.0

        return TestResult(
            name="controlled_movement",
            passed=passed,
            message=f"Moved {dist:.2f} blocks in 3s" if passed else f"Only moved {dist:.2f} blocks (expected >1)",
            metrics={
                "distance_moved": dist,
                "start_pos": list(start_pos),
                "end_pos": list(end_pos),
                "expected_min": 1.0
            }
        )

    def test_velocity_consistency(self, duration: float = 5.0) -> TestResult:
        """Test: Is movement velocity consistent? (Core smoothness proxy)"""
        self.log("Spawning bot...")
        self.bot_id = self.spawn_bot()

        self.log("Possessing...")
        if not self.possess():
            self.despawn_bot()
            return TestResult(
                name="velocity_consistency",
                passed=False,
                message="Failed to possess",
                metrics={}
            )

        time.sleep(0.5)

        # Start forward movement
        self.log("Starting forward movement...")
        self.set_controls(forward=True)

        # Sample positions
        self.log(f"Sampling positions for {duration}s...")
        positions = self.sample_positions(duration, interval=0.1)

        # Stop movement
        self.set_controls()

        # Calculate velocities
        velocities = self.calculate_velocities(positions)

        if velocities:
            avg_vel = sum(velocities) / len(velocities)
            variance = sum((v - avg_vel) ** 2 for v in velocities) / len(velocities)
            stddev = math.sqrt(variance)
            consistency = self.calculate_consistency(velocities)
            min_vel = min(velocities)
            max_vel = max(velocities)
        else:
            avg_vel = stddev = consistency = min_vel = max_vel = 0.0

        self.log(f"Avg velocity: {avg_vel:.4f}, stddev: {stddev:.4f}, consistency: {consistency:.3f}")

        # Cleanup
        self.unpossess()
        self.despawn_bot()

        # Threshold: consistency > 0.7 is considered smooth
        passed = consistency > 0.7

        return TestResult(
            name="velocity_consistency",
            passed=passed,
            message=f"Consistency: {consistency:.3f}" + (" (smooth)" if passed else " (jittery)"),
            metrics={
                "avg_velocity": avg_vel,
                "velocity_stddev": stddev,
                "consistency": consistency,
                "min_velocity": min_vel,
                "max_velocity": max_vel,
                "samples": len(positions),
                "duration": duration,
                "threshold": 0.7
            }
        )

    def test_stop_behavior(self) -> TestResult:
        """Test: Does NPC stop cleanly when controls released?"""
        self.log("Spawning bot...")
        self.bot_id = self.spawn_bot()

        self.log("Possessing...")
        if not self.possess():
            self.despawn_bot()
            return TestResult(
                name="stop_behavior",
                passed=False,
                message="Failed to possess",
                metrics={}
            )

        time.sleep(0.5)

        # Move for 2 seconds
        self.log("Moving forward...")
        self.set_controls(forward=True)
        time.sleep(2.0)

        # Stop
        self.log("Stopping...")
        self.set_controls()

        # Record position immediately after stop
        time.sleep(0.2)  # Brief settle
        stop_pos = self.get_bot_position()

        # Wait and check for drift
        time.sleep(2.0)
        final_pos = self.get_bot_position()

        # Calculate drift
        drift = math.sqrt(
            (final_pos[0] - stop_pos[0]) ** 2 +
            (final_pos[2] - stop_pos[2]) ** 2
        )
        self.log(f"Drift after stop: {drift:.4f} blocks")

        # Cleanup
        self.unpossess()
        self.despawn_bot()

        # Threshold: drift < 0.1 blocks
        passed = drift < 0.1

        return TestResult(
            name="stop_behavior",
            passed=passed,
            message="NPC stopped cleanly" if passed else f"NPC drifted {drift:.3f} blocks after stop",
            metrics={
                "drift_distance": drift,
                "stop_pos": list(stop_pos),
                "final_pos": list(final_pos),
                "threshold": 0.1
            }
        )

    # =========================================================================
    # Runner
    # =========================================================================

    def run_all_tests(self) -> List[TestResult]:
        """Run all tests."""
        print("Phase 1.5 Prediction Test Suite")
        print("=" * 50)

        print("\n[1/5] Waiting for world ready...")
        self.wait_for_ready()
        print("  World ready")

        print("\n[2/5] Getting player UID...")
        self.player_uid = self.get_player_uid()
        print(f"  Player UID: {self.player_uid}")

        tests = [
            ("possession_cycle", self.test_possession_cycle),
            ("controlled_movement", self.test_controlled_movement),
            ("velocity_consistency", self.test_velocity_consistency),
            ("stop_behavior", self.test_stop_behavior),
        ]

        for i, (name, test_fn) in enumerate(tests):
            print(f"\n[{i+3}/{len(tests)+2}] Running {name}...")
            try:
                result = test_fn()
                self.results.append(result)
                status = "PASS" if result.passed else "FAIL"
                print(f"  {status}: {result.message}")
            except Exception as e:
                result = TestResult(
                    name=name,
                    passed=False,
                    message=f"Exception: {e}",
                    metrics={}
                )
                self.results.append(result)
                print(f"  ERROR: {e}")

        return self.results

    def run_single_test(self, test_name: str) -> TestResult:
        """Run a single test by name."""
        print(f"Running single test: {test_name}")
        print("=" * 50)

        print("\nWaiting for world ready...")
        self.wait_for_ready()

        print("Getting player UID...")
        self.player_uid = self.get_player_uid()

        test_map = {
            "possession": self.test_possession_cycle,
            "movement": self.test_controlled_movement,
            "velocity": self.test_velocity_consistency,
            "stop": self.test_stop_behavior,
        }

        if test_name not in test_map:
            raise RuntimeError(f"Unknown test: {test_name}. Available: {list(test_map.keys())}")

        print(f"\nRunning {test_name}...")
        result = test_map[test_name]()
        self.results.append(result)

        status = "PASS" if result.passed else "FAIL"
        print(f"\n{status}: {result.message}")

        return result

    def print_report(self, label: Optional[str] = None):
        """Print test report."""
        print("\n" + "=" * 50)
        print("TEST RESULTS SUMMARY")
        if label:
            print(f"Label: {label}")
        print("=" * 50)

        passed_count = sum(1 for r in self.results if r.passed)
        total_count = len(self.results)

        for result in self.results:
            status = "PASS" if result.passed else "FAIL"
            print(f"\n{result.name}: {status}")
            print(f"  Message: {result.message}")
            for key, value in result.metrics.items():
                if isinstance(value, float):
                    print(f"  {key}: {value:.4f}")
                else:
                    print(f"  {key}: {value}")

        print(f"\n{'=' * 50}")
        print(f"TOTAL: {passed_count}/{total_count} passed")
        print("=" * 50)

    def to_json(self, label: Optional[str] = None) -> dict:
        """Convert results to JSON-serializable dict."""
        return {
            "label": label,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "passed": sum(1 for r in self.results if r.passed),
            "total": len(self.results),
            "tests": {r.name: asdict(r) for r in self.results}
        }


def main():
    parser = argparse.ArgumentParser(
        description="Phase 1.5 prediction test suite for polis-builder-npc"
    )
    parser.add_argument("--host", default="localhost", help="HTTP host (default: localhost)")
    parser.add_argument("--port", type=int, default=8585, help="HTTP port (default: 8585)")
    parser.add_argument("--test", choices=["possession", "movement", "velocity", "stop"],
                        help="Run a single test instead of all")
    parser.add_argument("--label", help="Label for this test run (e.g., 'baseline', 'prediction-v1')")
    parser.add_argument("--json", action="store_true", help="Output results as JSON only")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    suite = PredictionTestSuite(args.host, args.port, verbose=args.verbose)

    try:
        if args.test:
            suite.run_single_test(args.test)
        else:
            suite.run_all_tests()

        if args.json:
            print(json.dumps(suite.to_json(args.label), indent=2))
        else:
            suite.print_report(args.label)

        # Exit code: 0 if all passed, 1 if any failed
        all_passed = all(r.passed for r in suite.results)
        return 0 if all_passed else 1

    except Exception as e:
        if args.json:
            print(json.dumps({"error": str(e)}))
        else:
            print(f"FATAL: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
