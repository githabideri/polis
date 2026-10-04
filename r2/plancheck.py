"""
R2 plan validator - deterministic checks over the planner's JSON plan.

Design doc: section 9 (the validator checklist) and 12.1 (the material
ledger), with violations attributed to the frozen section 5.5 failure
codes. Pure: no model calls, no network. Given (plan_json, index,
inventory) it either returns a list of Job objects (valid plan) or a
Failure (honest rejection with code + layer + detail).

Check order (first failure wins, cheapest first):
  1. parse          -> planner_invalid_json
  2. reject form    -> (explicit model rejection, reason attached)
  3. per-job schema -> planner_invalid_json (type/fields/quantity)
  4. references     -> planner_invalid_reference (id not in the index)
  5. dependencies   -> planner_dependency_error (order/unknown dep)
  6. material ledger-> resource_not_found (consumer without a producer or
     inventory; the mine->place mismatch lands here)
"""

import json

from .jobs import (Job, Failure, JOB_CATALOG, Goal, GoalGrammarError,
                   deps_consistent)

MAX_QUANTITY = 100  # a single job asking for more is a plan smell


def check_goal(goal, fixture_ids):
    """Goal-intake check (runs BEFORE any planning): a goal whose `at`
    names a site not in the fixture registry is outside what the world
    can serve - rejected at intake, never handed to the planner.
    Returns None (ok) or a Failure."""
    at = getattr(goal, "at", None)
    if at and at.startswith("site-") and at not in set(fixture_ids):
        return Failure(
            "resource_not_found",
            "goal references unknown site %r (registry: %s)"
            % (at, sorted(fixture_ids)),
            goal=goal.describe())
    return None


def validate_plan(plan_raw, index, inventory, goal=None, recipes=None):
    """Validate a raw planner response.

    plan_raw: str or object (the model output)
    index:    candidate index from build_planner_prompt
    inventory: {material: qty} at plan time
    recipes:  live grid-recipe table (list of {name, output,
                shapeless, ingredients:[{code, qty}]}) from the harness
                /polis/recipes - required for craft jobs; without it a
                craft plan is rejected (unknown is never yes).

    Returns (jobs, None) on success, (None, Failure) on rejection.
    """
    # 1. parse (boundary normalization, round-2 finding: the 27B returns
    #    a BARE object for single-job plans; a job-shaped dict is
    #    normalized to a one-element list - documented, not invented)
    if isinstance(plan_raw, (str, bytes)):
        try:
            plan_raw = json.loads(plan_raw)
        except (ValueError, TypeError) as e:
            return None, Failure(
                "planner_invalid_json", "unparseable: %s" % e)
    if isinstance(plan_raw, dict) and "reject" in plan_raw:
        return None, Failure(
            "unsupported_goal",
            "planner rejected: %s" % plan_raw.get("reject"))
    if isinstance(plan_raw, dict) and "type" in plan_raw:
        plan_raw = [plan_raw]
    if not isinstance(plan_raw, list) or not plan_raw:
        return None, Failure(
            "planner_invalid_json",
            "plan must be a non-empty JSON list, got %r"
            % type(plan_raw).__name__)

    # 2. per-job schema
    jobs = []
    for i, item in enumerate(plan_raw):
        jid = ("j%d" % (i + 1)) if not isinstance(item, dict) or \
            not item.get("id") else item["id"]
        try:
            j = Job.from_dict(item, job_id=jid)
        except ValueError as e:
            return None, Failure(
                "planner_invalid_json", "%s" % e, job_id=jid)
        if j.quantity and j.quantity > MAX_QUANTITY:
            return None, Failure(
                "planner_invalid_json",
                "quantity %d exceeds the %d cap" % (j.quantity, MAX_QUANTITY),
                job_id=jid)
        # build_plan is GOAL-SCOPED (13.11): it exists in the catalog
        # but only the deterministic compiler may emit it - a planner
        # plan carrying one is outside the vocabulary it was given
        # (the 27B learns it via an A/B round, like sow did).
        if j.type == "build_plan" and \
                getattr(goal, "verb", None) != "build-plan":
            return None, Failure(
                "planner_invalid_json",
                "build_plan is outside the planner vocabulary "
                "(deterministic-compiler scoped)",
                job_id=jid)
        jobs.append(j)

    # 3. references (the trust boundary - 5.2)
    for j in jobs:
        for ref in (j.source, j.target, j.material if j.type in
                    ("place", "build") else None):
            if ref and isinstance(ref, str) and \
                    (ref.startswith("res-") or ref.startswith("site-")):
                if ref not in index:
                    return None, Failure(
                        "planner_invalid_reference",
                        "unknown candidate id %r" % ref, job_id=j.id)
    for j in jobs:
        for f in j.missing_refs():
            return None, Failure(
                "planner_invalid_json",
                "job %s type %s lacks required field %s"
                % (j.id, j.type, f), job_id=j.id)

    # 4. dependencies
    ok, problems = deps_consistent(jobs)
    if not ok:
        return None, Failure(
            "planner_dependency_error",
            "depends_on contradicts list order or references unknown ids: %s"
            % problems, job_id=problems[0] if problems else None)

    # 5. material ledger (12.1): simulate in execution order.
    #    planned quantities are the budgeting input; post-execution the
    #    ledger is corrected with the MEASURED yield.
    avail = dict(inventory or {})
    recipe_by = None
    if recipes is not None:
        recipe_by = {}
        for rc in recipes:
            name = rc.get("name") or rc.get("source")
            if name and rc.get("output"):
                recipe_by.setdefault(name.lower(), rc)
    for j in jobs:
        cat = JOB_CATALOG[j.type]
        # craft (1.22.7 grid crafting): validate against the live recipe
        # table; ingredients are consumed from the ledger, the output
        # added. A craft without a resolvable recipe is rejected -
        # the bot cannot invent recipes.
        if j.type == "craft":
            rc = None
            if recipe_by:
                rc = recipe_by.get((j.source or "").lower())
            if rc is None or rc.get("output") != j.material:
                return None, Failure(
                    "planner_invalid_reference",
                    "craft job %s: recipe %r does not produce %r "
                    "(live recipe table consulted)"
                    % (j.id, j.source, j.material), job_id=j.id)
            if rc.get("shapeless") is False:
                return None, Failure(
                    "planner_invalid_reference",
                    "craft job %s: recipe %r is shaped - the headless "
                    "path supports shapeless recipes only"
                    % (j.id, j.source), job_id=j.id)
            runs = j.quantity or 1
            for ing in rc.get("ingredients") or []:
                code = (ing.get("code") or "").lower()
                qty = max(1, int(ing.get("qty") or 1)) * runs
                if not code:
                    continue
                if avail.get(code, 0) < qty:
                    return None, Failure(
                        "resource_not_found",
                        "craft %s (recipe %s) needs %dx %s for %d run%s, have %d"
                        % (j.id, j.source, qty, code, runs,
                           "s" if runs != 1 else "",
                           avail.get(code, 0)),
                        job_id=j.id)
                avail[code] = avail.get(code, 0) - qty
            avail[j.material] = avail.get(j.material, 0) + (j.quantity or 1)
            continue
        if cat["consumes"]:
            need = j.quantity or 1
            if avail.get(j.material, 0) < need:
                # an external source (give_tool) of the same material
                # earlier in the list is the only legal cover
                produced = sum(
                    (pj.quantity or 1) for pj in jobs[:jobs.index(j)]
                    if JOB_CATALOG[pj.type]["produces"]
                    and pj.material == j.material
                    and JOB_CATALOG[pj.type]["source"] != "external")
                external = sum(
                    (pj.quantity or 1) for pj in jobs[:jobs.index(j)]
                    if JOB_CATALOG[pj.type]["source"] == "external"
                    and pj.material == j.material)
                if avail.get(j.material, 0) + produced + external < need:
                    return None, Failure(
                        "resource_not_found",
                        "material %r: need %d, have %d (world-produced %d, "
                        "external %d)"
                        % (j.material, need, avail.get(j.material, 0),
                           produced, external),
                        job_id=j.id)
        if cat["produces"] and j.material:
            src = JOB_CATALOG[j.type]["source"]
            if src == "world":
                # a world producer must reference a resource; the
                # material claim is checked HARD only against a MEASURED
                # drop (unknown drops = no claim - the "unknown is never
                # yes" rule applied to the ledger)
                rec = index.get(j.source) if j.source else None
                if rec is None:
                    return None, Failure(
                        "planner_invalid_reference",
                        "producer job %s has unknown source %s"
                        % (j.id, j.source), job_id=j.id)
                measured = getattr(rec, "drops", None)
                if measured is not None and measured != j.material:
                    return None, Failure(
                        "planner_invalid_reference",
                        "producer job %s claims material %r but the "
                        "measured drop of source %s is %r"
                        % (j.id, j.material, j.source, measured),
                        job_id=j.id)
                avail[j.material] = avail.get(j.material, 0) + \
                    (j.quantity or 1)

    # 6. claim compatibility (single bot: no two jobs on one resource)
    seen = {}
    for j in jobs:
        if j.source and j.type in ("mine", "harvest"):
            if j.source in seen:
                return None, Failure(
                    "claim_conflict",
                    "resource %s claimed by both %s and %s"
                    % (j.source, seen[j.source], j.id), job_id=j.id)
            seen[j.source] = j.id

    # 7. goal-target check (goal-aware validation): when a PLACE goal
    #    names a site, a place job must target exactly that site - a plan
    #    that achieves a DIFFERENT known site (or omits the place job
    #    altogether) is not the goal (the valid-unachieved gap found in
    #    P5 round 2, case F3). Goto goals are checked by the goal
    #    intake, not here.
    if goal is not None and getattr(goal, "verb", None) in ("place",
                                                            "build") and \
            getattr(goal, "at", None) and goal.at.startswith("site-"):
        if not any(j.type in ("place", "build") and j.target == goal.at
                   for j in jobs):
            return None, Failure(
                "planner_invalid_reference",
                "plan does not place/build at the goal's site %r"
                % goal.at,
                goal=goal.describe())
    if goal is not None and getattr(goal, "verb", None) == "build-plan" and \
            getattr(goal, "at", None) and goal.at.startswith("site-"):
        if not any(j.type == "build_plan" and j.target == goal.at
                   for j in jobs):
            return None, Failure(
                "planner_invalid_reference",
                "plan does not build %r at the goal's site %r"
                % (goal.object, goal.at),
                goal=goal.describe())

    return jobs, None
