"""R2 make chains: deterministic multi-step tool fabrication (2026-10-11).

A `make <tool>` goal compiles to an ordered job list drawn from this
module: gather (inputs, via the source map / search-when-unobserved)
-> knap (a stone head on the knapping surface) -> craft (the grid
assembly: head + stick). Pure data - the mission compiler
(scripts/r2-live-mission.py) renders the steps into Job records and
the executor runs them through the existing harness commands
(`knap <x> <y> <z> <recipe> [speed]`, `craft <output-code>`).

Every code pair here is verified against the LIVE 1.22.7 recipe book
(pulled 2026-10-11, ~13k recipes) and the live code endpoint:
  knifeblade-flint = knap(2x flint)          (the 10-10 J1 live chain)
  knife-generic-flint = knifeblade-flint + stick
  axe-flint         = axehead-flint + stick
  hoe-flint         = hoehead-flint + stick
  shovel-flint      = shovelhead-flint + stick
  spear-generic-flint = spearhead-flint + stick
  firestarter       = drygrass + 2x stick
  torch-basic-extinct-up = 2x drygrass + 1x stick
  basket-normal-reed = 10x cattailtops
  door-crude        = any tool + 3x stick + 2x log
1.22 specifics that shape the chains:
  - knapping is NOT a grid recipe (no recipe-book entry for a head);
    the harness `knap` command runs the 10x10 voxel surface. The
    target cell must hold a KNAPPING SURFACE (solid soil/rock) -
    the command rejects a tallgrass cell ("No knapping surface").
  - drygrass comes from knife-harvested grass (open question, G12:
    whether bare-hand harvest also yields it - verify in-world).
  - the copper tier (pickaxe/hammer/saw + stick) is M9: the inputs
    are cast heads (crucible chain), not knappable - a later module
    phase, deliberately not here.
"""

# material -> item code(s) it resolves to (the gather verb's material
# word; the source map owns the block families). Kept in one place so
# chains and the source map cannot drift.
MATERIAL_ITEM = {
    "flint": "flint",
    "stick": "stick",
    "drygrass": "drygrass",
    "cattail": "cattailtops",
    "wood": "log",
}

#: tool -> ordered steps. step = (kind, material_or_code, qty).
#:   kind "gather" -> material word (source map; search when unobserved)
#:   kind "knap"   -> the head's OUTPUT code (the knap command's recipe
#:                    match is by output code path, 2026-10-11)
#:   kind "craft"  -> the output code (the live recipe table check)
CHAINS = {
    "knife": [
        ("gather", "flint", 2),
        ("knap", "knifeblade-flint", 1),
        ("craft", "knife-generic-flint", 1),
    ],
    "axe": [
        ("gather", "flint", 2),
        ("knap", "axehead-flint", 1),
        ("craft", "axe-flint", 1),
    ],
    "hoe": [
        ("gather", "flint", 2),
        ("knap", "hoehead-flint", 1),
        ("craft", "hoe-flint", 1),
    ],
    "shovel": [
        ("gather", "flint", 2),
        ("knap", "shovelhead-flint", 1),
        ("craft", "shovel-flint", 1),
    ],
    "spear": [
        ("gather", "flint", 2),
        ("knap", "spearhead-flint", 1),
        ("craft", "spear-generic-flint", 1),
    ],
    "firestarter": [
        ("gather", "drygrass", 1),
        ("gather", "stick", 2),
        ("craft", "firestarter", 1),
    ],
    "torch": [
        ("gather", "drygrass", 2),
        ("gather", "stick", 1),
        ("craft", "torch-basic-extinct-up", 1),
    ],
    "basket": [
        ("gather", "cattail", 10),
        ("craft", "basket-normal-reed", 1),
    ],
    "door": [
        ("gather", "stick", 3),
        ("gather", "wood", 2),
        ("craft", "door-crude", 1),
    ],
}

#: which stone a head knaps from (flint is the standard early stone;
#: granite/andesite/chert/basalt/peridotite all knap too - the source
#: map's loose-stone gather covers them). One entry per head family.
KNAPOUS_STONE = {
    "knifeblade-flint": "flint",
    "axehead-flint": "flint",
    "hoehead-flint": "flint",
    "shovelhead-flint": "flint",
    "spearhead-flint": "flint",
}


def steps_for(tool, n=1):
    """The step list for making n of a tool: gathers scale with n,
    knap/craft quantities are n. Unknown tool -> KeyError (the
    compiler reports it as 'no make chain for X yet')."""
    if tool not in CHAINS:
        raise KeyError(tool)
    out = []
    for kind, what, per in CHAINS[tool]:
        out.append((kind, what, per * n))
    return out
