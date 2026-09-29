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

#: layers above the site base a plan may occupy (floor, walls, roof, +1)
MAX_LAYERS = 4


class PlanError(Exception):
    def __init__(self, detail):
        super().__init__(detail)
        self.detail = detail


class BuildingPlan:
    def __init__(self, name, footprint, materials, blocks, entry,
                 provides):
        self.name = name
        self.footprint = tuple(footprint)          # (w, d) in blocks
        self.materials = dict(materials)           # material -> total qty
        self.blocks = [((b["d"][0], b["d"][1], b["d"][2]), b["m"])
                       for b in blocks]            # [(dx,dy,dz), material]
        self.entry = tuple(entry)                  # (dx, dz) - the door
        self.provides = list(provides)             # survival function tags

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
        ex, ez = self.entry
        if not (0 <= ex < w and 0 <= ez < d):
            raise PlanError("entry %r outside footprint" % (self.entry,))
        # the DOOR: the entry column must be open in every layer
        # EXCEPT the floor (a threshold) and the plan's top layer (an
        # overhang roof). For the hut (3 layers) that leaves the wall
        # layer as the actual opening. A wall-only plan (2 layers)
        # has its top layer = the wall, so its entry stays open too.
        max_dy = max(dy for (_, dy, _), _ in self.blocks)
        for (dx, dy, dz), _ in self.blocks:
            if (dx, dz) == (ex, ez) and 0 < dy < max_dy:
                raise PlanError("entry cell (%d,%d) is blocked at layer %d "
                                "- the door must stay open" % (ex, ez, dy))
        # the floor layer must be solid - nothing is built on air
        floor = {(dx, dz) for (dx, dy, dz), _ in self.blocks if dy == 0}
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
        the build strategy: each phase places from the layer below."""
        ox, oy, oz = origin
        out = {}
        for (dx, dy, dz), m in self.blocks:
            out.setdefault(dy, []).append(((ox + dx, oy + dy, oz + dz), m))
        order = []
        for dy in sorted(out):
            name = {0: "floor", 1: "walls", 2: "roof"}.get(dy, "layer%d" % dy)
            order.append((name, sorted(out[dy])))
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
        provides=d.get("provides") or [])
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
