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
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

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

    def state(self, bot):
        r = http_json("%s/polis/state?botId=%d" % (self.base, bot),
                      timeout=15)
        return r

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
# memory + state
# ----------------------------------------------------------------------

class Oikistes:
    MEMORY_TURNS = 6          # rolling memory (each = user msg + reply)
    MAX_ACTIONS = 4           # tool actions per chat turn

    def __init__(self, args):
        self.args = args
        self.polis = Polis(args.harness, args.uid)
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
        self.bot = self._load_bot()

    # -- persistent state (survives restarts) --------------------------
    def _load_bot(self):
        try:
            d = json.load(open(self.state_path))
            return d.get("bot")
        except Exception:
            return None

    def _save_bot(self):
        os.makedirs(self.args.datadir, exist_ok=True)
        json.dump({"bot": self.bot}, open(self.state_path, "w"))

    # -- the in-game body ----------------------------------------------
    def body(self):
        """The agent's body: a persistent harness bot. R2 mission boots
        sweep the world, so the body is RESPAWNED after every mission -
        it is a presence, not an identity (identity is the transcript)."""
        if self.bot is not None:
            try:
                bots = http_json(self.polis.base + "/polis/bots",
                                 timeout=10)
                ids = [b.get("id") for b in
                       (bots.get("Data") or {}).get("bots", [])]
                if self.bot in ids:
                    return self.bot
            except Exception:
                pass
        r = self.polis.cmd("spawn", actor="oikistes")
        self.bot = (r.get("Data") or {}).get("id")
        self._save_bot()
        return self.bot

    # -- autonomy (mod-owned, read-only for the agent) -----------------
    def autonomy(self):
        try:
            r = self.polis.cmd("autonomy", ["get"])
            return ((r.get("Data") or {}).get("preset") or "guarded")
        except Exception:
            return "guarded"

    # -- compact world digest for the system prompt --------------------
    def world_digest(self):
        bot = self.body()
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
            s = int(pos[0]); t2 = int(pos[2])
            sr = self.polis.cmd(
                "scan", [str(s - 8), "2", str(t2 - 8),
                         str(s + 8), "6", str(t2 + 8)], bot)
            cnt = {}
            for bl in (sr.get("Data") or {}).get("blocks", []):
                c = bl.get("code") or "?"
                cnt[c] = cnt.get(c, 0) + 1
            top = sorted(cnt.items(), key=lambda kv: -kv[1])[:6]
            around = ", ".join("%s x%d" % (k.split(":")[-1], v)
                               for k, v in top) or "empty ground"
        except Exception:
            pass
        return ("bot=%d pos=(%s,%s,%s) holding=[%s] last_action=%s%s "
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

    # -- the tool surface ----------------------------------------------
    # Each tool returns a COMPACT observation string (<~400 chars).
    # The autonomy gate (check_tool) runs before any side effect.

    KNOWN = frozenset(
        ("state", "scan", "screenshot", "events", "autonomy",
         "mission", "give", "command"))

    def check_tool(self, tool, autonomy):
        if tool not in self.KNOWN:
            return False          # the gate whitelists; unknown is denied
        READONLY = ("state", "scan", "screenshot", "events", "autonomy")
        if autonomy == "strict":
            return tool in READONLY
        if autonomy == "guarded":
            return tool in READONLY or tool in ("mission", "give")
        return True  # free

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
                inv = [ "%s x%s" % (i.get("Code"), i.get("Qty", 1))
                        for i in (b.get("Backpack") or [])
                        if i.get("Code")]
                hands = [b.get(k) for k in ("RightHand", "LeftHand")
                         if b.get(k) and b.get(k).get("Code")]
                la = st.get("LastAction") or {}
                return ("bot=%d pos=(%s,%s,%s) hands=%s backpack=[%s] "
                        "last_action=%s %s"
                        % (bot, b.get("Pos", [0, 0, 0])[0],
                           b.get("Pos", [0, 0, 0])[1],
                           b.get("Pos", [0, 0, 0])[2],
                           [h.get("Code") for h in hands],
                           ", ".join(inv) or "-",
                           la.get("Name") or "-", la.get("Msg") or ""))
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

    def run_mission(self, goal_line):
        """Order work through the R2 job system (the actuator).
        Structured verbs (mine/harvest/sow) go through the deterministic
        compiler; anything else gets the 27B planner + validator."""
        verb = goal_line.split()[0] if goal_line.split() else ""
        out = os.path.join(
            self.args.datadir,
            "oik-mission-%s-%d.json" % (verb or "goal", int(time.time())))
        cmd = [sys.executable,
               os.path.join(HERE, "r2-live-mission.py"),
               "--harness", self.args.harness,
               "--uid", self.args.uid,
               "--goal", goal_line, "--out", out]
        if verb in ("mine", "harvest", "sow", "build"):
            cmd.append("--no-planner")
        else:
            cmd += ["--llm", self.args.llm,
                    "--llm-model", self.args.llm_model]
        try:
            p = subprocess.run(cmd, capture_output=True, text=True,
                               timeout=300)
            detail = (p.stdout or "").strip().splitlines()
            tail = detail[-2:] if detail else ["no output"]
        except subprocess.TimeoutExpired:
            tail = ["mission timed out (300s)"]
        # the mission booted a fresh bot and swept mine - respawn the body
        self.bot = None
        self._save_bot()
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
        tools = """state, scan, screenshot, events, autonomy, give, mission, command"""
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
            "granite at site-A x1 supply external'); command=<cmd,args> "
            "a direct harness command (free only). A 'sow <crop> xN at "
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
            "(crafting, cooking, smelting), say plainly that the job "
            "system has no verb for that yet, and offer the closest "
            "thing you can order. After each action you see its "
            "result; once you are done acting you MUST answer in "
            "plain text with a short report. You are the Oikistes: "
            "answer as it, in short plainspoken sentences - never "
            "echo the input back.\n"
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
                if not last and out.startswith("{"):
                    try:
                        act = json.loads(out)
                    except ValueError:
                        act = {"action": "state", "args": {},
                               "say": "malformed action"}
                    tool = str(act.get("action") or "")
                    args = act.get("args") or {}
                    obs = self.do_tool(tool, args, autonomy)
                    actions.append({"tool": tool, "args": args,
                                    "observation": obs[:400]})
                    if act.get("say"):
                        reply = str(act["say"])
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
