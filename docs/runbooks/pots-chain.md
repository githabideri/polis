# Runbook: the pots chain (clay → cooked meat → eat)

The pot-work food capability as one reproducible run. It proves the
fired-clay food ladder end to end in a single session:

```
clay (given) -> clayform table -> raw crucible
             -> pit kiln (create/feed/ignite/ff) -> fired crucible
             -> firepit (fuel + raw meat, the engine's own DoSmelt)
             -> cooked meat -> the bot eats (policy-gated)
```

Every stage runs the ENGINE'S OWN machinery (the game's clayform
table, the game's `BlockEntityPitKiln`, the firepit's `DoSmelt`, the
shared eat core) — the harness only moves bodies and reads state. The
only permitted external input is the clay and the raw meat the chain
gives the bot (the bare-start rule).

Verified: run7 (2026-10-10, survival-5), 6 jobs, 197 s, all ok; the
same run dispatched by the Oikistes brain through its `pots` tool.

## Sites (what you need in the world)

| site | what | how to place it |
|------|------|-----------------|
| `form_at` | an AIR cell where the clayform table is placed (the executor clears it to air first — soil tufts block the placement check) | anywhere at ground level next to a walkable cell; the bot walks to the cell beside it |
| `hole_at` | the FLOOR cell of a 1-deep hole (the pit kiln) | dig a 1-deep hole with `setblock air` / a mine job; the floor block may be anything solid |
| `firepit_at` | a `game:firepit-*` block | place one (`setblock game:firepit-extinct` or the place command) |

Find them with the Oikistes `query` tool (zone or coordinates), or
`polisctl` / the harness `scan` from the terminal. The cells are
`[x, y, z]` with y = the block layer.

## Three ways to run it

### 1. The chain runner (operator, terminal)

```
cd <polis-repo>
python3 scripts/r2-live-mission.py \
  --harness http://127.0.0.1:8585 --uid <playerUid> \
  --chain pots \
  --chain-params '{"form_at":[X,Y,Z], "hole_at":[X,Y,Z], "firepit_at":[X,Y,Z]}' \
  --keep-bots <botId> \
  --goal "pots chain: clay to cooked meat" \
  --out /tmp/pots-run.json
```

Optional params: `clay` (default `clay-red`), `clay_n` (4), `meat`
(`redmeat-raw`), `meat_n` (2), `fuel` (`charcoal`), `fuel_n` (2),
`form_recipe` (`crucible-red-raw`), `fired` (default derived — 1.22
renames the fired color: red → earthyorange; pass it explicitly for
other colors).

The run JSON is the record: per job, the engine's verdict
(`execution`) and the fresh-world oracle (`oracle`) are separate
fields (the 12.6/13.2 split).

### 2. Through Oikistes (the brain dispatches it)

```
POST /oikistes/chat  {"message": "Run the pots chain at base now:
clayform table at X,Y,Z; kiln hole floor at X,Y,Z; firepit at X,Y,Z."}
```

The brain calls its `pots` tool (the three cells are required), the
mission runs in the background (90-min cap), and a later `mission`
query (no goal) reports the verdict. This is the autonomy path: the
operator says "make food", the Oikistes finds the cells and orders
the work.

### 3. Stage by stage (harness, for diagnosis)

```
clayform <x> <y> <z> crucible-red-raw 8   # ~5 s sculpt; output in
                                           # the table's groundstorage
kiln create <x> <y> <z> crucible-red-raw 1  # the [item qty] args are
                                           # how the kiln gets its cargo
kiln feed <x> <y> <z>                      # all build stages
kiln ignite <x> <y> <z>
kiln ff   <x> <y> <z>                      # fast-forward the 20 h burn
# fired item now in the storage at the hole floor (container-take it)
container-set <x> <y> <z> 0 charcoal 2      # firepit: fuel slot
container-set <x> <y> <z> 1 redmeat-raw 2    # raw food, INPUT slot
be <x> <y> <z> igniteFuel                   # the 0-arg method call
# poll container-contents; the cooked meat appears in slot 2
eat redmeat-cooked 2                        # the shared eat core
```

## Engine facts (the ones that bite)

1. **The pitkiln block is non-persistent** (aux-style): `SetBlock`
   applies in memory but a chunk save reverts the cell. The whole
   create→feed→ignite→ff sequence must run in ONE live session; the
   fired output (in the persistent storage block at the hole floor)
   survives.
2. **`kiln create` has no other cargo input path**: it preserves a
   fireable item only if it is already in the hole storage or passed
   as the `[itemCode qty]` arguments. Without it, the kiln fires
   nothing.
3. **The firepit cooks the INPUT slot (1) only** via the item's own
   `DoSmelt` (fuel slot 0, output slot 2). A fired pot in the
   firepit is a no-op for single-ingredient food — the pot matters
   for multi-ingredient meals (cooking slots 3–6). The old 1.21
   "meat in the pot over the firepit" picture is wrong for 1.22.
4. **Goto is not a distance truth**: long walks get declared failed
   by the engine while the bot keeps walking. The chain executor
   polls the bot's actual position and re-issues until in range
   (4.5 m workstation reach) or the 180 s budget runs out.
5. **Placement checks treat soil tufts as blocking**: the clayform
   table's cell must be cleared to air first (the executor does it).
6. **Short item codes resolve** (the policy gate, the inventory
   helpers and the eat command all resolve through `AssetLocation`
   — "redmeat-cooked" matches "game:redmeat-cooked").
7. **Item codes are 1.22-renamed**: dirt → soil, red →
   earthyorange (fired clay), the fuel is `charcoal` /
   `log-grown-pine-ud`.

## Failure modes seen (and their fix)

| symptom | cause | fix |
|---------|-------|-----|
| `cannot place ... blocked by game:soil-low-*` | tuft in the target cell | the executor clears to air; manually: `setblock game:air` |
| `Out of range: N > 4.5` | the bot is not next to the workstation | walk it (the chain does); manually `goto <adjacent cell>` |
| kiln all-`True` but no fired item | `create` got no `[item qty]` args | pass them; or pre-fill the hole storage |
| cook never outputs | meat in the wrong slot | fuel=0, meat=1 (input), read slot 2 |
| `policy denied: domain default: deny` on eat | the item code was not resolved before the policy check | fixed in `PolisEatService` (resolved code); the rule lives in `assets/polis/polis-policies.json` (cooked meat is allowed by the default profile) |
