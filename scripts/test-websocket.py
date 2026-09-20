#!/usr/bin/env python3
"""WebSocket event streaming test script.

Tests the WebSocket endpoint at ws://localhost:8585/polis/ws

Usage:
    python3 scripts/test-websocket.py [--timeout 10]
"""

import asyncio
import json
import subprocess
import sys
import argparse

try:
    import websockets
except ImportError:
    print("ERROR: websockets library required. Install with: pip install websockets")
    sys.exit(1)

API_BASE = "http://localhost:8585"
WS_URL = "ws://localhost:8585/polis/ws"

def curl_cmd(endpoint, method="GET", data=None):
    """Run a curl command and return parsed JSON."""
    cmd = ["curl", "-s"]
    if method == "POST":
        cmd.extend(["-X", "POST", "-H", "Content-Type: application/json"])
        if data:
            cmd.extend(["-d", json.dumps(data)])
    cmd.append(f"{API_BASE}{endpoint}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return json.loads(result.stdout)
    except:
        return {"error": result.stdout or result.stderr}

async def test_websocket(timeout_sec=10):
    """Run WebSocket tests."""
    print(f"{'='*60}")
    print("WebSocket Event Streaming Test")
    print(f"{'='*60}\n")

    events_received = []
    tests_passed = 0
    tests_failed = 0

    def ok(msg):
        nonlocal tests_passed
        tests_passed += 1
        print(f"[PASS] {msg}")

    def fail(msg):
        nonlocal tests_failed
        tests_failed += 1
        print(f"[FAIL] {msg}")

    # Test 1: Check server is ready
    print("Test 1: Server readiness")
    status = curl_cmd("/polis/status")
    if status.get("server", {}).get("worldReady"):
        ok("Server is ready")
    else:
        fail(f"Server not ready: {status}")
        print("\nStart the VS server first!")
        return 1

    # Test 2: WebSocket connection
    print("\nTest 2: WebSocket connection")
    try:
        async with websockets.connect(WS_URL, close_timeout=2) as ws:
            ok(f"Connected to {WS_URL}")

            # Test 3: Send subscription
            print("\nTest 3: Subscription")
            await ws.send(json.dumps({"subscribe": {"level": "normal"}}))
            ok("Sent subscription (level=normal)")

            # Test 4: Spawn bot and receive event
            print("\nTest 4: bot_spawned event")
            spawn_result = curl_cmd("/polis/command", "POST", {"cmd": "spawn"})
            if spawn_result.get("Ok"):
                ok(f"Spawned bot: {spawn_result.get('Message')}")
                bot_id = spawn_result.get("Data", {}).get("id")
            else:
                fail(f"Spawn failed: {spawn_result}")
                bot_id = None

            # Wait for event
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=2)
                event = json.loads(msg)
                events_received.append(event)
                if event.get("type") == "bot_spawned":
                    ok(f"Received bot_spawned event: botId={event['data'].get('botId')}")
                else:
                    fail(f"Expected bot_spawned, got: {event.get('type')}")
            except asyncio.TimeoutError:
                fail("No event received after spawn (timeout)")

            # Test 5: action_complete event (give)
            print("\nTest 5: action_complete event (give)")
            give_result = curl_cmd("/polis/command", "POST", {"cmd": "give", "args": ["game:stone-granite", "3"]})
            if give_result.get("Ok"):
                ok(f"Give command: {give_result.get('Message')}")
            else:
                fail(f"Give failed: {give_result}")

            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=2)
                event = json.loads(msg)
                events_received.append(event)
                if event.get("type") == "action_complete" and event["data"].get("action") == "give":
                    ok(f"Received action_complete(give): ok={event['data'].get('ok')}")
                else:
                    fail(f"Expected action_complete(give), got: {event}")
            except asyncio.TimeoutError:
                fail("No event received after give (timeout)")

            # Test 6: action_complete event (drop)
            print("\nTest 6: action_complete event (drop)")
            drop_result = curl_cmd("/polis/command", "POST", {"cmd": "drop"})
            if drop_result.get("Ok"):
                ok(f"Drop command: {drop_result.get('Message')}")
            else:
                fail(f"Drop failed: {drop_result}")

            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=2)
                event = json.loads(msg)
                events_received.append(event)
                if event.get("type") == "action_complete" and event["data"].get("action") == "drop":
                    ok(f"Received action_complete(drop): ok={event['data'].get('ok')}")
                else:
                    fail(f"Expected action_complete(drop), got: {event}")
            except asyncio.TimeoutError:
                fail("No event received after drop (timeout)")

            # Test 7: bot_died event (despawn)
            print("\nTest 7: bot_died event")
            despawn_result = curl_cmd("/polis/command", "POST", {"cmd": "despawn"})
            if despawn_result.get("Ok"):
                ok(f"Despawn command: {despawn_result.get('Message')}")
            else:
                fail(f"Despawn failed: {despawn_result}")

            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=2)
                event = json.loads(msg)
                events_received.append(event)
                if event.get("type") == "bot_died":
                    ok(f"Received bot_died event: cause={event['data'].get('cause')}")
                else:
                    fail(f"Expected bot_died, got: {event.get('type')}")
            except asyncio.TimeoutError:
                fail("No event received after despawn (timeout)")

            # Test 8: Subscription level change
            print("\nTest 8: Subscription level change")
            await ws.send(json.dumps({"subscribe": {"level": "debug"}}))
            ok("Changed subscription to debug level")

    except websockets.exceptions.ConnectionClosed as e:
        fail(f"WebSocket closed unexpectedly: {e}")
    except ConnectionRefusedError:
        fail("Connection refused - is the server running?")
        return 1
    except Exception as e:
        fail(f"WebSocket error: {e}")
        return 1

    # Summary
    print(f"\n{'='*60}")
    print(f"Results: {tests_passed} passed, {tests_failed} failed")
    print(f"Events received: {len(events_received)}")
    print(f"{'='*60}")

    if events_received:
        print("\nEvents log:")
        for i, evt in enumerate(events_received, 1):
            print(f"  {i}. {evt.get('type')}: {json.dumps(evt.get('data', {}), default=str)[:80]}")

    return 0 if tests_failed == 0 else 1

def main():
    parser = argparse.ArgumentParser(description="Test WebSocket event streaming")
    parser.add_argument("--timeout", type=int, default=10, help="Test timeout in seconds")
    args = parser.parse_args()

    exit_code = asyncio.run(test_websocket(args.timeout))
    sys.exit(exit_code)

if __name__ == "__main__":
    main()
