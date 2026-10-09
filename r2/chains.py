"""
Mission-plan templates - a chain is DATA.

The campaign mode (r2-live-mission.py --jobs) takes an explicit
deterministic job list; before this module, such lists were typed
inline in sessions (the door and bridge chains, 2026-10-06/07) and
evaporated with them. A chain template is the same list, rendered as
data against live-world parameters (positions, item codes, counts)
at invocation time - the "a building is data" principle (builds/*.json)
applied to work.

The catalog is the validator (r2/jobs.py); campaign=True in
validate_plan is the gate that admits the GOAL-SCOPED job types these
chains use (forage, the crucible family). A rendered chain passes
through the same pre-execution checks as any operator campaign (live
cell scan, recipe table, material ledger) before anything runs.

Pure: render() returns JSON-serializable job dicts - no harness, no
world. New chains arrive as new @chain functions, not new runner code.
"""

#: name -> template function. The runner's --chain flag renders by name
#: with a JSON parameter object.
CHAINS = {}


def chain(name):
    """Register a chain template under its runner name."""
    def deco(fn):
        CHAINS[name] = fn
        return fn
    return deco


@chain("crucible-copper")
def crucible_copper(color="fire", ore="ore-copper", fuel="charcoal",
                    product="copper", melt="copper-melt",
                    firepit_at=None, mold_at=None,
                    wait_s=120, insert_n=1, fuel_n=1, give=()):
    """The 1.22 crucible smelt chain (2026-10-07 survival run, contract
    B2): craft crucible -> goto firepit -> crucible-fire ->
    crucible-insert <ore> -> crucible-fuel <fuel> -> wait (engine
    smelt progress) -> crucible-take -> crucible-pour <mold>.

    Parameters (live-world facts, supplied at invocation - never
    frozen here):

    color:     "fire" | "blue" | "red" - the clayform recipe's color
               variant; the bot crafts the `crucible-<color>-raw`
               block (clayform recipe `clayforming/crucible`, input
               `clay-<color>`) and the C# crucible-fire places it
               from the cargo into a firepit. (The 1.21 doc's
               small/medium size axis has no engine counterpart in
               1.22.7 - colors only.)
    ore:       the ore item code for the smelt slots
    fuel:      the fuel item code (or the `charcoal` keyword)
    product:   the item the engine is expected to produce at the mold
               (the ORACLE's claim - the measured delta is the proof,
               not this string)
    melt:      the symbolic intermediate the ledger passes between
               take and pour (the engine's melted state; unknown item
               codes stay symbolic - unknown is never yes)
    firepit_at: [x, y, z] firepit cell (optional - crucible-fire finds
               the nearest firepit from the bot; given, the chain
               walks there first and pins the fire to the cell)
    mold_at:   [x, y, z] mold ground position (REQUIRED - a pour
               without a mold is a plan smell)
    wait_s:    the wait job's seconds (the engine smelt duration;
               template parameter - the operator tunes it to the
               engine's honest pace)
    insert_n / fuel_n: slot counts
    give:      [(item, qty), ...] external setup the campaign prepends
               (a harness privilege, not a world fact) - e.g. the clay
               the crucible recipe eats, when the bot starts empty
    """
    if mold_at is None:
        raise ValueError(
            "crucible-copper: mold_at (the mold ground position) is "
            "required - a pour without a mold is a plan smell")
    if color not in ("fire", "blue", "red"):
        raise ValueError("crucible-copper: color must be 'fire', "
                         "'blue' or 'red' (got %r)" % color)
    crucible = "crucible-%s-raw" % color
    jobs = []
    for i, (item, qty) in enumerate(give):
        jobs.append({"id": "g%d" % i, "type": "give_tool",
                     "material": item, "n": int(qty),
                     "origin": "operator"})
    n = len(jobs)

    def nid():
        nonlocal n
        n += 1
        return "c%d" % n

    jobs.append({"id": nid(), "type": "craft",
                 "material": crucible, "source": "clayforming/crucible",
                 "n": 1, "origin": "deterministic"})
    if firepit_at:
        jobs.append({"id": nid(), "type": "goto",
                     "at": [int(v) for v in firepit_at],
                     "origin": "deterministic"})
    fire = {"id": nid(), "type": "crucible_fire",
            "material": crucible, "origin": "deterministic"}
    if firepit_at:
        fire["at"] = [int(v) for v in firepit_at]
    jobs.append(fire)
    jobs.append({"id": nid(), "type": "crucible_insert",
                 "material": ore, "n": int(insert_n),
                 "origin": "deterministic"})
    jobs.append({"id": nid(), "type": "crucible_fuel",
                 "material": fuel, "n": int(fuel_n),
                 "origin": "deterministic"})
    jobs.append({"id": nid(), "type": "wait",
                 "n": int(wait_s), "origin": "deterministic"})
    jobs.append({"id": nid(), "type": "crucible_take",
                 "material": melt, "n": 1, "origin": "deterministic"})
    jobs.append({"id": nid(), "type": "crucible_pour",
                 "material": melt, "at": [int(v) for v in mold_at],
                 "expect": product, "origin": "deterministic"})
    return jobs


def render(name, params=None):
    """Render a registered chain to its --jobs list. params is the
    JSON object the operator passes via --chain-params; unknown
    parameters are a TypeError (a template typo, caught at render
    time, not discovered mid-campaign)."""
    fn = CHAINS.get(name)
    if fn is None:
        raise KeyError("unknown chain %r (available: %s)"
                       % (name, ", ".join(sorted(CHAINS))))
    return fn(**(params or {}))

@chain("flint-tools")
def flint_tools(material="flint", surface_at=None,
                knife="knife-generic-flint", axe="axe-flint",
                knife_source="recipes/grid/tool/knife.json",
                axe_source="recipes/grid/tool/axe.json",
                give=()):
    """The P1 stone-tools chain (2026-10-10, J1 of the early-game
    ladder): place the knapping surface -> chip blade + axehead ->
    grid-assemble the knife and the axe.

    Parameters (live-world facts, supplied at invocation - never
    frozen here):

    material:     the chipping material item the bot carries
                  (default "flint" - the world's looseflints block
                  drops it; chert/granite/... via stone-<type>)
    surface_at:   [x, y, z] the cell the knapping surface block is
                  placed at (REQUIRED - the chip cannot float). The
                  knap job places it from cargo if the cell is not
                  a surface yet.
    knife / axe:  the grid-assembly output codes (1.22.7:
                  "knife-generic-flint" = knifeblade-flint + stick,
                  1x2 shaped; "axe-flint" = axehead-flint + stick)
    knife_source / axe_source: the live recipe table names
                  (the /polis/recipes asset paths; the validator
                  also matches by unique output)
    give:         [(item, qty), ...] external setup the campaign
                  prepends (a harness privilege, labeled
                  scaffolding in the evidence). DEFAULTS to the
                  contract-test scaffolding: the chipping material,
                  one surface item PER CHIP (the engine consumes the
                  knapping surface block on completion - live-
                  measured 2026-10-09), and two sticks. An
                  endogenous P1 run replaces these with
                  pick/chop jobs.
    """
    if surface_at is None:
        raise ValueError(
            "flint-tools: surface_at (the knapping surface cell) is "
            "required - the chip cannot float")
    if not give:
        give = [(material, 2), ("knappingsurface", 2), ("stick", 2)]
    jobs = []
    n = 0

    def nid():
        nonlocal n
        n += 1
        return "f%d" % n

    for i, (item, qty) in enumerate(give):
        jobs.append({"id": "g%d" % i, "type": "give_tool",
                     "material": item, "n": int(qty),
                     "origin": "operator"})
    jobs.append({"id": nid(), "type": "knap",
                 "at": [int(v) for v in surface_at],
                 "material": material,
                 "recipes": ["knifeblade-flint", "axehead-flint"],
                 "n": 1, "origin": "deterministic"})
    jobs.append({"id": nid(), "type": "craft",
                 "material": knife, "source": knife_source,
                 "n": 1, "origin": "deterministic"})
    jobs.append({"id": nid(), "type": "craft",
                 "material": axe, "source": axe_source,
                 "n": 1, "origin": "deterministic"})
    return jobs
