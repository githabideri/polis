#!/usr/bin/env python3
"""decider-service.py -- live Decider-2B readout endpoint (HTTP).

Wraps gguf-runner's GgufDecider (in-process llama.cpp, Q8_0 GGUF, T=1.3
option-letter readout -- the numerically-validated path) in a tiny HTTP
service so a decision loop on another machine can call it per step:

  POST /readout {"state": "<state text>", "options": ["goto_target",...],
                 "question": optional (defaults to the corpus CHOICE_Q)}
  -> {"ok": true, "probs": {"goto_target": 0.42,...},
      "choice": "goto_target", "ms": 3100}

  POST /prompt {"state":..., "options": [...], "question": optional}
  -> {"ok": true, "prompt": "<full chat-templated prompt text>",
      "letters": [<token id of option letter A>,...], "nopts": N}
  The /prompt endpoint exists for the *fast path* (decider-fast-client.py):
  a caller on another box (that lacks the decider package/tokenizer) gets
 the exact prompt this service would run, plus the option-letter token
  ids, and sends the prompt itself to a GPU llama-server (the 3060 card)
  over the tailnet, recovering the T=1.3 letter distribution from the
  raw n_probs. Total ~100-150 ms/row vs ~3-4 s for the in-process readout.

  GET /health -> {"ok": true, "gguf":..., "loaded": true}

The model is loaded once at startup (a few seconds for 2B Q8 on CPU) and
held in memory; requests are serialized on one llama context (not
thread-safe). This is the same readout the A/B corpus used, served live:
gate on p(oracle) (or p(proposal)), do NOT gate on argmax confidence alone
(the Q8 model makes its systematic travel-phase error confidently).

Run (the CPU batch box, vdec venv):
  /var/jevab/vdec/bin/python /var/jevab/decider-service.py \
      --gguf /models/jevab/decider-2b-Q8_0.gguf --port 8091 --host 0.0.0.0
"""
import argparse
import importlib.util
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CHOICE_Q = ("Given the bot's current game state, choose the single best "
            "action for the bot to execute next.")


def _load_gguf_runner(path):
    spec = importlib.util.spec_from_file_location("gguf_runner", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Service:
    def __init__(self, gguf, threads, ctx):
        gr = _load_gguf_runner(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                            "gguf-runner.py"))
        self.gr = gr
        self.gguf = gguf
        self.lock = threading.Lock()
        self.decider = None
        t0 = time.time()
        self.decider = gr.GgufDecider(gguf, threads=threads, context_tokens=ctx)
        self.load_ms = int((time.time() - t0) * 1000)
        # warmup decode (first call compiles/allocates)
        self.decider.decide("probe state", ["a", "b"], CHOICE_Q)

    def readout(self, state, options, question):
        with self.lock:
            t0 = time.time()
            d = self.decider.decide(state, list(options), question or CHOICE_Q)
            ms = int((time.time() - t0) * 1000)
            out = {"ok": bool(d["ok"]), "note": d.get("note", ""),
                   "probs": d.get("probs") or {o: 0.0 for o in options},
                   "choice": d.get("choice"), "ms": ms}
        return out

    def build_prompt(self, state, options, question):
        """Exact prompt the in-process readout would run, plus the option-
        letter token ids. For the fast path (decider-fast-client.py)."""
        with self.lock:
            t0 = time.time()
            g = self.gr
            item = g.dprompt_build(
                g.Example(state, [g.Q(question or CHOICE_Q, list(options), 0)], "infer"),
                self.decider.tok, g._NoShuffle(),
                max_options=min(g.MAX_OPTIONS, g.DP_MAX),
                max_ctx_tokens=g.MAX_CTX_TOKENS, layout="state_first")
            ids, nopts = item["ids"], item["nopts"][0]
            text = self.decider.tok.decode(ids)
            ms = int((time.time() - t0) * 1000)
            return {"ok": True, "prompt": text, "nopts": nopts,
                    "letters": [self.decider.letters[i] for i in range(nopts)],
                    "ms": ms}


class Handler(BaseHTTPRequestHandler):
    service = None

    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            d = self.service.decider
            self._send(200, {"ok": d is not None, "gguf": self.service.gguf,
                             "loaded": d is not None,
                             "load_ms": self.service.load_ms})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path == "/prompt":
            try:
                req = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
                state = req.get("state") or ""
                options = req.get("options") or []
                if not state or not options:
                    return self._send(400, {"error": "state and options are required"})
                d = self.service.build_prompt(state, options, req.get("question"))
                self._send(200, d)
            except Exception as e:
                self._send(500, {"ok": False, "error": repr(e)[:200]})
            return
        if self.path != "/readout":
            return self._send(404, {"error": "not found"})
        try:
            req = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
            state = req.get("state") or ""
            options = req.get("options") or []
            if not state or not options:
                return self._send(400, {"error": "state and options are required"})
            self._send(200, self.service.readout(state, options, req.get("question")))
        except Exception as e:
            self._send(500, {"ok": False, "note": repr(e)})

    def log_message(self, *a):
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gguf", required=True)
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8091)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--ctx", type=int, default=4096)
    a = ap.parse_args()
    print("loading %s..." % a.gguf, file=sys.stderr, flush=True)
    svc = Service(a.gguf, a.threads, a.ctx)
    Handler.service = svc
    print("decider service ready: %s (%d ms load)" % (a.gguf, svc.load_ms),
          file=sys.stderr, flush=True)
    ThreadingHTTPServer((a.host, a.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
