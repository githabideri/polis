#!/usr/bin/env python3
"""polisctl — CLI for the polis Vintage Story test harness.

Wraps the POST /polis/command API and the GET endpoints so an agent drives the
world with short, explicit commands instead of ad-hoc `curl | python3` one-liners.

The harness binds 127.0.0.1:8585 on the polis container only, so this must run
ON that container. Invoke from anywhere as:

    ssh <polis-host> 'polisctl <subcommand> …'

Time-of-day is first-class: `polisctl time <hour|preset>` drives the clock to a
target hour and freezes it there (deterministic lighting for screenshots). The
default target is the first online player; override with --uid.
"""
import sys, os, json, time, types, argparse, base64, math
import urllib.request

BASE = os.environ.get("POLIS_HARNESS", "http://127.0.0.1:8585")
PRESETS = {"dawn": 6.0, "sunrise": 6.0, "morning": 9.0, "noon": 12.0,
           "midday": 12.0, "afternoon": 15.0, "sunset": 18.0,
           "dusk": 19.5, "night": 0.5}


def _post(cmd, args, uid=None, timeout=30):
    ctx = {}
    if uid:
        ctx["playerUid"] = uid
    body = json.dumps({"cmd": cmd, "args": args, "context": ctx}).encode()
    req = urllib.request.Request(BASE + "/polis/command", data=body,
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _get(path, timeout=45):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        return json.load(r)


def _say(res):
    if not isinstance(res, dict):
        print(str(res)); return
    ok = res.get("ok", res.get("Ok"))
    msg = res.get("Message") or res.get("message")
    print(("OK  " if ok else "ERR ") + (msg or json.dumps(res)[:300]))


def _blocks(res):
    return (res.get("Data") or res).get("blocks") or []


def get_uid(a):
    if getattr(a, "uid", None):
        return a.uid
    try:
        d = _get("/polis/players")
        pl = d.get("Data", {}).get("players") or d.get("players") or []
        if pl:
            p = pl[0]
            return p.get("uid") or p.get("id") or p.get("playerUid")
    except Exception:
        pass
    return None


# ---- clock / time ----------------------------------------------------------
def cmd_clock(a):
    d = _get("/polis/clock")
    print("date=%s  hour=%.3f  speed=%s  moon=%s" % (
        d.get("date"), d.get("hourOfDay", -1), d.get("speedOfTime"),
        d.get("moonPhase")))


def cmd_time(a):
    t = a.target
    target = PRESETS[t] if isinstance(t, str) and t in PRESETS else float(t)
    # A daylock freeze sets CalendarSpeedMul=0, which settime alone cannot move —
    # clear it first (daylock off restores CalendarSpeedMul=0.5) or the clock stays put.
    _post("daylock", ["off"], a.uid)
    h0 = _get("/polis/clock").get("hourOfDay", 0)
    dist = (target - h0) % 24

    def freeze_at(tgt):
        s = int(tgt / 24 * 10000) - 40
        e = s + 420  # ~1h window; the daylock fast-forwards in and freezes
        _post("daylock", ["on", str(s), str(e)], a.uid)
        last = None
        for _ in range(12):
            time.sleep(2)
            h = _get("/polis/clock").get("hourOfDay", -1)
            if last is not None and abs(h - last) < 0.02:
                break
            last = h
        c = _get("/polis/clock")
        print("frozen  hour=%.2f  (target %.1f)  %s" % (
            c.get("hourOfDay", -1), tgt, c.get("date")))

    if dist < 0.2:
        freeze_at(target); return
    # pre-drive at a rate that lands within ~1h, then let daylock finish+freeze
    factor = max(3, min(40, int(dist * 1.5) + 3))
    _post("settime", [str(factor)], a.uid)
    for i in range(120):
        time.sleep(3)
        h = _get("/polis/clock").get("hourOfDay", 0)
        d2 = (target - h) % 24
        if i % 5 == 0:
            sys.stderr.write("\r  driving %.2f -> %.1f (dist %.2f)   " % (
                h, target, d2))
            sys.stderr.flush()
        if d2 < 1.0 or d2 > 23.0:
            break
    sys.stderr.write("\n")
    freeze_at(target)


# ---- movement / aim --------------------------------------------------------
def cmd_teleport(a):
    u = get_uid(a)
    args = [u, a.x, a.y, a.z]
    if a.yaw is not None:
        args.append(a.yaw)
    if a.pitch is not None:
        args.append(a.pitch)
    _say(_post("teleport", args, u))


def cmd_look(a):
    args = [a.x, a.y, a.z]
    if a.pitch is not None:
        args.append(a.pitch)
    _say(_post("look", args, get_uid(a)))


# ---- world query -----------------------------------------------------------
def cmd_scan(a):
    res = _post("scan", [a.x1, a.y1, a.z1, a.x2, a.y2, a.z2], get_uid(a))
    blocks = _blocks(res)
    if a.codes:
        seen = {}
        for b in blocks:
            c = b.get("code", "?")
            seen[c] = seen.get(c, 0) + 1
        for c, n in sorted(seen.items(), key=lambda kv: -kv[1]):
            print("  %-32s %d" % (c, n))
    else:
        for b in blocks:
            print("%s @ %s" % (b.get("code"), b.get("pos")))
    print("(%d blocks)" % len(blocks))


def cmd_map(a):
    """Column-height map over a footprint + interior-air check (house verifier)."""
    ox, oy, oz, w, d = (int(a.ox), int(a.oy), int(a.oz), int(a.w), int(a.d))
    # NOTE: the harness deserializes args as string[] — ints in the JSON body
    # fail the whole request silently (0 blocks). Keep these strings.
    res = _post("scan", [str(ox - 1), str(oy - 3), str(oz - 1),
                         str(ox + w), str(oy + 6), str(oz + d)], get_uid(a))
    cells = {}
    for b in _blocks(res):
        p = b.get("pos")
        if p:
            cells[(int(p[0]), int(p[1]), int(p[2]))] = b.get("code", "")
    def at(x, y, z):
        return cells.get((x, y, z), "air")
    print("column fill (rows=dz, cols=dx) above base y=%d; value = # solid in y+1..y+%d" % (oy, min(d, 5)))
    for dz in range(d):
        row = []
        for dx in range(w):
            n = sum(1 for dy in range(1, 6) if at(ox + dx, oy + dy, oz + dz) != "air")
            row.append("%d" % n)
        print("  dz=%d: %s" % (dz, " ".join(row)))
    ia = is_ = 0
    for dz in range(1, d - 1):
        for dx in range(1, w - 1):
            for dy in range(1, 4):
                if at(ox + dx, oy + dy, oz + dz) == "air":
                    ia += 1
                else:
                    is_ += 1
    print("interior: air=%d solid=%d  => %s" % (
        ia, is_, "HOLLOW (room)" if is_ == 0 else "SOLID (mound)"))


def cmd_setblock(a):
    _say(_post("setblock", [a.code, a.x, a.y, a.z], get_uid(a)))


# ---- player lifecycle (the human player starves when idle) -------------
def cmd_respawn(a):
    """Revive the (human) player. VS kills it at saturation 0; respawn restores
    health to max. hungerpause/give/eat are BOT-only, so this is the only lever
    on the human player — shoot within the short window before it re-starves."""
    u = get_uid(a)
    _say(_post("respawn", [u], u))


def cmd_godmode(a):
    """Pin-health god mode: pins maxhealth+currenthealth of every bot and the
    local player to 100000 every tick (counters damage AND starvation; a dead
    target is revived first). Not persisted — re-issue after a game restart.
    `godmode on|off [entityId]` (no id = all bots + first player)."""
    args = [a.onoff] + ([a.id] if a.id else [])
    _say(_post("godmode", args))


def cmd_sanity(a):
    """Temporal stability — 1.22's 'sanity' meter (the blue gear above the
    hotbar). The engine calls it SystemTemporalStability: per-player 0..1
    value in the watched attribute 'temporalStability'. Drains in unstable
    areas (~1%/7.5s) and near temporal rifts (~3%/s), recovers in stable
    areas (~1%/4s), clamped by active temporal storms; at 0 = 'Rust World'
    (damage + glitch overlay). Storms/rifts are scheduled on calendar days,
    so under daylock (frozen clock) a storm never ends and rifts never
    expire — use 'storms off' / 'rifts off' (persisted + live-cleared) to
    settle a wedged world.

    No args: status (per-player meter, storm state, rift count, config).
    <0-1> [player]: set + pin (re-asserted every second, godmode-style).
    off: release the pin.
    storms <off|veryrare|rare|sometimes|often>: world config (persisted);
    'off' also zeroes the live storm + broadcast (screen clears at once).
    rifts <off|invisible|visible>: world config (persisted); 'off' also
    wipes the existing rifts now.
    clear: wipe existing rifts without touching the config."""
    _say(_post("sanity", a.rest))


def cmd_gamemode(a):
    """Set the target player's VS game mode (the /gamemode path): 0=guest
    1=survival 2=creative 3=spectator, or by name. Creative is the proper
    god-mode for the HUMAN player (no hunger, no death, F3 fly/noclip).
    `gamemode <player> [mode]` — no mode = query the current one."""
    args = [a.player] + ([a.mode] if a.mode else [])
    _say(_post("gamemode", args))


def cmd_repin(a):
    """Re-assert the pilot pins after a game restart (godmode/sanity/creative
    and the clock do not persist across restarts): godmode all bots + player,
    sanity pinned, player creative, noon. Optional `x y z` teleports the
    player (after a restart it returns to world spawn). The standard
    follow-up to a cold-stack reset (xvnc + vsgame restart) when the
    client entity pass has died (bots invisible, see chunkprobe)."""
    uid = get_uid(a)
    _say(_post("godmode", ["on"]))
    if uid:
        cmd_sanity(types.SimpleNamespace(rest=["100", uid]))
        cmd_gamemode(types.SimpleNamespace(player=uid, mode="creative"))
    cmd_time(types.SimpleNamespace(target="noon", uid=None))
    if a.rest:
        if len(a.rest) != 3:
            print("repin: teleport target needs exactly x y z"); sys.exit(2)
        cmd_teleport(types.SimpleNamespace(x=a.rest[0], y=a.rest[1], z=a.rest[2],
                                           yaw=None, pitch=None, uid=None))


# ---- screenshots -----------------------------------------------------------
def _capture(a):
    u = get_uid(a)
    if getattr(a, "respawn", False):
        _post("respawn", [u], u)  # revive if it starved while we set up
        time.sleep(1)
    _post("teleport", [u, a.x, a.y, a.z, a.yaw, a.pitch], u)
    time.sleep(2)
    d = _get("/polis/cine-screenshot?playerUid=%s&yaw=%s&pitch=%s&frames=4"
             % (u, a.yaw, a.pitch))
    if not d.get("ok"):
        print("capture failed:", d); sys.exit(1)
    raw = base64.b64decode(d.get("base64") or d.get("base64Png"))
    out = os.path.join(a.dir, a.name + ".png")
    os.makedirs(a.dir, exist_ok=True)
    open(out, "wb").write(raw)
    print(out)


def cmd_shot(a):
    _capture(a)


def _aim(ex, ey, ez, tx, ty, tz):
    """yaw/pitch (radians) to look from eye to target. Convention (verified):
    forward = (-cos p*sin y, sin p, -cos p*cos y); yaw 0 = -Z, increases LEFT."""
    ex, ey, ez = float(ex), float(ey), float(ez)
    tx, ty, tz = float(tx), float(ty), float(tz)
    dx, dy, dz = tx - ex, ty - ey, tz - ez
    ln = math.sqrt(dx*dx + dy*dy + dz*dz)
    pitch = math.asin(max(-1.0, min(1.0, dy / ln)))
    yaw = math.atan2(-dx, -dz)
    return yaw, pitch


def cmd_shotat(a):
    """Photograph a target from a vantage: teleport to the vantage, compute the
    yaw/pitch that looks at the target (callers name geometry, not radians),
    cine-screenshot, save. The reliable deterministic-capture CLI surface."""
    u = get_uid(a)
    if getattr(a, "respawn", False):
        _post("respawn", [u], u)
        time.sleep(1)
    yaw, pitch = _aim(a.vx, a.vy, a.vz, a.tx, a.ty, a.tz)
    _post("teleport", [u, a.vx, a.vy, a.vz, yaw, pitch], u)
    time.sleep(2)
    d = _get("/polis/cine-screenshot?playerUid=%s&yaw=%s&pitch=%s&frames=15"
             % (u, yaw, pitch))
    if not d.get("ok"):
        print("capture failed:", d); sys.exit(1)
    raw = base64.b64decode(d.get("base64") or d.get("base64Png"))
    out = os.path.join(a.dir, a.name + ".png")
    os.makedirs(a.dir, exist_ok=True)
    open(out, "wb").write(raw)
    print("%s  (aim yaw=%.3f pitch=%.3f)" % (out, yaw, pitch))


def cmd_pano(a):
    """Panorama sweep: n evenly-spaced yaw shots around the player's current
    (or teleported) position, same-height pitch. Saves <dir>/<name>_p<i>.png
    and prints each path. --sheet renders a contact sheet if PIL is present.
    Use to scan for entities/structures in all directions from one spot."""
    u = get_uid(a)
    if a.x is not None:
        _post("teleport", [u, a.x, a.y, a.z, 0, 0], u)
        time.sleep(2)
    paths = []
    for i in range(a.n):
        yaw = 2.0 * math.pi * i / a.n
        d = _get("/polis/cine-screenshot?playerUid=%s&yaw=%s&pitch=%s&frames=4"
                 % (u, yaw, a.pitch))
        if not d.get("ok"):
            print("capture %d failed: %s" % (i, d)); sys.exit(1)
        raw = base64.b64decode(d.get("base64") or d.get("base64Png"))
        os.makedirs(a.dir, exist_ok=True)
        p = os.path.join(a.dir, "%s_p%d.png" % (a.name, i))
        open(p, "wb").write(raw)
        paths.append(p)
        print(p)
    if a.sheet:
        try:
            from PIL import Image
            ims = [Image.open(p).resize((480, 270)) for p in paths]
            cols = 2
            sheet = Image.new("RGB", (480 * cols, 270 * ((len(ims) + cols - 1) // cols)))
            for n_, im in enumerate(ims):
                sheet.paste(im, ((n_ % cols) * 480, (n_ // cols) * 270))
            sheet.save(os.path.join(a.dir, a.name + "_sheet.png"))
            print(os.path.join(a.dir, a.name + "_sheet.png"))
        except ImportError:
            print("# sheet skipped (PIL not installed on this machine)")


def cmd_players(a):
    d = _get("/polis/players")
    pl = d.get("Data", {}).get("players") or d.get("players") or []
    for p in pl:
        print("%-16s uid=%s  pos=%s" % (
            p.get("name") or p.get("uid"), p.get("uid"), p.get("pos")))


def cmd_bots(a):
    d = _get("/polis/bots")
    bs = d.get("Data", {}).get("bots") or d.get("bots") or []
    for b in bs[:40]:
        print("%-16s %s  sat=%s" % (b.get("uid"), b.get("name"), b.get("saturation")))
    print("(%d bots)" % len(bs))


def cmd_cmd(a):
    _say(_post(a.name, a.args, get_uid(a)))


def main():
    global BASE
    ap = argparse.ArgumentParser(prog="polisctl", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--uid", default=None, help="target player/bot uid (default: first online)")
    ap.add_argument("--base", default=None, help="harness base URL (default 127.0.0.1:8585)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("clock").set_defaults(fn=cmd_clock)

    p = sub.add_parser("time", help="drive the clock to an hour and freeze (presets: "
                      + ", ".join(PRESETS) + ")")
    p.add_argument("target"); p.set_defaults(fn=cmd_time)

    p = sub.add_parser("teleport")
    p.add_argument("x"); p.add_argument("y"); p.add_argument("z")
    p.add_argument("yaw", nargs="?"); p.add_argument("pitch", nargs="?")
    p.set_defaults(fn=cmd_teleport)

    p = sub.add_parser("look")
    p.add_argument("x"); p.add_argument("y"); p.add_argument("z")
    p.add_argument("pitch", nargs="?")
    p.set_defaults(fn=cmd_look)

    p = sub.add_parser("scan")
    p.add_argument("x1"); p.add_argument("y1"); p.add_argument("z1")
    p.add_argument("x2"); p.add_argument("y2"); p.add_argument("z2")
    p.add_argument("--codes", action="store_true", help="aggregate by code")
    p.set_defaults(fn=cmd_scan)

    p = sub.add_parser("map", help="column-height map + hollowness of a footprint")
    p.add_argument("ox"); p.add_argument("oy"); p.add_argument("oz")
    p.add_argument("w"); p.add_argument("d")
    p.set_defaults(fn=cmd_map)

    p = sub.add_parser("setblock")
    p.add_argument("code"); p.add_argument("x"); p.add_argument("y"); p.add_argument("z")
    p.set_defaults(fn=cmd_setblock)

    for name, fn in (("shot", cmd_shot),):
        p = sub.add_parser(name, help="teleport to a vantage + cine-screenshot -> <dir>/<name>.png")
        p.add_argument("name"); p.add_argument("x"); p.add_argument("y"); p.add_argument("z")
        p.add_argument("yaw"); p.add_argument("pitch")
        p.add_argument("--dir", default="/tmp")
        p.add_argument("--respawn", action="store_true", help="revive the player first (if it starved)")
        p.set_defaults(fn=fn)

    sub.add_parser("players").set_defaults(fn=cmd_players)
    sub.add_parser("bots").set_defaults(fn=cmd_bots)
    sub.add_parser("respawn", help="revive the player (VS starves it at sat 0; bot-only hunger levers don't apply)").set_defaults(fn=cmd_respawn)

    p = sub.add_parser("godmode", help="pin-health god mode: on|off [entityId] (all bots + first player; revives dead targets)")
    p.add_argument("onoff", choices=["on", "off"])
    p.add_argument("id", nargs="?", help="target a single entity id instead of all bots + player")
    p.set_defaults(fn=cmd_godmode)

    p = sub.add_parser("sanity", help="temporal stability ('sanity') meter + storms/rifts: status | <0-1> [player] | off | storms <preset> | rifts <mode> | clear")
    p.add_argument("rest", nargs="*", help="(no args)=status; <0-1>[player]=set+pin; off=unpin; storms <off|veryrare|rare|sometimes|often>; rifts <off|invisible|visible>; clear=wipe rifts")
    p.set_defaults(fn=cmd_sanity)

    p = sub.add_parser("gamemode", help="set the player's game mode: 0=guest 1=survival 2=creative 3=spectator (no mode = query)")
    p.add_argument("player")
    p.add_argument("mode", nargs="?")
    p.set_defaults(fn=cmd_gamemode)

    p = sub.add_parser("repin", help="re-assert pilot pins after a restart: godmode all + player, sanity, creative, noon [x y z to teleport the player]")
    p.add_argument("rest", nargs="*", help="optional x y z to teleport the player to")
    p.add_argument("--uid", help="player uid (default: first online player)")
    p.set_defaults(fn=cmd_repin)

    p = sub.add_parser("shotat", help="photo a target from a vantage: computes yaw/pitch from geometry")
    p.add_argument("name"); p.add_argument("vx"); p.add_argument("vy"); p.add_argument("vz")
    p.add_argument("tx"); p.add_argument("ty"); p.add_argument("tz")
    p.add_argument("--dir", default="/tmp")
    p.add_argument("--respawn", action="store_true")
    p.set_defaults(fn=cmd_shotat)

    p = sub.add_parser("pano", help="360° sweep: n yaw shots around the player -> <dir>/<name>_p<i>.png (+_sheet.png with --sheet)")
    p.add_argument("name")
    p.add_argument("x", nargs="?", help="teleport the player here first (else shoot in place)")
    p.add_argument("y", nargs="?")
    p.add_argument("z", nargs="?")
    p.add_argument("--n", type=int, default=8, help="number of shots (default 8)")
    p.add_argument("--pitch", type=float, default=0.0, help="radians, cine convention (0 = level)")
    p.add_argument("--dir", default="/tmp")
    p.add_argument("--sheet", action="store_true", help="also write a contact sheet (needs PIL)")
    p.set_defaults(fn=cmd_pano)

    p = sub.add_parser("cmd", help="raw passthrough: cmd <name> <arg> …")
    p.add_argument("name"); p.add_argument("args", nargs="*")
    p.set_defaults(fn=cmd_cmd)

    a = ap.parse_args()
    if a.base:
        BASE = a.base
    a.fn(a)


if __name__ == "__main__":
    main()
