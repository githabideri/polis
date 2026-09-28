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
from r2.plancheck import validate_plan, check_goal
from r2.jobqueue import GoalState
from r2.jobs import Goal, Job, Failure
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
    authoritative identity, doc 5.3). The site is the nearest EMPTY cell
    2-5 east of the bot (the world persists: earlier runs leave filled
    sites, so the first empty cell is searched, not assumed)."""
    out = []
    if getattr(goal, "at", None) and goal.at not in wm.fixtures:
        st = pol.state(bot)
        pos = st["Bot"]["Pos"]
        bx, bz = int(pos[0]), int(pos[2])
        cell = None
        for dx in range(2, 6):
            cand = (bx + dx, 3, bz)
            blocks = pol.cell_blocks(bot, cand, pad=0)
            if not any(b.get("pos") == [cand[0], cand[1], cand[2]]
                       for b in blocks):
                cell = list(cand)
                break
        if cell is None:  # everything filled - use the first anyway
            cell = [bx + 2, 3, bz]
        wm.register_fixture(goal.at, "build-site", cell, goal.object)
        present = pol.site_filled(bot, tuple(cell))
        wm.observe_fixture(goal.at, present, reason="fixture_setup")
    for fid, f in sorted(wm.fixtures.items()):
        cond = wm.fixture_observations.get(fid)
        out.append({"id": fid, "kind": f.kind,
                    "requirement": f.requirement,
                    "condition": cond.present if cond else None})
    return out


def execute_job(pol, bot, base, job, wm, run):
    """One job's actuation + oracle. Returns (ok, detail, measured).
    All game checks are FRESH observations (the 12.6 invariant)."""
    measured = {}
    if job.type == "give_tool":
        item = GIVE_ITEM.get(job.material, job.material)
        r = pol.cmd("give", [item, str(job.quantity or 1)], bot)
        ok = bool(r.get("Ok"))
        st = pol.state(bot)
        inv = inventory_of(st)
        got = inv.get(item, 0)
        if ok:
            ok = got >= (job.quantity or 1)
        measured = {item: got}
        return ok, ("gave %s x%d -> carried %d"
                    % (item, job.quantity or 1, got)), measured

    # resource-targeted jobs: the target cell is the resource's
    # representative cell (measured world fact, not model output)
    rec = wm.resources.get(job.source) if job.type in (
        "mine", "harvest", "pickup") else None
    if job.type in ("mine", "harvest", "pickup"):
        if rec is None:
            return False, "resource %s vanished from the model" % job.source, \
                measured
        cell = rec.cells[0]
        action = {"mine": "mine_target", "harvest": "harvest_target",
                  "pickup": "pickup_item"}[job.type]
        mission = {"mine": "mine", "harvest": "harvest",
                   "pickup": "pickup"}[job.type]
        pre = inventory_of(pol.state(bot))
        res = v5.execute(pol, bot, action, cell, base, mission)
        time.sleep(2)
        gone = not pol.cell_blocks(bot, cell) or not any(
            b.get("code") == rec.code and b.get("pos") == list(cell)
            for b in pol.cell_blocks(bot, cell))
        post = inventory_of(pol.state(bot))
        for k in set(pre) | set(post):
            if post.get(k, 0) > pre.get(k, 0):
                measured[k] = post[k] - pre[k]
        ok = bool(res.get("ok")) and gone
        msg = "%s %s -> exec_ok=%s gone=%s measured=%s" % (
            job.type, rec.code, res.get("ok"), gone, measured)
        return ok, msg, measured

    if job.type == "place":
        fix = wm.fixtures.get(job.target)
        if fix is None:
            return False, "site %s unknown" % job.target, measured
        cell = fix.cell
        item = GIVE_ITEM.get(job.material, job.material)
        res = v5.execute(pol, bot, "place_block", cell, base, "build",
                         buildblock=item)
        time.sleep(2)
        filled = pol.site_filled(bot, tuple(cell))
        cond = wm.observe_fixture(job.target, filled,
                                  reason="oracle")
        ok = bool(res.get("ok")) and filled
        msg = ("place %s -> exec_ok=%s site_filled=%s oracle=%s" %
               (item, res.get("ok"), filled, cond))
        return ok, msg, measured

    if job.type in ("goto", "travel"):
        fix = wm.fixtures.get(job.target)
        cell = tuple(fix.cell) if fix else base
        g = v5.goto_wait(pol, bot, cell)
        return bool(g.get("ok")), "goto %s -> %s" % (job.target,
                                                    g.get("msg")), measured
    if job.type == "wait":
        time.sleep(2)
        return True, "waited", measured
    return False, "unhandled job type %s" % job.type, measured


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--harness", required=True)
    ap.add_argument("--uid", required=True)
    ap.add_argument("--llm", required=True)
    ap.add_argument("--llm-model", required=True)
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
    inv = normalize_inv(inventory_of(st))
    fixtures = register_site(wm, pol, bot, goal, None)
    gfail = check_goal(goal, [f["id"] for f in fixtures])
    if gfail is not None:
        run.update({"outcome": "rejected",
                    "reason": "%s: %s" % (gfail.code, gfail.detail)})
        return finish(args.out, run, t0)

    # 3. plan (27B) + validate (deterministic, goal-aware)
    prompt, index = build_planner_prompt(wm, goal, inv, fixtures,
                                         center=(st["Bot"]["Pos"][0], 0,
                                                st["Bot"]["Pos"][2]))
    run["planner"] = {"prompt_chars": len(prompt),
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
    if getattr(goal, "supply", None) == "external" and goal.verb == "place":
        # 12.10 remediation (a): the operator declared external supply at
        # intake - the give_tool job is inserted DETERMINISTICALLY (no LLM)
        # so the planner sees a world it can plan; the queue executes both.
        op = Job("j0", "give_tool", source="operator",
                 material=goal.object, quantity=goal.n or 1)
        jobs = [op] + jobs
        run["supply"] = {"declared": True, "job": op.to_dict()}
    gs = GoalState(goal, jobs,
                  ("planner:%s + operator-supply" if "supply" in run
                   else "planner:%s") % args.llm_model)
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
    elif job.type == "place":
        wm.record_claim(job.target, job.id, bot)
    t0 = time.time()
    try:
        ok, detail, measured = execute_job(pol, bot, base, job, wm, run)
    except Exception as e:
        ok, detail, measured = False, "exception: %r" % e, {}
    run["steps"].append({
        "job": job.id, "type": job.type, "ok": ok,
        "detail": detail, "measured": measured,
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
    if job.type == "place":
        wm.release_claim(job.target)
        gs.consume(job.material, job.quantity or 1)
    if ok:
        gs.job_done(job, detail)
    else:
        code = "fixture_failed" if job.type == "place" \
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
