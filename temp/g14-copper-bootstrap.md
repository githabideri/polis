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

## Empirical state (break path VERIFIED 2026-10-12; forage campaign open)

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
  in the Lib, which keeps `Type`/`Collected` as public fields). New
  harness command **`blockdata <x> <y> <z>`**: returns the block code, the
  clutter `type`/`collected` fields, and a dry run of the engine's
  block-level break-drop logic (`Block.GetDrops`). Read-only.
- Deep-cave clutter cluster found at absolute (512145–147, y75–77,
  511970–73) — ~45 blocks from camp, 35+ blocks below surface: an old
  mine site, the most likely place for `pile-tools*`. First `blockdata`
  probe there is the next live step.

## 2026-10-12 (session 006) — G14 empirical phase: the break path is PROVEN

Live, with the campaign bot 156138, after the bdade6c deploy + full-stack
restart:

- **`blockdata` works on live per-chunk data** (first probe: mine-site
  toolrack → `type: toolrack-empty, collected: False`).
- **All 73 clutters in the r64 census are live-mapped** (mine complex +
  its annexes: toolracks, tables, beds, shelves, barrels, fences, chains,
  skeletons, rubble, pottery, weapons, cloth, bones). **No `pile-tools*`
  and no `tool-*` live anywhere in r64 of camp or the mine.**
- **World-DB archaeology (stale snapshot, still informative):** the
  `chunk` table is VS 1.22's protobuf format; BE entries carry world
  `posx/posy/posz` as plain int32s, and the `gamedata` registry gives
  numeric block IDs (`looseores-nativecopper-claystone-free` = 8561).
  Int32 scans found **5 `pile-tools` clutters and 38 nativecopper
  looseores piles** in the snapshot — but every pile-tools position is
  **rock live** (version-migration staleness; the live r64 rescans
  confirm zero clutters in those zones). Treat the pile-tools source as
  **dead in this world as it exists now**; the looseores count is the
  usable signal.
- **LOSEORES BREAK E2E (the core unknown) — VERIFIED:**
  1. `break 512122 112 511981 --skiplos` (bot in the adjacent cell) →
     pile block removed ("No block at target position" after).
  2. Engine spawned **3 × `game:nugget-nativecopper` item entities**
     (1 each) around the break site — the `dropsByType *` 1–3 range, as
     the asset says.
  3. `pickup` ×3 → all three collected, **stacked to 3 in the bot's
     slot 0** (nuggets stack; inventory shows `qty: 3`).
  The bot (Oikistes body) now carries 3 nuggets. No operator seeding
  anywhere in this chain: the break, the drops, and the pickup are all
  engine behavior; `--skiplos` only skipped the harness's own ray gate
  (thin 0.125 selection box), which is the disclosed reachability bypass.
- **Live looseores census (r64 from the mine-side approach point):**
  4 nativecopper piles — (512122,112,511981) [now broken], (512063,110,
  512074), (512064,110,512075), (512063,111,512076) [a 3-pile cluster,
  ~60 blocks west of the broken one] — plus 4 quartz piles at
  (512122–27, 116–117, 512018–39). 20 nuggets per ingot ⇒ an ingot needs
  roughly 7–20 more pile breaks; at ~38 piles world-wide (DB estimate) the
  total yield is ~3–6 ingots: enough for the anvil + hammer + spare
  ingots if the campaign forages systematically.
- **Navigation is the practical bottleneck, not the mechanics.** The
  wet basin between the camp side and the ore/pile side (muddygravel
  y106–109 under a ~2-block rim) repeatedly defeated the traverser
  ("stuck after 3 repaths" / "all navigation modes timed out") on
  long legs, but succeeded on short hops: (512083,113,512016) →
  (512115,112,511985) ["one step short"] → (512120,113,511985) →
  (512123,112,511985) [done]. The hillside traverser non-determinism
  (G14 residual (a)) is now the campaign-critical defect: a multi-hop
  planner (or a basin-rim-aware path) is needed before the forage
  campaign can run unsupervised.
- **Next:** forage the 3-pile cluster (≈6 nuggets more) and keep going
  until the bot holds 20 nuggets; then the mapped crucible → ingot →
  anvil → hammer chain runs on existing harness commands. The quartz
  piles are a future glass/ampoule side-line, not part of G14.

