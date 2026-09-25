#!/usr/bin/env python3
"""botview.py -- one-command live overview of the polis bot world.

Usage:
  python3 scripts/botview.py                          # one-shot snapshot
  python3 scripts/botview.py --follow [N]             # Ns loop (default 5),
      streams one line per tick and appends each tick to the JSONL
      sidecar (default /opt/polis/data/botview.jsonl)
  python3 scripts/botview.py --screenshot out.png     # + one observer
      screenshot (use sparingly - image budgets)

Stdlib only; runs inside the polis CT (harness on 127.0.0.1:8585) or
anywhere the harness port is reachable.
"""
import argparse
import json
import sys
import time
import urllib.request


def http_json(url, timeout=8):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.load(r)
    except Exception as e:
        return {"_error": str(e)}


def fetch(base):
    d = {
        "players": (http_json(base + "/polis/players").get("players") or []),
        "bots": ((http_json(base + "/polis/bots").get("Data") or {}).get("bots") or []),
        "zones": (http_json(base + "/polis/zones").get("Data") or {}),
        "events": (http_json(base + "/polis/events").get("events") or []),
    }
    return d


def one_line(d):
    bots = d["bots"]
    bpart = "; ".join(
        "#%s %s (%d,%d,%d) last=%s%s" % (
            b.get("id"), b.get("code"), *b.get("pos", (0, 0, 0))[:3],
            (b.get("lastAction") or {}).get("name", "?"),
            "" if (b.get("lastAction") or {}).get("ok", True) else " FAIL")
        for b in bots) or "none"
    ev = d["events"]
    evpart = ("; last: %s bot#%s %s" % (
        time.strftime("%H:%M:%S", time.localtime(ev[-1]["ts"] / 1000)),
        (ev[-1].get("data") or {}).get("botId"),
        (ev[-1].get("data") or {}).get("action"))) if ev else ""
    p = d["players"][0] if d["players"] else {}
    return "%s player=%s@(%d,%d,%d) bots: %s zones=%d%s" % (
        time.strftime("%H:%M:%S"), p.get("name", "?"),
        *(p.get("pos") or [0, 0, 0])[:3], bpart,
        d["zones"].get("count", 0), evpart)


def snapshot(d):
    return {
        "ts": int(time.time() * 1000),
        "players": d["players"],
        "bots": d["bots"],
        "zones": d["zones"],
        "events": d["events"][-5:],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--harness", default="http://127.0.0.1:8585")
    ap.add_argument("--follow", nargs="?", const="5", default=None,
                    help="loop period in seconds (narg: default 5)")
    ap.add_argument("--sidecar", default="/opt/polis/data/botview.jsonl")
    ap.add_argument("--screenshot", default=None,
                    help="write one observer screenshot to FILE (binary)")
    args = ap.parse_args()

    if args.screenshot:
        try:
            with urllib.request.urlopen(
                    args.harness + "/polis/observer-screenshot", timeout=15) as r:
                open(args.screenshot, "wb").write(r.read())
            print("screenshot: " + args.screenshot, file=sys.stderr)
        except Exception as e:
            print("screenshot failed: %s" % e, file=sys.stderr)

    d = fetch(args.harness)
    print(one_line(d))
    if args.follow is None:
        return

    period = float(args.follow)
    print("following every %.0fs (sidecar %s); ctrl-c to stop" %
          (period, args.sidecar), file=sys.stderr)
    prev_sig = None
    while True:
        time.sleep(period)
        d = fetch(args.harness)
        sig = json.dumps([(b["id"], b["pos"]) for b in d["bots"]], sort_keys=True)
        mark = "" if sig == prev_sig else " *moved*"
        prev_sig = sig
        line = one_line(d) + mark
        print(line, flush=True)
        with open(args.sidecar, "a") as f:
            f.write(json.dumps(snapshot(d)) + "\n")


if __name__ == "__main__":
    main()
