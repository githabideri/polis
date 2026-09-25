#!/usr/bin/env python3
"""gen-give-tool-rows.py -- build the give_tool labeled set (5-option readout).

The Decider was trained on 4-option sets (no give_tool). v5 added
`give_tool` as a first-class action and it generalized healthily
(uncalibrated p ~0.23 on the live tool-fault rows). This script builds a
labeled grid around the *actual* live no-tool states observed in
data/v5-mine-toolfault-2026-09-25.json (step 2/3): same state-text format
the model sees in the live loop, varying position / carried non-tool items
across a small grid.

Row types:
  A  no tool, proposal = give_tool  -> oracle give_tool   (good proposal)
  B  no tool, proposal = mine_target-> oracle give_tool   (bad proposal:
     the 27B-observed failure mode, repeated tool-less mine)
  C  with pickaxe, proposal = mine_target -> oracle mine_target (control:
     does the 5-option readout drift on the trained action?)

Output: JSONL (one object per row: id, type, state, options, oracle)
suitable for POSTing to decider-service.py /readout one by one, or for
batching through gguf-runner after a format shim.

Usage: gen-give-tool-rows.py [--n-per-type 12] [--control 6] [--out FILE]
"""
import argparse
import json
import sys

OPTIONS = ["goto_target", "mine_target", "goto_base", "wait", "give_tool"]

TASK = "task: mine the marker block, then return to base"
POS = [(512012, 3, 512022), (512016, 4, 512029), (512005, 3, 512015),
       (512024, 3, 512031)]
# non-tool carried items only (a pickaxe in carrying makes it a C row)
CARRY = ["game:linensack", "game:linensack, game:rock-granite"]
SINCE = ["pickaxe dropped", "no change"]
LAST_TOOLLESS = "Tool required: block needs tier 2"


def state(x, y, z, carry, since, last, proposed):
    return (f"{TASK}\n"
            "current phase: mine\n"
            f"facts: bot at ({x}, {y}, {z}), near_target=yes, near_base=no, "
            "marker_present=yes\n"
            f"carrying: {carry}\n"
            f"since_last_step: {since}\n"
            f"last_action: {last}\n"
            f"proposed action: {proposed}")


def grid(n):
    """Deterministic round-robin over position x carry x since, n rows."""
    combos = [(x, y, z, c, s) for (x, y, z) in POS for c in CARRY for s in SINCE]
    out = []
    for i in range(n):
        out.append(combos[i % len(combos)])
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n-per-type", type=int, default=12)
    ap.add_argument("--control", type=int, default=6)
    ap.add_argument("--out", default="give-tool-rows.jsonl")
    a = ap.parse_args()

    rows = []
    for i, (x, y, z, c, s) in enumerate(grid(a.n_per_type)):
        rows.append({
            "id": f"A{i:02d}", "type": "A",
            "state": state(x, y, z, c, s, LAST_TOOLLESS, "give_tool"),
            "options": OPTIONS, "oracle": "give_tool",
        })
        rows.append({
            "id": f"B{i:02d}", "type": "B",
            "state": state(x, y, z, c, s, LAST_TOOLLESS, "mine_target"),
            "options": OPTIONS, "oracle": "give_tool",
        })
    for i, (x, y, z, c, s) in enumerate(grid(a.control)):
        rows.append({
            "id": f"C{i:02d}", "type": "C",
            "state": state(x, y, z, "game:pickaxe-iron, " + c,
                           "phase travel -> mine", "done", "mine_target"),
            "options": OPTIONS, "oracle": "mine_target",
        })

    with open(a.out, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    print(f"wrote {len(rows)} rows ({a.n_per_type} A, {a.n_per_type} B, "
          f"{a.control} C) to {a.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
