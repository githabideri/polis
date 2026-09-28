"""
Approach resolution (13.6 step 1, formalizing the probe's neighbour
loop).

The terminology change: `goto(position)` (move a point; the pathfinder
stops where it can) and `approach(target, interaction predicate)`
(position oneself so an INTERACTION with the target succeeds) are
separate executor concepts. A mine/harvest job means "interact
successfully with the target block", not "stand on exactly X/Y/Z";
for an occupied solid block the valid destinations are the
neighbouring walkable cells around it.

candidates(target, solid_cells, from_pos)
    PURE. The ordered candidate list: the target cell itself first
    (the pathfinder stops one cell short of a solid - already in
    interaction range, and it is the least movement), then the
    ground-level neighbours ordered by distance from the bot's
    current position; a neighbour that is itself occupied by a solid
    block is filtered (you cannot stand in it). The target itself is
    never filtered.

approach(goto, try_action, from_pos, target, solid_cells)
    The driver with INJECTED callables (unit-testable without a
    game): for each candidate in order - `goto(cell)` (a point
    move); on a successful arrival `try_action()` (the interaction)
    runs and the ENGINE'S verdict decides:

      - action ok                     -> success (stop)
      - action failed with a
        range/LOS/stuck-class reason  -> next candidate
      - action failed definitively
        (e.g. "Tool required: tier 2") -> stop, that is the answer
      - goto stuck/failed             -> next candidate

    From the queue's perspective this whole loop is ONE job attempt:
    the JobQueue sees one running job, not six failed gotos (13.6).
    Returns (ok, detail, attempts, last_la) where attempts is the
    auditable per-candidate log for the run JSON.

No game imports here: everything the driver needs is injected.
"""

#: a failed action whose reason is in this set is worth retrying from a
#: different cell; anything else is definitive (a tool gap, a wrong
#: block, ... will not change with position)
RETRIABLE_MARKERS = (
    "range", "line of sight", "los", "stuck", "timeout",
    "out of", "too far",
)


def candidates(target, solid_cells, from_pos, radius=1):
    """Ordered approach candidates for an occupied solid block cell.

    target:      (x, y, z) the block cell
    solid_cells: iterable of cells occupied by solid blocks (the
                 scanner's view; the target itself included or not -
                 it is handled separately)
    from_pos:    (x, y, z) the bot's current position (distance order)
    """
    t = (int(target[0]), int(target[1]), int(target[2]))
    sol = set()
    for c in solid_cells:
        sol.add((int(c[0]), int(c[1]), int(c[2])))
    out = [t]
    seen = {t}
    nbs = []
    for dx in (-radius, 0, radius):
        for dz in (-radius, 0, radius):
            if dx == 0 and dz == 0:
                continue
            c = (t[0] + dx, t[1], t[2] + dz)
            if c in seen:
                continue
            seen.add(c)
            if c in sol:
                continue  # cannot stand inside a solid block
            nbs.append(c)
    fx, fz = int(from_pos[0]), int(from_pos[2])
    nbs.sort(key=lambda c: (abs(c[0] - fx) + abs(c[2] - fz), c))
    return out + nbs


def _retriable(msg):
    m = (msg or "").lower()
    return any(k in m for k in RETRIABLE_MARKERS)


def approach(goto, try_action, from_pos, target, solid_cells,
             max_candidates=9):
    """Walk the candidates; return (ok, detail, attempts, last_la).

    goto(cell)       -> {"ok": bool, "msg": str}
    try_action()     -> {"ok": bool, "last_action": {...}}
    """
    cands = candidates(target, solid_cells, from_pos)[:max_candidates]
    attempts = []
    last_la = {}
    for c in cands:
        g = goto(c)
        if not g.get("ok"):
            attempts.append({"cell": list(c), "stage": "goto",
                             "ok": False,
                             "msg": str(g.get("msg") or "")[:80]})
            continue
        res = try_action() or {}
        la = res.get("last_action") or {}
        last_la = la
        if res.get("ok") and la.get("Ok") is True:
            attempts.append({"cell": list(c), "stage": "action",
                             "ok": True,
                             "msg": str(la.get("Msg") or "")[:80]})
            return True, "approach via %s: action ok" % (c,), attempts, la
        attempts.append({"cell": list(c), "stage": "action",
                         "ok": False,
                         "msg": str(la.get("Msg") or "")[:80]})
        if la.get("Ok") is False and not _retriable(la.get("Msg")):
            return False, ("approach via %s: action failed "
                           "definitively (%s)"
                           % (c, str(la.get("Msg") or "")[:80])), \
                attempts, la
        # retriable: the next candidate cell
    return (False,
            "approach failed after %d candidate(s): %s"
            % (len(attempts), attempts),
            attempts, last_la)
