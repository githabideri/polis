#!/usr/bin/env python3
"""Nightly val-world canary: the drift guard for the deployed FT decider.

Measures the 96-row external val world (zero overlap with the FT training
corpus - the adoption test of report 16) against the on-demand model on
the 3060 card, using the CLEAN protocol: rendered prompts + one-shot
completions, paced. Never the dualp-runner's per-row fetch pattern (its
batch corruption of 14 rows, report 17, is a tooling artifact, not a
model signal).

Pre-committed degradation criteria (2026-09-26):
 FAIL if top-1 < 90/96 (FT measured 96/96 at adoption)
 or mean p_oracle < 0.95 (FT was ~1.0)
 or any p_oracle < 0.50 (a confident-wrong or broken readout;
 note: p < 0.001 was the batch-corruption
 signature - under the clean protocol it
 means real degradation, not a tooling
 artifact)
 exit 0 = OK, 1 = DEGRADED, 2 = infrastructure (more than half the rows
 errored: the mux/service is sick, not the model).

After measuring, a one-token completion on the 35B restores it as the
resident model (the courteous end state; the mux is on-demand by design,
this just keeps the card where users expect it).

Output: one JSONL line per row in --out-dir (default
/var/log/polis-canary) + a summary line on stdout (journald).
"""
import argparse
import importlib.util
import json
import os
import sys
import time
import urllib.request

# decider-fast-client.py has a hyphen (not an importable name) - load by path
_spec = importlib.util.spec_from_file_location(
 "decider_fast_client",
 os.path.join(os.path.dirname(os.path.abspath(__file__)),
 "decider-fast-client.py"))
_dfc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_dfc)
fast_readout = _dfc.fast_readout


def _post(url, payload, timeout):
 req = urllib.request.Request(url, data=json.dumps(payload).encode(),
 headers={"Content-Type": "application/json"})
 return json.load(urllib.request.urlopen(req, timeout=timeout))


def main():
 ap = argparse.ArgumentParser(
 description=__doc__,
 formatter_class=argparse.RawDescriptionHelpFormatter)
 ap.add_argument("--rows", required=True,
 help="val-world rows JSON (id/state/options/oracle)")
 ap.add_argument("--prompt", default="the CPU batch box's prompt endpoint",
 help="decider-service /prompt endpoint (the CPU batch box)")
 ap.add_argument("--card", default="http://the 3060 model mux",
 help="model mux (the 3060 host the 3060 model container, via tailnet)")
 ap.add_argument("--model", default="qwen35-decider-2b-ft2")
 ap.add_argument("--restore", default="qwen36-35b-mtp",
 help="model to make resident after measuring (empty = skip)")
 ap.add_argument("--out-dir", default="/var/log/polis-canary")
 ap.add_argument("--pace", type=float, default=0.3,
 help="seconds between rows")
 a = ap.parse_args()

 rows = json.load(open(a.rows))
 os.makedirs(a.out_dir, exist_ok=True)
 out = open(os.path.join(a.out_dir,
 time.strftime("%Y-%m-%d") + ".jsonl"), "a")

 top1 = 0
 psum = 0.0
 pmin = 1.0
 n_ok = 0
 errors = 0
 t0 = time.time()
 for r in rows:
 res = fast_readout(a.prompt, a.card, a.model,
 r["state"], r["options"], timeout=90)
 p_oracle = None
 if res.get("ok"):
 n_ok += 1
 p_oracle = res["probs"].get(r["oracle"]) or 0.0
 top1 += 1 if res["choice"] == r["oracle"] else 0
 psum += p_oracle
 pmin = min(pmin, p_oracle)
 else:
 errors += 1
 out.write(json.dumps({
 "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
 "row": r["id"], "mission": r.get("mission"),
 "ok": bool(res.get("ok")), "p_oracle": p_oracle,
 "choice": res.get("choice"), "oracle": r["oracle"],
 "ms": res.get("ms"),
 "error": (res.get("error") or "")[:120],
 }) + "\n")
 out.flush()
 time.sleep(a.pace)
 out.close()

 mean = psum / max(n_ok, 1)
 degraded = errors == 0 and (
 top1 < 90 or mean < 0.95 or pmin < 0.50)
 summary = {
 "model": a.model, "rows": len(rows), "ok": n_ok, "errors": errors,
 "top1": "%d/%d" % (top1, n_ok),
 "p_oracle_mean": round(mean, 4), "p_oracle_min": round(pmin, 4),
 "verdict": "DEGRADED" if degraded else "OK",
 "sec": int(time.time() - t0),
 }
 print(json.dumps(summary), flush=True)

 if a.restore:
 # restore the courteous resident (one-token completion; the mux
 # evicts the decider and loads the restore model)
 try:
 _post(a.card.rstrip("/") + "/v1/completions",
 {"model": a.restore, "prompt": "ok", "max_tokens": 1},
 180)
 summary["restored"] = a.restore
 except Exception as e:
 summary["restore_error"] = repr(e)[:100]
 print(json.dumps({"restore": summary.get("restored"),
 "restore_error": summary.get("restore_error")}),
 flush=True)

 if errors > len(rows) // 2:
 print("canary: more than half the rows errored - infrastructure, "
 "not model", file=sys.stderr)
 return 2
 return 1 if degraded else 0


if __name__ == "__main__":
 sys.exit(main())
