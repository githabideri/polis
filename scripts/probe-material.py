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
# a REAL player uid is required - the harness resolves the command
# context against registered players (a fabricated uid cannot spawn)
UID = os.environ.get("POLIS_UID", "d4pJ+Ty1RgaBHrQgQEV8z27E")


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


def inventory(state_resp):
    """The bot's inventory the way the game keeps it: hands + cargo grid
    (the state's top-level Items are GROUND item entities, not the bot's
    inventory - 2026-09-28 probe finding)."""
    b = (state_resp or {}).get("Bot") or {}
    out = {}
    for k in ("RightHand", "LeftHand"):
        it = b.get(k)
        if it and it.get("Code"):
            out[it["Code"]] = out.get(it["Code"], 0) + (it.get("Qty") or 1)
    for it in (b.get("Backpack") or []):
        if it.get("Code"):
            out[it["Code"]] = out.get(it["Code"], 0) + (it.get("Qty") or 1)
    return out


def state(bot):
    """GET /polis/state?botId=N - same shape v5 uses (Bot + ground Items)."""
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


def goto_wait(bot, cell, timeout=60):
    """v5's goto semantics: full arg list + poll LastAction until the
    walk settles (the command returns as soon as the walk STARTS)."""
    r = cmd("goto", [str(cell[0]), str(cell[1]), str(cell[2]), "true",
                     "0.02", "true"], bot, timeout=timeout)
    t0 = time.time()
    msg = r.get("Message") or r.get("error")
    while time.time() - t0 < timeout:
        la = state(bot).get("LastAction") or {}
        if la.get("Name") == "goto" and la.get("Ok") is not None:
            return la.get("Msg") or msg
        time.sleep(0.5)
    return msg + " (goto timeout)"


def main():
    out = {"probe": "material capability", "ts": time.strftime("%F %T")}
    # 1) wide scan around the testbed (surface AND the layer below it:
    # the flat testbed's stone, if any, sits at/below y=2)
    blocks = scan(511900, 0, 511950, 512100, 15, 512120)
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

    target = None  # (block_code, cell, note)
    for k, v in sorted(natural.items()):
        if v:
            target = (k, v[0], "natural")
            break
    if not target:
        # fall back: any rock-granite that is NOT on a known fixture row
        # (1.22: set-placed and natural granite share the code - the probe
        # below tells us whether the mined item behavior matches)
        for p in granite.get("game:rock-granite", []):
            if not (p[0] in range(512000, 512012) and p[2] in range(512015, 512025)):
                target = ("game:rock-granite", p, "non-fixture cell")
                break
    out["mined_cell"] = list(target) if target else None
    if not target:
        out["verdict"] = "no granite found in the probe region"
        print(json.dumps(out, indent=1))
        return

    code, cell, note = target
    # prefer ground-level (y==3) cells - the stable targets (v5's fixture
    # markers sit at ground level and mine cleanly)
    pool = natural.get(code) or ([cell] if note != "natural" else [])
    alts = [v for v in pool if v[1] == 3]
    if not alts and note != "natural":
        alts = [v for v in granite.get("game:rock-granite", [])
                if v[1] == 3
                and not (v[0] in range(512000, 512012)
                         and v[2] in range(512015, 512025))]
        if alts:
            code = "game:rock-granite"
    if alts and alts[0] != cell:
        cell = alts[0]
        note += ", re-targeted to ground level"
        out["mined_cell"] = [code, list(cell), note]
        print("re-targeted to ground-level cell", cell)
    # 2) mine it and diff the inventory - v5's approach pattern: walk a
    # neighbour cell first, then mine (the mine range is 4.5 blocks)
    r = cmd("spawn")
    bot = (r.get("Data") or {}).get("id")
    out["bot"] = bot
    cmd("give", ["pickaxe-iron", "1"], bot)
    pre = inventory(state(bot))
    neighbours = [(cell[0] + 1, cell[1], cell[2]),
                  (cell[0] - 1, cell[1], cell[2]),
                  (cell[0], cell[1], cell[2] + 1),
                  (cell[0], cell[1], cell[2] - 1)]
    mine_msg = None
    for nb in neighbours:
        mine_msg = goto_wait(bot, nb)
        out["goto"] = mine_msg
        m = cmd("mine", [str(cell[0]), str(cell[1]), str(cell[2]),
                         "true"], bot, timeout=120)
        mine_msg = m.get("Message") or m.get("error")
        out["mine_msg"] = mine_msg
        if not mine_msg or "line of sight" not in mine_msg:
            break
    out["mine_msg"] = mine_msg
    t0 = time.time()
    while time.time() - t0 < 30:
        if not any(b.get("code") == code and b.get("pos") == list(cell)
                   for b in scan(cell[0] - 1, 2, cell[2] - 1,
                                 cell[0] + 1, cell[2] + 1, cell[2] + 1)):
            break
        time.sleep(2)
    post = inventory(state(bot))
    delta = {}
    for c in set(pre) | set(post):
        if pre.get(c, 0) != post.get(c, 0):
            delta[c] = {"before": pre.get(c, 0), "after": post.get(c, 0)}
    out["inventory_delta"] = delta
    out["post_items"] = post
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
