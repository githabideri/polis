#!/usr/bin/env python3
"""
Phase 4 unit tests: the deterministic plan validator.

Pure: stub resource/site records, no network. Run:
  python3 tests/reflex/plancheck-test.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", ".."))

from r2.plancheck import (validate_plan, check_craft_pattern,
                          check_chop_target)

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

# 15. build (09-28 ring platform): external supply then one composite
#     job placing N blocks around the site
jobs, f = validate_plan(
    '[{"id":"j1","type":"give_tool","material":"granite","quantity":4},'
    '{"id":"j2","type":"build","target":"site-A","material":"granite",'
    '"quantity":4,"depends_on":["j1"]}]', INDEX, INV_EMPTY)
check("give->build valid", jobs is not None and f is None,
      str(f and f.to_dict()))
jobs, f = validate_plan(
    '[{"id":"j1","type":"build","target":"site-A","material":"granite",'
    '"quantity":4}]', INDEX, INV_EMPTY)
check("under-supplied build rejected",
      jobs is None and f.code == "resource_not_found",
      str(f and f.to_dict()))
jobs, f = validate_plan(
    '[{"id":"j1","type":"build","target":"site-A","material":"granite",'
    '"quantity":4}]',
    INDEX, INV_GRANITE, goal=_G(verb="build", object="granite",
                                at="site-B"))
check("build at a different site than the goal rejected",
      jobs is None and f.code == "planner_invalid_reference",
      str(f and f.to_dict()))
jobs, f = validate_plan(
    '[{"id":"j1","type":"build","target":"site-A","material":"granite",'
    '"quantity":4}]',
    INDEX, INV_GRANITE, goal=_G(verb="build", object="granite",
                                at="site-A"))
check("build matching the goal's site passes",
      jobs is not None and f is None, str(f and f.to_dict()))

# 16. build_plan (13.11): goal-scoped - only a build-plan goal may
#     carry one; it must target the goal's site
jobs, f = validate_plan(
    '[{"id":"j1","type":"build_plan","plan":"hut","target":"site-A"}]',
    INDEX, INV_GRANITE, goal=_G(verb="build-plan", object="hut",
                                at="site-A"))
check("build-plan goal: build_plan job at the goal's site passes",
      jobs is not None and f is None, str(f and f.to_dict()))
jobs, f = validate_plan(
    '[{"id":"j1","type":"build_plan","plan":"hut","target":"site-A"}]',
    INDEX, INV_GRANITE, goal=_G(verb="mine", object="granite"))
check("build_plan outside a build-plan goal rejected (vocabulary gate)",
      jobs is None and f.code == "planner_invalid_json",
      str(f and f.to_dict()))
jobs, f = validate_plan(
    '[{"id":"j1","type":"build_plan","plan":"hut","target":"site-A"}]',
    INDEX, INV_GRANITE, goal=_G(verb="build-plan", object="hut",
                                at="site-B"))
check("build_plan at a different site than the goal rejected",
      jobs is None and f.code == "planner_invalid_reference",
      str(f and f.to_dict()))

# --- operator campaigns (2026-10-06 door chain) ----------------------------
# The shaped crude-door recipe as the live endpoint exposes it: a 2x3
# pattern, the axe as a tool ingredient (present, never consumed), the
# log family cell, the stick cell.
DOOR = {
    "name": "grid/door-crude", "output": "door-crude", "shapeless": False,
    "pattern": "AS,PS,PS", "width": 2, "height": 3,
    "ingredients": [
        {"code": "axe", "qty": 1, "tags": "tool-axe", "isTool": True},
        {"code": "log-placed", "qty": 1},
        {"code": "stick", "qty": 1},
    ],
}
# check_craft_pattern: full inventory -> ok, tool NOT subtracted.
# (the campaign chops THREE branchy leaves: 2 logs + 3 sticks + the axe)
ok, missing, subs = check_craft_pattern(
    DOOR, {"axe-felling-copper": 1, "log-placed-oak-ud": 2, "stick": 3}, 1)
check("shaped: full inventory passes (family + glob matching)",
      ok and not missing, str(missing))
check("shaped: tool cell present but not subtracted",
      not any(k.startswith("axe") for k, _ in subs) and
      ("log-placed-oak-ud", 2) in subs and ("stick", 3) in subs,
      str(subs))
# zero logs -> no assignment can fill the grid -> rejected
ok, missing, _ = check_craft_pattern(
    DOOR, {"axe-felling-copper": 1, "log-placed-oak-ud": 0, "stick": 2}, 1)
check("shaped: zero logs -> rejected under every assignment",
      not ok and any("log" in m for m in missing), str(missing))
# no axe -> rejected (a craft without the tool is a refusal, not a wait)
ok, missing, _ = check_craft_pattern(
    DOOR, {"log-placed-oak-ud": 2, "stick": 2}, 1)
check("shaped: axe missing -> rejected",
      not ok and any("tool" in m for m in missing), str(missing))
# 2 runs -> double the cells (4 logs, 4 sticks)
ok, missing, _ = check_craft_pattern(
    DOOR, {"axe-felling-copper": 1, "log-placed-oak-ud": 4, "stick": 4}, 2)
check("shaped: n=2 doubles the cell requirement, still one axe",
      ok, str(missing))
# the OLD harness (no pattern exposed) stays rejected
ok, missing, _ = check_craft_pattern(
    {"name": "grid/door-crude", "output": "door-crude", "shapeless": False,
     "ingredients": DOOR["ingredients"]},
    {"axe-felling-copper": 1, "log-placed-oak-ud": 2, "stick": 2}, 1)
check("shaped without an exposed pattern stays rejected (old harness)",
      not ok, str(missing))

# The LIVE endpoint shape (2026-10-07): one ingredient per grid cell,
# row-major - a faithful projection of the engine's ResolvedIngredients.
# The tool cell is code "*:*" + tag tool-axe (wildcard: the engine
# matches the collectible's tag set; the validator matches the tool
# noun against the item code's tokens).
DOOR_PC = {
    "name": "crude door", "output": "door-crude", "shapeless": False,
    "pattern": "AS,PS,PS", "width": 2, "height": 3,
    "ingredients": [
        {"id": "A", "code": "*:*", "qty": 1,
         "tags": ["tool-axe"], "isTool": True},
        {"id": "S", "code": "stick", "qty": 1, "tags": [], "isTool": False},
        {"id": "P", "code": "log-placed-*-ud", "qty": 1,
         "tags": [], "isTool": False},
        {"id": "S", "code": "stick", "qty": 1, "tags": [], "isTool": False},
        {"id": "P", "code": "log-placed-*-ud", "qty": 1,
         "tags": [], "isTool": False},
        {"id": "S", "code": "stick", "qty": 1, "tags": [], "isTool": False},
    ],
}
ok, missing, subs = check_craft_pattern(
    DOOR_PC, {"axe-felling-copper": 1, "log-placed-oak-ud": 2, "stick": 3}, 1)
check("shaped per-cell (live endpoint): full inventory passes",
      ok and not missing, str(missing))
check("shaped per-cell: tool present but not subtracted",
      not any(k.startswith("axe") for k, _ in subs) and
      ("log-placed-oak-ud", 2) in subs and ("stick", 3) in subs, str(subs))
ok, missing, _ = check_craft_pattern(
    DOOR_PC, {"log-placed-oak-ud": 2, "stick": 3}, 1)
check("shaped per-cell: axe missing -> rejected",
      not ok and any("tool" in m for m in missing), str(missing))
# a cell/letter position mismatch means the mapping is not exposed
DOOR_BAD = {"name": "crude door", "output": "door-crude", "shapeless": False,
            "pattern": "AS,PS,PS", "width": 2, "height": 3,
            "ingredients": [dict(x) for x in DOOR_PC["ingredients"]]}
DOOR_BAD["ingredients"][1]["id"] = "P"
ok, missing, _ = check_craft_pattern(
    DOOR_BAD, {"axe-felling-copper": 1, "log-placed-oak-ud": 2, "stick": 3}, 1)
check("shaped per-cell: cell/letter position mismatch rejected",
      not ok, str(missing))

# validate_plan end-to-end: the campaign's full ledger - the give's axe
# and the chops' planned drops are what the craft's pattern check sees
idx = {}
INV = {}  # a fresh-world bot carries nothing yet
jobs, f = validate_plan(
    [{"id": "j1", "type": "give_tool", "material": "axe-felling-copper", "n": 1},
     {"id": "j2", "type": "chop", "at": [512016, 155, 512011], "n": 1,
      "material": "log-placed-oak-ud"},
     {"id": "j3", "type": "chop", "at": [512016, 156, 512011], "n": 1,
      "material": "log-placed-oak-ud"},
     {"id": "j4", "type": "chop", "at": [512017, 157, 512011], "n": 1,
      "material": "stick"},
     {"id": "j5", "type": "chop", "at": [512018, 157, 512011], "n": 1,
      "material": "stick"},
     {"id": "j6", "type": "chop", "at": [512017, 158, 512011], "n": 1,
      "material": "stick"},
     {"id": "j7", "type": "craft", "source": "door-crude",
      "material": "door-crude", "n": 1},
     {"id": "j8", "type": "mine", "at": [512018, 149, 512033], "n": 1,
      "material": "dirt"},
     {"id": "j9", "type": "place", "material": "door-crude",
      "target": "site-door", "n": 1}],
    index={"site-door": {"id": "site-door", "kind": "build-site",
                        "requirement": "empty"}},
    inventory=INV, recipes=[DOOR],
    cells={(512016, 155, 512011): "game:log-grown-oak-ud",
           (512016, 156, 512011): "game:log-grown-oak-ud",
           (512017, 157, 512011): "game:leavesbranchy-grown-oak",
           (512018, 157, 512011): "game:leavesbranchy-grown-oak",
           (512017, 158, 512011): "game:leavesbranchy-grown-birch",
           (512018, 149, 512033): "game:soil-low-none"},
    campaign=True)
check("campaign: the full door chain validates (give->chops->craft->mine->place)",
      jobs is not None and f is None, str(f and f.to_dict()))

# the same list WITHOUT campaign=True: chop is outside the 27B vocabulary
jobs, f = validate_plan(
    [{"id": "j2", "type": "chop", "at": [512016, 155, 512011], "n": 1}],
    index={}, inventory={}, recipes=None, cells=None, campaign=False)
check("chop in a (non-campaign) plan -> vocabulary gate",
      jobs is None and f.code == "planner_invalid_json", str(f and f.to_dict()))

# a chop at an EMPTY cell: the world scan rejects it before execution
jobs, f = validate_plan(
    [{"id": "j2", "type": "chop", "at": [512016, 155, 512011], "n": 1,
      "expect": "log-grown-*"}],
    index={}, inventory={}, recipes=None,
    cells={(512016, 155, 512011): "game:air"}, campaign=True)
check("chop at an air cell rejected before execution",
      jobs is None and f.code == "resource_not_found", str(f and f.to_dict()))

# a chop whose LIVE block does not match the expected block family
# (expect names the block that IS at the cell, not the drop it makes)
jobs, f = validate_plan(
    [{"id": "j2", "type": "chop", "at": [512016, 155, 512011], "n": 1,
      "expect": "log-grown-*"}],
    index={}, inventory={}, recipes=None,
    cells={(512016, 155, 512011): "game:rock-granite"}, campaign=True)
check("chop live-block family mismatch rejected (granite is not a log)",
      jobs is None and f.code == "planner_invalid_reference",
      str(f and f.to_dict()))

# a grown log at the cell satisfies the log-grown family even though
# the DROP (the material claim) is a placed log
jobs, f = validate_plan(
    [{"id": "j2", "type": "chop", "at": [512016, 155, 512011], "n": 1,
      "expect": "log-grown-*", "material": "log-placed-oak-ud"}],
    index={}, inventory={}, recipes=None,
    cells={(512016, 155, 512011): "game:log-grown-oak-ud"}, campaign=True)
check("chop: grown live block + placed-log drop claim validates",
      jobs is not None, str(f and f.to_dict()))

# a cell mine (campaign) budgets its declared material; without
# campaign=True the same job has no resolvable reference
jobs, f = validate_plan(
    [{"id": "j8", "type": "mine", "at": [512018, 149, 512033], "n": 1,
      "material": "dirt"}],
    index={}, inventory={}, recipes=None,
    cells={(512018, 149, 512033): "game:soil-low-none"}, campaign=True)
check("cell mine (campaign): the cell IS the reference",
      jobs is not None and f is None, str(f and f.to_dict()))
jobs, f = validate_plan(
    [{"id": "j8", "type": "mine", "at": [512018, 149, 512033], "n": 1,
      "material": "dirt"}],
    index={}, inventory={}, recipes=None, cells=None, campaign=False)
check("cell mine (non-campaign plan) has no resolvable reference",
      jobs is None, str(f and f.to_dict()))

# a cell mine at an EMPTY cell is rejected before execution (4b)
jobs, f = validate_plan(
    [{"id": "j8", "type": "mine", "at": [512018, 149, 512033], "n": 1,
      "material": "dirt"}],
    index={}, inventory={}, recipes=None,
    cells={(512018, 149, 512033): "game:air"}, campaign=True)
check("cell mine at air rejected before execution",
      jobs is None and f.code == "resource_not_found",
      str(f and f.to_dict()))

# the shaped craft with the inventory the bot ACTUALLY has at plan time
# (nothing yet) is rejected - the ledger projection is what saves the
# campaign plan; a campaign that skips the chops does not get the logs
jobs, f = validate_plan(
    [{"id": "j7", "type": "craft", "source": "door-crude",
      "material": "door-crude", "n": 1}],
    index={}, inventory={}, recipes=[DOOR], cells=None, campaign=True)
check("craft without its planned drops rejected (no free logs)",
      jobs is None and f.code == "resource_not_found",
      str(f and f.to_dict()))

# check_chop_target direct: expect = the live-block family
check("chop target: exact code ok",
      check_chop_target([1, 2, 3], "stick", "stick") is None)
check("chop target: glob family ok",
      check_chop_target([1, 2, 3], "log-grown-*", "log-grown-oak-ud") is None)
check("chop target: family root ok",
      check_chop_target([1, 2, 3], "log-grown", "log-grown-oak-ud") is None)
check("chop target: mismatch fails",
      check_chop_target([1, 2, 3], "log-grown-*", "rock-granite") is not None)

print()
print("plancheck-test: %d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
