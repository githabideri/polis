#!/usr/bin/env python3
"""
Approach-resolution tests (13.6 step 1): candidate ordering/filtering
and the retry driver with injected callables - no game, no network.

Run:  python3 tests/reflex/approach-test.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", ".."))

from r2.approach import candidates, approach

PASS, FAIL = 0, 0


def check(name, cond, why=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("ok   %s" % name)
    else:
        FAIL += 1
        print("FAIL %s  %s" % (name, why))


# --- candidates ----------------------------------------------------------
T = (10, 3, 10)
# a ground layer under the same-height ring + one solid neighbour:
# the ring cells stand on the ground (y=2), the cell above the solid
# neighbour is also standable, every other cell has no floor
GROUND = [(x, 2, z) for x in range(9, 12) for z in range(9, 12)]
SOL = [T, (11, 3, 10)] + GROUND
c = candidates(T, SOL, (0, 3, 0))
check("target first", c[0] == T)
check("7 grounded same-height + 2 on-top (target, solid neighbour)",
      len(c) == 1 + 9, "got %d" % len(c))
check("solid neighbour filtered", (11, 3, 10) not in c[1:])
check("cell on top of the solid kept", (11, 4, 10) in c[1:])
check("cell on top of the target kept", (10, 4, 10) in c[1:])
# distance ordering: from (0,3,0), the nearest grounded neighbour is
# (9,3,9) (|9-0|+|3-3|+|9-0| = 18 < |9-0|+|3-3|+|10-0| = 19)
check("distance-ordered", c[1] == (9, 3, 9), "got %r" % (c[1],))
check("no duplicates", len(set(map(tuple, c))) == len(c))
# floating cells (no floor under them) are not standable candidates;
# the one survivor is the cell on top of the target itself
c2 = candidates(T, [T], (0, 3, 0))
check("no ground under the ring -> target + its top cell",
      sorted(c2) == sorted([T, (10, 4, 10)]), "got %r" % (c2,))

# --- the driver ----------------------------------------------------------
def fake_state(pos):
    return {"Bot": {"Pos": list(pos)}}


# 1. first candidate (the target cell itself) arrives and the action ok
def t1():
    def goto(cell):
        return {"ok": True, "msg": "arrived"}
    def act():
        return {"ok": True, "last_action": {"Name": "mine", "Ok": True,
                                            "Msg": "mined"}}
    ok, detail, attempts, la = approach(goto, act, (0, 3, 0), T, [T])
    return ok is True and len(attempts) == 1 and la.get("Ok") is True
check("success on first candidate", t1())

# 2. goto stuck on candidate 1 - the action is tried from the stuck
#    position (out of range), then the next candidate arrives and works
def t2():
    calls = {"g": 0, "a": 0}
    def goto(cell):
        calls["g"] += 1
        if cell == T:
            return {"ok": False, "msg": "goto stuck"}
        return {"ok": True, "msg": "arrived"}
    def act():
        calls["a"] += 1
        if calls["a"] == 1:
            return {"ok": False,
                    "last_action": {"Name": "mine", "Ok": False,
                                    "Msg": "out of range"}}
        return {"ok": True, "last_action": {"Name": "mine", "Ok": True,
                                            "Msg": ""}}
    ok, detail, attempts, _ = approach(goto, act, (0, 3, 0), T, SOL)
    return ok is True and calls["g"] == 2 and calls["a"] == 2 and \
        attempts[0]["stage"] == "goto" and attempts[0]["ok"] is False
check("stuck -> action from stuck point -> next candidate -> success", t2())

# 2b. goto stuck but the action SUCCEEDS from the stopping point
#     (the pathfinder stopped one cell short of the column - already
#     in range; the 2026-10-07 trunk-chop case)
def t2b():
    calls = {"g": 0, "a": 0}
    def goto(cell):
        calls["g"] += 1
        return {"ok": False, "msg": "pathfinder stuck"}
    def act():
        calls["a"] += 1
        return {"ok": True, "last_action": {"Name": "chop", "Ok": True,
                                            "Msg": "chopped"}}
    ok, detail, attempts, _ = approach(goto, act, (0, 3, 0), T, SOL)
    return ok is True and calls["g"] == 1 and calls["a"] == 1 and \
        "stuck position" in detail
check("stuck -> action ok from the stuck position (no further gotos)", t2b())

# 3. action fails with a range/LOS reason -> retry; succeeds elsewhere
def t3():
    n = {"a": 0}
    def goto(cell):
        return {"ok": True, "msg": "arrived"}
    def act():
        n["a"] += 1
        if n["a"] == 1:
            return {"ok": False,
                    "last_action": {"Name": "mine", "Ok": False,
                                    "Msg": "out of range"}}
        return {"ok": True, "last_action": {"Name": "mine", "Ok": True,
                                            "Msg": ""}}
    ok, detail, attempts, _ = approach(goto, act, (0, 3, 0), T, [T])
    return ok is True and n["a"] == 2
check("retriable action failure -> retry", t3())

# 4. definitive action failure (tool tier) -> NO retry, single attempt
def t4():
    n = {"a": 0}
    def goto(cell):
        return {"ok": True, "msg": "arrived"}
    def act():
        n["a"] += 1
        return {"ok": False,
                "last_action": {"Name": "mine", "Ok": False,
                                "Msg": "Tool required: block needs tier 2"}}
    ok, detail, attempts, la = approach(goto, act, (0, 3, 0), T, [T])
    return ok is False and n["a"] == 1 and "definitively" in detail
check("definitive failure stops the retry", t4())

# 5. every candidate stuck -> the action is tried from each stuck
#    point, every verdict is an out-of-range refusal -> honest failure
#    with the full attempt log
def t5():
    calls = {"a": 0}
    def goto(cell):
        return {"ok": False, "msg": "pathfinder stuck"}
    def act():
        calls["a"] += 1
        return {"ok": False,
                "last_action": {"Name": "mine", "Ok": False,
                                "Msg": "out of range"}}
    ok, detail, attempts, _ = approach(goto, act, (0, 3, 0), T, SOL)
    return ok is False and calls["a"] >= 1 and all(
        not a["ok"] for a in attempts)
check("all-stuck -> action tried from each stuck point -> failed log", t5())

# 6. max_candidates caps the walk
def t6():
    calls = {"n": 0}
    def goto(cell):
        calls["n"] += 1
        return {"ok": False, "msg": "stuck"}
    def act():
        return {"ok": False,
                "last_action": {"Name": "mine", "Ok": False,
                                "Msg": "out of range"}}
    approach(goto, act, (0, 3, 0), T, SOL, max_candidates=3)
    return calls["n"] == 3
check("max_candidates caps the walk", t6())

print()
print("approach-test: %d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
