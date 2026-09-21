#!/usr/bin/env python3
"""aim-verify: deterministic proof that the camera-aim pipeline works.

Ground truth = the game's own ray trace, not pixel heuristics. After
orienting the player with `look`, GET /polis/look ray-traces from the
player's actual eye/orientation and reports the exact block the crosshair
hits. A correct aim hits the marker.

Lessons baked in (all found the hard way, 2026-09-21):
  * Marker must be SOLID: RayTraceForSelection skips decorative blocks
    (fire renders but is invisible to the ray trace). rock-granite works.
  * The marker must be a 1x3x3 wall: a 1-block target 20m away subtends
    only ~3deg of pitch (scan steps skip it), and the aim ray drifts in z
    as pitch changes (a 1-cell-wide target is missed by centimetres).
  * Center the player on the marker's z slab before scanning: a ray that
    travels exactly along a cell boundary is aliasing-fragile in the DDA.
  * Pitch convention (decoded empirically): pi = level, increasing = down;
    lookVec = (sin(yaw)*cos(p-pi), -sin(p-pi), cos(yaw)*cos(p-pi)). The
    scan is +-12deg around the analytic prediction and the verdict is
    purely hit-based, so a different convention would just report
    "no hits" instead of a false pass.

Usage:
  aim-verify.py [x y z] [--harness http://127.0.0.1:8585] [--player uid]
                [--no-place] [--code rock-granite] [--outdir /tmp/aim]
Exit 0 = some shot hit the marker wall; 1 = not verified.
"""
import argparse, base64, io, json, math, os, sys, time, urllib.parse, urllib.request

from PIL import Image


def http_get(url):
    with urllib.request.urlopen(url, timeout=25) as r:
        return r.read()


def harness_get(h, path):
    return json.loads(http_get(h + "/polis" + path))


def harness_cmd(h, cmd, args, uid):
    body = json.dumps({"cmd": cmd, "args": args, "context": {"playerUid": uid}}).encode()
    req = urllib.request.Request(h + "/polis/command", data=body,
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=15).read())


def aim(h, x, y, z, pitch, uid):
    return harness_cmd(h, "look", [str(x), str(y), str(z), f"{pitch:.4f}"], uid)


def crosshair(h, uid):
    q = urllib.parse.quote(uid, safe="")
    j = harness_get(h, "/look?uid=" + q)
    if "error" in j:
        raise RuntimeError(f"/polis/look failed: {j}")
    return j


def shot(h, x, y, z, yaw, pitch, uid):
    q = urllib.parse.quote(uid, safe="")
    j = json.loads(http_get(f"{h}/polis/observer-screenshot?x={x}&y={y}&z={z}"
                            f"&yaw={yaw:.4f}&pitch={pitch:.4f}&playerUid={q}"))
    if not j.get("ok"):
        return None
    return base64.b64decode(j["base64Png"])


def wall_cells(lx, ly, lz, user):
    if user:
        return {(lx, ly, lz)}
    # 4 cells deep in z (dz -1..2): the aim ray drifts up to ~1.5 cells in z
    # over 20 blocks (yaw/pitch coupling); the extra rear cell keeps the drift
    # inside the wall even when the DDA aliases at a boundary.
    return {(lx, ly + dy, lz - 1 + dz) for dy in range(3) for dz in range(4)}


def wall_center(lx, ly, lz, user):
    if user:
        return (lx + 0.5, ly + 0.5, lz + 0.5)
    return (lx + 0.5, ly + 1.5, lz + 0.5)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("coords", nargs="*", help="marker x y z (omit: auto-place 20 blocks ahead)")
    ap.add_argument("--harness", default=os.environ.get("HARNESS", "http://127.0.0.1:8585"))
    ap.add_argument("--player", default=None)
    ap.add_argument("--no-place", action="store_true")
    ap.add_argument("--code", default="rock-granite",
                    help="marker block code; must be SOLID (fire is decorative, rays pass through)")
    ap.add_argument("--outdir", default="/tmp/aim")
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    h = args.harness.rstrip("/")

    if args.player:
        uid = args.player
    else:
        players = harness_get(h, "/players")
        plist = players if isinstance(players, list) else players.get("players", [])
        plist = [p for p in plist if p.get("uid")]
        if not plist:
            sys.exit("no online player found")
        uid = plist[0]["uid"]
    me = harness_get(h, "/player?uid=" + urllib.parse.quote(uid, safe=""))
    if "error" in me:
        sys.exit(f"player not loaded: {me}")
    px, py, pz = me["pos"]
    orig_yaw, orig_pitch = me["yaw"], me["pitch"]
    orig_pos = [px, py, pz]
    user = bool(args.coords)
    print(f"player {me.get('name')} pos={me['pos']} orig yaw={orig_yaw:.4f} pitch={orig_pitch:.4f}",
          file=sys.stderr)

    if user:
        lx, ly, lz = (int(c) for c in args.coords[:3])
    elif args.no_place:
        sys.exit("no coords and --no-place: refuse to guess")
    else:
        lx, ly, lz = px + 20, py, pz
        cells = wall_cells(lx, ly, lz, False)
        for (bx, by, bz) in sorted(cells):
            r = harness_cmd(h, "setblock", [args.code, str(bx), str(by), str(bz)], uid)
            if not r.get("Ok"):
                sys.exit(f"marker placement failed at ({bx},{by},{bz}): {r.get('Message')}")
        print(f"placed {args.code} wall x={lx} y={ly}..{ly + 2} z={lz - 1}..{lz + 2}", file=sys.stderr)

    cx, cy, cz = wall_center(lx, ly, lz, user)
    yaw = math.atan2(cx - px, cz - pz)
    print(f"marker center=({cx},{cy},{cz}) yaw={yaw:.4f}", file=sys.stderr)

    # Center the player on the marker's z slab (avoids DDA boundary aliasing)
    if not user:
        harness_cmd(h, "teleport", [uid, str(px), str(py), str(lz + 0.5)], uid)
    time.sleep(0.5)
    me = harness_get(h, "/player?uid=" + urllib.parse.quote(uid, safe=""))
    px, py, pz = me["pos"]

    # Analytic prediction + +-12deg in 3deg steps (convention: pi=level, +down)
    eye_y = py + 1.7
    dist = math.dist([px, pz], [cx, cz])
    pred = math.pi + math.atan2(eye_y - cy, dist)
    coarse = [pred + i * math.pi / 60 for i in range(-4, 5)]

    cells = wall_cells(lx, ly, lz, user)
    attempts, hits = [], []

    def try_pitch(pitch):
        r = aim(h, lx, ly, lz, pitch, uid)
        if not r.get("Ok"):
            print(f"pitch={math.degrees(pitch):7.2f}deg  aim failed: {r.get('Message')}",
                  file=sys.stderr)
            return
        j = crosshair(h, uid)
        bs = j.get("blockSelection")
        line = f"pitch={math.degrees(pitch):7.2f}deg  "
        if bs:
            line += f"block={bs.get('code')}@{bs['pos']}"
        else:
            lv = j.get("lookVec")
            line += f"no-block lookVec={[round(v, 3) for v in lv] if lv else None}"
        if j.get("entitySelection"):
            line += f"  entity={j['entitySelection'].get('code')}"
        print(line, file=sys.stderr)
        hit_cell = tuple(bs["pos"]) if bs else None
        d = math.dist(bs["hit"], [cx, cy, cz]) if bs else None
        attempts.append([pitch, hit_cell is not None, d])
        if bs and tuple(bs["pos"]) in cells:
            hits.append([d, pitch])

    for p in coarse:
        try_pitch(p)

    if hits:
        best = min(hits)[1]
        for dp in (-0.026, 0.026):  # +-1.5deg
            try_pitch(best + dp)
    elif any(a[1] for a in attempts):
        # closest-miss refinement (for the report; never a pass on its own)
        cand = min((a for a in attempts if a[1]), key=lambda a: a[2] or 99.0)[0]
        for dp in (-0.026, 0.026):
            try_pitch(cand + dp)

    # Restore position + orientation (safety)
    harness_cmd(h, "teleport", [uid, str(orig_pos[0]), str(orig_pos[1]), str(orig_pos[2])], uid)
    aim(h, orig_pos[0] + math.sin(orig_yaw) * 20, orig_pos[1],
        orig_pos[2] + math.cos(orig_yaw) * 20, orig_pitch, uid)

    if hits:
        hits.sort()
        d, bp = hits[0]
        print(f"best: pitch={bp:.4f} ({math.degrees(bp):.2f}deg, pred "
              f"{math.degrees(pred):.2f}deg) hitDist-to-center={d:.3f}", file=sys.stderr)
        ev = f"{args.outdir}/aim-{int(time.time())}.png"
        r = aim(h, lx, ly, lz, bp, uid)
        data = shot(h, px, py, pz, yaw, bp, uid) if r.get("Ok") else None
        if data:
            open(ev, "wb").write(data)
        harness_cmd(h, "teleport", [uid, str(orig_pos[0]), str(orig_pos[1]), str(orig_pos[2])], uid)
        aim(h, orig_pos[0] + math.sin(orig_yaw) * 20, orig_pos[1],
            orig_pos[2] + math.cos(orig_yaw) * 20, orig_pitch, uid)
        print(json.dumps({"verified": True, "marker": [lx, ly, lz], "marker_center": [cx, cy, cz],
                          "yaw": yaw, "best_pitch": bp, "predicted_pitch": pred,
                          "hit_distance": d, "evidence": ev}, indent=2))
        sys.exit(0)

    print(json.dumps({"verified": False, "marker": [lx, ly, lz], "yaw": yaw,
                      "predicted_pitch": pred,
                      "attempts": [[p, b, d] for p, b, d in attempts]}, indent=2))
    sys.exit(1)


if __name__ == "__main__":
    main()
