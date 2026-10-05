"""R2 queries: deterministic world-model operations (Phase 2, 2026-09-28).

No model calls, no actions, no I/O - pure data transformation over
harness-observed facts (same discipline as projection.py: narrow
inputs, narrow outputs, so game internals never reach a model context
through any back door).

Amendment 12.3: every material record keeps BOTH raw identity and the
normalized class - the exact game code, a planner-facing kind
(crop/ore/rock/soil/...), and a material name that is NOT over-
normalized (crops keep their crop name: flax/rye/wheat, stage lives in
properties). Unknown codes map to their own material - never dropped.

Amendment 12.2: quantities are OBSERVED quantities (len of the observed
cells), never complete extents - a 3x3x4 scan cuts veins at its
boundary; `is_complete_extent` stays False in R2.
"""

# ---------------------------------------------------------------- codes ----

_PREFIX = "game:"

# Exact block code (prefix-stripped) -> (kind, material, properties)
EXACT_MAP = {
    "rock-granite": ("rock", "granite", {}),
    "rock-stone": ("rock", "stone", {}),
    "rock-limestone": ("rock", "limestone", {}),
    "soil-medium-none": ("air", "air", {}),
    "air": ("air", "air", {}),
    "dirt": ("soil", "dirt", {}),
    "soil-medium-normal": ("soil", "dirt", {}),
    # 1.22.7 soil block: one `soil` blocktype, variants are FERTILITY
    # (verylow/low/medium/high/compost) x grass coverage (none/normal/...),
    # full cube (class BlockSoil, cube shape). Mining one drops exactly one
    # `soil-{fertility}-none` item, which places the same block - the
    # honest dirt-hut material (builds/hut-dirt.json, 2026-10-05).
    "soil-verylow-none": ("soil", "dirt", {}),
    "soil-verylow-normal": ("soil", "dirt", {}),
    "soil-low-none": ("soil", "dirt", {}),
    "soil-low-normal": ("soil", "dirt", {}),
    "soil-high-none": ("soil", "dirt", {}),
    "soil-high-normal": ("soil", "dirt", {}),
    "soil-compost-none": ("soil", "dirt", {}),
    "soil-compost-normal": ("soil", "dirt", {}),
}

# Prefix rule (on the prefix-stripped code) -> (kind, material, props-fn)
PREFIX_RULES = [
    ("crop-", "crop"),
    ("ore-", "ore"),
    ("stone-", "stone"),
]


def _strip(code):
    c = str(code or "")
    return c[len(_PREFIX):] if c.startswith(_PREFIX) else c


def classify(code):
    """Block code -> (kind, material, properties, raw_code).

    crop-<name>-<stage>  -> ("crop", <name>, {"stage": <stage>})
    ore-<name>           -> ("ore", <name>, {})
    exact map wins; unknown codes are their own material (kind "block")
    - unknown is indexable, never silently discarded.
    """
    c = _strip(code)
    if not c:
        return ("air", "air", {}, str(code or ""))
    if c in EXACT_MAP:
        kind, mat, props = EXACT_MAP[c]
        return (kind, mat, dict(props), c)
    for prefix, kind in PREFIX_RULES:
        if c.startswith(prefix):
            rest = c[len(prefix):]
            if kind == "crop" and "-" in rest:
                name, stage = rest.rsplit("-", 1)
                try:
                    props = {"stage": int(stage)}
                except ValueError:
                    name, props = rest, {}
                return (kind, name, props, c)
            return (kind, rest, {}, c)
    return ("block", c, {}, c)


# ---------------------------------------------------------------- clusters ----

def cluster_cells(blocks):
    """Connected components of same (kind, material) cells over a scanned
    block list. Deterministic: 6-neighbourhood, cells sorted, clusters
    sorted by (kind, material, first cell).

    Returns a list of dicts:
      kind, material, code (representative raw code), properties,
      cells ([[x,y,z]...]), observed_quantity, centroid,
      is_complete_extent (always False in R2 - 12.3/12.8).
    """
    groups = {}
    props_seen = {}
    for b in blocks or []:
        code = b.get("code")
        kind, mat, props, raw = classify(code)
        if kind == "air":
            continue          # air is not a resource
        cell = b.get("pos")
        if not cell:
            continue
        key = (kind, mat)
        groups.setdefault(key, {})[tuple(cell)] = True
        if kind == "crop" and "stage" in props:
            ps = props_seen.setdefault(key, set())
            ps.add(props["stage"])
    out = []
    for (kind, mat) in sorted(groups):
        cells = groups[(kind, mat)]
        while cells:                      # in-place BFS: consumed cells are
            seed = sorted(cells)[0]       # removed, so the loop terminates
            del cells[seed]
            stack = [seed]
            comp = [seed]
            while stack:
                c = stack.pop()
                for d in ((1, 0, 0), (-1, 0, 0), (0, 1, 0),
                          (0, -1, 0), (0, 0, 1), (0, 0, -1)):
                    n = (c[0] + d[0], c[1] + d[1], c[2] + d[2])
                    if n in cells:
                        del cells[n]
                        comp.append(n)
                        stack.append(n)
            comp.sort()
            stages = sorted(props_seen.get((kind, mat), ()))
            out.append({
                "kind": kind, "material": mat,
                "code": mat if kind != "crop" else
                        "crop-" + mat + ("-" + str(stages[0])
                                         if len(stages) == 1 else ""),
                "properties": {"stages": stages} if stages else {},
                "cells": [[x, y, z] for (x, y, z) in comp],
                "observed_quantity": len(comp),
                "centroid": centroid(comp),
                "is_complete_extent": False,
            })
    out.sort(key=lambda r: (r["kind"], r["material"], r["cells"][0]))
    return out


def centroid(cells):
    """Integer centroid of a cell list (rounded; deterministic)."""
    if not cells:
        return [0, 0, 0]
    n = len(cells)
    return [int(round(sum(c[i] for c in cells) / n)) for i in range(3)]


def cells_in_radius(cells, center, radius):
    """True if ANY cell is within `radius` (2-D ground reach) of the
    center cell. Planner prefilter only - the live game still answers
    whether a specific cell is walkable when it matters (12.6)."""
    cx, cz = center[0], center[2]
    return any(abs(c[0] - cx) <= radius and abs(c[2] - cz) <= radius
               for c in cells)
