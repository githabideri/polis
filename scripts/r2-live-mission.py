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

Sanitization: the run JSON records model names and game-internal facts
only - no host names or addresses (the repo is publication-staged).
"""
import argparse
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
from r2.embodiment import embodiment as _embodiment_fn  # 09-29: the body-vs-solid-world check
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
}

#: material name -> the BLOCK code a place/build of it leaves in the
#: world (the oracle's count predicate). granite's placeable block is
#: rock-granite (the 2026-09-28 probe: the item is stone-granite, the
#: placed block is rock-granite).
MATERIAL_BLOCK = {"granite": "rock-granite", "stone": "rock-granite"}


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


def boot(pol, radius=12):
    """Fresh bot + first world observation. Returns (bot, wm, state)."""
    pol.sweep_bots(keep=None)
    time.sleep(2)
    r = v5.http_json(pol.base + "/polis/command",
                     {"cmd": "spawn", "args": [],
                      "context": {"playerUid": pol.uid}})
    bot = (r.get("Data") or {}).get("id")
    st = pol.state(bot)
    pos = st["Bot"]["Pos"]
    wm = WorldModel()
    wm.new_tick(reason="planner_scan")
    x0, z0 = int(pos[0]), int(pos[2])
    scan = pol.cmd("scan", [str(x0 - radius), "2", str(z0 - radius),
                            str(x0 + radius), "6", str(z0 + radius)], bot)
    wm.observe_scan(scan, reason="planner_scan")
    return bot, wm, st


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


def register_site(wm, pol, bot, goal, fixtures):
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
            cell, empty = None, False
            for dx in range(2, 6):
                cand = (bx + dx, 3, bz)
                blocks = pol.cell_blocks(bot, cand, pad=0)
                filled = any(b.get("pos") == [cand[0], cand[1], cand[2]]
                             for b in blocks)
                if not filled:
                    cell, empty = list(cand), True
                    break
            if cell is None:  # everything filled - the site cannot be a
                cell = [bx + 2, 3, bz]   # place target (empty cell absent)
            wm.register_fixture(goal.at, "build-site", cell, "empty")
            wm.observe_fixture(goal.at, empty, reason="fixture_setup")
    for fid, f in sorted(wm.fixtures.items()):
        cond = wm.fixture_observations.get(fid)
        out.append({"id": fid, "kind": f.kind,
                    "requirement": f.requirement,
                    "condition": cond.present if cond else None})
    return out


def execute_job(pol, bot, base, job, wm, run):
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
        r = pol.cmd("give", [item, str(qty)], bot)
        ok = bool(r.get("Ok"))
        st = pol.state(bot)
        inv = inventory_of(st)
        got = inv.get(item, 0)
        if ok:
            ok = got >= qty
        measured = {item: got}
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

    # resource-targeted jobs: the target cell is the resource's
    # representative cell (measured world fact, not model output)
    rec = wm.resources.get(job.source) if job.type in (
        "mine", "harvest", "pickup") else None
    if job.type in ("mine", "harvest", "pickup"):
        if rec is None:
            return (False, "resource %s vanished from the model" % job.source,
                    measured, {}, {"block_gone": None,
                                   "measured": measured})
        cell = rec.cells[0]
        pre = inventory_of(pol.state(bot))
        # the mine path needs a tool (granite is tier 2): v5's mission
        # setup gave one implicitly; the live orchestrator does the same
        # deterministically and records it (harness privilege)
        st0 = pol.state(bot)
        b0 = st0.get("Bot") or {}
        tool_codes = set()
        for k in ("RightHand", "LeftHand"):
            it = b0.get(k)
            if it and it.get("Code"):
                tool_codes.add(it["Code"])
        for it in (b0.get("Backpack") or []):
            if it.get("Code"):
                tool_codes.add(it["Code"])
        if job.type == "mine" and not any(
                (t or "").startswith(("pickaxe", "shovel", "axe", "hoe"))
                for t in tool_codes):
            tr = pol.cmd("give", ["pickaxe-iron", "1"], bot)
            pre = inventory_of(pol.state(bot))
            detail = ("%s %s -> gave pickaxe-iron ok=%s; "
                      % (job.type, rec.code, bool(tr.get("Ok"))))
        else:
            detail = "%s %s -> " % (job.type, rec.code)
        # 13.6 step 1: APPROACH resolution. goto(position) and
        # approach(target, interaction) are separate concepts: a mine/
        # harvest job means "interact successfully with the target
        # block" - for an occupied solid block the valid destinations
        # are the neighbouring walkable cells. The driver walks the
        # candidates (target first, then neighbours by distance, solids
        # filtered), retries on stuck/range/LOS, and stops on a
        # definitive engine verdict. From the queue's perspective this
        # whole loop is ONE job attempt; the per-candidate log goes to
        # the run JSON.
        cmd_name = {"mine": "mine", "harvest": "harvestcrop"}.get(job.type)
        solid = [b["pos"] for b in pol.cell_blocks(bot, cell, pad=2)
                 if (b.get("code") or "") != "game:air"]
        from_pos = tuple(pol.state(bot)["Bot"]["Pos"])

        def _goto(c):
            return v5.goto_wait(pol, bot, c, timeout=25)

        def _act():
            r = pol.cmd(cmd_name, [str(cell[0]), str(cell[1]),
                                   str(cell[2]), "true"], bot)
            st_p = pol.state(bot)
            pre_ms = st_p.get("LastActionMs") or 0
            t0 = time.time()
            la2 = {}
            while time.time() - t0 < 45:
                st2 = pol.state(bot)
                la2 = st2.get("LastAction") or {}
                if la2.get("Name") in (cmd_name, job.type) \
                        and la2.get("Ok") is not None \
                        and (st2.get("LastActionMs") or 0) > pre_ms:
                    break
                time.sleep(1)
            return {"ok": la2.get("Ok") is True, "last_action": la2}

        if cmd_name is not None:
            aok, adetail, attempts, la = r2approach.approach(
                _goto, _act, from_pos, cell, solid)
        else:
            # pickup targets an ITEM entity, not a block cell - v5's
            # item-entity approach stands
            res = v5.execute(pol, bot, "pickup_item", cell, base, "pickup")
            la = pol.state(bot).get("LastAction") or {}
            aok = bool(res.get("ok"))
            adetail = ("pickup -> %s" % (res.get("msg") or
                                         la.get("Msg") or ""))
            attempts = []
        # the drop lands in the cargo ASYNCHRONOUSLY (measured ~8 s after
        # the block is gone, run 12) - poll for it instead of a fixed
        # sleep; the block-gone check and the cargo diff are separate
        # oracles on the same fresh observations
        blocks = pol.cell_blocks(bot, cell)
        # 'gone' must be vacuity-proof: an empty scan (failure, air box)
        # is NOT proof the block is gone - the box always contains the
        # ground layer, so a non-empty scan is expected
        gone = bool(blocks) and not any(
            b.get("code") == rec.code and b.get("pos") == list(cell)
            for b in blocks)
        la_ok = la.get("Name") in ("mine", "mine_target", "harvestcrop",
                                   "harvest_target", "pickup",
                                   "pickup_item") \
            and la.get("Ok") is True
        post = {}
        for _ in range(9):  # up to ~18 s for the cargo registration
            time.sleep(2)
            post = inventory_of(pol.state(bot))
            if any(post.get(k, 0) > pre.get(k, 0)
                   for k in set(pre) | set(post)):
                break
        for k in set(pre) | set(post):
            if post.get(k, 0) > pre.get(k, 0):
                measured[k] = post.get(k, 0) - pre.get(k, 0)
        ok = aok and gone
        detail += (" | %s | last_action_ok=%s (%s) gone=%s measured=%s"
                   % (adetail, la.get("Ok"), (la.get("Msg") or "")[:60],
                      gone, measured))
        return ok, detail, measured, \
            {"last_action": {k: la.get(k) for k in
                             ("Name", "Ok", "Msg")},
             "approach_attempts": attempts}, \
            {"block_gone": gone, "measured": measured}

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

        def _item(m):
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
            try:
                v5.goto_wait(pol, bot, ev)
            except Exception:
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
        for phase, cells in plan.phases(origin):
            for cell, mat in cells:
                total += 1
                if _has(mat, cell):
                    landed += 1
                    parts.append("%s%s:pre" % (phase, cell))
                    continue
                L = cell[1]  # the block's layer; the bot's feet go to L
                if phase == "floor":
                    # stand OUTSIDE the footprint, adjacent to the cell
                    cands = [[cell[0] - 1, L, cell[2]],
                             [cell[0] + 1, L, cell[2]],
                             [cell[0], L, cell[2] - 1],
                             [cell[0], L, cell[2] + 1]]
                    cands = [c for c in cands
                             if not _inside(c[0], c[2])] or cands
                else:
                    # stand at foot level on a NEIGHBOUR (never the
                    # target cell - the engine refuses places into the
                    # bot's own cell); neighbours with support a layer
                    # down come first (the plan's own earlier phases)
                    cands = [[cell[0] + dx, L, cell[2] + dz]
                             for dx, dz in ((0, 1), (1, 0), (0, -1),
                                            (-1, 0))]
                    def _supported(c):
                        below = [c[0], L - 1, c[2]]
                        bs = pol.cell_blocks(bot, tuple(below),
                                             pad=0) or []
                        return any(b.get("pos") == list(below) for b in bs)
                    cands.sort(key=lambda c: 0 if _supported(c) else 1)
                placed_here = False
                for cand in cands:
                    try:
                        v5.goto_wait(pol, bot, cand)
                    except Exception:
                        # a failed goto is not automatically "try the
                        # next candidate": if the body itself is the
                        # problem (embedded/trapped), no candidate
                        # helps - abort with the structural reason
                        st, det = _emb()
                        if st != "OK":
                            return (False, "structural: standing goto "
                                    "for %s%s failed and the body is %s "
                                    "(- %s)" % (phase, cell, st, det),
                                    measured, {}, {"cells": None})
                        continue
                    res = v5.execute(pol, bot, "place_block", cell,
                                     base, "build",
                                     buildblock=_item(mat))
                    time.sleep(1)
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
                        break
                    parts.append("%s%s:attempt(ok=%s)"
                                 % (phase, cell, res.get("ok")))
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

    if job.type in ("goto", "travel"):
        fix = wm.fixtures.get(job.target)
        cell = tuple(fix.cell) if fix else base
        g = v5.goto_wait(pol, bot, cell)
        return (bool(g.get("ok")), "goto %s -> %s" % (job.target,
                                                      g.get("msg")),
                measured, {"goto": g.get("msg")},
                {"arrived": bool(g.get("ok"))})
    if job.type == "wait":
        time.sleep(2)
        return True, "waited", measured, {}, {"waited": True}
    return (False, "unhandled job type %s" % job.type, measured, {},
            {})


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
    ap.add_argument("--pregive", action="append", default=[],
                    help="external setup before the goal: '<item> <qty>' "
                         "(logged in the run JSON - a harness privilege, "
                         "not a world fact)")
    args = ap.parse_args()

    run = {"started": time.strftime("%Y-%m-%d %H:%M:%S %Z"),
           "model": args.llm_model,
           "goal_line": args.goal,
           "steps": []}
    t0 = time.time()
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
    bot, wm, st = boot(pol)
    run["bot"] = bot
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
    fixtures = register_site(wm, pol, bot, goal, None)
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
            if getattr(goal, "supply", None) != "external":
                missing = {m: (q, inv.get(m, 0))
                           for m, q in bp.materials.items()
                           if inv.get(m, 0) < q}
                if missing:
                    run.update({"outcome": "rejected",
                                "reason": "resource_not_found: %s "
                                          "(declare 'supply external' "
                                          "for harness supply)"
                                % ", ".join("%s need %d have %d" % (m, q, h)
                                            for m, (q, h) in
                                            sorted(missing.items()))})
                    return finish(args.out, run, t0)
            bp5 = st["Bot"]["Pos"]
            raw = json.dumps({"id": "j1", "type": "build_plan",
                              "plan": goal.object, "target": goal.at,
                              "origin": "deterministic"})
            prompt, index = build_planner_prompt(wm, goal, inv, fixtures,
                                                 center=(bp5[0], 0,
                                                         bp5[2]))
            run["planner"] = {"mode": "deterministic",
                              "chosen": {"plan": goal.object,
                                         "site": goal.at,
                                         "blocks": bp.total_blocks(),
                                         "supply": "external"
                                         if getattr(goal, "supply",
                                                    None) == "external"
                                         else "inventory"},
                              "candidates": sorted(index)}
            jobs, failure = validate_plan(raw, index, inv, goal=goal)
            run["plan"] = {"raw": raw, "latency_ms": 0,
                           "jobs": [j.to_dict() for j in jobs] if jobs else None,
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
    while job is not None and gs.status == "running":
        run_jobs(pol, bot, base, gs, job, run, wm)
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


def run_jobs(pol, bot, base, gs, job, run, wm):
    wm.new_tick(reason="pre_action", caused_by=job.id)
    if job.type in ("mine", "harvest"):
        wm.record_claim(job.source, job.id, bot)
    elif job.type in ("place", "build", "build_plan"):
        wm.record_claim(job.target, job.id, bot)
    t0 = time.time()
    try:
        (ok, detail, measured,
         execution, oracle) = execute_job(pol, bot, base, job, wm, run)
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
    if job.type in ("mine", "harvest"):
        rec = wm.resources.get(job.source)
        if rec is not None and measured:
            for code, qty in measured.items():
                rec.record_drop(classify(code)[1], wm.seq,
                                time.monotonic() * 1000,
                                int(time.time() * 1000))
                break
        for code, qty in measured.items():
            gs.record_measured(classify(code)[1], qty)
        wm.release_claim(job.source)
    if job.type in ("place", "build"):
        wm.release_claim(job.target)
        gs.consume(job.material, job.quantity or 1)
    if job.type == "build_plan":
        wm.release_claim(job.target)
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
