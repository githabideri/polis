"""
Building plan system - buildings are DATA, not code.

A plan file (builds/<name>.json) is the unit of the building library:
any source that can produce such a file (a repo directory now, a git
submodule later, an online library later still) is a building source;
this module is the shared API. The two consumers of ONE file:
  - creative mode (today): external/operator supply,
  - hardcore survival (later): `materials` is the shopping list the
    production chain decomposes into mine/chop/craft jobs, and
    `provides` is what survival systems query (shelter, bed space,
    workbench spot) - buildings, not raw blocks.

Pure: reads the file handed to it; no harness, no world.
"""

import json
import os

#: layers above the site base a plan may occupy (floor, up to three
#: wall layers, up to three stepped roof layers)
MAX_LAYERS = 7


class PlanError(Exception):
    def __init__(self, detail):
        super().__init__(detail)
        self.detail = detail


class BuildingPlan:
    def __init__(self, name, footprint, materials, blocks, entry,
                 provides, openings=(), floorless=False):
        self.name = name
        self.footprint = tuple(footprint)          # (w, d) in blocks
        self.materials = dict(materials)           # material -> total qty
        self.blocks = [((b["d"][0], b["d"][1], b["d"][2]), b["m"])
                       for b in blocks]            # [(dx,dy,dz), material]
        self.entry = tuple(entry)                  # (dx, dz[, door_height])
        self.provides = list(provides)             # survival function tags
        # a wall box standing on the site base: no built floor layer
        # (the terrain is the floor), dy=0 is the base wall layer.
        self.floorless = bool(floorless)
        # architectural openings the sequencer must never fill: local
        # (dx, dy, dz) cells that are part of the building's design
        # (windows, skylights) - they stay open forever and double as
        # permanent stands for the last-cell theorem (sequencer doc 4)
        self.openings = [tuple(o) for o in openings]

    @property
    def door_height(self):
        # the opening runs from layer 1 to door_height (2-tuple entry
        # = a 1-high opening); a lintel above it and anything beyond
        # are normal architecture
        return self.entry[2] if len(self.entry) > 2 else 1

    # -- validation (runs at load) --------------------------------------
    def validate(self):
        w, d = self.footprint
        if w < 1 or d < 1 or w > 16 or d > 16:
            raise PlanError("footprint out of bounds: %r" % (self.footprint,))
        seen = {}
        for (dx, dy, dz), m in self.blocks:
            if not (0 <= dx < w and 0 <= dz < d):
                raise PlanError("block (%d,%d,%d) outside footprint %r"
                                % (dx, dy, dz, self.footprint))
            if not (0 <= dy < MAX_LAYERS):
                raise PlanError("layer %d out of bounds (max %d)"
                                % (dy, MAX_LAYERS - 1))
            key = (dx, dy, dz)
            if key in seen:
                raise PlanError("two blocks share cell %r" % (key,))
            seen[key] = m
        # closed loop: declared totals must equal the block multiset
        # (a zero-declared material never counts as declared)
        actual = {}
        for _, m in self.blocks:
            actual[m] = actual.get(m, 0) + 1
        declared = {k: v for k, v in self.materials.items() if v}
        if actual != declared:
            raise PlanError("materials %r do not match the block list %r"
                            % (self.materials, actual))
        if len(self.entry) not in (2, 3):
            raise PlanError("entry must be (dx, dz) or (dx, dz, "
                            "door_height)")
        for o in self.openings:
            if len(o) != 3 or not (0 <= o[0] < w and 0 <= o[1] < MAX_LAYERS
                                   and 0 <= o[2] < d):
                raise PlanError("opening %r outside footprint %r"
                                % (o, self.footprint))
            if any((dx, dy, dz) == tuple(o) for (dx, dy, dz), _
                   in self.blocks):
                raise PlanError("opening %r collides with a block" % (o,))
        ex, ez = self.entry[0], self.entry[1]
        if not (0 <= ex < w and 0 <= ez < d):
            raise PlanError("entry %r outside footprint" % (self.entry,))
        # the DOOR: the entry column must be open in every layer of
        # the opening (1 .. door_height). The floor below is a
        # threshold, the layer above the opening a lintel (optional),
        # and the top layers an overhang - all normal architecture.
        #
        # A floorless plan is a wall box standing on the site base:
        # the terrain is the floor (no built dy=0 slab), so the forced
        # floor-solidity check is relaxed; its "door" is simply an
        # omitted block (declare it via `openings`), so the forced
        # door-open check is relaxed too. Both stay on by default.
        if not self.floorless:
            for (dx, dy, dz), _ in self.blocks:
                if (dx, dz) == (ex, ez) and 1 <= dy <= self.door_height:
                    raise PlanError("entry cell (%d,%d) is blocked at "
                                    "layer %d - the door must stay open"
                                    % (ex, ez, dy))
            # the floor layer must be solid - nothing is built on air
            floor = {(dx, dz) for (dx, dy, dz), _ in self.blocks
                     if dy == 0}
            for x in range(w):
                for z in range(d):
                    if (x, z) not in floor:
                        raise PlanError("floor is not solid: cell (%d,%d) "
                                        "missing" % (x, z))
        return self

    # -- compilation -----------------------------------------------------
    def phases(self, origin):
        """[(phase_name, [(cell, material)])] ordered for the executor:
        floor first (the bot stays OUTSIDE the footprint - same-layer
        placement from the side is the proven geometry), then walls
        (the bot stands ON the floor, places one layer up - the proven
        geometry), then roof (the bot stands ON the walls, places at
        its own level). The "bot on its own platform" footgun becomes
        the build strategy: each phase places from the layer below.

        Within a layer the CORNERS come first, then the rest (09-29,
        the last-corner dead-end that killed runs 13-15 at
        walls(4,1,4)): a corner's in-footprint neighbours are all
        layer-mates, so placed LAST (plain x,z sort) it has no open
        ledge left and no outside support; placed FIRST (everything
        open) it stands on its two open neighbours. Edge cells stand
        on their interior neighbour (floor for walls, layer below for
        solid roof layers)."""
        ox, oy, oz = origin
        out = {}
        for (dx, dy, dz), m in self.blocks:
            out.setdefault(dy, []).append(((ox + dx, oy + dy, oz + dz), m))

        def _order(items):
            cells = {c for c, _ in items}
            xs = {c[0] for c in cells}
            zs = {c[2] for c in cells}

            def corner(c):
                # a corner is at the extreme of the layer's bounding
                # box on BOTH axes (ring layers: the 4 corners; solid
                # layers: the 4 corners too - harmless to lead with
                # them). OR-of-neighbours was wrong: it marked every
                # edge cell of a solid layer as a corner.
                return (c[0] in (min(xs), max(xs)) and
                        c[2] in (min(zs), max(zs)))

            s = sorted(items)
            return [i for i in s if corner(i[0])] + \
                   [i for i in s if not corner(i[0])]

        order = []
        for dy in sorted(out):
            name = {0: "floor", 1: "walls", 2: "roof"}.get(dy,
                                                         "layer%d" % dy)
            order.append((name, _order(out[dy])))
        return order

    def block_at(self, dx, dy, dz):
        for (bx, by, bz), m in self.blocks:
            if (bx, by, bz) == (dx, dy, dz):
                return m
        return None

    def total_blocks(self):
        return len(self.blocks)


def load_plan(path):
    """Load and validate a plan file. Raises PlanError."""
    with open(path) as f:
        d = json.load(f)
    p = BuildingPlan(
        name=d.get("name") or os.path.basename(str(path)).rsplit(".", 1)[0],
        footprint=d.get("footprint") or (3, 3),
        materials=d.get("materials") or {},
        blocks=d.get("blocks") or [],
        entry=d.get("entry") or (0, 0),
        provides=d.get("provides") or [],
        openings=d.get("openings") or [],
        floorless=bool(d.get("floorless", False)))
    if not p.blocks:
        raise PlanError("plan has no blocks")
    p.validate()
    return p


def list_plans(directory):
    """Sorted plan names available in a directory (the library index)."""
    out = []
    if not os.path.isdir(directory):
        return out
    for fn in sorted(os.listdir(directory)):
        if fn.endswith(".json"):
            out.append(fn[:-5])
    return out
