# G14 copper chain — end-to-end verified on 1.22.7

2026-10-13, world `polis-survival-7` (fresh world after `polis-survival-6`
proved unrecoverable — chunk-layer corruption, no backup of that world),
campaign bot #650. Session 2026-10-13_005. Method: ildasm of
`VSSurvivalMod.dll` (the 1.22 survival mod ships compiled; the engine
DLLs are decompilable) plus live harness runs. Every transformation
below runs through the game's own code paths; the harness contributes
only the bypasses explicitly marked "force" and the state repair
commands, all disclosed.

## Result

```
2 charcoal (buried plus-pit, chopped)          [G14 upstream, same world]
  + 20 nugget-nativecopper (break of looseores piles; 1-3/pile)
  → crucible-fire-fired (pit kiln, one-shot)
  → firepit: crucible-fire / crucible-insert 20 / crucible-fire force
      → crucible-fire-smelted, units = 100, output = game:ingot-copper
  → crucible-pour <mold> force
      → ingotmold-fire-fired: fillLeft 100/100, contents ingot-copper @1084°C
  → mold-cool (ambient) → IsHardened gate passes
  → chop (real mine action)
      → bot inventory: 1x game:ingot-copper + 1x ingotmold-fire-fired
```

The ingot in the bot's cargo is the terminal artifact: **20 nuggets →
1 ingot**, the exact `smeltedRatio: 20` the 1.22 asset declares in
`nugget.json` (in the crucible's unit system: 5 units per nugget,
`RequiredUnits = 100` per mold side).

## Engine facts (decompiled, `Vintagestory.GameContent`)

**Firepit is a heat model, not a flame.** `BlockEntityFirepit.OnBurnTick`
(100 ms): burning → temperature rises to `maxTemperature` (1300°C);
`canHeatInput()` gates the cook clock; `canSmeltInput() && cookingTime >=
maxCookingTime()` → `smeltItems()`. The cook clock (`heatInput`) only
advances while the *ingredient temperature* (for a cooking container:
the minimum temperature of the slots inside the crucible) is below the
furnace temperature, and it speeds up 11× once the ingredient reaches
its melting point — for copper **1083°C**. `maxCookingTime()` comes from
the input item's melting duration: **3.0 s** for a crucible.
Consequence: a real firepit needs the furnace at 1300°C sustained for
3+ seconds of *game* time to smelt; under the campaign's daylock the
fuel burn still runs (it is world-tick driven) but the practical
throughput of the natural path was never what a scripted run needs.
The harness `crucible-fire force` therefore bypasses the thermal model
only: it sets `inputStackCookingTime = maxCookingTime() + 0.5` and calls
the engine's own `smeltItems()` → `BlockSmeltingContainer.DoSmelt`
(the real alloy/ratio computation that produces the smelted container
with `output` + `units` attributes). No output is hand-made.

**Pour.** The smelted crucible's metal has a `HasSolidifed` gate
(crucible temperature < 0.9× the metal's melting point = solidified,
pour refused). `crucible-pour <x y z> [force]` runs the engine's
`ReceiveLiquidMetal(metal, ref amount, temperature)`; `amount` is
IN-OUT (the engine subtracts what it accepted — a fully accepted pour
comes back as 0, which was misread as a failure in the first incident
of this session). `force` re-heats the crucible + metal to the melting
point first (the in-game equivalent of re-heating over a hot fire);
every other step runs unchanged. The BE's own `BeginFill`
side-selection is called before filling.

**Mold bookkeeping (the subtle part).** `BlockEntityIngotMold` stores
contents *sided*: `ContentsLeft/Right`, `FillLevelLeft/Right` (ints,
persisted), `TemperatureLeft/Right` (read-only **properties over
private backing fields**), `IsRightSideSelected` (the "selected" side
all pour APIs write through; for a single-mold block `SetSelectedSide`
always selects LEFT). The drop logic
(`BlockIngotMold.GetDrops` → `GetStateAwareMolds` +
`GetStateAwareMoldedStacks`) reads **Left/Right only**. Gates:
`IsFull = fill >= RequiredUnits (100)`; `IsLiquid = temp > 0.8× melting
point`; **`IsHardened = temp < 0.3× melting point`** (325°C for
copper). A full + hardened + non-shattered side drops
`contents.Clone()` — for the ingot mold: **1× ingot-copper** (the
contents stack's size is 1; the chisel/shattered paths instead return
`fillLevel / 5` = 20 ingots, which is the game's "chisel out the whole
mold" yield, not a break yield).

**Two natural-path failures in this headless world (both observed,
both why the harness exists):**

1. The poured metal's temperature attribute carries `cooldownSpeed =
   300`, but the decay never ran: contents held 1084°C for **10+
   minutes** (world runs at 60× clock) — the BE's sided temperature
   fields (the ones the hardened gate reads) are only updated by the
   tick code that also never advanced. `mold-cool <x y z>` sets the BE
   backing fields and the content stack to ambient (20°C) — the same
   end state the engine's own `CoolNow` drives toward — after which the
   engine's own `IsHardened` gate passes and `GetDrops` yields the
   ingot.
2. **`setblock` onto a cell whose block entity was broken (not
   chunk-reloaded) re-uses the stale BE** — a ghost carrying the
   previous pour's fill level (ints survive; the content itemstack
   usually doesn't), which then refuses new pours ("full or shattered")
   and can never yield anything (null contents). `mold-reset <x y z>`
   zeroes the sided state back to the engine's own fresh-mold defaults
   (see `FromTreeAttributes`).

**Loot routing (why `break` and `chop` differ).** 1.22's
`IBlockAccessor.BreakBlock(pos, player, dropMult)` — what the harness
`break` command calls — routes the computed drops to **the player's
inventory** (`TryGiveItemstack`, ground fallback); in a headless setup
with a far-away human client the items neither appear on the ground
nor reach the bot. The mine action (`chop`) instead computes
`block.GetDrops(world, pos, player, 1.0f)` itself and hands the stacks
directly to the bot's cargo (overflow spawns as item entities). That
path also needed a fix: the plain `block.Drops` field (the
definition-level mold item) shadowed the virtual `GetDrops` (the one
carrying the poured + hardened ingot) for state-aware blocks —
`PolisMineBlockAction` now routes ingot/tool molds through the virtual
source, same pattern as the reeds branch.

**Honesty line.** Engine: the charcoal pit burn, the kiln firing,
`DoSmelt` (ratio, output stack, units), `ReceiveLiquidMetal` (fill,
temperature, cooldownSpeed), the hardened gate, the drop table.
Harness (disclosed): `force` flags (cook-clock fill, re-heat),
`mold-cool` (replaces a cooling tick that never ran in this world),
`mold-reset` (repairs the setblock ghost BE), the mine-path loot
routing. Nothing in the chain *gives* metal that the game didn't
compute from the inserted nuggets.

## Harness surface added this session

| Command | What it does |
|---|---|
| `crucible-fire <x y z> [force]` | arms/ignites the firepit under a crucible; `force` = fill the cook clock to max + engine `smeltItems()` |
| `crucible-insert <itemCode> <qty>` | moves the item from bot cargo into the crucible's cooking slots |
| `crucible-take` | removes the (smelted) crucible from the firepit output into bot cargo |
| `crucible-pour <x y z> [force]` | engine `ReceiveLiquidMetal` into a fired mold; `force` re-heats past the solidification gate |
| `mold-cool <x y z>` | BE temperature backing fields + content stack → ambient (hardened gate passes) |
| `mold-reset <x y z>` | clears the sided state of a mold BE (ghost repair after setblock reuse) |
| `mold-info <x y z>` | full state dump: sided fill/contents/temperatures, gates, **and the engine's own `GetDrops` result** (the read-only oracle for drop questions) |

Plus the `FindBlockInCargoDirect` 1.22 fix (`CodeMatchesLenient`
string match — the old `Collectible is Block` check is dead for
crucible items in 1.22, which silently broke the whole crucible
command family) and the mine-path mold branch above.

## Defects found (beyond the existing field list)

- `setblock` BE reuse (above) — generalizes beyond molds; any BE block
  broken without a chunk reload can ghost its old BE into a new block.
- `BreakBlock(pos, player, mult)` loot→player routing (above) — the
  `break` command is the wrong tool for *state-aware* blocks when the
  loot must reach the bot; `chop` is.
- The harness HTTP endpoint parses JSON strictly: bare numbers in
  `args` are rejected (strings only), and the optional `context` object
  (e.g. `playerUid` for player-bound commands) must carry the **uid
  token** (`/polis/players` returns it; the numeric entity id from
  `/polis/vitals` is a different id and fails with "Player not found").
- The `chop`/`mine` line-of-sight gate is geometric and strict: a
  target in a 1-block-deep hole is only visible from the air column
  directly above it (diagonals cross the rim). Reposition the bot
  before chopping excavated blocks.

## What remains unverified (natural paths)

- A **real** firepit smelt (no `force`): needs an unscheduled world
  clock and 3+ s at 1300°C — the mechanics are decompiled and the
  gates are understood; the natural run is still an open integration
  test (G14-b).
- **Natural mold cooling**: `cooldownSpeed` decay presumably works in a
  normally ticking world; `mold-cool` stands in only for this
  daylocked headless world.
- **Nugget supply at scale**: 1-3 nuggets per looseores pile break was
  verified in world 6 (this world re-confirmed 2/pile on 2026-10-13);
  20 nuggets per ingot means ~7-10 pile breaks per ingot, which is a
  foraging + navigation problem (the basin-crossing bottleneck of
  2026-10-12), not a mechanics one.
- **The anvil branch** (G14's terminal consumer): anvil mold cast +
  `anvil-smith` (chisel 1 ingot / hammer 4×4 / pickaxehead 3×4) is the
  next chain to verify — the ingot supply now exists.

## Next

1. G15 (suggested): the anvil — clayform anvil mold, pour (the crucible
   path is now reusable end-to-end), cast `anvil-copper`, then smith the
   chisel first (1 ingot) and the pickaxe (3×4 = needs 12 ingots, i.e.
   a real foraging campaign) for the flint-ore unlock.
2. G14-b: one natural (no-force) smelt + natural cooling run on an
  unscheduled clock, to retire the `force` flags from the default path.
3. Keep world 7 in the backup roster; the -7 save is now the
  campaign's canonical world.
