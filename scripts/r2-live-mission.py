#!/usr/bin/env python3
"""
R2 Phase 6 - the live two-job milestone: goal -> 27B planner ->
deterministic validator -> JobQueue -> per-job executor (v5 primitives)
-> per-job oracle (fresh game observation) -> goal_complete.

The milestone is re-scoped per design doc 12.9: the mined material
(stone-granite) and the placeable material (rock-granite) are distinct
in this world, so the canonical two-job goal is an EXTERNAL-SUPPLY
place (give_tool -> place) or a multi-job harvest; mine->place lives in
the P5 fixtures as the validator's rejection case.

Wiring (all existing, no new game code):
  - Polis / goto_wait / execute / carrying_from: imported from
    scripts/jev-loop-v5.py (one implementation)
  - WorldModel + build_planner_prompt + validate_plan + GoalState:
    the r2/ package
  - the 27B via the same OpenAI-compatible endpoint the judge uses

Run on the polis CT:
  python3 scripts/r2-live-mission.py \
    --harness http://127.0.0.1:8585 --uid <playerUid> \
    --llm http://<llm>:8080 --llm-model <model> \
    --goal "place granite at site-A x1" \
    --out data/r2-run-<date>.json

Operator campaign mode (2026-10-06, the crude-door chain): an explicit
job list runs with no grammar parsing and no planner - the jobs are
validated against the LIVE world first (chop cells, the shaped recipe
pattern against the projected inventory), then execute in list order
through the normal queue/executor/oracle machinery. `--goal` is the
campaign description line (recorded in the run JSON):
  python3 scripts/r2-live-mission.py \
    --harness http://127.0.0.1:8585 --uid <playerUid> --no-planner \
    --goal "operator campaign: install door-crude at (x,y,z)" \
    --jobs '[{"type":"give_tool","material":"axe-felling-copper","n":1}, ...]' \
    --out data/r2-run-<date>.json

Sanitization: the run JSON records model names and game-internal facts
only - no host names or addresses (the repo is publication-staged).
"""
import argparse
import fnmatch
import importlib.util
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.join(HERE, "..")
sys.path.insert(0, REPO)

# the v5 module (dash in the filename -> explicit loader)
_v5_spec = importlib.util.spec_from_file_location(
    "jevloopv5", os.path.join(HERE, "jev-loop-v5.py"))
v5 = importlib.util.module_from_spec(_v5_spec)
_v5_spec.loader.exec_module(v5)

from r2.worldmodel import WorldModel
from r2.plannerprompt import build_planner_prompt
from r2.embodiment import embodiment as _embodiment_fn, is_solid  # 09-29: the body-vs-solid-world check
from r2.plancheck import validate_plan, check_goal
from r2.jobqueue import GoalState
from r2.jobs import Goal, Job, Failure
from r2 import approach as r2approach
from r2.queries import classify

# material name -> the ITEM code a give_tool job supplies (the placeable
# stone item, per the 2026-09-28 probe: rock-granite is what place
# consumes). Only the external-supply path uses this table.
GIVE_ITEM = {
    "granite": "rock-granite",
    "stone": "stone-granite",
    "rye": "crop-rye-2",
    "carrot": "crop-carrot-7",
    # 2026-10-05: digging a soil block drops one soil-{fertility}-none
    # item, which places the same block (the blocktype's own drop
    # declaration). The honest dirt-hut material (builds/hut-dirt.json).
    "dirt": "soil-low-none",
    # 2026-10-07: the raw material name "axe" is not an item code; the
    # engine's axe collectible is axe-felling-copper (the door recipe's
    # tool-axe cell matches it by tag, not by code).
    "axe": "axe-felling-copper",
}

#: material name -> the BLOCK code a place/build of it leaves in the
#: world (the oracle's count predicate). granite's placeable block is
#: rock-granite (the 2026-09-28 probe: the item is stone-granite, the
#: placed block is rock-granite).
MATERIAL_BLOCK = {"granite": "rock-granite", "stone": "rock-granite",
                  "dirt": "soil"}

#: materials a bare hand mines (no harness tool privilege - the honest
#: survival path: soil breaks by hand in 1.22, so the dirt hut needs no
#: iron where the world gives none). 2026-10-05.
HAND_MINABLE = {"dirt"}


def parse_goal_line(line):
    """'place granite at site-A x1 supply external' ->
    {verb, object, at, n, supply}. The supply flag is an OPERATOR
    declaration (design doc 12.10 remediation (a)): the operator says
    at intake that external (harness) supply is sanctioned for this
    goal; the orchestrator then supplies the material DETERMINISTICALLY
    (logged as job j0), so the planner sees a world it can plan.
    """
    toks = line.split()
    if not toks:
        raise ValueError("empty goal")
    goal = {"verb": toks[0], "object": toks[1] if len(toks) > 1 else ""}
    rest = toks[2:]
    i = 0
    while i < len(rest):
        if rest[i] == "at" and i + 1 < len(rest):
            goal["at"] = rest[i + 1]
            i += 2
        elif rest[i].startswith("x") and rest[i][1:].isdigit():
            goal["n"] = int(rest[i][1:])
            i += 1
        elif rest[i] == "supply" and i + 1 < len(rest):
            if rest[i + 1] != "external":
                raise ValueError("only 'supply external' is declared")
            goal["supply"] = "external"
            i += 2
        else:
            raise ValueError("unparseable goal token %r" % rest[i])
    return goal


def boot(pol, radius=14, keep=None):
    """Fresh bot + first world observation. Returns (bot, wm, state,
    scan_summary). `keep`: bot ids the sweep must NOT kill (2026-10-10:
    the sweep used to kill the Oikistes body and the operator's whole
    crew on every mission - the body-as-identity contract needs them
    to survive the mission's world reset)."""
    pol.sweep_bots(keep=keep)
    time.sleep(2)
    r = v5.http_json(pol.base + "/polis/command",
                     {"cmd": "spawn", "args": [],
                      "context": {"playerUid": pol.uid}})
    bot = (r.get("Data") or {}).get("id")
    st = pol.state(bot)
    pos = st["Bot"]["Pos"]
    wm = WorldModel()
    wm.new_tick(reason="planner_scan")
    x0, y0, z0 = int(pos[0]), int(pos[1]), int(pos[2])
    # bot-relative box (2026-10-05): the flat world lived at y2-6; the
    # Standard terrain of a survival world lives at y140+ - a hard-coded
    # low box scans the void (or the hillside) there.
    box = [str(x0 - radius), str(y0 - 4), str(z0 - radius),
           str(x0 + radius), str(y0 + 8), str(z0 + radius)]
    # 2026-10-10: wait for the box's CHUNKS before trusting the scan.
    # The old fixed 2 s sleep fired the scan while the server was still
    # loading the box's chunks (a 1.5 FPS world) - a 29x13x29 box then
    # "saw" the few blocks of whatever chunk had made it (the dirt-hut
    # mission counted 4 of 103 soil on a plateau holding 1600+). Re-scan
    # until the block count holds steady across two passes, or the
    # budget runs out; the last scan is what the world model gets.
    prev = None
    scan = None
    passes = 0
    n = 0
    for _ in range(14):          # ~42 s worst case at 3 s intervals
        passes += 1
        scan = pol.cmd("scan", box, bot)
        n = len((scan.get("Data") or {}).get("blocks", []) or [])
        if n == prev and passes > 1:
            break
        prev = n
        time.sleep(3)
    wm.observe_scan(scan, reason="planner_scan")
    # record what the boot scan actually saw (2026-10-10): the
    # mine-prep rejection 'scanned clusters cover 4 of 103' was a
    # chunk-timing artifact that was invisible in the run JSON;
    # the summary goes into the record so the next one is readable.
    from collections import Counter as _C
    _codes = _C((b.get("code") or "?") for b in
                (scan.get("Data") or {}).get("blocks", []) or [])
    scan_summary = {"box": [int(v) for v in box], "passes": passes,
                    "blocks": n, "top": dict(_codes.most_common(6)),
                    "bot_pos": [x0, y0, z0]}
    return bot, wm, st, scan_summary


def inventory_of(state):
    """carrying -> {code: qty} (hands + cargo)."""
    b = (state or {}).get("Bot") or {}
    out = {}
    for k in ("RightHand", "LeftHand"):
        it = b.get(k)
        if it and it.get("Code"):
            out[it["Code"]] = out.get(it["Code"], 0) + (it.get("Qty") or 1)
    for it in (b.get("Backpack") or []):
        if it.get("Code"):
            out[it["Code"]] = out.get(it["Code"], 0) + (it.get("Qty") or 1)
    return out


def normalize_inv(inv):
    """{normalized material: qty} for the planner's INVENTORY line."""
    out = {}
    for code, qty in inv.items():
        mat = classify(code)[1]
        out[mat] = out.get(mat, 0) + qty
    return out


def register_site(wm, pol, bot, goal, fixtures, operator_site=None):
    """Make sure the goal's site exists as a fixture (we created it -
    authoritative identity, doc 5.3). Convention (the one the P5
    fixtures use, e.g. C3): a build-site's REQUIREMENT is an empty
    cell and its condition is whether that empty cell is present - so
    the prompt line 'requirement=empty now=True/False' reads the same
    in the live world as in the measured suite.
    """
    out = []
    if getattr(goal, "at", None) and goal.at not in wm.fixtures:
        st = pol.state(bot)
        pos = st["Bot"]["Pos"]
        bx, bz = int(pos[0]), int(pos[2])
        if getattr(goal, "verb", None) == "sow":
            # a sow site is a FARMLAND cell (the crop lands on top of
            # it): find one nearby, or stage one deterministically
            # (operator action, recorded in the fixture's source)
            cell, src = None, "staged"
            near = []
            for b in (pol.cell_blocks(bot, (bx, 3, bz), pad=12) or []):
                if (b.get("code") or "").startswith("game:farmland"):
                    near.append(b["pos"])
            if near:
                near.sort(key=lambda p: abs(p[0] - bx) + abs(p[2] - bz))
                cell, src = near[0], "scanned"
            else:
                cell = [bx + 2, 2, bz]
                r = pol.cmd("setblock", ["game:farmland-dry-verylow",
                                         str(cell[0]), str(cell[1]),
                                         str(cell[2])], bot)
                src = "staged(ok=%s)" % r.get("Ok")
            wm.register_fixture(goal.at, "farmland", cell, "farmland")
            wm.observe_fixture(goal.at, True, reason="fixture_setup:%s" % src)
        else:
            by = int(pos[1])  # the bot's own standing layer (2026-10-05)
            if operator_site:  # the operator surveyed the spot (run JSON)
                cell = list(operator_site)
                blocks = pol.cell_blocks(bot, tuple(cell), pad=0)
                empty = not any(b.get("pos") == cell for b in blocks)
            else:
                cell, empty = None, False
                for dx in range(2, 6):
                    cand = (bx + dx, by, bz)
                    blocks = pol.cell_blocks(bot, cand, pad=0)
                    filled = any(b.get("pos") == [cand[0], cand[1],
                                                  cand[2]] for b in blocks)
                    if not filled:
                        cell, empty = list(cand), True
                        break
                if cell is None:  # everything filled - the site cannot
                    cell = [bx + 2, by, bz]  # be a place target
            wm.register_fixture(goal.at, "build-site", cell, "empty")
            wm.observe_fixture(goal.at, empty, reason="fixture_setup")
    for fid, f in sorted(wm.fixtures.items()):
        cond = wm.fixture_observations.get(fid)
        out.append({"id": fid, "kind": f.kind,
                    "requirement": f.requirement,
                    "condition": cond.present if cond else None})
    return out


def goto_arrive(pol, bot, cell, timeout=45):
    """Position-verified goto to a cell CENTRE (09-29). Two defects
    made v5.goto_wait unsafe for building: it polls the bot's
    LastAction (the LAST RECORDED action - a stale Ok=True from the
    PREVIOUS goto reads as an instant false 'arrived'), and the
    harness goto targets the cell CORNER - and the place command's
    standing-cell math ties (|dx|==|dz|) exactly on a corner, picking
    an offset into an already-placed block. A bot at the cell
    CENTRE never ties (dx=0 or dz=0 strictly dominates), and the
    arrival is verified by position, not by the action's word."""
    x = "%0.1f" % (cell[0] + 0.5)
    z = "%0.1f" % (cell[2] + 0.5)
    pol.cmd("goto", [x, str(cell[1]), z, "true", "0.02", "true"], bot)
    t0 = time.time()
    while time.time() - t0 < timeout:
        st = pol.state(bot)
        la = st.get("LastAction") or {}
        pos = (st.get("Bot") or {}).get("Pos") or [0, 0, 0]
        # x/z are centred; y is the FEET - the bot walks at the layer
        # level (y = cell[1]), it does not float at the cell centre
        # (09-29: the old check demanded y within 0.25 of cell+0.5 -
        # unsatisfiable - and every goto timed out silently)
        if (abs(pos[0] - (cell[0] + 0.5)) <= 0.25 and
                abs(pos[2] - (cell[2] + 0.5)) <= 0.25 and
                abs(pos[1] - cell[1]) <= 0.25):
            return True
        if la.get("Name") == "goto" and la.get("Ok") is False:
            return False
        time.sleep(0.5)
    return False


def recheck_and_recover(pol, bot, label=""):
    """Embodiment recheck + one recovery attempt (2026-10-05).

    The traverser sometimes lands a bot ONE BLOCK LOW: on hilly soil
    terrain an approach candidate built at the target block's y is the
    top-solid level, so the bot ends up standing IN the top soil layer
    (feet cell solid, head cell air/plant). Such a bot can still move -
    it is sunk, not wedged - so the recovery is to re-goto the correct
    stand height for its own column (top solid + 1). A bot whose HEAD
    cell is solid (fully buried) or whose body is clear but all four
    neighbours solid (TRAPPED) cannot be recovered by a goto.

    Returns (ok, state, detail): ok=True means the bot is standing
    (OK or recovered-OK). ok=False means the bot is wedged/trapped
    and the caller must abort the job with `detail`.
    """
    def _scan_and_classify():
        pos = pol.state(bot)["Bot"]["Pos"]
        bx, by, bz = int(pos[0]), int(pos[1]), int(pos[2])
        box = pol.cmd("scan", [str(bx - 1), str(by - 2), str(bz - 1),
                               str(bx + 1), str(by + 2), str(bz + 1)],
                      bot)
        blocks = (box.get("Data") or {}).get("blocks") or []
        cellmap = {}
        for b in blocks:
            pb = b.get("pos")
            code = b.get("code")
            if pb and code and code != "game:air":
                cellmap[(pb[0], pb[1], pb[2])] = code
        # top solid y in the bot's own column (from the same scan)
        top = None
        for (cx, cy, cz), code in cellmap.items():
            if cx == bx and cz == bz and is_solid(code):
                top = cy if top is None else max(top, cy)
        state, detail = _embodiment_fn(pos, cellmap)
        return state, detail, top, (bx, by, bz)

    state, detail, top, (bx, by, bz) = _scan_and_classify()
    if state == "OK":
        return True, state, "body clear%s" % ((" " + label) if label else "")
    if state == "TRAPPED":
        # "all 4 foot-level neighbours solid" is a 1-block dip on hilly
        # terrain, not a sealed pit: the VS agent auto-climbs ONE block,
        # so if any neighbour's stand height is within 1 block the bot
        # walks out. Only a pit whose walls are all >=2 blocks up is
        # genuinely inescapable.
        up_ok, up_detail = climb_out_possible(pol, bot)
        if up_ok:
            return True, "trapped-but-climbable", \
                ("%s: %s but %s (continuing)" % (label, detail,
                                                 up_detail))
        return False, state, \
            ("%s: %s and %s (no climb-out)" % (label, detail, up_detail))
    # EMBEDDED: try one recovery - re-goto the correct stand height
    # (top solid + 1) in the bot's own column
    if top is not None:
        target = (bx, top + 1, bz)
        v5.goto_wait(pol, bot, target, timeout=25)
        time.sleep(2)
        state2, detail2, _top2, _ = _scan_and_classify()
        if state2 == "OK":
            return True, "recovered", \
                ("%s: was %s (feet y%d, top solid y%d) - re-goto stand "
                 "height y%d -> OK" % (label, state, by, top, top + 1))
        return False, state2, \
            ("%s: recovery failed - was %s, after re-goto to y%d "
             "still %s: %s" % (label, state, top + 1, state2, detail2))
    # embedded but no solid in the column from the scan (odd) - abort
    return False, state, \
        "%s: %s (no top solid found to recover to)" % (label, detail)


def climb_out_possible(pol, bot):
    """Can the bot walk/climb out of where it stands? (2026-10-05)

    The VS agent auto-climbs ONE block; it cannot scale a 2-block wall.
    A bot that has descended is only stuck in a deep hollow if EVERY
    horizontal neighbour's standing height (top solid + 1) is >=2
    blocks above its feet. If any neighbour is within 1 block (or lower
    - an easy walk), the bot is on open ground, not in a pit, and the
    descent is normal terrain. Returns (possible, detail).
    """
    pos = pol.state(bot)["Bot"]["Pos"]
    bx, by, bz = int(pos[0]), int(pos[1]), int(pos[2])
    box = pol.cmd("scan", [str(bx - 1), str(by - 2), str(bz - 1),
                           str(bx + 1), str(by + 2), str(bz + 1)], bot)
    blocks = (box.get("Data") or {}).get("blocks") or []
    tops = {}
    for b in blocks:
        pb, code = b.get("pos"), b.get("code") or ""
        if pb and (is_solid(code)):
            tops[(pb[0], pb[2])] = max(tops.get((pb[0], pb[2]), pb[1]), pb[1])
    best = None
    for (nx, nz) in ((bx + 1, bz), (bx - 1, bz), (bx, bz + 1), (bx, bz - 1)):
        t = tops.get((nx, nz))
        if t is None:
            continue  # no solid in that column from this scan
        climb = (t + 1) - by  # neighbour stand height minus bot feet
        best = climb if best is None else min(best, climb)
    if best is None:
        # no solid neighbours found - treat as open ground (not a pit)
        return True, "no walled neighbours (open ground)"
    if best <= 1:
        return True, "climbable neighbour (%d block up)" % best
    return False, "all %d neighbours >=2 blocks up (deep hollow)" % best


def _rescue_wedged_bot(pol, bot, haul):
    """Hard-reset a wedged worker: despawn, respawn, re-give the
    measured haul. Returns the new bot id, or None. 2026-10-10: the
    mine loop ABORTED on the first wedge (a 2-deep hollow - the VS
    agent climbs 1, not 2) and the goal died with the bot's haul; the
    build path already had this pattern for its place-loop wedges, so
    the mine path shares it now."""
    pol.cmd("despawn", [str(bot)], bot)
    time.sleep(3)
    r = v5.http_json(pol.base + "/polis/command",
                    {"cmd": "spawn", "args": [],
                     "context": {"playerUid": pol.uid}})
    nb = (r.get("Data") or {}).get("id")
    if not nb:
        return None
    time.sleep(6)
    for item, q in sorted((kv for kv in haul.items() if kv[1] > 0),
                          key=lambda kv: kv[0]):
        pol.cmd("give", [item, str(q)], nb)
        time.sleep(1)
    return nb


def _fresh_exposed(pol, bot, rec, wm, mat, radius=20):
    """Cells of material `mat` that are CURRENTLY exposed (air directly
    above), from a fresh scan of the region around the build site AND the
    resource's bounding box (2026-10-05 v5). The scan-time mineable subset
    (worldmodel.observe_scan) is unreliable on hilly terrain: the boot scan
    window can resolve a buried pocket's interior - where every cell has a
    solid layer above - while the genuinely exposed top cells sit elsewhere,
    so the executor was handed all-buried targets and mined 0 (run v4).
    Re-deriving exposure at execution time (air above RIGHT NOW) fixes it.
    Mining a top cell exposes the one below; the driver re-scans on each
    (re-)run, so columns dig deeper across runs. Returns [] on any failure
    (the caller falls back to the scan-time subset)."""
    try:
        xs = [c[0] for c in rec.cells]
        ys = [c[1] for c in rec.cells]
        zs = [c[2] for c in rec.cells]
        for f in wm.fixtures.values():
            if getattr(f, "kind", None) == "build-site" and \
                    getattr(f, "cell", None):
                sx, sy, sz = f.cell
                for dx in (-radius, radius):
                    for dz in (-radius, radius):
                        xs.append(sx + dx)
                        zs.append(sz + dz)
                ys.append(sy - 6)
                ys.append(sy + 6)
        if not xs:
            return []
        x1, x2 = min(xs), max(xs)
        z1, z2 = min(zs), max(zs)
        y1 = min(ys) - 1
        y2 = max(ys) + 2   # include the layer above the tops
        # keep the scan bounded (the harness caps at 1M blocks)
        if (x2 - x1 + 1) > 80 or (z2 - z1 + 1) > 80 or (y2 - y1 + 1) > 50:
            cx, cz = (x1 + x2) // 2, (z1 + z2) // 2
            x1, x2 = cx - 40, cx + 40
            z1, z2 = cz - 40, cz + 40
            y2 = min(y2, y1 + 49)
        r = pol.cmd("scan", [str(x1), str(y1), str(z1),
                             str(x2), str(y2), str(z2)], bot)
        blocks = (r.get("Data") or {}).get("blocks", []) or []
        solid = {tuple(b["pos"]) for b in blocks
                 if b.get("code") and b.get("pos") and is_solid(b["code"])}
        cells = []
        for b in blocks:
            code = b.get("code") or ""
            pos = b.get("pos")
            if not code or not pos or code == "game:air":
                continue
            if classify(code)[1] != mat:
                continue
            if (pos[0], pos[1] + 1, pos[2]) not in solid:
                cells.append((pos[0], pos[1], pos[2]))
        return cells
    except Exception as e:
        sys.stderr.write("  _fresh_exposed: %r\n" % (e,))
        return []


def execute_job(pol, bot, base, job, wm, run, botref=None):
    """One job's actuation + oracle. Returns (ok, detail, measured,
    execution, oracle). The split is the 13.2 invariant: the ENGINE'S
    verdict on the action (execution) and the FRESH-WORLD check of the
    resulting condition (oracle) are related but not interchangeable -
    'action failed' and 'action succeeded but the world did not
    change' must produce different attribution. All game checks are
    FRESH observations (the 12.6 invariant)."""
    measured = {}
    if job.type == "give_tool":
        item = GIVE_ITEM.get(job.material, job.material)
        qty = job.quantity or 1
        # 2026-10-07: the give can be queued before the freshly
        # spawned agent is fully loaded; the game thread then drops
        # it and the state never shows the item (run: "gave axe x1
        # -> carried 0"). Re-issue the command up to 3 times before
        # declaring failure.
        got = 0
        for attempt in range(3):
            if attempt:
                pol.cmd("give", [item, str(qty)], bot)
            else:
                r = pol.cmd("give", [item, str(qty)], bot)
                ok = bool(r.get("Ok"))
            for _ in range(10):
                st = pol.state(bot)
                inv = inventory_of(st)
                # the state serializes codes with the namespace
                # prefix ("game:axe-felling-copper") - match both
                # forms
                got = inv.get(item, 0) + inv.get("game:" + item, 0)
                if got >= qty:
                    break
                time.sleep(1)
            if got >= qty:
                break
        measured = {item: got}
        ok = got >= qty
        return ok, ("gave %s x%d -> carried %d" % (item, qty, got)), \
            measured, \
            {"cmd": "give", "item": item, "ok": r.get("Ok")}, \
            {"carried": got, "required": qty}

    # sow (13.7 M2): 1.22's API does not expose right-click sowing (Item
    # has no public block reference), so sow is a COMPOSITE: approach
    # the farmland, then setblock a new crop above it. The seed
    # PRECONDITION is checked against the measured inventory; the seed
    # is NOT consumed by the composite - that non-consumption is an
    # engine-API gap recorded in the oracle (the crop is real; in the
    # real engine the seed is consumed on planting).
    if job.type == "sow":
        site = wm.fixtures.get(job.target)
        if site is None:
            return (False, "sow: unknown site %s" % job.target,
                    measured, {"cmd": "sow", "ok": False,
                               "reason": "unknown site"}, {})
        mat = job.material or "rye"
        crop_code = "crop-%s-2" % mat
        seed_code = "seeds-%s" % mat
        cell = list(site.cell)
        # the drop from the preceding harvest lands ASYNCHRONOUSLY (the
        # cargo registration flickers - run 25 read a transient zero): poll
        # for the seed instead of one-shot, exactly like the harvest's
        # post loop. Inventory keys carry the namespace prefix (game:...) -
        # the precondition must match both forms (run 27: a prefix-less
        # lookup read zero against a full right hand)
        need = job.quantity or 1
        seed_have = 0
        inv0 = {}
        for _ in range(12):  # up to ~12 s
            inv0 = inventory_of(pol.state(bot))
            seed_have = (inv0.get("game:" + seed_code, 0)
                         + inv0.get(seed_code, 0))
            if seed_have >= need:
                break
            time.sleep(1)
        if seed_have < need:
            return (False,
                    "sow: need %d %s, have %d (inventory: %s)"
                    % (need, seed_code, seed_have,
                       {k: v for k, v in inv0.items()}
                       if inv0 else "(empty)"), measured,
                    {"cmd": "sow", "ok": False,
                     "reason": "no seeds"},
                    {"seed_precondition": seed_have, "required": need,
                     "inventory": inv0})
        # stand-cell candidates: the WALKABLE layer (y+1) beside the
        # farmland column. The farmland is a ground-level block, so its
        # same-level neighbours are solid soil (run 29: the block-
        # neighbour logic found zero candidates), and the cell directly
        # above it is where the crop will be placed (the bot cannot
        # stand there - run 28)
        solid = set()
        for b in (pol.cell_blocks(bot, tuple(cell), pad=2) or []):
            if b.get("code") and b["code"] != "game:air":
                solid.add(tuple(b["pos"]))
        from_pos = tuple(pol.state(bot)["Bot"]["Pos"])
        stand_y = cell[1] + 1
        cands = []
        for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            c = (cell[0] + dx, stand_y, cell[2] + dz)
            if c not in solid:
                cands.append(c)
        cands.sort(key=lambda c: (abs(c[0] - from_pos[0]) +
                                  abs(c[2] - from_pos[2]), c))

        def _goto(c):
            return v5.goto_wait(pol, bot, c, timeout=25)

        def _act():
            r = pol.cmd("setblock", [crop_code, str(cell[0]),
                                     str(stand_y), str(cell[2])], bot)
            return {"ok": bool(r.get("Ok")),
                    "msg": r.get("Message") or r.get("error") or ""}

        attempts = []
        aok = False
        adetail = "no approach candidate (all stand cells blocked)"
        for cand in cands:
            g = _goto(cand)
            if not g.get("ok"):
                attempts.append({"cell": list(cand), "stage": "goto",
                                 "ok": False, "msg": g.get("msg") or ""})
                continue
            a = _act()
            attempts.append({"cell": list(cand), "stage": "action",
                             "ok": a["ok"], "msg": a["msg"]})
            aok = a["ok"]
            adetail = ("setblock %s from %s -> %s" % (crop_code, cand,
                                                     a["msg"] or
                                                     ("ok" if a["ok"] else "refused")))
            if aok:
                break
        la = pol.state(bot).get("LastAction") or {}
        # oracle: a crop block now sits in the walkable cell above the
        # farmland. Scan codes carry the namespace prefix - match both
        # forms (run 30: the crop was placed and stable, the oracle's
        # prefix-less startswith read it as absent)
        crop_cell = (cell[0], stand_y, cell[2])
        blocks = pol.cell_blocks(bot, crop_cell)
        crop_present = any(
            str(b.get("code") or "").replace("game:", "").startswith(
                "crop-" + mat)
            and b.get("pos") == list(crop_cell) for b in blocks)
        inv_post = inventory_of(pol.state(bot))
        seed_post = (inv_post.get("game:" + seed_code, 0)
                     + inv_post.get(seed_code, 0))
        ok = aok and crop_present
        detail = ("sow %s on %s -> %s | last_action_ok=%s crop_present=%s"
                  % (crop_code, job.target, adetail, la.get("Ok"),
                     crop_present))
        return ok, detail, measured, \
            {"last_action": {k: la.get(k) for k in ("Name", "Ok", "Msg")},
             "approach_attempts": attempts}, \
            {"crop_present": crop_present,
             "crop_cell": list(crop_cell),
             "seed_precondition": seed_have,
             "seed_after": seed_post,
             "seed_consumed": seed_post < seed_have,
             "api_gap": ("1.22 composite sow does not consume the seed "
                         "(engine placement is not exposed)" if not
                         seed_post < seed_have else None)}

    # cell-targeted jobs (2026-10-06 campaign): a chop, or a mine that
    # names its own cell instead of a world resource - one fixed cell,
    # approach + engine verdict + measured drop
    if job.type == "chop" or (job.type == "mine" and job.at):
        return _cell_break(pol, bot, wm, job, run)

    # resource-targeted jobs: the target cell is the resource's
    # representative cell (measured world fact, not model output)
    rec = wm.resources.get(job.source) if job.type in (
        "mine", "harvest", "pickup") else None
    if job.type in ("mine", "harvest", "pickup"):
        if rec is None:
            return (False, "resource %s vanished from the model" % job.source,
                    measured, {}, {"block_gone": None,
                                   "measured": measured})
        need = job.quantity or 1
        # 2026-10-05: the quantity loop. A cluster holds more blocks
        # than one approach+act pair, so walk the cluster's cells until
        # `need` are down or the cluster is exhausted; the oracle
        # reports the shortfall (a 3-of-103 job is an honest 3-of-103,
        # never a "done").
        # WALK ACTUALLY-EXPOSED CELLS (2026-10-05 v5, the failed hut run):
        # re-derive the target set at execution time from a FRESH scan -
        # a cell is mineable only if its layer directly above is air RIGHT
        # NOW. The scan-time mineable subset (worldmodel) resolved a buried
        # pocket's interior here (all cells roofed) and mined 0 of 139;
        # the exposed top cells sit around the build site, so the fresh
        # scan is centred on the site (and the resource's bbox). Sorting by
        # distance makes the bot dig its local area first; mining a top
        # cell exposes the one below, and the driver re-scans on each
        # (re-)run so columns dig deeper. Falls back to the scan-time
        # subset if the fresh scan finds nothing.
        target_mat = classify(rec.code)[1]
        cells = _fresh_exposed(pol, bot, rec, wm, target_mat)
        if not cells:
            cells = list(rec.mineable_cells) if rec.mineable_cells \
                else list(rec.cells)
        # walk order (2026-10-07): TOP-DOWN before nearest. The
        # distance-only order sent the bot to a hollow's exposed FLOOR
        # cells (air above them) and left it stranded 2+ below the rim
        # (two hut-build aborts: 5 and 6 mined, no walk-out). Top-down
        # mines the rim/surface first, so the bot's feet stay at most
        # one step below the current surface: the way it came down is
        # the way it climbs out.
        bp = tuple(pol.state(bot)["Bot"]["Pos"])
        cells.sort(key=lambda c: (-c[1], abs(c[0] - bp[0]) + abs(c[2] - bp[2])))
        # the mine path needs a tool (granite is tier 2) - EXCEPT
        # hand-minable material: no harness privilege where the world
        # gives none (the honest survival path)
        st0 = pol.state(bot)
        b0 = st0.get("Bot") or {}
        tool_codes = set()
        for k in ("RightHand", "LeftHand"):
            it = b0.get(k)
            if it and it.get("Code"):
                tool_codes.add(it["Code"])
        for it in (b0.get("Backpack") or []):
            if it and it.get("Code"):
                tool_codes.add(it["Code"])
        has_tool = any((t or "").startswith(
            ("pickaxe", "shovel", "axe", "hoe")) for t in tool_codes)
        if job.type == "mine" and not has_tool and \
                classify(rec.code)[1] not in HAND_MINABLE:
            tr = pol.cmd("give", ["pickaxe-iron", "1"], bot)
            detail = ("%s %s -> gave pickaxe-iron ok=%s; "
                      % (job.type, rec.code, bool(tr.get("Ok"))))
        else:
            detail = "%s %s -> " % (job.type, rec.code)
        cmd_name = {"mine": "mine", "harvest": "harvestcrop"}.get(job.type)
        mined, parts = 0, []
        last_la, last_attempts = {}, []
        wedged_rescues = 0  # budget: 4 hard-resets per mine job

        def _in_site(c):
            # a hole in the footprint is a hole in the floor - never
            # mine inside (or at the edge of) a declared build site
            for f in wm.fixtures.values():
                if f.kind == "build-site" and f.cell:
                    ox, oz = f.cell[0], f.cell[2]
                    if ox - 1 <= c[0] <= ox + 6 and oz - 1 <= c[2] <= oz + 6:
                        return True
            return False

        def _exposed(c):
            # only the surface is directly mineable: a buried cell's
            # top must be walkable
            a = [c[0], c[1] + 1, c[2]]
            ab = pol.cell_blocks(bot, tuple(a), pad=0) or []
            for b in ab:
                if b.get("pos") == a:
                    code = b.get("code") or ""
                    # 2026-10-10: grass and water are NON-blocking in
                    # the engine (the "*-free" codes; the bot stands in
                    # them and mines straight through). Counting them
                    # solid marked nearly every soil cell on the
                    # grassy plateau as "buried" (14/139 mined).
                    if code == "game:air" or code.endswith("-free") \
                            or "water" in code:
                        continue
                    return False
            return True

        max_y_seen = int(pol.state(bot)["Bot"]["Pos"][1])
        # v6 (2026-10-05): RE-TARGET DURING the job. v5's cell list was
        # sorted by the START position; once the few nearest were mined
        # the bot walked to far list cells while ignoring the ones that
        # became exposed beside it, and stalled at 3 of 139. Re-scan every
        # few iterations for cells CURRENTLY exposed near the bot's
        # current position (nearest first): it keeps digging its local
        # area instead of wandering. `tried` avoids revisits; a bounded
        # attempt count stops infinite churn. Mining still yields ~1 block
        # per column (the self-guard forbids digging one's own support),
        # so local density is what the re-targeting buys.
        tried = set()
        cells_tried = 0
        # (2026-10-07) 2:1 attempt budget: a 1:1 budget exhausted on
        # buried/stale cells before the top-down re-scan found enough
        # genuinely exposed ones (31 of 99 mined, job dead). Each try
        # is cheap when it fails fast, and the re-scan is what finds
        # the fresh surface as the bot digs.
        max_cells_tried = need * 2 + 80
        scan_every = 3
        iters_since_scan = 0
        while mined < need and cells_tried < max_cells_tried:
            iters_since_scan += 1
            if iters_since_scan >= scan_every or not cells:
                iters_since_scan = 0
                bp2 = tuple(pol.state(bot)["Bot"]["Pos"])
                fresh = _fresh_exposed(pol, bot, rec, wm, target_mat)
                cells = [c for c in fresh if c not in tried]
                # top-down before nearest (2026-10-07): same rule as the
                # initial sort - the rim before the pit floor
                cells.sort(key=lambda c: (-c[1], abs(c[0] - bp2[0]) +
                           abs(c[2] - bp2[2])))
            if not cells:
                break
            cell = cells.pop(0)
            tried.add(cell)
            cells_tried += 1
            if mined >= need:
                break
            if _in_site(cell):
                parts.append("%s:site" % (cell,))
                continue
            if not _exposed(cell):
                parts.append("%s:buried" % (cell,))
                continue
            # self-guard (2026-10-05 incident): never mine the bot's own
            # body cell or its support cell - digging out one's own
            # foundation is how the bot ended up buried in solid soil
            posn = pol.state(bot)["Bot"]["Pos"]
            feet = (int(posn[0]), int(posn[1]), int(posn[2]))
            if tuple(cell) in (feet, (feet[0], feet[1] - 1, feet[2]),
                               (feet[0], feet[1] + 1, feet[2])):
                parts.append("%s:own" % (cell,))
                continue
            # staleness is MATERIAL-based, not code-based: a cluster
            # groups same-material cells that may carry different
            # codes (soil-low-normal vs -none) - the code comparison
            # false-"already-gone"d every cell (run 2026-10-05)
            bs0 = pol.cell_blocks(bot, tuple(cell), pad=0) or []
            code0 = next((b.get("code") for b in bs0
                          if b.get("pos") == list(cell)), None)
            if code0 is None or code0 == "game:air":
                parts.append("%s:gone" % (cell,))
                continue
            pre = inventory_of(pol.state(bot))
            # 13.6 step 1: APPROACH resolution (per cell). goto and
            # approach are separate concepts: a mine job means "interact
            # successfully with the target block" - for an occupied
            # solid block the valid destinations are the neighbouring
            # walkable cells. The driver walks the candidates and stops
            # on a definitive engine verdict.
            solid = [b["pos"] for b in pol.cell_blocks(bot, cell, pad=2)
                     if (b.get("code") or "") != "game:air"]
            from_pos = tuple(pol.state(bot)["Bot"]["Pos"])

            def _goto(c):
                return v5.goto_wait(pol, bot, c, timeout=25)

            def _act():
                # the CommandResult verdict is IMMEDIATE and DEFINITIVE:
                # a validation refusal (no path / out of range / target
                # gone) never records a LastAction - waiting 45 s for
                # one was the 2026-10-05 12-minute stall.
                r = pol.cmd(cmd_name, [str(cell[0]), str(cell[1]),
                                       str(cell[2]), "true"], bot)
                if r.get("Ok") is False:
                    return {"ok": False,
                            "last_action": {"Name": cmd_name,
                                             "Ok": False,
                                             "Msg": r.get("Message") or ""}}
                # accepted: poll the ORACLE (the block) and the record;
                # the LastAction is a hint, the block-gone is the proof
                t_a = time.time()
                la2 = {}
                while time.time() - t_a < 60:
                    time.sleep(2)
                    st2 = pol.state(bot)
                    la2 = st2.get("LastAction") or {}
                    if la2.get("Name") in (cmd_name, job.type) \
                            and la2.get("Ok") is not None:
                        break
                    bs = pol.cell_blocks(bot, tuple(cell), pad=0) or []
                    if not any(b.get("pos") == list(cell) and
                               (b.get("code") or "") != "game:air"
                               for b in bs):
                        break  # the block is gone - the work is done
                gone_now = not any(
                    (b.get("code") or "") != "game:air" and
                    b.get("pos") == list(cell)
                    for b in (pol.cell_blocks(bot, tuple(cell), pad=0) or []))
                return {"ok": gone_now or la2.get("Ok") is True,
                        "last_action": la2}

            if cmd_name is not None:
                aok, adetail, attempts, la = r2approach.approach(
                    _goto, _act, from_pos, cell, solid)
            else:
                # pickup targets an ITEM entity, not a block cell -
                # v5's item-entity approach stands
                res = v5.execute(pol, bot, "pickup_item", cell, base,
                                 "pickup")
                la = pol.state(bot).get("LastAction") or {}
                aok = bool(res.get("ok"))
                adetail = ("pickup -> %s" % (res.get("msg") or
                                             la.get("Msg") or ""))
                attempts = []
            last_la, last_attempts = la, attempts
            # the drop lands in the cargo ASYNCHRONOUSLY (~8 s, run 12)
            # - poll for it instead of a fixed sleep; the block-gone
            # check and the cargo diff are separate oracles
            blocks = pol.cell_blocks(bot, cell)
            gone = bool(blocks) and not any(
                b.get("code") == rec.code and b.get("pos") == list(cell)
                for b in blocks)
            post = {}
            for _ in range(9):  # up to ~18 s for the cargo registration
                time.sleep(2)
                post = inventory_of(pol.state(bot))
                if any(post.get(k, 0) > pre.get(k, 0)
                       for k in set(pre) | set(post)):
                    break
            for k in set(pre) | set(post):
                if post.get(k, 0) > pre.get(k, 0):
                    measured[k] = measured.get(k, 0) + \
                        (post.get(k, 0) - pre.get(k, 0))
            if aok and gone:
                mined += 1
                parts.append("%s:down" % (cell,))
            else:
                parts.append("%s:failed(ok=%s gone=%s)"
                             % (cell, la.get("Ok"), gone))

            # WEDGE GUARD (2026-10-05 incident): one box scan around the
            # bot. Two fatal states abort the walk with an honest
            # diagnosis instead of a 12-minute silent stall: (1) the
            # bot's own body cells report solid - it is buried; (2) its
            # feet fell >=2 blocks below the highest it reached in this
            # job - it is at the bottom of a hole it cannot climb out
            # of (the VS agent climbs 1, not 2).
            posn = pol.state(bot)["Bot"]["Pos"]
            fy = int(posn[1])
            max_y_seen = max(max_y_seen, fy)

            # EMBODIMENT GUARD (2026-10-05): classify the body's relation
            # to the solid world. A SUNK bot (feet in the top soil layer,
            # head clear) is recoverable - recheck_and_recover re-gotos
            # the correct stand height and the loop continues. A bot whose
            # head is solid (fully buried) or that is TRAPPED is not:
            # abort with an honest diagnosis instead of a silent stall.
            rec_ok, rec_state, rec_detail = recheck_and_recover(
                pol, bot, "after %d mined" % mined)
            if not rec_ok:
                # 2026-10-10: rescue before aborting - the bot in a
                # 2-deep hollow is unclimbable, but the haul is safe
                # in the inventory: hard-reset the body, keep digging.
                if wedged_rescues < 4:
                    nb = _rescue_wedged_bot(pol, bot, measured)
                    if nb:
                        wedged_rescues += 1
                        print("[mine] rescue %d/4: bot wedged (%s) "
                              "- respawn+re-give the haul, continue"
                              % (wedged_rescues, rec_state),
                              flush=True)
                        bot = nb
                        if botref:
                            botref[0] = nb
                        max_y_seen = int(pol.state(bot)["Bot"]["Pos"][1])
                        continue
                return (False,
                        detail + (" | ABORT: %s (after %d mined)"
                                  % (rec_detail, mined)),
                        measured, {"last_action": last_la},
                        {"block_gone": mined >= 1, "measured": measured,
                         "mined": mined, "required": need,
                         "wedge": rec_state})
            if max_y_seen - fy >= 2:
                # descended 2+ blocks - but that is normal on hilly
                # terrain. Only a bot with NO climbable neighbour is
                # truly stuck in a deep hollow (the VS agent climbs 1,
                # not 2). A 1-block-up neighbour means open ground.
                up_ok, up_detail = climb_out_possible(pol, bot)
                if not up_ok:
                    if wedged_rescues < 4:
                        nb = _rescue_wedged_bot(pol, bot, measured)
                        if nb:
                            wedged_rescues += 1
                            print("[mine] rescue %d/4: bot in deep "
                                  "hollow - respawn+re-give, continue"
                              % (wedged_rescues,), flush=True)
                            bot = nb
                            if botref:
                                botref[0] = nb
                            max_y_seen = int(
                                pol.state(bot)["Bot"]["Pos"][1])
                            continue
                    return (False,
                            detail + (" | ABORT: bot in a deep hollow "
                                      "(feet y%d, max y%d; %s) after %d "
                                      "mined"
                                      % (fy, max_y_seen, up_detail, mined)),
                            measured, {"last_action": last_la},
                            {"block_gone": mined >= 1, "measured": measured,
                             "mined": mined, "required": need,
                             "wedge": "deep-hollow"})
        # A shortfall is NOT automatically fatal (2026-10-05, the failed
        # hut run). The loop got here either by reaching `need` or by
        # exhausting the cluster's mineable surface (a wedge aborts inside
        # the loop and returns before this point). An honest exhaustion
        # that still mined at least one block is a SOFT SUCCESS: the
        # build_plan's material preflight is the authoritative gate for
        # whether the total inventory is enough. Parking the whole
        # shortfall on one cluster had made a 74/139 partial read as a
        # fatal goal abort before the build's preflight could decide.
        reached = mined >= need
        partial = (not reached) and (mined >= 1)
        ok = reached or partial
        detail += (" | %d of %d mined%s (%s)"
                   % (mined, need,
                      "" if reached
                      else (" (surface exhausted)" if partial else ""),
                      ", ".join(parts[:8])))
        if len(parts) > 8:
            detail += " ... (+%d more cells)" % (len(parts) - 8)
        return ok, detail, measured, \
            {"last_action": {k: last_la.get(k) for k in
                             ("Name", "Ok", "Msg")},
             "approach_attempts": last_attempts,
             "cells_tried": len(parts)}, \
            {"block_gone": mined >= 1, "measured": measured,
             "mined": mined, "required": need,
             "reached": reached, "partial": partial}

    if job.type == "build":
        fix = wm.fixtures.get(job.target)
        if fix is None:
            return (False, "site %s unknown" % job.target, measured, {},
                    {"blocks": None})
        n = job.quantity or 1
        item = GIVE_ITEM.get(job.material, job.material)
        # the ring: N cells around the site, one layer ABOVE the site's
        # base cell (the ground layer is solid; the layer above is
        # where a platform goes - safe for both fixture kinds: the
        # farmland base sits at ground level, the build-site base at
        # the walkable layer)
        cell = fix.cell
        ring_y = cell[1] + 1
        RING = [(0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1),
                (-1, 0), (-1, 1), (2, 1), (2, 0), (2, -1), (1, -2),
                (0, -2), (-1, -2), (-2, -1), (-2, 0), (-2, 1), (-2, 2)]
        prefix = MATERIAL_BLOCK.get(job.material, job.material)

        def _count():
            boxes = pol.cell_blocks(bot, (cell[0], ring_y, cell[2]),
                                    pad=4) or []
            return sum(1 for b in boxes
                       if (b.get("code") or "").replace("game:", "")
                       .startswith(prefix))

        pre = _count()
        # per-attempt verification (run 29-1 finding): the engine
        # SILENTLY refuses a place into a cell the bot occupies, while
        # the place command still reports ok=True - so a reported-ok
        # placement is not trusted: the cell is re-scanned after each
        # attempt and only a LANDED block counts. Occupied/pre-filled
        # cells are skipped to the next ring cell (and the failure
        # message says how many skips - a second build over an existing
        # platform runs out of empty ring cells, and the agent should
        # be told that, not "build failed")
        used, placed, parts = set(), 0, []
        idx, attempts, skips = 0, 0, 0
        while placed < n and attempts < 3 * n:
            attempts += 1
            dx, dz = RING[idx % len(RING)]
            idx += 1
            c = [cell[0] + dx, ring_y, cell[2] + dz]
            if tuple(c) in used:
                continue
            # keep the bot off the platform (09-29 finding): it paths
            # ACROSS its own placed blocks and ends up standing on a
            # ring cell, where the engine silently refuses the place
            # (the phantom(ok=True) case). If it is on the platform
            # layer, drop it to the ground on the far side first.
            bp_now = (pol.state(bot).get("Bot") or {}).get("Pos") or [0, 0, 0]
            if bp_now[1] >= ring_y:
                v5.goto_wait(pol, bot, (cell[0] - 4, 3, cell[2]))
            occ = [b for b in (pol.cell_blocks(bot, tuple(c), pad=0)
                               or [])
                   if b.get("pos") == c]
            if occ:  # filled (or the bot is in the way) - next cell
                skips += 1
                continue
            res = v5.execute(pol, bot, "place_block", c, base, "build",
                             buildblock=item)
            time.sleep(1)
            chk = [b for b in (pol.cell_blocks(bot, tuple(c), pad=0)
                               or [])
                   if b.get("pos") == c and
                   (b.get("code") or "").replace("game:", "")
                   .startswith(prefix)]
            if chk:
                placed += 1
                used.add(tuple(c))
                parts.append("%s:landed" % (c,))
            else:
                parts.append("%s:phantom(ok=%s)" % (c, res.get("ok")))
        post = _count()
        delta = post - pre
        la = (pol.state(bot).get("LastAction") or {})
        ok = (placed == n) and (delta >= n)
        msg = ("build %s x%d at %s -> placed=%d/%d delta=%d %s"
               % (item, n, job.target, placed, n, delta, parts))
        if not ok and placed < n:
            msg += (" [ring: %d attempts, %d occupied/phantom skips -"
                    " the site may already carry a platform; build at"
                    " a fresh site or clear the ring first]"
                    % (attempts, skips))
        return ok, msg, {}, \
            {"last_action": {k: la.get(k) for k in
                             ("Name", "Ok", "Msg")},
             "placed": placed}, \
            {"pre": pre, "post": post, "delta": delta,
             "blocks": placed}

    if job.type == "build_plan":
        # a whole plan file, erected in phases (13.11). Each phase is
        # placed from the layer BELOW - the bot climbs its own work:
        # floor from the outside (same-layer, the proven 17:37
        # geometry), walls standing on the floor (at foot level), roof
        # standing on the walls. Per-cell verification (the phantom
        # rule: a reported ok is not a placed block), bounded
        # attempts, honest per-cell report.
        import r2.buildplans as _bp
        plan = _bp.load_plan(os.path.join(REPO, "builds",
                                          job.plan + ".json"))
        fix = wm.fixtures.get(job.target)
        if fix is None:
            return (False, "site %s unknown" % job.target, measured, {},
                    {"cells": None})
        origin = list(fix.cell)
        w, d = plan.footprint

        # material preflight (2026-10-05): 103 phantom place attempts
        # with an empty cargo are not a mission - check the cargo once,
        # before ANY cell, and say what is missing.
        inv_now = normalize_inv(inventory_of(pol.state(bot)))
        short = {m: (q, inv_now.get(m, 0))
                 for m, q in plan.materials.items()
                 if inv_now.get(m, 0) < q}
        if short:
            return (False, "build-plan %s: material short - %s (the "
                    "mine jobs must land first)"
                    % (job.plan,
                       ", ".join("%s need %d have %d"
                                 % (m, q, h)
                                 for m, (q, h) in
                                 sorted(short.items()))),
                    measured, {}, {"cells": None})

        def _item(m):
            # dirt: use the soil-<variant> the bot actually carries
            # (a soil-low-normal block drops soil-low-none - but another
            # fertility cluster drops its own code, and the place
            # command matches the exact block). 2026-10-05.
            if m == "dirt":
                have = {}
                b = (pol.state(bot).get("Bot") or {})
                for k in ("RightHand", "LeftHand"):
                    it = b.get(k)
                    if it and (it.get("Code") or "").startswith("soil"):
                        have[it["Code"]] = have.get(it["Code"], 0) + \
                            (it.get("Qty") or 1)
                for it in (b.get("Backpack") or []):
                    if it and (it.get("Code") or "").startswith("soil"):
                        have[it["Code"]] = have.get(it["Code"], 0) + \
                            (it.get("Qty") or 1)
                if have:
                    return sorted(have, key=lambda c: -have[c])[0]
            return GIVE_ITEM.get(m, m)

        def _prefix(m):
            return MATERIAL_BLOCK.get(m, m)

        def _has(mat, cell):
            bs = pol.cell_blocks(bot, tuple(cell), pad=0) or []
            return any(b.get("pos") == list(cell) and
                       (b.get("code") or "").replace("game:", "")
                       .startswith(_prefix(mat)) for b in bs)

        def _bot_pos():
            return ((pol.state(bot).get("Bot") or {}).get("Pos")
                    or [0, 0, 0])

        def _emb():
            # the body's relation to the solid world (09-29, the
            # block-in-bot-cell incident): raw position is
            # innocent-looking; the FAILURE is the relation between
            # the position and the solidity of its own cells.
            bp = _bot_pos()
            x, y, z = (int(p) for p in bp)
            bs = pol.cell_blocks(bot, (x, y, z), pad=2) or []
            cm = {tuple(b["pos"]): b.get("code") for b in bs}
            return _embodiment_fn(bp, cm)

        def _standable(c):
            # a standing candidate must be OPEN at the feet (a goto TO
            # a solid cell walks the bot into it - the pathfinder
            # accepts goals inside blocks, which is how the bot got
            # embedded 09-29) and supported a layer below when above
            # the walking layer (the bot stands on our placed blocks).
            # "Open" = no SOLID block: vegetation (tallgrass & co.) is
            # walk-through - the bot crosses the grassy pocket all day
            # (run 16: a lone tallgrass in the only outside neighbour
            # read as "occupied" and killed the floor). Support at
            # ground level is the terrain itself, not a block (run 14);
            # above that, only a SOLID block below counts (grass is
            # not a ledge).
            bs = pol.cell_blocks(bot, tuple(c), pad=0) or []
            if any(b.get("pos") == list(c) and is_solid(b.get("code"))
                   for b in bs):
                return False
            if c[1] <= origin[1]:
                return True
            below = [c[0], c[1] - 1, c[2]]
            bs2 = pol.cell_blocks(bot, tuple(below), pad=0) or []
            return any(b.get("pos") == list(below)
                       and is_solid(b.get("code")) for b in bs2)

        def _inside(x, z):
            return (origin[0] <= x < origin[0] + w and
                    origin[2] <= z < origin[2] + d)

        # PRE-FLIGHT: the body must be clear before ANY placement,
        # and for a footprint build it must be OUTSIDE the footprint
        # - a floor phase started with the bot inside builds a wall
        # around it. Structural failures abort; they are not
        # retryable (no amount of re-trying a target fixes a body
        # that cannot stand).
        st, det = _emb()
        if st != "OK":
            return (False, "structural pre-flight: %s - %s (rescue: "
                    "dig the bot's cell out / open a corridor, then "
                    "re-run - the mission is idempotent)" % (st, det),
                    measured, {}, {"cells": None})
        bp0 = _bot_pos()
        if (origin[0] <= bp0[0] < origin[0] + w and
                origin[2] <= bp0[2] < origin[2] + d):
            ev = [origin[0] - 2, origin[1], origin[2] - 2]
            if not goto_arrive(pol, bot, ev):
                st, det = _emb()
                if st != "OK":
                    return (False, "structural pre-flight: bot inside "
                            "the footprint and cannot walk out: %s - %s"
                            % (st, det), measured, {}, {"cells": None})
                return (False, "pre-flight: bot inside the footprint "
                        "and the walk-out failed; aborting rather than "
                        "building the floor around it", measured, {},
                        {"cells": None})

        landed = 0
        total = 0
        parts = []
        stuck = 0      # 2026-10-07: consecutive body-OK goto failures
        rescues = 0    # hard-resets performed this run (bounded)
        for phase, cells in plan.phases(origin):
            for cell, mat in cells:
                total += 1
                if _has(mat, cell):
                    landed += 1
                    parts.append("%s%s:pre" % (phase, cell))
                    print("[build] %s %s: pre (already present, skip)"
                          % (phase, cell), flush=True)
                    continue
                L = cell[1]  # the block's layer; the bot's feet go to L
                # all 4 horizontal neighbours are candidates -
                # _standable is the whole rule. (09-29: there used to
                # be a floor-only filter keeping just the OUTSIDE
                # neighbours. Wrong for cells with an interior side:
                # the interior neighbour at ground level is open
                # ground - the floor is built at the bot's feet, not
                # under it. The filter left a lone tallgrass cell as
                # the only candidate and killed run 16.)
                cands = [[cell[0] - 1, L, cell[2]],
                         [cell[0] + 1, L, cell[2]],
                         [cell[0], L, cell[2] - 1],
                         [cell[0], L, cell[2] + 1]]
                if phase != "floor":
                    # elevated: neighbours with support a layer down
                    # come first (the plan's own earlier phases)
                    def _supported(c):
                        below = [c[0], L - 1, c[2]]
                        bs = pol.cell_blocks(bot, tuple(below),
                                             pad=0) or []
                        return any(b.get("pos") == list(below)
                                   and is_solid(b.get("code"))
                                   for b in bs)
                    cands.sort(key=lambda c: 0 if _supported(c) else 1)
                # a candidate with a block AT foot level is not a
                # ledge (09-29: the previous phase's own blocks are
                # the candidates - standing on one embeds the bot)
                cands = [c for c in cands if _standable(c)]
                if not cands:
                    # (2026-10-05 wedge fix) the target's whole foot-level ring
                    # is filled, so no horizontal approach at its own level
                    # exists. Try the levels adjacent to the target instead:
                    #   L-1: stand on the level BELOW and place UP - how a wall
                    #         goes on a floor (stand on the floor / the border,
                    #         place the wall one over + one up).
                    #   L+1: stand on top of a filled neighbour and place DOWN
                    #         - fills the interior cell of a closing floor.
                    for lvl in (L - 1, L + 1):
                        alt = [[cell[0] - 1, lvl, cell[2]],
                               [cell[0] + 1, lvl, cell[2]],
                               [cell[0], lvl, cell[2] - 1],
                               [cell[0], lvl, cell[2] + 1]]
                        alt = [c for c in alt if _standable(c)]
                        if not alt:
                            continue
                        alt.sort(key=lambda c: abs(c[0] - cell[0])
                                 + abs(c[2] - cell[2]))
                        cands = alt
                        print("[build] %s %s: no ledge at level %d -> "
                              "stand at level %d: %s"
                              % (phase, cell, L, lvl, cands[0]),
                              flush=True)
                        break
                if not cands:
                    # 2026-10-10 reach-aware stand search (the roof fix):
                    # the 4-neighbour rings at L-1/L/L+1 only find ledge
                    # positions at the target's own level - a roof 3-4
                    # blocks above the floor had NO candidate a
                    # ground-level bot (climb 1, not 3) can occupy, so
                    # the run died "goto stuck" on its own wall (the
                    # hut-flat 44/54). A stand position is any cell
                    # from which the target is within placement reach:
                    # horizontal <= 2, target up to 3 above the feet
                    # (the VS reach window is larger; this is the
                    # conservative corner that covers overhead roof
                    # placement from inside or from a low rim). Head
                    # room is checked too - the bot's head cell must
                    # be open or it is standing in a filled cell.
                    reach = []
                    for sx in range(cell[0] - 2, cell[0] + 3):
                        for sz in range(cell[2] - 2, cell[2] + 3):
                            for sy in range(L - 3, L + 2):
                                c = [sx, sy, sz]
                                if c == list(cell):
                                    continue
                                if not _standable(c):
                                    continue
                                above = [sx, sy + 1, sz]
                                bs3 = pol.cell_blocks(bot, tuple(above),
                                                      pad=0) or []
                                if any(b.get("pos") == list(above)
                                       and is_solid(b.get("code"))
                                       for b in bs3):
                                    continue
                                reach.append(c)
                    # ground-level positions first (walk-in through the
                    # door, not a climb onto the wall), then nearer
                    # targets, then closer to where the bot already is
                    reach.sort(key=lambda c: (L - c[1],
                                              abs(c[0] - cell[0]) +
                                              abs(c[2] - cell[2]),
                                              abs(c[0] - int(bp0[0])) +
                                              abs(c[2] - int(bp0[2]))))
                    if reach:
                        print("[build] %s %s: no ledge at levels %d/%d/"
                              "%d -> reach-aware stand %s (target %d "
                              "above feet)"
                              % (phase, cell, L - 1, L, L + 1,
                                 reach[0], L - reach[0][1]),
                              flush=True)
                        cands = reach
                if not cands:
                    return (False,
                            "structural: no standable candidate for "
                            "%s%s (levels %d/%d/%d and the reach "
                            "window -2..+2 x 1 below..3 above are all "
                            "unusable) - the plan geometry or a "
                            "neighbouring structure leaves no ledge"
                            % (phase, cell, L - 1, L, L + 1),
                            measured, {}, {"cells": None})
                placed_here = False
                for cand in cands:
                    # position-verified: the bot must ACTUALLY be on
                    # the candidate before a place is issued (a
                    # stale LastAction made the old goto_wait lie)
                    if not goto_arrive(pol, bot, cand):
                        st, det = _emb()
                        print("[build] %s %s: goto to %s failed (body %s)"
                              % (phase, cell, cand, st), flush=True)
                        if st != "OK":
                            return (False, "structural: standing goto "
                                    "for %s%s failed and the body is %s "
                                    "(- %s)" % (phase, cell, st, det),
                                    measured, {}, {"cells": None})
                        # 2026-10-07 stuck rescue: three consecutive
                        # body-OK goto failures means the pathfinder
                        # wedged (a 1-wide roof walk; a stale scan
                        # that routes the bot into its own placed
                        # block). No further goto in this run can
                        # succeed, so hard-reset the body: despawn +
                        # respawn + re-give the shortfall (the
                        # external-supply give is already sanctioned;
                        # the pre-check makes over-giving harmless).
                        if stuck >= 2 and rescues < 8:
                            rescues += 1
                            stuck = 0
                            print("[build] rescue %d/8: bot wedged "
                                  "(body %s) - despawn+respawn+re-give"
                                  % (rescues, st), flush=True)
                            # 2026-10-10: the empty-args despawn was a
                            # NO-OP since the 4ffc4a0 contract - the
                            # 'rescue' never actually removed the wedged
                            # body (it just stacked replacements on top;
                            # part of the 18-bot pile-up). Explicit id.
                            pol.cmd("despawn", [str(bot)], bot)
                            time.sleep(3)
                            r2 = v5.http_json(pol.base + "/polis/command",
                                              {"cmd": "spawn", "args": [],
                                               "context": {"playerUid":
                                                           pol.uid}})
                            nb = (r2.get("Data") or {}).get("id")
                            if not nb:
                                return (False, "rescue failed: spawn "
                                        "returned no bot", measured, {},
                                        {"cells": None})
                            time.sleep(6)
                            bot = nb
                            if botref:
                                botref[0] = nb
                            inv_now = normalize_inv(
                                inventory_of(pol.state(bot)))
                            for m2, (q2, h2) in sorted(
                                    {m3: (q3, inv_now.get(m3, 0))
                                     for m3, q3 in plan.materials.items()
                                     if inv_now.get(m3, 0) < q3}
                                    .items()):
                                pol.cmd("give", [GIVE_ITEM.get(m2, m2),
                                                 str(q2 - h2)], bot)
                                time.sleep(1)
                            print("[build] rescue done: new bot %s"
                                  % nb, flush=True)
                            break  # re-approach the same cell fresh
                        stuck += 1
                        continue
                    # DIRECT place (09-29): the harness command is
                    # async (returns "placing..."); the result is read
                    # from the WORLD (re-scan), the action record is
                    # diagnostic only. v5.execute's LastAction poll
                    # can read stale and burns its 90 s budget per
                    # cell (that is what made the mission crawl).
                    pol.cmd("place", [_item(mat)] + [str(c) for c in cell],
                            bot, timeout=120)
                    t_cell = time.time()
                    while time.time() - t_cell < 12:
                        time.sleep(1)
                        if _has(mat, cell):
                            break
                    la = (pol.state(bot).get("LastAction") or {})
                    print("[build] %s %s: %s" % (phase, cell,
                                                 "landed" if _has(mat, cell)
                                                 else "attempt(%s)" % la.get("Msg", "?")),
                          flush=True)
                    if _has(mat, cell):
                        # BIDIRECTIONAL oracle: the target gained its
                        # block AND the body is still clear. The
                        # engine's place rejection is unreliable in
                        # BOTH directions (a phantom ok, and a block
                        # appearing in the bot's own cell) - this is
                        # the check that catches an embedding the
                        # instant it happens
                        st, det = _emb()
                        if st != "OK":
                            return (False, "structural: place into %s "
                                    "landed but the body ended %s "
                                    "(- %s) - a block in the bot's own "
                                    "cell; the target cell must be "
                                    "replaced after rescue" % (cell, st, det),
                                    measured, {}, {"cells": None})
                        landed += 1
                        placed_here = True
                        parts.append("%s%s:landed" % (phase, cell))
                        # 2026-10-07: settle before the next cell's
                        # candidate scan - a scan issued immediately
                        # after a place can read the pre-place chunk
                        # snapshot and treat a just-placed block as
                        # air (that is what fed the wedge above).
                        time.sleep(3)
                        stuck = 0
                        break
                    parts.append("%s%s:attempt(%s)"
                                 % (phase, cell, la.get("Msg", "?")))
        # oracle: every cell present, and the door (entry) still open
        present = 0
        for (dx, dy, dz), mat in plan.blocks:
            cell = [origin[0] + dx, origin[1] + dy, origin[2] + dz]
            if _has(mat, cell):
                present += 1
        ex, ez = plan.entry[0], plan.entry[1]
        # the door oracle checks the whole OPENING (layers 1..
        # door_height): the floor under the door is a threshold, the
        # lintel above it and the roof over it are architecture
        door_open = True
        for h in range(1, plan.door_height + 1):
            door = [origin[0] + ex, origin[1] + h, origin[2] + ez]
            door_bs = pol.cell_blocks(bot, tuple(door), pad=0) or []
            if any(b.get("pos") == list(door) for b in door_bs):
                door_open = False
        la = (pol.state(bot).get("LastAction") or {})
        ok = (present == plan.total_blocks()) and door_open
        msg = ("build-plan %s at %s -> present=%d/%d door_open=%s %s"
               % (job.plan, job.target, present, plan.total_blocks(),
                  door_open, parts[:12]))
        return ok, msg, {}, \
            {"last_action": {k: la.get(k) for k in
                             ("Name", "Ok", "Msg")},
             "landed": landed, "attempts_reported": len(parts)}, \
            {"present": present, "total": plan.total_blocks(),
             "door_open": door_open}

    if job.type == "place":
        fix = wm.fixtures.get(job.target)
        if fix is None:
            return (False, "site %s unknown" % job.target, measured, {},
                    {"site_filled": None})
        cell = fix.cell
        item = GIVE_ITEM.get(job.material, job.material)
        # 2026-10-07: the engine's place reach is 4.5 blocks (a
        # door-craft run failed with "out of range: 7.06 > 4.50" when
        # the bot placed from where it had finished crafting). Walk
        # to the nearest standable neighbour of the target first
        # (3-D ring + standability, the build executor's rules): for
        # a doorway the two AIR neighbours (outside/inside the
        # opening) both work, solid neighbours (the wall flanking
        # the door) are excluded, and above ground level a solid
        # support below the feet is required.
        L = cell[1]
        reached = None
        for level in (L, L - 1, L + 1):
            cands = []
            for dx, dz in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                c = (cell[0] + dx, level, cell[2] + dz)
                bs = pol.cell_blocks(bot, c, pad=0) or []
                if any(b.get("pos") == list(c) and is_solid(b.get("code"))
                       for b in bs):
                    continue
                if level > base[1]:
                    below = pol.cell_blocks(
                        bot, (c[0], c[1] - 1, c[2]), pad=0) or []
                    if not any(b.get("pos") == [c[0], c[1] - 1, c[2]]
                               and is_solid(b.get("code")) for b in below):
                        continue
                cands.append(c)
            for c in cands:
                if goto_arrive(pol, bot, c):
                    reached = c
                    break
            if reached:
                break
        if not reached:
            return (False, "place %s: no standable neighbour of %s "
                    "reachable" % (item, cell), measured, {},
                    {"site_filled": None})
        res = v5.execute(pol, bot, "place_block", cell, base, "build",
                         buildblock=item)
        time.sleep(2)
        filled = pol.site_filled(bot, tuple(cell))
        cond = wm.observe_fixture(job.target, filled,
                                  reason="oracle")
        la = pol.state(bot).get("LastAction") or {}
        ok = bool(res.get("ok")) and filled
        msg = ("place %s -> exec_ok=%s site_filled=%s oracle=%s" %
               (item, res.get("ok"), filled, cond))
        return ok, msg, measured, \
            {"last_action": {k: la.get(k) for k in
                             ("Name", "Ok", "Msg")},
             "exec_ok": res.get("ok")}, \
            {"site_filled": filled, "wm_condition": cond}

    if job.type == "craft":
        # 1.22.7 grid crafting (10-04 endogenous craft chain; the
        # 2026-10-06 shaped door recipe): the ENGINE'S GridRecipe
        # engine matches the bot's cargo and ConsumeInput consumes /
        # produces - the orchestrator only issues the command and
        # MEASURES the result as inventory deltas (ingredients
        # consumed, output gained). The pattern itself is engine-
        # side; what made the run safe was the pre-execution pattern
        # check (plancheck.check_craft_pattern) over the live recipe
        # table and the projected inventory.
        item = job.material
        runs = job.quantity or 1
        pre = inventory_of(pol.state(bot))
        r = pol.cmd("craft", [item], bot)
        la = {}
        t_a = time.time()
        # a validation rejection never records a LastAction - no point
        # polling (an accepted craft completes in well under the window)
        while r.get("Ok") is not False and time.time() - t_a < 60:
            la = pol.state(bot).get("LastAction") or {}
            if la.get("Name") == "craft" and la.get("Ok") is not None:
                break
            time.sleep(2)
        post = inventory_of(pol.state(bot))
        for k in set(pre) | set(post):
            d = post.get(k, 0) - pre.get(k, 0)
            if d:
                measured[k] = measured.get(k, 0) + d
        ok = bool(r.get("Ok")) and la.get("Ok") is True
        detail = ("craft %s x%d -> cmd_ok=%s last_action_ok=%s "
                  "measured=%s"
                  % (item, runs, r.get("Ok"), la.get("Ok"), measured))
        return ok, detail, measured, \
            {"cmd": "craft", "item": item, "runs": runs,
             "ok": r.get("Ok"),
             "last_action": {k: la.get(k) for k in ("Name", "Ok", "Msg")}}, \
            {"produced": {k: v for k, v in measured.items() if v > 0},
             "consumed": {k: v for k, v in measured.items() if v < 0},
             "measured": measured}

    if job.type in ("goto", "travel"):
        fix = wm.fixtures.get(job.target)
        cell = tuple(fix.cell) if fix else base
        g = v5.goto_wait(pol, bot, cell)
        return (bool(g.get("ok")), "goto %s -> %s" % (job.target,
                                                      g.get("msg")),
                measured, {"goto": g.get("msg")},
                {"arrived": bool(g.get("ok"))})
    if job.type == "wait":
        # a time valve: quantity is SECONDS (default 2). The crucible
        # chain (2026-10-07) uses it to wait out engine smelt progress
        # (a template parameter); a bare wait is the 2-s beat.
        secs = max(2, job.quantity or 2)
        time.sleep(secs)
        return True, "waited %ds" % secs, measured, {}, {"waited": secs}
    # knap (2026-10-10, J1 of the early-game ladder): chip stone items
    # on the knappingsurface block. The engine's KnappingRecipe table
    # resolves each `recipes` entry by output code or name; Lane A's
    # C# command validates range, the surface block and the cargo
    # material. Two engine facts (live-measured 2026-10-09):
    #   * the surface is CONSUMED: CompleteKnapToBot clears the block
    #     on completion - one surface block per chip, so each chip
    #     re-places the surface from cargo first;
    #   * the completion marker is the block going to AIR (the
    #     LastAction the action records at start is Ok=True - it
    #     cannot be the wait condition). The MEASURED inventory delta
    #     of the outputs is the oracle - never the command's ok.
    if job.type == "knap":
        mat = job.material or "flint"
        recipes = job.recipes or []
        if not job.at:
            return (False, "knap job has no surface cell (at)",
                    measured, {}, {})
        sx, sy, sz = [int(v) for v in job.at]
        cell = (sx, sy, sz)

        def _code_at(c):
            return (_cell_code(pol, bot, c) or "").replace("game:",
                                                           "", 1)

        # preflight: the chipping material in cargo (one per recipe -
        # one stone per surface) + a surface item per chip to place
        pre = inventory_of(pol.state(bot))

        def _inv_get(inv, c):
            return inv.get(c, 0) + inv.get("game:" + c, 0)

        runs = job.quantity or 1
        nchips = len(recipes) * runs
        need_mat = nchips
        need_surf = nchips
        if _inv_get(pre, mat) < need_mat or \
                _inv_get(pre, "knappingsurface") < need_surf:
            return (False,
                    "knap: need %d %s and %d knappingsurface "
                    "(one stone + one surface per chip), have %d / %d"
                    % (need_mat, mat, need_surf,
                       _inv_get(pre, mat),
                       _inv_get(pre, "knappingsurface")),
                    measured,
                    {"cell": cell},
                    {"material_have": _inv_get(pre, mat),
                     "surface_have": _inv_get(pre, "knappingsurface")})

        # the chips: per recipe x run - ensure surface, stand
        # adjacent, chip, wait for the block to go to air
        last = {}
        cmd_ok = True
        chip_msgs = []
        for _run in range(runs):
            for rname in recipes:
                if _code_at(cell) != "knappingsurface":
                    res = v5.execute(pol, bot, "place_block", cell,
                                     base, "build",
                                     buildblock="knappingsurface")
                    time.sleep(2)
                    if _code_at(cell) != "knappingsurface":
                        return (False,
                                "surface placement did not land at %s "
                                "(code=%s, exec=%s)"
                                % (cell, _code_at(cell),
                                   res.get("ok")),
                                measured,
                                {"cell": list(cell)},
                                {"surface_present": False})
                arrived = False
                for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    g = v5.goto_wait(pol, bot,
                                     (sx + dx, sy, sz + dz))
                    if g.get("ok"):
                        arrived = True
                        break
                if not arrived:
                    return (False, "knap: could not reach a cell "
                                   "adjacent to %s" % (cell,),
                            measured,
                            {"cell": list(cell)},
                            {"surface_present": True,
                             "arrived": False})
                r = pol.cmd("knap", [str(sx), str(sy), str(sz), rname],
                            bot)
                if r.get("Ok") is False:
                    cmd_ok = False
                    chip_msgs.append("%s: %s" % (rname,
                                                 r.get("Msg", "")))
                    continue
                # wait for the engine's completion marker: the
                # surface block goes to air (CompleteKnapToBot)
                t_a = time.time()
                code_now = _code_at(cell)
                while code_now == "knappingsurface" and \
                        time.time() - t_a < 180:
                    time.sleep(3)
                    code_now = _code_at(cell)
                    last = pol.state(bot).get("LastAction") or {}
                if code_now == "knappingsurface":
                    cmd_ok = False
                    chip_msgs.append("%s: still on the surface "
                                      "after 180s (last_action=%s)"
                                      % (rname, last.get("Msg")))
                elif code_now not in ("", None):
                    chip_msgs.append("%s: surface became %s "
                                      "(not air)" % (rname, code_now))
                else:
                    chip_msgs.append("%s: chipped (block cleared)"
                                      % rname)
        post = inventory_of(pol.state(bot))
        for k in set(pre) | set(post):
            d = post.get(k, 0) - pre.get(k, 0)
            if d:
                measured[k] = measured.get(k, 0) + d
        produced = {}
        for rname in recipes:
            produced[rname] = max(0, _inv_get(post, rname) -
                                  _inv_get(pre, rname))
        consumed = _inv_get(pre, mat) - _inv_get(post, mat)
        ok = cmd_ok and all(v >= runs for v in produced.values())
        detail = ("knap %s (x%d) on %s -> %s; produced=%s "
                  "consumed=%d"
                  % (recipes, runs, cell,
                     " | ".join(chip_msgs), produced, consumed))
        return ok, detail, measured, \
            {"cell": list(cell),
             "recipes": recipes, "runs": runs,
             "chips": chip_msgs,
             "last_action": {k: last.get(k)
                             for k in ("Name", "Ok", "Msg")}}, \
            {"produced": produced, "consumed": consumed,
             "measured": measured}
    # forage (2026-10-07, B1): the forageable-plant gather
    if job.type == "forage":
        return _forage(pol, bot, wm, job, run)
    # the crucible pot-work steps (2026-10-07, B2)
    if job.type in ("crucible_fire", "crucible_insert", "crucible_fuel",
                    "crucible_take", "crucible_pour"):
        return _crucible(pol, bot, job, measured)
    # pots chain (2026-10-10, J2-J5): clayform / kiln_fire /
    # firepit_fuel / cook / eat - one harness-primitive-driven stage
    # each (firepit_fuel added 2026-10-10 deploy: the endogenous
    # firepit fueling + deterministic firestarter re-arm).
    if job.type in ("clayform", "kiln_fire", "firepit_fuel", "cook",
                    "eat"):
        return _pots_stage(pol, bot, job, measured)
    return (False, "unhandled job type %s" % job.type, measured, {},
            {})


# --------------------------------------------------------------------------
# Operator campaign mode (--jobs, 2026-10-06)
# --------------------------------------------------------------------------

class _CampaignGoal:
    """The stand-in goal for a --jobs run: a human-readable line,
    not a grammar-parsed goal (the operator's job list IS the plan).
    GoalState needs a to_dict()/describe() surface - that is all."""

    def __init__(self, line):
        self.line = line

    def to_dict(self):
        return {"line": self.line, "origin": "operator", "campaign": True}

    def describe(self):
        return self.line


def _cell_code(pol, bot, cell):
    """The live block code at an exact cell (None when empty)."""
    want = [int(c) for c in cell]
    for b in (pol.cell_blocks(bot, tuple(cell), pad=0) or []):
        if b.get("pos") == want:
            return b.get("code")
    return None


def _live_recipes(pol, output, limit=50):
    """The live /polis/recipes endpoint (10-04 craft chain: the shapeless
    table; the 2026-10-06 shaped extension adds pattern/width/height and
    per-ingredient tags/isTool). Output-substring filter, page-capped."""
    r = pol.get("/polis/recipes?output=%s&limit=%d" % (output, limit))
    rows = r.get("recipes")
    if rows is None:
        rows = (r.get("Data") or {}).get("recipes")
    return rows or []


def _campaign_jobs(args):
    """Parse + schema-validate the --jobs list (the jobs.py catalog is
    the validation machinery - chop included). Returns (jobs, None)
    or (None, reason)."""
    try:
        raw = json.loads(args.jobs)
    except ValueError as e:
        return None, "jobs JSON unparseable: %s" % e
    if not isinstance(raw, list) or not raw:
        return None, "--jobs must be a non-empty JSON array of job objects"
    jobs = []
    for i, d in enumerate(raw):
        if not isinstance(d, dict):
            return None, "job %d: not a JSON object" % (i + 1)
        d = dict(d)
        if not d.get("id"):
            d["id"] = "j%d" % (i + 1)
        if not d.get("origin"):
            # a give is an operator PRIVILEGE (harness, not a world
            # fact); the rest of the list is deterministic work
            d["origin"] = ("operator" if d.get("type") == "give_tool"
                           else "deterministic")
        if d.get("type") == "craft" and not d.get("source"):
            # the campaign names the PRODUCED item; the validator matches
            # the recipe by output (several variants may exist - the
            # satisfiable one wins, mirroring the engine's first-match)
            d["source"] = d.get("material")
        try:
            jobs.append(Job.from_dict(d))
        except ValueError as e:
            return None, "job %s: %s" % (d.get("id"), e)
    return jobs, None


def _cell_break(pol, bot, wm, job, run):
    """Approach + break ONE fixed cell (a chop job, or a cell-targeted
    mine from an operator campaign). Same contract as the mine branch:
    the approach module walks the standable cells around the block
    (stuck/goto retries, definitive engine verdict stops the walk);
    the block-gone scan is the oracle; the drop is MEASURED as the
    pre/post inventory delta, never assumed; the wedge guard runs after
    the attempt (a wedged bot aborts with an honest diagnosis instead
    of a silent stall)."""
    cmd_name = "chop" if job.type == "chop" else "mine"
    cell = [int(v) for v in job.at]
    measured = {}
    # staleness before the walk: the surveyed cell may already be empty
    # (a re-run) - say so, do not walk there
    code0 = _cell_code(pol, bot, cell)
    if code0 is None or (code0 or "").lower() in ("", "game:air", "air"):
        return (False, "%s %s: the live cell is empty (nothing to %s)"
                % (cmd_name, cell, cmd_name), measured,
                {"cmd": cmd_name, "ok": False,
                 "reason": "cell empty at execution"},
                {"block_gone": True, "measured": {}})
    # the standable ring: the block's solid neighbourhood
    solid = [b["pos"] for b in pol.cell_blocks(bot, tuple(cell), pad=2)
             if (b.get("code") or "") != "game:air"]
    from_pos = tuple(pol.state(bot)["Bot"]["Pos"])
    pre = inventory_of(pol.state(bot))

    def _goto(c):
        return v5.goto_wait(pol, bot, c, timeout=25)

    def _act():
        # the CommandResult verdict is IMMEDIATE and DEFINITIVE (the
        # mine branch's contract): a validation refusal (no path / out
        # of range / target gone) never records a LastAction
        r = pol.cmd(cmd_name, [str(cell[0]), str(cell[1]),
                               str(cell[2]), "true"], bot)
        if r.get("Ok") is False:
            return {"ok": False,
                    "last_action": {"Name": cmd_name, "Ok": False,
                                    "Msg": r.get("Message") or ""}}
        # accepted: poll the ORACLE (the block) and the record; the
        # LastAction is a hint, the block-gone is the proof
        t_a = time.time()
        la2 = {}
        while time.time() - t_a < 60:
            time.sleep(2)
            st2 = pol.state(bot)
            la2 = st2.get("LastAction") or {}
            if la2.get("Name") in (cmd_name, job.type) \
                    and la2.get("Ok") is not None:
                break
            bs = pol.cell_blocks(bot, tuple(cell), pad=0) or []
            if not any(b.get("pos") == list(cell) and
                       (b.get("code") or "") != "game:air" for b in bs):
                break  # the block is gone - the work is done
        gone_now = not any(
            (b.get("code") or "") != "game:air" and
            b.get("pos") == list(cell)
            for b in (pol.cell_blocks(bot, tuple(cell), pad=0) or []))
        return {"ok": gone_now or la2.get("Ok") is True,
                "last_action": la2}

    aok, adetail, attempts, la = r2approach.approach(
        _goto, _act, from_pos, cell, solid)
    # the drop lands in the cargo ASYNCHRONOUSLY - poll for it (the
    # mine branch's window), then measure the delta
    post = {}
    for _ in range(9):
        time.sleep(2)
        post = inventory_of(pol.state(bot))
        if any(post.get(k, 0) > pre.get(k, 0)
               for k in set(pre) | set(post)):
            break
    for k in set(pre) | set(post):
        if post.get(k, 0) > pre.get(k, 0):
            measured[k] = measured.get(k, 0) + \
                (post.get(k, 0) - pre.get(k, 0))
    blocks = pol.cell_blocks(bot, cell)
    gone = bool(blocks) and not any(
        (b.get("code") or "") != "game:air" and b.get("pos") == list(cell)
        for b in blocks)
    # the wedge guard (the mine branch's): a wedged bot aborts the job
    # with an honest diagnosis instead of a 12-minute silent stall
    rec_ok, rec_state, rec_detail = recheck_and_recover(
        pol, bot, "after %s %s" % (cmd_name, cell))
    if not rec_ok:
        return (False,
                "%s %s -> %s | ABORT: %s"
                % (cmd_name, cell, adetail, rec_detail),
                measured,
                {"last_action": {k: la.get(k) for k in ("Name", "Ok", "Msg")},
                 "approach_attempts": attempts},
                {"block_gone": gone, "measured": measured,
                 "wedge": rec_state})
    ok = bool(aok) and gone
    detail = ("%s %s -> %s | last_action_ok=%s block_gone=%s measured=%s"
              % (cmd_name, cell, adetail, la.get("Ok"), gone, measured))
    return ok, detail, measured, \
        {"last_action": {k: la.get(k) for k in ("Name", "Ok", "Msg")},
         "approach_attempts": attempts}, \
        {"block_gone": gone, "measured": measured}


# --------------------------------------------------------------------------
# Forage (2026-10-07 survival run, B1) and the crucible pot-work
# --------------------------------------------------------------------------

def _code_matches(code, plant):
    """Exact code, family glob (`fruitingbush-*`) or family root
    (prefix up to the next '-') - the plancheck convention."""
    e = str(plant or "").split(":")[-1].lower()
    if "*" in e:
        return fnmatch.fnmatchcase(code, e)
    return code == e or code.startswith(e + "-")


def _nearest_target(pol, bot, plant, radius=24, limit=50):
    """The nearest instance of a plant code / family glob from the
    /polis/targets scan (the harness' interactable-block view, centred
    on the bot; the zone= parameter on the same endpoint is Lane A's
    addition, used by oikistes' query tool). Returns [x, y, z] or
    None. JSON case is tolerated (the harness serializes POCOs
    PascalCase; older payloads camelCase)."""
    token = str(plant or "").split(":")[-1]
    filter_ = token.split("*")[0]  # the codeContains substring
    url = ("/polis/targets?botId=%d&mode=blocks&radius=%d&limit=%d"
           "&codeContains=%s") % (bot, radius, limit, filter_)
    r = pol.get(url) or {}
    for key in ("Blocks", "blocks"):
        for b in (r.get(key) or []):
            code = (b.get("Code") or b.get("code") or "") \
                .split(":")[-1].lower()
            p = b.get("Pos") or b.get("pos")
            if not p or len(p) < 3:
                continue
            if _code_matches(code, plant):
                return [int(p[0]), int(p[1]), int(p[2])]
    return None


def _pick_once(pol, bot, cell, count):
    """One pick round (Lane A's harness command: `pick x y z [count]`,
    issued from an adjacent cell - it runs the same pick path the
    mod's forage interrupt uses; the engine's verdict is immediate and
    definitive, and the result carries the items gathered). Returns
    the approach module's try_action shape."""
    r = pol.cmd("pick", [str(cell[0]), str(cell[1]), str(cell[2]),
                         str(max(1, count))], bot, timeout=120)
    la = {"Name": "pick", "Ok": r.get("Ok"), "Msg": r.get("Message") or ""}
    if r.get("Ok") is not False:
        t_a = time.time()
        while time.time() - t_a < 20:
            la = pol.state(bot).get("LastAction") or {}
            if la.get("Name") == "pick" and la.get("Ok") is not None:
                break
            time.sleep(1)
    return {"ok": r.get("Ok") is True and la.get("Ok") is not False,
            "last_action": la, "data": r.get("Data") or {}}


def _forage(pol, bot, wm, job, run):
    """Gather from a forageable plant (the 1.22 fruiting bush): walk
    to an ADJACENT cell (the approach module's neighbour ring - a
    bush is a solid block, the pick must come from next to it), then
    repeat `pick` on the target until the count is met or the plant
    yields nothing (exhausted - an honest stop, never a stall). The
    target is the job's `at` cell (a known target from a targets
    query) or, without one, the nearest instance of the plant code /
    family found in the /polis/targets scan at run time. Drops are
    MEASURED as the pre/post inventory delta, never assumed (chop's
    precedent). deliver=drop drops everything at the bot's feet on
    completion; carry (default) leaves the cargo in the bot."""
    plant = (job.plant or "").split(":")[-1].lower()
    cell = [int(v) for v in job.at] if job.at else \
        _nearest_target(pol, bot, plant)
    if cell is None:
        return (False,
                "forage %s: no instance of %r in range (targets scan)"
                % (plant, job.plant), {},
                {"cmd": "targets", "ok": False},
                {"found": False})
    want = job.quantity or 1
    # staleness before the walk: the surveyed cell may already be gone
    code0 = _cell_code(pol, bot, cell)
    if code0 is None or (code0 or "").lower() in ("", "game:air", "air"):
        return (False,
                "forage %s: cell %s is empty (nothing to forage)"
                % (plant, cell), {},
                {"cmd": "pick", "ok": False,
                 "reason": "cell empty at execution"},
                {"target": list(cell), "measured": {}})
    # the standable ring around the block
    solid = [b["pos"] for b in (pol.cell_blocks(bot, tuple(cell), pad=2) or [])
             if (b.get("code") or "") != "game:air"]
    from_pos = tuple(pol.state(bot)["Bot"]["Pos"])
    pre0 = inventory_of(pol.state(bot))

    def _settle(baseline):
        """wait for the drop to land in the cargo (short window - the
        pick is fast, unlike a chop's 60s break poll)"""
        post = inventory_of(pol.state(bot))
        for _ in range(6):
            if _delta_gain(pre0, post, job) > baseline:
                return post
            time.sleep(2)
            post = inventory_of(pol.state(bot))
        return post

    def _goto(c):
        return v5.goto_wait(pol, bot, c, timeout=25)

    def _act():
        return _pick_once(pol, bot, cell, want)

    aok, adetail, attempts, la = r2approach.approach(
        _goto, _act, from_pos, cell, solid)
    rounds = 1
    have = _delta_gain(pre0, _settle(0), job)
    max_rounds = max(2, min(want + 2, job.budget))
    last_pick_ok = aok
    while have < want and rounds < max_rounds and last_pick_ok:
        r = _pick_once(pol, bot, cell, want - have)
        post = _settle(have)
        now = _delta_gain(pre0, post, job)
        if r["ok"] and now == have:
            break  # the plant yielded nothing this round: exhausted
        have = now
        rounds += 1
        last_pick_ok = r["ok"]
    measured = _delta_dict(pre0, inventory_of(pol.state(bot)))
    ok = aok and have >= want
    detail = ("forage %s @ %s -> %d/%d gathered in %d pick round%s "
              "(%s; last_action_ok=%s)"
              % (plant, cell, have, want, rounds,
                 "s" if rounds != 1 else "", adetail, la.get("Ok")))
    if ok and (job.deliver or "carry") == "drop":
        # drop = the bot's position on completion (Lane A extends the
        # C# drop with an optional position; none given = at the feet)
        dr = pol.cmd("drop", [], bot, timeout=60)
        detail += " | dropped at the feet (cmd_ok=%s)" % dr.get("Ok")
    return ok, detail, measured, \
        {"cmd": "pick", "cell": list(cell),
         "last_action": {k: la.get(k) for k in ("Name", "Ok", "Msg")},
         "approach_attempts": attempts}, \
        {"target": list(cell), "gathered": have, "wanted": want,
         "rounds": rounds, "measured": measured}


def _delta_dict(pre, post):
    """{code: post-pre} over positive deltas (the measured drop)."""
    out = {}
    for k in set(pre) | set(post):
        d = post.get(k, 0) - pre.get(k, 0)
        if d > 0:
            out[k] = d
    return out


def _delta_gain(pre, post, job):
    """Items gained that count toward the job's claim: the claimed
    material (classified) if the job names one, else everything."""
    want = (job.material or "").lower()
    gain = 0
    for k, v in _delta_dict(pre, post).items():
        mat = (classify(k)[1] or "").lower()
        if want and mat != want and k.lower() != want:
            continue
        gain += v
    return gain


def _crucible(pol, bot, job, measured):
    """One crucible pot-work step (2026-10-07, B2): Lane A's C# harness
    commands (the 1.22 crucible; the cooking pot reuses the same base
    later). Command contract: crucible-fire [color] [at x y z]
    (places a `crucible-<color>-raw` block from the cargo into a
    firepit - nearest from the bot, or the given cell - colors
    fire/blue/red; the 1.22 engine has no size variants);
    crucible-insert <item> [count] (smelt slots); crucible-fuel
    <item|charcoal> [count] (fuel slots); crucible-take (removes the
    smelted content, respecting the engine's tongs requirement);
    crucible-pour <x y z> (pours the melt at a mold ground position,
    returns what it produced). The bot must stand at the crucible -
    the chain's goto walks there first. Evidence: the CommandResult
    plus the measured inventory delta (take/pour)."""
    which = job.type.split("_", 1)[1]
    cmd = "crucible-" + which
    args = []
    if which == "fire":
        # material = crucible-<color>-raw (the clayform recipe output)
        parts = (job.material or "").split("-")
        color = parts[1] if len(parts) >= 3 else "fire"
        if color not in ("fire", "blue", "red"):
            color = "fire"
        args = [color]
        if job.at:
            args += ["at", str(job.at[0]), str(job.at[1]), str(job.at[2])]
    elif which in ("insert", "fuel"):
        args = [job.material or ""]
        if job.quantity:
            args.append(str(job.quantity))
    elif which == "pour":
        args = [str(v) for v in (job.at or [])]
    pre = inventory_of(pol.state(bot))
    r = pol.cmd(cmd, args, bot, timeout=120)
    la = {}
    if r.get("Ok") is not False:
        t_a = time.time()
        while time.time() - t_a < 60:
            la = pol.state(bot).get("LastAction") or {}
            if la.get("Name") == cmd and la.get("Ok") is not None:
                break
            time.sleep(2)
    post = inventory_of(pol.state(bot))
    for k, v in _delta_dict(pre, post).items():
        measured[k] = measured.get(k, 0) + v
    for k in set(pre) | set(post):
        d = post.get(k, 0) - pre.get(k, 0)
        if d < 0:
            measured[k] = measured.get(k, 0) + d
    ok = r.get("Ok") is True and la.get("Ok") is not False
    data = r.get("Data") or {}
    detail = ("%s %s -> cmd_ok=%s last_action_ok=%s measured=%s"
              % (cmd, " ".join(args), r.get("Ok"), la.get("Ok"),
                 measured))
    if data:
        detail += " data=%s" % data
    return ok, detail, measured, \
        {"cmd": cmd, "args": args, "ok": r.get("Ok"),
         "last_action": {k: la.get(k) for k in ("Name", "Ok", "Msg")},
         "data": data}, \
        {"measured": measured, "data": data}


def _pots_stage(pol, bot, job, measured):
    """One pots-chain stage (2026-10-10, J2-J5). Each stage drives the
    harness primitives that were live-verified on the survival run,
    then observes the FRESH world as its oracle (the 12.6/13.2 split:
    the command's verdict is `execution`, the world check is
    `oracle`). All stages are goal-scoped campaign jobs (the 27B
    planner never learned this vocabulary).

    Engine facts baked in (measured 2026-10-10, survival-5):
    - clayform places its own game:clayform table via direct SetBlock,
      but the placement check treats soil tufts as blocking: the
      target cell is cleared to air first. On completion the table
      converts to a groundstorage holding the shaped RAW item.
    - the pit kiln (1-deep hole) must run create/feed/ignite/ff in ONE
      live session (the game:pitkiln block is non-persistent; the
      fired output lands in the persistent storage at the hole floor
      and survives the session).
    - the 1.22 firepit cooks the INPUT slot (1) through the item's
      own DoSmelt (fuel slot 0, output slot 2); the pot is only
      needed for multi-ingredient meals.
    - eat runs the shared policy-gated core (PolisEatService).
    """
    def _cell(c):
        return [str(v) for v in (c or [])]

    def _goto(cell):
        # the workstation actions enforce a short reach (4.5 m). The
        # engine's goto verdict is not a distance truth: long walks
        # get declared failed while the bot keeps walking (run 5:
        # 108 m -> 25 m with the engine saying "no"). So poll the
        # actual bot position and re-issue until we are in range or
        # the budget runs out.
        tx, ty, tz = int(cell[0]) + 1, int(cell[1]), int(cell[2])
        t0 = time.time()
        last_issue = 0.0
        while time.time() - t0 < 180:
            if time.time() - last_issue > 20:
                try:
                    pol.cmd("goto", [str(tx), str(ty), str(tz),
                                     "true", "0.02", "true"], bot,
                            timeout=15)
                except Exception:
                    pass
                last_issue = time.time()
            try:
                pos = pol.state(bot).get("Bot", {}).get("Pos") or []
            except Exception:
                pos = []
            if len(pos) >= 3:
                d = ((float(pos[0]) - tx) ** 2 +
                     (float(pos[2]) - tz) ** 2) ** 0.5
                if d <= 4:
                    return True
            time.sleep(3)
        return False

    def _stored(cell):
        d = pol.cmd("container-contents", _cell(cell), bot,
                    timeout=30).get("Data") or {}
        return {s.get("code"): s.get("qty", 1)
                for s in d.get("slots", []) if s.get("code")}

    def _take(cell, slot, tries=4):
        for _ in range(tries):
            r = pol.cmd("container-take",
                        _cell(cell) + [str(slot)], bot, timeout=30)
            if not r.get("Ok"):
                break

    def _inv():
        return inventory_of(pol.state(bot))

    which = job.type
    cell = job.at or []

    if which == "clayform":
        if not cell:
            return (False, "clayform: no at cell", measured,
                    {"cmd": "clayform", "ok": False,
                     "reason": "no at"}, {})
        recipe = job.material or ""
        clay = job.expect or "clay-red"
        pre = _inv()
        have = (pre.get("game:" + clay, 0) + pre.get(clay, 0))
        if have <= 0:
            return (False, "clayform: no %s in cargo" % clay,
                    measured, {"cmd": "clayform", "ok": False,
                               "reason": "no clay"}, {})
        near = _goto(cell)
        # the placement check treats tufts as blocking: clear first
        pol.cmd("setblock", ["game:air"] + _cell(cell), bot, timeout=30)
        r = pol.cmd("clayform", _cell(cell) + [recipe, "8"], bot,
                    timeout=180)
        stored = {}
        for _ in range(30):
            stored = _stored(cell)
            if stored:
                break
            time.sleep(2)
        for i in range(4):
            _take(cell, i)
        post = _inv()
        have_out = (post.get("game:" + recipe, 0)
                    + post.get(recipe, 0))
        for k, v in _delta_dict(pre, post).items():
            measured[k] = measured.get(k, 0) + v
        ok = r.get("Ok") is True and have_out > 0
        return (ok,
                "clayform %s recipe=%s stored=%s bot_has=%d"
                % (" ".join(_cell(cell)), recipe, stored, have_out),
                measured,
                {"cmd": "clayform",
                 "args": _cell(cell) + [recipe, "8"],
                 "ok": r.get("Ok"), "near": near},
                {"stored": stored, "bot_has": have_out,
                 "expected": recipe})

    if which == "kiln_fire":
        if not cell:
            return (False, "kiln_fire: no at cell", measured,
                    {"cmd": "kiln", "ok": False,
                     "reason": "no at"}, {})
        fired = job.material or ""
        raw = (job.recipes or [fired])[0]
        pre = _inv()
        have = (pre.get("game:" + raw, 0) + pre.get(raw, 0))
        if have <= 0:
            return (False, "kiln_fire: no %s in cargo" % raw,
                    measured, {"cmd": "kiln", "ok": False,
                               "reason": "no raw item"}, {})
        near = _goto(cell)
        steps = []
        # create preserves the fireable item only if it is already in
        # the hole storage or passed as [itemCode qty] (the vanilla
        # conversion has no other input path) - we pass the bot's raw
        # item explicitly.
        r = pol.cmd("kiln", ["create"] + _cell(cell) + [raw, "1"],
                    bot, timeout=120)
        steps.append(("create", bool(r.get("Ok"))))
        steps.append(("feed",
                     bool(pol.cmd("kiln", ["feed"] + _cell(cell),
                                  bot, timeout=300).get("Ok"))))
        steps.append(("ignite",
                     bool(pol.cmd("kiln", ["ignite"] + _cell(cell),
                                  bot, timeout=60).get("Ok"))))
        rff = pol.cmd("kiln", ["ff"] + _cell(cell), bot, timeout=60)
        steps.append(("ff", bool(rff.get("Ok"))))
        # OnFired lands the fired item in the storage at the hole
        # floor (the same cell the kiln BE occupied)
        stored = {}
        for _ in range(30):
            stored = _stored(cell)
            if fired in stored:
                break
            time.sleep(2)
        _take(cell, 0)
        _take(cell, 1)
        _take(cell, 2)
        _take(cell, 3)
        post = _inv()
        have_out = (post.get("game:" + fired, 0) + post.get(fired, 0))
        for k, v in _delta_dict(pre, post).items():
            measured[k] = measured.get(k, 0) + v
        ok = all(o for _, o in steps) and have_out > 0
        return (ok,
                "kiln_fire %s %s -> %s steps=%s bot_has=%d"
                % (" ".join(_cell(cell)), raw, fired, steps,
                   have_out),
                measured,
                {"cmd": "kiln", "steps": steps, "near": near},
                {"stored": stored, "bot_has": have_out,
                 "expected": fired})

    if which == "firepit_fuel":
        if not cell:
            return (False, "firepit_fuel: no at cell (the firepit)", measured,
                    {"cmd": "firepit_fuel", "ok": False, "reason": "no at"}, {})
        fuel = job.material or "charcoal"
        n = job.quantity or 1
        near = _goto(cell)
        r = pol.cmd("firepit-fuel", _cell(cell) + [fuel, str(n)], bot,
                    timeout=60)
        if r.get("Ok") is not True:
            return (False, "firepit_fuel %s: %s"
                    % (" ".join(_cell(cell)), r.get("Message")), measured,
                    {"cmd": "firepit-fuel", "ok": False, "near": near}, {})
        d = r.get("Data") or {}
        if not d.get("canIgniteFuel"):
            # fresh (unarmed) firepit: the deterministic firestarter
            # re-arm (engine's own completion path, no 25% roll)
            lr = pol.cmd("firepit-light", _cell(cell), bot, timeout=60)
            if lr.get("Ok") is not True:
                return (False, "firepit_fuel %s: re-arm failed: %s"
                        % (" ".join(_cell(cell)), lr.get("Message")),
                        measured,
                        {"cmd": "firepit-light", "ok": False,
                         "near": near}, {})
            d = lr.get("Data") or {}
        # an armed firepit with fuel auto-ignites on the engine's next
        # burn tick (OnBurnTick: !IsBurning && canIgniteFuel &&
        # canSmelt() -> igniteFuel()). Detection: the `be` dump exposes
        # BE fields as "name=value" strings - there is NO IsBurning
        # property in the dump (2026-10-10: polling that key
        # false-failed the stage while the pit burned, aborting
        # cook/eat); fuelBurnTime > 0 is the live-burn signal.
        burning = False
        fuel_burn = -1.0
        fv = {}
        for _ in range(30):
            b = pol.cmd("be", _cell(cell), bot, timeout=30)
            dd = b.get("Data") or {}
            fv = {}
            for fstr in dd.get("fields") or []:
                if isinstance(fstr, str) and "=" in fstr:
                    k, v = fstr.split("=", 1)
                    fv[k] = v
            try:
                fuel_burn = float(fv.get("fuelBurnTime", "0") or 0)
            except (TypeError, ValueError):
                fuel_burn = 0.0
            burning = fuel_burn > 0
            if burning:
                break
            time.sleep(1)
        return (burning,
                "firepit_fuel %s: fueled %sx%s, %s (fuelBurnTime=%.1f, canIgniteFuel=%s)"
                % (" ".join(_cell(cell)), fuel, n,
                   "burning" if burning else "NOT burning after re-arm",
                   fuel_burn, fv.get("canIgniteFuel", "?")),
                measured,
                {"cmd": "firepit-fuel", "ok": True, "near": near},
                {"burning": burning, "armed": bool(d.get("canIgniteFuel")),
                 "fuelBurnTime": fuel_burn})

    if which == "cook":
        if not cell:
            return (False, "cook: no at cell (the firepit)", measured,
                    {"cmd": "cook", "ok": False,
                     "reason": "no at"}, {})
        cooked = job.material or ""
        raw = (job.recipes or [cooked])[0]
        n = job.quantity or 1
        pre = _inv()
        near = _goto(cell)
        # bot-driven (2026-10-10 endogenous pass): the meat goes into
        # the input slot (1) through the bot's own firepit-put action
        # (the 1.22 firepit GUI is slot writes only). The fuel was
        # handled by the firepit_fuel stage, which left the pit
        # burning - no operator slot writes, no direct-ignite call.
        fp = pol.cmd("firepit-put",
                     _cell(cell) + ["1", raw, str(n)], bot, timeout=60)
        if fp.get("Ok") is not True:
            return (False,
                    "cook %s: firepit-put failed: %s"
                    % (" ".join(_cell(cell)), fp.get("Message")),
                    measured,
                    {"cmd": "firepit-put", "ok": False, "near": near}, {})
        out = {}
        for _ in range(60):
            d = pol.cmd("container-contents", _cell(cell), bot,
                        timeout=30).get("Data") or {}
            out = {s.get("code"): s.get("qty", 1)
                   for s in d.get("slots", [])
                   if s.get("code") and s.get("slot") == 2}
            if out:
                break
            time.sleep(3)
        _take(cell, 2)
        post = _inv()
        have_out = (post.get("game:" + cooked, 0)
                    + post.get(cooked, 0))
        for k, v in _delta_dict(pre, post).items():
            measured[k] = measured.get(k, 0) + v
        ok = have_out > 0
        return (ok,
                "cook %s: %sx%s into input slot via bot (firepit %s) -> output=%s bot_has=%d"
                % (" ".join(_cell(cell)), raw, n,
                   "burning" if (fp.get("Data") or {}).get("burning") else "cold"),
                measured,
                {"cmd": "firepit-put", "ok": True,
                 "output": out, "near": near},
                {"bot_has": have_out, "expected": cooked})

    if which == "eat":
        item = job.material or ""
        n = job.quantity or 1
        r = pol.cmd("eat", [item, str(n)], bot, timeout=120)
        d = r.get("Data") or {}
        ok = r.get("Ok") is True
        return (ok,
                "eat %sx %s: %s" % (n, item, r.get("Message") or ""),
                {item: d.get("units", 0) if ok else 0},
                {"cmd": "eat", "args": [item, str(n)],
                 "ok": r.get("Ok")},
                {"before": d.get("before"), "after": d.get("after"),
                 "units": d.get("units")})

    return (False, "pots stage: unknown type %s" % which, measured,
            {}, {})


def _parse_keep(args):
    """--keep-bots (comma-separated ids) -> [int, ...]."""
    return [int(x) for x in
            (getattr(args, "keep_bots", "") or "").split(",")
            if x.strip().isdigit()]


def run_campaign(args, run, t0):
    """The operator campaign (--jobs, 2026-10-06): an explicit
    deterministic job list (give / chop / craft / mine / place), no
    grammar parsing, no 27B. The jobs validate against the LIVE world
    BEFORE any action (chop cells from a fresh scan; the shaped recipe
    pattern against the projected inventory - the same planner-side
    honesty a planned job gets, applied to operator-declared jobs),
    then run in list order through the normal run_jobs/execute_job
    machinery with the per-job origin recorded. The run JSON is the
    same shape as a normal run: goal line, plan, steps with the
    execution/oracle split, queue, world snapshot, outcome - plus a
    final oracle summary of the per-job results."""
    run["mode"] = "operator-campaign"
    pol = v5.Polis(args.harness, args.uid)

    # 1. schema (the jobs.py catalog - chop included; n/at/expect
    #    are the operator field names)
    jobs_raw, err = _campaign_jobs(args)
    if err:
        run.update({"outcome": "rejected", "reason": err})
        return finish(args.out, run, t0)

    # 2. world observation (fresh bot, boot scan). The keep list is
    # the agent's body + crew: run_campaign used to drop it (2026-10-10 -
    # every operator campaign killed the Oikistes body and the crew on
    # boot), so it is threaded here exactly as the planner path does.
    keep = _parse_keep(args)
    bot, wm, st, boot_scan = boot(pol, keep=keep or None)
    run["keep_bots"] = keep
    run["bot"] = bot
    run["boot_scan"] = boot_scan
    run["goal"] = {"line": args.goal, "origin": "operator",
                   "campaign": True}
    st = pol.state(bot)

    # 3. live pre-execution checks (the validator gate):
    #    place/build jobs with an explicit cell get a site fixture -
    #    the EXISTING place semantics (the site-filled oracle; a door's
    #    entity height is a game-side matter); a goto that names a cell
    #    (the crucible chain's walk to the firepit, 2026-10-07) gets
    #    one the same way - the goto executor only reads fixture cells
    for j in jobs_raw:
        if j.type in ("place", "build", "goto") and j.at and not j.target:
            sid = "site-job-%s" % j.id
            wm.register_fixture(sid, "build-site", list(j.at), "empty")
            wm.observe_fixture(
                sid, not pol.site_filled(bot, tuple(j.at)),
                reason="fixture_setup:operator")
            j.target = sid
    #    cell jobs (chop, cell-mine): a fresh scan of every target
    #    cell is the world index the chop check validates against
    cells = {}
    for j in jobs_raw:
        if j.at:
            cells[tuple(int(v) for v in j.at)] = _cell_code(pol, bot, j.at)
    #    craft: the live recipe table (only when the list needs it)
    recipes = None
    if any(j.type == "craft" for j in jobs_raw):
        seen, rows = set(), []
        for j in jobs_raw:
            if j.type == "craft" and j.material not in seen:
                seen.add(j.material)
                rows.extend(_live_recipes(pol, j.material))
        recipes = rows

    # 4. the deterministic validator over the live world (the ledger
    #    simulates in execution order: the give's axe and the chops'
    #    planned drops are what the craft's pattern check sees)
    inv = normalize_inv(inventory_of(st))
    index = {r.id: r for r in wm.resources.values()}
    for fid, f in wm.fixtures.items():
        index[fid] = {"id": fid, "kind": f.kind,
                      "requirement": f.requirement}
    plan_raw = [j.to_dict() for j in jobs_raw]
    jobs, failure = validate_plan(
        plan_raw, index, inv, goal=None, recipes=recipes, cells=cells,
        campaign=True)
    run["planner"] = {"mode": "operator-campaign", "goal": args.goal,
                      "jobs": len(jobs_raw)}
    run["plan"] = {"raw": args.jobs[:600], "latency_ms": 0,
                   "jobs": [j.to_dict() for j in jobs] if jobs else None,
                   "failure": failure.to_dict() if failure else None}
    if failure is not None:
        run.update({"outcome": "rejected",
                    "reason": "%s (%s): %s"
                    % (failure.code, failure.layer, failure.detail)})
        return finish(args.out, run, t0)

    # 5. the queue drives execution (the normal machinery)
    base = tuple(st["Bot"]["Pos"])
    gs = GoalState(_CampaignGoal(args.goal), jobs, "operator-campaign")
    job = gs.start()
    botref = [bot]
    while job is not None and gs.status == "running":
        run_jobs(pol, bot, base, gs, job, run, wm, botref=botref)
        bot = botref[0]
        job = gs.next_job()

    # 6. the same run metadata as a normal run + the final oracle
    run["queue"] = gs.to_dict()
    run["worldSnapshot"] = wm.to_dict()
    run["outcome"] = gs.status
    run["oracle"] = {
        "status": gs.status,
        "failure": gs.failure.to_dict() if gs.failure else None,
        "jobs": [{"job": s.get("job"), "type": s.get("type"),
                  "ok": s.get("ok"), "measured": s.get("measured"),
                  "oracle": s.get("oracle")}
                 for s in run["steps"]]}
    print("CAMPAIGN %s: %s  (%d jobs, %ds)"
          % (gs.status.upper(), args.goal, len(jobs),
             int(time.time() - t0)))
    if gs.failure:
        print("  failure: %s - %s"
              % (gs.failure.code, gs.failure.detail))
    finish(args.out, run, t0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--harness", required=True)
    ap.add_argument("--uid", required=True)
    ap.add_argument("--no-planner", action="store_true",
                    help="deterministic plan for one-verb mine/harvest "
                         "goals (13.6 step 2: prove executor+ledger+oracle "
                         "without the LLM in the loop)")
    ap.add_argument("--llm", default="")
    ap.add_argument("--llm-model", default="")
    ap.add_argument("--goal", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--jobs", default="",
                    help="operator campaign: an explicit deterministic "
                         "job list (JSON array; job objects with "
                         "type/at/n/expect/origin). With this flag the "
                         "goal line is the campaign description - no "
                         "grammar parsing, no planner; the jobs are "
                         "validated against the live world, then run "
                         "in list order. Implies --no-planner.")
    ap.add_argument("--chain", default="",
                    help="a mission-plan template (r2/chains.py, e.g. "
                         "crucible-copper): rendered to a --jobs list "
                         "with --chain-params before validation")
    ap.add_argument("--chain-params", default="",
                    help="JSON object of template parameters for "
                         "--chain (firepit_at, mold_at, color, ore, "
                         "fuel, wait_s, ...)")
    ap.add_argument("--site", default="",
                    help="operator-declared build-site 'x,y,z' (the "
                         "driver registers it as the goal's site fixture, "
                         "logged in the run JSON)")
    ap.add_argument("--keep-bots", default="",
                    help="comma-separated bot ids the boot sweep must "
                         "not kill (the agent's body + the crew)")
    ap.add_argument("--pregive", action="append", default=[],
                    help="external setup before the goal: '<item> <qty>' "
                         "(logged in the run JSON - a harness privilege, "
                         "not a world fact)")
    args = ap.parse_args()

    # a mission-plan template renders to a --jobs list before anything
    # else (the chain module is pure data - the campaign machinery is
    # unchanged below it)
    if args.chain:
        from r2 import chains as r2chains
        params = json.loads(args.chain_params) if args.chain_params else {}
        try:
            args.jobs = json.dumps(r2chains.render(args.chain, params))
        except (KeyError, ValueError, TypeError) as e:
            print("CHAIN %s: %s" % (args.chain, e))
            sys.exit(2)
        print("CHAIN %s: rendered %s jobs" % (args.chain,
                                              len(json.loads(args.jobs))))

    run = {"started": time.strftime("%Y-%m-%d %H:%M:%S %Z"),
           "model": args.llm_model,
           "goal_line": args.goal,
           "steps": []}
    t0 = time.time()
    if args.jobs:
        run_campaign(args, run, t0)
        return
    pol = v5.Polis(args.harness, args.uid)

    # 1. goal intake (grammar + known site)
    gd = parse_goal_line(args.goal)
    try:
        goal = Goal.from_dict(gd)
    except Exception as e:
        run.update({"outcome": "rejected", "reason": str(e)})
        return finish(args.out, run, t0)
    run["goal"] = goal.to_dict()

    # 2. world observation
    keep_bots = _parse_keep(args)
    bot, wm, st, boot_scan = boot(pol, keep=keep_bots or None)
    run["bot"] = bot
    run["boot_scan"] = boot_scan
    for spec in args.pregive:
        item, qty = spec.split()
        r = pol.cmd("give", [item, qty], bot)
        run.setdefault("setup", []).append(
            {"give": item, "qty": qty, "ok": bool(r.get("Ok"))})
        time.sleep(1)
    st = pol.state(bot)

    # 2b. declared external supply (12.10 remediation (a)): the operator
    # said at intake that harness supply is sanctioned, so the material is
    # given DETERMINISTICALLY BEFORE the planner runs - the 27B then sees a
    # place goal it can actually plan (its refusal prior fires on the
    # pre-supply world). Recorded as job j0+ for the queue/run JSON.
    # build-plan (13.11) generalizes this to the plan's whole material
    # list: one give job per material.
    ops = []
    if getattr(goal, "supply", None) == "external" and \
            goal.verb in ("place", "build", "build-plan"):
        if goal.verb == "build-plan":
            import r2.buildplans as _bp
            _plan = _bp.load_plan(os.path.join(REPO, "builds",
                                              goal.object + ".json"))
        else:
            _plan = None
        mats = _plan.materials if _plan else \
            {goal.object: goal.n or (4 if goal.verb == "build" else 1)}
        for i, (m, q) in enumerate(sorted(mats.items())):
            item = GIVE_ITEM.get(m, m)
            r = pol.cmd("give", [item, str(q)], bot)
            ops.append(Job("j%d" % i, "give_tool", origin="operator",
                           material=m, quantity=q))
            run["supply"] = {"declared": True, "item": item,
                             "qty": q, "ok": bool(r.get("Ok"))}
            time.sleep(1)
        if _plan is not None:
            st = pol.state(bot)

    inv = normalize_inv(inventory_of(st))
    op_site = None
    if args.site:
        try:
            op_site = [int(v) for v in args.site.split(",")]
            assert len(op_site) == 3
        except ValueError:
            run.update({"outcome": "rejected",
                        "reason": "--site must be 'x,y,z' ints"})
            return finish(args.out, run, t0)
        run["site"] = {"declared": op_site, "origin": "operator"}
    fixtures = register_site(wm, pol, bot, goal, None, op_site)
    gfail = check_goal(goal, [f["id"] for f in fixtures])
    if gfail is not None:
        run.update({"outcome": "rejected",
                    "reason": "%s: %s" % (gfail.code, gfail.detail)})
        return finish(args.out, run, t0)

    # 3. plan + validate (deterministic, goal-aware)
    if getattr(args, "no_planner", False) and goal.verb in (
            "mine", "harvest", "sow", "build", "build-plan"):
        # the deterministic goal compiler (13.6 step 2, no LLM): a
        # one-verb acquisition goal has one obvious plan - the closest
        # resource with sufficient observed quantity. The SAME
        # validator gate applies to the synthesized plan.
        if goal.verb == "build-plan":
            # a building plan (13.11): the plan file is the design,
            # the compiler just names it. Supply: the inventory, or
            # the operator's external pre-give (2b, per material).
            import r2.buildplans as _bp
            if not getattr(goal, "at", None):
                run.update({"outcome": "rejected",
                            "reason": "deterministic: build-plan goal "
                                      "needs 'at <site>'"})
                return finish(args.out, run, t0)
            plan_path = os.path.join(REPO, "builds",
                                     goal.object + ".json")
            if not os.path.exists(plan_path):
                avail = ", ".join(_bp.list_plans(
                    os.path.join(REPO, "builds"))) or "none"
                run.update({"outcome": "rejected",
                            "reason": "unknown plan %r (library: %s)"
                            % (goal.object, avail)})
                return finish(args.out, run, t0)
            bp = _bp.load_plan(plan_path)
            bp5 = st["Bot"]["Pos"]
            prompt, index = build_planner_prompt(wm, goal, inv, fixtures,
                                                 center=(bp5[0], 0,
                                                         bp5[2]),
                                                 max_candidates=64)
            if getattr(goal, "supply", None) != "external":
                # mine-prep (2026-10-05): a short inventory is not a
                # rejection when the missing material is hand-minable
                # in the scanned world - the compiler walks the
                # clusters (nearest first, as the planner would) and
                # prepends one mine job per cluster until the shortfall
                # is covered. The plan is [mine.., build_plan]; the
                # ledger and the build_plan's own material preflight
                # both still apply (unknown is never yes).
                missing = {m: (q, inv.get(m, 0))
                           for m, q in bp.materials.items()
                           if inv.get(m, 0) < q}
                jobs = []
                for m, (need_q, have_q) in sorted(missing.items()):
                    if m not in HAND_MINABLE:
                        run.update({"outcome": "rejected",
                                    "reason": "resource_not_found: %s "
                                              "need %d have %d (not "
                                              "hand-minable - declare "
                                              "'supply external' for "
                                              "harness supply)"
                                    % (m, need_q, have_q)})
                        return finish(args.out, run, t0)
                    # oversample (2026-10-05): a 1:1 target risks a
                    # shortfall at the build's material preflight because
                    # some cluster cells are buried (no air above) or
                    # already dug, so the bot cannot mine them all. Mine
                    # ~35% extra; the build_plan uses only what the plan
                    # needs, the surplus stays in the backpack.
                    shortfall = int(round(need_q * 1.35)) - have_q
                    # 2026-10-10: allocate from the FULL world model, not
                    # the planner prompt's index. The index is the 64
                    # NEAREST clusters - a size limit for the LLM prompt.
                    # In a dense survival plateau those 64 are 1-3-cell
                    # fragments (grass, sparse soil), and the one real
                    # dirt cluster (2534 cells here) sorts past them by
                    # centroid distance; the allocator then 'covered 4 of
                    # 103' while the dirt sat 2 m away. The deterministic
                    # path feeds no LLM; it may use the whole model.
                    cands = [r for r in
                             wm.find_unclaimed(
                                 wm.find_resources(fresh=False))
                             if r.material == m]
                    cands.sort(key=lambda r: abs(
                        (r.centroid or [0, 0, 0])[0] - bp5[0]) + abs(
                        (r.centroid or [0, 0, 0])[2] - bp5[2]))
                    # per-cluster allocation cap: 40 when the shortfall
                    # can be spread (the 2026-10-07 over-mine lesson),
                    # but when there are few clusters the cap must grow
                    # or a single-cluster world can never cover the
                    # shortfall (2026-10-10: one 2529-cell plateau).
                    # Sized from the OVERSAMPLED shortfall (not the raw
                    # need-have): the 1.35x safety margin must fit inside
                    # the cap or the allocation can never reach zero.
                    per_cluster_cap = max(40,
                                          shortfall // max(1,
                                                           len(cands)))
                    for rec in cands:
                        if shortfall <= 0:
                            break
                        # allocate by the MINEABLE surface (top cells), not
                        # the full cell count - a big blob is ~97% buried
                        # interior, so len(cells) overstates what a bare
                        # hand can reach. Using the mineable count spreads
                        # the shortfall across several clusters instead of
                        # parking it all on the nearest one.
                        n_mine = (len(rec.mineable_cells)
                                  if rec.mineable_cells
                                  else len(rec.cells))
                        # (2026-10-07) cap the per-cluster allocation at
                        # 40 and spread the shortfall over several
                        # clusters: the scan-time mineable count
                        # overstates what the exposed surface actually
                        # yields (one 99-cell job on the slope west of
                        # the site mined 31 and died on its attempt
                        # budget). With the cap the compiler emits one
                        # mine job per cluster and the bot hops region
                        # to region - the inventory carries across jobs
                        # in one run, and each job's own wedge guard
                        # still applies.
                        take = min(shortfall, n_mine, per_cluster_cap)
                        if take <= 0:
                            continue
                        jobs.append({"id": "j%d" % (len(jobs) + 1),
                                     "type": "mine",
                                     "source": rec.id, "material": m,
                                     "quantity": take,
                                     "origin": "deterministic",
                                     "depends_on": ([jobs[-1]["id"]]
                                                    if jobs else [])})
                        shortfall -= take
                    if shortfall > 0:
                        # 2026-10-10 diagnostic: the rejection number
                        # came from a black box (boot scan saw 3778
                        # blocks but the allocator covered 4) - record
                        # exactly what the candidate index held when
                        # it ran.
                        run["alloc_debug"] = {
                            "wm_resources": [
                                {"id": r.id, "material": r.material,
                                 "code": r.code,
                                 "cells": len(r.cells),
                                 "mineable": (len(r.mineable_cells)
                                              if r.mineable_cells else None),
                                 "observed": r.observed_quantity,
                                 "centroid": r.centroid}
                                for r in wm.find_resources(
                                    fresh=False)],
                            "index_cands": [
                                {"id": k, "material": r.material,
                                 "cells": len(r.cells),
                                 "mineable": (len(r.mineable_cells)
                                              if r.mineable_cells
                                              else None)}
                                for k, r in index.items()
                                if k.startswith("res-")],
                        }
                        run.update({"outcome": "rejected",
                                    "reason": "resource_not_found: %s: "
                                              "scanned clusters cover "
                                              "%d of %d (declare 'supply "
                                              "external' for harness "
                                              "supply)"
                                    % (m, (need_q - have_q) - shortfall,
                                       need_q - have_q)})
                        return finish(args.out, run, t0)
                jobs.append({"id": "j%d" % (len(jobs) + 1),
                             "type": "build_plan",
                             "plan": goal.object, "target": goal.at,
                             "origin": "deterministic",
                             "depends_on": ([jobs[-1]["id"]]
                                            if jobs else [])})
                raw = json.dumps(jobs)
            else:
                # external supply (12.10 (a)): the material is pre-given
                # in step 2b, so the plan is JUST the build job - no mine.
                # (Define `jobs` here too: run["planner"] below reads it
                # for mine_prep; the old single-object `raw` left it
                # unbound - UnboundLocalError, run v7.)
                jobs = [{"id": "j1", "type": "build_plan",
                         "plan": goal.object, "target": goal.at,
                         "origin": "deterministic"}]
                raw = json.dumps(jobs)
            run["planner"] = {"mode": "deterministic",
                              "chosen": {"plan": goal.object,
                                         "site": goal.at,
                                         "blocks": bp.total_blocks(),
                                         "supply": "external"
                                         if getattr(goal, "supply",
                                                    None) == "external"
                                         else "inventory",
                                         "mine_prep": [
                                             {"job": j["id"],
                                              "material": j["material"],
                                              "source": j["source"],
                                              "quantity": j["quantity"]}
                                             for j in jobs
                                             if j["type"] == "mine"]},
                              "candidates": sorted(index)}
            jobs_v, failure = validate_plan(raw, index, inv, goal=goal)
            jobs = jobs_v
            run["plan"] = {"raw": raw, "latency_ms": 0,
                           "jobs": [j.to_dict() for j in jobs_v] if jobs_v else None,
                           "failure": failure.to_dict() if failure else None}
        elif goal.verb == "build":
            # the ring platform (09-28): ONE composite job that places
            # N blocks around the goal site, one layer above the site's
            # base cell. Supply: the inventory, or a declared external
            # pre-give (2b above, which runs before the inventory is
            # read - so the ledger sees the supplied material).
            n = goal.n or 4
            if n > 16:
                run.update({"outcome": "rejected",
                            "reason": "deterministic: build is capped "
                                      "at 16 blocks (one ring)"})
                return finish(args.out, run, t0)
            if not getattr(goal, "at", None):
                run.update({"outcome": "rejected",
                            "reason": "deterministic: build goal needs "
                                      "'at <site>'"})
                return finish(args.out, run, t0)
            have = inv.get(goal.object, 0)
            if have < n and getattr(goal, "supply", None) != "external":
                run.update({"outcome": "rejected",
                            "reason": "resource_not_found: %s: have %d, "
                                      "need %d (declare 'supply external' "
                                      "for harness supply)"
                            % (goal.object, have, n)})
                return finish(args.out, run, t0)
            bp4 = st["Bot"]["Pos"]
            raw = json.dumps({"id": "j1", "type": "build",
                              "quantity": n, "target": goal.at,
                              "material": goal.object,
                              "origin": "deterministic"})
            prompt, index = build_planner_prompt(wm, goal, inv, fixtures,
                                                 center=(bp4[0], 0,
                                                         bp4[2]))
            run["planner"] = {"mode": "deterministic",
                              "chosen": {"site": goal.at, "blocks": n,
                                         "supply": "inventory"
                                         if have >= n else "external"},
                              "candidates": sorted(index)}
            jobs, failure = validate_plan(raw, index, inv, goal=goal)
            run["plan"] = {"raw": raw, "latency_ms": 0,
                           "jobs": [j.to_dict() for j in jobs] if jobs else None,
                           "failure": failure.to_dict() if failure else None}
        elif goal.verb == "sow":
            # the 2-job endogenous chain (13.6): harvest the nearest crop
            # of the goal's material, then sow at the goal's site. The
            # 27B degenerates (silent token loop) on the new "sow"
            # vocabulary (measured 2026-09-28), so the deterministic
            # compiler takes the structured case - the design-level
            # answer to the 27B's refusal (12.10 remediation (a) applied
            # to the planner itself).
            import math as _math
            bp2 = st["Bot"]["Pos"]
            best = None
            for r in wm.resources.values():
                if r.kind != "crop" or r.material != goal.object:
                    continue
                if r.observed_quantity < (goal.n or 1):
                    continue
                c = r.cells[0]
                d = _math.hypot(c[0] - bp2[0], c[2] - bp2[2])
                if best is None or d < best[0]:
                    best = (d, r)
            if best is None or not getattr(goal, "at", None):
                run.update({"outcome": "rejected",
                            "reason": "deterministic: sow needs a crop "
                                      "resource and a site"
                            if best is None else
                            "deterministic: sow goal needs 'at <site>'"})
                return finish(args.out, run, t0)
            d, r = best
            n = goal.n or 1
            raw = json.dumps([
                {"id": "j1", "type": "harvest", "quantity": n,
                 "source": r.id, "material": goal.object,
                 "origin": "deterministic"},
                {"id": "j2", "type": "sow", "quantity": n,
                 "target": goal.at, "material": goal.object,
                 "depends_on": ["j1"], "origin": "deterministic"}])
            prompt, index = build_planner_prompt(wm, goal, inv, fixtures,
                                                 center=(bp2[0], 0, bp2[2]))
            run["planner"] = {"mode": "deterministic",
                              "chosen": {"harvest": {"id": r.id,
                                                     "distance": round(d, 1)},
                                         "sow": {"site": goal.at}},
                              "candidates": sorted(index)}
            jobs, failure = validate_plan(raw, index, inv, goal=goal)
            run["plan"] = {"raw": raw, "latency_ms": 0,
                           "jobs": [j.to_dict() for j in jobs] if jobs else None,
                           "failure": failure.to_dict() if failure else None}
        else:
            import math as _math
            bp = st["Bot"]["Pos"]
            best = None
            for r in wm.resources.values():
                if r.material != goal.object:
                    continue
                if r.observed_quantity < (goal.n or 1):
                    continue
                c = r.cells[0]
                d = _math.hypot(c[0] - bp[0], c[2] - bp[2])
                if best is None or d < best[0]:
                    best = (d, r)
            if best is None:
                run.update({"outcome": "rejected",
                            "reason": "deterministic: no %s resource with "
                                      "sufficient observed quantity" % goal.object})
                return finish(args.out, run, t0)
            d, r = best
            raw = json.dumps({"id": "j1", "type": goal.verb,
                              "quantity": goal.n or 1, "source": r.id,
                              "origin": "deterministic"})
            prompt, index = build_planner_prompt(wm, goal, inv, fixtures,
                                                 center=(bp[0], 0, bp[2]))
            run["planner"] = {"mode": "deterministic",
                              "chosen": {"id": r.id, "distance": round(d, 1),
                                          "observed": r.observed_quantity},
                              "candidates": sorted(index)}
            jobs, failure = validate_plan(raw, index, inv, goal=goal)
            run["plan"] = {"raw": raw, "latency_ms": 0,
                           "jobs": [j.to_dict() for j in jobs] if jobs else None,
                           "failure": failure.to_dict() if failure else None}
    else:
        prompt, index = build_planner_prompt(wm, goal, inv, fixtures,
                                             center=(st["Bot"]["Pos"][0], 0,
                                                    st["Bot"]["Pos"][2]))
        run["planner"] = {"mode": "llm",
                          "prompt_chars": len(prompt),
                          "candidates": sorted(index)}
        raw, ms = call_llm(args.llm, args.llm_model, prompt)
        jobs, failure = validate_plan(raw, index, inv, goal=goal)
        run["plan"] = {"raw": raw[:600], "latency_ms": ms,
                       "jobs": [j.to_dict() for j in jobs] if jobs else None,
                       "failure": failure.to_dict() if failure else None}
    if failure is not None:
        run.update({"outcome": "rejected",
                    "reason": "%s (%s): %s"
                    % (failure.code, failure.layer, failure.detail)})
        return finish(args.out, run, t0)

    # 4. the queue drives execution (R2: strictly sequential)
    base = tuple(st["Bot"]["Pos"])
    if ops:
        jobs = ops + jobs   # already executed pre-planning (2b)
    gs = GoalState(goal, jobs,
                  ("planner:%s + operator-supply" if ops
                   else "planner:%s") % args.llm_model)
    for op in ops:
        gs.job_status[op.id] = "done"
        gs.log(op.id, "job_done",
               "operator supply - deterministic, pre-planning (12.10a)")
        gs.record_measured(op.material, op.quantity or 1)
    job = gs.start()
    botref = [bot]
    while job is not None and gs.status == "running":
        run_jobs(pol, bot, base, gs, job, run, wm, botref=botref)
        bot = botref[0]
        job = gs.next_job()

    run["queue"] = gs.to_dict()
    run["worldSnapshot"] = wm.to_dict()
    run["outcome"] = gs.status
    print("GOAL %s: %s  (%d jobs, %ds)"
          % (gs.status.upper(), goal.describe(), len(jobs),
             int(time.time() - t0)))
    if gs.failure:
        print("  failure: %s - %s" % (gs.failure.code, gs.failure.detail))
    finish(args.out, run, t0)


def _is_food_preempt(detail):
    """The food-pressure interrupt signatures (the mod's forage
    controller records them on the preempted job and on refused
    retries). The mission re-runs the job after the episode - it is
    NOT a plan failure (2026-10-04: the bot survives its mission by
    foraging; the interrupted job is retried, the plan stands)."""
    return bool(detail) and any(s in detail for s in
                                ("preempted:food_pressure",
                                 "refused:foraging"))

def wait_not_foraging(pol, bot, timeout=300):
    """Wait out the mod-side forage episode. It is mod-driven
    (PolisForageController) and self-terminates - satiation, target
    exhaustion, or its 4-minute watchdog - so r2 only polls
    state.Bot.Foraging. Never re-issues a job action during it: that
    is what the mod refuses ("refused:foraging")."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        st = pol.state(bot)
        if not (st.get("Bot") or {}).get("Foraging"):
            return True
        time.sleep(2)
    return False

def run_jobs(pol, bot, base, gs, job, run, wm, botref=None):
    wm.new_tick(reason="pre_action", caused_by=job.id)
    if job.type in ("mine", "harvest") and job.source:
        wm.record_claim(job.source, job.id, bot)
    elif job.type in ("place", "build", "build_plan"):
        wm.record_claim(job.target, job.id, bot)
    t0 = time.time()
    if botref is not None:
        bot = botref[0]
    try:
        (ok, detail, measured,
         execution, oracle) = execute_job(pol, bot, base, job, wm, run,
                                           botref=botref)
        # The food-pressure interrupt: if the job was preempted (or
        # refused mid-forage), the meal runs out first and the SAME
        # job is re-run - up to two times. The plan is untouched.
        attempts = 0
        while not ok and _is_food_preempt(detail) and attempts < 2:
            attempts += 1
            run["steps"].append({
                "job": job.id, "type": job.type, "ok": False,
                "detail": detail,
                "note": "food-pressure: job interrupted, waiting out "
                        "the forage episode (attempt %d)" % attempts,
                "origin": job.origin,
                "execution": execution, "oracle": {},
                "wall_s": round(time.time() - t0, 1)})
            print("  [r2] job %s preempted by food pressure - "
                  "waiting for the forage episode to finish" % job.id)
            if not wait_not_foraging(pol, bot):
                detail = ("food-pressure: forage episode did not end "
                          "in 300s (stuck?); job not re-run")
                break
            print("  [r2] forage episode done - re-running job %s "
                  "(attempt %d)" % (job.id, attempts))
            wm.new_tick(reason="pre_action_retry", caused_by=job.id)
            if botref is not None:
                bot = botref[0]
            (ok, detail, measured,
             execution, oracle) = execute_job(pol, bot, base, job, wm, run,
                                              botref=botref)
    except Exception as e:
        import traceback
        open("/tmp/r2-job-traceback.txt", "w").write(
            "".join(traceback.format_exception(type(e), e,
                                               e.__traceback__)))
        ok, detail, measured = False, "exception: %r" % e, {}
        execution, oracle = {"exception": "%r" % e}, {}
    run["steps"].append({
        "job": job.id, "type": job.type, "ok": ok,
        "detail": detail, "measured": measured,
        "origin": job.origin,
        "execution": execution,   # the engine's verdict on the action
        "oracle": oracle,         # the fresh-world check of the result
        "wall_s": round(time.time() - t0, 1)})
    if job.type in ("mine", "harvest", "chop", "forage"):
        # a cell-targeted job (campaign) has no resource record; a
        # resource job's measured drop corrects the record's claim
        rec = wm.resources.get(job.source) if job.source else None
        if rec is not None and measured:
            for code, qty in measured.items():
                rec.record_drop(classify(code)[1], wm.seq,
                                time.monotonic() * 1000,
                                int(time.time() * 1000))
                break
        for code, qty in measured.items():
            gs.record_measured(classify(code)[1], qty)
        if job.source:
            wm.release_claim(job.source)
    if job.type in ("place", "build"):
        wm.release_claim(job.target)
        gs.consume(job.material, job.quantity or 1)
    if job.type == "build_plan":
        wm.release_claim(job.target)
    if job.type == "craft" and ok and measured:
        # the MEASURED output is the ledger number (the engine's
        # outQty, not the plan's guess); the consumed ingredients are
        # already negative deltas in `measured`
        out = job.quantity or 1
        mat = classify(job.material)[1]
        for code, qty in measured.items():
            if classify(code)[1] == mat:
                out = qty
                break
        gs.record_measured(mat, out)
    if ok:
        gs.job_done(job, detail)
    else:
        code = "fixture_failed" if job.type in ("place", "build",
                                               "build_plan") \
            else "job_budget_exhausted"
        gs.job_failed(job, Failure(code, detail))


def call_llm(llm, model, prompt, timeout=180):
    t0 = time.time()
    r = v5.http_json(llm + "/v1/chat/completions", {
        "model": model, "temperature": 0, "max_tokens": 600,
        "chat_template_kwargs": {"enable_thinking": False},
        "messages": [{"role": "system",
                      "content": "You answer with ONE JSON value only."},
                     {"role": "user", "content": prompt}]}, timeout=timeout)
    ms = int((time.time() - t0) * 1000)
    try:
        msg = r["choices"][0]["message"]
        text = (msg.get("content") or msg.get("reasoning_content") or "")
    except Exception:
        text = ""
    return text.strip(), ms


def finish(out, run, t0):
    run["finished"] = time.strftime("%Y-%m-%d %H:%M:%S %Z")
    run["wall_s"] = round(time.time() - t0, 1)
    path = os.path.join(REPO, out)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(run, f, indent=1)
    print("wrote %s" % out)


if __name__ == "__main__":
    main()
