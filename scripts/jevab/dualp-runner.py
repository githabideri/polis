#!/usr/bin/env python3
"""dualp-runner.py -- batch dual readout (Laya noul + Decider choice) over
labeled (state, proposal) pairs, for threshold re-derivation.

Pure-stdlib (the game testbed compatible). For each row in the input JSON
(list of {id, mission, state, options, oracle, proposed} -- `proposed`
may be None, meaning "the oracle is the proposal under evaluation"):

 1. Laya 421M noul pre-filter (openjev /v1/systemone, the v5 question)
 p_laya = P(yes | state, proposal)
 2. Decider 2B choice readout (fast path: decider-service /prompt +
 card /v1/completions, T=1.3 letter-subset softmax)
 p_dec = P(proposal | state, options)

Output: one JSON object per row on stdout (JSONL) plus a summary file.
`correct` = (proposal == oracle). The tau re-derivation splits on it.

Usage:
 dualp-runner.py --rows ft-rows.json --out dualp.jsonl \
 --openjev the Laya noul endpoint \
 --prompt the CPU batch box's prompt endpoint --card http://the 3060 model mux \
 [--model qwen35-decider-2b] [--skip-laya] [--skip-decider]
"""
import argparse
import json
import sys
import time
import urllib.request

# --- v5's mission definitions (copied, kept in sync manually) -----------
LAYA_INSTRUCTIONS = {
 "mine": (
 "Answer yes only if the proposed action matches the current phase: "
 "travel phase needs goto_target, mine phase needs mine_target, "
 "pickup phase needs pickup_item (while an item is still on the "
 "ground), return phase needs goto_base, done phase needs wait, and "
 "the bot carries the tool the phase needs (mining needs a "
 "pickaxe). give_tool is correct only when the bot lacks the tool "
 "its phase needs. place_block is never correct for this mining "
 "task. No otherwise - a proposed action that contradicts the "
 "phase, skips an unfinished step, or uses a missing tool is no."),
 "harvest": (
 "Answer yes only if the proposed action matches the current phase: "
 "travel phase needs goto_target, harvest phase needs "
 "harvest_target, pickup phase needs pickup_item (while a "
 "harvested item is still on the ground), return phase needs "
 "goto_base, done phase needs wait. place_block is never correct "
 "for this harvesting task. No otherwise - a proposed action that "
 "contradicts the phase or skips an unfinished step is no "
 "(returning to base while the crop is still present skips the "
 "goal)."),
 # build missions are not part of the live loop yet; skip Laya for them
}

T = 1.3
E = 2.718281828459045


def _post(url, payload, timeout):
 body = json.dumps(payload).encode()
 req = urllib.request.Request(url, data=body,
 headers={"Content-Type": "application/json"})
 return json.load(urllib.request.urlopen(req, timeout=timeout))


def laya_noul(openjev, mission, state, timeout=60):
 q = {"type": "noul", "instructions": LAYA_INSTRUCTIONS[mission]}
 t0 = time.time()
 try:
 r = _post(openjev.rstrip("/") + "/v1/systemone",
 {"state": state, "questions": {"proposal_ok": q}}, timeout)
 a = (r.get("answers") or {}).get("proposal_ok") or {}
 return {"p": a.get("noul"), "ms": int((time.time() - t0) * 1000),
 "error": r.get("_error")}
 except Exception as e:
 return {"p": None, "ms": int((time.time() - t0) * 1000),
 "error": repr(e)[:160]}


def decider_fast(prompt_url, card_url, model, state, options, timeout=60):
 t0 = time.time()
 try:
 pr = _post(prompt_url.rstrip("/") + "/prompt",
 {"state": state, "options": list(options)}, timeout)
 if not pr.get("ok"):
 raise RuntimeError("prompt: " + str(pr.get("error", pr))[:160])
 letters, nopts = pr["letters"], pr["nopts"]
 resp = _post(card_url.rstrip("/") + "/v1/completions", {
 "model": model, "prompt": pr["prompt"], "max_tokens": 1,
 "logprobs": True, "top_logprobs": 1, "n_probs": 8192,
 "temperature": 1.0,
 }, timeout)
 top = resp["choices"][0]["logprobs"]["content"][0]["top_logprobs"]
 p1 = {t["id"]: (E ** t["logprob"] if t["logprob"] is not None else 0.0)
 for t in top}
 raw = [p1.get(l, 0.0) ** (1.0 / T) for l in letters[:nopts]]
 z = sum(raw) or 1.0
 probs = {o: r / z for o, r in zip(options[:nopts], raw)}
 for o in options[nopts:]:
 probs[o] = 0.0
 return {"p": None, "probs": probs,
 "choice": max(probs, key=probs.get),
 "ms": int((time.time() - t0) * 1000), "error": None}
 except Exception as e:
 return {"p": None, "probs": None, "choice": None,
 "ms": int((time.time() - t0) * 1000), "error": repr(e)[:160]}


def main():
 ap = argparse.ArgumentParser(description=__doc__,
 formatter_class=argparse.RawDescriptionHelpFormatter)
 ap.add_argument("--rows", required=True)
 ap.add_argument("--out", required=True)
 ap.add_argument("--openjev", default="the Laya noul endpoint")
 ap.add_argument("--prompt", default="the CPU batch box's prompt endpoint")
 ap.add_argument("--card", default="http://the 3060 model mux")
 ap.add_argument("--model", default="qwen35-decider-2b")
 ap.add_argument("--skip-laya", action="store_true")
 ap.add_argument("--skip-decider", action="store_true")
 ap.add_argument("--timeout", type=float, default=90.0)
 ap.add_argument("--pace", type=float, default=0.5,
 help="sleep seconds between rows. REQUIRED > 0 for the "
 "the 3060 host mux: this llama.cpp build corrupts tail-token "
 "logprobs when multiple shared-prefix prompts land "
 "in one server batch with --cache-prompt (2026-09-25 "
 "R1: 14/96 rows read p_oracle=0.000 in a tight batch "
 "but 0.64-1.000 spaced; live loop requests are "
 "seconds apart and unaffected).")
 a = ap.parse_args()

 rows = json.load(open(a.rows))
 if isinstance(rows, dict):
 rows = rows.get("rows", [])

 out = open(a.out, "w")
 n_ok = n_err = 0
 t0 = time.time()
 for i, r in enumerate(rows):
 if a.pace and i > 0:
 time.sleep(a.pace)
 # proposal under evaluation: the row's `proposed`, or the oracle
 # when the row carries no natural proposal (A/B corpus convention)
 prop = r.get("proposed")
 if prop is None:
 prop = r["oracle"]
 state = r["state"]
 if "proposed action:" not in state:
 state = state + "\nproposed action: " + prop

 rec = {"id": r.get("id"), "mission": r.get("mission"),
 "family": r.get("family"), "oracle": r.get("oracle"),
 "proposed": prop,
 "correct": bool(prop == r.get("oracle"))}

 if not a.skip_laya and r.get("mission") in LAYA_INSTRUCTIONS:
 rec.update({"laya": laya_noul(a.openjev, r["mission"], state,
 a.timeout)})
 if not a.skip_decider:
 if not getattr(main, "_warmed", False):
 # prewarm: force the mux model switch BEFORE the timed batch
 decider_fast(a.prompt, a.card, a.model,
 "task: mine the marker block, then return to base\n"
 "current phase: done\nfacts: bot at (1, 2, 3), "
 "near_target=no, near_base=yes, marker_present=no\n"
 "carrying: empty\nitems: none\nsince_last_step: "
 "no change\nlast_action: done\nproposed action: wait",
 ["goto_target", "mine_target", "pickup_item",
 "place_block", "give_tool", "goto_base", "wait"],
 a.timeout)
 main._warmed = True
 d = decider_fast(a.prompt, a.card, a.model, state,
 r.get("options") or [], a.timeout)
 rec["decider"] = {
 "p": (d["probs"] or {}).get(prop),
 "choice": d["choice"], "ms": d["ms"], "error": d["error"],
 }

 ok = rec.get("laya", {}).get("p") is not None and rec.get("decider", {}).get("p") is not None
 n_ok += 1 if ok else 0
 n_err += 0 if ok else 1
 rec["n_ok"] = int(ok)
 out.write(json.dumps(rec) + "\n")
 out.flush()
 if (i + 1) % 20 == 0:
 sys.stderr.write("...%d/%d (%d ok) %ds\n" %
 (i + 1, len(rows), n_ok, int(time.time() - t0)))
 out.close()
 sys.stderr.write("done: %d rows, %d with both readouts, %d s\n" %
 (len(rows), n_ok, int(time.time() - t0)))
 return 0


if __name__ == "__main__":
 sys.exit(main())
