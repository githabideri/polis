#!/usr/bin/env python3
"""remap-7opt-rows.py -- normalize every labeled row in the polis data/
directory to the 7-option fine-tune format (2026-09-25).

Sources:
  ab-decider-*.rows.json        41-row A/B corpus (state, options, oracle)
  give-tool-rows-*.json         30-row give_tool grid (same shape)
  v5-*.json                     live v5 runs (state_text, oracle; 11 rows)
  labeled-set-*.json            v1-v4 live rows (state_text, oracle)

Normalization:
  - options -> the mission's 7-option set (letter positions fixed)
  - state -> the v5 serializer shape: an `items:` line is inserted after
    `carrying:` (dropped pickaxe rows get the pickaxe code, else "none")
  - rows whose oracle is not in the 7-option set are dropped (none expected)

Output: data/ft-rows-2026-09-25.json  (list; deduped on state+oracle)
Usage: python3 remap-7opt-rows.py [outdir]
"""
import glob
import json
import os
import re
import sys

MINE = ("goto_target", "mine_target", "pickup_item", "place_block",
        "give_tool", "goto_base", "wait")
HARVEST = ("goto_target", "harvest_target", "pickup_item", "place_block",
           "give_tool", "goto_base", "wait")


def mission_of(state):
    if state.startswith("task: harvest"):
        return "harvest"
    if state.startswith("task: place a block"):
        return "build"
    return "mine"


def normalize_state(state):
    """Insert the items: line after carrying: (old formats lack it)."""
    if "\nitems: " in state:
        return state
    m = re.search(r"^(.*\ncarrying: [^\n]*)\n", state)
    if not m:
        return state
    if "dropped" in state:
        items = "game:pickaxe-iron"
    else:
        items = "none"
    return m.group(1) + "\nitems: " + items + state[m.end():]


def take(d):
    """Row containers: top-level list, or dict with rows/data/results."""
    if isinstance(d, list):
        return d
    if isinstance(d, dict):
        for k in ("rows", "data", "results"):
            if isinstance(d.get(k), list):
                return d[k]
    return None


def main(outdir="data"):
    here = os.path.dirname(os.path.abspath(__file__))
    datadir = outdir if os.path.isabs(outdir) else os.path.join(
        os.path.dirname(here), "..", outdir)
    seen = {}
    n_src = 0
    for path in sorted(glob.glob(os.path.join(datadir, "*.json"))):
        base = os.path.basename(path)
        if base.startswith("ft-rows"):
            continue
        try:
            d = json.load(open(path))
        except Exception:
            continue
        rows = take(d)
        if not rows:
            continue
        for i, r in enumerate(rows):
            state = r.get("state") or r.get("state_text")
            oracle = r.get("oracle")
            if not state or not oracle:
                continue
            mission = mission_of(state)
            options = list(MINE if mission in ("mine", "build") else HARVEST)
            if oracle not in options:
                continue
            state = normalize_state(state)
            key = (state, oracle)
            if key in seen:
                continue
            seen[key] = {
                "id": "%s-%d" % (base.split("-")[0], len(seen)),
                "source": base, "mission": mission,
                "family": (r.get("family")
                           or (r.get("type") if r.get("type") in
                               ("A", "B", "C") else mission)),
                "state": state, "options": options, "oracle": oracle,
                "proposed": r.get("proposed") or r.get("proposal"),
            }
        n_src += 1
    out = [seen[k] for k in sorted(seen)]
    outpath = os.path.join(datadir, "ft-rows-2026-09-25.json")
    json.dump(out, open(outpath, "w"), indent=1)
    from collections import Counter
    print("sources scanned: %d, rows kept: %d" % (n_src, len(out)))
    print("by oracle:", dict(Counter(x["oracle"] for x in out)))
    print("by mission:", dict(Counter(x["mission"] for x in out)))
    print("wrote", outpath)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "data")
