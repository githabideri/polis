# Vintage Story Block Codes Reference

> Source: wiki.vintagestory.at (v1.20.7) | Total: 12,822 blocks

This document provides block codes for placing/setting blocks via poliscli/harness.

## Quick Reference - Common Blocks

### Workstations
| Block | Code |
|-------|------|
| Anvil (Copper) | `anvil-copper` |
| Anvil (Iron) | `anvil-iron` |
| Anvil (Steel) | `anvil-steel` |
| Quern (Granite) | `quern-granite` |
| Quern (Basalt) | `quern-basalt` |
| Firepit (Cold) | `firepit-cold` |
| Firepit (Lit) | `firepit-lit` |
| Forge | `forge` |
| Barrel | `barrel` |
| Chest | `chest-north` |
| Crate | `crate` |

### Storage & Containers
| Block | Code |
|-------|------|
| Chest (North) | `chest-north` |
| Chest (East) | `chest-east` |
| Chest (South) | `chest-south` |
| Chest (West) | `chest-west` |
| Crate | `crate` |
| Barrel | `barrel` |
| Bowl (Fired) | `bowl-fired` |
| Basket Trap | `baskettrap-reed` |

### Natural Stone
| Block | Code |
|-------|------|
| Granite | `rock-granite` |
| Basalt | `rock-basalt` |
| Andesite | `rock-andesite` |
| Limestone | `rock-limestone` |
| Sandstone | `rock-sandstone` |
| Chalk | `rock-chalk` |
| Slate | `rock-slate` |
| Marble (Green) | `rock-greenmarble` |
| Marble (Red) | `rock-redmarble` |
| Obsidian | `rock-obsidian` |

### Building Materials - Stone
| Block | Code |
|-------|------|
| Cobblestone (Granite) | `cobblestone-granite` |
| Stone Brick (Granite) | `stonebrick-granite` |
| Polished Rock (Granite) | `polishedrock-granite` |
| Aged Stone Bricks (Granite) | `agedstonebricks-granite` |

### Building Materials - Wood
| Block | Code |
|-------|------|
| Oak Planks | `planks-oak` |
| Birch Planks | `planks-birch` |
| Pine Planks | `planks-pine` |
| Maple Planks | `planks-maple` |
| Oak Log (UD) | `log-placed-oak-ud` |
| Birch Log (UD) | `log-placed-birch-ud` |

### Lighting
| Block | Code |
|-------|------|
| Torch (Up) | `torch-basic-lit-up` |
| Torch (North) | `torch-basic-lit-north` |
| Lantern (Up) | `lantern-up` |
| Lantern (Down) | `lantern-down` |
| Candle | `candle` |
| Chandelier (8 candles) | `chandelier-candle8` |

### Doors & Gates
| Block | Code |
|-------|------|
| Oak Door | `door-plank-oak-north-closed-left` |
| Iron Door | `irondoor-north-closed-left` |
| Bamboo Gate | `bamboogate-green-n-closed-free` |
| Fence Gate (Oak) | `woodenfencegate-oak-n-closed` |

### Farming
| Block | Code |
|-------|------|
| Farmland (Dry) | `farmland-dry-none` |
| Farmland (Moist) | `farmland-moist-none` |
| Crop (Carrot, Stage 1) | `crop-carrot-1` |
| Crop (Onion, Stage 1) | `crop-onion-1` |
| Crop (Cabbage, Stage 1) | `crop-cabbage-1` |

### Fencing
| Block | Code |
|-------|------|
| Wooden Fence (Oak) | `woodenfence-oak-n` |
| Dry Stone Fence (Granite) | `drystonefence-granite-n` |
| Rough Hewn Fence (Oak) | `roughhewnfence-oak-n` |

### Ores (in rock)
| Block | Code |
|-------|------|
| Native Copper (Poor, Granite) | `ore-poor-nativecopper-granite` |
| Native Copper (Medium, Granite) | `ore-medium-nativecopper-granite` |
| Native Copper (Rich, Granite) | `ore-rich-nativecopper-granite` |
| Cassiterite (Tin, Rich, Granite) | `ore-rich-cassiterite-granite` |
| Limonite (Iron, Rich, Andesite) | `ore-rich-limonite-andesite` |
| Coal (Bituminous, Shale) | `ore-bituminouscoal-shale` |

### Fluids & Weather
| Block | Code |
|-------|------|
| Water (Still) | `water-still-7` |
| Water (Flowing North) | `water-n-7` |
| Lava (Still) | `lava-still-7` |
| Ice (Lake) | `lakeice` |
| Ice (Glacier) | `glacierice` |
| Snow Block | `snowblock` |

### Air & Special
| Block | Code |
|-------|------|
| Air | `air` |
| Mantle (Bedrock) | `mantle` |

---

## Block Code Patterns

### Ores
Pattern: `ore-{grade}-{mineral}-{rocktype}`
- Grades: poor, medium, rich, bountiful
- Minerals: nativecopper, cassiterite, limonite, malachite, galena, nativegold, nativesilver, etc.
- Rock types: granite, basalt, andesite, limestone, sandstone, chalk, slate, etc.

Example: `ore-rich-limonite-basalt` (rich iron ore in basalt)

### Loose Ores (surface)
Pattern: `looseores-{mineral}-{rocktype}-free`
Example: `looseores-nativecopper-granite-free`

### Directional Blocks
Many blocks have directional variants:
- Cardinal: `-north`, `-east`, `-south`, `-west` or `-n`, `-e`, `-s`, `-w`
- Vertical: `-up`, `-down`, `-ud` (up-down)
- Combined: `-ne`, `-nw`, `-se`, `-sw`

### Doors
Pattern: `door-{type}-{wood}-{facing}-{state}-{hinge}`
- Types: plank, log, 1x3gate, 2x2gate, 1x2heavy, 1x3heavy
- State: opened, closed
- Hinge: left, right

Example: `door-plank-oak-north-closed-left`

### Fences
Pattern: `{fencetype}fence-{material}-{connections}`
- Connections are cardinal letters (n, e, s, w, ne, nw, etc.)

### Stairs
Pattern: `{material}stairs-{variant}-{facing}-{half}`
- Facing: north, east, south, west
- Half: down (bottom), up (top)

### Slabs
Pattern: `{material}slab-{variant}-{position}`
- Position: down, up, free

### Crops
Pattern: `crop-{plant}-{growthstage}`
- Growth stages typically 1-9 or more depending on plant

### Logs
Pattern: `log-{state}-{wood}-{orientation}`
- State: placed, grown
- Orientation: ud (up-down), ns, we, etc.

### Roofing
Pattern: `slantedroofing-{material}-{facing}-{snowcover}`
- Materials: thatch, slate, copper, ceramic, etc.
- Complex directional patterns

---

## Rock Types Reference

| Rock Type | Code | Common Uses |
|-----------|------|-------------|
| Granite | granite | Building, tools |
| Basalt | basalt | Building, tools |
| Andesite | andesite | Building, tools |
| Limestone | limestone | Flux, building |
| Sandstone | sandstone | Building |
| Chalk | chalk | Lime, building |
| Slate | slate | Roofing |
| Marble (Green) | greenmarble | Decorative |
| Marble (Red) | redmarble | Decorative |
| Obsidian | obsidian | Tools (sharp) |
| Peridotite | peridotite | Deep rock |
| Phyllite | phyllite | Medium depth |
| Shale | shale | Coal deposits |
| Claystone | claystone | Clay deposits |
| Chert | chert | Flint tools |

---

## Ore Minerals Reference

| Ore Name | Metal | Code |
|----------|-------|------|
| Native Copper | Copper | nativecopper |
| Malachite | Copper | malachite |
| Cassiterite | Tin | cassiterite |
| Limonite | Iron | limonite |
| Magnetite | Iron | magnetite |
| Hematite | Iron | hematite |
| Galena | Lead/Silver | galena |
| Native Gold | Gold | nativegold |
| Native Silver | Silver | nativesilver |
| Bismuthinite | Bismuth | bismuthinite |
| Sphalerite | Zinc | sphalerite |

---

## Full Block List

See `vs-block-codes-raw.txt` for the complete alphabetical list of all 12,822 block codes.
