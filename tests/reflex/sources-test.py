#!/usr/bin/env python3
"""
Reflex for the source map (r2/sources.py, 2026-10-11): the
search->extract gather chain's knowledge base - material word
bridged to the block family that yields it and how it is extracted.

Pure: no network, no game. Run:
  python3 tests/reflex/sources-test.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", ".."))

from r2.sources import (Source, SOURCES, MATERIALS, lookup, fam_match,
                        scan_report, compile_gather_plan)

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
    """World-model record stub (the fields compile_gather_plan reads)."""
    def __init__(self, id, code, qty, centroid=(0, 0, 0)):
        self.id, self.code, self.observed_quantity = id, code, qty
        self.centroid = centroid


class Goal:
    """Goal stub (n only is what the compiler reads)."""
    def __init__(self, n):
        self.n = n


# --- the table ------------------------------------------------------------
check("the map holds the 11 source-mapped materials, in order",
      MATERIALS == ("flint", "stick", "wood", "cattail", "drygrass",
                    "cranberry", "dirt", "granite", "stone", "clay",
                    "sand"),
      str(MATERIALS))
check("every source names at least one block family and one drop",
      all(s.families and s.drops for s in SOURCES.values()))
check("cattail carries the knife gate",
      SOURCES["cattail"].tool == "knife-generic-flint")
check("drygrass is the cuttable tallgrass (knife tool, all hand-era)",
      SOURCES["drygrass"].families == ("tallgrass-",)
      and SOURCES["drygrass"].drops == ("drygrass",)
      and SOURCES["drygrass"].kind == "mine"
      and SOURCES["drygrass"].tool == "knife-generic-flint"
      and SOURCES["drygrass"].hand_families == ("tallgrass-",))
check("lookup('grass') resolves to the drygrass source",
      lookup("grass") is SOURCES["drygrass"])
check("lookup of a tallgrass variant code resolves to drygrass",
      lookup("tallgrass-medium-free") is SOURCES["drygrass"]) 
check("sticks are an ITEM: leaf block families + a loose ground code",
      SOURCES["stick"].families == ("leavesbranchy-",)
      and "stick" in SOURCES["stick"].loose)
check("wood covers grown AND placed logs (the log-grown->log-placed "
      "drop mapping)",
      "log-grown-" in SOURCES["wood"].families
      and "log-placed-" in SOURCES["wood"].families)
check("granite covers intact + cracked rock (the broken block is not "
      "a new resource)",
      "rock-granite" in SOURCES["granite"].families
      and "crackedrock-granite" in SOURCES["granite"].families)

# --- lookup ----------------------------------------------------------------
for m in MATERIALS:
    check("lookup(%r) -> %s" % (m, m), lookup(m) is SOURCES[m])
check("lookup alias: coopersreed -> cattail",
      lookup("coopersreed") is SOURCES["cattail"])
check("lookup alias: cattailtops (the drop) -> cattail",
      lookup("cattailtops") is SOURCES["cattail"])
check("lookup alias: berries -> cranberry",
      lookup("berries") is SOURCES["cranberry"])
check("lookup alias: soil -> dirt", lookup("soil") is SOURCES["dirt"])
check("lookup block code: ore-flint-andesite -> flint (the 2026-10-11 "
      "failure mode: the ledger named the vein, the goal the material)",
      lookup("ore-flint-andesite") is SOURCES["flint"])
check("lookup block code: looseflints-granite -> flint (the early-game "
      "source: ground blocks, breakable before any pickaxe)",
      lookup("looseflints-granite") is SOURCES["flint"])
check("lookup namespaced block: game:tallplant-coopersreed-land-normal-free "
      "-> cattail",
      lookup("game:tallplant-coopersreed-land-normal-free")
      is SOURCES["cattail"])
check("lookup leaf block: leavesbranchy-grown1-birch -> stick",
      lookup("leavesbranchy-grown1-birch") is SOURCES["stick"])
check("lookup drop code: fruit-cranberry -> cranberry",
      lookup("fruit-cranberry") is SOURCES["cranberry"])
check("lookup drop code: stone-granite -> granite",
      lookup("stone-granite") is SOURCES["granite"])
check("lookup snow-covered block: rock-granite-free -> granite",
      lookup("rock-granite-free") is SOURCES["granite"])
check("lookup: a vein's CLASSIFIED material (flint-andesite) is NOT a "
      "word - the family is",
      lookup("flint-andesite") is None)
check("lookup: unknown material stays unknown (no guessing)",
      lookup("brick") is None and lookup("") is None)

# --- fam_match --------------------------------------------------------------
check("prefix family: ore-flint-andesite vs ore-flint-",
      fam_match("ore-flint-andesite", "ore-flint-") is True)
check("prefix family: the snow-covered reed vs tallplant-coopersreed-",
      fam_match("tallplant-coopersreed-land-normal-free",
                "tallplant-coopersreed-") is True)
check("exact family: rock-granite vs rock-granite",
      fam_match("rock-granite", "rock-granite") is True)
check("snow twin: rock-granite-free matches bare rock-granite",
      fam_match("rock-granite-free", "rock-granite") is True)
check("no cross-match: crackedrock-granite vs rock-granite",
      fam_match("crackedrock-granite", "rock-granite") is False)
check("no cross-match: ore-flint vs ore-flint- (the bare code is not "
      "the family)",
      fam_match("ore-flint", "ore-flint-") is False)
check("namespacing is normalized on the code side",
      fam_match("game:sand-clay-0", "sand-") is True)

# --- matches_drop (the 12.9 loosening) --------------------------------------
check("cattail source accepts its two documented drops",
      SOURCES["cattail"].matches_drop("cattailtops")
      and SOURCES["cattail"].matches_drop("cattailroot"))
check("granite source accepts the granite stone (and rejects flint)",
      SOURCES["granite"].matches_drop("stone-granite")
      and not SOURCES["granite"].matches_drop("ore-flint-andesite"))
check("stick source accepts the item itself",
      SOURCES["stick"].matches_drop("stick")
      and not SOURCES["stick"].matches_drop("log-placed-birch"))
check("namespaced drops are normalized",
      SOURCES["cattail"].matches_drop("game:cattailtops"))

# --- scan_report (the honest failure) ---------------------------------------
r = scan_report({"grass-plain": 30, "soil-dirt": 20,
                 "leavesbranchy-grown1-birch": 5, "rock-granite": 3},
                "flint")
check("scan_report says the honest count",
      "58 blocks" in r, r)
check("scan_report speaks the operator's language (pretty names)",
      "grass" in r and "soil" in r and "birch" in r and "granite" in r
      and "ore-" not in r, r)
check("scan_report names the missing material",
      r.endswith("no flint"), r)
check("scan_report: an empty census still reads",
      "no cattail" in scan_report({}, "cattail"))

# --- compile_gather_plan ----------------------------------------------------
# 1. ledger empty (the 2026-10-11 stick case): search->extract
flint = SOURCES["flint"]
jobs, note = compile_gather_plan([], Goal(10), flint, bot_pos=(0, 0))
check("empty ledger: a search job leads the plan",
      len(jobs) == 2 and jobs[0]["type"] == "search"
      and jobs[0]["material"] == "flint"
      and jobs[0]["expect"] == "ore-flint-,looseflints-"
      and jobs[0]["quantity"] == 10, str(jobs))
check("empty ledger: the extract depends on the search and carries the "
      "family globs (no source id - it resolves at run time)",
      jobs[1]["type"] == "gather"
      and jobs[1]["depends_on"] == ["j1"]
      and jobs[1]["expect"] == "ore-flint-,looseflints-"
      and "source" not in jobs[1], str(jobs))
check("empty ledger: the note is honest",
      "search->extract" in note, note)

# 2. ledger covers the quantity: direct extract, one job per cluster
cattail = SOURCES["cattail"]
jobs, note = compile_gather_plan(
    [Rec("res-01", "tallplant-coopersreed-land-normal", 30, (1, 5, 2)),
     Rec("res-02", "tallplant-coopersreed-land-normal", 20, (30, 5, 40))],
    Goal(25), cattail, bot_pos=(0, 0))
check("sufficient ledger: direct extract, no search job",
      all(j["type"] == "gather" for j in jobs)
      and all("source" in j for j in jobs), str(jobs))
check("sufficient ledger: nearest-first allocation",
      jobs[0]["source"] == "res-01"
      and jobs[0]["quantity"] == 25, str(jobs))
check("sufficient ledger: the knife gate is carried into the job",
      all(j.get("tool") == "knife-generic-flint" for j in jobs),
      str(jobs))

# 3. two-cluster split with the allocation cap (2026-10-07/10-10
#    mine-prep pattern: the cap grows as the cluster count shrinks)
granite = SOURCES["granite"]
jobs, note = compile_gather_plan(
    [Rec("res-01", "rock-granite", 60, (0, 0, 3)),
     Rec("res-02", "rock-granite", 40, (20, 0, 20))],
    Goal(50), granite, bot_pos=(0, 0))
check("two clusters: nearest first, cap 40, the rest from the second",
      [j["quantity"] for j in jobs] == [40, 10]
      and jobs[0]["source"] == "res-01"
      and jobs[1]["source"] == "res-02", str(jobs))

# 4. single cluster holding everything: the cap must not undercut
#    the need (a 60-quantity need from one 100-quantity cluster is
#    one job, not a capped 40)
jobs, note = compile_gather_plan(
    [Rec("res-01", "rock-granite", 100, (0, 0, 3))],
    Goal(60), granite, bot_pos=(0, 0))
check("single big cluster: one job for the full need",
      len(jobs) == 1 and jobs[0]["quantity"] == 60, str(jobs))

# 5. partial ledger (less than the need): search->extract again
jobs, note = compile_gather_plan(
    [Rec("res-01", "rock-granite", 3, (0, 0, 3))],
    Goal(10), granite, bot_pos=(0, 0))
check("partial ledger: search leads, the note counts the shortfall",
      jobs[0]["type"] == "search"
      and "search->extract" in note and "3 of 10" in note, note)

# 6. forage source: the extract job carries the forage glob (the
#    engine's pick arm, not the break command)
cranberry = SOURCES["cranberry"]
jobs, note = compile_gather_plan([], Goal(5), cranberry, bot_pos=(0, 0))
check("forage source: the extract job names the forage family glob",
      jobs[1].get("plant") == "fruitingbush-*", str(jobs))

# 7. zero-quantity clusters do not take allocations
jobs, note = compile_gather_plan(
    [Rec("res-01", "rock-granite", 0, (0, 0, 3)),
     Rec("res-02", "rock-granite", 12, (5, 0, 5))],
    Goal(10), granite, bot_pos=(0, 0))
check("observed-zero clusters are skipped, the rest allocated",
      [j["source"] for j in jobs] == ["res-02"]
      and jobs[0]["quantity"] == 10, str(jobs))

# 8. fam_match_resource (2026-10-11): the world model stores the
#    CLASSIFIED material; families match raw block codes. The matcher
#    must bridge both: kind-prefixed codes are reconstructed, and
#    unknown-kind codes (full code kept as material) match directly.
from r2.sources import fam_match_resource
from types import SimpleNamespace
ore_rec = SimpleNamespace(id="res-432", kind="ore", material="flint-claystone",
                          code="flint-claystone")
loose_rec = SimpleNamespace(id="res-101", kind="block",
                            material="looseflints-claystone-free",
                            code="looseflints-claystone-free")
rock_rec = SimpleNamespace(id="res-201", kind="rock", material="granite",
                           code="granite")
check("ore resource matches its raw family via reconstruction",
      fam_match_resource(ore_rec, ["ore-flint-"]),
      str(vars(ore_rec)))
check("ore resource does NOT match a foreign family",
      not fam_match_resource(ore_rec, ["ore-chromite-"]))
check("unknown-kind (loose) resource matches directly",
      fam_match_resource(loose_rec, ["looseflints-"]))
check("multiple families: one hit is enough",
      fam_match_resource(ore_rec, ["ore-flint-", "looseflints-"]))
check("string input still works (a plain code string)",
      fam_match_resource("ore-flint-andesite", ["ore-flint-"]))
check("rock resource reconstructs its raw code for the family",
      fam_match_resource(rock_rec, ["rock-granite-"]))

# 9. era-aware allocation (2026-10-11): flint has two eras - loose
#    ground flint (hand) and the ore vein (pickaxe, M9). Pre-pickaxe,
#    the allocator must never allocate to the ore cluster; post-
#    pickaxe it joins behind the hand family.
class RecK(Rec):
    def __init__(self, id, code, qty, kind="block", centroid=(0, 0, 0)):
        super(RecK, self).__init__(id, code, qty, centroid)
        self.kind = kind
flint = SOURCES["flint"]
ore = RecK("res-434", "flint-claystone", 20, kind="ore",
           centroid=(10, 0, 30))
loose = RecK("res-101", "looseflints-claystone-free", 6,
             centroid=(0, 0, 4))
jobs, note = compile_gather_plan([ore, loose], Goal(10), flint,
                                 bot_pos=(0, 0), inv={})
check("pre-pickaxe: the ore cluster is never allocated",
      all(j.get("source") != "res-434" for j in jobs), str(jobs))
jobs, note = compile_gather_plan([ore, loose], Goal(10), flint,
                                 bot_pos=(0, 0),
                                 inv={"game:pickaxe-iron": 1})
check("post-pickaxe: hand family leads, ore joins behind",
      [j["source"] for j in jobs] == ["res-101", "res-434"]
      and jobs[0]["quantity"] == 6 and jobs[1]["quantity"] == 4,
      str(jobs))

print()
print("sources-test: %d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
