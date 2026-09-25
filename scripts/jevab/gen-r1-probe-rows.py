#!/usr/bin/env python3
"""gen-r1-probe-rows.py -- R1: out-of-distribution probes for the FT decider.

The 9th-pass fine-tune scored 96/96 on the val world -- but that world
draws from the *trained* channel vocabulary (same task phrasings, same
block ids). R1 asks what the model does when the channel carries
content it has never seen:

  Family oov-id:   trained task phrasing; carrying/items lines contain
                   block ids absent from the training corpus (coal/copper/
                   tin ores, pine/birch logs, potato/oat/barley crops and
                   seeds). Phase machine unchanged -> oracle is by phase.
  Family oov-task: natural mission phrasings ("mine the coal ore, then
                   return to base") + the same OOV ids, so both the task
                   line and the item lines are novel at once.

The state-text template is byte-identical to gen-world-variety-rows.py
(the (model, question, state-text) calibration unit must not drift):
same facts line tokens (marker_present / crop_present), same radii,
same phase machine, same give_tool rule. `proposed` = oracle for all
probe rows (we read p_oracle and the argmax choice; rejection of faulty
proposals was already characterised in the 9th pass).

Usage: gen-r1-probe-rows.py [--n 96] [--seed 20260925] [--out ...]
"""
import argparse
import json
import math
import random

NEAR_T = {"mine": 3.5, "harvest": 2.5}
NEAR_B = 2.5
FIXTURE_LABEL = {"mine": "marker_present", "harvest": "crop_present"}

# OOV item ids: never present in the 09-25 corpora (granite/limestone
# ores, oak, wheat, iron ingot, dirt, carrot, wood-log, chicken feather).
OOV = {
    "ore": ["game:stone-coal", "game:stone-copper", "game:stone-tin",
            "game:stone-silver", "game:stone-iron", "game:stone-gold"],
    "wood": ["game:wood-pine", "game:wood-birch", "game:wood-spruce",
             "game:wood-linden", "game:wood-willow"],
    "crop": ["game:crop-potato", "game:crop-oat", "game:crop-barley",
             "game:crop-rye"],
    "seed": ["game:seeds-potato", "game:seeds-oat", "game:seeds-barley",
             "game:seeds-rye"],
    "misc": ["game:wool-sheep", "game:feathers-dove", "game:flint"],
}

# Natural mission phrasings (R1's live missions use these too).
TASKS = {
    "mine": [
        "mine the coal ore, then return to base",
        "mine the copper ore, then return to base",
        "mine the granite ore, then return to base",
        "mine the tin ore, then return to base",
    ],
    "harvest": [
        "harvest the wheat, then return to base",
        "harvest the potato patch, then return to base",
        "harvest the oats, then return to base",
        "harvest the barley, then return to base",
    ],
}
# Trained phrasings (control for the oov-task family)
TASKS_TRAINED = {
    "mine": "mine the marker block, then return to base",
    "harvest": "harvest the crop, then return to base",
}

PHASE_LAST = {
    "travel": [("no change", "none"), ("no change", "walked")],
    "mine": [("no change", "mining"), ("no change", "mined"),
             ("no change", "done")],
    "harvest": [("no change", "done"), ("no change", "harvesting")],
    # pickup/return: per-mission, matching the trained semantics
    "pickup-mine": [("marker gone, ground item appeared", "mined"),
                    ("ground item appeared", "picked 1x game:stone-copper")],
    "pickup-harvest": [("crop gone, ground item appeared", "harvested crop"),
                       ("ground item appeared", "picked 1x game:crop-potato")],
    "return-mine": [("marker gone", "mined"),
                    ("ground item picked up", "picked 1x game:stone-copper")],
    "return-harvest": [("crop gone", "harvested crop"),
                       ("ground item picked up", "picked 1x game:crop-potato")],
    "done": [("no change", "arrived"), ("no change", "done")],
}


def dist(a, b):
    return math.hypot(a[0] - b[0], a[2] - b[2])


def carry_for(rng, mission):
    # pickaxe-dominant for mine (mirrors the trained 3/5 mix), OOV ids as
    # the *other* carried items; harvest carries OOV crops/seeds/misc
    if mission == "mine":
        return rng.choice([
            ["game:pickaxe-iron", "game:linensack", rng.choice(OOV["ore"])],
            ["game:pickaxe-iron", rng.choice(OOV["misc"])],
            ["game:pickaxe-iron"],
            ["game:linensack", rng.choice(OOV["ore"])],
            [rng.choice(OOV["wood"]), rng.choice(OOV["ore"])],
        ])
    return rng.choice([
        [rng.choice(OOV["seed"])],
        [rng.choice(OOV["crop"])],
        [rng.choice(OOV["crop"]), rng.choice(OOV["seed"])],
        [rng.choice(OOV["misc"])],
    ])


def items_for(rng, phase, mission):
    pool = OOV["ore"] if mission == "mine" else OOV["crop"]
    if phase == "pickup":
        return [rng.choice(pool)]
    if phase in ("return", "done"):
        return rng.choice([[], [], [rng.choice(pool + OOV["misc"])]])
    return rng.choice([[], [], [rng.choice(pool)],
                       [rng.choice(pool), rng.choice(OOV["misc"])]])


def make_row(rng, mission, phase, oov_task):
    base = (512005, 3, 512022)
    target = (base[0] + 14, 3 + (1 if mission == "harvest" else 0), base[2])
    d = rng.uniform(2, 30)
    ang = rng.uniform(0, 2 * math.pi)
    bot = (int(target[0] + d * math.cos(ang)), 3,
           int(target[2] + d * math.sin(ang)))
    near_t = dist(bot, target) <= NEAR_T[mission]
    near_b = dist(bot, base) <= NEAR_B
    fixture = {"travel": True, "mine": True, "harvest": True,
               "pickup": False, "return": False, "done": False}[phase]

    carrying = carry_for(rng, mission)
    if phase == "mine" and not any("pickaxe" in (c or "") for c in carrying):
        oracle = "give_tool"
    else:
        oracle = {"travel": "goto_target", "mine": "mine_target",
                  "harvest": "harvest_target", "pickup": "pickup_item",
                  "return": "goto_base", "done": "wait"}[phase]

    options = (["goto_target", "mine_target", "pickup_item", "place_block",
                "give_tool", "goto_base", "wait"] if mission == "mine"
               else ["goto_target", "harvest_target", "pickup_item",
                     "place_block", "give_tool", "goto_base", "wait"])

    if oov_task:
        task = rng.choice(TASKS[mission])
    else:
        task = TASKS_TRAINED[mission]

    since, last = rng.choice(PHASE_LAST[(phase + "-" + mission)
                                        if phase in ("pickup", "return")
                                        else phase])
    state = (
        "task: %s\n"
        "current phase: %s\n"
        "facts: bot at (%d, %d, %d), near_target=%s, near_base=%s, %s=%s\n"
        "carrying: %s\nitems: %s\n"
        "since_last_step: %s\nlast_action: %s\nproposed action: %s"
    ) % (
        task, phase, bot[0], bot[1], bot[2],
        "yes" if near_t else "no", "yes" if near_b else "no",
        FIXTURE_LABEL[mission], "yes" if fixture else "no",
        ", ".join(carrying) or "empty",
        ", ".join(items_for(rng, phase, mission)) or "none",
        since, last, oracle,
    )
    return {
        "id": None, "source": "r1-probe-2026-09-25", "mission": mission,
        "family": ("oov-task" if oov_task else "oov-id"),
        "state": state, "options": options, "oracle": oracle,
        "proposed": oracle,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=96,
                    help="total probe rows (split evenly over 4 families)")
    ap.add_argument("--seed", type=int, default=20260925)
    ap.add_argument("--out", default="data/r1-probe-rows-2026-09-25.json")
    a = ap.parse_args()
    rng = random.Random(a.seed)

    fams = [("mine", False), ("harvest", False),
            ("mine", True), ("harvest", True)]
    per = a.n // len(fams)
    rows, seen = [], set()
    i = 0
    while len(rows) < a.n:
        mission, oov_task = fams[i % len(fams)]
        phase = rng.choice(["travel", "mine" if mission == "mine"
                            else "harvest", "pickup", "return", "done"])
        r = make_row(rng, mission, phase, oov_task)
        key = (r["state"], r["oracle"])
        if key not in seen:
            seen.add(key)
            r["id"] = "r1-%03d" % len(rows)
            rows.append(r)
        i += 1
        if i > a.n * 20:
            break
    json.dump(rows, open(a.out, "w"), indent=1)
    from collections import Counter
    print("%d rows -> %s" % (len(rows), a.out))
    print("by family:", dict(Counter(r["family"] for r in rows)))
    print("by mission:", dict(Counter(r["mission"] for r in rows)))
    print("oracle:", dict(Counter(r["oracle"] for r in rows)))


if __name__ == "__main__":
    main()
