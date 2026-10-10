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

import fnmatch
import json

from .jobs import (Job, Failure, JOB_CATALOG, Goal, GoalGrammarError,
                   deps_consistent)
from .queries import classify

MAX_QUANTITY = 100  # a single job asking for more is a plan smell


# --------------------------------------------------------------------------
# Shaped-recipe validation (2026-10-06 door campaign)
# --------------------------------------------------------------------------

def _strip(code):
    """Namespace-prefix stripping from an item/block code.

    VS item codes are `namespace:name`; the vanilla world index is
    game:-dominated but mod items come in other namespaces (the door
    chain's door-crude is survival:-namespaced, 2026-10-06), so strip
    whatever the prefix is when a colon is present. Un-namespaced
    codes pass through untouched.
    """
    c = str(code or "")
    if ":" in c:
        return c.split(":", 1)[1]
    return c


def _tags(ing):
    """The ingredient's tag set from a live recipe row: the harness
    exposes tags as a comma-joined string or a list."""
    t = ing.get("tags")
    if t is None:
        return []
    if isinstance(t, str):
        return [x.strip() for x in t.split(",")
                if x.strip() and x.strip().lower() != "null"]
    if isinstance(t, list):
        return [str(x) for x in t if x]
    return []


def _is_tool(ing):
    """A tool ingredient: the endpoint's explicit isTool flag (new
    harness), or a tool-* tag (the door recipe's axe is tagged
    "tool-axe"). Tools must be PRESENT but are never consumed - the
    engine's ConsumeInput skips them (measured 2026-10-04: the saw
    survived the plank craft)."""
    if ing.get("isTool") is True:
        return True
    return any(str(t).lower().startswith("tool") for t in _tags(ing))


def _code_covers(item, ing):
    """Does a held item (code or normalized material key) cover this
    recipe ingredient? Four shapes, in order:
      1. exact            door-crude == door-crude
      2. glob             log-placed-*-ud matches log-placed-oak-ud
      3. code family      a recipe code that is the ROOT of a family
                          ("log-placed" covers log-placed-oak-ud; the
                          engine matches the whole placed-log family)
      4. tag              a tag appearing in the item code
                          ("axe" in axe-felling-copper)
    """
    ic = _strip(item).lower()
    if not ic:
        return False
    c = _strip(ing.get("code") or "").lower()
    # "*:*" strips to a bare "*" - do NOT let it act as a match-all
    # glob: a wildcard-code ingredient is tag-constrained (the door's
    # axe cell is "*:*" + tool-axe), so the tag checks below decide.
    if c and c != "*":
        if ic == c:
            return True
        if "*" in c and fnmatch.fnmatchcase(ic, c):
            return True
        if "*" not in c and ic.startswith(c + "-"):
            return True
    if c == "*" and not _tags(ing):
        return True      # a truly unconstrained "any item" cell
    for t in _tags(ing):
        t = str(t).lower()
        if ic == t or t in ic:
            return True
        # a wildcard-code tool ingredient ("*:*" + tag "tool-axe"): the
        # engine matches the collectible's actual tag set; the validator
        # only has code strings, so match the tool noun against the
        # item code's tokens (axe-felling-copper carries "axe").
        if c in ("", "*", "*:*") and t.startswith("tool-"):
            noun = t[len("tool-"):]
            if noun and (noun in ic.split("-") or noun in ic):
                return True
    return False


def _pattern_check(inv, runs, slots, assign, cells_str):
    """ONE letter->ingredient assignment over the pattern. inv is
    mutated (non-tool cells subtracted). Returns (ok, missing, subs)."""
    per = {ch: cells_str.count(ch) for ch in slots}
    missing, subs = [], []
    for ch, ing in zip(slots, assign):
        label = _strip(ing.get("code") or "") or "?"
        if _is_tool(ing):
            have = sum(v for k, v in inv.items() if _code_covers(k, ing))
            if have < 1:
                missing.append("tool cell %s (%s) - not carried"
                               % (ch, label))
            continue          # present, not subtracted
        need = per[ch] * max(1, int(ing.get("qty") or 1)) * runs
        have = sum(v for k, v in inv.items() if _code_covers(k, ing))
        if have < need:
            missing.append("cell %s needs %d x %s, have %d"
                           % (ch, need, label, have))
        need_left = need
        for k in sorted(inv):
            if need_left <= 0:
                break
            if not _code_covers(k, ing):
                continue
            take = min(inv.get(k, 0), need_left)
            if take:
                inv[k] -= take
                subs.append((k, take))
                need_left -= take
    return (not missing), missing, subs


def check_craft_pattern(recipe, inv, runs=1):
    """A SHAPED recipe (pattern/width/height exposed by the live
    endpoint) validated against a held inventory - the door-craft
    chain (2026-10-06: the 2x3 "AS,PS,PS" crude door, an axe tool cell
    that is not consumed, a log family cell, a stick cell).

    Every non-tool pattern cell must be covered by a held item whose
    code matches the ingredient's code/glob/tag; cells of one letter
    are distinct units (two P cells need two logs). Tool cells require
    PRESENCE only and are never subtracted.

    The letter->ingredient mapping has two endpoint shapes:
      - per-cell (the live endpoint, 2026-10-07: one ingredient per
        grid cell in row-major order - a faithful projection of the
        engine's ResolvedIngredients). The mapping is FIXED by
        position (no assignment search); same-letter cells must agree
        on code/tags/isTool/qty or the recipe is rejected.
      - deduped (one ingredient per distinct letter, first-appearance
        order - the test-fixture and pre-2026-10-07 shape). The
        file's own order is tried first (what the engine uses), then
        the remaining assignments - an anomalous file order should not
        block a satisfiable craft; the engine's own GridRecipe
        matching is the final authority (a craft the pattern check let
        through can still fail at execution - the oracle measures that
        honestly).
    Any other count mismatch means the mapping is not exposed and the
    recipe is rejected (unknown is never yes).

    inv: a MUTABLE inventory map (normalized materials or item codes -
         they coincide for the codes that shaped recipes use) checked
         and drained. Returns (ok, missing, subs) - subs is
         [(key, qty)] subtracted from inv (under the satisfying
         assignment, when one exists), for the ledger.
    """
    from itertools import permutations
    pattern = (recipe.get("pattern") or "").strip()
    ings = recipe.get("ingredients") or []
    if not pattern:
        return False, ["shaped recipe without an exposed pattern"], []
    cells_str = "".join(row for row in pattern.split(","))
    cells = [ch for ch in cells_str if ch and ch != "."]
    slots, seen = [], set()
    for ch in cells:
        if ch not in seen:
            seen.add(ch)
            slots.append(ch)

    assign = None
    if len(ings) == len(cells):
        for i, ch in enumerate(cells):
            iid = ings[i].get("id")
            if iid not in (None, "", ch):
                return False, ["cell %d: pattern letter %r vs endpoint "
                               "ingredient id %r - the slot/ingredient "
                               "mapping is not consistent"
                               % (i, ch, iid)], []
        assign = []
        for ch in slots:
            i0 = cells.index(ch)
            ref = ings[i0]
            for i, ch2 in enumerate(cells):
                if ch2 == ch:
                    for fld in ("code", "tags", "isTool", "qty"):
                        if ings[i].get(fld) != ref.get(fld):
                            return False, ["letter %r: cells with the "
                                           "same letter disagree on %r"
                                           % (ch, fld)], []
            assign.append(ref)
    elif len(ings) != len(slots):
        return False, ["pattern %r has %d cells and %d distinct letters "
                       "but the endpoint lists %d ingredients - the "
                       "slot/ingredient mapping is not exposed"
                       % (pattern, len(cells), len(slots), len(ings))], []

    if assign is not None:
        # per-cell form: one deterministic assignment (the engine's own)
        ok, missing, _ = _pattern_check(dict(inv), runs, slots, assign,
                                        cells_str)
        if ok:
            ok2, _, subs = _pattern_check(inv, runs, slots, assign,
                                          cells_str)
            if ok2:
                return True, [], subs
        return False, (missing or ["pattern %r unsatisfiable with this "
                                    "inventory" % pattern]), []

    # deduped form: the vanilla convention first (the file's ingredient
    # order), then - only when it cannot be satisfied - the remaining
    # assignments
    order = [list(ings)]
    if len(slots) <= 4:
        order += [list(p_) for p_ in permutations(ings)
                  if list(p_) != list(ings)]
    best_missing = None
    for perm in order:
        ok, missing, _ = _pattern_check(
            dict(inv), runs, slots, perm, cells_str)
        if ok:
            # drain the caller's map under THIS assignment (the
            # ledger needs one consistent drain; the engine's own
            # matching is the authority on which)
            ok2, _, subs = _pattern_check(inv, runs, slots, perm,
                                          cells_str)
            if ok2:
                return True, [], subs
        if missing and (best_missing is None
                        or len(missing) < len(best_missing)):
            best_missing = missing
    if best_missing is None:
        best_missing = ["pattern %r unsatisfiable with this "
                        "inventory" % pattern]
    return False, ["under no letter/ingredient assignment: %s"
                    % "; ".join(best_missing)], []



def check_chop_target(at, expect, code, job_id=None, verb="chop"):
    """The chop check (2026-10-06): an operator-declared cell job's
    target cell, validated against the live world index - a job
    pointing at air is rejected BEFORE execution. With an `expect`
    family ("log-grown-*") the live block code must match it (exact,
    glob, or family root) - the block that IS there, not the drop it
    will make (a grown log drops a placed log; the drop claim is the
    job's `material`, guard-checked against the measured drop after
    execution). Without one, any non-air block passes - breakability
    is the engine's verdict at execution time, not something a code
    tells us. Returns None (ok) or a Failure."""
    c = _strip(code or "").lower()
    if not c or c == "air":
        return Failure(
            "resource_not_found",
            "%s at %s: the live cell is empty (no block to %s)"
            % (verb, at, verb), job_id=job_id)
    if expect:
        e = _strip(expect).lower()
        ok = (fnmatch.fnmatchcase(c, e) if "*" in e
              else (c == e or c.startswith(e + "-")))
        if not ok:
            return Failure(
                "planner_invalid_reference",
                "%s at %s: live block %r does not match the "
                "expected block family %r"
                % (verb, at, code, expect), job_id=job_id)
    return None


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


def validate_plan(plan_raw, index, inventory, goal=None, recipes=None,
                  cells=None, campaign=False):
    """Validate a raw planner response.

    plan_raw: str or object (the model output)
    index:    candidate index from build_planner_prompt
    inventory: {material: qty} at plan time
    recipes:  live grid-recipe table (list of {name, output,
                shapeless, ingredients:[{code, qty}]}) from the harness
                /polis/recipes - required for craft jobs; without it a
                craft plan is rejected (unknown is never yes). The
                new endpoint shape adds pattern/width/height and
                per-ingredient tags/isTool, which unlocks SHAPED
                recipes (the door-craft chain, 2026-10-06).
    cells:    {(x, y, z): block_code} live cell index - enables the
                chop check (an operator campaign's cell jobs validated
                against the world, the same way res-/site- refs are).
    campaign: True for an OPERATOR-DECLARED job list (the --jobs mode,
                2026-10-06 door campaign). Such lists may carry the
                goal-scoped chop type and cell-targeted mines (their
                cell is the reference); a 27B plan may never.

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
        # a build-plan goal sizes its acquisition to the plan (the 103-
        # block hut needs a 103-block mine - that is not a plan smell).
        # 2026-10-05.
        cap = MAX_QUANTITY
        if goal is not None and \
                getattr(goal, "verb", None) == "build-plan":
            cap = max(MAX_QUANTITY, 150)
        # a wait job's quantity is SECONDS (the time valve the
        # crucible chain waits out engine smelt progress with), not a
        # material count - the plan-smell cap does not apply (the
        # execution-time budget is the stall valve).
        if j.type != "wait" and j.quantity and j.quantity > cap:
            return None, Failure(
                "planner_invalid_json",
                "quantity %d exceeds the %d cap" % (j.quantity, cap),
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
        # chop (2026-10-06, same precedent as build_plan): it exists in
        # the catalog but only an operator campaign may declare it -
        # the 27B was never taught the verb (it cannot emit one).
        if j.type == "chop" and not campaign:
            return None, Failure(
                "planner_invalid_json",
                "chop is outside the planner vocabulary "
                "(operator-campaign scoped)",
                job_id=jid)
        # forage (2026-10-07) and the crucible family (2026-10-07)
        # are campaign-scoped on the same precedent.
        if j.type in ("forage", "crucible_fire", "crucible_insert",
                      "crucible_fuel", "crucible_take", "crucible_pour",
                      "knap", "firepit_fuel") and not campaign:
            return None, Failure(
                "planner_invalid_json",
                "%s is outside the planner vocabulary "
                "(operator-campaign scoped)" % j.type,
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

    # 4b. campaign cell jobs (2026-10-06 door campaign, 2026-10-07
    #     forage): the operator's chop / cell-mine / cell-forage jobs
    #     name a fixed cell - validate each against the live cell index
    #     before any execution (a job at air dies here, not mid-
    #     approach; a declared `expect`/`plant` family must match the
    #     live block). The index is caller-provided (a fresh scan); a
    #     missing entry reads as empty (unknown is never yes).
    if cells is not None:
        for j in jobs:
            if j.type == "chop" or (j.type in ("mine", "forage") and j.at):
                key = tuple(int(v) for v in j.at) if j.at else None
                code = None
                if key is not None:
                    code = cells.get(key, cells.get("%d,%d,%d" % key))
                f = check_chop_target(
                    j.at, (j.plant if j.type == "forage" else j.expect),
                    code, job_id=j.id, verb=j.type)
                if f is not None:
                    return None, f

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
        # external supply (12.10a): from this point on the given
        # material IS available - the ledger sees it like any
        # produced material (the campaign's craft depends on its
        # given tool). The consumer fallback below no longer re-adds
        # externals: they are already in `avail` (no double count).
        if j.type == "give_tool" and j.material:
            avail[j.material] = avail.get(j.material, 0) + (j.quantity or 1)
            continue
        # craft (1.22.7 grid crafting): validate against the live recipe
        # table; ingredients are consumed from the ledger, the output
        # added. A craft without a resolvable recipe is rejected -
        # the bot cannot invent recipes.
        if j.type == "craft":
            rc = None
            if recipe_by:
                rc = recipe_by.get((j.source or "").lower())
            if rc is None and recipe_by:
                # the operator campaigns name the PRODUCED item, not
                # the recipe file: match by output. Several variants
                # may exist (the door has two: log-placed / 
                # logsection-placed) - the first SATISFIABLE one wins,
                # mirroring the engine's own first-match behaviour.
                outs = [r for r in recipe_by.values()
                        if _strip(r.get("output") or "").lower()
                        == _strip(j.material or "").lower()]
                if len(outs) == 1:
                    rc = outs[0]
                else:
                    rc = next(
                        (r for r in outs
                         if check_craft_pattern(
                             r, dict(avail), j.quantity or 1)[0]),
                        None)
            if rc is None or _strip(rc.get("output") or "").lower() \
                    != _strip(j.material or "").lower():
                return None, Failure(
                    "planner_invalid_reference",
                    "craft job %s: recipe %r does not produce %r "
                    "(live recipe table consulted)"
                    % (j.id, j.source, j.material), job_id=j.id)
            if rc.get("shapeless") is False:
                if not rc.get("pattern"):
                    return None, Failure(
                        "planner_invalid_reference",
                        "craft job %s: recipe %r is shaped - the headless "
                        "path supports shapeless recipes only"
                        % (j.id, j.source), job_id=j.id)
                # the endpoint exposes the grid (pattern/width/height
                # + per-ingredient tags/isTool): validate the pattern
                # against the ledger state at this point (the earlier
                # producers' planned yield is in `avail` - the door's
                # two logs come from two chop jobs above). The tool
                # cells must be present, not consumed (2026-10-06
                # door-craft chain).
                ok, missing, subs = check_craft_pattern(
                    rc, dict(avail), j.quantity or 1)
                if not ok:
                    return None, Failure(
                        "resource_not_found",
                        "craft %s (recipe %s, pattern %s): %s"
                        % (j.id, j.source, rc.get("pattern"),
                           "; ".join(missing)),
                        job_id=j.id)
                for k, qty in subs:
                    avail[k] = avail.get(k, 0) - qty
                avail[j.material] = avail.get(j.material, 0) + \
                    (j.quantity or 1)
                continue
            runs = j.quantity or 1
            for ing in rc.get("ingredients") or []:
                code = (ing.get("code") or "").lower()
                qty = max(1, int(ing.get("qty") or 1)) * runs
                if not code:
                    continue
                if ing.get("isTool") is True:
                    # the new endpoint flags tool ingredients: present
                    # but NOT subtracted (the engine's ConsumeInput
                    # skips them - measured 2026-10-04: the saw
                    # survived the plank craft)
                    if avail.get(code, 0) < 1:
                        return None, Failure(
                            "resource_not_found",
                            "craft %s (recipe %s): tool %s not carried"
                            % (j.id, j.source, code),
                            job_id=j.id)
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
        # knap (2026-10-10, J1): one material item per recipe, one
        # output each. The outputs are KNOWN item codes (the engine's
        # KnappingRecipe table, live-probed from the assets - the job
        # requires them), so they budget the ledger directly: no
        # measured-drop uncertainty like a mine has.
        if j.type == "knap":
            runs = j.quantity or 1
            nrec = len(j.recipes or [])
            need = nrec * runs
            if avail.get(j.material, 0) < need:
                return None, Failure(
                    "resource_not_found",
                    "knap %s: needs %dx %s for %d run%s, have %d"
                    % (j.id, need, j.material, runs,
                       "s" if runs != 1 else "",
                       avail.get(j.material, 0)),
                    job_id=j.id)
            avail[j.material] = avail.get(j.material, 0) - need
            for r in (j.recipes or []):
                avail[r] = avail.get(r, 0) + runs
            continue
        if cat["consumes"]:
            need = j.quantity or 1
            if avail.get(j.material, 0) < need:
                # an external source (give_tool) of the same material
                # earlier in the list is ALREADY inside `avail` (the
                # give block above) - the fallback shortfall re-counts
                # only the world producers (the arithmetic is
                # identical to the old external-sum path, without
                # double counting)
                produced = sum(
                    (pj.quantity or 1) for pj in jobs[:jobs.index(j)]
                    if JOB_CATALOG[pj.type]["produces"]
                    and pj.material == j.material
                    and JOB_CATALOG[pj.type]["source"] != "external")
                if avail.get(j.material, 0) + produced < need:
                    return None, Failure(
                        "resource_not_found",
                        "material %r: need %d, have %d (world-produced %d; "
                        "external supply already counted in have)"
                        % (j.material, need, avail.get(j.material, 0),
                           produced),
                        job_id=j.id)
        if cat["produces"] and j.material:
            src = JOB_CATALOG[j.type]["source"]
            if src == "world":
                # a cell-targeted mine/chop/forage (operator campaign)
                # names its own cell: the pre-scan above IS the
                # reference check, and the declared material budgets
                # the ledger. forage without a cell (nearest instance
                # found at run time) and the crucible_take's melt
                # (symbolic intermediate of the smelt chain) budget
                # their claim the same way: they are campaign-scoped,
                # so no res-* reference exists by construction.
                if campaign and (
                        (j.at and j.type in ("mine", "chop"))
                        or j.type in ("forage", "crucible_take",
                                      "clayform", "kiln_fire", "cook")):
                    avail[j.material] = avail.get(j.material, 0) + \
                        (j.quantity or 1)
                    continue
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
