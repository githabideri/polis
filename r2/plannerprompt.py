"""
R2 planner projection - turns the WorldModel + goal into the planner
prompt and the candidate index the validator trusts.

Design doc: section 8 (the planner prompt) and 5.2 (the trust boundary:
symbolic references). The model sees candidate IDs only - it may choose
among them, never invent one, never emit coordinates. This module is
pure: given (world_model, fixture records, inventory, goal) it returns
(prompt_text, candidate_index).
"""

from r2.queries import normalize_material

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
   A mine job of material X produces X - check the material codes match
   what the place job consumes. give_tool sources material from outside
   the world (a harness supply) - use it only if the goal permits
   external supply; prefer world-producing jobs.
5. Order producers before consumers. Keep the plan minimal.
6. If the goal cannot be met from the candidates, answer exactly
   {{"reject":"<one-line reason>"}}.

GOAL
{goal}

CANDIDATE RESOURCES (id, material, quantity, distance)
{resources}

FIXTURES (id, kind, requirement, current condition)
{fixtures}

INVENTORY (material code: quantity)
{inventory}

ANSWER (one JSON value only, no prose):
"""


def build_planner_prompt(wm, goal, inventory, fixtures, max_candidates=16):
    """Project the world into the planner prompt.

    Returns (prompt_text, candidate_index) where candidate_index maps
    every res-*/site-* id in the prompt to its record - the validator
    (r2/plancheck.py) resolves references against exactly this index.
    """
    index = {}

    # resources: unclaimed first, sorted by distance (nearest work first)
    res = wm.find_unclaimed(max_count=max_candidates)
    lines = []
    for r in res:
        rid = r.id
        index[rid] = r
        lines.append("  %s  %s  qty=%d  %dm"
                     % (rid, r.material or "?",
                        r.observed_quantity or 1,
                        r.distance_m or 0))
    resources = "\n".join(lines) or "  (none - the world scan is empty)"

    # fixtures: the site registry with their stamped condition
    flines = []
    for f in fixtures:
        fid = f.get("id")
        index[fid] = f
        cond = f.get("condition")
        cond_s = cond.get("satisfied") if isinstance(cond, dict) else cond
        flines.append("  %s  %s  requirement=%s  now=%s"
                      % (fid, f.get("kind"), f.get("requirement"),
                         cond_s))
    fixtures_s = "\n".join(flines) or "  (none)"

    inv = ", ".join("%s:%d" % (k, v) for k, v in sorted(inventory.items())) \
        or "(empty)"

    prompt = PROMPT_HEADER.format(
        types=", ".join(PLANNER_JOB_TYPES),
        goal=goal.describe() if isinstance(goal, Goal) else str(goal),
        resources=resources,
        fixtures=fixtures_s,
        inventory=inv)
    return prompt, index
