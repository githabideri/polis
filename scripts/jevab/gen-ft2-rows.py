#!/usr/bin/env python3
"""gen-ft2-rows.py -- corpus assembly for the Decider-2B fine-tune round 2
(2026-09-26, 11th pass).

Round 1 (9th pass) taught the model to read the world instead of following
the proposal. Two residual gaps measured since:

1. The BUILD mission (11th pass): a new phase name ("build") and an
   INVERTED fixture (build_site_filled starts "no"). The FT-1 decider
   scored p~1.0 on build/return/give_tool but p~0.0 on build-travel rows
   (the judge covered it). Round 2 trains on the build mission family so
   the reflex owns it end to end.

2. Abstention: the §16/§17 residual risk - outside the learned
   distribution the model guesses confidently instead of going quiet. The
   jev-designer rule: a choice question gets an explicit escape option.
   In this loop the escape is "wait". Round 2 adds states where NONE of
   the 7 actions is right - the mission does not map to any phase
   (out-of-vocabulary goal, idle scene), the loop is stalled (no progress
   for several steps, last action failed), and the facts contradict each
   other - all labeled "wait". These are exactly the states the judge's
   instructions already route to wait, so the reflex and the arbiter agree
   on the contract.

Deliberately NOT in scope: teaching the model to be uncertain about
states that DO have a right answer (that would lower confidence on the
96-row val world and regress the adoption baseline).

Output:
  ft2-train.jsonl  v1 rows (363) + R1a OOV probes (96) + build grid (~80)
                   + abstention train split (48)  -> loftune --rows
  ft2-val.json     val world (96, zero overlap, the drift-guard set)
                   + abstention held-out split (48)  -> loftune --val-rows
"""
import json
import math
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(HERE), "..", "data")
rng = random.Random(20260926)

TASK_BUILD = "place a granite stone at the build site, then return to base"
FIXTURE_BUILD = "build_site_filled"
NEAR_T = 2.5
NEAR_B = 2.5

# the block in hand is the build "tool"
CARRY_BUILD_WITH = [
    ["game:rock-granite", "game:linensack"],
    ["game:rock-granite"],
    ["game:rock-granite", "game:linensack", "game:rock-limestone"],
]
CARRY_BUILD_WITHOUT = [
    ["game:linensack"],
    [],
    ["game:linensack", "game:dirt"],
]
DISTRACTORS = ["game:dirt", "game:stone-granite", "game:seeds-carrot",
               "game:wood-log", "game:feathers-chicken"]

PHASE_LAST_BUILD = {
    "travel": [("no change", "none"), ("no change", "walked"),
               ("no change", "done")],
    "build": [("no change", "placing"), ("no change", "done")],
    "return": [("build site filled", "placed"), ("build site filled", "done")],
    "done": [("no change", "arrived"), ("no change", "done")],
}

OPTIONS_BUILD = ["goto_target", "harvest_target", "pickup_item",
                 "place_block", "give_tool", "goto_base", "wait"]


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2])


def make_build_row(rng, phase, d=None):
    base = (512005, 3, 512022)
    target = (base[0] + 14, 3, base[2])
    if d is None:
        d = rng.uniform(2, 30)
    ang = rng.uniform(0, 2 * math.pi)
    bot = (int(target[0] + d * math.cos(ang)), 3,
           int(target[2] + d * math.sin(ang)))
    near_t = dist(bot, target) <= NEAR_T
    near_b = dist(bot, base) <= NEAR_B
    # INVERTED fixture: the site starts empty and gets filled
    fixture = {"travel": False, "build": False,
               "return": True, "done": True}[phase]

    if phase in ("travel", "build"):
        # block still to place: carried unless this row is the give_tool
        # case (the build "tool" is the block itself)
        has_block = True
        if phase == "build" and rng.random() < 0.2:
            has_block = False
        carrying = (rng.choice(CARRY_BUILD_WITH) if has_block
                    else rng.choice(CARRY_BUILD_WITHOUT))
        items = rng.choice([[], [], [rng.choice(DISTRACTORS)]])
    else:
        # block consumed by the placement
        carrying = [c for c in rng.choice(CARRY_BUILD_WITH + CARRY_BUILD_WITHOUT)
                    if "rock-granite" not in (c or "")]
        items = rng.choice([[], [], [rng.choice(DISTRACTORS)]])

    since, last = rng.choice(PHASE_LAST_BUILD[phase])

    if phase == "travel":
        oracle = "goto_target"
    elif phase == "build":
        oracle = "give_tool" if not has_block else "place_block"
    else:
        oracle = "wait" if near_b else "goto_base"

    proposed = oracle if rng.random() < 0.85 else rng.choice(
        ["goto_base", "wait", "pickup_item"])
    state = (
        "task: %s\n"
        "current phase: %s\n"
        "facts: bot at (%d, %d, %d), near_target=%s, near_base=%s, %s=%s\n"
        "carrying: %s\nitems: %s\n"
        "since_last_step: %s\nlast_action: %s\nproposed action: %s"
    ) % (
        TASK_BUILD, phase, bot[0], bot[1], bot[2],
        "yes" if near_t else "no", "yes" if near_b else "no",
        FIXTURE_BUILD, "yes" if fixture else "no",
        ", ".join(carrying) or "empty",
        ", ".join(items) or "none",
        since, last, proposed,
    )
    return {
        "id": None, "source": "ft2-build-2026-09-26", "mission": "build",
        "family": phase, "state": state, "options": OPTIONS_BUILD,
        "oracle": oracle, "proposed": proposed,
    }


# ---------------------------------------------------------------------------
# Abstention rows: states where none of the 7 actions is right. The oracle
# is "wait" (the loop's escape action) and the proposal is usually a
# plausible-but-wrong action, exactly as the live loop presents them.
# ---------------------------------------------------------------------------

ABSTAIN_TASKS = [
    # (task, fixture_label, fixture_present, near_t, near_b, phase, carry, items, since, last, faulty_proposal)
    ("fix the wooden fence, then return to base", "marker_present", True,
     True, False, "travel",
     ["game:linensack", "game:wood-log"], [],
     "no change", "walked", "goto_target"),
    ("feed the chickens, then return to base", "crop_present", True,
     False, True, "done",
     ["game:linensack"], [],
     "no change", "done", "goto_base"),
    ("paint the wall, then return to base", "marker_present", False,
     False, True, "done",
     ["game:linensack"], [],
     "no change", "done", "wait"),
    ("haul the clay, then return to base", "marker_present", True,
     True, False, "travel",
     ["game:linensack"], [],
     "no change", "walked", "goto_base"),
    # stalled: no progress for three steps, last action failed
    ("mine the marker block, then return to base", "marker_present", True,
     True, False, "travel",
     ["game:pickaxe-iron", "game:linensack"], [],
     "no progress for 3 steps", "goto failed: no path", "goto_target"),
    ("harvest the crop, then return to base", "crop_present", True,
     True, False, "harvest",
     ["game:linensack"], [],
     "no progress for 3 steps", "harvest failed: not mature", "harvest_target"),
    ("mine the marker block, then return to base", "marker_present", True,
     False, False, "travel",
     ["game:pickaxe-iron", "game:linensack"], [],
     "no progress for 4 steps", "goto failed: no path", "goto_target"),
    # contradictions: the facts disagree with the phase
    ("mine the marker block, then return to base", "marker_present", False,
     True, False, "travel",
     ["game:pickaxe-iron", "game:linensack"], [],
     "no change", "none", "mine_target"),
    ("harvest the crop, then return to base", "crop_present", True,
     False, True, "done",
     ["game:linensack", "game:crop-carrot"], [],
     "no change", "arrived", "harvest_target"),
    ("mine the marker block, then return to base", "marker_present", True,
     True, True, "travel",
     ["game:pickaxe-iron", "game:linensack"], [],
     "no change", "done", "goto_target"),
    ("harvest the crop, then return to base", "crop_present", False,
     True, True, "return",
     ["game:linensack"], ["game:crop-carrot"],
     "crop gone, ground item appeared", "harvested crop", "goto_base"),
    # idle scene with no mappable goal
    ("organize the backpack, then return to base", "marker_present", False,
     False, True, "done",
     ["game:linensack", "game:dirt", "game:stone-granite"], [],
     "no change", "done", "goto_base"),
    ("check the mine cart, then return to base", "marker_present", False,
     False, True, "done",
     ["game:pickaxe-iron", "game:linensack"], [],
     "no change", "done", "goto_base"),
]


def make_abstain_row(rng, spec):
    (task, fixture_label, fixture, near_t, near_b, phase,
     carry, items, since, last, faulty) = spec
    base = (512005, 3, 512022)
    target = (base[0] + 14, 3, base[2])
    bot = (base[0] + rng.randint(-1, 3), 3, base[2] + rng.randint(-1, 3))
    options = (["goto_target", "mine_target", "pickup_item", "place_block",
                "give_tool", "goto_base", "wait"]
               if "mine" in task else ["goto_target", "harvest_target",
                                       "pickup_item", "place_block",
                                       "give_tool", "goto_base", "wait"])
    proposed = faulty if rng.random() < 0.7 else rng.choice(options)
    state = (
        "task: %s\n"
        "current phase: %s\n"
        "facts: bot at (%d, %d, %d), near_target=%s, near_base=%s, %s=%s\n"
        "carrying: %s\nitems: %s\n"
        "since_last_step: %s\nlast_action: %s\nproposed action: %s"
    ) % (
        task, phase, bot[0], bot[1], bot[2],
        "yes" if near_t else "no", "yes" if near_b else "no",
        fixture_label, "yes" if fixture else "no",
        ", ".join(carry) or "empty",
        ", ".join(items) or "none",
        since, last, proposed,
    )
    return {
        "id": None, "source": "ft2-abstain-2026-09-26", "mission": task[:8],
        "family": "abstain", "state": state, "options": options,
        "oracle": "wait", "proposed": proposed,
    }


def main():
    out = os.path.join(DATA, "ft2-rows-2026-09-26")
    os.makedirs(out, exist_ok=True)

    # 1) carry over: v1 training corpus + R1a OOV probes
    v1 = json.load(open(os.path.join(DATA, "ft-rows-v2-2026-09-25.json")))
    oov = json.load(open(os.path.join(DATA, "r1-probe-rows-2026-09-25.json")))
    # the val world must NOT leak into training
    valworld = json.load(open(os.path.join(DATA, "valworld-2026-09-26.json")))
    val_states = set(r["state"] for r in valworld)
    v1 = [r for r in v1 if r["state"] not in val_states]
    oov = [r for r in oov if r["state"] not in val_states]

    # 2) build mission grid (~80 rows across the four phases)
    build = []
    for phase in ("travel", "travel", "build", "build", "build",
                  "return", "return", "done", "done"):
        for _ in range(8):
            build.append(make_build_row(rng, phase))

    # 3) abstention rows: ~96, deduped (the 13 templates with small
    # positional variation produce identical twins), split half/half
    abstain = []
    for i in range(96):
        spec = ABSTAIN_TASKS[i % len(ABSTAIN_TASKS)]
        abstain.append(make_abstain_row(rng, spec))
    seen, uabstain = set(), []
    for r in abstain:
        if r["state"] in seen:
            continue
        seen.add(r["state"])
        uabstain.append(r)
    half = len(uabstain) // 2
    abstain_train, abstain_held = uabstain[:half], uabstain[half:]

    train = v1 + oov + build + abstain_train
    rng.shuffle(train)
    for i, r in enumerate(train):
        r["id"] = "ft2-%03d" % i
    with open(os.path.join(out, "train.jsonl"), "w") as f:
        for r in train:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    val = valworld + abstain_held
    for i, r in enumerate(val):
        r.setdefault("id", "ft2val-%03d" % i)
    with open(os.path.join(out, "val.json"), "w") as f:
        json.dump(val, f, indent=1, ensure_ascii=False)

    from collections import Counter
    print("train: %d rows" % len(train))
    print("  by family:", dict(Counter(r["family"] for r in train)))
    print("  by oracle:", dict(Counter(r["oracle"] for r in train)))
    print("val: %d rows" % len(val),
          "(valworld %d + abstain-held %d)" % (len(valworld), len(abstain_held)))
    # leak check: no train state may equal a val state
    overlap = set(r["state"] for r in train) & set(r["state"] for r in val)
    print("train/val state overlap:", len(overlap))
    assert not overlap


if __name__ == "__main__":
    sys.exit(main())
