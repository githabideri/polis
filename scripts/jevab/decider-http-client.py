#!/usr/bin/env python3
"""HTTP readout of the Decider via the 3060 card (llama-mux) — live-loop client.

The Decider 2B (Qwen3.5-2B decision fine-tune, Q8_0) is served by the
llama-mux on the 3060 card (the homelab 3060 box) as `qwen35-decider-2b`.
This script is the production-side twin of `gguf-runner.py` (the C-API
reference implementation): it builds the exact same prompt (no-shuffle,
state_first) and recovers the T=1.3 option-letter readout from the server's
raw full-vocabulary softmax — see report §14 for the protocol and the
validation against the C-API baseline.

The one non-obvious wire detail: on the 925e1179 llama-server the OAI
`top_logprobs` body key is NOT what feeds the N-entries top list on
`/v1/completions` — that mapping only applies to the chat path. Send the raw
llama.cpp `n_probs` body key (pass-through) and the server returns the
requested N raw T=1 full-vocab probabilities in `top_logprobs[]`.

 p_T(i) = p_1(i)^(1/1.3) / sum_j p_1(j)^(1/1.3) (over option letters)

The partition-function constant cancels in the ratio, so the raw T=1 numbers
convert exactly to the T=1.3 readout the model was graded with.

Usage:
 decider-http-client.py [--url http://<card>:8081] [--model qwen35-decider-2b]
 [--corpus DIR] [--max-rows N] [--timeout 120]

`--corpus` is the labeled-set directory (same layout the ab-runner reads:
state/options/oracle/step). Output: one JSON line per row (state, options,
p(oracle), choice, per-option probs, latency) plus a summary object on the
last line. For the live loop, import `decider_readout()` from this file.
"""

import argparse
import json
import statistics
import sys
import time
import types
import urllib.request
from dataclasses import dataclass

DEFAULT_URL = "http://the 3060 model mux" # the 3060 card (Tailscale, the 3060 model container mux)
DEFAULT_MODEL = "qwen35-decider-2b"
T = 1.3
CHOICE_Q = "Which one action is the single best next step right now?"


@dataclass
class Q:
 text: str
 options: list
 gold: int = 0


@dataclass
class Example:
 context: str
 qs: list
 task: str = "infer"
 image: bytes = None


def _stub_decider_infer():
 """The decider package's `infer` module pulls torch at import; we only
 need its Q/Example dataclasses (if the real ones import cleanly, use
 those)."""
 try:
 import decider.infer # noqa: F401
 return True
 except Exception:
 m = types.ModuleType("decider.infer")
 m.Q, m.Example = Q, Example
 sys.modules["decider.infer"] = m
 return False


def load_rows(pattern):
 import glob
 rows = []
 for p in sorted(glob.glob(pattern)):
 data = json.load(open(p))
 for i, r in enumerate(data):
 r = dict(r)
 r["set"] = data.get("set", p)
 r["step"] = data.get("step", i)
 rows.append(r)
 return rows


def build_prompt(state, options, tok):
 from decider.prompt import build, MAX_OPTIONS

 class NoShuffle:
 def shuffle(self, x):
 return x

 def sample(self, xs, k):
 return xs[:k]

 item = build(Example(state, [Q(CHOICE_Q, list(options), 0)], "infer"),
 tok, NoShuffle(), max_options=min(255, MAX_OPTIONS),
 max_ctx_tokens=1536, layout="state_first")
 return item["ids"], item["nopts"][0]


def decider_readout(prompt_text, tok, url=DEFAULT_URL, model=DEFAULT_MODEL,
 timeout=120):
 """Full T=1.3 option readout over the HTTP server. Returns
 (probs_by_letter, latency_s, n_prompt_tokens). probs are keyed by the
 option LETTER (A..), not index."""
 from decider.prompt import letter_ids
 body = json.dumps({
 "model": model, "prompt": prompt_text, "max_tokens": 1,
 "logprobs": True, "top_logprobs": 1, "n_probs": 8192,
 "temperature": 1.0,
 }).encode()
 req = urllib.request.Request(url + "/v1/completions", data=body,
 headers={"Content-Type": "application/json"})
 t0 = time.perf_counter()
 resp = json.load(urllib.request.urlopen(req, timeout=timeout))
 dt = time.perf_counter() - t0
 top = resp["choices"][0]["logprobs"]["content"][0]["top_logprobs"]
 # raw T=1 full-vocab probabilities:
 p1 = {t["id"]: (2.718281828459045 ** t["logprob"] if t["logprob"] is not None else 0.0)
 for t in top}
 # reweight to T over the option letters (constant cancels):
 letters = letter_ids(tok)
 raw = [p1.get(letters[i], 0.0) ** (1.0 / T) for i in range(255)]
 z = sum(raw) or 1.0
 probs = {chr(ord("A") + i): r / z for i, r in enumerate(raw)}
 ntok = resp.get("usage", {}).get("prompt_tokens")
 return probs, dt, ntok


def main():
 ap = argparse.ArgumentParser(description=__doc__)
 ap.add_argument("--url", default=DEFAULT_URL)
 ap.add_argument("--model", default=DEFAULT_MODEL)
 ap.add_argument("--corpus", default=None, help="labeled-set dir (glob *.json)")
 ap.add_argument("--max-rows", type=int, default=0)
 ap.add_argument("--timeout", type=float, default=120.0)
 args = ap.parse_args()

 from transformers import AutoTokenizer
 _stub_decider_infer()
 import os
 here = os.path.dirname(os.path.abspath(__file__))
 # Tokenizer + `decider` package live in `models/decider-2b/` (repo: the small
 # text files only; the.gguf/.safetensors weights live on host model stores,
 # never in git — see scripts/jevab/README.md). Point DECIDER_TOKENIZER at a
 # local decider directory if the repo layout differs.
 tok = AutoTokenizer.from_pretrained(os.environ.get(
 "DECIDER_TOKENIZER", os.path.join(here, "..", "..", "models", "decider-2b")))

 rows = load_rows(os.path.join(args.corpus, "*.json"))
 if args.max_rows:
 rows = rows[:args.max_rows]

 out = []
 for r in rows:
 ids, nopts = build_prompt(r["state"], r["options"], tok)
 text = tok.decode(ids)
 assert tok.encode(text, add_special_tokens=False) == ids, \
 f"prompt re-encode mismatch {r['set']}#{r['step']}"
 probs, dt, ntok = decider_readout(text, tok, args.url, args.model, args.timeout)
 po = {o: probs[chr(ord("A") + i)] for i, o in enumerate(r["options"][:nopts])}
 choice = max(po, key=po.get)
 rec = {"set": r["set"], "step": r["step"], "oracle": r["oracle"],
 "choice": choice, "p_oracle": round(po[r["oracle"]], 4),
 "probs": {k: round(v, 4) for k, v in po.items()},
 "latency_s": round(dt, 3), "n_prompt_tokens": ntok,
 "correct": choice == r["oracle"]}
 out.append(rec)
 print(json.dumps(rec), flush=True)

 n = len(out)
 top1 = sum(r["correct"] for r in out) / n
 po = [r["p_oracle"] for r in out]
 brier = sum((p - (1 if r["correct"] else 0)) ** 2 for p, r in zip(po, out)) / n
 cc = [p for p, r in zip(po, out) if r["correct"]]
 cw = [p for p, r in zip(po, out) if not r["correct"]]
 summary = {"n": n, "top1": round(top1, 4),
 "mean_p_oracle": round(sum(po) / n, 4), "brier": round(brier, 4),
 "conf_correct": round(sum(cc) / len(cc), 4) if cc else None,
 "conf_wrong": round(sum(cw) / len(cw), 4) if cw else None,
 "mean_latency_s": round(statistics.mean(r["latency_s"] for r in out), 3),
 "p90_latency_s": round(sorted(r["latency_s"] for r in out)[int(0.9 * (n - 1))], 3)}
 print("SUMMARY " + json.dumps(summary), flush=True)


if __name__ == "__main__":
 main()
