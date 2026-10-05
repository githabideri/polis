"""Embodiment: what is the bot's body doing TO and TO THE solid world?

2026-09-29 (the block-in-bot-cell incident): a build placed a block
into a cell the bot's body occupied; the engine kept the bot there,
half-embedded in solid geometry. Raw telemetry did not reveal it -
the bot's *position* is innocent-looking; the failure lives in the
RELATION between that position and the solidity of the cells around
it. So this module computes that relation.

Discipline (like projection.py / queries.py): narrow inputs (a
position + a cell->code map from a small scan), narrow outputs (one
classified state + a one-line detail). No harness, no I/O, no game
internals - the mission script feeds it and decides what to do:

    EMBEDDED  - a cell the body occupies is solid. Pathfinding is
                meaningless (you cannot route out of solid geometry).
                Rescue = dig the cell out (operator/devops), then
                the mission may resume.
    TRAPPED   - the body's cells are air, but all four horizontal
                neighbours at foot level are solid. No walk-out
                exists. Rescue = open a corridor.
    OK        - the body's cells are air and at least one horizontal
                neighbour is open: the bot can walk.

The body is treated as the feet cell plus the cell above (STRICT -
no straddle: a body touching a block's edge is squeezed, not
embedded; embedding is when the body's centre cells are solid).
`body_cells()` with straddle widening exists as a utility for
collision-adjacent reasoning. Solidity is a VOCABULARY judgement,
not a physics query: kinds the settlement builds or walks on (rock,
stone) are solid; air, soil, crops and unknowns are not (the scan's
"no block" is air anyway).
"""

from r2.queries import classify

#: kinds that solidly block a body
SOLID_KINDS = ("rock", "stone", "soil")  # 2026-10-05: 1.22 soil is a full cube (class BlockSoil)


def _strip(code):
    c = str(code or "")
    return c[len("game:"):] if c.startswith("game:") else c


def is_solid(code):
    """Vocabulary-level solidity: does a block of this code occupy a
    cell so that a body cannot share it?"""
    if not code:
        return False
    kind, _, _, _ = classify(code)
    if kind in SOLID_KINDS:
        return True
    # defensive: an unlisted rock-* code is still rock
    return _strip(code).startswith("rock-")


def body_cells(pos):
    """Utility: the cells a standing body occupies/overlaps: feet +
    head, widened by straddle (a position fraction < 0.3 or > 0.7
    means the body crosses that cell boundary). NOT what EMBEDDED
    uses - embedding is judged on the strict centre cells."""
    x, y, z = (int(p) for p in pos)
    fx, fz = pos[0] - x, pos[2] - z
    cells = {(x, y, z), (x, y + 1, z)}
    if fx < 0.3:
        cells.add((x - 1, y, z))
        cells.add((x - 1, y + 1, z))
    if fx > 0.7:
        cells.add((x + 1, y, z))
        cells.add((x + 1, y + 1, z))
    if fz < 0.3:
        cells.add((x, y, z - 1))
        cells.add((x, y + 1, z - 1))
    if fz > 0.7:
        cells.add((x, y, z + 1))
        cells.add((x, y + 1, z + 1))
    return cells


def embodiment(pos, cellmap):
    """Classify the body's relation to the solid world.

    pos: [x, y, z] floats (the bot's feet position).
    cellmap: {(x,y,z): block_code} - only the cells that were
    queried (a small scan around the bot); a missing key means "no
    block / air".

    -> (state, detail) with state in {"OK", "TRAPPED", "EMBEDDED"}.
    EMBEDDED is checked first and reports the worst cell (feet
    before head, then by position).
    """
    x, y, z = (int(p) for p in pos)
    feet = (x, y, z)
    # EMBEDDED: the strict centre cells (feet first - the worst
    # case, then the head). A body merely touching a neighbour's
    # edge is not embedded.
    for c in (feet, (x, y + 1, z)):
        code = cellmap.get(c)
        if code and is_solid(code):
            where = "feet" if c == feet else "body"
            return ("EMBEDDED",
                    "%s cell %r is solid (%s) - the bot is inside a "
                    "block; no path exists" % (where, c, code))
    # TRAPPED: feet cell air, but every horizontal neighbour at foot
    # level solid
    neigh = [(x + 1, y, z), (x - 1, y, z), (x, y, z + 1), (x, y, z - 1)]
    open_neigh = [n for n in neigh
                  if not (cellmap.get(n) and is_solid(cellmap.get(n)))]
    if not open_neigh:
        return ("TRAPPED",
                "body clear but all 4 horizontal neighbours solid "
                "%r - no walk-out" % (neigh,))
    return ("OK", "body clear, %d open neighbour(s)" % len(open_neigh))
