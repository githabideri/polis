# Vintage Story Item Codes Reference

> Source: wiki.vintagestory.at (v1.20.10) | Total: 3,713 items

This document provides item codes for giving items to bots via poliscli/harness.

## Quick Reference - Common Items

### Tools (Metal)
| Item | Code |
|------|------|
| Copper Pickaxe | `pickaxe-copper` |
| Iron Pickaxe | `pickaxe-iron` |
| Steel Pickaxe | `pickaxe-steel` |
| Copper Axe | `axe-felling-copper` |
| Iron Axe | `axe-felling-iron` |
| Steel Axe | `axe-felling-steel` |
| Copper Shovel | `shovel-copper` |
| Iron Shovel | `shovel-iron` |
| Copper Knife | `knife-copper` |
| Iron Knife | `knife-iron` |
| Copper Hoe | `hoe-copper` |
| Iron Hoe | `hoe-iron` |
| Saw | `saw-iron` |
| Hammer | `hammer-copper` |
| Chisel | `chisel-copper` |

### Tools (Stone/Primitive)
| Item | Code |
|------|------|
| Flint Axe | `axe-flint` |
| Granite Axe | `axe-granite` |
| Obsidian Axe | `axe-obsidian` |
| Flint Knife | `knife-flint` |
| Stone Shovel | `shovel-stone` |
| Wooden Club | `club-plain` |

### Weapons
| Item | Code |
|------|------|
| Copper Spear | `spear-copper` |
| Iron Spear | `spear-iron` |
| Copper Sword Blade | `blade-falx-copper` |
| Iron Sword Blade | `blade-falx-iron` |
| Bow | `bow-simple` |
| Copper Arrow | `arrow-copper` |
| Iron Arrow | `arrow-iron` |
| Sling | `sling` |

### Metal Ingots
| Item | Code |
|------|------|
| Copper Ingot | `ingot-copper` |
| Tin Ingot | `ingot-tin` |
| Bronze Ingot | `ingot-tinbronze` |
| Iron Ingot | `ingot-iron` |
| Steel Ingot | `ingot-steel` |
| Gold Ingot | `ingot-gold` |
| Silver Ingot | `ingot-silver` |
| Lead Ingot | `ingot-lead` |

### Metal Bits (small amounts)
| Item | Code |
|------|------|
| Copper Bits | `metalbit-copper` |
| Iron Bits | `metalbit-iron` |
| Gold Bits | `metalbit-gold` |
| Silver Bits | `metalbit-silver` |

### Wood & Building Materials
| Item | Code |
|------|------|
| Oak Plank | `plank-oak` |
| Birch Plank | `plank-birch` |
| Pine Plank | `plank-pine` |
| Maple Plank | `plank-maple` |
| Firewood | `firewood` |
| Stick | `stick` |
| Stone Brick | `stonebrick-granite` |

### Food - Grains
| Item | Code |
|------|------|
| Spelt Grain | `grain-spelt` |
| Rye Grain | `grain-rye` |
| Rice Grain | `grain-rice` |
| Flax Seeds | `seeds-flax` |
| Spelt Flour | `flour-spelt` |
| Spelt Dough | `dough-spelt` |
| Perfect Spelt Bread | `bread-spelt-perfect` |

### Food - Vegetables
| Item | Code |
|------|------|
| Carrot | `vegetable-carrot` |
| Onion | `vegetable-onion` |
| Cabbage | `vegetable-cabbage` |
| Turnip | `vegetable-turnip` |
| Pumpkin | `vegetable-pumpkin` |
| Parsnip | `vegetable-parsnip` |

### Food - Fruits
| Item | Code |
|------|------|
| Apple | `fruit-saguaro` |
| Blueberry | `fruit-blueberry` |
| Cranberry | `fruit-cranberry` |
| Orange | `fruit-orange` |
| Mango | `fruit-mango` |
| Cherry | `fruit-redcurrant` |

### Food - Meat
| Item | Code |
|------|------|
| Raw Bushmeat | `bushmeat-raw` |
| Cooked Bushmeat | `bushmeat-cooked` |
| Raw Poultry | `poultry-raw` |
| Cooked Poultry | `poultry-cooked` |
| Raw Redmeat | `redmeat-raw` |
| Cooked Redmeat | `redmeat-cooked` |

### Containers & Storage
| Item | Code |
|------|------|
| Linen Sack | `linen-sack` |
| Basket | `basket-normal` |

### Armor
| Item | Code |
|------|------|
| Chain Helmet (Iron) | `armor-head-chain-iron` |
| Chain Body (Iron) | `armor-body-chain-iron` |
| Chain Legs (Iron) | `armor-legs-chain-iron` |
| Plate Body (Iron) | `armor-body-plate-iron` |
| Plate Body (Steel) | `armor-body-plate-steel` |
| Brigandine Body (Iron) | `armor-body-brigandine-iron` |
| Leather Jerkin | `armor-body-jerkin-leather` |

### Ore Chunks
| Item | Code |
|------|------|
| Native Copper (Rich) | `ore-rich-nativecopper` |
| Native Copper (Medium) | `ore-medium-nativecopper` |
| Native Copper (Poor) | `ore-poor-nativecopper` |
| Cassiterite (Tin, Rich) | `ore-rich-cassiterite` |
| Limonite (Iron, Rich) | `ore-rich-limonite` |
| Galena (Lead, Rich) | `ore-rich-galena` |

---

## Item Code Patterns

### Tools
- Metal tools: `{tool}-{material}` (e.g., `pickaxe-iron`, `shovel-copper`)
- Stone tools: `{tool}-{stone}` (e.g., `axe-flint`, `knife-obsidian`)
- Axes specifically: `axe-felling-{material}` for felling axes

### Ingots & Metal
- Ingots: `ingot-{metal}` (copper, iron, steel, gold, silver, lead, tin, etc.)
- Metal bits: `metalbit-{metal}`
- Nuggets: `nugget-{metal}`
- Plates: `metalplate-{metal}`

### Food
- Bread: `bread-{grain}-{quality}` where quality: partbaked, perfect, charred
- Flour: `flour-{grain}`
- Dough: `dough-{grain}`
- Vegetables: `vegetable-{type}`
- Fruits: `fruit-{type}`
- Meat: `{type}-{state}` (bushmeat-raw, poultry-cooked, etc.)

### Armor
- Pattern: `armor-{slot}-{type}-{material}`
- Slots: head, body, legs
- Types: chain, plate, brigandine, scale, lamellar, jerkin
- Materials: copper, iron, steel, leather, etc.

### Ore
- Pattern: `ore-{grade}-{mineral}` where:
  - grade: poor, medium, rich, bountiful
  - mineral: nativecopper, cassiterite, limonite, malachite, galena, etc.

### Clothing (563 items)
- Pattern: `clothes-nadiya-{slot}-{style}`
- Large variety of styles and slots

---

## Metal Types Reference

| Common Name | Code | Source Ore |
|-------------|------|------------|
| Copper | copper | nativecopper, malachite |
| Tin | tin | cassiterite |
| Bronze | tinbronze | copper + tin alloy |
| Black Bronze | blackbronze | copper + silver + gold |
| Bismuth Bronze | bismuthbronze | copper + bismuth + zinc |
| Iron | iron | limonite, magnetite, hematite |
| Meteoric Iron | meteoriciron | meteorite |
| Steel | steel | iron + carbon (bloomery) |
| Gold | gold | nativegold, quartz-gold |
| Silver | silver | nativesilver, galena |
| Lead | lead | galena |

---

## Full Item List

See `vs-item-codes-raw.txt` for the complete alphabetical list of all 3,713 item codes.
