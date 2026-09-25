#!/usr/bin/env python3
"""gen-world-variety-rows.py -- grow the labeled corpus with world variety.

The existing corpus (ft-rows-2026-09-25.json) is concentrated in one
regime: dist-8 fixtures, fixed carrying (linensack [+pickaxe]), empty
items line. The Decider's residual error is a travel-phase bias (mine
family 24/30), i.e. exactly the under-represented regime. This generator
varies what the state text can express WITHOUT changing its format
(the (model, question, state-text) calibration unit stays intact):

  - distance: 3..30 blocks (near_target/near_base derived from the real
    v5 radii: 3.5 mine, 2.5 harvest / 2.5 base) in both axes
  - carrying: per-mission sets (mine: pickaxe +/- linensack +/-
    distractors; harvest: linensack / empty / +distractor)
  - items line: none / 1 / 2 distractor ground items / mission items
    (pickup phase)
  - since_last_step / last_action: phase-consistent variants

Phase -> oracle mapping is the v5 phase machine; proposal = oracle for
~85% of rows, with a small, controlled fault mix (goto_base skip-goal,
give_tool-while-carrying) matching the observed live fault types.

Usage: gen-world-variety-rows.py [--n 240] [--seed 20260925] [--out ...]
"""
import argparse
import json
import math
import random

TASKS = {
    "mine": "mine the marker block, then return to base",
    "harvest": "harvest the crop, then return to base",
}
NEAR_T = {"mine": 3.5, "harvest": 2.5}
NEAR_B = 2.5
FIXTURE_LABEL = {"mine": "marker_present", "harvest": "crop_present"}

CARRY_MINE = [
    ["game:pickaxe-iron", "game:linensack"],
    ["game:pickaxe-iron"],
    ["game:linensack"],
    [],
    ["game:pickaxe-iron", "game:linensack", "game:dirt"],
]
CARRY_HARVEST = [
    ["game:linensack"],
    [],
    ["game:linensack", "game:dirt"],
    ["game:linensack", "game:stone-granite"],
]
DISTRACTORS = ["game:dirt", "game:stone-granite", "game:seeds-carrot",
               "game:wood-log", "game:feathers-chicken"]
PHASE_LAST = {
    "travel": [("no change", "none"), ("no change", "done"),
               ("no change", "walked")],
    "mine": [("no change", "mining"), ("no change", "mined"),
             ("no change", "done")],
    "harvest": [("no change", "done"), ("no change", "harvesting")],
    "pickup": [("crop gone, ground item appeared", "harvested crop"),
               ("marker gone, ground item appeared", "mined"),
               ("ground item appeared", "picked 1x game:seeds-carrot")],
    "return": [("marker gone", "mined"), ("crop gone", "harvested crop"),
               ("ground item picked up", "picked 1x game:stone-granite"),
               ("harvested item now carried", "harvested crop")],
    "done": [("no change", "arrived"), ("no change", "done")],
}


def dist(a, b):
    return math.hypot(a[0] - b[0], a[2] - b[2])


def make_row(rng, mission, phase, d=None):
    # fixture 14 blocks east of the base (a middle-of-the-road distance);
    # the bot sits at a random offset that realises the requested nearness
    base = (512005, 3, 512022)
    target = (base[0] + 14, 3 + (1 if mission == "harvest" else 0), base[2])
    if d is None:
        d = rng.uniform(2, 30)
    ang = rng.uniform(0, 2 * math.pi)
    bot = (int(target[0] + d * math.cos(ang)), 3,
           int(target[2] + d * math.sin(ang)))
    near_t = dist(bot, target) <= NEAR_T[mission]
    near_b = dist(bot, base) <= NEAR_B
    fixture = {"travel": True, "mine": True, "harvest": True,
               "pickup": False, "return": False, "done": False}[phase]

    carrying = rng.choice(CARRY_MINE if mission == "mine" else CARRY_HARVEST)
    # phase consistency for the items line
    if phase == "pickup":
        items = rng.choice([["game:crop-carrot"], ["game:seeds-carrot"],
                            ["game:crop-carrot", "game:seeds-carrot"],
                            ["game:stone-granite"]])
        if mission == "harvest":
            carrying = [c for c in carrying if "carrot" not in c]
    elif phase in ("return", "done"):
        items = rng.choice([[], [], [rng.choice(DISTRACTORS)]])
    else:
        items = rng.choice([[], [], [rng.choice(DISTRACTORS)],
                            [rng.choice(DISTRACTORS), rng.choice(DISTRACTORS)]])

    since, last = rng.choice(PHASE_LAST[phase])
    if phase == "mine" and not any("pickaxe" in (c or "") for c in carrying):
        oracle = "give_tool"
    elif phase == "pickup":
        oracle = "pickup_item"
    else:
        oracle = {"travel": "goto_target", "mine": "mine_target",
                  "harvest": "harvest_target", "return": "goto_base",
                  "done": "wait"}[phase]

    options = (["goto_target", "mine_target", "pickup_item", "place_block",
                "give_tool", "goto_base", "wait"] if mission == "mine"
               else ["goto_target", "harvest_target", "pickup_item",
                     "place_block", "give_tool", "goto_base", "wait"])
    proposed = oracle if rng.random() < 0.85 else None
    if proposed is None:
        faulty = ["goto_base"]
        if any("pickaxe" in (c or "") for c in carrying) and phase in ("travel", "mine"):
            faulty.append("give_tool")
        proposed = rng.choice(faulty)

    state = (
        "task: %s\n"
        "current phase: %s\n"
        "facts: bot at (%d, %d, %d), near_target=%s, near_base=%s, %s=%s\n"
        "carrying: %s\nitems: %s\n"
        "since_last_step: %s\nlast_action: %s\nproposed action: %s"
    ) % (
        TASKS[mission], phase, bot[0], bot[1], bot[2],
        "yes" if near_t else "no", "yes" if near_b else "no",
        FIXTURE_LABEL[mission], "yes" if fixture else "no",
        ", ".join(carrying) or "empty",
        ", ".join(items) or "none",
        since, last, proposed,
    )
    return {
        "id": None, "source": "world-variety-2026-09-25", "mission": mission,
        "family": phase, "state": state, "options": options,
        "oracle": oracle, "proposed": proposed,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=240)
    ap.add_argument("--seed", type=int, default=20260925)
    ap.add_argument("--out", default="data/world-variety-rows-2026-09-25.json")
    a = ap.parse_args()
    rng = random.Random(a.seed)

    # phase mix: travel gets the largest share (the under-represented
    # regime), then mine/harvest, then the rest
    plan = []
    for frac, ph in ((0.35, "travel"), (0.25, "mine"), (0.12, "harvest"),
                     (0.10, "pickup"), (0.12, "return"), (0.06, "done")):
        plan += [ph] * max(1, int(a.n * frac / 2))  # x2 missions
    rng.shuffle(plan)
    rows = []
    i = 0
    while len(rows) < a.n and i < len(plan) * 3:
        ph = plan[i % len(plan)]
        if ph in ("mine", "harvest", "pickup"):
            mission = ph if ph != "mine" else "mine"  # harvest rows only from harvest/pickup
            if ph == "pickup":
                mission = "harvest" if rng.random() < 0.6 else "mine"
        else:
            # travel/return/done: 60/40 mine/harvest split
            mission = "harvest" if rng.random() < 0.4 else "mine"
        rows.append(make_row(rng, mission, ph))
        i += 1

    seen, out = set(), []
    for r in rows:
        key = (r["state"], r["oracle"], r["proposed"])
        if key in seen:
            continue
        seen.add(key)
        r["id"] = "wv-%03d" % len(out)
        out.append(r)
    json.dump(out, open(a.out, "w"), indent=1)
    from collections import Counter
    print("%d rows -> %s" % (len(out), a.out))
    print("by family:", dict(Counter(r["family"] for r in out)))
    print("by mission:", dict(Counter(r["mission"] for r in out)))
    print("oracle:", dict(Counter(r["oracle"] for r in out)))
    print("faulty (proposed!=oracle):",
          sum(1 for r in out if r["proposed"] != r["oracle"]))


if __name__ == "__main__":
    main()
