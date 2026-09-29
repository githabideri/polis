#!/usr/bin/env python3
"""Building plan system tests (13.11): load, validate, compile.
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

# 1. the hut loads and validates
p = load_plan(os.path.join(BUILDS, "hut.json"))
check("hut loads", p.name == "hut" and p.footprint == (3, 3))
check("hut has 25 blocks", p.total_blocks() == 25,
      str(p.total_blocks()))
check("hut materials closed (25 granite)",
      p.materials == {"granite": 25}, str(p.materials))
check("hut provides shelter", "shelter" in p.provides)

# 2. the hut is well-formed (validate() passed at load - assert the
#    invariants directly too): the door column is open at the WALL
#    layer (a threshold floor below and an overhang roof above are
#    both normal architecture)
check("hut wall layer is open at the door",
      (1, 1, 0) not in {(dx, dy, dz) for (dx, dy, dz), _ in p.blocks})
check("hut door column has threshold floor + overhang roof",
      (1, 0, 0) in {(dx, dy, dz) for (dx, dy, dz), _ in p.blocks} and
      (1, 2, 0) in {(dx, dy, dz) for (dx, dy, dz), _ in p.blocks})
floor = {(dx, dz) for (dx, dy, dz), _ in p.blocks if dy == 0}
check("hut floor is the full 3x3",
      floor == {(x, z) for x in range(3) for z in range(3)})
walls = {(dx, dz) for (dx, dy, dz), _ in p.blocks if dy == 1}
check("hut walls = perimeter ring minus the door",
      walls == {(x, z) for x in range(3) for z in range(3)
                if (x, z) != (1, 1)} - {(1, 0)})
roof = {(dx, dz) for (dx, dy, dz), _ in p.blocks if dy == 2}
check("hut roof is the full 3x3",
      roof == {(x, z) for x in range(3) for z in range(3)})

# 3. compilation: phases ordered floor -> walls -> roof, absolute cells
phases = p.phases([10, 3, 20])
names = [n for n, _ in phases]
check("phases ordered floor,walls,roof", names == ["floor", "walls",
                                                   "roof"], str(names))
by_name = dict((n, cs) for n, cs in phases)
check("floor phase: 9 blocks at origin layer",
      len(by_name["floor"]) == 9 and
      all(c[1] == 3 for c, _ in by_name["floor"]))
check("walls phase: 7 blocks one layer up",
      len(by_name["walls"]) == 7 and
      all(c[1] == 4 for c, _ in by_name["walls"]))
check("roof phase: 9 blocks two layers up",
      len(by_name["roof"]) == 9 and
      all(c[1] == 5 for c, _ in by_name["roof"]))
check("no two phases share a cell",
      len({c for n, cs in phases for c, _ in cs}) == 25)

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


base = json.load(open(os.path.join(BUILDS, "hut.json")))
d = dict(base)
d["materials"] = {"granite": 24}          # wrong total
expect_error("materials mismatch rejected", d, "do not match")
d = json.load(open(os.path.join(BUILDS, "hut.json")))
d["entry"] = [0, 0]                        # a walled cell
expect_error("blocked entry rejected", d, "door must stay open")
d = json.load(open(os.path.join(BUILDS, "hut.json")))
d["blocks"] = [b for b in d["blocks"]
               if not (b["d"][0] == 1 and b["d"][1] == 0
                       and b["d"][2] == 1)]  # floor hole
d["materials"] = {"granite": 24}
expect_error("floor hole rejected", d, "floor is not solid")
d = json.load(open(os.path.join(BUILDS, "hut.json")))
d["blocks"] = [b for b in d["blocks"] if b["d"][1] < 3]
d["blocks"].append({"d": [0, 4, 0], "m": "granite"})
d["materials"] = {"granite": 25}
expect_error("layer above the cap rejected", d, "layer")
d = json.load(open(os.path.join(BUILDS, "hut.json")))
d["blocks"] = []
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
