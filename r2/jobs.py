"""
R2 job/goal contracts - goal grammar (v1), the Job dataclass, the job
effect catalog and the structured failure taxonomy.

Design doc: docs/design/job-system-r2.md
  - section 6: goal grammar {verb, object, at, n}; ordered job list with
    optional depends_on; the Job dataclass; completion via fixture oracles.
  - section 5.5: the failure codes, each attributed to a layer
    (observation / query / planner / validation / execution / oracle).
  - section 12.1 (amendment): the job-effect catalog, the material-ledger
    rules, and the external-source (give) distinction.

Pure data + validation: no I/O here. The planner prompt (r2/plannerprompt.py)
projects the world into the candidate vocabulary this module defines; the
validator (r2/plancheck.py) checks plans against it.
"""

from dataclasses import dataclass, field, asdict


# --------------------------------------------------------------------------
# Goal grammar (v1)
# --------------------------------------------------------------------------

GOAL_VERBS = ("mine", "harvest", "place", "goto", "sow", "plant",
              "build", "construct", "build-plan", "craft")

#: operator synonyms that normalize onto another grammar verb
GOAL_VERB_ALIASES = {"plant": "sow", "construct": "build"}


class GoalGrammarError(Exception):
    """Raised for goals outside the v1 grammar. Mapped to the
    `unsupported_goal` failure code (layer: goal) by the caller."""

    def __init__(self, detail):
        super().__init__(detail)
        self.detail = detail


@dataclass
class Goal:
    verb: str                    # one of GOAL_VERBS
    object: str                  # material / block / destination name
    at: str | None = None        # "site-*" id or "x y z" coordinates
    n: int | None = None         # required quantity (int >= 1)
    supply: str | None = None    # operator declaration: "external" (the
                                 # orchestrator supplies the material
                                 # deterministically - 12.10 remediation (a))

    def to_dict(self):
        return {"verb": self.verb, "object": self.object,
                "at": self.at, "n": self.n, "supply": self.supply}

    @classmethod
    def from_dict(cls, d):
        if not isinstance(d, dict):
            raise GoalGrammarError("goal must be a JSON object")
        verb = d.get("verb")
        if verb not in GOAL_VERBS:
            raise GoalGrammarError(
                "verb %r outside the v1 grammar %r" % (verb, GOAL_VERBS))
        verb = GOAL_VERB_ALIASES.get(verb, verb)
        obj = d.get("object")
        if not isinstance(obj, str) or not obj:
            raise GoalGrammarError("goal.object must be a non-empty string")
        at = d.get("at")
        if at is not None and not isinstance(at, str):
            raise GoalGrammarError("goal.at must be a string or null")
        n = d.get("n")
        if n is not None and (not isinstance(n, int) or n < 1):
            raise GoalGrammarError("goal.n must be a positive integer")
        supply = d.get("supply")
        if supply is not None and supply != "external":
            raise GoalGrammarError(
                "goal.supply must be 'external' or null, got %r" % supply)
        return cls(verb=verb, object=obj, at=at, n=n, supply=supply)

    def describe(self):
        s = "%s %s" % (self.verb, self.object)
        if self.at:
            s += " at %s" % self.at
        if self.n:
            s += " x%d" % self.n
        return s


# --------------------------------------------------------------------------
# Job catalog (effect semantics, section 12.1)
# --------------------------------------------------------------------------
# The ledger needs one effect description per job type:
#   produces  - adds material (what it yields is MEASURED after execution,
#               never assumed - the ledger records the observation)
#   consumes  - requires material before it can run (checked by the
#               pre-execution ledger simulation)
#   source    - where the effect material comes from: "world" (mining /
#               harvesting the world) or "external" (harness give - flagged,
#               not a world fact)
#   needs     - the reference fields the validator must find populated

JOB_CATALOG = {
    "mine":      {"produces": True,  "consumes": False,
                  "source": "world",    "needs": ("source",)},
    "harvest":   {"produces": True,  "consumes": False,
                  "source": "world",    "needs": ("source",)},
    "place":     {"produces": False, "consumes": True,
                  "source": "world",    "needs": ("target", "material")},
    "goto":      {"produces": False, "consumes": False,
                  "source": "world",    "needs": ("target",)},
    "sow":       {"produces": False, "consumes": True,
                  "source": "world",    "needs": ("target", "material")},
    "build":     {"produces": False, "consumes": True,
                  "source": "world",    "needs": ("target", "material")},
    # a building plan (13.11): one composite job erects a whole plan
    # file. `plan` names the file; its materials are resolved by the
    # orchestrator (multi-material, so outside the single-material
    # ledger) and it is GOAL-SCOPED: only the deterministic compiler
    # may emit it (the 27B planner gains it via an A/B gate, like sow
    # did - it is deliberately NOT in PLANNER_JOB_TYPES yet).
    "build_plan": {"produces": False, "consumes": False,
                  "source": "world",    "needs": ("target", "plan")},
    # 1.22.7 grid crafting (no workbench block in this build): the
    # game's own GridRecipe engine (Matches + ConsumeInput) runs against
    # the bot's cargo inventory. Semantics: `material` names the
    # PRODUCED item code; `source` names the recipe (its asset path, e.g.
    # "grid/plank" - NOT a "res-*" world resource, the validator
    # resolves it against the live recipe table). The recipe's
    # ingredients are consumed from the ledger by the validator.
    "craft":     {"produces": True,  "consumes": True,
                  "source": "world",    "needs": ("material", "source")},
    # tree-chopping (2026-10-06 door campaign): the same mechanics as
    # mine (approach resolution, engine verdict, measured drop) recorded
    # under its own action name. GOAL-SCOPED like build_plan: operator
    # campaigns declare chop jobs (a fixed `at` cell, an optional
    # `expect` live-block family, a `material` drop claim); the 27B
    # planner's vocabulary never gained the verb, so it cannot emit one.
    "chop":      {"produces": True,  "consumes": False,
                  "source": "world",    "needs": ("at",)},
    # knap (2026-10-10, J1 of the early-game ladder): chip stone items
    # on the knappingsurface block (the engine's KnappingRecipe table;
    # the C# command validates range, surface and the cargo material).
    # `at` is the surface cell, `material` the chipping material in
    # cargo, `recipes` the output item codes (the oracle is the
    # measured delta of exactly these). GOAL-SCOPED exactly like chop:
    # catalog + ledger + executor, but NOT in the 27B planner
    # vocabulary.
    "knap":      {"produces": True,  "consumes": True,
                  "source": "world",    "needs": ("at", "material",
                                                  "recipes")},
    # forage (2026-10-07 survival run): gather the fruit of a forageable
    # plant (the 1.22 fruiting bush, `fruitingbush-<state>-<type>`): the
    # executor walks to an ADJACENT cell and issues the harness `pick`
    # command on the target (Lane A's command - the same pick path the
    # mod's forage interrupt uses), repeating until the count is met.
    # `plant` names the block code or a family glob (`fruitingbush-*`);
    # `at` is a known target cell (from a targets query) and optional -
    # without it the executor finds the nearest instance within radius
    # at run time; `deliver` is carry (default) | drop (at the bot's
    # feet on completion); `material` claims the drop (the bush's fruit
    # item) for the ledger. GOAL-SCOPED exactly like chop: catalog +
    # ledger + executor, but NOT in the 27B planner vocabulary.
    "forage":    {"produces": True,  "consumes": False,
                  "source": "world",    "needs": ("plant",)},
    # crucible smelt (2026-10-07 survival run): the pot-work family.
    # Lane A's C# commands (the 1.22 crucible reuses the same base for
    # the cooking pot later); the bot must stand at the crucible - the
    # chain's goto walks there first. `material` is the slot item
    # (crucible size for fire, ore for insert, fuel or the `charcoal`
    # keyword for fuel, the melt for take/pour), `quantity` its count,
    # `at` the firepit cell for fire (optional) and the mold cell for
    # pour. Ledger: fire consumes the crucible item, insert/fuel
    # consume, take produces the melt, pour consumes the melt (symbolic
    # - the ingot is the oracle's measured delta). GOAL-SCOPED: campaign
    # chains only, never in the 27B vocabulary.
    "crucible_fire":   {"produces": False, "consumes": True,
                        "source": "world",  "needs": ("material",)},
    "crucible_insert": {"produces": False, "consumes": True,
                        "source": "world",  "needs": ("material",)},
    "crucible_fuel":   {"produces": False, "consumes": True,
                        "source": "world",  "needs": ("material",)},
    "crucible_take":   {"produces": True,  "consumes": False,
                        "source": "world",  "needs": ("material",)},
    "crucible_pour":   {"produces": False, "consumes": True,
                        "source": "world",  "needs": ("material", "at")},
    "give_tool": {"produces": True,  "consumes": False,
                  "source": "external", "needs": ("material",)},
    "pickup":    {"produces": False, "consumes": False,
                  "source": "world",    "needs": ("source",)},
    "travel":    {"produces": False, "consumes": False,
                  "source": "world",    "needs": ("target",)},
    "wait":      {"produces": False, "consumes": False,
                  "source": "world",    "needs": ()},
}

#: job types the planner may emit in a plan (section 12.1 amended
#: catalog). build_plan is EXCLUDED: goal-scoped to the deterministic
#: compiler until an A/B round teaches the 27B the vocabulary.
#: chop (2026-10-06), forage (2026-10-07) and the crucible family
#: (2026-10-07) are EXCLUDED on the same precedent: the campaigns
#: need them, the 27B never learned them.
PLANNER_JOB_TYPES = tuple(
    k for k in JOB_CATALOG
    if k not in ("build_plan", "chop", "forage", "crucible_fire",
                 "crucible_insert", "crucible_fuel", "crucible_take",
                 "crucible_pour"))

#: provenance of a job's origin (13.1, frozen): the queue runs a mix of
#: jobs made by different principals; the run JSON is the transparency
#: record, so every job says who made it.
ORIGINS = ("planner", "operator", "deterministic", "repair")

#: jobs whose effect material is a world observation (ledger "world" side)
WORLD_PRODUCERS = ("mine", "harvest")


@dataclass
class Job:
    id: str
    type: str
    source: str | None = None      # "res-*" resource id (the trust boundary)
    target: str | None = None      # "site-*" id / destination
    material: str | None = None    # normalized material code
    quantity: int | None = None    # positive int
    plan: str | None = None        # build_plan: the plan file name
    at: list | None = None         # cell-targeted jobs (chop, operator
                                   # cell-mine): [x, y, z] - the cell IS
                                   # the reference (no res-* id)
    expect: str | None = None      # chop: the expected family of the
                                   # LIVE block code at `at` (pre-exec
                                   # check; exact / glob / family root).
                                   # The drop claim is `material`.
                                   # (a grown log block drops a placed
                                   # log - the two families differ)
    plant: str | None = None       # forage: the forageable's block code
                                   # or family glob (`fruitingbush-*`)
    deliver: str | None = None     # forage: "carry" (default) | "drop"
                                   # (drop everything at the bot's feet
                                   # on completion)
    recipes: list | None = None    # knap: the OUTPUT item codes to chip
                                   # in this pass (the engine's
                                   # KnappingRecipe table resolves each
                                   # by output code or name); REQUIRED
                                   # for knap (the oracle is the
                                   # measured delta of exactly these)
    depends_on: list = field(default_factory=list)
    claims: list = field(default_factory=list)
    budget: int = 12               # max execution steps (the stall valve)
    status: str = "ready"          # ready|running|blocked|done|abandoned
    # provenance of the job's ORIGIN (13.1): the queue runs a mix of
    # deterministic and planned jobs; the run JSON must say who made each
    origin: str = "planner"

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d, job_id=None):
        if not isinstance(d, dict):
            raise ValueError("job must be a JSON object")
        jid = d.get("id") or job_id
        jtype = d.get("type")
        if not jid or not isinstance(jid, str):
            raise ValueError("job.id missing")
        if jtype not in JOB_CATALOG:
            raise ValueError("job type %r not in the catalog %r"
                             % (jtype, sorted(JOB_CATALOG)))
        qty = d.get("quantity")
        if qty is None and d.get("n") is not None:
            qty = d.get("n")       # operator campaigns write `n` (the
                                   # goal-grammar quantity name)
        if qty is not None and (not isinstance(qty, int) or qty < 1):
            raise ValueError("job %s: quantity must be a positive integer"
                             % jid)
        at = d.get("at")
        if at is not None:
            if (not isinstance(at, (list, tuple)) or len(at) != 3
                    or not all(isinstance(v, int) and not
                               isinstance(v, bool) for v in at)):
                raise ValueError("job %s: at must be [x, y, z] ints"
                                 % jid)
            at = list(at)
        expect = d.get("expect")
        if expect is not None and not isinstance(expect, str):
            raise ValueError("job %s: expect must be a string"
                             % jid)
        plant = d.get("plant")
        if plant is not None and not isinstance(plant, str):
            raise ValueError("job %s: plant must be a string" % jid)
        deliver = d.get("deliver")
        if deliver is not None and deliver not in ("carry", "drop"):
            raise ValueError("job %s: deliver must be 'carry' or 'drop'"
                             % jid)
        recipes = d.get("recipes")
        if recipes is not None:
            if (not isinstance(recipes, list) or not recipes
                    or not all(isinstance(x, str) and x for x in recipes)):
                raise ValueError("job %s: recipes must be a non-empty "
                                 "list of output item codes" % jid)
            recipes = list(recipes)
        if jtype == "knap" and not recipes:
            raise ValueError("job %s: knap requires 'recipes' (the "
                             "output item codes to chip)" % jid)
        deps = d.get("depends_on") or []
        if not isinstance(deps, list) or not all(
                isinstance(x, str) for x in deps):
            raise ValueError("job %s: depends_on must be a list of ids" % jid)
        origin = d.get("origin", "planner")
        if origin not in ORIGINS:
            raise ValueError("job %s: unknown origin %r (frozen: %r)"
                             % (jid, origin, sorted(ORIGINS)))
        return cls(id=jid, type=jtype,
                   source=d.get("source"), target=d.get("target"),
                   material=d.get("material"), quantity=qty,
                   plan=d.get("plan"), at=at, expect=expect,
                   plant=plant, deliver=deliver, recipes=recipes,
                   depends_on=list(deps),
                   claims=list(d.get("claims") or []),
                   budget=int(d.get("budget") or 12),
                   status=d.get("status") or "ready",
                   origin=origin)

    def missing_refs(self):
        """Catalog-mandated reference fields this job leaves empty.
        A cell-targeted mine carries its reference in `at` (the cell,
        live-scanned by the validator) instead of a resource id."""
        needs = list(JOB_CATALOG[self.type]["needs"])
        if self.type == "mine" and "source" in needs and self.at:
            needs.remove("source")
        return [f for f in needs if getattr(self, f) in (None, "")]

    def ledger_deltas(self):
        """[(material, sign)] for the pre-execution ledger simulation.
        `sign` is +1 (produces, quantity = job quantity or 1) / -1
        (consumes). Producing jobs yield their ACTUAL drop after execution
        (measured); here the symbol stands in for the simulation."""
        if self.type not in JOB_CATALOG:
            return []
        cat = JOB_CATALOG[self.type]
        if not self.material:
            return []
        qty = self.quantity or 1
        # craft: the ledger entry is the produced output only; its
        # ingredients are consumed against the recipe table by the
        # validator (a single-material delta pair would cancel itself).
        if self.type == "craft":
            return [(self.material, +qty)] if cat["produces"] else []
        # knap: each recipe in the pass consumes one material item and
        # yields its output (the validator checks the same pair; the
        # live measured delta is the oracle).
        if self.type == "knap":
            out = []
            for r in (self.recipes or []):
                out.append((r, +qty))
            out.append((self.material, -(len(self.recipes or [1]) * qty)))
            return out
        out = []
        if cat["produces"]:
            out.append((self.material, +qty))
        if cat["consumes"]:
            out.append((self.material, -qty))
        return out


# --------------------------------------------------------------------------
# Section 5.5 - the structured failure taxonomy (frozen)
# --------------------------------------------------------------------------

#: code -> owning layer. Every failure recorded in a run JSON carries
#: (code, layer, detail). This table is the single source of attribution.
FAILURE_CODES = {
    "unsupported_goal":          "goal",
    "planner_invalid_json":      "planner",
    "planner_invalid_reference": "validation",
    "planner_dependency_error":  "validation",
    "resource_not_found":        "query",
    "target_not_reachable":      "query",
    "claim_conflict":            "query",
    "job_budget_exhausted":      "execution",
    "fixture_failed":            "oracle",
}


class Failure:
    """A structured failure record (the §5.5 taxonomy, one per incident)."""

    def __init__(self, code, detail, job_id=None, goal=None):
        if code not in FAILURE_CODES:
            raise ValueError("unknown failure code %r (frozen taxonomy)"
                             % code)
        self.code = code
        self.layer = FAILURE_CODES[code]
        self.detail = detail
        self.job_id = job_id
        self.goal = goal

    def to_dict(self):
        return {"code": self.code, "layer": self.layer,
                "detail": self.detail, "job_id": self.job_id,
                "goal": self.goal}


def deps_consistent(jobs):
    """Check the depends_on field against list order (section 6): a
    dependency that points to a later job (or a missing id) is a
    planner_dependency_error. Returns (ok, list_of_problem_job_ids)."""
    pos = {j.id: i for i, j in enumerate(jobs)}
    problems = []
    for j in jobs:
        for d in j.depends_on:
            if d not in pos:
                problems.append(j.id)          # unknown id
            elif pos[d] > pos[j.id]:
                problems.append(j.id)          # contradicts the order
    return (not problems), problems
