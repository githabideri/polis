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
c = candidates(T, [T, (11, 3, 10)], (0, 3, 0))
check("target first", c[0] == T)
check("8 neighbours for radius 1 (minus 1 solid-filtered)",
      len(c) == 1 + 7, "got %d" % len(c))
check("solid neighbour filtered", (11, 3, 10) not in c[1:])
# distance ordering: from (0,3,0), the nearest neighbour is (9,3,9)
# (|9-0|+|9-0| = 18 < |9-0|+|10-0| = 19)
check("distance-ordered", c[1] == (9, 3, 9), "got %r" % (c[1],))
check("no duplicates", len(set(map(tuple, c))) == len(c))
# empty solid set -> full 8
c2 = candidates(T, [], (0, 3, 0))
check("no solids -> 9 candidates", len(c2) == 9)

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

# 2. goto stuck on candidate 1, action succeeds on candidate 2
def t2():
    calls = {"n": 0}
    def goto(cell):
        calls["n"] += 1
        if cell == T:
            return {"ok": False, "msg": "goto stuck"}
        return {"ok": True, "msg": "arrived"}
    def act():
        return {"ok": True, "last_action": {"Name": "mine", "Ok": True,
                                            "Msg": ""}}
    ok, detail, attempts, _ = approach(goto, act, (0, 3, 0), T, [T])
    return ok is True and calls["n"] >= 2 and \
        attempts[0]["stage"] == "goto" and attempts[0]["ok"] is False
check("stuck -> next candidate -> success", t2())

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

# 5. every candidate stuck -> honest failure with the attempt log
def t5():
    def goto(cell):
        return {"ok": False, "msg": "pathfinder stuck"}
    def act():
        raise AssertionError("action must not run without an arrival")
    ok, detail, attempts, _ = approach(goto, act, (0, 3, 0), T, [T,
                                                                (11, 3, 10)])
    return ok is False and len(attempts) == 8 and all(
        a["stage"] == "goto" for a in attempts)
check("all-stuck -> one failed attempt with full log", t5())

# 6. max_candidates caps the walk
def t6():
    calls = {"n": 0}
    def goto(cell):
        calls["n"] += 1
        return {"ok": False, "msg": "stuck"}
    def act():
        raise AssertionError
    approach(goto, act, (0, 3, 0), T, [], max_candidates=3)
    return calls["n"] == 3
check("max_candidates caps the walk", t6())

print()
print("approach-test: %d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
