#!/usr/bin/env python3
"""
Phase 3 unit tests: goal grammar, job catalog, failure taxonomy.

Pure: no network, no fixtures. Run:  python3 tests/reflex/jobs-test.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", ".."))

from r2.jobs import (Goal, GoalGrammarError, Job, JOB_CATALOG,
                     FAILURE_CODES, Failure, deps_consistent, ORIGINS)

PASS = 0
FAIL = 0

def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("ok   %s" % name)
    else:
        FAIL += 1
        print("FAIL %s  %s" % (name, detail))


# --- goal grammar ---------------------------------------------------------
g = Goal.from_dict({"verb": "mine", "object": "granite", "n": 5})
check("goal basic", g.verb == "mine" and g.n == 5)
g2 = Goal.from_dict({"verb": "place", "object": "granite", "at": "site-A"})
check("goal with site", g2.at == "site-A")
for bad in ({"verb": "fly", "object": "x"},             # verb outside grammar
            {"verb": "mine", "object": ""},             # empty object
            {"verb": "mine", "object": "x", "n": 0},    # n must be >= 1
            {"object": "x"},                            # missing verb
            "mine granite"):                            # not an object
    try:
        Goal.from_dict(bad)
        check("goal rejects %r" % (bad if isinstance(bad, str) else bad.get("verb")),
              False, "no exception")
    except GoalGrammarError:
        check("goal rejects %r" % (bad if isinstance(bad, str) else bad.get("verb")),
              True)

f = Failure("unsupported_goal", "verb fly", goal="fly x")
check("unsupported_goal layer=goal", f.layer == "goal")

# --- job catalog ----------------------------------------------------------
check("catalog covers the v5 families + 12.1 additions",
      set(JOB_CATALOG) == {"mine", "harvest", "place", "goto",
                           "give_tool", "pickup", "travel", "wait"})
check("give_tool is external", JOB_CATALOG["give_tool"]["source"] == "external")
check("mine/harvest produce from world",
      all(JOB_CATALOG[t]["produces"] and JOB_CATALOG[t]["source"] == "world"
          for t in ("mine", "harvest")))
check("place consumes", JOB_CATALOG["place"]["consumes"]
      and JOB_CATALOG["place"]["needs"] == ("target", "material"))

j = Job.from_dict({"id": "j1", "type": "place", "target": "site-A",
                   "material": "granite", "quantity": 5,
                   "depends_on": ["j0"]})
check("job round-trip", j.to_dict()["quantity"] == 5
      and j.ledger_deltas() == [("granite", -5)])
check("job missing refs flagged",
      Job.from_dict({"id": "j2", "type": "place"}).missing_refs()
      == ["target", "material"])
for bad in ({"id": "j3", "type": "teleport"},            # unknown type
            {"id": "j4", "type": "mine", "quantity": 0}, # bad quantity
            {"id": "j5", "type": "mine", "depends_on": 7}):
    try:
        Job.from_dict(bad)
        check("job rejects %s" % bad["type"], False, "no exception")
    except ValueError:
        check("job rejects %s" % bad["type"], True)

# --- dependency order -----------------------------------------------------
jobs = [Job("j1", "mine", source="res-17", material="granite", quantity=3),
        Job("j2", "place", target="site-A", material="granite", quantity=3,
            depends_on=["j1"])]
ok, probs = deps_consistent(jobs)
check("deps forward-consistent", ok and not probs)
jobs[1].depends_on = ["j3"]            # unknown id
ok, probs = deps_consistent(jobs)
check("deps unknown id rejected", not ok and probs == ["j2"])
jobs[1].depends_on = ["j1"]
jobs.append(Job("j3", "wait"))
jobs[2].depends_on = ["j1"]
jobs[1].depends_on = ["j3"]            # points backwards
ok, probs = deps_consistent(jobs)
check("deps backward rejected", not ok and probs == ["j2"])

# --- failure taxonomy -----------------------------------------------------
check("frozen codes present",
      set(FAILURE_CODES) == {"unsupported_goal", "planner_invalid_json",
                             "planner_invalid_reference",
                             "planner_dependency_error", "resource_not_found",
                             "target_not_reachable", "claim_conflict",
                             "job_budget_exhausted", "fixture_failed"})
for c, layer in FAILURE_CODES.items():
    try:
        f = Failure(c, "x")
        check("code %s layer %s" % (c, layer), f.layer == layer)
    except ValueError:
        check("code %s layer %s" % (c, layer), False, "unknown code")
try:
    Failure("made_up_code", "x")
    check("unknown code rejected", False, "no exception")
except ValueError:
    check("unknown code rejected", True)

# job origin (13.1): provenance is a frozen field, default planner
check("origins frozen set",
      set(ORIGINS) == {"planner", "operator", "deterministic", "repair"})
j = Job.from_dict({"id": "j1", "type": "wait"})
check("default origin planner", j.origin == "planner")
j2 = Job.from_dict({"id": "j0", "type": "give_tool", "origin": "operator"})
check("operator origin accepted", j2.origin == "operator"
      and j2.to_dict()["origin"] == "operator")
try:
    Job.from_dict({"id": "j9", "type": "wait", "origin": "alien"})
    check("unknown origin rejected", False, "no exception")
except ValueError:
    check("unknown origin rejected", True)

print()
print("jobs-test: %d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
