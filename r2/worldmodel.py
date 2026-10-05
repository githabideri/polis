"""R2 WorldModel (Phase 2, 2026-09-28; design doc §4-§5, §11.4, §12).

The shared semantic view of the game in the Python decision layer:

  C# / game          = authoritative truth (right now)
  WorldModel         = remembered, structured, STAMPED view of that truth
  models             = consumers of projections - never write, never raw

Ownership (doc §5.1): WorldModel owns the record dicts + sequence;
JobQueue owns the claims (this model holds a read-only view for
find_unclaimed); the executor owns action/phase state; fixture
completion oracles are the deterministic per-family functions.

THE STALENESS INVARIANT (doc §11.4, frozen):

  WorldModel records may be stale. Action preconditions and completion
  checks must never be satisfied from cached records alone.

Implementation form (amendments 12.1/12.2): every observation carries a
`seq` (monotonic within the run - the OPERATIONAL freshness basis), a
`monotonic_ms` (process clock), a `wall_ms` (diagnostics only - wall
clocks jump and are never used for correctness), and a `reason`
(lifecycle phase: fixture_setup / pre_action / post_action / oracle /
planner_scan, plus optional caused_by_action_id). Queries used by
execution paths take `fresh=True` and return `None` (unknown) unless the
record was observed at the CURRENT sequence value - unknown is never
yes and never no; it forces a new observation from the game. Planning
queries (`fresh=False`) may use stale records to NOMINATE candidates;
they can never prove anything (12.6: plan_valid !=
action_precondition_current).

No C# tick endpoint in R2 (12.2): a game tick becomes worthwhile only
with long-lived knowledge, concurrent observers, time-decay,
save/reload. The harness exposes no clock anyway.

The WorldModel is mission-agnostic on purpose: it does not know what a
"marker" is. The executor feeds it fixture CONDITION values computed by
the frozen predicates (r2.types.fixture_bool - one implementation) and
asks it for freshness-gated reads.
"""
import time

from r2 import queries


# ---------------------------------------------------------------- types ----

class ResourceRecord:
    """A scanned cluster of same (kind, material) cells (an observation,
    stamped).

    Amendment 12.3: keeps raw identity (code) and normalized class
    (kind/material/properties) side by side; observed_quantity is the
    number of CURRENTLY OBSERVED cells, never a complete extent
    (is_complete_extent stays False in R2).

    The id is stable within a run/snapshot (12.5 rule: scoped to the
    snapshot that introduced it; a later refresh must not silently
    rebind a job's target - jobs retain their own binding).
    """

    def __init__(self, rid, kind, material, code, properties, cells,
                 source="scan"):
        self.id = rid
        self.kind = kind
        self.material = material
        self.code = code
        self.properties = dict(properties)
        self.cells = list(cells)
        self.mineable_cells = None   # the MINEABLE surface subset: cells
                                     # whose layer ABOVE is not solid
                                     # (the rest are buried interior cells
                                     # a bare hand cannot reach). Set by
                                     # observe_scan from the raw scan.
        self.centroid = None
        self.observed_quantity = len(cells)
        self.is_complete_extent = False
        self.source = source               # "scan" | "verified" | "fixture"
        self.seq = 0                        # last observed at (run sequence)
        self.monotonic_ms = 0.0
        self.wall_ms = 0
        # MEASURED drop material (what mining this resource yields, from
        # the post-mine inventory diff). Distinct from the BLOCK material:
        # the 2026-09-28 probe found granite blocks drop the stone-granite
        # item. None = unmeasured; the planner/ledger fall back to
        # `material` only for unmeasured resources.
        self.drops = None

    def record_drop(self, material, seq, monotonic_ms, wall_ms):
        """Record the measured drop (called with the post-mine inventory
        observation). Stamped like any other observation."""
        self.drops = material
        self.seq, self.monotonic_ms, self.wall_ms = seq, monotonic_ms, wall_ms

    def drop_material(self):
        """The material the ledger must simulate: the measured drop when
        known, the block material as proxy when not."""
        return self.drops or self.material

    @property
    def quantity(self):
        """Observed quantity (alias - 12.2: never an assumed extent)."""
        return self.observed_quantity

    def to_dict(self):
        return {"id": self.id, "kind": self.kind,
                "material": self.material, "code": self.code,
                "properties": self.properties, "cells": self.cells,
                "centroid": self.centroid,
                "observed_quantity": self.observed_quantity,
                "is_complete_extent": self.is_complete_extent,
                "source": self.source, "seq": self.seq,
                "monotonic_ms": self.monotonic_ms,
                "wall_ms": self.wall_ms,
                "drops": self.drops}


class FixtureRecord:
    """Fixture IDENTITY - authoritative configuration (we created it).

    Never carries current condition: condition is a FixtureObservation,
    re-queried from the game whenever it matters (doc §5.3).
    """

    def __init__(self, fid, kind, cell, requirement):
        self.id = fid
        self.kind = kind              # "marker" | "crop" | "build-site" | ...
        self.cell = list(cell)
        self.requirement = requirement  # "absent" | "filled" | "block:<code>"

    def to_dict(self):
        return {"id": self.id, "kind": self.kind, "cell": self.cell,
                "requirement": self.requirement}


class FixtureObservation:
    """The fixture's current CONDITION, stamped (12.2/12.6).

    `present` is what the frozen predicate produced from a specific scan;
    `seq` says WHEN in the run's observation sequence that scan happened;
    `reason` says WHERE in the action lifecycle (a future bug where an
    oracle reads a post_action observation becomes visibly absurd in the
    run JSON instead of "some recent scan").
    """

    def __init__(self, seq, present, monotonic_ms, wall_ms, reason,
                 caused_by=None):
        self.seq = seq
        self.present = present
        self.monotonic_ms = monotonic_ms
        self.wall_ms = wall_ms
        self.reason = reason
        self.caused_by = caused_by

    def to_dict(self):
        return {"seq": self.seq, "present": self.present,
                "monotonic_ms": self.monotonic_ms,
                "wall_ms": self.wall_ms, "reason": self.reason,
                "caused_by": self.caused_by}


class ClaimRecord:
    """A target reserved by a live job. JobQueue is the authoritative
    owner; this is the model's read-only mirror (doc §5.1)."""

    def __init__(self, target_id, job_id, bot_id, seq):
        self.target_id = target_id
        self.job_id = job_id
        self.bot_id = bot_id
        self.seq = seq

    def to_dict(self):
        return {"target_id": self.target_id, "job_id": self.job_id,
                "bot_id": self.bot_id, "seq": self.seq}


# ---------------------------------------------------------------- model ----

class WorldModel:
    """In-memory per goal run (doc §7: the run JSON is the persistence)."""

    def __init__(self):
        self.seq = 0                  # run observation sequence (12.2)
        self.resources = {}           # id -> ResourceRecord
        self._resource_keys = {}      # (kind, material, centroid) -> id
        self.fixtures = {}            # id -> FixtureRecord
        self.fixture_observations = {}  # id -> FixtureObservation
        self.claim_index = {}         # target_id -> ClaimRecord (read-only
                                      # view; JobQueue owns the claims)
        self._res_seq = 0
        self._obs_log = []            # (seq, reason, kind, target) - provenance
        self._solid_cells = set()     # (x,y,z) of solid blocks in the last
                                      # scan - used to mark the mineable
                                      # (top) surface of each cluster

    # --------------------------------------------------------- sequence ----

    def new_tick(self, reason=None, caused_by=None):
        """Start a new observation cycle (kept name: existing call sites;
        semantics = advance the run's observation sequence)."""
        self.seq += 1
        if reason is not None:
            self._obs_log.append((self.seq, reason, None, caused_by))
        return self.seq

    # ---------------------------------------------------- observations ----

    def observe_scan(self, scan_resp, reason="planner_scan", caused_by=None):
        """Cluster the blocks of a /polis/scan response into resource
        records at the current sequence value (12.2/12.3). Returns the
        touched ResourceRecords."""
        from r2 import queries
        from r2.embodiment import is_solid
        now = time.monotonic() * 1000.0
        wall = int(time.time() * 1000)
        self._obs_log.append((self.seq, reason, "scan", caused_by))
        raw_blocks = (scan_resp.get("Data") or {}).get("blocks", []) or []
        # the solid surface of the scanned region - a cluster cell whose
        # layer above is solid is buried interior and a bare hand cannot
        # mine it (the failed hut run learned this the hard way: a big
        # soil blob is ~97% buried, so allocating to len(cells) is a lie).
        self._solid_cells = {tuple(b["pos"]) for b in raw_blocks
                             if b.get("code") and b.get("pos")
                             and is_solid(b["code"])}
        out = []
        for cl in queries.cluster_cells(raw_blocks):
            key = (cl["kind"], cl["material"], tuple(cl["centroid"]))
            rid = self._resource_keys.get(key)
            if rid is None:
                self._res_seq += 1
                rid = "res-%02d" % self._res_seq
                self._resource_keys[key] = rid
                self.resources[rid] = ResourceRecord(
                    rid, cl["kind"], cl["material"], cl["code"],
                    cl["properties"], cl["cells"],
                    source="fixture" if reason == "fixture_setup" else "scan")
            rec = self.resources[rid]
            rec.cells = cl["cells"]
            # the mineable surface: cluster cells with a non-solid layer
            # above (open to the sky). A cell whose above is outside the
            # scan window is treated as open (a benign false positive -
            # the per-cell pre-check at mine time still guards it).
            sc = self._solid_cells
            rec.mineable_cells = [c for c in cl["cells"]
                                  if (c[0], c[1] + 1, c[2]) not in sc]
            rec.centroid = cl["centroid"]
            rec.observed_quantity = cl["observed_quantity"]
            rec.properties.update(cl["properties"])
            rec.seq = self.seq
            rec.monotonic_ms = now
            rec.wall_ms = wall
            out.append(rec)
        return out

    def observe_fixture(self, fix_id, present, reason="pre_action",
                        caused_by=None):
        """Record a fixture CONDITION observation at the current sequence
        value. `present` is whatever the frozen predicate computed from a
        real scan - the model stores, never recomputes (one
        implementation)."""
        self.fixture_observations[fix_id] = FixtureObservation(
            self.seq, present, time.monotonic() * 1000.0,
            int(time.time() * 1000), reason, caused_by)
        return present

    # ------------------------------------------------------------ queries ----

    def register_fixture(self, fix_id, kind, cell, requirement):
        """Authoritative configuration (we created it - doc §5.3)."""
        self.fixtures[fix_id] = FixtureRecord(fix_id, kind, cell, requirement)
        return self.fixtures[fix_id]

    def get_fixture(self, fix_id):
        return self.fixtures.get(fix_id)

    def fixture_condition(self, fix_id, fresh=True):
        """The fixture's condition, freshness-gated (doc §11.4, 12.6).

        fresh=True (the only mode execution paths may use): the
        observation must come from the CURRENT sequence value, else
        None. fresh=False (planning/nomination only): the latest
        observation, however old - callers may consider it, never prove
        with it.

        Returns True/False or None (unknown).
        """
        obs = self.fixture_observations.get(fix_id)
        if obs is None:
            return None
        if fresh and obs.seq != self.seq:
            return None
        return obs.present

    def fixture_satisfies(self, fix_id, fresh=True):
        """Requirement check against the (fresh) condition: 'absent'
        wants condition False, 'filled' wants True. Unknown (None) is
        never satisfaction (the invariant)."""
        fix = self.fixtures.get(fix_id)
        cond = self.fixture_condition(fix_id, fresh=fresh)
        if fix is None or cond is None:
            return None
        if fix.requirement == "absent":
            return not cond
        if fix.requirement == "filled":
            return cond
        return None

    def find_resources(self, material=None, kind=None, center=None,
                       radius=None, fresh=False):
        """Candidate resources (doc §5.2 - referenced symbolically).
        `fresh` is a FILTER, not a proof: fresh=True keeps only records
        observed at the current sequence value; fresh=False is the
        planning mode (stale allowed to nominate, 12.6)."""
        out = []
        for rec in self.resources.values():
            if fresh and rec.seq != self.seq:
                continue
            if material and rec.material != material:
                continue
            if kind and rec.kind != kind:
                continue
            if center is not None and radius is not None:
                if not queries.cells_in_radius(rec.cells, center, radius):
                    continue
            out.append(rec)
        out.sort(key=lambda r: r.id)
        return out

    # ------------------------------------------------------------- claims ----

    def record_claim(self, target_id, job_id, bot_id):
        """JobQueue mirror (the queue remains authoritative)."""
        self.claim_index[target_id] = ClaimRecord(target_id, job_id, bot_id,
                                                 self.seq)

    def release_claim(self, target_id):
        self.claim_index.pop(target_id, None)

    def find_unclaimed(self, records):
        """The subset of candidate records no live job has claimed."""
        return [r for r in records if r.id not in self.claim_index]

    # --------------------------------------------------------- serialization ----

    def to_dict(self):
        """The worldSnapshot of the run JSON (doc §7)."""
        return {
            "seq": self.seq,
            "resources": [r.to_dict() for r in
                          sorted(self.resources.values(),
                                 key=lambda r: r.id)],
            "fixtures": {k: v.to_dict() for k, v in
                         sorted(self.fixtures.items())},
            "fixture_observations": {
                k: v.to_dict() for k, v in
                sorted(self.fixture_observations.items())},
            "claim_index": {k: v.to_dict() for k, v in
                            sorted(self.claim_index.items())},
            "observation_log": [
                {"seq": s, "reason": r, "kind": k, "caused_by": c}
                for (s, r, k, c) in self._obs_log],
        }
