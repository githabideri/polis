#!/usr/bin/env python3
"""decider-fast-client.py -- Decider-2B readout via the 3060 card, fast path.

Pure-stdlib client for boxes that do NOT carry the decider package or
tokenizer (e.g. the polis testbed CT). Two hops:

  1. POST <prompt-service>/prompt (the CPU batch box decider-service, which has
 the tokenizer + decider package loaded) -> the exact prompt text the
     in-process readout would run, plus the option-letter token ids.
  2. POST <card>/v1/completions (the 3060 host llama-mux llama-server, over
 the tailnet) with the raw `n_probs` body key (the 925e1179 build's
     OAI `top_logprobs` key does NOT feed the N-entry list on
     /v1/completions -- see decider-http-client.py) -> raw T=1
     full-vocabulary probabilities.

Recovery is the same math as decider-http-client.py:

    p_T(i) = p_1(i)^(1/T) / sum_j p_1(j)^(1/T), T = 1.3, over the
    option letters (the partition-function constant cancels in the ratio).

Expected end-to-end ~100-150 ms/row (LAN prompt hop ~5 ms + tailnet
card inference ~70-100 ms), vs ~3-4 s for the CPU batch box in-process readout.

Usage (CLI):
  decider-fast-client.py --prompt the CPU batch box's prompt endpoint \
      --card http://the 3060 model mux --model qwen35-decider-2b-ft \
      --state-file /path/state.txt --options goto_target,mine_target,...

Importable:
  from decider-fast-client import fast_readout
  r = fast_readout(prompt_url, card_url, model, state, options)
  # -> {"ok": bool, "probs": {option: p}, "choice": option, "ms": int,
  # "error": None|str}
"""
import argparse
import json
import sys
import time
import urllib.request

T = 1.3
E = 2.718281828459045


def _post(url, payload, timeout):
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body,
                                 headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=timeout))


def fast_readout(prompt_url, card_url, model, state, options, timeout=60):
    """One Decider-2B option readout: prompt via the service, inference on
 the card. Returns the same schema as the /readout endpoint."""
    t0 = time.time()
    # hop 1: the exact prompt + letter token ids
    pr = _post(prompt_url.rstrip("/") + "/prompt",
               {"state": state, "options": list(options)}, timeout)
    if not pr.get("ok"):
        return {"ok": False, "probs": None, "choice": None,
                "ms": int((time.time() - t0) * 1000),
                "error": "prompt: " + str(pr.get("error", pr))[:160]}
    letters, nopts = pr["letters"], pr["nopts"]
    # hop 2: raw T=1 full-vocab probabilities from the card
    try:
        resp = _post(card_url.rstrip("/") + "/v1/completions", {
            "model": model, "prompt": pr["prompt"], "max_tokens": 1,
            "logprobs": True, "top_logprobs": 1, "n_probs": 8192,
            "temperature": 1.0,
        }, timeout)
    except Exception as e:
        return {"ok": False, "probs": None, "choice": None,
                "ms": int((time.time() - t0) * 1000),
                "error": "card: " + repr(e)[:160]}
    top = resp["choices"][0]["logprobs"]["content"][0]["top_logprobs"]
    p1 = {t["id"]: (E ** t["logprob"] if t["logprob"] is not None else 0.0)
          for t in top}
    raw = [p1.get(l, 0.0) ** (1.0 / T) for l in letters[:nopts]]
    z = sum(raw) or 1.0
    probs = {o: r / z for o, r in zip(options[:nopts], raw)}
    for o in options[nopts:]:
        probs[o] = 0.0
    choice = max(probs, key=probs.get)
    return {"ok": True, "probs": probs, "choice": choice,
            "ms": int((time.time() - t0) * 1000), "error": None}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--prompt", required=True, help="decider-service base URL")
    ap.add_argument("--card", required=True, help="llama-server/mux base URL")
    ap.add_argument("--model", default="qwen35-decider-2b-ft2",
                    help="model id on the card; base model: qwen35-decider-2b")
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--options", required=True, help="comma-separated")
    ap.add_argument("--timeout", type=float, default=60.0)
    a = ap.parse_args()
    state = open(a.state_file).read()
    options = [o.strip() for o in a.options.split(",") if o.strip()]
    r = fast_readout(a.prompt, a.card, a.model, state, options, a.timeout)
    print(json.dumps(r, indent=1))
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
