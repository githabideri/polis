#!/usr/bin/env python3
"""gen-pickup-place-rows.py -- labeled 7-option grid rows for the pickup_item
and place_block options (2026-09-25, fine-tune corpus extension).

Same grid discipline as gen-give-tool-rows.py: A/B contrast pairs plus
controls, state text in the exact v5 serializer format (incl. the new
`items:` line), 7-option prompt set per mission.

Row families:
  pm-A  mine, item on ground, propose pickup_item   (oracle pickup_item)
  pm-B  mine, item on ground, propose goto_base     (oracle pickup_item)
  pm-C  mine, nothing on ground, return phase       (oracle goto_base)
  ph-A  harvest, item on ground, propose pickup_item (oracle pickup_item)
  ph-B  harvest, item on ground, propose goto_base   (oracle pickup_item)
  pb-A  build, marker present, propose place_block   (oracle place_block)
  pb-B  build, marker present, propose goto_base     (oracle place_block)
  pb-C  build, marker gone, return phase             (oracle goto_base)

Usage: python3 gen-pickup-place-rows.py > data/pickup-place-rows-2026-09-25.json
"""
import json
import random

random.seed(20260925)

MINE_OPTS = ["goto_target", "mine_target", "pickup_item", "place_block",
             "give_tool", "goto_base", "wait"]
HARVEST_OPTS = ["goto_target", "harvest_target", "pickup_item", "place_block",
                "give_tool", "goto_base", "wait"]
BUILD_OPTS = MINE_OPTS  # build uses the mine-style set (letter parity)

T_MINE = "mine the marker block, then return to base"
T_HARVEST = "harvest the crop, then return to base"
T_BUILD = "place a block at the marker, then return to base"


def state(task, phase, x, y, z, near_t, near_b, fixture_label, fixture,
          carrying, items, since, last_action, proposed):
    return ("task: %s\ncurrent phase: %s\n"
            "facts: bot at (%d, %d, %d), near_target=%s, near_base=%s, %s=%s\n"
            "carrying: %s\nitems: %s\n"
            "since_last_step: %s\nlast_action: %s\nproposed action: %s"
            % (task, phase, x, y, z,
               "yes" if near_t else "no", "yes" if near_b else "no",
               fixture_label, "yes" if fixture else "no",
               carrying, items, since, last_action, proposed))


def row(rid, fam, state_text, options, oracle, proposed):
    return {"id": rid, "family": fam, "type": proposed, "state": state_text,
            "options": options, "oracle": oracle, "proposed": proposed}


def pos(i):
    return (512008 + (i % 7) * 3, 3, 512016 + (i % 5) * 2)


rows = []
i = 0

# --- mine pickup: item on ground (marker gone) ---------------------------
for k in range(12):
    x, y, z = pos(k)
    item = "rock-granite" if k % 3 == 0 else "stone-granite" if k % 3 == 1 \
        else "game:rock-granite"
    last = ["marker removed", "mining done", "no change"][k % 3]
    since = "marker gone" if k % 2 == 0 else "no change"
    st = state(T_MINE, "pickup", x, y, z, k % 4 == 0, False,
               "marker_present", False,
               "game:pickaxe-iron, game:linensack", item, since, last,
               "pickup_item")
    rows.append(row("pm-A%02d" % k, "pickup-mine", st, MINE_OPTS,
                    "pickup_item", "pickup_item"))
    i += 1
for k in range(12):
    x, y, z = pos(k + 2)
    item = "rock-granite" if k % 2 == 0 else "stone-granite"
    st = state(T_MINE, "pickup", x, y, z, False, False,
               "marker_present", False,
               "game:pickaxe-iron, game:linensack", item,
               "no change" if k % 2 else "marker gone", "marker removed",
               "goto_base")
    rows.append(row("pm-B%02d" % k, "pickup-mine", st, MINE_OPTS,
                    "pickup_item", "goto_base"))
    i += 1
for k in range(6):
    x, y, z = pos(k + 4)
    st = state(T_MINE, "return", x, y, z, False, False,
               "marker_present", False,
               "game:pickaxe-iron, game:linensack", "none",
               "no change", "marker removed", "goto_base")
    rows.append(row("pm-C%02d" % k, "pickup-mine", st, MINE_OPTS,
                    "goto_base", "goto_base"))
    i += 1

# --- harvest pickup: harvested item on ground (crop gone) -----------------
for k in range(6):
    x, y, z = pos(k + 1)
    st = state(T_HARVEST, "pickup", x, y, z, k % 3 == 0, False,
               "crop_present", False,
               "game:linensack", "crop-carrot",
               "crop gone" if k % 2 == 0 else "no change",
               "harvested crop", "pickup_item")
    rows.append(row("ph-A%02d" % k, "pickup-harvest", st, HARVEST_OPTS,
                    "pickup_item", "pickup_item"))
    i += 1
for k in range(6):
    x, y, z = pos(k + 3)
    st = state(T_HARVEST, "pickup", x, y, z, False, False,
               "crop_present", False,
               "game:linensack", "crop-carrot", "no change", "harvested crop",
               "goto_base")
    rows.append(row("ph-B%02d" % k, "pickup-harvest", st, HARVEST_OPTS,
                    "pickup_item", "goto_base"))
    i += 1

# --- build: marker present -> place_block ----------------------------------
for k in range(6):
    x, y, z = pos(k + 5)
    st = state(T_BUILD, "build", x, y, z, True, False,
               "marker_present", True,
               "rock-granite, game:linensack", "none",
               "no change" if k % 2 else "arrived at marker",
               "none", "place_block")
    rows.append(row("pb-A%02d" % k, "build", st, BUILD_OPTS,
                    "place_block", "place_block"))
    i += 1
for k in range(6):
    x, y, z = pos(k + 6)
    st = state(T_BUILD, "build", x, y, z, True, False,
               "marker_present", True,
               "rock-granite, game:linensack", "none",
               "arrived at marker", "none", "goto_base")
    rows.append(row("pb-B%02d" % k, "build", st, BUILD_OPTS,
                    "place_block", "goto_base"))
    i += 1
for k in range(6):
    x, y, z = pos(k + 7)
    st = state(T_BUILD, "return", x, y, z, False, False,
               "marker_present", False,
               "rock-granite, game:linensack", "none",
               "no change", "block placed", "goto_base")
    rows.append(row("pb-C%02d" % k, "build", st, BUILD_OPTS,
                    "goto_base", "goto_base"))
    i += 1

print(json.dumps(rows, indent=1))
