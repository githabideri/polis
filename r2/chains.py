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


@chain("anvil-copper")
def anvil_copper(color="fire", table_at=None, kiln_at=None,
                mold_at=None, ore="ore-copper", fuel="charcoal",
                pours=1, wait_s=120, insert_n=20, fuel_n=2,
                anvil_at=None, smith=None, give=()):
    """The G15 anvil cast chain (2026-11-17, world 7): clayform
    anvilmold -> kiln fire -> place the fired mold -> N x (crucible
    smelt + pour into the mold). The mold's fill is the engine's
    `requiredUnits = 900` (blocktypes/clay/fired/toolmold.json,
    measured on world 7): one crucible smelt pours 100 units, so
    9 pours complete the fill, the mold breaks, and it drops the
    `anvil-copper` block. The fill is WORLD-PERSISTENT (vcdbs) -
    pours may be split across sessions; `mold-info` is the fill
    oracle. With `anvil_at` the chain places the cast block
    (a `pickup` of the drop is the operator's live step - the drop
    lands at the mold) and, with `smith`, smiths the work item
    (default: the chisel from the bank's ingot). The anvil's work
    item must be >20C: the C# `anvil-heat` disclosed bypass stands
    in for fire heating (the gate is checked, not bypassed; the
    bypass is logged on the C# side).

    Parameters (live-world facts, supplied at invocation - never
    frozen here):

    color:      "fire" | "blue" | "red" - the clay color variant
                (raw `clay-<color>`, the clayform recipe
                `clayforming/anvilmold` -> `toolmold-<color>-raw-\
anvil`; the fired toolmold keeps the `fire` color name in its
                variant group)
    table_at:   [x, y, z] the clayform table cell (REQUIRED - the
                raw mold is produced in its groundstorage)
    kiln_at:    [x, y, z] the 1-deep pit-kiln hole's floor cell
                (REQUIRED - the fire step; the fired block lands in
                the storage at the hole floor)
    mold_at:    [x, y, z] the cell the FIRED toolmold block is
                placed at (REQUIRED - the pour target)
    ore/fuel:   the crucible cycle inputs (G14 convention: ore
                `ore-copper`, fuel `charcoal`)
    pours:      1..9 - how many smelt+pour cycles this invocation
                runs (9 completes the fill from an empty mold)
    wait_s:     the engine smelt wait (G14 used 120)
    insert_n / fuel_n: the slot counts (G14: 20 nuggets, 2 charcoal)
    anvil_at:   [x, y, z] where the cast anvil block is placed
                (operator-campaign only; implies the drop pickup
                was done live)
    smith:      (produced, workitem) - the trailing anvil_smith job
                (e.g. ("chisel-copper", "ingot-copper"))
    give:       [(item, qty), ...] external setup (a harness
                privilege, labeled scaffolding in the evidence) -
                e.g. the anvil block when the smithing branch is
                exercised before the 9-pour fill, or the ingot
                work item
    """
    if table_at is None or kiln_at is None or mold_at is None:
        raise ValueError(
            "anvil-copper: table_at, kiln_at and mold_at are "
            "required (the mold cannot float)")
    if color not in ("fire", "blue", "red"):
        raise ValueError("anvil-copper: color must be 'fire', "
                         "'blue' or 'red' (got %r)" % color)
    if not 1 <= int(pours) <= 9:
        raise ValueError("anvil-copper: pours must be 1..9 "
                         "(9 completes the 900-unit fill)")
    raw = "toolmold-%s-raw-anvil" % color
    fired = "toolmold-%s-fired-anvil" % color
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
        return "a%d" % n

    jobs.append({"id": nid(), "type": "clayform",
                 "at": [int(v) for v in table_at],
                 "material": raw,
                 "expect": "clay-%s" % color,
                 "origin": "deterministic"})
    jobs.append({"id": nid(), "type": "kiln_fire",
                 "at": [int(v) for v in kiln_at],
                 "material": fired,
                 "recipes": [raw], "origin": "deterministic"})
    jobs.append({"id": nid(), "type": "place",
                 "at": [int(v) for v in mold_at],
                 "material": fired, "origin": "deterministic"})
    for i in range(int(pours)):
        last = (i == int(pours) - 1) and int(pours) == 9
        jobs.append({"id": nid(), "type": "crucible_fire",
                     "material": crucible,
                     "origin": "deterministic"})
        jobs.append({"id": nid(), "type": "crucible_insert",
                     "material": ore, "n": int(insert_n),
                     "origin": "deterministic"})
        jobs.append({"id": nid(), "type": "crucible_fuel",
                     "material": fuel, "n": int(fuel_n),
                     "origin": "deterministic"})
        jobs.append({"id": nid(), "type": "wait",
                     "n": int(wait_s), "origin": "deterministic"})
        jobs.append({"id": nid(), "type": "crucible_take",
                     "material": "copper-melt", "n": 1,
                     "origin": "deterministic"})
        jobs.append({"id": nid(), "type": "crucible_pour",
                     "material": "copper-melt",
                     "at": [int(v) for v in mold_at],
                     "expect": ("anvil-copper" if last
                                else "mold-fill-%d" % (i + 1)),
                     "origin": "deterministic"})
    if anvil_at:
        jobs.append({"id": nid(), "type": "place",
                     "at": [int(v) for v in anvil_at],
                     "material": "anvil-copper",
                     "origin": "deterministic"})
        if smith:
            jobs.append({"id": nid(), "type": "anvil_smith",
                         "at": [int(v) for v in anvil_at],
                         "material": smith[0], "expect": smith[1],
                         "origin": "deterministic"})
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


@chain("pots")
def pots(clay="clay-red", clay_n=4, form_recipe="crucible-red-raw",
         fired=None, form_at=None, hole_at=None, firepit_at=None,
         meat="redmeat-raw", meat_n=2, fuel="charcoal", fuel_n=2,
         give=()):
    """The pot-work food chain (2026-10-10, J2-J5 of the early-game
    ladder - all four stages live-verified on the survival run;
    see STATUS.md). One end-to-end pass proves the fired-clay food
    capability: clay -> clayform table (raw item in the table's
    groundstorage) -> pit kiln (fired item from the hole storage) ->
    firepit cooking (the engine's own DoSmelt on the input slot) ->
    the bot eats (the shared policy-gated eat core).

    Parameters (live-world facts, supplied at invocation):

    clay / clay_n:      the clay item given to the bot (the only
                        permitted external input; 1.22 has clay-red
                        and clay-blue)
    form_recipe:        the clayform recipe's OUTPUT code
                        (e.g. crucible-red-raw, pot-red-raw)
    fired:              the expected FIRED item; default derived
                        (1.22 renames the fired color: red ->
                        earthyorange; other colors pass it explicitly)
    form_at:            [x, y, z] - the AIR cell the clayform table is
                        placed in (the executor clears it first; soil
                        tufts block the placement check)
    hole_at:            [x, y, z] - the floor cell of a 1-deep hole
                        (the pit kiln runs create/feed/ignite/ff in
                        one live session; the fired output lands in
                        the storage at that cell)
    firepit_at:         [x, y, z] - the firepit cell (fuel slot 0,
                        input slot 1, output slot 2). The bot fuels it
                        endogenously (firepit-fuel; a fresh, unarmed
                        firepit gets the deterministic firestarter
                        re-arm first) and puts the meat in the input
                        slot itself (firepit-put) - no operator slot
                        writes, no direct-ignite shortcut (2026-10-10)
    meat / meat_n:      the raw food to cook (default redmeat-raw)
    fuel / fuel_n:      the firepit's fuel (default charcoal)
    give:               additional (item, qty) external setup
    """
    for name, val in (("form_at", form_at), ("hole_at", hole_at),
                      ("firepit_at", firepit_at)):
        if val is None:
            raise ValueError(
                "pots: %s is required ([x, y, z])" % name)
    if not give:
        give = [(clay, clay_n), (meat, meat_n), (fuel, fuel_n)]
    if fired is None:
        parts = form_recipe.split("-")
        fired = (parts[0] + "-earthyorange-fired"
                 if len(parts) >= 3 and parts[1] == "red"
                 else (form_recipe[:-4] + "-fired"
                       if form_recipe.endswith("-raw")
                       else form_recipe))
    cooked = (meat[:-4] + "-cooked" if meat.endswith("-raw")
              else meat)
    jobs = []
    n = 0

    def nid():
        nonlocal n
        n += 1
        return "p%d" % n

    for i, (item, qty) in enumerate(give):
        jobs.append({"id": "g%d" % i, "type": "give_tool",
                     "material": item, "n": int(qty),
                     "origin": "operator"})
    jobs.append({"id": nid(), "type": "clayform",
                 "at": [int(v) for v in form_at],
                 "material": form_recipe,
                 "expect": clay,
                 "n": 1, "origin": "deterministic"})
    jobs.append({"id": nid(), "type": "kiln_fire",
                 "at": [int(v) for v in hole_at],
                 "material": fired,
                 "recipes": [form_recipe],
                 "n": 1, "origin": "deterministic"})
    jobs.append({"id": nid(), "type": "firepit_fuel",
                 "at": [int(v) for v in firepit_at],
                 "material": fuel, "n": int(fuel_n),
                 "origin": "deterministic"})
    jobs.append({"id": nid(), "type": "cook",
                 "at": [int(v) for v in firepit_at],
                 "material": cooked,
                 "recipes": [meat],
                 "n": int(meat_n),
                 "origin": "deterministic"})
    jobs.append({"id": nid(), "type": "eat",
                 "material": cooked, "n": int(meat_n),
                 "origin": "deterministic"})
    return jobs
