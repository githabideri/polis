#!/usr/bin/env python3
"""
r2-progression.py - the early-game ladder runner.

Runs a stages file (docs/design/early-game-progression-test.md) against a
LIVE game world: each stage runs its jobs (a chain via r2-live-mission.py
or raw job files), then its EXIT ORACLE is checked against world state
(zones, blocks, containers, inventories, vitals). The runner fails fast:
a stage that does not pass stops the ladder and the summary says why.
The exit oracle is the gate - a job run is only trusted for what its
exit state proves.

    python3 r2-progression.py stages-file.json [--output summary.json]
    [--start P3] [--stop-after P4] [--harness http://127.0.0.1:8585]

Stage shape (stages file):
  {
    "world": "polis-survival-5",
    "zones": [{"name": "base", "box": [x1, y1, z1, x2, y2, z2]}],
    "stages": [
      {"id": "P0", "desc": "...",
       "pre":  {"zones": ["base"]},          # assumptions; BLOCKED if unmet
       "chain": "pots",                       # OR "jobs": [ {...} ]
       "params": {"zone": "base"},
       "exit": {"any": [ {"any_bot_sat": 1400},
                         {"container_items": {"at": [x,y,z],
                                              "code": "crucible-*", "min": 1}} ],
                "all": [ {"zone": "base"} ]}}
    ]
  }

Exit-oracle predicates (all read LIVE state; none read mission claims):
  zone <name>            zone exists in the live world
  zones [a, b]           all listed zones exist
  box_present [x,y,z]    that cell is a groundstorage block
  block_present [x,y,z]  non-air block at that cell
  block_code [x,y,z] <code-prefix>   block matches the prefix
  block_count <box> <code-prefix> <min>   count cells in a box
  container_items {at: [x,y,z], code: <prefix>, min: n}
  item_count {code: <prefix>, min: n, where: "bots"|"zone:<name>"|"all"}
  any_bot_sat <n>        at least one bot's satiety >= n
  all_bots_sat <n>       every bot's satiety >= n

Oracle values: block/item codes may use a single trailing * wildcard
(prefix match). Booms from the mission run's `measured` data are NOT
used here - the oracle re-reads the world (that is the whole point).
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

HARNESS = os.environ.get("POLIS_HARNESS", "http://127.0.0.1:8585")
KEY = "cmd"
HERE = os.path.dirname(os.path.abspath(__file__))
R2 = os.path.dirname(HERE)


def _jget(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read())


def _post(url, payload):
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


class World:
    def __init__(self, base, world_name):
        self.base = base.rstrip("/")
        self.world_name = world_name
        self.zones = self._read_zones()

    def _read_zones(self):
        w = _jget(self.base + "/polis/world?key=" + KEY).get("Data") or {}
        out = {}
        for z in w.get("zones") or []:
            out[z.get("name")] = z
        return out

    def command(self, cmd, *args):
        return _post(self.base + "/polis/command?key=" + KEY,
                     {"cmd": cmd, "args": [str(a) for a in args]})

    def scan_box(self, box, include_air=False):
        args = list(box)
        if include_air:
            args.append("--include-air")
        r = self.command("scan", *args)
        return (r.get("Data") or {}).get("blocks") or []

    def bots(self):
        return _jget(self.base + "/polis/bots?key=" + KEY).get("Data") or {}

    def vitals(self):
        r = self.command("vitals")
        return (r.get("Data") or {})


def code_matches(actual, pattern):
    if pattern is None or pattern == "":
        return True
    if actual is None:
        return False
    a = actual
    if a.startswith("game:"):
        a2 = a[len("game:"):]
        p2 = pattern[len("game:"):] if pattern.startswith("game:") else pattern
        if a2.startswith(p2.rstrip("*")):
            return True
    return a.startswith(pattern.rstrip("*"))


def check_zone(w, val):
    return val in w.zones


def check_zones(w, val):
    return all(v in w.zones for v in val)


def check_block_present(w, val):
    cell, _ = _two(val)
    r = w.command("cell_blocks", *cell)
    blocks = (r.get("Data") or {}).get("blocks") or []
    return len(blocks) > 0 and blocks[0].get("code") != "game:air"


def check_block_code(w, val):
    cell, pattern = _two(val)
    r = w.command("cell_blocks", *cell)
    blocks = (r.get("Data") or {}).get("blocks") or []
    if not blocks:
        return False
    return code_matches(blocks[0].get("code"), pattern)


def _two(val):
    if isinstance(val, (list, tuple)):
        return val[0], val[1] if len(val) > 1 else None
    raise ValueError("expected [cell, pattern]")


def check_box_present(w, val):
    r = w.command("cell_blocks", *val)
    blocks = (r.get("Data") or {}).get("blocks") or []
    return len(blocks) > 0 and code_matches(blocks[0].get("code"), "game:groundstorage")


def check_block_count(w, val):
    box, pattern, minimum = val[0], val[1], int(val[2])
    blocks = w.scan_box(box, include_air=False)
    n = sum(1 for b in blocks if code_matches(b.get("code"), pattern))
    return n >= minimum, "matched %d (need %d)" % (n, minimum)


def check_container_items(w, val):
    cell = val["at"]
    pattern = val.get("code")
    minimum = int(val.get("min", 1))
    r = w.command("container-contents", *cell)
    slots = (r.get("Data") or {}).get("slots") or []
    n = 0
    for s in slots:
        if s.get("empty"):
            continue
        if code_matches(s.get("code"), pattern):
            n += s.get("n", 1)
    return n >= minimum, "found %d (need %d)" % (n, minimum)


def check_item_count(w, val):
    code = val["code"]
    minimum = int(val.get("min", 1))
    where = val.get("where", "all")
    total = 0
    # bots' cargo
    if where in ("bots", "all"):
        for bid, rec in w.bots().items():
            r = w.command("inventory", bid)
            for it in (r.get("Data") or {}).get("items") or []:
                if code_matches(it.get("code"), code):
                    total += it.get("qty", 1)
    # zone boxes + containers inside zone boxes
    if where in ("all",) or where.startswith("zone:"):
        names = w.zones.keys() if where == "all" else [where[5:]]
        for name in names:
            z = w.zones[name]
            box = z.get("box")
            if not box:
                continue
            blocks = w.scan_box(box, include_air=True)
            for b in blocks:
                if code_matches(b.get("code"), "game:groundstorage"):
                    r = w.command("container-contents", b["x"], b["y"], b["z"])
                    for s in (r.get("Data") or {}).get("slots") or []:
                        if not s.get("empty") and code_matches(s.get("code"), code):
                            total += s.get("n", 1)
    # world containers (kiln holes etc. are not in zone boxes - callers
    # use container_items for those)
    return total >= minimum, "found %d (need %d)" % (total, minimum)


def check_any_bot_sat(w, val):
    v = w.vitals()
    sats = [x.get("sat") for x in (v.get("bots") or [])
            if isinstance(x.get("sat"), (int, float))]
    return bool(sats) and max(sats) >= val, "max sat %s (need %s)" % (sats and max(sats), val)


def check_all_bots_sat(w, val):
    v = w.vitals()
    sats = [x.get("sat") for x in (v.get("bots") or [])
            if isinstance(x.get("sat"), (int, float))]
    return bool(sats) and min(sats) >= val, "min sat %s (need %s)" % (sats and min(sats), val)


ORACLES = {
    "zone": check_zone,
    "zones": check_zones,
    "block_present": check_block_present,
    "block_code": check_block_code,
    "box_present": check_box_present,
    "block_count": check_block_count,
    "container_items": check_container_items,
    "item_count": check_item_count,
    "any_bot_sat": check_any_bot_sat,
    "all_bots_sat": check_all_bot_sat,
}


def eval_oracle(w, spec, label):
    """returns (ok, detail). spec: {"all": [preds]} and/or {"any": [preds]}"""
    results = []
    if "all" in spec:
        for pred in spec["all"]:
            ok, det = _one(w, pred)
            results.append((label + ":all", ok, det))
        if any(not ok for _, ok, _ in results):
            return False, _fmt(results)
    if "any" in spec:
        for pred in spec["any"]:
            ok, det = _one(w, pred)
            results.append((label + ":any", ok, det))
        if not any(ok for _, ok, _ in results):
            return False, _fmt(results)
    return True, _fmt(results) or "ok"


def _one(w, pred):
    for key, val in pred.items():
        fn = ORACLES.get(key)
        if fn is None:
            return False, "unknown oracle: " + key
        res = fn(w, val)
        if isinstance(res, tuple):
            return res
        return bool(res), ""
    return False, "empty predicate"


def _fmt(results):
    if not results:
        return ""
    bad = [d for _, ok, d in results if not ok]
    return "; ".join(bad) if bad else "all predicates passed (%d)" % len(results)


def run_jobs(w, stage, output_dir):
    if stage.get("chain"):
        params = stage.get("params") or {}
        cmd = [sys.executable, os.path.join(HERE, "r2-live-mission.py"),
               "chain", stage["chain"]]
        for k, v in params.items():
            cmd += ["--" + k, str(v)]
        cmd += ["--world-name", w.world_name]
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=6000)
        out = p.stdout.strip()
        ok = p.returncode == 0
        return ok, ("chain %s rc=%d out=%s" % (stage["chain"], p.returncode,
                     out[-400:] if out else p.stderr[-400:]))
    jobs = stage.get("jobs")
    if jobs is None:
        return True, "no jobs (pure-oracle stage)"
    payload = {"world": w.world_name, "jobs": jobs,
               "params": stage.get("params") or {}}
    jf = os.path.join(output_dir, "ladder-" + stage["id"] + ".json")
    with open(jf, "w") as f:
        json.dump(payload, f, indent=2)
    p = subprocess.run([sys.executable, os.path.join(HERE, "r2-live-mission.py"),
                        "mission", jf, "--world-name", w.world_name,
                        "--output", os.path.join(output_dir, stage["id"] + ".run.json")],
                       capture_output=True, text=True, timeout=6000)
    return p.returncode == 0, ("jobs rc=%d out=%s" % (p.returncode,
                     (p.stdout or p.stderr)[-400:]))


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(2)
    stages_file = args[0]
    opts = {"output": None, "start": None, "stop_after": None,
            "harness": HARNESS, "world": None}
    i = 1
    while i < len(args):
        if args[i] == "--output":
            opts["output"] = args[i + 1]; i += 2
        elif args[i] == "--start":
            opts["start"] = args[i + 1]; i += 2
        elif args[i] == "--stop-after":
            opts["stop_after"] = args[i + 1]; i += 2
        elif args[i] == "--harness":
            opts["harness"] = args[i + 1]; i += 2
        elif args[i] == "--world":
            opts["world"] = args[i + 1]; i += 2
        else:
            print("unknown arg:", args[i]); sys.exit(2)

    with open(stages_file) as f:
        spec = json.load(f)
    world_name = opts["world"] or spec.get("world")
    w = World(opts["harness"], world_name)
    if world_name and w.zones and not any(
            z.get("name") == "base" for z in w.zones.values()):
        print("warning: world %s has no base zone yet" % world_name)

    # the stages file may DECLARE zones the world lacks; create them
    # (a P0-style precondition of the ladder, not a stage claim)
    for z in spec.get("zones") or []:
        if z["name"] not in w.zones:
            r = w.command("zone", z["name"], "create", *z["box"])
            print("zone %s: %s" % (z["name"], r.get("Message")))
            w.zones = w._read_zones()

    output_dir = os.path.join(R2, "runs", "ladder-" + time.strftime("%Y%m%d-%H%M"))
    os.makedirs(output_dir, exist_ok=True)

    summary = {"world": world_name, "date": time.strftime("%Y-%m-%d %H:%M UTC",
                 time.gmtime()), "stages": [],
               "overall": "pending"}
    started = opts["start"] is None
    stopped = False
    for stage in spec["stages"]:
        sid = stage["id"]
        if not started:
            if sid == opts["start"]:
                started = True
            else:
                continue
        if stopped:
            break
        print("\n=== stage %s: %s" % (sid, stage.get("desc", "")))
        entry = {"id": sid, "desc": stage.get("desc", ""),
                 "status": "pending", "detail": ""}
        # preconditions
        if stage.get("pre"):
            ok, det = eval_oracle(w, stage["pre"], sid + ".pre")
            if not ok:
                entry.update(status="BLOCKED", detail=det)
                summary["stages"].append(entry)
                summary["overall"] = "blocked at " + sid
                print("  BLOCKED: " + det)
                break
            print("  pre ok")
        t0 = time.time()
        ok, det = run_jobs(w, stage, output_dir)
        ms = int((time.time() - t0) * 1000)
        if not ok:
            entry.update(status="FAILED", detail=det, ms=ms)
            summary["stages"].append(entry)
            summary["overall"] = "failed at " + sid
            print("  FAILED: " + det)
            break
        print("  jobs ok in %d ms" % ms)
        # exit oracle
        if stage.get("exit"):
            ok, det = eval_oracle(w, stage["exit"], sid + ".exit")
            if not ok:
                entry.update(status="ORACLE-FAIL", detail=det, ms=ms)
                summary["stages"].append(entry)
                summary["overall"] = "oracle failed at " + sid
                print("  ORACLE-FAIL: " + det)
                break
            print("  exit ok: " + det)
        entry.update(status="OK", detail=det, ms=ms)
        summary["stages"].append(entry)
        if sid == opts["stop_after"]:
            stopped = True
    if summary["overall"] == "pending":
        summary["overall"] = "PASS (%d stages)" % len(summary["stages"])
    out = opts["output"] or os.path.join(output_dir, "ladder-summary.json")
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w") as f:
        json.dump(summary, f, indent=2)
    print("\n=== ladder: " + summary["overall"])
    print("summary: " + out)
    sys.exit(0 if summary["overall"].startswith("PASS") else 1)


if __name__ == "__main__":
    main()
