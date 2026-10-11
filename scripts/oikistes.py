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
import re
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
    def __init__(self, base, model, max_tokens=4000, llama=False,
                 thinking_budget=3000):
        self.url = base.rstrip("/") + "/v1/chat/completions"
        self.base = base.rstrip("/")
        self.model = model
        self.max_tokens = max_tokens
        # thinking_budget: the llama.cpp Qwen3 template accepts it as
        # a top-level body param (live-verified on the strata mux
        # 2026-10-11) and caps the THINKING stream separately from
        # max_tokens - without it the 3.6 spends the entire output
        # budget on scratchpad and emits no tool call / reply.
        self.thinking_budget = thinking_budget
        # llama=True: the engine is llama.cpp (strata) and speaks
        # chat_template_kwargs. vLLM (the 27B unit) is left on its own
        # template defaults - those already produced correct native
        # tool calls in the 10-11 A/B, so nothing is sent there.
        self.llama = llama

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

    def chat(self, messages, tools=None, timeout=240,
             thinking=None, max_tokens=None, thinking_budget=None):
        """One OpenAI-compatible chat-completions round - engine-
        agnostic: strata (llama.cpp) and vLLM both serve this shape,
        and any future OpenAI-compatible brain works unchanged.
        `tools` is the JSON-schema tool array (assets/oikistes/
        tools.json); with it present the request asks for automatic
        tool choice, and the reply may carry tool_calls instead of
        content.

        thinking: None = default (on for tool rounds); pass True to
        force it on for a plain-text step (see the loop: the 3.6's
        chat template emits an immediate im_end when thinking is
        switched OFF mid-conversation - measured 10-11 - so the
        summary step runs thinking ON with a bigger budget).

        Returns (content, tool_calls): tool_calls is a list of
        {"id", "name", "args_json"} or None when the model answered
        in plain text. reasoning_content (the 3.6 thinking stream)
        is the model's scratchpad - dropped, never shown."""
        body = {
            "model": self.model, "temperature": 0.2,
            "max_tokens": max_tokens or self.max_tokens,
            "messages": messages,
        }
        if self.llama:
            tt = bool(tools) if thinking is None else thinking
            body["chat_template_kwargs"] = {"enable_thinking": tt}
            tb = (thinking_budget if thinking_budget is not None
                  else self.thinking_budget)
            if tt and tb:
                body["thinking_budget"] = tb
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
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
        content = (m.get("content") or "").strip()
        calls = None
        if m.get("tool_calls"):
            calls = []
            for i, tc in enumerate(m["tool_calls"]):
                fn = tc.get("function") or {}
                calls.append({"id": tc.get("id") or ("call_%d" % i),
                              "name": fn.get("name") or "",
                              "args_json": fn.get("arguments") or "{}"})
        return content, calls


# ----------------------------------------------------------------------
# prompt assets (the model-visible surface: data files, not code)
# ----------------------------------------------------------------------

ASSETS = os.path.join(REPO, "assets", "oikistes")

PROMPT_TOKENS = ("@@BODY@@", "@@AUTONOMY@@", "@@AUTONOMY_NOTE@@",
                 "@@PLANS@@", "@@WORLD@@", "@@MEMORY@@")


def _load_prompt_assets():
    """Load the model-visible surface: the system prompt template
    (assets/oikistes/prompt.md - @@TOKENS@@ filled per turn) and the
    OpenAI `tools=` array (assets/oikistes/tools.json - the single
    source of truth for what a tool is). The split: what the MODEL
    SEES is data; what the MACHINE DOES (dispatch, the autonomy gate)
    stays in code. Fails at startup, loudly: a brain configured by
    files must not silently run without them (the service is
    Restart=always, so the error shows in the journal)."""
    tpath = os.path.join(ASSETS, "prompt.md")
    jpath = os.path.join(ASSETS, "tools.json")
    try:
        template = open(tpath).read()
        tools = json.load(open(jpath))
    except Exception as e:
        raise SystemExit("oikistes: cannot load prompt assets "
                          "%s / %s: %r" % (tpath, jpath, e))
    present = set(re.findall(r"@@[A-Z_]+@@", template))
    missing = [t for t in PROMPT_TOKENS if t not in present]
    if missing:
        raise SystemExit("oikistes: prompt.md missing tokens: %s"
                          % ", ".join(missing))
    for t in tools:
        fn = t.get("function") or {}
        if not (fn.get("name") and fn.get("description")
                and "parameters" in fn):
            raise SystemExit(
                "oikistes: bad tool definition in tools.json: %r"
                % (fn.get("name", t)))
    return template, tools


# ----------------------------------------------------------------------
# the query tool's helpers (module level: pure, testable)
# ----------------------------------------------------------------------

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
        self.models = {"primary": LLM(args.llm, args.llm_model,
                                      llama=True)}
        if args.alt_llm and args.alt_model:
            self.models["alt"] = LLM(args.alt_llm, args.alt_model)
        self.active = os.environ.get("OIK_BRAIN") or "primary"
        # the model-visible surface (data files, not code) - loaded
        # once at boot; the sync check against KNOWN catches a
        # tools.json drift at startup instead of at first chat
        self.prompt_template, self.tools = _load_prompt_assets()
        _names = [t["function"]["name"] for t in self.tools]
        _unknown = [n for n in _names if n not in self.KNOWN]
        _missing = sorted(self.KNOWN - set(_names))
        if _unknown or _missing:
            raise SystemExit(
                "oikistes: tools.json out of sync with KNOWN tools "
                "(unknown=%s missing=%s)" % (_unknown, _missing))
        self.lock = threading.Lock()
        self.mission = None
        self.born = time.time()
        self.state_path = os.path.join(args.datadir, "oikistes-state.json")
        self.transcript_path = os.path.join(args.datadir, "oikistes-log.jsonl")
        # The world name: the env POLIS_WORLD (set in the unit drop-in)
        # is the SEED from service boot; the game is the authority -
        # _live_world_check() adopts the live name from /polis/status
        # each chat turn, and a world change clears the rolling memory
        # (zone names, bot ids, positions are poison across worlds).
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
        self._adopt_world(self.world)

    def _adopt_world(self, world):
        """Adopt a world name (the env seed at boot, or the live name
        from /polis/status - the game is the authority). If it differs
        from the one the rolling memory was written under (and one was
        written): clear the transcript and forget the bot id - zone
        names and ids do not survive a world change."""
        if not world or world == self.world:
            return
        st = self._load_state()
        if st.get("world") and st.get("world") != world:
            try:
                open(self.transcript_path, "w").close()
            except Exception:
                pass
            self.bot = None
            self._respawns_left = 1
            self.log("system",
                     "world changed %s -> %s: memory reset" %
                     (st.get("world"), world))
        self.world = world
        st["world"] = world
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

    def _live_world_check(self):
        """Each turn: ask the game which world it has loaded. The env
        POLIS_WORLD is only the seed from service boot - if the
        operator pointed the game at another world, adopt it (the
        rolling memory of the old world is poison). An unreachable
        harness (the restart window) keeps the last known world."""
        try:
            r = self.polis.get("/polis/status")
        except Exception:
            return
        live = ((r.get("server") or {}).get("worldName") or "")
        if live:
            self._adopt_world(live)

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
        base = ("bot=%d pos=(%s,%s,%s) sat=%s/%s holding=[%s] "
                "last_action=%s%s around=[%s] recent=[%s]"
                % (bot,
                   pos[0] if len(pos) > 0 else "?",
                   pos[1] if len(pos) > 1 else "?",
                   pos[2] if len(pos) > 2 else "?",
                   b.get("Saturation") or 0,
                   b.get("MaxSaturation") or "?",
                   ", ".join(inv) or "nothing",
                   la.get("Name") or "-",
                   (" (%s)" % la.get("Msg")) if la.get("Msg") else "",
                   around,
                   "; ".join(evs) or "-"))
        # the player's satiety (2026-10-11, rule 7 'FOOD FIRST': the
        # digest is the only place the LLM sees hunger - the first
        # run lost the operator to starvation while the body munched
        # on its own ration)
        try:
            vit = self.polis.get("/polis/vitals")
            for p in (vit or {}).get("players") or []:
                base += (" | player %s sat=%s/%s" % (
                    p.get("name"), p.get("sat"), p.get("satMax")))
        except Exception:
            pass
        out = base
        m = self.mission
        if m is not None:
            if m.get("done"):
                out += ("\nlast mission %s: outcome=%s | %s" % (
                    m["id"], m.get("outcome"),
                    (m.get("summary") or "")[:200]))
            else:
                out += ("\nbackground mission %s ('%s') running "
                        "%.0f min - the settlement is free; 'mission' "
                        "with no goal reports status" % (
                            m["id"], m.get("goal"),
                            (time.time() - m.get("started", time.time()))
                            / 60.0))
        return out + "\n" + "\n".join(self._world_lines(pos))

    # -- the tool surface ----------------------------------------------
    # Each tool returns a COMPACT observation string (<~400 chars).
    # The autonomy gate (check_tool) runs before any side effect.

    KNOWN = frozenset(
        ("state", "scan", "screenshot", "events", "autonomy",
         "mission", "pots", "command", "query", "zone",
         "crew", "follow", "vocab", "preview"))

    def check_tool(self, tool, autonomy):
        if tool not in self.KNOWN:
            return False          # the gate whitelists; unknown is denied
        READONLY = ("state", "scan", "screenshot", "events", "autonomy",
                    "query", "vocab")
        if autonomy == "strict":
            return tool in READONLY
        if autonomy == "guarded":
            return tool in READONLY or tool in (
                "mission", "pots", "zone", "follow", "preview")
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
                a = {"goal": a, "bots": "self"}
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
            elif tool == "pots":
                parts = a.split()
                a = {"form_at": parts[0], "hole_at": parts[1],
                     "firepit_at": parts[2]} if len(parts) >= 3 else {}
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
            elif tool == "vocab":
                a = {"word": a}
            elif tool == "preview":
                # 'box3x3 123 45 678' - plan name then origin cell
                parts = a.split()
                a = {"plan": parts[0],
                     "origin": " ".join(parts[1:])} if parts else {}
            elif tool == "follow":
                a = {"mode": a.strip()} if a.strip() else {"mode": "off"}
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
                # no coordinates: the box is centred on the BODY, not the
                # world origin (10-11: the model's natural no-arg scans
                # hit (0,2,0) twice before it thought to check its own
                # position - one wasted round trip per search)
                if "x" not in a and "z" not in a:
                    try:
                        pos = ((self.polis.state(bot).get("Bot") or {})
                               .get("Pos", [0, 0, 0]))
                        a = {"x": int(pos[0]), "y": int(pos[1]),
                             "z": int(pos[2])}
                    except Exception:
                        pass
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
            if tool == "mission":
                if not a.get("goal"):
                    return self._mission_status()
                if isinstance(a.get("bots"), (list, tuple)):
                    a["bots"] = ",".join(str(x) for x in a["bots"])
                elif a.get("bots") is None:
                    a["bots"] = "self"
                return self.run_mission(str(a["goal"]),
                                        a.get("bots") or "self")
            if tool == "pots":
                return self.run_pots(a)
            if tool == "query":
                return self._query(a)
            if tool == "zone":
                return self._zone(a, autonomy)
            if tool == "vocab":
                return self._vocab(a)
            if tool == "preview":
                return self._preview(a)
            if tool == "crew":
                return self._crew(a.get("n"))
            if tool == "command":
                r = self.polis.cmd(str(a["cmd"]),
                                   [str(x) for x in a.get("args", [])],
                                   bot, actor="oikistes")
                return "%s: %s" % (r.get("Message") or
                                   r.get("error"),
                                   r.get("Data") or "")
            if tool == "follow":
                return self._follow(a)
        except Exception as e:
            return "tool %s failed: %r" % (tool, e)
        return "unknown tool %r" % tool

    def _follow(self, a):
        """The follow TOGGLE (2026-10-11): mode me|all|off. The mod's
        follow controller (PolisFollowController) tracks the chosen
        bots to the player's LIVE position on a 2 s tick (re-issue
        after 6+ blocks, idle bots only) until turned off. Explicit by
        design - not a natural-language sifter."""
        mode = str((a or {}).get("mode", "off")).lower()
        if mode not in ("me", "all", "off"):
            return "follow: mode must be 'me', 'all' or 'off'"
        if mode == "off":
            r = self.polis.cmd("follow", ["off"], actor="oikistes")
            return r.get("Message") or str(r)
        if mode == "me":
            ids = [self.bot]
        else:
            ids = [b.get("id") for b in self.polis.bots_list()
                   if b.get("id") is not None]
        r = self.polis.cmd("follow", [",".join(str(i) for i in ids)],
                           actor="oikistes")
        return r.get("Message") or str(r)

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

    def _vocab(self, a):
        """The name<->code resolver (2026-10-11): the user says a human
        word ("cattail", "flint"), the game knows codes
        (tallplant-coopersreed, looseflints-*). This queries the
        harness' LIVE /polis/codes registry (self-syncing across game
        updates - nothing pre-generated) and returns the matching
        names/codes with their measured drop lists. Read-only, always
        allowed."""
        word = str(a.get("word") or a.get("name") or "").strip()
        if not word:
            return "vocab: give me a word to resolve"
        r = self.get("/polis/codes?name=%s&limit=12" % quote(word.lower()))
        d = r.get("Data") or r.get("data") or r
        if not d.get("ok", True) and d.get("error"):
            return "vocab: the codes endpoint is unavailable (%s) - " \
                   "use the hot list or ask the operator" % d["error"]
        rows = d.get("codes") or d.get("Codes") or []
        if not rows:
            return ("vocab: no code or name contains %r - it may be a "
                    "variant spelling (ask again with the code you "
                    "suspect, or check the hot list)" % word)
        out = []
        for x in rows:
            code = x.get("code") or x.get("Code") or "?"
            name = x.get("name") or x.get("Name") or ""
            kind = x.get("kind") or x.get("Kind") or "?"
            drops = []
            for dr in (x.get("drops") or x.get("Drops") or [])[:4]:
                dc = dr.get("code") or dr.get("Code") or "?"
                dq = dr.get("qty") or dr.get("Qty") or 1
                drops.append("%sx%s" % (dc, dq) if dq != 1 else dc)
            out.append("%s %s (name: %s; drops: %s)"
                       % (kind, code, name or "?",
                          ", ".join(drops) if drops else "-"))
        return ("vocab for %r (%d match%s):\n"
                + "\n".join(out)) % (word, len(rows),
                                     "" if len(rows) == 1 else "es")

    def _preview(self, a):
        """The TRANSPARENT BLUEPRINT (2026-10-11): before a build is
        commenced, show the whole plan as translucent cubes at the
        named origin (the harness' build-preview - nothing is placed;
        cyan = will be placed, red = collision, green = already there,
        grey = unknown code). The human sees it in VNC/webui; the
        reply carries the same counts for my report. ALWAYS preview
        before proposing a build; never build on a plan the human has
        not seen previewed (guarded autonomy)."""
        plan = str(a.get("plan") or "").strip()
        origin = str(a.get("origin") or "").split()
        dur = a.get("duration_ms") or 300000
        try:
            dur = int(dur)
        except (TypeError, ValueError):
            dur = 300000
        if plan not in self.plans:
            return ("preview: unknown plan %r (available: %s)"
                    % (plan, ", ".join(self.plans)))
        if len(origin) != 3:
            return "preview: origin must be 'x y z' (the ground anchor)"
        try:
            x, y, z = (int(v) for v in origin)
        except ValueError:
            return "preview: origin must be three integers"
        try:
            bp = buildplans.load_plan(
                os.path.join(REPO, "builds", plan + ".json"))
        except Exception as e:
            return "preview: plan %s failed to load: %s" % (plan, e)
        payload = [{"pos": [x + dx, y + dy, z + dz], "code": m}
                   for (dx, dy, dz), m in bp.blocks]
        r = self.polis.cmd("build-preview", [json.dumps(payload), str(dur)],
                           None, actor="oikistes")
        return "preview: %s" % (r.get("Message") or r.get("error"))

    def run_mission(self, goal_line, bots="self"):
        """Order work through the R2 job system (the actuator).
        Structured verbs (mine/harvest/sow) go through the deterministic
        compiler; anything else gets the 27B planner + validator.
        A goal that names its site as 'at x,y,z' passes the triple
        through as the AUTHORITATIVE --site (register_site's operator
        path) - a surveyed ledge, not the auto-found cell east of the
        spawn (2026-10-07: the builder surveys before it builds).
        A 'goto <player>' goal (2026-10-11, the 'come to me' case) is
        the exception: players are not sites, so the planner can never
        target them - the fast path walks the selected bots (bots:
        'self' | 'all' | 'id1,id2') to the player's live position."""
        verb = goal_line.split()[0] if goal_line.split() else ""
        out = os.path.join(
            self.args.datadir,
            "oik-mission-%s-%d.json" % (verb or "goal", int(time.time())))
        cmd = [sys.executable,
               os.path.join(HERE, "r2-live-mission.py"),
               "--harness", self.args.harness,
               "--uid", self.args.uid,
               "--goal", goal_line, "--out", out]
        if self.args.llm:
            cmd += ["--llm", self.args.llm,
                    "--llm-model", self.args.llm_model or "default"]
        goto_target = None
        toks = goal_line.split()
        if verb.lower() == "goto" and len(toks) > 1:
            obj = toks[1].strip().lower().rstrip(".,")
            players = self.polis.get("/polis/players")
            plist = players if isinstance(players, list) else \
                ((players or {}).get("players") or [])
            if obj in ("me", "player", "operator", "operator's", "you"):
                for p in plist:
                    if (p.get("uid") or "") == self.args.uid:
                        goto_target = p
                        break
                if goto_target is None and len(plist) == 1:
                    goto_target = plist[0]
            else:
                for p in plist:
                    if (p.get("name") or "").lower() == obj or \
                            (p.get("uid") or "").lower() == obj:
                        goto_target = p
                        break
        if goto_target is not None:
            cmd += ["--goto-player",
                    goto_target.get("name") or self.args.uid,
                    "--bots", str(bots), "--body", str(self.bot)]
        elif "at" in toks:
            i = toks.index("at")
            if i + 1 < len(toks):
                trip = toks[i + 1].split(",")
                if len(trip) == 3 and all(p.isdigit() for p in trip):
                    cmd += ["--site", toks[i + 1]]
        elif verb.lower() == "goto" and len(toks) == 4 and \
                all(t.isdigit() for t in toks[1:4]):
            # 'goto x y z' (space-separated, as the tool doc says) -
            # the planner can never emit coordinates, so the triple must
            # become the AUTHORITATIVE site here or the goal dies on
            # arrival (2026-10-11: the 13:01 flint-search goto ended in
            # 0 s with no run for exactly this reason).
            cmd += ["--site", ",".join(toks[1:4])]
        if verb in ("mine", "harvest", "gather", "sow", "forage", "build", "make",
                    "build-plan"):
            cmd.append("--no-planner")
        else:
            cmd += ["--llm", self.args.llm,
                    "--llm-model", self.args.llm_model]
        # 2026-10-10: the mission's boot sweep must not kill the
        # settlement - it passes the whole pre-mission roster (my body
        # + the crew) as the keep list. The mission's own worker is
        # cleaned up below when the run ends.
        pre_roster = set(b.get("id") for b in self.polis.bots_list())
        if pre_roster:
            cmd += ["--keep-bots",
                    ",".join(str(i) for i in sorted(pre_roster))]
        # 2026-10-11 (campaign mode): a non-goto mission runs ON the
        # agent's own body (the --bot attach) - its cargo is the
        # campaign's banked state and survives the run. A dead body
        # with the respawn budget spent is an honest rejection, not a
        # silent stranger spawn (the oikistes identity contract above).
        if goto_target is None:
            bid = self.body()
            if bid is None:
                return ("mission REJECTED - my body is dead and the "
                        "respawn budget is spent for this service "
                        "boot; rebind it (POST /oikistes/bot) or "
                        "restart the oikistes service")
            cmd += ["--bot", str(bid)]
        # 2026-10-10 (second pass): the mission runs in the BACKGROUND.
        # The old blocking subprocess.run held the agent (and the chat
        # lock, and the user's UI - 90-minute 'unreachable' windows)
        # for the whole run. Now: Popen + a worker thread; this call
        # returns in milliseconds and the settlement stays conversable.
        # The 90-minute cap is enforced by the worker (wait(5400)).
        m_id = os.path.basename(out)[:-len(".json")]
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
        self.mission = {"id": m_id, "goal": goal_line, "out": out,
                        "started": time.time(), "done": False,
                        "outcome": None, "summary": None,
                        "pid": proc.pid, "pre_roster": pre_roster}
        threading.Thread(target=self._mission_worker,
                         args=(proc,), daemon=True).start()
        self.log("system", "mission %s dispatched (pid %d): %s"
                 % (m_id, proc.pid, goal_line))
        return ("mission %s DISPATCHED (worker pid %d) - it runs in "
                "the BACKGROUND, the settlement is not blocked. "
                "Check it later with the 'mission' tool (no goal = "
                "status); it reports running or the final verdict."
                % (m_id, proc.pid))

    def _mission_worker(self, proc):
        """Background mission lifecycle: wait (capped at 90 min),
        world hygiene (despawn non-roster bots - the body is in the
        pre-roster so it survives; it is an identity, never
        respawned here), read the verdict from the run JSON (the
        persistence of record), record it. The next digest and the
        'mission' tool report it."""
        m = self.mission
        if m is None:
            return
        try:
            proc.wait(timeout=5400)
        except subprocess.TimeoutExpired:
            proc.kill()
            m["outcome"] = "timeout(5400s)"
        if m["outcome"] != "timeout(5400s)":
            try:
                post = [b.get("id") for b in self.polis.bots_list()]
                for i in post:
                    if i is not None and i not in m["pre_roster"] and \
                            i != self.bot:
                        self.polis.cmd("despawn", [str(i)],
                                       actor="oikistes-mission-cleanup")
            except Exception:
                pass
        try:
            d = json.load(open(m["out"]))
            steps = " -> ".join("%s(%s %s)" % (
                s["job"], s["type"],
                "ok" if s["ok"] else "failed") for s in d.get("steps", []))
            m["outcome"] = d.get("outcome")
            m["summary"] = ("'%s' -> %s in %ss | %s | %s"
                            % (m["goal"], d.get("outcome"),
                               d.get("wall_s"),
                               steps or "no steps",
                               d.get("reason") or ""))
        except Exception:
            if m["outcome"] != "timeout(5400s)":
                m["outcome"] = "ended (no run JSON)"
            m["summary"] = "mission '%s' -> %s" % (
                m["goal"], m["outcome"])
        m["done"] = True
        m["done_at"] = time.time()
        self.log("system", "mission %s finished: %s" % (
            m["id"], m["summary"]))

    def run_pots(self, a):
        """The pot-work food chain (the early-game ladder J2-J5) as
        ONE background mission: clay -> clayform table (raw item) ->
        pit-kiln fire (fired item) -> firepit cook (the engine's own
        DoSmelt) -> the bot eats (one meat per fire load - the 1.22
        firepit quirk, STATUS). The R2 chain template (r2/chains.py
        'pots') renders the job list; the run JSON is the record.
        All three site cells are required - the brain knows them from
        its zones/digest (the hole and the firepit live at the base);
        the fired color follows the 1.22 rename (red ->
        earthyorange)."""
        def trip(v):
            if v is None:
                return None
            if isinstance(v, (list, tuple)):
                v = [str(x) for x in v]
            else:
                v = str(v).replace(" ", ",").split(",")
            v = [p for p in v if p.strip()]
            if len(v) != 3:
                return None
            return [int(float(x)) for x in v]
        form = trip(a.get("form_at"))
        hole = trip(a.get("hole_at"))
        fire = trip(a.get("firepit_at"))
        if form is None or hole is None or fire is None:
            return ("pots needs all three site cells: "
                    "form_at (the air cell for the clayform table), "
                    "hole_at (the floor of a 1-deep hole - the pit "
                    "kiln), firepit_at (the firepit cell) - as "
                    "[x,y,z] triples. You know them from the base "
                    "zone (query it first if unsure).")
        if self.mission is not None and not self.mission.get("done"):
            return ("a mission (%s) is still running - the pots "
                    "chain would fight it for the same workstations; "
                    "check it with the 'mission' tool first"
                    % self.mission["id"])
        params = {"form_at": form, "hole_at": hole,
                  "firepit_at": fire}
        for k in ("clay", "clay_n", "meat", "meat_n", "fuel",
                  "fuel_n", "form_recipe", "fired"):
            if a.get(k) is not None:
                params[k] = a[k]
        # One meat per fire load: the 1.22 firepit reliably cooks only
        # the first of two meats in one load and drops the raw second
        # (2026-10-10, the STATUS engine-quirk item). The ladder
        # fixture keeps meat_n=2 as the validation instrument; the
        # settlement chain orders the reliably-completable one.
        params.setdefault("meat_n", 1)
        out = os.path.join(
            self.args.datadir,
            "oik-pots-%d.json" % int(time.time()))
        cmd = [sys.executable,
               os.path.join(HERE, "r2-live-mission.py"),
               "--harness", self.args.harness,
               "--uid", self.args.uid,
               "--chain", "pots",
               "--chain-params", json.dumps(params),
               "--goal", "pots chain (clay to cooked meat to eat)",
               "--out", out]
        if self.args.llm:
            cmd += ["--llm", self.args.llm,
                    "--llm-model", self.args.llm_model or "default"]
        pre_roster = set(b.get("id")
                         for b in self.polis.bots_list())
        if pre_roster:
            cmd += ["--keep-bots",
                    ",".join(str(i) for i in sorted(pre_roster))]
        m_id = os.path.basename(out)[:-len(".json")]
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
        self.mission = {"id": m_id, "goal": "pots chain",
                        "out": out, "started": time.time(),
                        "done": False, "outcome": None,
                        "summary": None, "pid": proc.pid,
                        "pre_roster": pre_roster}
        threading.Thread(target=self._mission_worker,
                         args=(proc,), daemon=True).start()
        self.log("system",
                 "pots mission %s dispatched (pid %d): %s"
                 % (m_id, proc.pid, json.dumps(params)))
        return ("pots chain DISPATCHED (worker pid %d): clay -> "
                "crucible (clayform) -> fired (pit kiln) -> cooked "
                "meat (firepit) -> the bot eats. It runs in the "
                "BACKGROUND; check it later with the 'mission' tool "
                "(no goal). Sites: table %s, kiln hole %s, firepit %s"
                % (proc.pid, form, hole, fire))

    def _mission_status(self):
        m = self.mission
        if m is None:
            return ("no mission has been dispatched since this "
                    "service started")
        if not m["done"]:
            return ("mission %s RUNNING (%.0f min in, 90-min cap): "
                    "goal '%s' - the settlement is free meanwhile; "
                    "check again later"
                    % (m["id"], (time.time() - m["started"]) / 60.0,
                       m["goal"]))
        return ("mission %s FINISHED: outcome=%s | %s" % (
            m["id"], m["outcome"], m["summary"] or ""))

    # -- the conversation loop ------------------------------------------
    def system_prompt(self, autonomy, digest, memory):
        # The prompt is a TEMPLATE FILE (assets/oikistes/prompt.md),
        # not a code string: it is content the model reads. The
        # autonomy note stays inline - it is the human-readable form
        # of the gate the code enforces (check_tool).
        note = {"strict": "reads only - no missions, no giving, no "
                           "commands",
                "guarded": "you may order missions; direct commands "
                           "and item-giving are denied (item needs "
                           "go through gather/craft missions or the "
                           "operator)",
                "free": "all tools are open"}[autonomy]
        return (self.prompt_template
                .replace("@@BODY@@", str(self.bot))
                .replace("@@AUTONOMY@@", autonomy.upper())
                .replace("@@AUTONOMY_NOTE@@", note)
                .replace("@@PLANS@@", ", ".join(self.plans) or "none yet")
                .replace("@@WORLD@@", digest)
                .replace("@@MEMORY@@", memory or "(none yet)"))

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
            return None, ["a chat is in flight"]
        try:
            autonomy = self.autonomy()
            self._live_world_check()
            self.log("user", message, actor=actor)
            # Following is an EXPLICIT toggle (the follow tool / the
            # webui button) - no movement reflex any more (2026-10-11,
            # operator decision: the old 'come to me' regex was too
            # tight a sifter for natural language).
            actions = []
            llm = self.models[self.active]
            msgs = [
                {"role": "system",
                 "content": self.system_prompt(
                     autonomy, self.world_digest(),
                     self.memory_text())},
                {"role": "user", "content": message},
            ]
            reply = ""
            for step in range(self.MAX_ACTIONS + 1):
                last = step == self.MAX_ACTIONS
                # the world keeps moving between tool calls: the
                # system message (fresh digest) is rebuilt in place
                # each step
                msgs[0]["content"] = self.system_prompt(
                    autonomy, self.world_digest(),
                    self.memory_text())
                content, calls = llm.chat(
                    msgs, tools=(None if last else self.tools),
                    thinking=(True if last else None),
                    max_tokens=(6000 if last else None),
                    thinking_budget=(3000 if last else None))
                if calls and not last:
                    # feed the assistant turn back exactly as the
                    # server wants it (the chat template renders the
                    # tool_calls before the role:tool results)
                    msgs.append({
                        "role": "assistant",
                        "content": content or None,
                        "tool_calls": [{
                            "id": c["id"], "type": "function",
                            "function": {"name": c["name"],
                                         "arguments": c["args_json"]}}
                            for c in calls]})
                    for c in calls:
                        try:
                            a = json.loads(c["args_json"] or "{}")
                        except ValueError:
                            a = {}
                        obs = self.do_tool(c["name"], a, autonomy)
                        actions.append({"tool": c["name"], "args": a,
                                        "observation": str(obs)[:400]})
                        msgs.append({"role": "tool",
                                     "tool_call_id": c["id"],
                                     "name": c["name"],
                                     "content": str(obs)[:400]})
                    continue
                reply = (content or "").strip()
                break
            if not reply:
                # the model spent the whole step thinking and said
                # nothing: report what actually happened instead of
                # a bare "done" (10-11: the flint search ended in
                # "done" twice and the operator could not tell what
                # the agent had done)
                ran = ", ".join(dict.fromkeys(a["tool"] for a in actions))
                reply = ("no reply text (thinking ate the budget)"
                         " - ran: " + ran) if ran else "done"
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
    ThreadingHTTPServer.request_queue_size = 64
    srv = ThreadingHTTPServer((args.host, args.port), make_handler(oik))
    print("Oikistes serving on %s:%d (model %s)"
          % (args.host, args.port, args.llm_model), flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
