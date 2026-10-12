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

## Empirical state (1 resolved 2026-10-12; 2-3 open)

1. **`looseores-nativecopper-*`** (1 in world, at 512122,112,511981):
   **RESOLVED 2026-10-12** - right-click pickup is a dead end (no
   `looseores` itemtype in 1.22; the pickup branch is client-gated), but
   *breaking* the pile (resistance 0.15, hand) drops **1-3
   `nugget-nativecopper`** per the `dropsByType` `*` pattern. The only
   harness obstacle is the line-of-sight gate on the 0.125-tall selection
   box - `break <x> <y> <z> --skiplos` added this session (claims still
   enforced; the drops are the engine logic). Live break test pending the
   deploy.
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
  1.22 (IPlayer-only). ~~RESOLVED 2026-10-12 — see the section below: the
  chain is public API and server-callable (our `activate` already ran it;
  last night's no-op was a non-empty active hotbar slot plus the missing
  itemtype). The pickup branch is client-gated, so bots never pick up via
  right-click; the practical gaps are the harness LOS gate on thin boxes
  (`--skiplos`) and reading per-chunk attributes (`blockdata`).~~
- The anvil work-item temperature gate (`>20°C`) means the `anvil-smith`
  command needs the anvil to hold **molten** metal first (a crucible pour
  onto the anvil) — the current harness command takes `<anvilPos> <recipe>`
  and assumes the work item is already hot; the full loop (pour then
  smith) is not yet a single command.

## 2026-10-12 — right-click wall resolved; looseores re-graded

The "IPlayer-only wall" from last night was a **dispatch problem, not a
behavior rejection** — and the looseores dead-end is wrong on the break
path:

- **The interaction chain is fully server-callable.** `Block.OnBlockInteractStart
  (IWorldAccessor, IPlayer, BlockSelection)` and the `OnBlockInteractStep/Stop/Cancel`
  phases are public API; the wiki (Modding:Right_click_events, verified
  1.19.8) documents the Start→Step→Cancel→Stop phase chain. Our `activate`
  command already calls `block.OnBlockInteractStart(world, player, sel)`
  (`PolisActivateBlockAction` line 111) — with the **context player**, so a
  godmode player's right-click genuinely runs engine-side.
- **The right-click *pickup* branch is client-gated.** In
  `BlockBehaviorRightClickPickup.OnBlockInteractStart` (vssurv ildasm
  51251): the give/pickup flow (`TryGiveItemstack` / `SpawnItemEntity`) is
  behind a `world.Side == AppSide.Client` check. In a headless-bot setup
  the bot has no client, so a server-side call with the bot as byPlayer
  never picks up. A godmode player (real client, Xvnc display) *can*
  complete it — but only with an **empty active hotbar slot** (a non-empty
  slot that doesn't match the pickup stack rejects the whole interact;
  last night's silent no-op was exactly this, plus the missing itemtype —
  see below).
- **There is no `looseores` itemtype in 1.22** (checked `itemtypes/`;
  `BlockLooseOres` has no `OnPickBlock` override either), so right-click
  pickup resolves to a null stack even for a player. Right-clicking a
  loose-ore pile is a **dead end** in this build.
- **Breaking is the real path.** `blocktypes/stone/looseores.json`
  `dropsByType`: the `*` pattern drops **1–3 `nugget-{ore}`** (avg 2)
  directly; nativesilver/nativegold drop 1 nugget; quartz drops ore +
  0.2 quartz. The block has `resistance: 0.15` — hand-breakable.
  So a loose nativecopper pile yields ~2 copper nuggets per break — no
  hammer needed for the nuggets.
- **Smelting math:** `nugget.json` `combustiblePropsByType` gives
  `smeltedRatio: 20, smeltedStack: ingot-copper` — 20 nuggets per ingot.
  One pile is ~5–15% of an ingot; the bulk flow is still
  **hammer → grid → nuggets from the 60 ore blocks**.
- **Harness LOS wall (thin boxes).** The engine's `RayTraceForSelection`
  cannot hit the pile's selection box (0.125 tall, `collisionbox: null`),
  so the harness line-of-sight gate rejects adjacent bots (reproduced
  live: bot standing in the adjacent cell, break → "No line of sight").
  New: `break ... --skiplos` bypasses the harness gate only (claims still
  enforced; the break and its drops are the engine's).
- **Clutter `type` is per-chunk data** (block code is just `game:clutter`;
  no variant, no itemtype). It lives in a block entity
  (`entityBehaviors: [ShapeFromAttributes]` — `BEBehaviorShapeFromAttributes`
  in the Lib). New harness command **`blockdata <x> <y> <z>`**: returns
  the block code, the BE's serialized tree attributes (the `type` string
  should be in there), and a **dry run of the engine's break drops** (the
  BE shape behavior's `GetDrops`, else `Block.GetDrops`). Read-only.
- Deep-cave clutter cluster found at absolute (512145–147, y75–77,
  511970–73) — ~45 blocks from camp, 35+ blocks below surface: an old
  mine site, the most likely place for `pile-tools*`. First `blockdata`
  probe there is the next live step.

