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


def validate_plan(plan_raw, index, inventory):
    """Validate a raw planner response.

    plan_raw: str or object (the model output)
    index:    candidate index from build_planner_prompt
    inventory: {material: qty} at plan time

    Returns (jobs, None) on success, (None, Failure) on rejection.
    """
    # 1. parse
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
        jobs.append(j)

    # 3. references (the trust boundary - 5.2)
    for j in jobs:
        for ref in (j.source, j.target, j.material if j.type in
                    ("place",) else None):
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
    for j in jobs:
        cat = JOB_CATALOG[j.type]
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

    return jobs, None
