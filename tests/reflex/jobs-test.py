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
g3 = Goal.from_dict({"verb": "construct", "object": "granite",
                    "at": "site-A"})
check("construct aliases to build (09-28)", g3.verb == "build")
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
check("catalog covers the v5 families + 12.1 + 13.7 sow + 09-28 build "
      "+ 13.11 plan + 10-04 craft + 10-06 chop",
      set(JOB_CATALOG) == {"mine", "harvest", "place", "goto",
                           "give_tool", "pickup", "travel", "wait",
                           "sow", "build", "build_plan", "craft", "chop"})
from r2.jobs import PLANNER_JOB_TYPES
check("build_plan + chop are GOAL-SCOPED (not in the planner vocabulary)",
      "build_plan" not in PLANNER_JOB_TYPES and
      "chop" not in PLANNER_JOB_TYPES and
      "build" in PLANNER_JOB_TYPES and len(PLANNER_JOB_TYPES) == 11)
g4 = Goal.from_dict({"verb": "build-plan", "object": "hut",
                    "at": "site-A"})
check("build-plan goal (plan id as object)",
      g4.verb == "build-plan" and g4.object == "hut")
check("give_tool is external", JOB_CATALOG["give_tool"]["source"] == "external")
check("mine/harvest produce from world",
      all(JOB_CATALOG[t]["produces"] and JOB_CATALOG[t]["source"] == "world"
          for t in ("mine", "harvest")))
check("place consumes", JOB_CATALOG["place"]["consumes"]
      and JOB_CATALOG["place"]["needs"] == ("target", "material"))
check("sow consumes on a site target (13.7 M2)",
      JOB_CATALOG["sow"]["consumes"]
      and JOB_CATALOG["sow"]["needs"] == ("target", "material"))
check("build consumes on a site target (09-28 ring platform)",
      JOB_CATALOG["build"]["consumes"]
      and JOB_CATALOG["build"]["needs"] == ("target", "material"))

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

# --- chop (2026-10-06 door campaign) ---------------------------------------
chop = Job.from_dict({"id": "c1", "type": "chop",
                      "at": [512016, 155, 512011], "n": 1,
                      "expect": "log-grown-*", "origin": "deterministic"})
check("chop parses (at/n/expect, operator fields)",
      chop.at == [512016, 155, 512011] and chop.quantity == 1 and
      chop.expect == "log-grown-*" and chop.origin == "deterministic")
check("chop needs its cell (missing at)",
      Job.from_dict({"id": "c2", "type": "chop"}).missing_refs() == ["at"])
check("chop catalog row (world producer, no tool)",
      JOB_CATALOG["chop"]["produces"] and
      JOB_CATALOG["chop"]["source"] == "world" and not
      JOB_CATALOG["chop"]["consumes"])
for bad, why in (({"id": "c3", "type": "chop", "at": [1, 2]},
                  "at needs 3 ints"),
                 ({"id": "c4", "type": "chop", "at": [1, 2, 3],
                   "expect": ["x"]}, "expect must be a string"),
                 ({"id": "c5", "type": "chop", "n": 0}, "n must be >= 1")):
    try:
        Job.from_dict(bad)
        check("chop rejects %s" % why, False, "no exception")
    except ValueError:
        check("chop rejects %s" % why, True)
# cell-targeted mine: `at` replaces the resource id as its reference
m1 = Job.from_dict({"id": "m1", "type": "mine", "at": [512018, 149, 512033],
                    "n": 1, "material": "dirt"})
check("cell mine: at is the reference (no source needed)",
      m1.missing_refs() == [] and m1.at == [512018, 149, 512033])
check("resource mine still needs a source",
      Job.from_dict({"id": "m2", "type": "mine",
                     "source": "res-x", "material": "granite"}).missing_refs() == []
      and Job.from_dict({"id": "m3", "type": "mine",
                         "material": "granite"}).missing_refs() == ["source"])

print()
print("jobs-test: %d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
