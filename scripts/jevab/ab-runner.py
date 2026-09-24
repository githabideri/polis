#!/usr/bin/env python3
"""ab-runner.py -- A/B evaluation of Jev-style decision models on the polis labeled corpus.

Feeds every labeled row (state_text + oracle action) through each candidate model as a
*choice* question over the mission action set, then scores: top-1 accuracy vs oracle,
p(oracle), multiclass Brier, latency, and calibration (mean confidence on correct vs
incorrect rows).

Usage (on the A/B container):
  ab-runner.py --model laya   --sets /opt/jevab/corpus/data/*.json --out results/laya.json
  ab-runner.py --model decider --sets ... --out results/decider.json
  ab-runner.py --model semif  --sets ... --out results/semif.json
  ab-runner.py --model all    --sets ... --out results/ab-all.json
  add --smoke 5 to only run 5 rows (interface validation)

Row contract (labeled set 'rows'):
  state_text: str   -- the full state the reflex sees
  oracle:     str   -- correct action label
  proposal:   str   -- what the production policy proposed (context only)
  phase:      str
  mission:    "mine" | "harvest" (inferred from the set)
"""
import argparse
import glob
import json
import os
import sys
import time

MINE_ACTIONS = ["goto_target", "mine_target", "goto_base", "wait"]
HARVEST_ACTIONS = ["goto_target", "harvest_target", "goto_base", "wait"]
CHOICE_Q = ("Given the bot's current game state, choose the single best action for the bot "
            "to execute next.")


def infer_mission(path, meta):
    s = (path + " " + " ".join(str(v) for v in meta.values() if isinstance(v, str))).lower()
    return "harvest" if "harvest" in s else "mine"


def load_rows(glob_pattern):
    rows = []
    for path in sorted(glob.glob(glob_pattern)):
        meta = json.load(open(path))
        mission = infer_mission(path, meta)
        actions = HARVEST_ACTIONS if mission == "harvest" else MINE_ACTIONS
        for r in meta.get("rows", []):
            if not r.get("state_text") or not r.get("oracle"):
                continue
            rows.append({
                "set": os.path.basename(path),
                "mission": mission,
                "step": r.get("step"),
                "state": r["state_text"],
                "oracle": r["oracle"],
                "proposal": r.get("proposal"),
                "phase": r.get("phase"),
                "options": actions,
            })
    return rows


def summarize(rows, tag):
    n = len(rows)
    acc = sum(1 for r in rows if r["choice"] == r["oracle"]) / n
    brier = sum(sum((p - (1.0 if o == r["oracle"] else 0.0)) ** 2
                    for o, p in r["probs"].items()) for r in rows) / n
    p_oracle = sum(r["probs"][r["oracle"]] for r in rows) / n
    cc = [r["probs"][r["choice"]] for r in rows if r["choice"] == r["oracle"]]
    cw = [r["probs"][r["choice"]] for r in rows if r["choice"] != r["oracle"]]
    return {
        "model": tag,
        "rows": n,
        "acc_top1": round(acc, 4),
        "mean_p_oracle": round(p_oracle, 4),
        "brier": round(brier, 4),
        "mean_ms": round(sum(r["ms"] for r in rows) / n, 1),
        "conf_correct": round(sum(cc) / len(cc), 4) if cc else None,
        "conf_wrong": round(sum(cw) / len(cw), 4) if cw else None,
        "by_mission": {},
    }


def _by_mission(rows, s):
    for m in ("mine", "harvest"):
        sub = [r for r in rows if r["mission"] == m]
        if sub:
            s["by_mission"][m] = {
                "n": len(sub),
                "acc_top1": round(sum(1 for r in sub if r["choice"] == r["oracle"]) / len(sub), 4),
                "mean_p_oracle": round(sum(r["probs"][r["oracle"]] for r in sub) / len(sub), 4),
            }
    return s


# ---------------------------------------------------------------- laya
def run_laya(rows):
    from laya import Router
    t0 = time.perf_counter()
    router = Router()
    INSTRUCTIONS = "Decide which single action the agent takes next in this situation."
    for r in rows:
        ts = time.perf_counter()
        q = {"type": "choice",
             "instructions": INSTRUCTIONS,
             "criteria": {o: None for o in r["options"]}}
        out = router.predict(r["state"], {"act": q}, model="typed-decisions")
        r["ms"] = (time.perf_counter() - ts) * 1000
        ans = out["answers"]["act"]
        if ans.get("type") != "choice":
            print("laya unexpected answer:", json.dumps(ans)[:300], file=sys.stderr)
            raise SystemExit(2)
        r["probs"] = {o: float(ans["probabilities"].get(o, 0.0)) for o in r["options"]}
        r["choice"] = ans["choice"]
        print(f"  laya {r['set']}#{r['step']}: {r['choice']} p_oracle={r['probs'][r['oracle']]:.3f}", file=sys.stderr)
    print(f"laya: loaded+ran {len(rows)} rows in {time.perf_counter()-t0:.1f}s", file=sys.stderr)


# ---------------------------------------------------------------- decider
_DEC = None
def run_decider(rows):
    global _DEC
    if _DEC is None:
        from decider.infer import Decider
        _DEC = Decider("/var/jevab/weights/decider-2b", device="cpu")
    for r in rows:
        ts = time.perf_counter()
        out = _DEC.decide(r["state"], [{"question": CHOICE_Q, "options": r["options"]}])[0]
        r["ms"] = (time.perf_counter() - ts) * 1000
        r["probs"] = {o: float(out["probs"].get(o, 0.0)) for o in r["options"]}
        r["choice"] = out["choice"]
        print(f"  decider {r['set']}#{r['step']}: {r['choice']} p_oracle={r['probs'][r['oracle']]:.3f}", file=sys.stderr)


# ---------------------------------------------------------------- semif
_SEM = None
def run_semif(rows):
    global _SEM
    if _SEM is None:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        from semif_phase1.direct import score as semif_score
        w = "/var/jevab/weights/qwen3.5-4b"
        tok = AutoTokenizer.from_pretrained(w, trust_remote_code=True)
        model = AutoModelForCausalLM.from_pretrained(
            w, dtype=torch.bfloat16, trust_remote_code=True)
        model.eval()
        _SEM = (model, tok, {"source": "Qwen/Qwen3.5-4B", "revision": "main"})
    model, tok, meta = _SEM
    for i, r in enumerate(rows):
        row = {"id": f"{r['set']}#{r['step']}", "state": r["state"],
               "question": CHOICE_Q,
               "options": [{"id": o, "description": ""} for o in r["options"]]}
        ts = time.perf_counter()
        out = semif_score(model, tok, row, meta)
        r["ms"] = (time.perf_counter() - ts) * 1000
        probs = out.get("probs") or out.get("option_probs") or {}
        # map letter/option ids back
        norm = {}
        for k, v in probs.items():
            key = k.strip().lower()
            for j, o in enumerate(r["options"]):
                if key in (o.lower(), chr(ord("A") + j)):
                    norm[o] = float(v)
        r["probs"] = {o: norm.get(o, 0.0) for o in r["options"]}
        r["choice"] = max(r["probs"], key=r["probs"].get)
        print(f"  semif {r['set']}#{r['step']}: {r['choice']} p_oracle={r['probs'][r['oracle']]:.3f}", file=sys.stderr)


RUNNERS = {"laya": run_laya, "decider": run_decider, "semif": run_semif}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, choices=list(RUNNERS) + ["all"])
    ap.add_argument("--sets", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--smoke", type=int, default=0)
    args = ap.parse_args()

    rows = load_rows(args.sets)
    if args.smoke:
        # one row per mission for interface validation
        seen = set()
        sel = []
        for r in rows:
            if r["mission"] not in seen:
                seen.add(r["mission"])
                sel.append(r)
        rows = sel[:args.smoke]
    print(f"loaded {len(rows)} rows", file=sys.stderr)

    models = list(RUNNERS) if args.model == "all" else [args.model]
    out = {"corpus": args.sets, "rows": len(rows), "models": {}}
    for m in models:
        t0 = time.perf_counter()
        RUNNERS[m](rows)
        s = _by_mission(rows, summarize(rows, m))
        s["wall_s"] = round(time.perf_counter() - t0, 1)
        out["models"][m] = s
        print(json.dumps(s, indent=1))

    out_path = os.path.expanduser(args.out)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    rows_path = out_path + ".rows.json"
    slim = [{k: r.get(k) for k in ("set", "step", "mission", "state", "options", "oracle", "choice", "probs", "ms")} for r in rows]
    json.dump(slim, open(rows_path, "w"), indent=1)
    out["rows"] = None  # per-row detail in sidecar file
    out["rows_detail"] = os.path.basename(rows_path)
    json.dump(out, open(out_path, "w"), indent=1)
    print(f"wrote {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
