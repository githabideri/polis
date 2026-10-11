#!/usr/bin/env python3
"""Reflex tests for r2/makechains.py (the make <tool> chain data).

Pure data integrity: every chain renders, scales, and stays inside
the vocabulary the mission compiler and the source map understand.
The CODES were verified against the live 1.22.7 recipe book
(2026-10-11 pull, ~13k recipes) when the module was written; this
suite guards against drift, not against the game.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from r2.makechains import CHAINS, KNAPOUS_STONE, MATERIAL_ITEM, steps_for

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


# 1. every chain is a non-empty ordered list of (kind, what, qty)
for tool, steps in CHAINS.items():
    check("chain %s is a step list" % tool,
          isinstance(steps, list) and len(steps) >= 2
          and all(len(s) == 3 and isinstance(s[2], int) and s[2] > 0
                  for s in steps),
          repr(steps))

# 2. a knap chain must gather its knappable stone before the knap,
#    and the craft output must follow the head it assembles
for tool, steps in CHAINS.items():
    kinds = [s[0] for s in steps]
    if "knap" in kinds:
        head = [s[1] for s in steps if s[0] == "knap"][0]
        stone = KNAPOUS_STONE.get(head)
        check("chain %s knaps %s from a declared stone" % (tool, head),
              stone is not None and ("gather", stone, 2) in steps,
              "stone=%r steps=%r" % (stone, steps))
        check("chain %s crafts after knapping" % tool,
              kinds.index("knap") < kinds.index("craft"))
    if "craft" in kinds:
        out = [s[1] for s in steps if s[0] == "craft"][0]
        check("chain %s craft output is an item code" % tool,
              isinstance(out, str) and out and ":" not in out,
              out)

# 3. every gather material in a chain is a known material word
for tool, steps in CHAINS.items():
    for kind, what, _ in steps:
        if kind == "gather":
            check("chain %s gathers known material %r" % (tool, what),
                  what in MATERIAL_ITEM, "unknown material")

# 4. steps_for scales gathers with n, keeps knap/craft at n
check("steps_for knife x1",
      steps_for("knife", 1) ==
      [("gather", "flint", 2), ("knap", "knifeblade-flint", 1),
       ("gather", "stick", 1), ("craft", "knife-generic-flint", 1)])
check("steps_for knife x3 scales the gather",
      steps_for("knife", 3) ==
      [("gather", "flint", 6), ("knap", "knifeblade-flint", 3),
       ("gather", "stick", 3), ("craft", "knife-generic-flint", 3)])
check("steps_for torch x2",
      steps_for("torch", 2) ==
      [("gather", "drygrass", 4), ("gather", "stick", 2),
       ("craft", "torch-basic-extinct-up", 2)])

# 5. unknown tool raises (the compiler names the gap honestly)
try:
    steps_for("pickaxe")
    check("unknown tool raises", False, "no KeyError")
except KeyError:
    check("unknown tool raises", True)

# 6. the copper-tier tools are deliberately NOT in the early chains
#    (pickaxe/hammer/saw are metal-only in 1.22 - the M9 crucible
#    line is a later module phase)
for tool in ("pickaxe", "hammer", "saw"):
    check("%s absent from early chains" % tool, tool not in CHAINS)

print()
print("%d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
