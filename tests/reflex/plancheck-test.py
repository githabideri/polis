#!/usr/bin/env python3
"""
Phase 4 unit tests: the deterministic plan validator.

Pure: stub resource/site records, no network. Run:
  python3 tests/reflex/plancheck-test.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", ".."))

from r2.plancheck import validate_plan

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


class Rec:
    def __init__(self, id, material, drops=None):
        self.id, self.material, self.drops = id, material, drops

def R(i, m, drops=None):  # resource stub
    return Rec(i, m, drops)

INDEX = {
    "res-01": R("res-01", "stone-granite", drops="stone-granite"),
    "res-02": R("res-02", "granite"),         # a world that drops placeable
    "res-03": R("res-03", "crop-rye-2"),
    "site-A": {"id": "site-A", "kind": "build-site",
               "requirement": "granite"},
    "site-B": {"id": "site-B", "kind": "build-site",
               "requirement": "empty"},
}
INV_EMPTY = {}
INV_GRANITE = {"granite": 5}


# 1. valid: place from inventory
jobs, f = validate_plan(
    '[{"id":"j1","type":"place","target":"site-A","material":"granite",'
    '"quantity":5}]', INDEX, INV_GRANITE)
check("place from inventory valid", jobs is not None and f is None,
      str(f and f.to_dict()))

# 2. valid: external supply then place
jobs, f = validate_plan(
    '[{"id":"j1","type":"give_tool","material":"granite","quantity":5},'
    '{"id":"j2","type":"place","target":"site-A","material":"granite",'
    '"quantity":5,"depends_on":["j1"]}]', INDEX, INV_EMPTY)
check("give->place valid", jobs is not None and f is None,
      str(f and f.to_dict()))

# 3. THE mine->place mismatch (12.9): mine yields stone-granite,
#    place needs granite, no inventory -> resource_not_found
jobs, f = validate_plan(
    '[{"id":"j1","type":"mine","source":"res-01","material":"stone-granite",'
    '"quantity":5},'
    '{"id":"j2","type":"place","target":"site-A","material":"granite",'
    '"quantity":5,"depends_on":["j1"]}]', INDEX, INV_EMPTY)
check("mine(stone)->place(granite) REJECTED",
      jobs is None and f is not None and f.code == "resource_not_found",
      str(f and f.to_dict()))
check("  ... attributed to the query layer (frozen mapping)",
      f is not None and f.layer == "query")

# 4. mine->place MATCH: resource drops the placeable material directly
jobs, f = validate_plan(
    '[{"id":"j1","type":"mine","source":"res-02","material":"granite",'
    '"quantity":5},'
    '{"id":"j2","type":"place","target":"site-A","material":"granite",'
    '"quantity":5,"depends_on":["j1"]}]', INDEX, INV_EMPTY)
check("mine(granite)->place(granite) valid", jobs is not None and f is None,
      str(f and f.to_dict()))

# 5. unknown reference
jobs, f = validate_plan(
    '[{"id":"j1","type":"place","target":"site-Z","material":"granite"}]',
    INDEX, INV_GRANITE)
check("unknown site rejected",
      jobs is None and f.code == "planner_invalid_reference",
      str(f and f.to_dict()))

# 6. unparseable
jobs, f = validate_plan("not json at all", INDEX, INV_GRANITE)
check("garbage -> planner_invalid_json",
      jobs is None and f.code == "planner_invalid_json",
      str(f and f.to_dict()))

# 7. explicit rejection form
jobs, f = validate_plan('{"reject":"no granite in scope"}', INDEX, INV_GRANITE)
check("reject form -> unsupported_goal",
      jobs is None and f.code == "unsupported_goal"
      and "no granite in scope" in f.detail, str(f and f.to_dict()))

# 8. backward dependency
jobs, f = validate_plan(
    '[{"id":"j1","type":"wait"},{"id":"j2","type":"wait","depends_on":["j1"]}]',
    INDEX, INV_GRANITE)
check("wait->wait forward ok", jobs is not None)
jobs, f = validate_plan(
    '[{"id":"j1","type":"place","target":"site-B","material":"granite",'
    '"depends_on":["j2"]},'
    '{"id":"j2","type":"give_tool","material":"granite","quantity":3}]',
    INDEX, INV_EMPTY)
check("backward dependency rejected",
      jobs is None and f.code == "planner_dependency_error",
      str(f and f.to_dict()))

# 9. duplicate claim (two jobs on the same resource)
jobs, f = validate_plan(
    '[{"id":"j1","type":"mine","source":"res-01","material":"stone-granite"},'
    '{"id":"j2","type":"harvest","source":"res-01","material":"stone-granite"}]',
    INDEX, INV_GRANITE)
check("duplicate claim rejected",
      jobs is None and f.code == "claim_conflict", str(f and f.to_dict()))

# 10. producer claims a material its MEASURED drop contradicts
jobs, f = validate_plan(
    '[{"id":"j1","type":"mine","source":"res-01","material":"granite"}]',
    INDEX, INV_GRANITE)
check("producer/measured-drop mismatch rejected",
      jobs is None and f.code == "planner_invalid_reference",
      str(f and f.to_dict()))

# 10b. same claim WITHOUT a measured drop: no claim possible - allowed
jobs, f = validate_plan(
    '[{"id":"j1","type":"mine","source":"res-02","material":"granite"}]',
    INDEX, INV_GRANITE)
check("unmeasured drop: claim passes (unknown is never yes)",
      jobs is not None and f is None, str(f and f.to_dict()))

# 11. quantity cap
jobs, f = validate_plan(
    '[{"id":"j1","type":"give_tool","material":"granite","quantity":101}]',
    INDEX, INV_GRANITE)
check("quantity cap enforced",
      jobs is None and f.code == "planner_invalid_json",
      str(f and f.to_dict()))

# 12. harvest from a crop resource
jobs, f = validate_plan(
    '[{"id":"j1","type":"harvest","source":"res-03",'
    '"material":"crop-rye-2","quantity":3}]', INDEX, INV_GRANITE)
check("harvest crop valid", jobs is not None and f is None,
      str(f and f.to_dict()))

# 13. place needing more than inventory+producer combined
jobs, f = validate_plan(
    '[{"id":"j1","type":"give_tool","material":"granite","quantity":2},'
    '{"id":"j2","type":"place","target":"site-A","material":"granite",'
    '"quantity":5}]', INDEX, INV_EMPTY)
check("under-supplied place rejected",
      jobs is None and f.code == "resource_not_found",
      str(f and f.to_dict()))

print()
print("plancheck-test: %d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)

# 14. goal-aware target check (P5 round-2 F3 gap)
from r2.plancheck import check_goal
from r2.jobs import Goal as _G
g = _G(verb="place", object="granite", at="site-Z")
check("goal intake: unknown site rejected",
      check_goal(g, ["site-A"]) is not None)
check("goal intake: known site passes",
      check_goal(g, ["site-A", "site-Z"]) is None)
check("goal intake: no at -> passes",
      check_goal(_G(verb="mine", object="granite"), []) is None)
jobs, f = validate_plan(
    '[{"id":"j1","type":"place","target":"site-A","material":"granite"}]',
    INDEX, INV_GRANITE, goal=_G(verb="place", object="granite", at="site-B"))
check("plan targeting a different site than the goal rejected",
      jobs is None and f.code == "planner_invalid_reference",
      str(f and f.to_dict()))
jobs, f = validate_plan(
    '[{"id":"j1","type":"place","target":"site-A","material":"granite"}]',
    INDEX, INV_GRANITE, goal=_G(verb="place", object="granite", at="site-A"))
check("plan matching the goal's site passes",
      jobs is not None and f is None, str(f and f.to_dict()))
