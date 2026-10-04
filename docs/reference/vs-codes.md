# Vintage Story Block and Item Codes Reference

This document lists commonly used block and item codes for the polis project. These codes are compatible with harness commands (`give`, `place`, `setblock`, `mine`, etc.) and `sapi.World.GetBlock()` / `sapi.World.GetItem()`.

**Format:** All codes use the `game:` domain prefix (e.g., `game:rock-granite`).

## Table of Contents

- [Rock/Stone Blocks](#rockstone-blocks-placeable)
- [Ore Blocks](#ore-blocks-placeable-minable)
- [Terrain Blocks](#terrain-blocks)
- [Building Materials](#building-materials)
- [Storage/Furniture](#storagefurniture)
- [Tools](#tools)
- [Weapons](#weapons)
- [Resources/Materials](#resourcesmaterials)
- [Food/Plants](#foodplants)
- [Animals](#animals)
- [Naming Conventions](#naming-conventions)

---

## Rock/Stone Blocks (Placeable)

**Pattern:** `game:rock-{type}`

| Code | Description |
|------|-------------|
| `game:rock-granite` | Granite rock block |
| `game:rock-andesite` | Andesite rock block |
| `game:rock-basalt` | Basalt rock block |
| `game:rock-chalk` | Chalk rock block |
| `game:rock-bauxite` | Bauxite rock block |
| `game:rock-shale` | Shale rock block |
| `game:rock-sandstone` | Sandstone rock block |
| `game:rock-limestone` | Limestone rock block |
| `game:rock-slate` | Slate rock block |
| `game:rock-conglomerate` | Conglomerate rock block |
| `game:rock-claystone` | Claystone rock block |
| `game:rock-marble` | Marble rock block |
| `game:rock-phyllite` | Phyllite rock block |
| `game:rock-peridotite` | Peridotite rock block |
| `game:rock-kimberlite` | Kimberlite rock block |

**Note:** Mining rock blocks drops stone items (e.g., mining `game:rock-granite` drops `game:stone-granite`).

---

## Ore Blocks (Placeable, Minable)

**Pattern:** `game:ore-{grade}-{mineral}-{host rock}`

### Grade Prefixes
- `poor` - Low ore content
- `medium` - Medium ore content (often just the mineral name without grade)
- `rich` - High ore content
- `bountiful` - Very high ore content

### Iron Ores (Tier 3 pickaxe required)
| Code Pattern | Mineral | Drops |
|--------------|---------|-------|
| `game:ore-poor-limonite-{rock}` | Limonite | Iron ore |
| `game:ore-medium-limonite-{rock}` | Limonite | Iron ore |
| `game:ore-rich-limonite-{rock}` | Limonite | Iron ore |
| `game:ore-*-magnetite-{rock}` | Magnetite | Iron ore |
| `game:ore-*-hematite-{rock}` | Hematite | Iron ore |

### Copper Ores (Tier 2 pickaxe)
| Code Pattern | Mineral | Drops |
|--------------|---------|-------|
| `game:ore-*-malachite-{rock}` | Malachite | Copper ore |
| `game:ore-*-nativecopper-{rock}` | Native Copper | Copper nuggets |
| `game:ore-rich-nativecopper-andesite` | Native Copper in Andesite | Copper nuggets |

### Other Metal Ores
| Code Pattern | Mineral | Drops |
|--------------|---------|-------|
| `game:ore-*-cassiterite-{rock}` | Cassiterite | Tin ore |
| `game:ore-*-nativegold-{rock}` | Native Gold | Gold nuggets |
| `game:ore-*-nativesilver-{rock}` | Native Silver | Silver nuggets |
| `game:ore-*-galena-{rock}` | Galena | Lead/Silver ore |
| `game:ore-*-sphalerite-{rock}` | Sphalerite | Zinc ore |
| `game:ore-*-bismuthinite-{rock}` | Bismuthinite | Bismuth ore |

### Fuel Ores (Tier 2 pickaxe)
| Code | Description |
|------|-------------|
| `game:ore-lignite-chalk` | Lignite (brown coal) in chalk |
| `game:ore-bituminouscoal-{rock}` | Bituminous coal |
| `game:ore-anthracite-{rock}` | Anthracite (hard coal) |

**Example:** `game:ore-poor-limonite-shale` = Poor quality limonite iron ore in shale rock

---

## Terrain Blocks

### Soil
**Pattern:** `game:soil-{fertility}-{grass coverage}`

| Code | Description |
|------|-------------|
| `game:soil-medium-normal` | Medium fertility soil with normal grass |
| `game:soil-medium-verysparse` | Medium fertility soil with very sparse grass |
| `game:soil-medium-none` | Medium fertility soil with no grass |
| `game:soil-high-normal` | High fertility soil |
| `game:soil-low-sparse` | Low fertility sparse grass |

### Other Terrain
| Code | Description |
|------|-------------|
| `game:gravel-{type}` | Gravel (andesite, granite, etc.) |
| `game:sand-{color}` | Sand (yellow, brown, etc.) |
| `game:clay-{color}` | Clay blocks |
| `game:peat-*` | Peat blocks |

---

## Building Materials

### Wood/Logs
**Pattern:** `game:log-{type}-{orientation}`

| Code | Description |
|------|-------------|
| `game:log-placed-oak-ud` | Placed oak log (up-down orientation) |
| `game:log-placed-pine-ud` | Placed pine log |
| `game:log-placed-birch-ud` | Placed birch log |
| `game:log-placed-maple-ud` | Placed maple log |
| `game:log-resin-pine-ud` | Resin-bearing pine log (harvestable) |

### Planks
**Pattern:** `game:planks-{wood type}`

| Code | Description |
|------|-------------|
| `game:planks-oak` | Oak planks |
| `game:planks-pine` | Pine planks |
| `game:planks-birch` | Birch planks |
| `game:planks-maple` | Maple planks |

### Doors and Gates
**Pattern:** `game:door-{style}-{wood}` or `game:wattlegate-{type}-{orientation}`

| Code | Description |
|------|-------------|
| `game:door-solid-oak` | Solid oak door |
| `game:door-windowed-oak` | Windowed oak door |
| `game:wattlegate-sticks-n-closed-left-free` | Wattle gate (sticks, north-facing, closed) |

### Fences
**Pattern:** `game:fence-{wood}`

| Code | Description |
|------|-------------|
| `game:fence-oak` | Oak fence |
| `game:fence-pine` | Pine fence |

---

## Storage/Furniture

### Containers
| Code | Description |
|------|-------------|
| `game:chest-east` | Chest (facing east) |
| `game:chest-north` | Chest (facing north) |
| `game:barrel` | Barrel (sealed container for liquids) |
| `game:storagevessel-red-fired` | Storage vessel (fired clay) |
| `game:crate-{wood}` | Wooden crate |
| `game:trunk-{wood}` | Wooden trunk |

### Furniture
| Code | Description |
|------|-------------|
| `game:chair-plain` | Plain wooden chair |
| `game:lantern-south` | Hanging lantern (south-facing) |
| `game:groundstorage` | Ground storage (items placed on ground) |

### Workstations
| Code | Description |
|------|-------------|
| `game:quern-granite` | Granite quern (grinding mill) |
| `game:anvil-steel` | Steel anvil |
| `game:anvil-iron` | Iron anvil |
| `game:forge` | Forge/furnace |

---

## Tools

### Pickaxes
**Pattern:** `game:pickaxe-{material}`

| Code | Tool Tier | Durability |
|------|-----------|------------|
| `game:pickaxe-copper` | 2 | 300 |
| `game:pickaxe-gold` | 2 | 150 |
| `game:pickaxe-silver` | 2 | 175 |
| `game:pickaxe-tinbronze` | 3 | 450 |
| `game:pickaxe-bismuthbronze` | 3 | 500 |
| `game:pickaxe-blackbronze` | 3 | 550 |
| `game:pickaxe-iron` | 4 | 1000 |
| `game:pickaxe-meteoriciron` | 4 | 1300 |
| `game:pickaxe-steel` | 5 | 2500 |

### Axes
**Pattern:** `game:axe-{material}`

| Code | Description |
|------|-------------|
| `game:axe-copper` | Copper axe |
| `game:axe-tinbronze` | Tin bronze axe |
| `game:axe-iron` | Iron axe |
| `game:axe-steel` | Steel axe |

### Knives
**Pattern:** `game:knife-{type}-{material}`

**Important:** Knife codes require a type identifier. Common types: `generic`, `dagger`, `stiletto`, `khanjar`, `baselard`

| Code | Description |
|------|-------------|
| `game:knife-generic-copper` | Copper knife (generic) |
| `game:knife-generic-tinbronze` | Tin bronze knife |
| `game:knife-generic-iron` | Iron knife |
| `game:knife-generic-steel` | Steel knife |
| `game:knife-dagger-copper` | Copper dagger |
| `game:knife-stiletto-iron` | Iron stiletto |

### Other Tools
| Code | Description |
|------|-------------|
| `game:shovel-{material}` | Shovel |
| `game:hoe-{material}` | Hoe (farming) |
| `game:hammer-{material}` | Hammer |
| `game:saw-{material}` | Saw (woodworking) |
| `game:chisel-{material}` | Chisel (stonecutting) |

---

## Weapons

| Code | Description |
|------|-------------|
| `game:blade-blackguard-iron` | Iron blackguard blade |
| `game:sword-{material}` | Sword |
| `game:spear-{material}` | Spear |
| `game:bow-simple` | Simple bow |
| `game:arrow-flint` | Flint arrows |

---

## Resources/Materials

### Stone Items (from mining)
**Pattern:** `game:stone-{type}`

| Code | Description |
|------|-------------|
| `game:stone-granite` | Granite stone (item) |
| `game:stone-andesite` | Andesite stone |
| `game:stone-basalt` | Basalt stone |
| `game:stone-chalk` | Chalk stone |
| `game:stone-bauxite` | Bauxite stone |

### Basic Resources
| Code | Description |
|------|-------------|
| `game:flint` | Flint |
| `game:stick` | Wooden stick |
| `game:firewood` | Firewood |
| `game:drygrass` | Dry grass |
| `game:bone` | Bone |
| `game:resin` | Pine resin |
| `game:peat` | Peat (fuel) |

### Ore Items (from mining ore blocks)
| Code | Description |
|------|-------------|
| `game:ore-lignite` | Lignite ore |
| `game:ore-limonite` | Limonite iron ore |
| `game:nugget-nativecopper` | Native copper nuggets |
| `game:nugget-nativegold` | Gold nuggets |

---

## Food/Plants

> **1.22 food model (verified 2026-10-04):** foods are *variant-based* — the
> registered code is `base-variant` (e.g. `game:fruit-blueberry`,
> `game:bushmeat-raw`) and the per-variant nutrition table lives in
> `nutritionPropsByType` (satiety, health, foodcategory, plus new-in-1.22
> intoxication/psychedelic fields). The domain is `game:` even for assets
> stored under the survival mod's asset dir. There is no plain `game:berry`
> anymore.

### Berry Bushes (Harvestable)

**1.22 pattern:** `game:fruitingbush-{state}-{type}` (the 1.21
`{size}berrybush-{type}-{state}` codes are gone)

- `state`: `wild` (affects the forage stat, `forageStatAffectedByType`),
  `grown` (planted)
- `type`: `beautyberry`, `blueberry`, `cloudberry`, `cranberry`, `blackberry`,
  `blackcurrant`, `raspberry`, `redcurrant`, `whitecurrant`, `strawberry`

| Code | Description |
|------|-------------|
| `game:fruitingbush-grown-blueberry` | Grown blueberry bush |
| `game:fruitingbush-wild-cranberry` | Wild cranberry bush |

Harvest with `harvest`; the drop is the matching `game:fruit-{type}` item.

### Fruit (Harvested)

**Pattern:** `game:fruit-{type}` (bush fruits + tree fruits)

| Code | Satiety | Notes |
|------|---------|-------|
| `game:fruit-blueberry` | 80 (default) | no spoil |
| `game:fruit-cranberry` | 60 | spoils to rot (~12h) |
| `game:fruit-cherry` | 40 | |
| `game:fruit-lychee` | 40 | spoils (360h) |
| `game:fruit-saguaro` | 60 | +1 health |
| `game:fruit-breadfruit` | 200 | |

All are `foodcategory: Fruit`. (Table: survival mod
`itemtypes/food/fruit.json` → `nutritionPropsByType`; `"*"` = 80 default.)

### Crops
**Pattern:** `game:crop-{type}-{stage}`

Stages: 1-9 (varies by crop), higher = more mature

| Code | Description |
|------|-------------|
| `game:crop-flax-9` | Mature flax crop |
| `game:crop-wheat-9` | Mature wheat |
| `game:crop-spelt-9` | Mature spelt |

### Meat/Animal Products
**Pattern:** `game:{meat}-{state}` (raw / cooked / cured)

| Code | Description |
|------|-------------|
| `game:redmeat-raw` | Raw red meat (sheep, pig) |
| `game:bushmeat-raw` | Raw bushmeat (small game) — confirmed live |
| `game:poultry-raw` | Raw poultry (chicken) |
| `game:feather` | Feather |
| `game:fat` | Animal fat |
| `game:hide-*` | Animal hide |

### Other Foods (variant-based, `game:` domain)

| Code pattern | Notes |
|--------------|-------|
| `game:vegetable-{type}` | e.g. `game:vegetable-bambooshoot` (satiety 100, category NoNutrition — a trap: "vegetable" base has no nutrition) |
| `game:dough-{type}`, `game:grain-{type}`, `game:fishraw-*`, `game:fishchunk-*`, `game:fishfillet-*`, `game:egg-*`, `game:cheese-*`, `game:butter`, `game:pemmican`, `game:insect-*`, `game:spice-*`, `game:legume-*`, `game:pickledlegume-*`, `game:pickledvegetable-*`, `game:rawcassava-*`, `game:rawcheese-*`, `game:ontree-*` | one JSON per family under `itemtypes/food/`, each with its own per-variant `nutritionPropsByType` |
| `game:liquid-alcohol` / `-vinegarportion` / `-spirit` | drinks — intoxication values live here (see below) |

**Intoxication (new in 1.22):** top-level tree floats `intoxication` (≤ 1.1)
and `psychedelic` (≤ 2.0) on the entity's `WatchedAttributes`; the drinking
path maintains them. `detox`-style effects = lowering those floats.

**Satiety mechanics:** entities declare the `hunger` behavior to carry the
synced `hunger` tree (0-1500 saturation + 5 nutrition levels); bots do —
see `polisbot.json` and `docs/design/food-hunger-skills-policies.md`.
`harness: hunger` reads it, `harness: eat` applies it.

---

## Animals

**Pattern:** `game:{animal}-{variant}-{age}-{gender}` (varies by animal)

### Common Animals
| Code | Description |
|------|-------------|
| `game:chicken-hen` | Female chicken |
| `game:chicken-rooster` | Male chicken |
| `game:pig-wild-male` | Wild pig (male) |
| `game:pig-wild-female` | Wild pig (female) |
| `game:sheep-bighorn-male` | Bighorn sheep (male) |
| `game:sheep-bighorn-female` | Bighorn sheep (female) |
| `game:sheep-bighorn-adult-male` | Adult bighorn sheep (male) |
| `game:hare-male` | Hare (male) |
| `game:hare-female` | Hare (female) |
| `game:wolf-male` | Wolf (male) |

### Dead Animals (Blocks)
| Code | Description |
|------|-------------|
| `game:carcass-medium` | Medium carcass block (from butchered large animals) |

**Note:** After butchering, animal corpses become carcass blocks. Use `mine` to break them for bones.

---

## Naming Conventions

### Block Code Patterns

| Pattern | Example | Description |
|---------|---------|-------------|
| `{type}-{material}` | `rock-granite` | Basic block |
| `{type}-{orientation}` | `chest-east` | Directional block |
| `ore-{grade}-{mineral}-{host}` | `ore-poor-limonite-shale` | Ore with grade and host rock |
| `{block}-{variant}-{state}` | `berrybush-blueberry-ripe` | Blocks with states |
| `log-{modifier}-{wood}-{orientation}` | `log-placed-oak-ud` | Logs with modifiers |

### Item Code Patterns

| Pattern | Example | Description |
|---------|---------|-------------|
| `{tool}-{material}` | `pickaxe-copper` | Basic tools |
| `knife-{type}-{material}` | `knife-generic-copper` | Knives (require type) |
| `stone-{rock type}` | `stone-granite` | Stone items |
| `fruit-{type}` | `fruit-blueberry` | Harvested fruits |

### Tool Tier Requirements

| Tier | Materials | Can Mine |
|------|-----------|----------|
| 0-1 | Stone, Flint | Soil, soft blocks |
| 2 | Copper, Gold, Silver | Rock, low-tier ores |
| 3 | Tin/Bismuth/Black Bronze | Iron ores (limonite, etc.) |
| 4 | Iron, Meteoric Iron | Higher-tier ores |
| 5 | Steel | All blocks |

### Ore Mineral to Metal Mapping

| Player Term | Actual Mineral Names |
|-------------|----------------------|
| Iron ore | `limonite`, `magnetite`, `hematite` |
| Copper ore | `malachite`, `nativecopper` |
| Tin ore | `cassiterite` |
| Gold ore | `nativegold` |
| Silver ore | `nativesilver`, `galena` |
| Zinc ore | `sphalerite` |
| Bismuth ore | `bismuthinite` |

**Tip:** When searching for ores, search for the mineral name (e.g., `-s limonite`) rather than "iron ore".

---

## Usage Examples

```bash
# Give items to bot
./scripts/poliscli.py give game:pickaxe-copper
./scripts/poliscli.py give game:stone-granite 10
./scripts/poliscli.py give game:knife-generic-copper

# Search for blocks
./scripts/poliscli.py targets -s ore --radius 32
./scripts/poliscli.py targets -s chest --radius 16
./scripts/poliscli.py targets -s limonite --radius 32  # Find iron ore

# Mine/Harvest
./scripts/poliscli.py mine 100 65 200  # Mine block at coords
./scripts/poliscli.py harvest 100 65 200  # Harvest berry bush

# Spawn entities
./scripts/poliscli.py spawnkill game:sheep-bighorn-adult-male

# Food & satiety
./scripts/poliscli.py hunger                # read saturation/levels/health (all bots + player)
./scripts/poliscli.py eat game:fruit-blueberry 3   # engine satiety path (verified: 3x80)
```

---

*Document generated from project documentation and testing artifacts. For the most up-to-date codes, check the VS wiki or use in-game commands.*
