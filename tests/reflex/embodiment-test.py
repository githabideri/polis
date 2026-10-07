#!/usr/bin/env python3
"""Embodiment tests (09-29): the bot's body vs the solid world.
The incident geometry (block-in-bot-cell) is a fixture: raw position
is innocent, the RELATION is the failure."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.join(HERE, "..", "..")
sys.path.insert(0, REPO)

from r2.embodiment import body_cells, embodiment, is_solid

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


# 1. the vocabulary
check("granite is solid", is_solid("game:rock-granite"))
check("stone is solid", is_solid("rock-stone"))
check("unlisted rock-* is solid (defensive)", is_solid("rock-mystery"))
check("soil IS solid (1.22 full cube, 10-05 amendment; a standing body's feet never share it)",
      is_solid("soil-medium-normal") and is_solid("soil-low-none"))
check("air / no-block is not solid", not is_solid("air")
      and not is_solid(None) and not is_solid(""))
check("crop is not solid (walk-through)",
      not is_solid("game:crop-rye-2"))

# 2. body cells (the straddle utility): centred = feet + head only
c = body_cells([5.5, 3, 7.5])
check("centred body = feet + head",
      c == {(5, 3, 7), (5, 4, 7)}, str(c))
# the incident straddle: x fraction 0.75 crosses the +x boundary
c = body_cells([5.75, 3, 7.25])
check("straddle widens the body (+x side, both levels)",
      (6, 3, 7) in c and (6, 4, 7) in c and (4, 3, 7) not in c,
      str(c))
# a fraction of 0.5 is mid-cell: no widening
c = body_cells([5.5, 3, 7.5])
check("mid-cell fraction does not widen",
      c == {(5, 3, 7), (5, 4, 7)}, str(c))

# 3. the incident itself (2026-09-29): the bot's feet at the BOTTOM
#    of a granite block; every raw field looked almost innocent
incident = {(512005, 3, 512034): "game:rock-granite",
            (512006, 3, 512034): "game:rock-granite",
            (512005, 3, 512035): "game:rock-granite"}
state, detail = embodiment([512005.25, 3, 512034.50], incident)
check("incident classifies EMBEDDED", state == "EMBEDDED",
      state + " " + detail)
check("incident names the feet cell and the block",
      "(512005, 3, 512034)" in detail and "granite" in detail,
      detail)

# 4. the same position, cell open: OK with open neighbours
okmap = {(512006, 3, 512034): "game:rock-granite"}
state, _ = embodiment([512005.25, 3, 512034.50], okmap)
check("clear cell with an open neighbour is OK", state == "OK", state)

# 5. TRAPPED: body clear, all four horizontal neighbours solid
wall = {(512006, 3, 512034): "rock-granite",
        (512004, 3, 512034): "rock-granite",
        (512005, 3, 512035): "rock-granite",
        (512005, 3, 512033): "rock-granite"}
state, detail = embodiment([512005.5, 3, 512034.5], wall)
check("four solid neighbours = TRAPPED", state == "TRAPPED",
      state + " " + detail)

# 6. one open neighbour breaks the trap
wall2 = dict(wall)
del wall2[(512004, 3, 512034)]
state, _ = embodiment([512005.5, 3, 512034.5], wall2)
check("one open neighbour = OK", state == "OK", state)

# 7. head-only blockage is still EMBEDDED (the body is not clear)
head = {(512005, 4, 512034): "rock-granite"}
state, detail = embodiment([512005.5, 3, 512034.5], head)
check("solid head cell = EMBEDDED (detail says 'body')",
      state == "EMBEDDED" and "body cell" in detail,
      state + " " + detail)

# 8. the pre-incident state of the run (the bot at the footprint
#    corner before the floor closed): open cell, open outside
pre = {(512006, 3, 512034): "rock-granite",
       (512005, 3, 512035): "rock-granite"}
state, _ = embodiment([512005.75, 3, 512034.25], pre)
check("pre-incident (open corner, two solid neighbours) is OK",
      state == "OK", state)

print()
print("embodiment-test: %d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
