# Vintage Story Entity Codes Reference

> Source: wiki.vintagestory.at (v1.18.15) | Total: 391 entities

This document provides entity codes for spawning creatures via poliscli/harness.

## Quick Reference - Common Entities

### Livestock (farmable)
| Entity | Code |
|--------|------|
| Rooster | `chicken-rooster` |
| Hen | `chicken-hen` |
| Chick | `chicken-baby` |
| Male Pig | `pig-wild-male` |
| Female Pig | `pig-wild-female` |
| Piglet | `pig-wild-piglet` |
| Male Sheep | `sheep-bighorn-male` |
| Female Sheep | `sheep-bighorn-female` |
| Lamb | `sheep-bighorn-lamb` |

### Predators (dangerous)
| Entity | Code |
|--------|------|
| Male Wolf | `wolf-male` |
| Female Wolf | `wolf-female` |
| Wolf Pup | `wolf-pup` |
| Male Bear (Brown) | `bear-male-brown` |
| Female Bear (Brown) | `bear-female-brown` |
| Male Fox | `fox-male` |
| Female Fox | `fox-female` |
| Male Hyena | `hyena-male` |
| Female Hyena | `hyena-female` |
| Raccoon | `raccoon-male` |

### Monsters
| Entity | Code |
|--------|------|
| Drifter (Normal) | `drifter-normal` |
| Drifter (Deep) | `drifter-deep` |
| Drifter (Tainted) | `drifter-tainted` |
| Drifter (Corrupt) | `drifter-corrupt` |
| Drifter (Nightmare) | `drifter-nightmare` |
| Drifter (Double-headed) | `drifter-double-headed` |
| Locust (Bronze) | `locust-bronze` |
| Locust (Corrupt) | `locust-corrupt` |
| Bowtorn (Surface) | `bowtorn-surface` |
| Shiver (Surface) | `shiver-surface` |

### Deer (wild game)
| Entity | Code |
|--------|------|
| Elk (Male) | `deer-elk-male-adult` |
| Elk (Female) | `deer-elk-female-adult` |
| Moose (Male) | `deer-moose-male-adult` |
| Moose (Female) | `deer-moose-female-adult` |
| Whitetail (Male) | `deer-whitetail-male-adult` |
| Whitetail (Female) | `deer-whitetail-female-adult` |
| Caribou (Male) | `deer-caribou-male-adult` |
| Caribou (Female) | `deer-caribou-female-adult` |

### Goats
| Entity | Code |
|--------|------|
| Mountain Goat (Male) | `goat-mountain-male-adult` |
| Mountain Goat (Female) | `goat-mountain-female-adult` |
| Angora Goat (Male) | `goat-angora-male-adult` |
| Ibex (Male) | `goat-ibexalp-male-adult` |
| Musk Ox (Male) | `goat-muskox-male-adult` |

### Small Animals
| Entity | Code |
|--------|------|
| Hare (Male) | `hare-male-lightbrown` |
| Hare (Female) | `hare-female-lightbrown` |
| Hare Baby | `hare-baby` |
| Gazelle (Male) | `gazelle-male` |
| Gazelle (Female) | `gazelle-female` |
| Salmon | `salmon` |
| Grub | `grub` |

### NPCs & Traders
| Entity | Code |
|--------|------|
| Trader (Foods) | `humanoid-trader-foods` |
| Trader (Building Materials) | `humanoid-trader-buildmaterials` |
| Trader (Survival Goods) | `humanoid-trader-survivalgoods` |
| Trader (Commodities) | `humanoid-trader-commodities` |
| Trader (Luxuries) | `humanoid-trader-luxuries` |
| Trader (Furniture) | `humanoid-trader-furniture` |
| Trader (Clothing) | `humanoid-trader-clothing` |
| Trader (Artisan) | `humanoid-trader-artisan` |
| Trader (Treasure Hunter) | `humanoid-trader-treasurehunter` |

### Special Entities
| Entity | Code |
|--------|------|
| Armor Stand | `armorstand` |
| Armor Stand (Aged) | `armorstand-aged` |
| Straw Dummy | `strawdummy` |
| Bee Swarm | `beemob` |
| Bell | `bell-normal` |
| Skeleton with Loot | `skeletonwithloot` |

---

## Entity Code Patterns

Entity codes follow the pattern: `type-variant-sex-age`

### Bears
- `bear-{sex}-{color}` where color: black, brown, sun, panda, polar

### Deer
- `deer-{species}-{sex}-{age}` where:
  - species: elk, moose, whitetail, caribou, chital, fallow, guemal, marsh, pampas, pudu, redbrocket, taruca, water
  - sex: male, female
  - age: adult, baby

### Goats
- `goat-{breed}-{sex}-{age}` where:
  - breed: angora, ibexalp, ibexnub, markhor, mountain, muskox, nubian, sirohi, takingold, turdag, valais
  - sex: male, female
  - age: adult, baby

### Hares
- `hare-{sex}-{color}` where:
  - color: arctic, ashgrey, darkbrown, desert, gold, lightbrown, lightgrey, silver, smokegrey

### Foxes
- `fox-male`, `fox-female`, `fox-pup-forest`
- `fox-arctic-male`, `fox-arctic-female`, `fox-pup-arctic`

### Drifters (monsters)
- `drifter-{tier}` where tier: normal, deep, tainted, corrupt, nightmare, double-headed

### Locusts (mechanical monsters)
- `locust-bronze`, `locust-corrupt`, `locust-corrupt-sawblade`
- Hacked variants: `locust-bronze-hacked`, `locust-corrupt-hacked`

---

## Butterflies (169 species)

Butterflies use the pattern: `butterfly-{species}{sex}`

Common examples:
- `butterfly-monarch`
- `butterfly-peacock`
- `butterfly-redadmiral`
- `butterfly-mourningcloak`
- `butterfly-smalltortoiseshell`

---

## Full Entity List

See `vs-entity-codes-raw.txt` for the complete alphabetical list of all 391 entity codes.
