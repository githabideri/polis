#!/usr/bin/env python3
"""Material capability probe (R2 design doc §12.8, 2026-09-28).

Answers, against the LIVE game, the questions the planner validator
(P4) must not guess:

  1. What do NATURAL granite blocks scan as? (vs set-placed
     rock-granite - the 1.22 fixture marker)
  2. What exactly does mining a natural granite drop into inventory?
     (item code, quantity)
  3. Does `place` accept that item representation, and what block code
     does the placed stone scan as?

Run it from the game box:  python3 scripts/probe-material.py
Read-only on the world except: it mines ONE natural granite cell and
places ONE block (both recorded in the JSON output for cleanup).
"""
import json
import os
import sys
import time
import urllib.request

HARNESS = os.environ.get("POLIS_HARNESS", "http://127.0.0.1:8585")
UID = "probe-" + time.strftime("%H%M%S")


def cmd(c, args=(), bot=None, timeout=60):
    ctx = {"playerUid": UID}
    if bot is not None:
        ctx["botId"] = int(bot)
    req = urllib.request.Request(
        HARNESS + "/polis/command",
        data=json.dumps({"cmd": c, "args": list(args),
                         "context": ctx}).encode(),
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"Ok": False, "error": str(e)}


def state(bot):
    """GET /polis/state?botId=N - same shape v5 uses (top-level Items)."""
    for _ in range(10):
        try:
            with urllib.request.urlopen(
                    HARNESS + "/polis/state?botId=%d" % int(bot),
                    timeout=15) as r:
                d = json.loads(r.read())
            if "Bot" in d:
                return d
        except Exception:
            pass
        time.sleep(1)
    return {}


def scan(x1, y1, z1, x2, y2, z2):
    r = cmd("scan", [str(x1), str(y1), str(z1), str(x2), str(y2), str(z2)],
            timeout=120)
    return (r.get("Data") or {}).get("blocks", [])


def main():
    out = {"probe": "material capability", "ts": time.strftime("%F %T")}
    # 1) wide scan around the testbed spawn (511997, 512019-ish)
    blocks = scan(511970, 2, 511990, 512035, 12, 512055)
    codes = {}
    for b in blocks:
        c = b.get("code") or "?"
        codes.setdefault(c, []).append(b.get("pos"))
    out["scan_total_blocks"] = len(blocks)
    out["codes"] = {k: {"count": len(v),
                        "sample": v[:3]}
                    for k, v in sorted(codes.items())}
    granite = {k: v for k, v in codes.items() if "granite" in k}
    out["granite_codes"] = {k: len(v) for k, v in granite.items()}
    natural = {}
    for k, v in granite.items():
        if k != "game:rock-granite":
            natural[k] = v
    out["natural_candidates"] = {k: v[:5] for k, v in natural.items()}
    print(json.dumps(out["codes"], indent=1))
    print("GRANITE:", {k: len(v) for k, v in granite.items()})
    print("NATURAL:", {k: v[:5] for k, v in natural.items()})

    target = None
    for k, v in sorted(natural.items()):
        if v:
            target = (k, v[0])
            break
    if not target:
        # fall back: any rock-granite that is NOT on a known fixture row
        for p in granite.get("game:rock-granite", []):
            if not (p[0] in range(512000, 512012) and p[2] in range(512015, 512025)):
                target = ("game:rock-granite (unfixed cell)", p)
                break
    out["mined_cell"] = target
    if not target:
        out["verdict"] = "no granite found in the probe region"
        print(json.dumps(out, indent=1))
        return

    code, cell = target
    # 2) mine it and diff the inventory
    r = cmd("spawn")
    bot = (r.get("Data") or {}).get("id")
    out["bot"] = bot
    cmd("give", ["pickaxe-iron", "1"], bot)
    pre = state(bot).get("Items") or []
    g = cmd("goto", [str(cell[0]), str(cell[1]), str(cell[2])], bot, timeout=90)
    out["goto"] = g.get("Message") or g.get("error")
    m = cmd("mine", [str(cell[0]), str(cell[1]), str(cell[2]), "true"], bot,
            timeout=120)
    out["mine_msg"] = m.get("Message") or m.get("error")
    t0 = time.time()
    while time.time() - t0 < 30:
        if not any(b.get("code") == code and b.get("pos") == list(cell)
                   for b in scan(cell[0] - 1, 2, cell[2] - 1,
                                 cell[0] + 1, cell[2] + 1, cell[2] + 1)):
            break
        time.sleep(2)
    post = state(bot).get("Items") or []

    def norm(items):
        d = {}
        for i in items:
            c = i.get("Code")
            d[c] = d.get(c, 0) + (i.get("Count") or 1)
        return d
    pre_n, post_n = norm(pre), norm(post)
    delta = {}
    for c in set(pre_n) | set(post_n):
        if pre_n.get(c, 0) != post_n.get(c, 0):
            delta[c] = {"before": pre_n.get(c, 0), "after": post_n.get(c, 0)}
    out["inventory_delta"] = delta
    out["post_items"] = post_n
    new_item = next((c for c, d in delta.items() if d["after"] > d["before"]),
                    None)
    out["dropped_item"] = new_item
    print("INVENTORY DELTA:", delta)

    # 3) place it at a spare cell and see what the block scans as
    if new_item:
        place_cell = (cell[0] + 3, cell[1] - 1, cell[2] + 1)
        # place <itemcode> x y z finds the item in the bot's inventory
        # itself (v5's place_block branch does the same - no select)
        p = cmd("place", [new_item, str(place_cell[0]), str(place_cell[1]),
                          str(place_cell[2])], bot, timeout=180)
        out["place_msg"] = p.get("Message") or p.get("error")
        t0 = time.time()
        placed_as = None
        while time.time() - t0 < 60:
            bs = scan(place_cell[0] - 1, 2, place_cell[2] - 1,
                      place_cell[0] + 1, place_cell[2] + 1, place_cell[2] + 1)
            hit = [b.get("code") for b in bs
                   if b.get("pos") == list(place_cell)
                   and b.get("code") not in (None, "", "air", "game:air",
                                             "game:soil-medium-none",
                                             "game:soil-medium-normal")]
            if hit:
                placed_as = hit[0]
                break
            time.sleep(3)
        out["placed_cell"] = list(place_cell)
        out["placed_scans_as"] = placed_as
        print("PLACED:", new_item, "->", placed_as)
        cmd("despawn", [], str(bot))
    out["verdict"] = ("natural granite: %r mines to %r; place accepts %r -> "
                      "%r" % (code, new_item, new_item,
                               out.get("placed_scans_as")))
    print(json.dumps(out, indent=1))
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "data", "material-probe-%s.json" % time.strftime("%Y-%m-%d"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(out, open(path, "w"), indent=1)
    print("wrote", path)


if __name__ == "__main__":
    main()
