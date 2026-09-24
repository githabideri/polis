#!/usr/bin/env python3
"""semif-post.py -- map the SemIf cli (mode=direct, backend=llamacpp) JSONL output
onto the A/B corpus (oracle labels) and produce the same summary schema as
ab-runner.py, so the 4B result is directly comparable to the Decider/Laya rows.

Usage:
  python3 semif-post.py --cli-out results/semif4b-q4.jsonl \
      --sets corpus/data/*.json --tag semif4b-q4 --out results/semif4b-q4-summary.json
"""
import argparse
import glob
import importlib.util
import json
import os

import numpy


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cli-out", required=True)
    ap.add_argument("--sets", required=True)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    spec = importlib.util.spec_from_file_location("ab_runner", "/var/jevab/ab-runner.py")
    ab = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ab)

    # corpus rows: build the same id the cli input used
    MINE = ["goto_target", "mine_target", "goto_base", "wait"]
    HARVEST = ["goto_target", "harvest_target", "goto_base", "wait"]
    labels = {}
    for path in sorted(glob.glob(args.sets)):
        meta = json.load(open(path))
        s = (path + " " + " ".join(str(v) for v in meta.values() if isinstance(v, str))).lower()
        mission = "harvest" if "harvest" in s else "mine"
        actions = HARVEST if mission == "harvest" else MINE
        for r in meta.get("rows", []):
            if not r.get("state_text") or not r.get("oracle"):
                continue
            rid = f"{os.path.basename(path)}#{r.get('step')}"
            labels[rid] = {
                "set": os.path.basename(path),
                "mission": mission,
                "step": r.get("step"),
                "options": actions,
                "oracle": r["oracle"],
            }

    out_rows = []
    extra = []
    n_total = 0
    with open(args.cli_out) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            n_total += 1
            d = json.loads(line)
            lab = labels.get(d["id"])
            if lab is None:
                print(f"warn: no corpus label for {d['id']}", flush=True)
                continue
            option_ids = d.get("option_ids") or lab["options"]
            probs = {option_ids[j]: float(p)
                     for j, p in enumerate(d["probabilities"][:len(option_ids)])}
            choice = max(probs, key=probs.get)
            r = {
                "set": lab["set"], "mission": lab["mission"], "step": lab["step"],
                "options": lab["options"], "oracle": lab["oracle"],
                "probs": probs, "choice": choice,
                "ms": float(d.get("forward_seconds", 0.0)) * 1000.0,
                "note": "",
            }
            out_rows.append(r)
            extra.append({
                "id": d["id"],
                "allowed_token_mass": d.get("allowed_token_mass"),
                "full_vocab_argmax_id": d.get("full_vocab_argmax_id"),
                "total_seconds": d.get("total_seconds"),
                "prompt_tokens": d.get("input_tokens"),
            })

    rows = out_rows
    s = ab._by_mission(rows, ab.summarize(rows, args.tag))
    s["rows_total"] = n_total
    s["rows_ok"] = len(rows)
    s["mean_allowed_token_mass"] = float(numpy.mean(
        [e["allowed_token_mass"] for e in extra if e["allowed_token_mass"] is not None]))
    s["mean_input_tokens"] = float(numpy.mean(
        [e["prompt_tokens"] for e in extra if e["prompt_tokens"] is not None]))
    s["readout"] = "semif direct, llamacpp GGUF, T=1 native"
    s["gguf"] = os.path.basename(json.loads(open(args.cli_out).readline())["model"]["gguf"]["file"])

    out = {"corpus": args.sets, "rows": len(rows), "models": {args.tag: s}}
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(out, f, indent=1)
    with open(args.out + ".rows.json", "w") as f:
        json.dump(out_rows, f, indent=1)
    with open(args.out + ".extra.json", "w") as f:
        json.dump(extra, f, indent=1)
    print(json.dumps(s, indent=1))


if __name__ == "__main__":
    main()
