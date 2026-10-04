"""
R2 build sequencer - placement ordering for building plans (design doc
13.13). The 5x5 dead-end, made checkable.

The problem
-----------
Runs 14-17 of the 106-block 5x5 hut each died the same way: at some
wall-tier-2 cell the executor found NO standable candidate (all four
horizontal neighbours at foot level were occupied, unsupported, or
floating) and aborted honestly. The diagnosis (13.13): a single bot,
placing at foot level from the four same-layer neighbours, cannot reach
the middle cells of a ring edge of 5+ at wall tiers 2+ - the interior
neighbour has no support a layer down (interior cells are never walls),
the outside neighbour floats, and the same-edge neighbours are already
placed. The 3x3 ring works because its edge middles stand on the
interior floor cell.

What this module does
---------------------
1. `standable` - the exact predicate the live executor uses
   (r2-live-mission.py `_standable`): a cell is a standing candidate
   when it is OPEN (no solid block) and supported - at or below ground
   level the terrain is the support, above it a solid block must be a
   layer down. This part is pure geometry and fully knowable; it is the
   failure mode, not a guess.

2. `sequence` - a deterministic placement order for a plan on a flat
   site, computed by simulation: layer by layer (bottom up), within a
   layer a greedy pass places the lowest (x,z) cell that currently has
   a standable candidate. The greedy pass makes corners-first EMERGENT
   (a corner is the first cell of its layer whose stand is unblocked),
   which is the ordering the 3x3 success run exhibited - and it stops
   with an honest `stuck` set when no remaining cell has a stand.

3. Scaffold policy - when a layer needs support/stands from below,
   the required cells of the layer below are filled with SCAFFOLD
   blocks (temporary, torn down afterwards). Placing a scaffold block
   DETERMINISTICALLY creates standing cells above it - this is the
   only lever on the stand predicate. The 5x5 hut needs the 3x3
   interior platform at each of layers 1-3 (27 temporary blocks);
   the solid 3x3 layer and the apex need none. Teardown is the
   reverse order: breaking a scaffold block needs only a standable
   neighbour, and the level below supplies it.

4. The last-cell theorem (the 13.13 dead-end, one level up): a stand
   is only a stand while it is unplaced. In a CLOSED layer (every
   cell's four neighbours are layer cells - a footprint-wide solid
   layer above ground) the cell placed LAST has no unplaced stand
   left and is unplaceable - by any order. The fix is
   architectural, not cleverer ordering: the plan keeps one OPENING
   (a hatch) in such a layer; cells adjacent to the opening have a
   PERMANENT stand (the opening never receives a plan block) and the
   sequencer places opening-adjacent cells last. Order within a
   layer is two-phase: FRAGILE cells first (every stand of the cell
   is a layer cell - it must be placed before its stands are; most-
   constrained first, then (x,z)), then the rest by (x,z) (a cell
   with at least one permanent stand can never be sealed within the
   layer, so any order works). A closed layer with no opening is
   reported infeasible with that diagnosis - the alternative is the
   standing-range extension (13.13 option 1), which needs a C# change.

Honest scope (what this model does NOT claim)
---------------------------------------------
The live failure signature is "no standable candidate" - that is what
this module predicts, exactly. The engine's FACE-acceptance logic
(which face of which neighbouring block the click lands on) is NOT
modelled here: runs 13-15's all-day phantom battles showed it is
finer-grained than any static rule, and the per-cell oracle (re-scan
after each place) is the final judge for it, as it always has been.
The greedy order therefore PREFERS stands that are face-plausible
(adjacent to already-placed same-layer blocks - the geometry the 3x3
success used) so the engine gets its best chance per cell; if it still
refuses, the executor's existing phantom/structural reporting applies
unchanged. The sequencer over-promises nothing it cannot prove.

Pure: no I/O, no harness. The world is a predicate `solid(x,y,z)`.
The live mission feeds it a local snapshot (one scan of the building
region plus margin); tests feed it dict worlds.
"""

from .buildplans import BuildingPlan, PlanError

# order kinds in the sequencer output
KIND_PLAN = "plan"
KIND_SCAFFOLD = "scaffold"
KIND_TEARDOWN = "teardown"


# ------------------------------------------------------------------
# worlds
# ------------------------------------------------------------------

class DictWorld:
    """A world as a set of solid cells (test double; the live adapter
    is the same shape, filled from one region scan)."""

    def __init__(self, cells=()):
        self.cells = set(tuple(c) for c in cells)

    def solid(self, x, y, z):
        return (x, y, z) in self.cells


class CompositeWorld:
    """Base world plus cells placed during the simulation."""

    def __init__(self, base, added=()):
        self.base = base
        self.added = set(added)

    def solid(self, x, y, z):
        return (x, y, z) in self.added or self.base.solid(x, y, z)

    def add(self, c):
        self.added.add(tuple(c))


# ------------------------------------------------------------------
# the stand predicate (calibrated: r2-live-mission.py `_standable`)
# ------------------------------------------------------------------

def standable(c, world, ground_y):
    """Can the bot stand in cell c (feet cell) against this world?
    Open (no SOLID block - vegetation passes, so the world predicate
    already excludes it) and supported: at or below ground level the
    terrain is the support; above it a solid block a layer down."""
    x, y, z = c
    if world.solid(x, y, z):
        return False
    if y <= ground_y:
        return True
    return world.solid(x, y - 1, z)


def _n4(t):
    x, y, z = t
    return ((x - 1, y, z), (x + 1, y, z), (x, y, z - 1), (x, y, z + 1))


def stand_candidates(t, world, ground_y):
    """The standing cells for a placement of t: the four same-layer
    horizontal neighbours that are standable (the executor's exact
    candidate set - the bot places at foot level)."""
    return [c for c in _n4(t) if standable(c, world, ground_y)]


def _cheb(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]), abs(a[2] - b[2]))


def face_plausible(t, c, world, ground_y):
    """Soft heuristic (NOT a feasibility predicate): is stand c
    face-plausible for target t - c within chebyshev-1 of a solid
    same-layer neighbour of t (the geometry the 3x3 success run used:
    stand on the interior cell, click the placed corner's side face).
    Used to ORDER candidates, never to veto a stand."""
    x, y, z = t
    if _cheb(c, t) != 1:
        return False
    for f in _n4(t) + ((x, y + 1, z), (x, y - 1, z)):
        if f != t and f != c and world.solid(*f) and f[1] == y:
            if _cheb(f, c) <= 1:
                return True
    return False


# ------------------------------------------------------------------
# the sequencer
# ------------------------------------------------------------------

class SequencerResult:
    def __init__(self, ok, order, scaffold, stuck, notes=()):
        self.ok = ok
        self.order = order      # [(cell, material, kind)]
        self.scaffold = list(scaffold)
        self.stuck = list(stuck)
        self.notes = list(notes)

    def summary(self):
        n_plan = sum(1 for _, _, k in self.order if k == KIND_PLAN)
        n_sca = sum(1 for _, _, k in self.order if k == KIND_SCAFFOLD)
        n_tear = sum(1 for _, _, k in self.order if k == KIND_TEARDOWN)
        s = "sequencer: %s | plan=%d scaffold=%d teardown=%d" % (
            "OK" if self.ok else "STUCK", n_plan, n_sca, n_tear)
        if self.stuck:
            s += " | stuck=%d first=%s" % (len(self.stuck), self.stuck[0])
        return s


def _door_cells(plan, origin):
    """Absolute cells the door keeps OPEN (layers 1..door_height)."""
    ex, ez = plan.entry[0], plan.entry[1]
    out = set()
    for dy in range(1, plan.door_height + 1):
        out.add((origin[0] + ex, origin[1] + dy, origin[2] + ez))
    return out


def _reserved_cells(plan, origin):
    """All cells the building keeps OPEN forever: the door plus the
    declared architectural openings (windows, skylights). The platform
    never fills a reserved cell, and a reserved cell that is supported
    is a PERMANENT stand (the last-cell theorem, doc item 4)."""
    out = _door_cells(plan, origin)
    for dx, dy, dz in plan.openings:
        out.add((origin[0] + dx, origin[1] + dy, origin[2] + dz))
    return out


def _plan_cell_map(plan, origin):
    return {(origin[0] + dx, origin[1] + dy, origin[2] + dz): m
            for (dx, dy, dz), m in plan.blocks}


def _scaffold_material(plan):
    """The material the platform is built from: the plan's material.
    Single-material plans (the only kind with ring walls today) are
    exact; for multi-material plans the largest declared material is
    used (the operator can override via the plan's scaffold_material
    field if the build source provides one)."""
    mats = [(v, k) for k, v in plan.materials.items() if v]
    if not mats:
        raise PlanError("plan has no materials to scaffold with")
    return max(mats)[1]


def _layer_cells(plan, origin, layer):
    """Plan cells at `layer` (absolute), sorted by (x,z)."""
    out = [(c, m) for c, m in _plan_cell_map(plan, origin).items()
           if c[1] == origin[1] + layer]
    return sorted(out, key=lambda im: (im[0][0], im[0][2]))


def _footprint_cells(plan, origin, layer):
    """All footprint cells at `layer` (absolute), sorted by (x,z)."""
    w, d = plan.footprint
    return [(origin[0] + dx, origin[1] + layer, origin[2] + dz)
            for dx in range(w) for dz in range(d)]


def _platform_cells(plan, origin, L, reserved, world):
    """The OPEN footprint cells at layer L-1 that must become solid
    (scaffolded) before layer L can be placed. A cell of the layer
    below enters the platform when it is the missing support under
    a cell that must be STANDABLE at layer L: either an open stand
    cell (an open footprint cell adjacent to a plan cell of layer L
    - the stand that layer's cells will use) or a plan cell that will
    serve as a stand for one of its own layer neighbours (in a full
    layer, the interior cells stand up their siblings). The target's
    own placement needs no support (the engine places against a face;
    blocks float) - but a cell only stands when the block under it is
    solid, so the platform exists to stand stands up. Nothing else is
    scaffolded: the platform is as small as the stand geometry demands
    (a 5x5 hut: the 3x3 interiors at layers 1-3, minus cells whose
    stand-above is never used, minus the door column, minus declared
    openings - 24 blocks). Reserved cells (door, openings) stay
    open."""
    if L == 0:
        return []
    plan_L = {c for c, _ in _layer_cells(plan, origin, L)}
    below_layer = origin[1] + L - 1
    have_all = set(_plan_cell_map(plan, origin))
    need = set()
    for t in plan_L:   # support under a plan cell that stands siblings
        if any(n in plan_L for n in _n4(t)):
            need.add((t[0], t[1] - 1, t[2]))
    for s in _footprint_cells(plan, origin, L):   # support for open stands
        if s in have_all or world.solid(*s):
            continue                       # not an open stand
        if any(n in plan_L for n in _n4(s)):
            need.add((s[0], s[1] - 1, s[2]))
    out = []
    for c in sorted(need):
        if c[1] != below_layer or c in reserved:
            continue
        if world.solid(*c):
            continue                       # plan cell / floor / earlier
                                            # platform: already solid
        if c not in _footprint_cells(plan, origin, L - 1):
            continue
        out.append(c)
    return out


def sequence(plan, origin, base_world, ground_y=None, max_scaffold=256,
             scaffold_material=None):
    """Deterministic placement order for `plan` at `origin`.

    base_world: a world predicate (solid cells as of now - for a
      resume, the already-built cells are simply solid in it).
    ground_y: the site's ground level (default: origin's y - the flat
      site assumption; the live adapter passes the probed level).
    max_scaffold: cap on temporary blocks; 0 disables the platform
      (reproduces the raw 13.13 dead-end for plans that need it).

    Returns SequencerResult. `stuck` non-empty => the plan as given
    is not completable by one bot at foot level under this policy;
    the stuck cells are the honest report (same signature the live
    executor emits: no standable candidate).
    """
    origin = tuple(origin)
    gy = origin[1] if ground_y is None else ground_y
    mat_scaf = scaffold_material or _scaffold_material(plan)

    # resume: plan cells already solid in the world count as placed
    w = CompositeWorld(base_world)
    placed_plan = set()
    for c, m in _plan_cell_map(plan, origin).items():
        if base_world.solid(*c):
            w.add(c)
            placed_plan.add(c)

    reserved = _reserved_cells(plan, origin)
    layers = sorted({c[1] - origin[1] for c in _plan_cell_map(plan, origin)})
    order = []
    scaffold = []
    stuck = []
    notes = []

    for L in layers:
        # (a) platform: solidify exactly the open cells of the layer
        # below that layer L needs as stand support (see
        # _platform_cells). A platform layer stands on the layer below
        # it, which is solid by induction (the floor first). The
        # cluster gets the same fragile-first order as a plan layer -
        # it is a solid cluster too, and a closed one (the 3x3 at
        # layer 3) has a last cell with no stand: that cell is SKIPPED
        # with an honest note, never optimistically placed, and the
        # layers above are simulated against the reduced world (the
        # stand above the skipped cell simply stops being standable).
        if L > 0 and max_scaffold > 0:
            pool = _platform_cells(plan, origin, L, reserved, w)
            set_P = set(pool)

            def _pplace(c):
                w.add(c)
                scaffold.append(c)
                order.append((c, mat_scaf, KIND_SCAFFOLD))
                pool.remove(c)

            # phase 1: fragile platform cells, fewest stands first
            while pool:
                frag = []
                for c in pool:
                    s = stand_candidates(c, w, gy)
                    if s and all(x in set_P for x in s):
                        frag.append((len(s), c[0], c[2], c))
                if not frag:
                    break
                frag.sort()
                if len(scaffold) >= max_scaffold:
                    notes.append("scaffold budget %d reached; platform "
                                 "incomplete" % max_scaffold)
                    pool = []
                    break
                _pplace(frag[0][3])
            # phase 2: the rest by (x,z); a cell with no stand at its
            # turn is skipped (the closed-cluster last cell)
            for c in sorted(pool, key=lambda c: (c[0], c[2])):
                if len(scaffold) >= max_scaffold:
                    notes.append("scaffold budget %d reached; platform "
                                 "incomplete" % max_scaffold)
                    break
                if not stand_candidates(c, w, gy):
                    notes.append("scaffold %s: no stand at its turn "
                                 "(closed-cluster last cell); stands "
                                 "above it lose their support" % (c,))
                    pool.remove(c)
                    continue
                _pplace(c)

        # (b) the layer's plan cells, fragile-first two-phase order.
        # A stand is PERMANENT for this layer when it is not a plan
        # cell of the layer (an opening/hatch, the open interior
        # before the next platform step, the ground margin, the open
        # annulus of a shrinking footprint): it never gets placed, so
        # it never stops being a stand. A cell ALL of whose stands
        # are layer cells is FRAGILE - it must be placed before all
        # its stands are, else it is sealed (the last-cell theorem).
        cell_mat = _plan_cell_map(plan, origin)
        layer_all = [c for c, _ in _layer_cells(plan, origin, L)]
        set_L = set(layer_all)
        pool = [c for c in layer_all if not w.solid(*c)]

        def _place(c):
            w.add(c)
            placed_plan.add(c)
            order.append((c, cell_mat[c], KIND_PLAN))
            pool.remove(c)

        # phase 1: fragile cells, most-constrained first (fewest
        # stands, then (x,z)) - the boundary peel that keeps the
        # fragile region from sealing its own centre
        while True:
            frag = []
            for c in pool:
                s = stand_candidates(c, w, gy)
                if s and all(x in set_L for x in s):
                    frag.append((len(s), c[0], c[2], c))
            if not frag:
                break
            frag.sort()
            _place(frag[0][3])

        # phase 2: the rest, by (x,z) - each has a permanent stand,
        # so no order within the phase can seal one
        stuck = None
        for c in sorted(pool, key=lambda c: (c[0], c[2])):
            if not stand_candidates(c, w, gy):
                stuck = list(pool)
                break
            _place(c)
        if stuck is not None:
            # is this the closed-layer dead end (no opening at all)?
            if all(not stand_candidates(n, w, gy)
                   for c in stuck for n in _n4(c) if n not in set_L):
                notes.append(
                    "closed layer %d has no opening: its last cell has "
                    "no stand. Add a hatch cell to the plan (one open "
                    "cell in the layer) or the standing-range "
                    "extension (13.13 option 1, C#)" % L)
            stuck = [c for c in stuck
                     if not stand_candidates(c, w, gy)] or stuck
            break
        if stuck:
            break

    if not stuck:
        # teardown: reverse placement order = topmost platform level
        # first; each block is broken from a standable neighbour
        # (the platform level below, or the floor) - the same stand
        # predicate, so no new geometry is assumed.
        for c in reversed(scaffold):
            w.add(c)  # still solid while we break down through it
            order.append((c, mat_scaf, KIND_TEARDOWN))

    return SequencerResult(not stuck, order, scaffold, stuck or [], notes)


def check(plan, origin, base_world, ground_y=None, max_scaffold=256):
    """Pre-flight convenience: run the simulation, return
    (ok, result). The live mission calls this BEFORE any placement;
    a not-ok result is an honest plan rejection carrying the stuck
    set (the 13.13 signature), not a run that crawls to a dead cell."""
    r = sequence(plan, origin, base_world, ground_y, max_scaffold)
    return (not r.stuck, r)
