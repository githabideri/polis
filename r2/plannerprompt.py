"""
R2 planner projection - turns the WorldModel + goal into the planner
prompt and the candidate index the validator trusts.

Design doc: section 8 (the planner prompt) and 5.2 (the trust boundary:
symbolic references). The model sees candidate IDs only - it may choose
among them, never invent one, never emit coordinates. This module is
pure: given (world_model, fixture records, inventory, goal) it returns
(prompt_text, candidate_index).
"""

from .jobs import Goal, Job, JOB_CATALOG, PLANNER_JOB_TYPES

PROMPT_HEADER = """\
You are the PLANNER for a single builder bot in a block world.
Turn the goal into a STRICT JSON plan - a list of job objects.

RULES
1. Job types allowed: {types}.
2. References: use ONLY the candidate ids listed below (res-*, site-*).
   You may choose among them. You may NOT invent an id or emit
   coordinates.
3. Every job object: {{"id":"j1","type":"<type>","quantity":<int>=1}}
   plus per type:
   - mine/harvest/pickup: "source":"res-<id>"
   - place/goto/travel:   "target":"site-<id>" (or a res-* for goto)
   - place/give_tool:     "material":"<material code>"
   - optional "depends_on":["j<id>"] (must point EARLIER in the list)
4. Material flow: a place job needs its material in the INVENTORY or as
   the output of an earlier producing job (mine/harvest/give_tool).
   A mine/harvest job produces the resource's MEASURED DROPS material
   (the drops= column) - a place job must consume exactly that code.
   Do NOT check quantities yourself: do no arithmetic - the
   deterministic validator after you checks all material balances.
   Propose the plan you believe is best; if you believe the goal cannot
   be met at all, use rule 6.
5. Goal semantics: "mine X" / "harvest X" means perform the action on a
   resource whose code or material name matches X. The material it
   actually yields (drops=) may differ - that is a consequence, not a
   blocker, for mine/harvest goals.
6. External supply: for a place goal whose material is absent from the
   INVENTORY and is not the measured output of any world producer, you
   MUST plan a give_tool job for the required quantity. External supply
   is a SANCTIONED plan form in this system: the planner proposes, it
   does not second-guess the operator's goal.
7. Keep the plan minimal. Order producers before consumers.
8. If the goal cannot be met from the candidates, answer exactly
   {{"reject":"<one-line reason>"}}.
9. Do NO arithmetic. You may reject ONLY when a required resource or
   site is absent from the candidate lists. Quantity sufficiency is
   decided by the deterministic validator that runs after you. In
   particular:
   - if the INVENTORY already holds the material a place job needs,
     the answer is a single place job (inventory material is usable
     as-is, no mining involved);
   - if the inventory lacks it, add a give_tool job for the shortfall
     - that is a LEGAL plan (rule 6); do not check the quantity
     yourself, do not mine to cover it.

GOAL
{goal}

CANDIDATE RESOURCES (id, block material, raw code, measured drops, qty, dist)
{resources}

FIXTURES (id, kind, requirement, current condition)
{fixtures}

INVENTORY (material code: quantity)
{inventory}

ANSWER (one JSON value only, no prose):
"""


def build_planner_prompt(wm, goal, inventory, fixtures, max_candidates=16,
                         center=None):
    """Project the world into the planner prompt.

    center: the bot's (x, _, z) for distance ordering (optional).
    Returns (prompt_text, candidate_index) where candidate_index maps
    every res-*/site-* id in the prompt to its record - the validator
    (r2/plancheck.py) resolves references against exactly this index.
    """
    index = {}

    # resources: unclaimed first, nearest to the bot first (planning mode:
    # stale allowed to NOMINATE - 12.6; the index is the trust boundary)
    cands = wm.find_unclaimed(wm.find_resources(fresh=False))
    def _dist(r):
        if center is None or r.centroid is None:
            return 0
        return abs(r.centroid[0] - center[0]) + \
            abs(r.centroid[2] - center[2])
    cands = sorted(cands, key=_dist)[:max_candidates]
    lines = []
    for r in cands:
        rid = r.id
        index[rid] = r
        extra = ""
        if r.properties.get("stage") is not None:
            extra = " stage=%s" % r.properties["stage"]
        dm = r.drop_material() or "?"
        lines.append("  %s  block=%s  code=%s  drops=%s%s  qty=%d  %dm"
                     % (rid, r.material or "?", r.code or "?",
                        dm + (" (measured)" if r.drops
                              else " (assumed, unmeasured)"),
                        extra,
                        int(r.observed_quantity or 1), _dist(r)))
    resources = "\n".join(lines) or "  (none - the world scan is empty)"

    # fixtures: the site registry with their stamped condition
    flines = []
    for f in fixtures:
        fid = f.get("id")
        index[fid] = f
        cond = f.get("condition")
        cond_s = cond.get("satisfied") if isinstance(cond, dict) else cond
        kind = f.get("kind") or ""
        if kind == "build-site":
            if cond_s is False:
                state = "PLACE TARGET (empty - ready for a place job)"
            elif cond_s is True:
                state = "FILLED (already satisfied here)"
            else:
                state = "condition unknown"
        else:
            state = "present" if cond_s else "absent"
        flines.append("  %s  %s  requirement=%s  %s"
                      % (fid, kind, f.get("requirement"), state))
    fixtures_s = "\n".join(flines) or "  (none)"

    inv = ", ".join("%s:%d" % (k, v) for k, v in sorted(inventory.items())) \
        or "(empty)"

    prompt = PROMPT_HEADER.format(
        types=", ".join(PLANNER_JOB_TYPES),
        goal=goal.describe() if isinstance(goal, Goal) else str(goal),
        resources=resources,
        fixtures=fixtures_s,
        inventory=inv)
    # appended AFTER .format(): the worked example contains JSON braces
    prompt += """

EXAMPLE (worked):
GOAL: place granite at site-A x1
INVENTORY: (empty)
no world producer yields granite
-> [{"id":"j1","type":"give_tool","material":"granite","quantity":1},
    {"id":"j2","type":"place","target":"site-A","material":"granite",
     "quantity":1,"depends_on":["j1"]}]"""
    return prompt, index
