#!/usr/bin/env python3
"""Building plan system tests (13.11, 09-29 evening rev 2): the hut is a
5x5 with 3-high walls and a stepped roof - load, validate, compile.
Pure - no harness, no world."""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.join(HERE, "..", "..")
sys.path.insert(0, REPO)

from r2.buildplans import BuildingPlan, PlanError, load_plan, list_plans

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


BUILDS = os.path.join(REPO, "builds")
W = D = 5

# 1. the hut loads and validates
p = load_plan(os.path.join(BUILDS, "hut.json"))
check("hut loads", p.name == "hut" and p.footprint == (5, 5))
check("hut has 106 blocks", p.total_blocks() == 106,
      str(p.total_blocks()))
check("hut materials closed (106 granite)",
      p.materials == {"granite": 106}, str(p.materials))
check("hut provides shelter", "shelter" in p.provides)
check("hut door is 1 wide x 2 high at (2,0)",
      p.entry == (2, 0, 2) and p.door_height == 2)

# 2. the geometry invariants (validate() passed at load - assert the
#    shape directly too)
cells = {(dx, dy, dz) for (dx, dy, dz), _ in p.blocks}
check("hut opening is empty (the two door cells)",
      (2, 1, 0) not in cells and (2, 2, 0) not in cells)
check("hut has the lintel above the opening",
      (2, 3, 0) in cells)
check("hut has the threshold floor under the door",
      (2, 0, 0) in cells)
floor = {(dx, dz) for (dx, dy, dz), _ in p.blocks if dy == 0}
check("hut floor is the full 5x5",
      floor == {(x, z) for x in range(5) for z in range(5)})
perim = {(x, z) for x in range(5) for z in range(5)
         if x in (0, 4) or z in (0, 4)}
walls = {(dx, dz) for (dx, dy, dz), _ in p.blocks if 1 <= dy <= 3}
check("hut walls = perimeter x3 minus the 2 opening cells",
      len([c for c in p.blocks if 1 <= c[0][1] <= 3]) == 46 and
      walls == perim, str(len([c for c in p.blocks
                               if 1 <= c[0][1] <= 3])))
roof = {(dx, dy, dz) for (dx, dy, dz), _ in p.blocks if dy >= 4}
tier = lambda dy: {(dx, dz) for (dx, d2, dz) in roof if d2 == dy}
check("hut roof is a stepped 5x5 -> 3x3 -> 1x1",
      len(tier(4)) == 25 and len(tier(5)) == 9 and len(tier(6)) == 1
      and tier(6) == {(2, 2)})

# 3. compilation: phases ordered bottom-up, absolute cells
phases = p.phases([10, 3, 20])
by_dy = {}
for n, cs in phases:
    dy = cs[0][0][1] - 3
    by_dy[dy] = by_dy.get(dy, 0) + len(cs)
check("phases ordered bottom-up (dy 0..6)",
      list(by_dy) == [0, 1, 2, 3, 4, 5, 6], str(list(by_dy)))
check("phase sizes 25/15/15/16/25/9/1 (door cells leave the wall tiers)",
      [by_dy[d] for d in range(7)] == [25, 15, 15, 16, 25, 9, 1],
      str([by_dy[d] for d in range(7)]))
check("no two phases share a cell",
      len({c for n, cs in phases for c, _ in cs}) == 106)

# 3b. corners-first order (09-29, the last-corner dead-end): the four
#     corners of a layer come first (placed last they have no open
#     ledge and no outside support - runs 13-15 died at walls(4,1,4));
#     edges follow (they stand on their interior neighbour).
by_layer = {}
for n, cs in p.phases((0, 0, 0)):
    by_layer[cs[0][0][1]] = [c for c, _ in cs]
check("wall corners first (dy1)",
      by_layer[1][:4] == [(0, 1, 0), (0, 1, 4), (4, 1, 0), (4, 1, 4)],
      str(by_layer[1][:4]))
check("roof-5 corners first (dy4)",
      by_layer[4][:4] == [(0, 4, 0), (0, 4, 4), (4, 4, 0), (4, 4, 4)],
      str(by_layer[4][:4]))
check("roof-3 corners first (dy5)",
      by_layer[5][:4] == [(1, 5, 1), (1, 5, 3), (3, 5, 1), (3, 5, 3)],
      str(by_layer[5][:4]))
check("floor corners first (dy0) - harmless there",
      by_layer[0][:4] == [(0, 0, 0), (0, 0, 4), (4, 0, 0), (4, 0, 4)],
      str(by_layer[0][:4]))

# 4. validation failures
def plan_file(d):
    f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    json.dump(d, f)
    f.close()
    return f.name


def expect_error(name, d, needle):
    path = plan_file(d)
    try:
        load_plan(path)
        check(name, False, "no error raised")
    except PlanError as e:
        check(name, needle in e.detail, e.detail)
    finally:
        os.unlink(path)


def fresh():
    return json.load(open(os.path.join(BUILDS, "hut.json")))


d = fresh()
d["materials"] = {"granite": 105}            # wrong total
expect_error("materials mismatch rejected", d, "do not match")
d = fresh()
d["blocks"].append({"d": [2, 1, 0], "m": "granite"})
d["materials"] = {"granite": 107}            # block inside the opening
expect_error("blocked opening rejected", d, "door must stay open")
d = fresh()
d["blocks"] = [b for b in d["blocks"]
               if not (b["d"][0] == 2 and b["d"][1] == 0
                       and b["d"][2] == 2)]  # floor hole
d["materials"] = {"granite": 105}
expect_error("floor hole rejected", d, "floor is not solid")
d = fresh()
d["blocks"] = [b for b in d["blocks"] if b["d"][1] < 7]
d["blocks"].append({"d": [0, 7, 0], "m": "granite"})
d["materials"] = {"granite": 107}
expect_error("layer above the cap rejected", d, "layer")
d = fresh()
d["blocks"] = []
d["materials"] = {}
expect_error("empty plan rejected", d, "no blocks")
try:
    load_plan(os.path.join(BUILDS, "no-such-building.json"))
    check("unknown plan raises", False)
except Exception:
    check("unknown plan raises", True)

# 5. the library index
check("list_plans finds the hut", list_plans(BUILDS) == ["hut"],
      str(list_plans(BUILDS)))
check("list_plans on a missing dir is empty",
      list_plans(os.path.join(BUILDS, "nope")) == [])

print()
print("buildplans-test: %d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
