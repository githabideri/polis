#!/usr/bin/env python3
"""
R2 Phase 5 - planner A/B measurement against the 27B.

Feeds each fixture case (tests/reflex/fixtures/planner-cases.json)
through the REAL pipeline: WorldModel.observe_scan -> candidate
projection (build_planner_prompt) -> one 27B call (temperature 0) ->
deterministic validator (validate_plan) -> semantic outcome scoring.

Scores (design doc section 10): parse, schema, reference, dependency,
material/ledger - plus the goal-achievement semantics the validator
cannot see (a plan can pass the validator and still not achieve the
goal - that gap is a first-class measurement, not a bug in the
validator).

Run on the polis CT (LAN reach to the 27B):
  python3 scripts/jevab/planner-ab-measure.py \
    --cases tests/reflex/fixtures/planner-cases.json \
    --llm http://<llm>:8080 --llm-model <model> \
    --out data/planner-ab-2026-09-28.json

The result JSON records model names and case ids only - no host names,
no addresses (the repo is publication-staged).
"""
import argparse
import json
import os
import sys
import time

REPO = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    "..", "..")
sys.path.insert(0, REPO)

from r2.worldmodel import WorldModel
from r2.plannerprompt import build_planner_prompt
from r2.plancheck import validate_plan
from r2.jobs import Goal, GoalGrammarError


def http_json(url, payload, timeout=180):
    import urllib.request
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def call_llm(llm, model, prompt, timeout=180):
    t0 = time.time()
    r = http_json(llm + "/v1/chat/completions", {
        "model": model,
        "temperature": 0,
        "max_tokens": 600,
        "chat_template_kwargs": {"enable_thinking": False},
        "messages": [
            {"role": "system",
             "content": "You answer with ONE JSON value only. No prose."},
            {"role": "user", "content": prompt}],
    }, timeout=timeout)
    ms = int((time.time() - t0) * 1000)
    try:
        msg = r["choices"][0]["message"]
        text = (msg.get("content")
                or msg.get("reasoning_content") or "").strip()
    except Exception:
        text = ""
    return text, ms


def build_world(case):
    """WorldModel from the case's block list (+ measured drops + fixtures)."""
    wm = WorldModel()
    wm.new_tick(reason="planner_scan")
    wm.observe_scan(
        {"Ok": True, "Data": {"blocks": case["blocks"]}},
        reason="planner_scan")
    for rid, drop in (case.get("drops") or {}).items():
        rec = wm.resources.get(rid)
        if rec is None:
            print("  !! drops key %s not in the index (%s)"
                  % (rid, sorted(wm.resources)))
            continue
        rec.record_drop(drop, wm.seq, time.monotonic() * 1000,
                        int(time.time() * 1000))
    for f in case.get("fixtures") or []:
        wm.register_fixture(f["id"], f["kind"], f["cell"],
                            f["requirement"])
        # the fixture's CURRENT condition (a stamped observation)
        wm.observe_fixture(f["id"], f.get("condition", False),
                           reason="fixture_setup")
    return wm


def goal_achieved(jobs, goal, case, index):
    """The semantic check the validator cannot do: does this plan, if
    executed, achieve the goal? (heuristic over the frozen job types)"""
    if goal.verb == "place":
        mat = goal.object
        have = 0
        for j in jobs:
            if j.type == "place" and (j.target == goal.at or
                                      goal.at is None) \
                    and j.material == mat:
                have += j.quantity or 1
        return have >= (goal.n or 1)
    if goal.verb == "mine":
        # the goal object is a name; achieved by a mine job whose source
        # is a plausible candidate (material or its block family matches)
        fam = goal.object
        for j in jobs:
            if j.type != "mine":
                continue
            rec = index.get(j.source)
            if rec is None:
                return False
            if j.material in (fam, getattr(rec, "material", None)) or \
                    fam in (j.material, getattr(rec, "material", None)):
                return True
        return False
    if goal.verb == "harvest":
        for j in jobs:
            if j.type != "harvest":
                continue
            rec = index.get(j.source)
            if rec is None or rec.kind != "crop":
                return False
            if goal.object.split("-")[1] in str(rec.material) or \
                    rec.material in goal.object:
                return True
        return False
    if goal.verb == "goto":
        return any(j.type in ("goto", "travel")
                   and (j.target == goal.at or goal.at is None)
                   for j in jobs)
    return False


def score_case(case, llm, model):
    goal = Goal.from_dict(case["goal"])
    wm = build_world(case)
    fixtures = []
    for fid, f in sorted(wm.fixtures.items()):
        cond = wm.fixture_observations.get(fid)
        fixtures.append({"id": fid, "kind": f.kind,
                         "requirement": f.requirement,
                         "condition": cond.present if cond else None})
    prompt, index = build_planner_prompt(
        wm, goal, case["inventory"], fixtures, center=(512010, 0, 512019))
    raw, ms = call_llm(llm, model, prompt)
    out = {"id": case["id"], "cat": case["cat"], "expect": case["expect"],
           "latency_ms": ms, "prompt_chars": len(prompt),
           "raw": raw[:600], "prompt": None}

    # -- the validator (deterministic) --------------------------------------
    jobs, failure = validate_plan(raw, index, case["inventory"])
    if failure is not None:
        out.update({"valid": False,
                    "failure": failure.to_dict(),
                    "outcome": "rejected",
                    "achieved": False})
        return out
    achieved = goal_achieved(jobs, goal, case, index)
    out.update({"valid": True, "achieved": achieved,
                "jobs": [j.to_dict() for j in jobs],
                "outcome": "valid" if achieved else "valid-unachieved"})
    return out


def verdict(case, res):
    """CORRECT / CORRECT-CAUGHT / WRONG with a reason, per the case's
    expected outcome class."""
    exp = case["expect"]
    o = res["outcome"]
    if o == "rejected":
        if exp == "reject":
            return "CORRECT", "honest rejection as expected"
        if exp == "either":
            return "CORRECT", "honest rejection (acceptable)"
        return "WRONG", "rejected a goal the candidates could meet"
    if o == "valid-unachieved":
        return "WRONG", "plan passes the validator but does not achieve " \
            "the goal (semantic gap - the measurement's key signal)"
    # o == "valid"
    if exp == "valid":
        return "CORRECT", "achieved"
    if exp == "reject":
        return "WRONG", "invented a plan for an unmet goal"
    # exp == "either"
    uses_external = any(j["type"] == "give_tool" for j in res["jobs"])
    if not uses_external:
        return "CORRECT", "world-only plan"
    return "CORRECT", "external supply used (acceptable for this case)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", required=True)
    ap.add_argument("--llm", required=True)
    ap.add_argument("--llm-model", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--only", default="", help="comma list of case ids")
    args = ap.parse_args()
    only = set(args.only.split(",")) if args.only else None

    cases = json.load(open(os.path.join(REPO, args.cases)))
    results = []
    for c in cases:
        if only and c["id"] not in only:
            continue
        t0 = time.time()
        try:
            r = score_case(c, args.llm, args.llm_model)
        except Exception as e:
            r = {"id": c["id"], "cat": c["cat"], "expect": c["expect"],
                 "outcome": "error", "error": repr(e)}
        v, why = verdict(c, r)
        r["verdict"], r["why"] = v, why
        r["wall_s"] = round(time.time() - t0, 1)
        results.append(r)
        print("%s [%s] %s: %s (%s)  %ds  %s"
              % (r["id"], r["cat"], r["expect"], v, r["outcome"],
                 r.get("wall_s", 0), r.get("why") or
                 (r.get("failure") or {}).get("code", "")), flush=True)

    os.makedirs(os.path.dirname(os.path.join(REPO, args.out)), exist_ok=True)
    doc = {"cases_file": args.cases, "model": args.llm_model,
           "date": time.strftime("%Y-%m-%d %H:%M %Z"),
           "results": results,
           "summary": summarize(results)}
    with open(os.path.join(REPO, args.out), "w") as f:
        json.dump(doc, f, indent=1)
    print()
    for k, v in doc["summary"].items():
        print("%s: %s" % (k, v))
    print("wrote %s" % args.out)


def summarize(results):
    s = {"total": len(results)}
    for v in ("CORRECT", "WRONG"):
        s[v] = sum(1 for r in results if r.get("verdict") == v)
    s["honest_rejections"] = sum(
        1 for r in results if r.get("outcome") == "rejected")
    s["validator_catches"] = sum(
        1 for r in results
        if r.get("valid") is False and
        (r.get("failure") or {}).get("code") in (
            "resource_not_found", "planner_invalid_reference"))
    s["valid_unachieved"] = sum(
        1 for r in results if r.get("outcome") == "valid-unachieved")
    s["latency_ms_p50"] = sorted(
        r.get("latency_ms", 0) for r in results)[len(results) // 2] \
        if results else 0
    by_cat = {}
    for r in results:
        by_cat.setdefault(r["cat"], []).append(r.get("verdict"))
    s["by_category"] = {
        k: {"correct": v.count("CORRECT"), "wrong": v.count("WRONG"),
            "total": len(v)} for k, v in sorted(by_cat.items())}
    return s


if __name__ == "__main__":
    main()
