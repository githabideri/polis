#!/usr/bin/env python3
"""
Oikistes (οἰκιστής - "the settler/founder"): the settlement's builder
manager. An LLM (35B-class, text) with a small tool surface over the
polis harness: it can OBSERVE the world (state, scan, screenshot,
events), it can ORDER WORK through the R2 mission runner (the job
system does the acting), and under `free` autonomy it can issue
harness commands directly. Every actuation carries actor=oikistes.

Design constraints (the 2026-09-27 re-scope):
  - LEAN: short system prompt, compact tool observations (<~400 chars),
    one chat in flight at a time, a rolling memory of the last few
    exchanges - not a context that grows without bound.
  - THE POLICY IS NOT IN THE MODEL: the autonomy preset (free /
    guarded / strict, mod-owned world config) is READ on every turn
    and enforced here, in the execution path - the model proposes,
    the gate disposes. The agent can never change its own autonomy.
  - RESILIENT: the model may answer in plain text (a reply) or with a
    JSON action object; a malformed action is fed back as an error
    observation, not a crash. The harness may be briefly unreachable
    after a world restart - calls retry once.

HTTP surface (served on its own port; the web UI reaches it through
the UI proxy):
    GET  /oikistes/status        name/model/autonomy/memory/uptime
    POST /oikistes/chat          {message, actor} -> {reply, actions}
    GET  /oikistes/transcript    recent logged exchanges
    POST /oikistes/reset         clear the rolling memory

Everything the service needs from the outside is a CLI argument -
this file is public-repo code and carries no host-specific values.
"""

import argparse
import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, quote

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, REPO)
from r2 import buildplans  # the building plan library (13.11)
from r2.embodiment import embodiment as _embodiment_fn  # the body-vs-solid-world check (09-29)

# ----------------------------------------------------------------------
# harness / llm clients
# ----------------------------------------------------------------------

def http_json(url, payload=None, timeout=30, retries=1):
    data = None
    if payload is not None:
        data = json.dumps(payload).encode()
    last_err = None
    for _ in range(retries + 1):
        try:
            req = urllib.request.Request(
                url, data=data,
                headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except Exception as e:
            last_err = e
            time.sleep(1)
    raise last_err


class Polis:
    def __init__(self, base, uid):
        self.base = base.rstrip("/")
        self.uid = uid

    def cmd(self, c, args=(), bot=None, t=120, actor="oikistes"):
        ctx = {"playerUid": self.uid, "actor": actor}
        if bot is not None:
            ctx["botId"] = int(bot)
        r = http_json(self.base + "/polis/command",
                      {"cmd": c, "args": list(args), "context": ctx},
                      timeout=t)
        return r

    def get(self, path, params=None, timeout=15):
        """A plain GET with a query string (the targets endpoint, the
        zone registry, vitals - anything that is not a command)."""
        if params:
            q = "&".join("%s=%s" % (k, quote(str(v), safe=""))
                         for k, v in params.items() if v not in (None, ""))
            path = "%s?%s" % (path, q)
        return http_json(self.base + path, None, timeout)

    def goto(self, bot, x, y, z, t=90):
        """Walk the body to a cell (fire-and-forget; the caller settles
        before the next observation - the harness' goto is a pathfind
        order, not a transaction)."""
        return self.cmd("goto", [str(x), str(y), str(z)], bot, t=t)

    def state(self, bot):
        r = http_json("%s/polis/state?botId=%d" % (self.base, bot),
                      timeout=15)
        return r

    def cell_blocks(self, bot, pos, pad=2):
        """The blocks of a (2*pad+1)^3 box centred on a cell - the
        scan command. The state tool's embodiment check uses it to tell
        a body that stands in air from one that is embedded or trapped.
        (The state tool referenced this method before it existed - the
        check silently died; 2026-10-10.)"""
        x, y, z = pos
        r = self.cmd("scan", [str(x - pad), str(y - pad), str(z - pad),
                              str(x + pad), str(y + pad), str(z + pad)],
                     bot)
        return (r.get("Data") or {}).get("blocks") or []

    def players(self):
        """Online players: [{uid, name, pos:[x,y,z], yaw, pitch, ...}] -
        the harness' /polis/players. The operator's body is the one
        whose uid matches our --uid."""
        r = self.get("/polis/players")
        return r.get("players") or []

    def zones(self):
        """Named zones from the mod registry: [{name, x1,y1,z1,x2,y2,z2}].
        /polis/zones wraps the zone-list command; the anonymous Data
        object keeps lowercase field names, the POCO wrapper does not -
        be tolerant of both."""
        r = self.get("/polis/zones")
        d = r.get("Data") or r.get("data") or {}
        raw = d.get("zones") or d.get("Zones") or []
        out = []
        for z in raw:
            b = z.get("bounds") or z.get("Bounds") or {}
            out.append({"name": z.get("name") or z.get("Name"),
                        "x1": b.get("x1") or b.get("X1"),
                        "y1": b.get("y1") or b.get("Y1"),
                        "z1": b.get("z1") or b.get("Z1"),
                        "x2": b.get("x2") or b.get("X2"),
                        "y2": b.get("y2") or b.get("Y2"),
                        "z2": b.get("z2") or b.get("Z2")})
        return out

    def bots_list(self):
        """The harness bot registry: [{id, code, pos, lastAction, ...}]."""
        r = self.get("/polis/bots")
        return ((r.get("Data") or r.get("data") or {}).get("bots") or [])

    def events(self, n=12):
        r = http_json(self.base + "/polis/events?limit=%d" % n,
                      timeout=10)
        return r.get("Data") or r.get("data") or []

    def screenshot(self, bot, path):
        r = http_json(self.base + "/polis/observer-screenshot",
                      {"botId": bot, "path": path}, timeout=30)
        return r


class LLM:
    def __init__(self, base, model, max_tokens=400):
        self.url = base.rstrip("/") + "/v1/chat/completions"
        self.base = base.rstrip("/")
        self.model = model
        self.max_tokens = max_tokens

    def _wait_loaded(self, budget=120):
        """The 35B lives on an exclusive-GPU mux: when its server dies
        (it runs at the edge of the 12 GB card) the mux reloads it and
        refuses connections while the load runs (~1 min). Poll the model
        status instead of failing the whole turn. A server without a
        status field (vLLM) is loaded if it answers at all."""
        t0 = time.time()
        while time.time() - t0 < budget:
            try:
                r = http_json(self.base + "/v1/models", timeout=5)
                for m in r.get("data", []):
                    if m.get("id") == self.model:
                        st = (m.get("status") or {})
                        if not st or st.get("value") == "loaded":
                            return True
            except Exception:
                pass
            time.sleep(5)
        return False

    def chat(self, messages, timeout=240):
        body = {
            "model": self.model, "temperature": 0.2,
            "max_tokens": self.max_tokens,
            "messages": messages,
            # thinking off: the reasoning mode burns the whole budget
            # in invisible tokens and returns empty content (measured on
            # both the 27B judge and the 35B) - the action protocol is a
            # short-JSON task, it wants direct answers
            "chat_template_kwargs": {"enable_thinking": False},
        }
        try:
            r = http_json(self.url, body, timeout=timeout, retries=1)
        except Exception:
            if not self._wait_loaded():
                raise
            r = http_json(self.url, body, timeout=timeout, retries=1)
        try:
            m = r["choices"][0]["message"]
        except (KeyError, IndexError) as e:
            raise RuntimeError("no completion: %r" % e)
        return (m.get("content") or "").strip()


# ----------------------------------------------------------------------
# the query tool's helpers (module level: pure, testable)
# ----------------------------------------------------------------------

def _extract_action_json(text):
    """The 35B-class brains sometimes emit the tool object AFTER a line
    of prose ('Done. I have marked ... {"action":...}'). The chat loop
    used to treat such a reply as a final answer, so the tool call was
    lost and the raw JSON leaked into the transcript (2026-10-07: the
    'base' exchange). Find the first balanced object that carries an
    'action' key; None when the text holds no such object."""
    i = text.find('{"action"')
    if i < 0:
        return None
    depth = 0
    for j in range(i, len(text)):
        c = text[j]
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                try:
                    obj = json.loads(text[i:j + 1])
                except ValueError:
                    return None
                if isinstance(obj, dict) and "action" in obj:
                    return obj
                return None
    return None


def _query_args(parts):
    """Parse the query tool's argument tokens. Two shapes:

    zone form:      query <zonename ...> [mode=...] [code=...]
                           [radius=N] [limit=N]
    coordinate:     query <x> <z> [radius]

    key=value tokens are mode / code / radius / limit / cap (any
    order); the remaining tokens: two or more bare integers are the
    'x z [radius]' coordinate form (a third integer is the radius),
    one bare integer is the radius, other words join into the target
    (a multi-word zone name). A zone name containing digits still
    parses - only BARE integers are positional."""
    keys = {}
    bare = []
    words = []
    for p in parts:
        if "=" in p:
            k, v = p.split("=", 1)
            keys[k.strip().lower()] = v.strip()
        elif p.lstrip("-").isdigit():
            bare.append(p)
        else:
            words.append(p)
    a = {}
    if len(bare) >= 2:
        a["target"] = " ".join(bare[:2])
        if len(bare) >= 3 and "radius" not in keys:
            a["radius"] = bare[2]
    elif bare:
        a.setdefault("radius", bare[0])
    if words:
        a["target"] = " ".join(words) if "target" not in a \
            else a["target"] + " " + " ".join(words)
    a.update(keys)
    return a


def _targets_digest(r, cap=12):
    """The compact LLM digest of a /polis/targets payload: counts
    plus up to `cap` lines of code@position (entities carry their
    uid). Tolerant of the harness' JSON case (the C# POCOs serialize
    PascalCase - System.Text.Json's default for property names -
    while older payloads are camelCase). Capped well under a full
    scan's 200 rows: the agent wants the shape of the place, not a
    spreadsheet."""
    blocks = r.get("Blocks") or r.get("blocks") or []
    ents = r.get("Entities") or r.get("entities") or []
    lines = []
    for b in blocks[:cap]:
        code = (b.get("Code") or b.get("code") or "?")
        code = code.split(":")[-1]
        p = b.get("Pos") or b.get("pos") or []
        lines.append("%s@%s" % (code, ",".join(str(int(v)) for v in p)))
    for e in ents[:max(0, cap - len(lines))]:
        code = (e.get("Code") or e.get("code") or "?").split(":")[-1]
        p = e.get("Pos") or e.get("pos") or []
        lines.append("%s(id=%s)@%s" % (code, e.get("Id") or e.get("id"),
                                       ",".join(str(int(v)) for v in p)))
    n = len(blocks) + len(ents)
    out = "targets: %d (blocks=%d entities=%d)" % (n, len(blocks),
                                                   len(ents))
    if lines:
        out += ": " + "; ".join(lines)
    if n > len(lines):
        out += " (+%d more)" % (n - len(lines))
    return out[:400]


# ----------------------------------------------------------------------
# memory + state
# ----------------------------------------------------------------------

class Oikistes:
    MEMORY_TURNS = 6          # rolling memory (each = user msg + reply)
    MAX_ACTIONS = 4           # tool actions per chat turn

    def __init__(self, args):
        self.args = args
        self.polis = Polis(args.harness, args.uid)
        # the building library (13.11): plan files are DATA; new
        # buildings arrive as new files - the agent sees the index
        # every turn
        self.plans = buildplans.list_plans(os.path.join(REPO, "builds"))
        # swappable brains: primary (default) + optional alt - the
        # operator switches at runtime (POST /oikistes/model) to A/B
        # the models on the same task battery
        self.models = {"primary": LLM(args.llm, args.llm_model)}
        if args.alt_llm and args.alt_model:
            self.models["alt"] = LLM(args.alt_llm, args.alt_model)
        self.active = "primary"
        self.lock = threading.Lock()
        self.born = time.time()
        self.state_path = os.path.join(args.datadir, "oikistes-state.json")
        self.transcript_path = os.path.join(args.datadir, "oikistes-log.jsonl")
        # the world name as the service is told it (env POLIS_WORLD, set
        # in the unit). If it changes under a running agent, the rolling
        # memory of the old world (zone names, bot ids, positions) is
        # poison - a new world starts with a clean memory.
        self.world = os.environ.get("POLIS_WORLD") or ""
        self.bot = self._load_bot()
        # the body's auto-respawn budget: one per service boot. A body
        # that keeps dying is a bug to report, not a loop to retry.
        self._respawns_left = 1
        if self.world:
            self._check_world_change()

    # -- persistent state (survives restarts) --------------------------
    def _load_state(self):
        try:
            return json.load(open(self.state_path))
        except Exception:
            return {}

    def _save_state(self):
        os.makedirs(self.args.datadir, exist_ok=True)
        json.dump({"bot": self.bot, "world": self.world},
                  open(self.state_path, "w"))

    def _load_bot(self):
        return self._load_state().get("bot")

    def _save_bot(self):
        self._save_state()

    def _check_world_change(self):
        """The env world name differs from the one the rolling memory
        was written under (and one was written): clear the transcript
        and forget the bot id (ids do not survive a world change)."""
        st = self._load_state()
        if st.get("world") and st.get("world") != self.world:
            try:
                open(self.transcript_path, "w").close()
            except Exception:
                pass
            self.bot = None
            self._respawns_left = 1
            self.log("system",
                     "world changed %s -> %s: memory reset" %
                     (st.get("world"), self.world))
        st["world"] = self.world
        st["bot"] = self.bot
        self._save_state()

    # -- the in-game body ----------------------------------------------
    # 2026-10-10: the body is an IDENTITY, not a presence. The old
    # contract ("respawned after every mission") made body() spawn a
    # fresh bot whenever the stored id was not in the roster, and
    # run_mission() forced that by nulling the id after each mission -
    # so every mission (and every silently-adopted dead id) added a
    # worker to the world; one evening that grew to 18. Now: the body
    # persists across missions; if it dies it auto-respawns ONCE per
    # service boot (logged); after the budget it stays dead and asks
    # the operator to rebind (POST /oikistes/bot). It never adopts an
    # existing bot.
    def body(self):
        """The agent's persistent body. Returns the live body id, or
        None when the body is dead and the respawn budget is spent."""
        if self.bot is not None:
            try:
                bots = http_json(self.polis.base + "/polis/bots",
                                 timeout=10)
                ids = [b.get("id") for b in
                       (bots.get("Data") or {}).get("bots", [])]
                if self.bot in ids:
                    return self.bot
            except Exception:
                return self.bot   # harness unreachable: assume alive
        # the body is gone (or unbound): spend the respawn budget
        if self._respawns_left > 0:
            self._respawns_left -= 1
            r = self.polis.cmd("spawn", actor="oikistes-body")
            new = (r.get("Data") or {}).get("id")
            if new is not None:
                self.bot = new
                self._save_bot()
                self.log("system",
                         "body respawned as %d (%d respawn(s) left "
                         "this boot)" % (new, self._respawns_left))
                return self.bot
        # dead and out of budget: stay dead, the digest says so
        return None

    # -- autonomy (mod-owned, read-only for the agent) -----------------
    def autonomy(self):
        try:
            r = self.polis.cmd("autonomy", ["get"])
            return ((r.get("Data") or {}).get("preset") or "guarded")
        except Exception:
            return "guarded"

    # -- compact world digest for the system prompt --------------------
    def _world_lines(self, pos):
        """The surroundings lines shared by the digest and the state
        tool (2026-10-10, the Oikistes post-mortem): the operator's
        player body, the named zones, the bot roster. The agent used to
        be blind to all three - it could not see the player standing
        next to it, it forgot the zones (so it claimed to define 'base'
        again or to find 'none'), and it could not say where its
        partners stood."""
        lines = []
        try:
            plist = self.polis.players()
            mine = [p for p in plist
                    if (p.get("uid") or "") == self.args.uid]
            others = [p for p in plist
                      if (p.get("uid") or "") != self.args.uid]
            if mine:
                p0 = mine[0]
                pp = [int(v) for v in (p0.get("pos") or [0, 0, 0])]
                bx = int(pos[0]) if len(pos) > 0 else 0
                bz = int(pos[2]) if len(pos) > 2 else 0
                dist = int(((pp[0] - bx) ** 2 + (pp[2] - bz) ** 2) ** 0.5)
                lines.append("player=%s at (%s,%s,%s), %d blocks from me"
                             % (p0.get("name") or "?", pp[0], pp[1],
                                pp[2], dist))
            else:
                lines.append("player=not online")
            if others:
                lines.append("other players: " + ", ".join(
                    "%s at (%s)" % (p.get("name") or "?",
                                   ",".join(str(int(v)) for v in
                                             (p.get("pos") or [])))
                    for p in others[:4]))
        except Exception:
            lines.append("player=? (harness unreachable)")
        try:
            zs = self.polis.zones()
            if zs:
                lines.append("zones: " + ", ".join(
                    "%s (x %s..%s, z %s..%s)" % (z["name"], z["x1"],
                                                z["x2"], z["z1"],
                                                z["z2"])
                    for z in zs[:8]))
            else:
                lines.append("zones: none defined")
        except Exception:
            pass
        try:
            bs = self.polis.bots_list()
            if bs:
                lines.append("bots (%d): " % len(bs) + ", ".join(
                    "%s@%s,%s" % (b.get("id"),
                                 int((b.get("pos") or [0, 0, 0])[0]),
                                 int((b.get("pos") or [0, 0, 0])[2]))
                    for b in bs[:8]))
            else:
                lines.append("bots: none")
        except Exception:
            pass
        return lines

    def world_digest(self):
        bot = self.body()
        if bot is None:
            return ("YOUR BODY IS DEAD (auto-respawn budget spent). "
                    "You cannot act until the operator rebinds you "
                    "(POST /oikistes/bot) - say so honestly.")
        try:
            st = self.polis.state(bot)
        except Exception as e:
            return "world unreachable: %r" % e
        b = st.get("Bot") or {}
        pos = b.get("Pos") or []
        inv = []
        for k in ("RightHand", "LeftHand"):
            it = b.get(k)
            if it and it.get("Code"):
                inv.append("%s x%s" % (it["Code"].split(":")[-1],
                                       it.get("Qty", 1)))
        for it in (b.get("Backpack") or []):
            if it.get("Code"):
                inv.append("%s x%s" % (it["Code"].split(":")[-1],
                                       it.get("Qty", 1)))
        la = st.get("LastAction") or {}
        evs = []
        try:
            for e in self.polis.events(6):
                evs.append("%s %s" % (e.get("actor") or "?",
                                      e.get("event") or e.get("cmd")))
        except Exception:
            pass
        around = "-"
        try:
            s = int(pos[0]); t2 = int(pos[2]); py = int(pos[1])
            # the window is RELATIVE TO THE GROUND THE BODY STANDS ON:
            # the old hard-coded y2..6 window (flat-world bedrock slab)
            # reads nothing on a plateau at y120+ - the same
            # zero-based-terrain assumption that made the world pillar
            # "disappear" (2026-10-10).
            sr = self.polis.cmd(
                "scan", [str(s - 8), str(py - 2), str(t2 - 8),
                         str(s + 8), str(py + 4), str(t2 + 8)], bot)
            cnt = {}
            for bl in (sr.get("Data") or {}).get("blocks", []):
                c = bl.get("code") or "?"
                cnt[c] = cnt.get(c, 0) + 1
            top = sorted(cnt.items(), key=lambda kv: -kv[1])[:6]
            around = ", ".join("%s x%d" % (k.split(":")[-1], v)
                               for k, v in top) or "empty ground"
        except Exception:
            pass
        base = ("bot=%d pos=(%s,%s,%s) holding=[%s] last_action=%s%s "
                "around=[%s] recent=[%s]"
                % (bot,
                   pos[0] if len(pos) > 0 else "?",
                   pos[1] if len(pos) > 1 else "?",
                   pos[2] if len(pos) > 2 else "?",
                   ", ".join(inv) or "nothing",
                   la.get("Name") or "-",
                   (" (%s)" % la.get("Msg")) if la.get("Msg") else "",
                   around,
                   "; ".join(evs) or "-"))
        return base + "\n" + "\n".join(self._world_lines(pos))

    # -- the tool surface ----------------------------------------------
    # Each tool returns a COMPACT observation string (<~400 chars).
    # The autonomy gate (check_tool) runs before any side effect.

    KNOWN = frozenset(
        ("state", "scan", "screenshot", "events", "autonomy",
         "mission", "give", "command", "query", "zone", "crew"))

    def check_tool(self, tool, autonomy):
        if tool not in self.KNOWN:
            return False          # the gate whitelists; unknown is denied
        READONLY = ("state", "scan", "screenshot", "events", "autonomy",
                    "query")
        if autonomy == "strict":
            return tool in READONLY
        if autonomy == "guarded":
            return tool in READONLY or tool in ("mission", "give", "zone")
        return True  # free

    # zone subcommands that READ (everything else writes the zone
    # registry - do_tool gates those to free; check_tool cannot see
    # the arguments)
    ZONE_READ_SUBS = ("list", "show")
    ZONE_WRITE_SUBS = ("define", "remove", "rename")

    def do_tool(self, tool, a, autonomy):
        # the model sometimes passes a bare string where the protocol
        # says an object - normalize per tool instead of failing
        if isinstance(a, str):
            if tool == "mission":
                a = {"goal": a}
            elif tool == "give":
                parts = a.split()
                a = {"item": parts[0],
                     "qty": int(parts[1]) if len(parts) > 1 and
                     parts[1].isdigit() else 1} if parts else {}
            elif tool == "command":
                a = {"cmd": a.split()[0],
                     "args": a.split()[1:]} if a.strip() else {}
            elif tool == "scan":
                # the 35B passes scan a single string 'x y z' - normalize
                # it (an unnormalised string became x=0,y=2,z=0: a scan of
                # the world origin that 'found' nothing, 2026-10-10)
                parts = a.split()
                a = {"x": int(parts[0]),
                     "y": int(parts[1]) if len(parts) > 1 else 2,
                     "z": int(parts[2]) if len(parts) > 2 else 0} \
                    if parts else {}
            elif tool == "query":
                a = _query_args(a.split())
            elif tool == "zone":
                parts = a.split()
                a = {"sub": parts[0].lower(), "args": parts[1:]} \
                    if parts else {}
            elif tool == "crew":
                # crew=<n>: the worker roster (my body excluded) is
                # brought to exactly n - the ONE way to size the crew;
                # raw spawn/despawn are retired (they are how the 18-bot
                # swarm grew, 2026-10-10).
                parts = a.split()
                try:
                    a = {"n": int(parts[0])}
                except (IndexError, ValueError):
                    a = {"n": None}
            else:
                a = {}
        if not self.check_tool(tool, autonomy):
            return "DENIED: autonomy=%s does not permit tool %r" % (
                autonomy, tool)
        bot = self.body()
        try:
            if tool == "state":
                st = self.polis.state(bot)
                b = st.get("Bot") or {}
                pos = b.get("Pos", [0, 0, 0])
                inv = [ "%s x%s" % (i.get("Code"), i.get("Qty", 1))
                        for i in (b.get("Backpack") or [])
                        if i.get("Code")]
                hands = [b.get(k) for k in ("RightHand", "LeftHand")
                         if b.get(k) and b.get(k).get("Code")]
                la = st.get("LastAction") or {}
                out = ("bot=%d pos=(%s,%s,%s) hands=%s backpack=[%s] "
                       "last_action=%s %s"
                       % (bot, pos[0], pos[1], pos[2],
                          [h.get("Code") for h in hands],
                          ", ".join(inv) or "-",
                          la.get("Name") or "-", la.get("Msg") or ""))
                # the body's relation to the solid world (09-29): raw
                # position is innocent-looking - EMBEDDED/TRAPPED is
                # what the agent must see to know it (or anything in
                # the world) cannot walk
                try:
                    x, y, z = (int(p) for p in pos)
                    bs = self.polis.cell_blocks(bot, (x, y, z),
                                                pad=2) or []
                    cm = {tuple(bb["pos"]): bb.get("code")
                          for bb in bs}
                    est, edet = _embodiment_fn(pos, cm)
                    out += " embodiment=%s (%s)" % (est, edet)
                except Exception as e:
                    out += " embodiment=? (%s)" % e
                return out + "\n" + "\n".join(self._world_lines(pos))
            if tool == "scan":
                x = int(a.get("x", 0)); y = int(a.get("y", 2))
                z = int(a.get("z", 0)); rad = int(a.get("r", 8) or 8)
                res = self.polis.cmd(
                    "scan", [str(x - rad), str(y), str(z - rad),
                             str(x + rad), str(y + 4), str(z + rad)], bot)
                blocks = (res.get("Data") or {}).get("blocks", [])
                cnt = {}
                for bl in blocks:
                    cnt[bl.get("code")] = cnt.get(bl.get("code"), 0) + 1
                top = sorted(cnt.items(), key=lambda kv: -kv[1])[:10]
                return ("scan (%d..%d, %d..%d, %d..%d): %d blocks: %s"
                        % (x - rad, x + rad, y, y + 4, z - rad, z + rad,
                           len(blocks),
                           ", ".join("%s x%d" % (k, v)
                                      for k, v in top) or "none"))
            if tool == "screenshot":
                p = os.path.join(
                    self.args.datadir,
                    "obs-%d.png" % int(time.time()))
                r = self.polis.screenshot(bot, p)
                return ("screenshot saved to %s" % p) if r.get("Ok") \
                    else "screenshot failed: %s" % r.get("Message")
            if tool == "events":
                evs = self.polis.events(int(a.get("n", 8) or 8))
                return "; ".join("%s %s %s" % (e.get("actor") or "?",
                                              e.get("event") or "",
                                              e.get("detail") or "")
                                 for e in evs) or "no recent events"
            if tool == "autonomy":
                return "autonomy preset: %s (mod-owned; I cannot change it)" \
                    % self.autonomy()
            if tool == "give":
                r = self.polis.cmd("give", [str(a["item"]),
                                            str(int(a.get("qty", 1)))],
                                   bot, actor="oikistes")
                return ("gave %s x%s: %s" % (a["item"], a.get("qty", 1),
                                             r.get("Message")))
            if tool == "mission":
                return self.run_mission(str(a["goal"]))
            if tool == "query":
                return self._query(a)
            if tool == "zone":
                return self._zone(a, autonomy)
            if tool == "crew":
                return self._crew(a.get("n"))
            if tool == "command":
                r = self.polis.cmd(str(a["cmd"]),
                                   [str(x) for x in a.get("args", [])],
                                   bot, actor="oikistes")
                return "%s: %s" % (r.get("Message") or
                                   r.get("error"),
                                   r.get("Data") or "")
        except Exception as e:
            return "tool %s failed: %r" % (tool, e)
        return "unknown tool %r" % tool

    def _crew(self, n):
        """crew=<n>: bring the worker roster (MY BODY EXCLUDED) to
        exactly n: recruit if short, retire the NEWEST (highest ids)
        if over, hard cap 8, the body is never touched. The one
        sanctioned way to size the crew (2026-10-10: raw spawn/
        despawn - one per message - grew an 18-bot swarm)."""
        if n is None:
            return "crew: give a target headcount, e.g. {'n': 2}"
        MAX_CREW = 8
        if not (0 <= n <= MAX_CREW):
            return "crew: target must be 0..%d (got %s)" % (MAX_CREW, n)
        bots = self.polis.bots_list()
        me = self.bot
        ids = sorted(b.get("id") for b in bots if b.get("id") != me)
        if n > len(ids):
            new = []
            for _ in range(n - len(ids)):
                r = self.polis.cmd("spawn", actor="oikistes-crew")
                nid = (r.get("Data") or {}).get("id")
                if nid is not None:
                    new.append(nid)
            ids = sorted(ids + new)
            verb = "recruited %s" % new if new else "recruit failed"
        elif n < len(ids):
            to_retire = ids[len(ids) - n:]   # newest go first
            for i in to_retire:
                self.polis.cmd("despawn", [str(i)],
                               actor="oikistes-crew")
            ids = sorted(ids[:len(ids) - len(to_retire)])
            verb = "retired %s" % to_retire
        else:
            verb = "unchanged"
        return ("%s: crew now %d worker(s) %s (plus me, %s)" %
                (verb, len(ids), ids, me))

    def _query(self, a):
        """query <zonename | x z [radius]> [mode=blocks|entities|all]
        [code=<substr>] -> a compact digest of the /polis/targets
        scan. Zone form: the zone= parameter (an AABB scan of the
        named zone - Lane A's addition to the existing endpoint).
        Coordinate form: the endpoint's existing radius mode centred
        on the body - the (disposable) body walks there first; moving
        a presence is not a world change. The digest is counts plus a
        capped list of code/position (uid for entities) - under 400
        chars, LLM-friendly. JSON case is tolerated (the harness
        serializes POCOs PascalCase; older payloads camelCase)."""
        target = str(a.get("target") or a.get("zone")
                     or a.get("zonename") or a.get("name") or "").strip()
        parts = target.split()
        if not parts:
            return "query: give a zone name, or 'x z [radius]'"
        params = {"mode": str(a.get("mode") or "all"),
                  "limit": str(int(a.get("limit") or 20))}
        if a.get("code"):
            params["codeContains"] = str(a["code"])
        polys = self.polis
        if len(parts) >= 2 and \
                all(p.lstrip("-").isdigit() for p in parts[:2]):
            # coordinate form: x z [radius]
            x, z = int(parts[0]), int(parts[1])
            rad = int(a.get("radius") or (
                parts[2] if len(parts) > 2 and parts[2].lstrip("-").isdigit()
                else 8))
            bot = self.body()
            by = int((polys.state(bot).get("Bot") or {}).get(
                "Pos", [0, 0, 0])[1])
            polys.goto(bot, x, by, z)
            time.sleep(8)  # settle: the radius query centres on the
            # body's actual stopping point, not the destination
            params["botId"] = bot
            params["radius"] = rad
        else:
            params["playerUid"] = self.args.uid
            params["zone"] = target
        try:
            r = polys.get("/polis/targets", params)
        except Exception as e:
            return "query %s: harness unreachable (%s)" % (target, e)
        if not r or r.get("Ok") is False:
            return "query %s: %s" % (target, r.get("Message") or "no data")
        return _targets_digest(r, int(a.get("cap") or 12))

    def _zone(self, a, autonomy):
        """zone list|show|define|remove|rename - the named rectangular
        world regions the targets endpoint scans (the harness zone
        commands; rename is Lane A's 2026-10-07 addition). list/show
        read (guarded+); define/remove/rename write the registry
        (free only). Zone commands are world-scoped - no bot context.
        define <name> x1 y1 z1 x2 y2 z2; rename <old> <new>."""
        sub = str(a.get("sub") or a.get("cmd")
                  or a.get("action") or "").lower()
        args = [str(x) for x in (a.get("args") or [])]
        if sub not in self.ZONE_READ_SUBS and autonomy != "free":
            return ("DENIED: autonomy=%s does not permit zone %r "
                    "(writes are free-only; list/show read)"
                    % (autonomy, sub))
        if sub == "list":
            cmd, args = "zone-list", []
        elif sub == "show":
            cmd, args = "zone-show", args[:1]
        elif sub == "define":
            cmd, args = "zone-define", args
        elif sub == "remove":
            cmd, args = "zone-remove", args[:1]
        elif sub == "rename":
            cmd, args = "zone-rename", args[:2]
        else:
            return ("zone: unknown subcommand %r (list|show|define|"
                    "remove|rename)" % sub)
        if sub != "list" and (not args or (sub == "define" and len(args) < 7)
                              or (sub == "rename" and len(args) < 2)):
            return ("zone %s: missing arguments (define needs "
                    "<name> x1 y1 z1 x2 y2 z2; rename <old> <new>)" % sub)
        r = self.polis.cmd(cmd, args, None, actor="oikistes")
        return "zone %s: %s" % (sub, r.get("Message") or r.get("error")
                                or ("ok" if r.get("Ok") else "no reply"))

    def run_mission(self, goal_line):
        """Order work through the R2 job system (the actuator).
        Structured verbs (mine/harvest/sow) go through the deterministic
        compiler; anything else gets the 27B planner + validator.
        A goal that names its site as 'at x,y,z' passes the triple
        through as the AUTHORITATIVE --site (register_site's operator
        path) - a surveyed ledge, not the auto-found cell east of the
        spawn (2026-10-07: the builder surveys before it builds)."""
        verb = goal_line.split()[0] if goal_line.split() else ""
        out = os.path.join(
            self.args.datadir,
            "oik-mission-%s-%d.json" % (verb or "goal", int(time.time())))
        cmd = [sys.executable,
               os.path.join(HERE, "r2-live-mission.py"),
               "--harness", self.args.harness,
               "--uid", self.args.uid,
               "--goal", goal_line, "--out", out]
        toks = goal_line.split()
        if "at" in toks:
            i = toks.index("at")
            if i + 1 < len(toks):
                trip = toks[i + 1].split(",")
                if len(trip) == 3 and all(p.isdigit() for p in trip):
                    cmd += ["--site", toks[i + 1]]
        if verb in ("mine", "harvest", "sow", "build", "build-plan"):
            cmd.append("--no-planner")
        else:
            cmd += ["--llm", self.args.llm,
                    "--llm-model", self.args.llm_model]
        try:
            p = subprocess.run(cmd, capture_output=True, text=True,
                               timeout=1800)
            detail = (p.stdout or "").strip().splitlines()
            tail = detail[-2:] if detail else ["no output"]
        except subprocess.TimeoutExpired:
            tail = ["mission timed out (1800s)"]
        # 2026-10-10: the body is an identity - it is NOT respawned
        # here. The old null-after-mission ("the mission swept the
        # world") is what turned every mission into a new-recruit
        # event; if the mission's sweep kills the body, body() catches
        # it on the next call and spends the one-respawn budget.
        # read the verdict from the run JSON (the persistence of record)
        try:
            d = json.load(open(out))
            steps = " -> ".join("%s(%s %s)" % (
                s["job"], s["type"],
                "ok" if s["ok"] else "failed") for s in d.get("steps", []))
            return ("mission '%s' -> %s in %ss | %s | %s"
                    % (goal_line, d.get("outcome"),
                       d.get("wall_s"),
                       steps or "no steps",
                       d.get("reason") or ""))
        except Exception:
            return "mission '%s' -> %s" % (goal_line, " | ".join(tail)[:300])

    # -- the conversation loop ------------------------------------------
    def system_prompt(self, autonomy, digest, memory):
        tools = ("state, scan, screenshot, events, autonomy, give, "
                 "mission, query, zone, crew, command")
        return (
            "You are the OIKISTES, the settlement's builder manager, a "
            "builder bot with a body in a block world. Your partners are "
            "the settlement's operator (you) and the devops engineer; "
            "you answer them directly, in short plainspoken replies.\n"
            "AUTONOMY: %s. This is a WORLD-OWNED policy, not yours: you "
            "read it, the execution path enforces it. You can never "
            "change it yourself. %s\n"
            "TOOLS (when you must act, answer with exactly one JSON "
            "object, no prose: {\"action\":\"<tool>\","
            "\"args\":{...},\"say\":\"<one short line>\"}). "
            "Available: %s. Tool meanings: state=inspect your body and "
            "inventory; scan=<x,y,z> block census; screenshot=save a "
            "view; events=recent actor-tagged activity; autonomy=read "
            "the preset; give=<item,qty> hand an item to your body; "
            "mission=<goal line> order a job through the job system "
            "(goals like 'mine granite x1', 'harvest rye x1', 'sow rye "
            "x1 at site-A', 'build granite x4 at site-A', 'place "
            "granite at site-A x1 supply external'); "
            "query={target:<zonename | x z [radius]>} [mode=blocks|entities|all] "
            "[code=<substr>] what is in a named zone or around a point "
            "(the target key takes the zone name or two coordinates, "
            "e.g. {\"target\":\"storage1\"} or {\"target\":\"512020 512025\","
            "\"mode\":\"all\"}; a compact digest of the targets scan - "
            "counts plus a capped code/position list; the coordinate "
            "form walks your body there first); "
            "zone={sub:list|show|define|remove|rename, args:[...]} "
            "named rectangular world regions (define <name> x1 y1 z1 "
            "x2 y2 z2; show/remove <name>; rename <old> <new> - "
            "writes are free-only); "
            "command=<cmd,args> "
            "a direct harness command (free only). Rules for the risky "
            "ones: 'despawn <id>' removes EXACTLY the bot with that id - if "
            "the reply names a different id or returns an error, STOP and "
            "report it verbatim; never 'repair' a failed despawn by "
            "spawning. 'spawn' ADDS a new bot to the world; it is a creation "
            "act, never a retry mechanism for any other command. A 'sow <crop> xN at "
            "<site>' mission is the COMPLETE endogenous chain - the "
            "mission itself harvests the seed and sows it; never "
            "pre-harvest for it. A 'build <material> xN at <site>' "
            "mission places N blocks as a ring platform at the site "
            "(add 'supply external' if the bot holds none). "
            "BUILDINGS: 'build-plan <id> at <site>' erects a whole "
            "building from the library; plans available now: %s. A "
            "building is DATA (a plan file), not a fixed shape - new "
            "buildings arrive as new files, and a composition of "
            "build primitives that stands well is worth saving as "
            "one. A hut means: a floor, walls with ONE opening (the "
            "door), a roof over - a place to shelter from weather and "
            "the night. Suggest only work you can actually order from "
            "this vocabulary; if the user wants something outside it "
            "(e.g. foraging berries, smelting in a crucible - the "
            "campaign chains are operator-ordered, not goal verbs), "
            "say plainly that the job system has no goal verb for that "
            "yet, and offer the closest thing you can order. "
            "WORLD BLOCK: the current-world section lists your body, the "
            "operator's PLAYER (by name, with its position and the "
            "distance from you), any other players, the NAMED ZONES as "
            "the registry holds them (never define a zone that is already "
            "listed, and never claim to have defined one without the zone "
            "list in front of you), and the BOT ROSTER (id at x,z). "
            "IF THE OPERATOR GIVES YOU A LOCATION OR COORDINATES, use the "
            "query tool in coordinate form against THAT location - do not "
            "scan your own position and call their spot empty. YOUR OWN "
            "MOVEMENT IS GOTO: a pathfind order that can fail when the "
            "way is blocked - report the harness message VERBATIM, do not "
            "paraphrase it, and never claim to have teleported yourself "
            "(only the player can be teleported; the teleport command "
            "takes the player's name or uid as its first argument). When "
            "a tool returns an error, repeat the exact message in your "
            "report - paraphrasing it loses the diagnosis. After each "
            "action you see its "
            "result; once you are done acting you MUST answer in "
            "plain text with a short report. You are the Oikistes: "
            "answer as it, in short plainspoken sentences - never "
            "echo the input back.\n"
            "OPERATING DISCIPLINE (hard rules): "
            "1 HONEST REPORTS - claim only what you SAW in a harness "
            "reply. Ordered is not done; a mission 'started' is running, "
            "not finished. When a tool fails, repeat the exact message "
            "and stop guessing at it. "
            "2 PLAN BEFORE ACTING - a multi-part request ('do it all') "
            "gets decomposed into an ordered plan that you report FIRST; "
            "then you execute one step at a time (a mission at a time, "
            "watched via events) - never launch a swarm of parallel "
            "jobs, and never start a build you have not checked the "
            "material for. "
            "3 FAIL FAST - the same goal failing twice means STOP: "
            "report the exact failure and say what would have to be "
            "true for it to work. Never retry an identical command with "
            "identical arguments. A reply that names a different id or "
            "count than you requested is a bug report, not a nudge to "
            "improvise. "
            "4 CREW - size the crew with the crew TOOL, never with raw "
            "spawn/despawn (that is how an 18-bot swarm grew, 2026-10-10). "
            "{'tool':'crew','args':{'n':2}} sets the worker roster (your "
            "body excluded) to exactly 2: it recruits if short, retires "
            "the newest if over (hard cap 8). Read the digest first - "
            "it lists the roster. One message = one mission = at most a "
            "small crew change; when work ends, shrink back toward 1-2 "
            "and report the final headcount. A growing roster across "
            "turns is a bug. "
            "5 BUILD FROM WHAT EXISTS - soil/dirt is the common, "
            "hand-minable material (in this game version 'dirt' is the "
            "soil-* block family); granite (rock-granite) needs a "
            "mining step first. If a building's material is not on "
            "hand, say so and order the mining - do not order the "
            "building and call the failure an accident.\n"
            "Current world (fresh): %s\n"
            "Recent exchanges:\n%s"
            % (autonomy.upper(),
               {"strict": "reads only - no missions, no giving, no "
                           "commands",
                "guarded": "you may order missions and give items; "
                           "direct commands are denied",
                "free": "all tools are open"}[autonomy],
               tools, ", ".join(self.plans) or "none yet", digest,
               memory or "(none yet)"))

    def memory_text(self):
        try:
            lines = open(self.transcript_path).read().splitlines()[-40:]
        except Exception:
            lines = []
        out = []
        for ln in lines[-(self.MEMORY_TURNS * 2):]:
            try:
                d = json.loads(ln)
            except Exception:
                continue
            if d.get("role") == "user":
                out.append("  %s: %s" % (d.get("actor") or "user",
                                         d.get("text", "")[:200]))
            elif d.get("role") == "oikistes":
                out.append("  oikistes: %s" % (d.get("text", "")[:200]))
        return "\n".join(out[-12:])

    def log(self, role, text, actor=None):
        os.makedirs(self.args.datadir, exist_ok=True)
        rec = {"ts": time.strftime("%Y-%m-%d %H:%M:%S %Z"),
               "role": role, "text": text}
        if actor:
            rec["actor"] = actor
        with open(self.transcript_path, "a") as f:
            f.write(json.dumps(rec) + "\n")

    def transcript(self, n=50):
        try:
            lines = open(self.transcript_path).read().splitlines()
        except Exception:
            lines = []
        out = []
        for ln in lines[-n:]:
            try:
                out.append(json.loads(ln))
            except Exception:
                continue
        return out

    def chat(self, message, actor="user"):
        if not self.lock.acquire(blocking=False):
            return None, ["a chat is already in flight"]
        try:
            autonomy = self.autonomy()
            self.log("user", message, actor=actor)
            actions = []
            digest = self.world_digest()
            reply = ""
            for step in range(self.MAX_ACTIONS + 1):
                last = step == self.MAX_ACTIONS
                base = self.system_prompt(autonomy, digest,
                                          self.memory_text())
                if step == 0:
                    msg = base + "\n\nNew message from %s: %s" % (
                        actor, message)
                else:
                    msg = (base +
                           "\n\nYour actions this turn and their "
                           "results:\n" + json.dumps(actions,
                                                      indent=1))
                if last:
                    msg += ("\nAnswer NOW in plain text - no JSON "
                            "action, a short report of what happened.")
                out = self.models[self.active].chat(
                    [{"role": "user", "content": msg}])
                if not last:
                    act = None
                    pre = ""
                    if out.startswith("{"):
                        try:
                            act = json.loads(out)
                        except ValueError:
                            act = {"action": "state", "args": {},
                                   "say": "malformed action"}
                    else:
                        # the 35B emits the action object after a line of
                        # prose - execute it instead of leaking it into
                        # the transcript (the 'base' exchange, 2026-10-07)
                        act = _extract_action_json(out)
                        if act is not None:
                            pre = out[:out.find('{"action"')].strip(" .,:-")
                    if act is not None:
                        tool = str(act.get("action") or "")
                        args = act.get("args") or {}
                        obs = self.do_tool(tool, args, autonomy)
                        actions.append({"tool": tool, "args": args,
                                        "observation": obs[:400]})
                        reply = str(act.get("say") or pre or "")
                        digest = self.world_digest()   # fresh each step
                        continue
                reply = out
                break
            if not reply:
                reply = "done"
            self.log("oikistes", reply)
            return reply, actions
        finally:
            self.lock.release()

    def status(self):
        return {"name": "Oikistes",
                "model": self.models[self.active].model,
                "brain": self.active,
                "models": {k: v.model for k, v in self.models.items()},
                "autonomy": self.autonomy(),
                "bot": self.bot,
                "world": self.world,
                "uptime_s": int(time.time() - self.born),
                "memory_turns": self.MEMORY_TURNS,
                "transcript_lines": len(self.transcript(10 ** 6))}

    def set_brain(self, brain):
        if brain not in self.models:
            return None
        self.active = brain
        return self.status()


# ----------------------------------------------------------------------
# http surface
# ----------------------------------------------------------------------

def make_handler(oik):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, obj):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            u = urlparse(self.path)
            if u.path == "/oikistes/status":
                try:
                    self._send(200, oik.status())
                except Exception as e:
                    self._send(500, {"error": repr(e)})
            elif u.path == "/oikistes/transcript":
                n = 50
                q = parse_qs(u.query)
                if q.get("n"):
                    n = int(q["n"][0])
                self._send(200, oik.transcript(n))
            else:
                self._send(404, {"error": "unknown path"})

        def do_POST(self):
            u = urlparse(self.path)
            ln = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(ln) or b"{}") if ln else {}
            if u.path == "/oikistes/chat":
                if oik.lock.locked():
                    self._send(429, {"error": "chat in flight"})
                    return
                try:
                    reply, actions = oik.chat(
                        str(body.get("message", "")),
                        str(body.get("actor") or "user"))
                    self._send(200, {"reply": reply,
                                     "actions": actions})
                except Exception as e:
                    self._send(500, {"reply": None,
                                     "actions": [],
                                     "error": repr(e)})
            elif u.path == "/oikistes/reset":
                try:
                    open(oik.transcript_path, "w").close()
                    self._send(200, {"ok": True})
                except Exception as e:
                    self._send(500, {"error": repr(e)})
            elif u.path == "/oikistes/bot":
                # operator rebind: point the agent's body at a named
                # bot id (after a death the agent could not respawn,
                # or to adopt a specific laborer as the body).
                try:
                    b = int(body.get("bot"))
                    bots = oik.polis.bots_list()
                    ids = [x.get("id") for x in bots]
                    if b not in ids:
                        self._send(400, {"error": "bot %d not in "
                                                 "roster %s" % (b, ids)})
                        return
                    oik.bot = b
                    oik._save_bot()
                    oik.log("system", "operator rebind: body = %d" % b)
                    self._send(200, {"ok": True, "bot": b})
                except Exception as e:
                    self._send(400, {"error": repr(e)})
            elif u.path == "/oikistes/model":
                brain = str(body.get("brain") or body.get("id") or "")
                st = oik.set_brain(brain)
                if st is None:
                    self._send(400, {"error": "unknown brain %r; "
                                             "available: %s"
                                             % (brain,
                                                ", ".join(oik.models))})
                else:
                    self._send(200, st)
            else:
                self._send(404, {"error": "unknown path"})

    return H


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--harness", required=True,
                    help="polis harness base url")
    ap.add_argument("--uid", required=True,
                    help="owner player uid for harness contexts")
    ap.add_argument("--llm", required=True,
                    help="llama.cpp/vLLM base url of the primary brain")
    ap.add_argument("--llm-model", required=True,
                    help="the primary brain's model id")
    ap.add_argument("--alt-llm", default="",
                    help="optional second brain (A/B comparison)")
    ap.add_argument("--alt-model", default="",
                    help="the second brain's model id")
    ap.add_argument("--datadir", default=os.path.join(REPO, "data"))
    ap.add_argument("--port", type=int, default=8587)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()
    os.makedirs(args.datadir, exist_ok=True)
    oik = Oikistes(args)
    srv = ThreadingHTTPServer((args.host, args.port), make_handler(oik))
    print("Oikistes serving on %s:%d (model %s)"
          % (args.host, args.port, args.llm_model), flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
