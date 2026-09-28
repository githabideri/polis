"""
R2 job/goal contracts - goal grammar (v1), the Job dataclass, the job
effect catalog and the structured failure taxonomy.

Design doc: docs/design/2026-09-26-job-system-r2.md
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

GOAL_VERBS = ("mine", "harvest", "place", "goto")


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
    "give_tool": {"produces": True,  "consumes": False,
                  "source": "external", "needs": ("material",)},
    "pickup":    {"produces": False, "consumes": False,
                  "source": "world",    "needs": ("source",)},
    "travel":    {"produces": False, "consumes": False,
                  "source": "world",    "needs": ("target",)},
    "wait":      {"produces": False, "consumes": False,
                  "source": "world",    "needs": ()},
}

#: job types the planner may emit in a plan (section 12.1 amended catalog).
PLANNER_JOB_TYPES = tuple(JOB_CATALOG)

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
    depends_on: list = field(default_factory=list)
    claims: list = field(default_factory=list)
    budget: int = 12               # max execution steps (the stall valve)
    status: str = "ready"          # ready|running|blocked|done|abandoned

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
        if qty is not None and (not isinstance(qty, int) or qty < 1):
            raise ValueError("job %s: quantity must be a positive integer"
                             % jid)
        deps = d.get("depends_on") or []
        if not isinstance(deps, list) or not all(
                isinstance(x, str) for x in deps):
            raise ValueError("job %s: depends_on must be a list of ids" % jid)
        return cls(id=jid, type=jtype,
                   source=d.get("source"), target=d.get("target"),
                   material=d.get("material"), quantity=qty,
                   depends_on=list(deps),
                   claims=list(d.get("claims") or []),
                   budget=int(d.get("budget") or 12),
                   status=d.get("status") or "ready")

    def missing_refs(self):
        """Catalog-mandated reference fields this job leaves empty."""
        return [f for f in JOB_CATALOG[self.type]["needs"]
                if getattr(self, f) in (None, "")]

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
