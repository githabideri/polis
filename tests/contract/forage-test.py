#!/usr/bin/env python3
"""
Lane B (2026-10-07) contract test: the forage job.

Pure: no network, no game world. Verifies the campaign-scoped forage
type against the plancheck gate: the vocabulary boundary (a 27B plan
can never carry one), the live-cell pre-scan (a forage with a known
`at` cell is validated against the cell index like chop), and the
material-ledger budgeting (a forage without a cell budgets its claim
in a campaign).

Run:  python3 tests/contract/forage-test.py
"""
import sys, os, types
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", ".."))

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


index = {"site-A": types.SimpleNamespace()}

def forage_job(at=None, plant="fruitingbush-*", n=2,
               material="fruit-corn"):
    j = {"id": "f1", "type": "forage", "plant": plant, "n": n,
         "material": material, "origin": "deterministic"}
    if at:
        j["at"] = at
    return j


# --- vocabulary boundary --------------------------------------------------
jobs, fail = validate_plan([forage_job()], index, {})
check("forage rejected outside a campaign",
      jobs is None and fail is not None
      and fail.code == "planner_invalid_json")
check("rejection says operator-campaign scoped",
      fail is not None and "operator-campaign scoped" in fail.detail)

# --- live-cell pre-scan (with `at`) ---------------------------------------
bush_cell = (512016, 155, 512012)
at = list(bush_cell)
j = forage_job(at=at)

jobs, fail = validate_plan([j], index, {},
                           cells={bush_cell: "game:fruitingbush-grown-corn"},
                           campaign=True)
check("campaign forage at a live bush passes",
      jobs is not None and fail is None)

jobs, fail = validate_plan([j], index, {},
                           cells={bush_cell: "game:fruitingbush-wild-corn"},
                           campaign=True)
check("glob plant family accepts any bush state",
      jobs is not None and fail is None)

jobs, fail = validate_plan([j], index, {},
                           cells={bush_cell: "game:granite"},
                           campaign=True)
check("forage at a non-bush cell rejected (pre-exec)",
      jobs is None and fail is not None
      and fail.code == "planner_invalid_reference")

jobs, fail = validate_plan([j], index, {},
                           cells={bush_cell: "air"},
                           campaign=True)
check("forage at air rejected",
      jobs is None and fail is not None
      and fail.code == "resource_not_found")

j_exact = forage_job(at=at, plant="fruitingbush-grown-corn")
jobs, fail = validate_plan([j_exact], index, {},
                           cells={bush_cell: "game:fruitingbush-grown-corn"},
                           campaign=True)
check("exact plant code matches the live block", jobs is not None)
jobs, fail = validate_plan([j_exact], index, {},
                           cells={bush_cell: "game:fruitingbush-wild-corn"},
                           campaign=True)
check("exact plant code rejects a wrong bush state",
      jobs is None and fail is not None
      and fail.code == "planner_invalid_reference")

# --- ledger budgeting -----------------------------------------------------
# no live scan: the pre-scan is skipped (the caller has no cell index),
# the campaign branch budgets the claim
jobs, fail = validate_plan([forage_job()], index, {},
                           cells=None, campaign=True)
check("campaign forage without a cell: budgeted, not rejected",
      jobs is not None and fail is None)

# the foraged fruit feeds a later consumer in the same campaign
plan = [
    forage_job(),
    {"id": "f2", "type": "place", "target": "site-A",
     "material": "fruit-corn", "n": 2, "origin": "deterministic"},
]
jobs, fail = validate_plan(plan, index, {}, campaign=True)
check("ledger: forage budgets its fruit for a later place",
      jobs is not None and fail is None
      and [j.id for j in jobs] == ["f1", "f2"])

# short supply: a place without a producer is a resource failure
plan = [{"id": "f2", "type": "place", "target": "site-A",
         "material": "fruit-corn", "n": 2, "origin": "deterministic"}]
jobs, fail = validate_plan(plan, index, {}, campaign=True)
check("ledger: consumer without producer fails (resource_not_found)",
      jobs is None and fail is not None
      and fail.code == "resource_not_found")

# inventory shortfall: the consumer needs more than the forage claims
plan = [
    forage_job(n=1),
    {"id": "f2", "type": "place", "target": "site-A",
     "material": "fruit-corn", "n": 3, "origin": "deterministic"},
]
jobs, fail = validate_plan(plan, index, {}, campaign=True)
check("ledger: consumer out-claiming the producer fails",
      jobs is None and fail is not None
      and fail.code == "resource_not_found")

# a forage carrying an inventory it already has still budgets on top
plan = [
    forage_job(n=2),
    {"id": "f2", "type": "place", "target": "site-A",
     "material": "fruit-corn", "n": 4, "origin": "deterministic"},
]
jobs, fail = validate_plan(plan, index, {"fruit-corn": 2}, campaign=True)
check("ledger: inventory + foraged combine to satisfy the consumer",
      jobs is not None and fail is None)

print()
print("forage-test: %d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
