#!/usr/bin/env python3
"""
Lane B (2026-10-07) contract test: the crucible-copper mission chain
(r2/chains.py) and its passage through the campaign validator.

Pure: no network, no game world. The chain is data; the test renders
it and validates the render against the same pre-execution checks an
operator campaign gets (vocabulary gate, recipe table, material
ledger). Live-world facts (mold cell, firepit cell, item codes, smelt
duration) are PARAMETERS - the test supplies stubs, the runner
supplies reality.

Run:  python3 tests/contract/crucible-chain-test.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", ".."))

from r2.chains import CHAINS, render
from r2.plancheck import validate_plan
from r2.jobs import JOB_CATALOG

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


# --- registry ---------------------------------------------------------------
check("crucible-copper is registered", "crucible-copper" in CHAINS)
check("all crucible steps are catalog types",
      all(t in JOB_CATALOG for t in
          ("crucible_fire", "crucible_insert", "crucible_fuel",
           "crucible_take", "crucible_pour")))

# --- render: shape ------------------------------------------------------------
jobs = render("crucible-copper",
              {"mold_at": [512020, 150, 512025], "wait_s": 90})
seq = [j["type"] for j in jobs]
check("renders the 7-step shape (no firepit pin)",
      seq == ["craft", "crucible_fire", "crucible_insert",
              "crucible_fuel", "wait", "crucible_take",
              "crucible_pour"], str(seq))
check("unpinned fire leaves fire without a cell",
      "at" not in jobs[1])
check("pour is pinned to the mold cell with the product claim",
      jobs[6]["at"] == [512020, 150, 512025]
      and jobs[6]["expect"] == "copper")
check("wait carries the smelt seconds", jobs[4]["n"] == 90)
check("every step is deterministic-origin",
      all(j["origin"] == "deterministic" for j in jobs))

jobs2 = render("crucible-copper",
               {"mold_at": [1, 2, 3], "firepit_at": [9, 10, 11]})
check("firepit pin adds a goto before the fire (and pins it)",
      [j["type"] for j in jobs2][:3] == ["craft", "goto",
                                         "crucible_fire"]
      and jobs2[1]["at"] == [9, 10, 11] and jobs2[2]["at"] == [9, 10, 11])

jobs3 = render("crucible-copper",
               {"mold_at": [1, 2, 3], "give": [("clay", 9),
                                               ("ore-copper", 3)]})
check("give prepends external setup jobs (operator origin)",
      [j["type"] for j in jobs3][:2] == ["give_tool", "give_tool"]
      and all(j["origin"] == "operator" for j in jobs3[:2]))

# --- render: parameter guards --------------------------------------------------
try:
    render("crucible-copper", {})
    check("missing mold_at raises", False, "no exception")
except ValueError as e:
    check("missing mold_at raises", "mold" in str(e))
try:
    render("crucible-copper", {"mold_at": [1, 2, 3], "color": "green"})
    check("bad color raises", False, "no exception")
except ValueError:
    check("bad color raises", True)
try:
    render("no-such-chain", {})
    check("unknown chain raises KeyError", False, "no exception")
except KeyError:
    check("unknown chain raises KeyError", True)

# --- validator: the rendered chain passes a campaign validation ---------------
# (each check renders fresh: validate_plan returns Job objects, and the
# validator's input is the RAW dict list - the runner's --jobs shape)
index = {}
inventory = {"clay": 9, "ore-copper": 3, "charcoal": 4}
recipes = [{"name": "clayforming/crucible", "output": "crucible-fire-raw",
            "shapeless": True,
            "ingredients": [{"code": "clay", "qty": 3}]}]

PARAMS = {"mold_at": [512020, 150, 512025], "wait_s": 90}

jobs, fail = validate_plan(render("crucible-copper", PARAMS), index,
                           inventory, recipes=recipes, campaign=True)
check("rendered chain validates as a campaign (ledger balances)",
      jobs is not None and fail is None,
      str(fail and fail.to_dict()))

jobs, fail = validate_plan(render("crucible-copper", PARAMS), index,
                           inventory, recipes=recipes, campaign=False)
check("same chain rejected outside a campaign (vocabulary)",
      jobs is None and fail is not None
      and fail.code == "planner_invalid_json")

jobs, fail = validate_plan(render("crucible-copper", PARAMS), index, {},
                           recipes=recipes, campaign=True)
check("no clay in inventory: the craft fails (resource_not_found)",
      jobs is None and fail is not None
      and fail.code == "resource_not_found",
      str(fail and fail.to_dict()))

jobs, fail = validate_plan(render("crucible-copper", PARAMS), index,
                           {"clay": 3, "ore-copper": 3, "charcoal": 4},
                           recipes=None, campaign=True)
check("no recipe table: the craft cannot be invented",
      jobs is None and fail is not None
      and fail.code == "planner_invalid_reference",
      str(fail and fail.to_dict()))

# --- ledger: the melt intermediate ---------------------------------------------
# take produces the symbolic melt, pour consumes it - with nothing else
# in the inventory the smelt's own arithmetic must balance
jobs, fail = validate_plan(
    [{"id": "t1", "type": "crucible_take",
      "material": "copper-melt", "n": 1, "origin": "deterministic"},
     {"id": "p1", "type": "crucible_pour",
      "material": "copper-melt", "at": [1, 2, 3], "expect": "copper",
      "origin": "deterministic"}],
    index, {}, campaign=True)
check("melt produced by take feeds the pour (ledger)",
      jobs is not None and fail is None)
jobs, fail = validate_plan(
    [{"id": "p1", "type": "crucible_pour",
      "material": "copper-melt", "at": [1, 2, 3], "expect": "copper",
      "origin": "deterministic"}],
    index, {}, campaign=True)
check("pour without a preceding take fails (no melt in hand)",
      jobs is None and fail is not None
      and fail.code == "resource_not_found")

# --- wait: the quantity cap does not apply to seconds --------------------------
jobs, fail = validate_plan(
    [{"id": "w1", "type": "wait", "n": 120,
      "origin": "deterministic"}],
    index, {}, campaign=True)
check("wait quantity is seconds, not a material count (cap exempt)",
      jobs is not None and fail is None,
      str(fail and fail.to_dict()))
jobs, fail = validate_plan(
    [{"id": "x1", "type": "harvest", "source": "res-1",
      "material": "wheat", "n": 500, "origin": "deterministic"}],
    index, {}, campaign=True)
check("a non-wait job still hits the quantity cap",
      jobs is None and fail is not None
      and fail.code == "planner_invalid_json")

print()
print("crucible-chain-test: %d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
