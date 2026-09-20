---
title: VS NPC Action Primitives - Harvesting, Mining, Butchering, Loot Collection
date: 2026-01-15
tags:
  - vintage-story
  - modding
  - npc
  - ai
  - harvesting
  - mining
  - butchering
status: draft
type: implementation-guide
author: gpt-5.1-thinking
---

# Scope
This document defines *concrete, implementable* action primitives for an NPC system targeting Vintage Story (VS), with emphasis on:

- Harvesting *harvestable blocks* (berry bushes, resin logs, etc.) via interaction-driven mechanics.
- Harvesting *farmland crops* via maturity checks and controlled collection.
- Mining via a server-side “simulate mining progress” loop that adheres to tool/tier rules and block resistance, then performs the final break.
- Butchering via the vanilla `harvestable` entity behavior (corpse harvest inventory), not ad-hoc ground drops.
- Collecting dropped items near the NPC (with minimal race-condition safeguards).

**Explicitly out of scope for now**:
- “Quadrant” mining mechanics (treated as mod-specific; not implemented).
- Workstation processing (anvil/quern/etc.).

# Repos available
Agent assumes these repos exist locally (cloned):

- `vsapi/`
- `vssurvivalmod/`
- `vsessentialsmod/`
- `vsvillage/`

Use repo-relative references below.

# Key API facts (why the chosen approach)
## `BreakBlock` is the *finalization* step, not mining logic
- `IBlockAccessor.BreakBlock(BlockPos pos, IPlayer byPlayer, float dropQuantityMultiplier = 1f)` removes a block, calls drop/break callbacks, triggers neighbor updates, and spawns returned drops into the world. It does **not** model mining time.

**Implication**: For NPC mining that “feels like vanilla,” implement a server-side progress loop using block resistance + tool mining speed, and only call `BreakBlock` at completion.

## `DamageBlock` is for visuals / client decals
- `IBlockAccessor.DamageBlock(...)` is primarily to broadcast block-damage decal state to clients. It is not a complete server-side mining state machine.

**Implication**: Use `DamageBlock` optionally to show visuals while the NPC mines; do not depend on it for timing or authoritative progress.

## Prefer interaction path for `Harvestable` blocks
Many gatherables (berry bushes, resin logs, cactus, etc.) are implemented via the `Harvestable` block behavior:
- Right-click harvest swaps the block to a harvested variant (`harvestedBlockCode`) and optionally uses other behaviors (e.g., `Transient`) for timed replacement/regrowth.

**Implication**: For NPCs, simulate the *same interaction path* as a player rather than `BreakBlock` for these blocks.

## Butchering is inventory-driven via entity behavior
Vanilla butchering uses the `harvestable` entity behavior:
- Knife interaction sets entity to harvested state and populates the corpse’s harvest inventory (`"harvestableInv"` attribute).

**Implication**: For NPC butchering, trigger the behavior path to fill the harvest inventory, then transfer stacks to NPC inventory—no need to spawn `EntityItem` drops for determinism.

# Action primitive contracts
Each primitive should be implemented as an NPC “action” with:

- Preconditions (range, tool present, access rights)
- Execution (movement + interaction/mining)
- Postconditions (inventory updated, block/entity state updated)
- Failure modes (blocked by claim/tier/no tool/invalid target)

The action layer should remain deterministic where possible by:
- Avoiding reliance on timing-sensitive entity-drop scanning when direct transfer is feasible.
- Using short “settle delay” when burst drops are expected (tree felling).

---

# Primitive A: Harvest harvestable blocks (berries/resin/etc.)
## Goal
Harvest blocks implemented with the `Harvestable` behavior by simulating player-like interaction.

## Why
Using `BreakBlock` can bypass intended mechanics (harvest variants/regrowth) and can make yields inconsistent.

## Target identification
A block is “harvestable via interaction” if it contains the `Harvestable` block behavior (JSON behavior).

### Implementation plan
1. **Locate the target block** at `BlockPos pos` via `IWorldAccessor.BlockAccessor.GetBlock(pos)`.
2. **Detect Harvestable behavior** on the block (behavior list). If absent, this primitive is not applicable.
3. **Perform interaction** using the same method path as a player right-click:
   - Create/obtain an `IPlayer` context representing the NPC actor (must be non-null).
   - Call the block’s interaction entrypoint (typical path is `OnBlockInteractStart/Step/Stop` depending on VS internals).
4. **Optional**: After harvest, chain `collectNearbyDrops(radius)` if the harvest spawns ground items (some harvestables do).

### Notes
- Many harvestables swap block codes rather than breaking; ensure the action considers the final block state.
- Claims: access checks are often done via `world.Claims.TryAccess(byPlayer, pos, EnumBlockAccessFlags.Use)`; if the NPC acts “as a player,” it may be blocked in protected areas.

### Code references
- Block behavior documentation for `Harvestable` (conceptual, non-code):
  - VS wiki: `Harvestable` behavior (right-click harvest, `harvestedBlockCode`).

(Agent: locate actual block behavior implementation within game assemblies is not in repos here; treat behavior presence on block as the detection trigger and call standard block interaction methods.)

---

# Primitive B: Harvest farmland crops (maturity check → harvest)
## Goal
Harvest crops on farmland only when mature.

## Why
Farmland crops use growth stages; maturity is not guaranteed by “block placed in ripe state.” This primitive avoids harvesting too early and keeps results consistent.

## Maturity model
Crops have growth stages; different crops have different stage counts.

### Implementation plan
1. Identify the farmland/crop block entity at or around the target position:
   - Either the farmland BE contains crop state, or the crop block encodes it.
2. Use crop growth APIs to check maturity.
   - VS API exposes a `CropBehavior.TryGrowCrop(...)` hook; farmland likely invokes crop behavior internally.
3. If mature:
   - Prefer player-like harvesting (if the crop supports a harvest interaction).
   - Otherwise do a controlled break:
     - Call `BreakBlock(pos, byPlayer, dropMult)`.
4. Immediately or shortly after, collect drops:
   - For single-block harvests, a near-immediate scan is fine.
   - For multi-block cascades (rare for crops), wait 1–2 ticks before scanning.

### Code references
- `vsapi/`:
  - Search for `CropBehavior.TryGrowCrop(` to find the method signature and usage patterns.
- `vsvillage/`:
  - Search for villager crop tasks (e.g., cultivate/harvest logic) and how they select farmland POIs.
- `vssurvivalmod/`:
  - Search for farmland block entity and crop stage storage (often in BE farmland code).

---

# Primitive C: Mine block (simulate mining → finalize break)
## Goal
NPC mines like a player: respects tool tier and mining time.

## Why
`BreakBlock` finalizes instantly; vanilla mining time is derived from block resistance and tool mining speed.

## Inputs
- `BlockPos pos`
- Required tool type (pickaxe/shovel/axe) inferred from block material/tool classes.

## Data needed
- Block resistance (seconds) and required mining tier.
- Tool mining speed vs block material, and tool tier.

### Implementation plan
1. **Validate target**:
   - `block = world.BlockAccessor.GetBlock(pos)`
   - Determine `requiredTier` from block data.
2. **Validate tool**:
   - Ensure NPC has an appropriate tool equipped.
   - Determine `toolTier` and `miningSpeed` for the block material.
   - If `toolTier < requiredTier` → fail.
3. **Compute break time**:
   - `tBreak = block.Resistance / miningSpeed` (miningSpeed must be > 0).
4. **Run a progress loop**:
   - Accumulate progress each server tick (`dt`).
   - Optionally call `BlockAccessor.DamageBlock(...)` periodically to show damage decals.
5. **Finalize**:
   - Call `BlockAccessor.BreakBlock(pos, byPlayer, dropMult)`.
6. **Collect**:
   - Chain `collectNearbyDrops(radius)`.

### Optional: visuals
- Use `DamageBlock` with appropriate `BlockFacing`, damage amount, and the actor player.

### Code references
- `vsapi/`:
  - `IBlockAccessor.BreakBlock(...)`
  - `IBlockAccessor.DamageBlock(...)`
- `vssurvivalmod/`:
  - Tool items (pickaxe/axe/shovel) for patterns of tier/speed stats.

---

# Primitive D: Butcher entity (knife harvest → transfer harvest inventory)
## Goal
Perform vanilla-style butchering and collect outputs into NPC inventory.

## Why
Vanilla behavior already defines yield logic (weight, death cause modifiers, tool tiers) and stores results in corpse inventory.

## Implementation plan
1. **Preconditions**:
   - Entity is dead and has `harvestable` behavior.
   - NPC has a knife equipped.
2. **Trigger harvest**:
   - Invoke the same code path as shift+right-click knife harvesting.
   - This should transition entity to harvested state and populate `harvestableInv`.
3. **Transfer inventory**:
   - Read the corpse harvest inventory attribute (`"harvestableInv"`) and convert to an `InventoryBase`.
   - Move stacks into NPC inventory using standard give/merge logic.
4. **Cleanup**:
   - Optionally mark corpse as “looted” or empty to avoid re-harvesting.

## Code references
- `vsessentialsmod/Entity/Behavior/BehaviorHarvestable.cs`
  - Starting point: find how the behavior:
    - Detects knife interaction
    - Sets harvested state
    - Calculates drops
    - Writes inventory to `"harvestableInv"`
- `vssurvivalmod/`:
  - Knife item implementation (search `ItemKnife`)

---

# Primitive E: Collect nearby drops (EntityItem scan)
## Goal
Collect dropped item entities around the NPC into its inventory.

## Why
Many actions (mining, breaking) spawn `EntityItem` drops. This primitive consolidates pickup.

## Timing note
For most single-block events, scanning immediately works.
For burst-drop events (tree felling, large cascades), *wait 1–2 ticks* or collect until stable (no new EntityItem for N ticks) to avoid missing late spawns.

## Implementation plan
1. Scan entities in radius:
   - `world.GetEntitiesAround(npcPos, radius, radius, filter => filter is EntityItem)`
2. For each `EntityItem`:
   - Attempt to insert its `ItemStack` into NPC inventory.
   - If fully inserted: despawn/remove entity item.
   - If partially inserted: update remaining stack on the entity.
3. Concurrency:
   - Add a simple reservation mechanism to avoid two NPCs collecting the same item simultaneously (e.g., mark entity ID in a short-lived “claimed by NPC” map).

## Code references
- `vsapi/`:
  - Entity querying utilities (`GetEntitiesAround`) and `EntityItem` types.
- `vsvillage/`:
  - Patterns for villagers collecting after tasks (search for item collection logic).

---

# Actor context: `IPlayer` / permissions / drop context
Many core methods expect an `IPlayer` context (`byPlayer`) for:
- claim access checks (`TryAccess`)
- drop context (tool stats, traits)

**Avoid passing null**: some drop logic and modded blocks can fail when `byPlayer` is null.

## Recommendation
Implement a lightweight “NPC player context”:
- If you can map each NPC to a real `IServerPlayer`, do so.
- Otherwise implement a minimal `IPlayer` wrapper that provides:
  - inventory/active slot (so tool context exists)
  - player UID/name
  - world reference

---

# Suggested implementation order
1. `collectNearbyDrops(radius)` (utility)
2. `mineBlock(pos)` (progress loop + break + collect)
3. `butcherEntity(entity)` (BehaviorHarvestable + transfer)
4. `harvestHarvestableBlock(pos)` (interaction)
5. `harvestFarmlandCrop(pos)` (maturity check + harvest)

---

# Quick search checklist for the agent (repo-relative)
Use ripgrep to locate exact code and patterns.

## Butchering
- `vsessentialsmod/Entity/Behavior/BehaviorHarvestable.cs`
- `vssurvivalmod/**/ItemKnife*.cs` (knife interaction)

## Mining stats patterns
- `vssurvivalmod/**/ItemPickaxe*.cs` / `ItemAxe*.cs` / `ItemShovel*.cs`
- Search for `MiningSpeed`, `ToolTier`, `RequiredMiningTier`, `Resistance` usage.

## Crops / farmland
- `vsapi/**/CropBehavior*.cs` and search for `TryGrowCrop`
- `vssurvivalmod/**/BEFarmland*.cs` (or similar) and search for growth stage storage.
- `vsvillage/**` search for villager farming tasks and POI selection.

---

# Minimal failure modes to implement
- Target block/entity no longer exists (chunk unloaded / changed).
- Claim denied (no Use/Build permission).
- Tool missing or wrong tier.
- Inventory full (handle partial pickup).
- Harvest already done (corpse empty / block already harvested).

---

# Determinism/testing notes
For automated tests:
- Prefer direct inventory transfer where possible (butchering, small harvestables).
- For actions that inherently spawn many drops (tree felling), use a short settle delay then scan.
- Reset test areas via schematics / worldedit rather than relying on natural regrowth.

