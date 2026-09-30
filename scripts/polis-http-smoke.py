#!/usr/bin/env python3
import argparse
import json
import math
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import quote


class HarnessClient:
    def __init__(self, base_url, request_timeout):
        self.base_url = base_url.rstrip("/")
        self.request_timeout = request_timeout

    def get(self, path):
        return self._request("GET", path)

    def post(self, path, payload):
        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        return self._request("POST", path, data=data, headers=headers)

    def _request(self, method, path, data=None, headers=None):
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


def ensure_ok(result, label):
    if not isinstance(result, dict) or result.get("Ok") is not True:
        raise RuntimeError(f"{label} failed: {result}")


def wait_for_state(client, bot_id, predicate, timeout, interval, description):
    deadline = time.time() + timeout
    last_state = None
    while time.time() < deadline:
        state = get_state(client, bot_id)
        last_state = state
        try:
            if predicate(state):
                return state
        except Exception:
            pass
        time.sleep(interval)
    raise RuntimeError(
        f"Timeout waiting for {description}. Last state: {json.dumps(last_state, sort_keys=True)}"
    )


def wait_for_ready(client, timeout, interval):
    deadline = time.time() + timeout
    last_status = None
    while time.time() < deadline:
        status = client.get("/polis/status")
        last_status = status
        server = status.get("server") if isinstance(status, dict) else None
        if server and server.get("worldReady") is True:
            return status
        time.sleep(interval)
    raise RuntimeError(
        f"Timeout waiting for worldReady. Last status: {json.dumps(last_status, sort_keys=True)}"
    )


def get_state(client, bot_id):
    path = "/polis/state"
    if bot_id is not None:
        path += f"?botId={bot_id}"
    return client.get(path)


def command(client, cmd, args):
    return client.post("/polis/command", {"cmd": cmd, "args": args})


def encode_uid(uid):
    return quote(uid, safe="")


def right_hand_matches(state, item_code, qty):
    bot = state.get("Bot") or {}
    slot = bot.get("RightHand")
    if not slot:
        return False
    return slot.get("Code") == item_code and slot.get("Qty") == qty


def right_hand_empty(state):
    bot = state.get("Bot") or {}
    return bot.get("RightHand") is None


def items_present(state):
    items = state.get("Items") or []
    return len(items) > 0


def last_action_ok(state, name):
    action = state.get("LastAction") or {}
    return action.get("Name") == name and action.get("Ok") is True


def distance(pos, target):
    return math.sqrt(
        (pos[0] - target[0]) ** 2 + (pos[1] - target[1]) ** 2 + (pos[2] - target[2]) ** 2
    )


def main():
    parser = argparse.ArgumentParser(
        description="HTTP smoke test for polis test harness."
    )
    parser.add_argument("--host", default="localhost", help="HTTP host (default: localhost)")
    parser.add_argument("--port", type=int, default=8585, help="HTTP port (default: 8585)")
    parser.add_argument(
        "--request-timeout",
        type=float,
        default=5.0,
        help="HTTP request timeout seconds (default: 5)",
    )
    parser.add_argument(
        "--poll",
        type=float,
        default=0.5,
        help="Polling interval seconds (default: 0.5)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Timeout for state waits seconds (default: 30)",
    )
    parser.add_argument(
        "--ready-timeout",
        type=float,
        default=120.0,
        help="Timeout waiting for worldReady seconds (default: 120)",
    )
    parser.add_argument(
        "--pickup-timeout",
        type=float,
        default=30.0,
        help="Timeout for pickup retries seconds (default: 30)",
    )
    parser.add_argument(
        "--pickup-retry-delay",
        type=float,
        default=1.0,
        help="Delay between pickup retries seconds (default: 1)",
    )
    parser.add_argument(
        "--item-code",
        default="game:stone-granite",
        help="Item code to use (default: game:stone-granite)",
    )
    parser.add_argument(
        "--item-qty",
        type=int,
        default=5,
        help="Quantity to give/drop/pickup (default: 5)",
    )
    parser.add_argument(
        "--entity-code",
        default=None,
        help="Optional entity code to spawn (default: mod default)",
    )
    parser.add_argument(
        "--player-uid",
        default=None,
        help="Optional player uid for /polis/player and /polis/look (URL-encoded in requests)",
    )
    parser.add_argument(
        "--drop-slot",
        type=int,
        default=-1,
        help="Drop slot index (-1 auto, 0 right, 1 left) (default: -1)",
    )
    parser.add_argument(
        "--drop-qty",
        type=int,
        default=0,
        help="Drop quantity (0=all) (default: 0)",
    )
    parser.add_argument(
        "--pickup-range",
        type=float,
        default=3.0,
        help="Pickup range (default: 3.0)",
    )
    parser.add_argument(
        "--goto",
        nargs=3,
        type=float,
        metavar=("X", "Y", "Z"),
        help="Optional goto target (X Y Z)",
    )
    parser.add_argument(
        "--goto-timeout",
        type=float,
        default=60.0,
        help="Goto timeout seconds (default: 60)",
    )
    parser.add_argument(
        "--goto-distance",
        type=float,
        default=0.75,
        help="Goto success distance threshold (default: 0.75)",
    )
    parser.add_argument(
        "--stop-after-goto",
        action="store_true",
        help="Stop the bot after a successful goto",
    )
    parser.add_argument("--verbose", action="store_true", help="Verbose output")

    args = parser.parse_args()

    base_url = f"http://{args.host}:{args.port}"
    client = HarnessClient(base_url, args.request_timeout)

    try:
        client.get("/polis")
    except Exception as exc:
        print(f"ERROR: Harness not reachable at {base_url}: {exc}", file=sys.stderr)
        return 2

    print("OK: Harness reachable")

    try:
        wait_for_ready(client, args.ready_timeout, args.poll)
        print("OK: World ready")

        if args.player_uid:
            encoded_uid = encode_uid(args.player_uid)
            player_info = client.get(f"/polis/player?uid={encoded_uid}")
            if args.verbose:
                print(f"player -> {player_info}")
            look_info = client.get(f"/polis/look?uid={encoded_uid}&range=48")
            if args.verbose:
                print(f"look -> {look_info}")

        spawn_args = [args.entity_code] if args.entity_code else []
        spawn_result = command(client, "spawn", spawn_args)
        if args.verbose:
            print(f"spawn -> {spawn_result}")
        ensure_ok(spawn_result, "spawn")
        bot_id = (spawn_result.get("Data") or {}).get("id")
        if bot_id is None:
            raise RuntimeError(f"spawn returned no bot id: {spawn_result}")

        select_result = command(client, "select", [str(bot_id)])
        if args.verbose:
            print(f"select -> {select_result}")
        ensure_ok(select_result, "select")

        wait_for_state(
            client,
            bot_id,
            lambda s: (s.get("Error") is None)
            and (s.get("Bot") or {}).get("Id") == bot_id,
            args.timeout,
            args.poll,
            "bot state",
        )
        print(f"OK: Bot #{bot_id} available")

        give_result = command(client, "give", [args.item_code, str(args.item_qty)])
        if args.verbose:
            print(f"give -> {give_result}")
        ensure_ok(give_result, "give")

        wait_for_state(
            client,
            bot_id,
            lambda s: right_hand_matches(s, args.item_code, args.item_qty),
            args.timeout,
            args.poll,
            "right hand inventory",
        )
        print("OK: Give verified")

        drop_result = command(
            client, "drop", [str(args.drop_slot), str(args.drop_qty)]
        )
        if args.verbose:
            print(f"drop -> {drop_result}")
        ensure_ok(drop_result, "drop")

        wait_for_state(
            client,
            bot_id,
            lambda s: right_hand_empty(s) and items_present(s) and last_action_ok(s, "drop"),
            args.timeout,
            args.poll,
            "drop result",
        )
        print("OK: Drop verified")

        pickup_deadline = time.time() + args.pickup_timeout
        pickup_result = None
        while time.time() < pickup_deadline:
            pickup_result = command(
                client, "pickup", ["", f"{args.pickup_range}"]
            )
            if args.verbose:
                print(f"pickup -> {pickup_result}")
            if pickup_result.get("Ok") is True:
                break
            msg = pickup_result.get("Message") or ""
            if "CanCollect returned false" in msg:
                time.sleep(args.pickup_retry_delay)
                continue
            raise RuntimeError(f"pickup failed: {pickup_result}")

        if pickup_result is None or pickup_result.get("Ok") is not True:
            raise RuntimeError(f"pickup timed out: {pickup_result}")

        wait_for_state(
            client,
            bot_id,
            lambda s: right_hand_matches(s, args.item_code, args.item_qty)
            and not items_present(s)
            and last_action_ok(s, "pickup"),
            args.timeout,
            args.poll,
            "pickup result",
        )
        print("OK: Pickup verified")

        if args.goto:
            target = args.goto
            goto_result = command(
                client,
                "goto",
                [str(target[0]), str(target[1]), str(target[2])],
            )
            if args.verbose:
                print(f"goto -> {goto_result}")
            ensure_ok(goto_result, "goto")

            wait_for_state(
                client,
                bot_id,
                lambda s: (s.get("Bot") or {}).get("Pos")
                and distance((s.get("Bot") or {}).get("Pos"), target)
                <= args.goto_distance,
                args.goto_timeout,
                args.poll,
                "goto target reached",
            )
            print("OK: Goto verified")

            if args.stop_after_goto:
                stop_result = command(client, "stop", [])
                if args.verbose:
                    print(f"stop -> {stop_result}")
                ensure_ok(stop_result, "stop")
                print("OK: Stop sent")

        print("Smoke test complete: PASS")
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
