#!/usr/bin/env python3
"""Three-way decider A/B: base vs FT1 vs FT2, per corpus slice.

Clean protocol (report 17): rendered prompts via the CPU batch box's /prompt
service, one-shot completions against the mux, paced. Measures:

  valworld-96 top-1, mean/min p_oracle (both FTs used it as the
                       early-stop target; base never saw it)
  oov-96 top-1, mean p_oracle (R1a slice; pattern-seen for
 the FTs, never seen for any model at row level)
  abstain-45 the NEW slice for FT2: states where none of the 7
                       actions is right. Quietness metrics: fraction
                       top-1 == wait, mean/max of per-row max-p (a
                       calibrated abstainer should be QUIET: pick the
                       escape option with moderate confidence, not a
                       confident wrong action).

One JSONL per (model, slice) in --out-dir + one summary table on
stdout. Restores the resident 35B when done.
"""
import argparse
import importlib.util
import json
import os
import time
import urllib.request

_spec = importlib.util.spec_from_file_location(
    "decider_fast_client",
    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                 "decider-fast-client.py"))
_dfc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_dfc)
fast_readout = _dfc.fast_readout

MODELS = ["qwen35-decider-2b", "qwen35-decider-2b-ft", "qwen35-decider-2b-ft2"]


def _post(url, payload, timeout):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=timeout))


def measure(prompt, card, model, rows, out_path, pace):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    top1 = 0
    psum = 0.0
    pmin = 1.0
    n_ok = 0
    maxps = []
    wait_top1 = 0
    with open(out_path, "w") as out:
        for r in rows:
            res = fast_readout(prompt, card, model, r["state"],
                               r["options"], timeout=90)
            p_oracle = None
            maxp = None
            choice = None
            if res.get("ok"):
                n_ok += 1
                p_oracle = res["probs"].get(r["oracle"]) or 0.0
                choice = res["choice"]
                top1 += 1 if choice == r["oracle"] else 0
                psum += p_oracle
                pmin = min(pmin, p_oracle)
                maxp = max(res["probs"].values()) if res["probs"] else 0.0
                maxps.append(maxp)
                wait_top1 += 1 if choice == "wait" else 0
            out.write(json.dumps({
                "row": r["id"], "family": r.get("family"),
                "mission": r.get("mission"),
                "ok": bool(res.get("ok")), "choice": choice,
                "oracle": r["oracle"], "p_oracle": p_oracle,
                "max_p": maxp, "ms": res.get("ms"),
                "error": (res.get("error") or "")[:100],
            }) + "\n")
            out.flush()
            time.sleep(pace)
    return {
        "model": model,
        "rows": len(rows), "ok": n_ok,
        "top1": top1,
        "top1_pct": round(100.0 * top1 / max(n_ok, 1), 1),
        "p_oracle_mean": round(psum / max(n_ok, 1), 4),
        "p_oracle_min": round(pmin, 4),
        "maxp_mean": round(sum(maxps) / max(n_ok, 1), 4),
        "maxp_max": round(max(maxps), 4) if maxps else None,
        "wait_top1_pct": round(100.0 * wait_top1 / max(n_ok, 1), 1),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--prompt", default=os.environ.get("POLIS_PROMPT_URL"))
    ap.add_argument("--card", default=os.environ.get("POLIS_CARD_URL"))
    ap.add_argument("--valworld", default="/opt/polis/data/valworld-2026-09-26.json")
    ap.add_argument("--oov", default="/opt/polis/data/r1-probe-rows-2026-09-25.json")
    ap.add_argument("--abstain", default="/opt/polis/data/ft2-val.json",
                    help="the 141-row FT2 val set; abstain rows are the "
                         "family=abstain subset")
    ap.add_argument("--out-dir", default="/opt/polis/data/ft2-ab")
    ap.add_argument("--pace", type=float, default=0.25)
    ap.add_argument("--restore", default="qwen36-35b-mtp")
    a = ap.parse_args()

    valworld = json.load(open(a.valworld))
    oov = json.load(open(a.oov))
    abstain = [r for r in json.load(open(a.abstain))
               if r.get("family") == "abstain"]
    slices = {"valworld": valworld, "oov": oov, "abstain": abstain}
    print("slices:", {k: len(v) for k, v in slices.items()}, flush=True)

    results = []
    for m in MODELS:
        for name, rows in slices.items():
            t0 = time.time()
            s = measure(a.prompt, a.card, m, rows,
                        os.path.join(a.out_dir, "%s-%s.jsonl"
                                     % (m, name)), a.pace)
            s["slice"] = name
            s["sec"] = int(time.time() - t0)
            results.append(s)
            print(json.dumps(s), flush=True)

    with open(os.path.join(a.out_dir, "summary.json"), "w") as f:
        json.dump(results, f, indent=1)

    # restore the courteous resident
    try:
        _post(a.card.rstrip("/") + "/v1/completions",
              {"model": a.restore, "prompt": "ok", "max_tokens": 1}, 180)
        print("restored", a.restore, flush=True)
    except Exception as e:
        print("restore error:", repr(e)[:100], flush=True)


if __name__ == "__main__":
    main()
