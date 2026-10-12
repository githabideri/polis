# G14 — 1.22 copper bootstrap: what the game assets actually say

Night of 2026-10-11/12, session 2026-10-10_006. Method: game asset JSON
(CT 249 `/opt/vintagestory/extra/vintagestory/assets/survival/`) + ILDASM of
`vssurvival.dll` (`/tmp/vssurv.ild` on the CT). No gameplay was faked; the
only world actions were disclosed (ripen, one teleport of the godmode
player, bot walks/pokes).

## The chain (all verified against assets)

| Step | Mechanic | Verified by |
|---|---|---|
| 1. Get a **hammer** | World **clutter** (`stackrandomizer-clutter/mines.json`): breaking clutter piles (`pile-tools*`, scribe desks, mine rubble) drops tools incl. `tool-hammer` with a random metal variant. **`hammer.json` variant list starts at copper** (copper, tinbronze, …, steel) — no stone/flint tier. | itemtypes/meta/stackrandomizer-*.json; itemtypes/tool/hammer.json |
| 2. Get **ore** | `ore-{grade}-nativecopper-{rock}` block (BlockOre) → item `ore-{grade}-nativecopper-{rock}` (ItemOre). World 6: 60 blocks within r64 of camp, all y95-106 (buried 5-17 deep under claystone/rock). **No stone pickaxe exists in 1.22** (`pickaxe.json` variants start at copper). Open question: is the ore hand-breakable? (the whole 1.22 early game implies native metal must be gettable without a pickaxe — but the ore here is deep). | itemtypes/tool/pickaxe.json; `/polis/targets?codeContains=ore-medium-nativecopper&includePlain` |
| 3. Ore → **nugget** | Grid recipe `nuggets.json`: **`tags: ["tool-hammer"], isTool: true`** (any hammer item) + `ore-{grade}-{ore}-*` → `nugget-{ore}` (qty from ore attributes). Tag-based, not code-based. | recipes/grid/nuggets.json |
| 4. Nugget → **ingot** | **Crucible** (clayform → kiln-fired, sits on firepit). `BlockSmeltingContainer.CanSmelt`: matches an **alloy recipe** (vanilla `alloy.json` has **zero variants** — dead path) OR the item's **CombustibleProperties/smeltedStack**. `nugget.json` carries `smeltedRatio: 20 → ingot-copper`. `GetMetal(stack)` = `stack.Variant["metal"]` (ore items have no `metal` variant key → **ore items are NOT crucible-smeltable**; nuggets/ingots are). | recipes/grid/nuggets.json; itemtypes/resource/nugget.json; ILDASM CanSmelt/GetMetal (276355, 276690) |
| 5. Ingot → **tools** | **Anvil** (`anvil-copper` block, variant copper). `anvil-smith` command: needs the anvil block + a **hot work item (>20°C = molten metal poured onto the anvil, which is an ILiquidMetalSink — "anvilmergehit")** + a smithing recipe: `chisel` (1 ingot), `hammer` (4×4 ingot grid), `pickaxe` (3×4 ingot grid). Outputs `chisel-copper`, `hammerhead-copper`/`hammer-copper`, `pickaxehead-copper`; grid-combine with a stick. **Anvil base/top (anvilpart) smithing only allows iron+** — the first anvil is cast, not smithed. | recipes/smithing/{chisel,hammer,pickaxe}.json; blocktypes/metal/{anvil,anvilpart}.json; recipes/clayforming/anvilmold.json |
| 6. Anvil from **clay** | Clayform `toolmold-{color}-raw-anvil` → pour molten copper from crucible → `anvil-copper` block. (Circularity note: the mold needs molten copper, which needs nuggets, which need a hammer — so the anvil-cast is step 5's *refresh*, not the bootstrap.) | recipes/clayforming/anvilmold.json |

**So the 1.22 first-metal path is:** find/obtain a hammer (clutter) → hammer
ore into nuggets → crucible-smelt nuggets → pour into ingot mold / anvil
mold → anvil → chisel + hammer + pickaxehead → grid: pickaxe → mine flint
ore (world 6 has 100 flint-claystone) → iron etc. The **only** missing
link is the *first* hammer: a world clutter drop.

## Empirical state (unresolved, needs a live test)

1. **`looseores-nativecopper-*`** (1 in world, at 512122,112,511981):
   `RightClickPickup { dropsPickupMode: true }` — but (a) 1.22 moved block
   interact to **IPlayer-only** `OnBlockInteractStart` (bodies can't
   right-click blocks), and (b) **no `looseores` itemtype exists**, so
   `OnPickBlock` (the drop source) resolves to nothing. My `activate`
   (bot, adjacent, LOS ok) did nothing: block stayed, no item anywhere.
   Likely a 1.22 dead-end or engine quirk — needs one careful test with a
   *player* right-click (noVNC) to settle whether anything drops.
2. **Ore hand-minability**: ore buried under 5-17 blocks of claystone/rock;
   the mission `mine` job will not auto-give tools anymore (integrity fix
   5afaa72 this session — the old code silently handed an IRON pickaxe,
   which would have eaten the whole copper quest).
3. **Clutter near camp**: 73 clutter blocks within r64 of camp, but the
   targets endpoint doesn't expose the clutter `type` attribute — which
   piles are `pile-tools*` (the hammer source) is unknown until one breaks
   them or we read chunk blobs from the world SQLite
   (`/root/.config/VintagestoryData/Saves/polis-survival-6.vcdbs`).

## Campaign implications

- The campaign's first-metal quest = **"find a tool pile and break it"**
  (an agent-doable search + break loop) OR operator-disclosed seeding of a
  `hammer-copper` item (if the world proves barren — disclosed, like ripen).
- Harness gap found: **bodies cannot perform `OnBlockInteractStart`** in
  1.22 (IPlayer-only). Any block interaction (right-click containers,
  loose-ore pickup, GUI-less block use) needs either a harness command that
  emulates it server-side or a player context. The `activate` command
  claims to work with a bot but the engine swallows it silently for
  IPlayer-gated behaviors. This is the same wall as the berry forage fix —
  watch for it in every new "interact" flow.
- The anvil work-item temperature gate (`>20°C`) means the `anvil-smith`
  command needs the anvil to hold **molten** metal first (a crucible pour
  onto the anvil) — the current harness command takes `<anvilPos> <recipe>`
  and assumes the work item is already hot; the full loop (pour then
  smith) is not yet a single command.
