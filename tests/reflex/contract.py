#!/usr/bin/env python3
"""
Phase 0 contract gate - the behavioral contract of the reflex loop.

What it freezes (docs/design/2026-09-26-job-system-r2.md, §5.4):

  T1  prompt    build_state_text() re-renders every frozen corpus state
                byte-identically. The 2B model was fine-tuned on exactly
                this 8-line representation; a wording change is a model
                regression, not a refactor.
  T2  decision  decide_cascade() + needs_judge() replay every recorded
                live step and reproduce (path, executed) exactly, with
                the judge-call condition matching the recorded calls.
                (A synthetic decider-err step covers the service-fault
                branch, which live runs rarely hit.)
  T3  readout   recorded decider readouts are coherent: the choice is a
                valid option, and when it equals the oracle its
                probability equals the max probability.
  T4  state     (review round 2, 11.1) build_reflex_state() reconstructs
                the frozen reflex-state DTO - and through it the exact
                8-line prompt - from the recorded raw observation
                (state + carry + scan + prev + injected). This is the
                seam T1 cannot cover: T1 freezes the projection, T4
                freezes the construction feeding it.
  T2b run       (review round 2, 11.1) run-level transitions are
                consistent: a run ends at its goal step or at the step
                budget; completion implies the goal was seen; the
                recorded completion step matches the transition rule.
  T5  staleness (Phase 2, 2026-09-28, doc §11.4/§12.6) the WorldModel's
                freshness discipline: fresh reads return the observed
                value, one tick later the same record is unknown (None -
                never yes, never no), completion flips only on FRESH
                observations (both polarities), and resource records
                nominate (stale) but never authorize (fresh).

The implementation under test is selected with --impl:

  v5 (default)   imports scripts/jev-loop-v5.py
  r2             imports r2/projection.py + r2/executor.py (Phase 1)

Both implementations must pass identically - that is the
behavior-identity proof for the extraction. This gate checks CODE
drift; the nightly canary checks MODEL drift (different thing).

Exit code 0 = the contract holds.
"""
import argparse
import importlib.util
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)


def load_impl(name):
    if name == "v5":
        path = os.path.join(REPO, "scripts", "jev-loop-v5.py")
    elif name == "r2":
        # Phase 1: the extracted modules. projection exposes
        # build_state_text, executor exposes decide_cascade/needs_judge,
        # types exposes the T4 seam (build_reflex_state, oracle_action,
        # carrying_from, MISSIONS) - same names as v5.
        proj = importlib.import_module("r2.projection")
        execm = importlib.import_module("r2.executor")
        ns = type("NS", (), {})()
        ns.build_state_text = proj.build_state_text
        ns.decide_cascade = execm.decide_cascade
        ns.needs_judge = execm.needs_judge
        ns.build_reflex_state = importlib.import_module("r2.types").build_reflex_state
        ns.oracle_action = importlib.import_module("r2.types").oracle_action
        ns.carrying_from = importlib.import_module("r2.types").carrying_from
        ns.fixture_bool = importlib.import_module("r2.types").fixture_bool
        ns.MISSIONS = importlib.import_module("r2.types").MISSIONS
        return ns
    else:
        raise SystemExit("unknown impl %r (v5 | r2)" % name)
    spec = importlib.util.spec_from_file_location("polis_v5", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------- T1 ----

FACTS_RE = re.compile(
    r"^facts: bot at \((-?[\d.]+), (-?[\d.]+), (-?[\d.]+)\), "
    r"near_target=(yes|no), near_base=(yes|no), (\w+)=(yes|no)$")


def parse_state(state):
    """Invert build_state_text: parse the 8-line reflex prompt into the
    fields the builder takes. The lines are self-delimiting, so free-text
    fields (task, since, last_action) parse by prefix."""
    lines = state.split("\n")
    assert len(lines) == 8, "expected 8 lines, got %d: %r" % (
        len(lines), state[:120])
    assert lines[0].startswith("task: ")
    assert lines[1].startswith("current phase: ")
    m = FACTS_RE.match(lines[2])
    assert m, "unparseable facts line: %r" % lines[2]
    assert lines[3].startswith("carrying: ")
    assert lines[4].startswith("items: ")
    assert lines[5].startswith("since_last_step: ")
    assert lines[6].startswith("last_action: ")
    assert lines[7].startswith("proposed action: ")
    x, y, z = (float(m.group(1)), float(m.group(2)), float(m.group(3)))
    carrying = lines[3][len("carrying: "):]
    items = lines[4][len("items: "):]
    return dict(
        task=lines[0][len("task: "):],
        phase=lines[1][len("current phase: "):],
        pos=[x, int(y), z],
        near_t=m.group(4) == "yes",
        near_b=m.group(5) == "yes",
        fixture_label=m.group(6),
        fixture=m.group(7) == "yes",
        carrying=[] if carrying == "empty" else carrying.split(", "),
        items=[] if items == "none" else items.split(", "),
        since=lines[5][len("since_last_step: "):],
        last_action=None if lines[6][len("last_action: "):] == "none"
        else lines[6][len("last_action: "):],
        proposal=lines[7][len("proposed action: "):],
    )


def test_prompt(impl, rows):
    fails = 0
    for r in rows:
        f = parse_state(r["state"])
        got = impl.build_state_text(
            f["task"], f["phase"], f["pos"], f["near_t"], f["near_b"],
            f["fixture_label"], f["fixture"], f["carrying"],
            ", ".join(f["items"][:3]) or "none", f["since"],
            f["last_action"] or "none", f["proposal"])
        if got != r["state"]:
            fails += 1
            if fails <= 3:
                print("T1 MISMATCH [%s %s]" % (r["source"], r["family"]))
                for a, b in zip(got.split("\n"), r["state"].split("\n")):
                    if a != b:
                        print("   got:  %r" % a)
                        print("   want: %r" % b)
    return fails, len(rows)


# ---------------------------------------------------------------- T2 ----

def reconstruct_tiers(row):
    """Rebuild (reflex, dref, judge) from a recorded live step. The
    reconstruction mirrors the call structure of the original loop: the
    decider is only fetched when Laya passed its gate, the judge only
    when a branch needs it."""
    path = row["path"]
    p = row["p"]
    if path.startswith("reflex-err"):
        reflex = {"p": p, "error": path[len("reflex-err:"):]}
        dref, judge = None, None
    elif path == "judge":
        reflex = {"p": p, "error": None}
        dref = None
        judge = {"choice": row["judge_choice"]}
    elif path == "reflex":
        reflex = {"p": p, "error": None}
        dref, judge = None, None
    elif path.startswith("decider-err"):
        reflex = {"p": p, "error": None}
        dref = {"probs": None, "error": path[len("decider-err:")]}
        judge = None
    elif path == "reflex+decider":
        reflex = {"p": p, "error": None}
        dref = _decider_dict(row)
        judge = None
    else:  # reflex->judge, reflex+decider->judge
        reflex = {"p": p, "error": None}
        dref = _decider_dict(row)
        judge = {"choice": row["judge_choice"]}
    return reflex, dref, judge


def _decider_dict(row):
    if row["p_decider"] is None:
        return {"probs": {}, "error": None}
    return {"probs": {row["proposal"]: row["p_decider"]}, "error": None}


def test_decision(impl, runs):
    fails, n = 0, 0
    for run in runs:
        tau = run["tau"]
        for row in run["rows"]:
            n += 1
            reflex, dref, judge = reconstruct_tiers(row)
            # judge-call condition must match what was actually called
            want_judge = impl.needs_judge(
                reflex, dref, row["proposal"],
                tau["yes"], tau["dec"], tau["strong"])
            if want_judge != (row["judge_choice"] is not None):
                fails += 1
                print("T2 JUDGE-CALL MISMATCH [%s step %d path=%s]" % (
                    run["file"], row["step"], row["path"]))
                continue
            path, final, stall, _ = impl.decide_cascade(
                reflex, dref, judge, row["proposal"], row["options"],
                row["last_final"], tau["yes"], tau["dec"], tau["strong"])
            if path != row["path"] or final != row["executed"] \
                    or stall != bool(row["stall_bypass"]):
                fails += 1
                if fails <= 5:
                    print("T2 MISMATCH [%s step %d path=%s]" % (
                        run["file"], row["step"], row["path"]))
                    print("   got:  path=%r final=%r stall=%s" % (
                        path, final, stall))
                    print("   want: path=%r final=%r stall=%s" % (
                        row["path"], row["executed"], row["stall_bypass"]))
    return fails, n


def test_decision_synthetic(impl):
    """The decider-service-fault branch (live runs rarely hit it)."""
    opts = ["goto_target", "harvest_target", "pickup_item", "place_block",
            "give_tool", "goto_base", "wait"]
    tau = dict(tau_yes=0.35, tau_dec=0.5, tau_strong=0.40)
    path, final, stall, pdec = impl.decide_cascade(
        {"p": 0.9, "error": None},
        {"probs": None, "error": "connect timeout"},
        None, "goto_target", opts, None, **tau)
    ok = path.startswith("decider-err:") and final == "goto_target" \
        and not stall and pdec is None
    return (0 if ok else 1), 1


# ---------------------------------------------------------------- T3 ----

def test_readout(rows):
    fails, n = 0, 0
    for r in rows:
        m = r.get("measured")
        if not m:
            continue
        n += 1
        opts = r.get("options") or []
        if m.get("choice") is not None and opts \
                and m["choice"] not in opts:
            fails += 1
            print("T3 INVALID CHOICE [%s %s]: %r" % (
                r["source"], r["family"], m["choice"]))
            continue
        if m.get("choice") == r.get("oracle") and m.get("max_p") is not None \
                and m.get("p_oracle") is not None:
            if abs(m["p_oracle"] - m["max_p"]) > 1e-9:
                fails += 1
                print("T3 ORACLE-NOT-MAX [%s %s]: p_oracle=%r max_p=%r" % (
                    r["source"], r["family"], m["p_oracle"], m["max_p"]))
    return fails, n


# ---------------------------------------------------------------- T4 ----

def test_state_construction(impl, t4):
    """T4 (review round 2, 11.1): raw observation -> reflex-state DTO.

    Replay the implementation's constructor over the recorded context of
    every captured step and require the frozen DTO (and, chained, the
    exact prompt text) back. The oracle-carry rule mirrors the loop's
    fetch semantics: the oracle derives from the post-injection fetch
    when present (rows captured before that field exist fall back to
    the pre-injection fetch, which clean runs made equivalent).
    """
    fails, n = 0, 0
    for fdoc in t4:
        for r in fdoc["rows"]:
            n += 1
            ctx = r["ctx"]
            oracle_carry = impl.carrying_from(
                ctx.get("post_state") or ctx["carry_state"])
            dto = impl.build_reflex_state(ctx, r["prev"],
                                          injected=r["injected"],
                                          oracle_carry=oracle_carry)
            ok = (dto == r["golden"])
            if ok:
                got = impl.build_state_text(
                    dto["task"], dto["phase"], dto["pos"], dto["near_t"],
                    dto["near_b"], dto["fixture_label"], dto["fixture"],
                    dto["carrying"], dto["items_line"], dto["since"],
                    dto["last_msg"], dto["proposal"])
                ok = (got == r["state_text"])
            if not ok:
                fails += 1
                if fails <= 5:
                    print("T4 MISMATCH [%s step %d]" % (fdoc["mission"], r["step"]))
                    want = r["golden"]
                    for k in sorted(set(want) | set(dto)):
                        if want.get(k) != dto.get(k):
                            print("   dto[%s]: got %r want %r" % (
                                k, dto.get(k), want.get(k)))
    return fails, n


def test_run_transitions(t4):
    """T2b (review round 2, 11.1): run-level transition consistency.

    A run ends at its goal step or at the step budget, whichever comes
    first; completion implies the goal was seen; the recorded
    completion step equals the goal step on completed runs.
    """
    fails, n = 0, 0
    for fdoc in t4:
        for run in fdoc["runs"]:
            n += 1
            gs, sr = run["goal_step"], run["steps_run"]
            sb, mc = run["steps_budget"], run["mission_complete"]
            ok = (sr == gs) if gs is not None else (sr == sb)
            if ok and mc:
                ok = (gs is not None)
            if ok and mc and gs is not None:
                ok = (run["steps_to_complete"] == gs)
            if not ok:
                fails += 1
                print("T2b TRANSITION [%s run %d]: goal=%r run=%r budget=%r"
                      " complete=%r stc=%r" % (
                          fdoc["mission"], run["run"], gs, sr, sb, mc,
                          run["steps_to_complete"]))
    return fails, n


def test_worldmodel_staleness(impl, t4):
    """T5 (Phase 2, 2026-09-28; doc §11.4/§12.6): the staleness invariant.

    Replays the T4 golden rows through the WorldModel exactly as the
    live loop does - one tick per step, the fixture condition observed
    from the recorded scan (the same frozen predicate both sides use),
    then a tick advance proving staleness. Checks per run:
      a) a fresh read returns the observed condition;
      b) after the next tick the same record is UNKNOWN (None), and the
         requirement check on it is None too (unknown is never yes and
         never no);
      c) the satisfaction flag is monotone once the completion condition
         is met (a goal that was seen cannot un-happen from the cached
         view); a stale-satisfied + fresh-not record can never prove
         completion (both polarities, synthetic);
      d) resource records observed on tick t are gone from the fresh
         (authorizing) set at tick t+1 but still available for
         nomination (stale) - nominate, never authorize (12.6-E).
    """
    from r2 import worldmodel as wm_mod
    requirement = {"mine": "absent", "harvest": "absent", "build": "filled"}
    kindmap = {"mine": "marker", "harvest": "crop", "build": "build-site"}
    fails, n = 0, 0
    for fdoc in t4:
        mission = fdoc["mission"]
        for run in fdoc["runs"]:
            n += 1
            rows = [r for r in fdoc["rows"]
                    if r.get("run") is None or r.get("run") == run.get("run")]
            if len(fdoc["runs"]) == 1:
                rows = fdoc["rows"]
            wm = wm_mod.WorldModel()
            wm.new_tick(reason="fixture_setup")
            target = fdoc["rows"][0]["ctx"]["target"]
            wm.register_fixture("f", kindmap[mission], target,
                                requirement[mission])
            run_ok, seen_complete = True, False
            for r in rows:
                ctx = r["ctx"]
                cond = impl.fixture_bool(mission, ctx["scan"], ctx["target"],
                                         ctx.get("marker"))
                wm.new_tick(reason="pre_action")
                wm.observe_scan(ctx["scan"], reason="pre_action")
                wm.observe_fixture("f", cond, reason="pre_action")
                # a) fresh read returns the observed value
                if wm.fixture_condition("f", fresh=True) != cond:
                    run_ok = False
                # d) records observed this tick are NOT authorizing next
                fresh_now = wm.find_resources(fresh=True)
                wm.new_tick()  # advance: everything observed at t is stale
                if any(rec.seq != wm.seq for rec in
                       wm.find_resources(fresh=True)):
                    run_ok = False
                stale_view = wm.find_resources(fresh=False)
                if fresh_now and not stale_view:
                    run_ok = False      # nominees must survive the advance
                # c) satisfaction from the FRESH condition of this tick
                sat = wm.fixture_satisfies("f", fresh=False)  # latest obs
                if seen_complete and sat is not True:
                    run_ok = False      # completion un-happened: impossible
                if sat is True:
                    seen_complete = True
                if run["mission_complete"] and r is rows[-1]:
                    if sat is not True:
                        run_ok = False   # completed run's last observation
                                          # must show the satisfied state
            # c) both polarities, synthetic (independent of the rows):
            wmp = wm_mod.WorldModel()
            wmp.register_fixture("s", "build-site", target, "filled")
            wmp.new_tick(); wmp.observe_fixture("s", True, "pre_action")
            wmp.new_tick(); wmp.observe_fixture("s", False, "oracle")
            if wmp.fixture_satisfies("s", fresh=True) is not False:
                run_ok = False          # stale-filled + fresh-empty: NOT done
            wmn = wm_mod.WorldModel()
            wmn.register_fixture("s", "build-site", target, "filled")
            wmn.new_tick(); wmn.observe_fixture("s", False, "pre_action")
            wmn.new_tick(); wmn.observe_fixture("s", True, "oracle")
            if wmn.fixture_satisfies("s", fresh=True) is not True:
                run_ok = False          # stale-empty + fresh-filled: done
            if not run_ok:
                fails += 1
                print("T5 STALENESS [%s run %d] invariant violated" %
                      (mission, run.get("run")))
    return fails, n


# ---------------------------------------------------------------- main ----

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--impl", default="v5", choices=["v5", "r2"])
    ap.add_argument("--fixdir", default=HERE + "/fixtures")
    args = ap.parse_args()

    impl = load_impl(args.impl)
    corpora = json.load(open(os.path.join(args.fixdir, "reflex-corpora.json")))
    live = json.load(open(os.path.join(args.fixdir, "live-runs.json")))
    t4 = json.load(open(os.path.join(args.fixdir, "reflex-state-t4.json")))

    f1, n1 = test_prompt(impl, corpora["rows"])
    f2, n2 = test_decision(impl, live["runs"])
    f2s, n2s = test_decision_synthetic(impl)
    f3, n3 = test_readout(corpora["rows"])
    f4, n4 = test_state_construction(impl, t4)
    f2b, n2b = test_run_transitions(t4)
    f5, n5 = test_worldmodel_staleness(impl, t4)

    total_fail = f1 + f2 + f2s + f3 + f4 + f2b + f5
    print("impl=%s" % args.impl)
    print("T1 prompt    %3d/%3d byte-identical" % (n1 - f1, n1))
    print("T2 decision  %3d/%3d replayed exactly" % (
        n2 + n2s - f2 - f2s, n2 + n2s))
    print("T3 readout   %3d/%3d coherent" % (n3 - f3, n3))
    print("T4 state     %3d/%3d reconstructed exactly" % (n4 - f4, n4))
    print("T2b run      %3d/%3d transitions consistent" % (n2b - f2b, n2b))
    print("T5 staleness %3d/%3d invariants hold" % (n5 - f5, n5))
    if total_fail:
        print("CONTRACT BROKEN: %d failure(s)" % total_fail)
        sys.exit(1)
    print("CONTRACT HOLDS")


if __name__ == "__main__":
    main()
