#!/usr/bin/env python3
"""
J1 (2026-10-10, early-game ladder) contract test: the knap job and
the flint-tools chain (P1: stone knife + axe from the world's flint).

Pure: no network, no game world. The chain is data; the test renders
it and validates it against the same pre-execution checks an
operator campaign gets (vocabulary gate, recipe table, material
ledger). Live-world facts (surface cell, item codes, the grid
recipe names) are PARAMETERS - the test supplies stubs, the runner
supplies reality (the live recipe names were probed from the engine
assets + the /polis/recipes endpoint on the run world).

Run:  python3 tests/contract/knap-test.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", ".."))

from r2.chains import CHAINS, render
from r2.plancheck import validate_plan
from r2.jobs import JOB_CATALOG, Job

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


SURFACE = [512100, 126, 511990]
RECIPES = [
    {"name": "recipes/grid/tool/knife.json",
     "output": "knife-generic-flint", "shapeless": False,
     "pattern": "T,S", "width": 1, "height": 2,
     "ingredients": [{"code": "knifeblade-flint", "qty": 1},
                     {"code": "stick", "qty": 1}]},
    {"name": "recipes/grid/tool/axe.json",
     "output": "axe-flint", "shapeless": False,
     "pattern": "H,S", "width": 1, "height": 2,
     "ingredients": [{"code": "axehead-flint", "qty": 1},
                     {"code": "stick", "qty": 1}]},
]

# --- registry ---------------------------------------------------------------
check("knap is in the job catalog (produces+consumes)",
      JOB_CATALOG.get("knap", {}).get("produces") is True
      and JOB_CATALOG.get("knap", {}).get("consumes") is True)
check("flint-tools is a registered chain",
      "flint-tools" in CHAINS)

# --- schema: from_dict ------------------------------------------------------
j = Job.from_dict({"id": "k1", "type": "knap",
                   "at": SURFACE, "material": "flint",
                   "recipes": ["knifeblade-flint"], "n": 1,
                   "origin": "deterministic"})
check("knap parses (at + material + recipes)",
      j.at == SURFACE and j.material == "flint"
      and j.recipes == ["knifeblade-flint"])
try:
    Job.from_dict({"id": "k2", "type": "knap",
                   "at": SURFACE, "material": "flint",
                   "origin": "deterministic"})
    check("knap without recipes is rejected", False, "no exception")
except ValueError as e:
    check("knap without recipes is rejected", "recipes" in str(e))
try:
    Job.from_dict({"id": "k3", "type": "knap",
                   "at": SURFACE, "material": "flint",
                   "recipes": "knifeblade-flint",
                   "origin": "deterministic"})
    check("knap recipes as a bare string is rejected", False,
          "no exception")
except ValueError as e:
    check("knap recipes as a bare string is rejected", True)

# --- render: shape ----------------------------------------------------------
jobs = render("flint-tools", {"surface_at": SURFACE})
seq = [j["type"] for j in jobs]
check("renders give x3 -> knap -> craft x2",
      seq == ["give_tool", "give_tool", "give_tool",
              "knap", "craft", "craft"], str(seq))
check("the three gives are operator-labeled scaffolding",
      all(j["origin"] == "operator" for j in jobs[:3])
      and all(j["origin"] == "deterministic" for j in jobs[3:]))
check("the knap is pinned to the surface cell with both heads",
      jobs[3]["at"] == SURFACE
      and jobs[3]["material"] == "flint"
      and jobs[3]["recipes"] == ["knifeblade-flint",
                                 "axehead-flint"])
check("the crafts name the assembled tools",
      jobs[4]["material"] == "knife-generic-flint"
      and jobs[5]["material"] == "axe-flint")

try:
    render("flint-tools", {})
    check("missing surface_at raises", False, "no exception")
except ValueError as e:
    check("missing surface_at raises", "surface_at" in str(e))

jobs2 = render("flint-tools", {"surface_at": SURFACE,
                               "give": [("flint", 4),
                                        ("knappingsurface", 1),
                                        ("stick", 3)]})
check("explicit give wins over the default scaffolding",
      [j["n"] for j in jobs2[:3]] == [4, 1, 3])

# --- validator: the campaign passes with the recipe table --------------------
index = {}
jobs3, fail = validate_plan(render("flint-tools", {"surface_at": SURFACE}),
                            index, {}, recipes=RECIPES,
                            campaign=True)
check("rendered chain validates as a campaign (ledger balances)",
      jobs3 is not None and fail is None,
      str(fail and fail.to_dict()))

jobs4, fail = validate_plan(render("flint-tools", {"surface_at": SURFACE}),
                            index, {}, recipes=RECIPES,
                            campaign=False)
check("same chain rejected outside a campaign (vocabulary)",
      jobs4 is None and fail is not None
      and fail.code == "planner_invalid_json")

# --- validator: ledger arithmetic -------------------------------------------
# no flint given and none in the starting inventory: the knap cannot
# be funded
raw = [{"id": "g1", "type": "give_tool", "material": "knappingsurface",
        "n": 1, "origin": "operator"},
       {"id": "k1", "type": "knap", "at": SURFACE, "material": "flint",
        "recipes": ["knifeblade-flint", "axehead-flint"],
        "origin": "deterministic"}]
jobs5, fail = validate_plan(raw, index, {}, campaign=True)
check("knap without the chipping material fails (resource_not_found)",
      jobs5 is None and fail is not None
      and fail.code == "resource_not_found",
      str(fail and fail.to_dict()))
jobs6, fail = validate_plan(raw, index, {"flint": 1}, campaign=True)
check("one flint for two recipes fails (one per recipe)",
      jobs6 is None and fail is not None
      and fail.code == "resource_not_found",
      str(fail and fail.to_dict()))
jobs7, fail = validate_plan(raw, index, {"flint": 2}, campaign=True)
check("two flint for two recipes passes the knap ledger",
      jobs7 is not None and fail is None,
      str(fail and fail.to_dict()))

# the craft leg: the heads the knap produced feed both tools
raw8 = [{"id": "g1", "type": "give_tool", "material": "flint",
         "n": 2, "origin": "operator"},
        {"id": "g2", "type": "give_tool", "material": "knappingsurface",
         "n": 1, "origin": "operator"},
        {"id": "g3", "type": "give_tool", "material": "stick",
         "n": 2, "origin": "operator"},
        {"id": "k1", "type": "knap", "at": SURFACE, "material": "flint",
         "recipes": ["knifeblade-flint", "axehead-flint"],
         "origin": "deterministic"},
        {"id": "c1", "type": "craft", "material": "knife-generic-flint",
         "source": "recipes/grid/tool/knife.json",
         "origin": "deterministic"},
        {"id": "c2", "type": "craft", "material": "axe-flint",
         "source": "recipes/grid/tool/axe.json",
         "origin": "deterministic"}]
jobs9, fail = validate_plan(raw8, index, {}, recipes=RECIPES,
                            campaign=True)
check("knap-produced heads feed the knife and axe crafts (ledger)",
      jobs9 is not None and fail is None,
      str(fail and fail.to_dict()))
jobs10, fail = validate_plan(raw8, index, {}, recipes=None,
                             campaign=True)
check("the crafts cannot be invented without the recipe table",
      jobs10 is None and fail is not None
      and fail.code == "planner_invalid_reference",
      str(fail and fail.to_dict()))
raw11 = [dict(d) for d in raw8]
raw11[2] = {"id": "g3", "type": "give_tool", "material": "stick",
            "n": 1, "origin": "operator"}
jobs12, fail = validate_plan(raw11, index, {}, recipes=RECIPES,
                             campaign=True)
check("one stick for knife+axe fails at the second craft",
      jobs12 is None and fail is not None
      and fail.code == "resource_not_found",
      str(fail and fail.to_dict()))

print()
print("knap-test: %d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
