# Game Code Accessibility Analysis & Recommendations

> Research date: 2026-01-22 | polis-builder-npc

## Overview

Vintage Story has ~17,000 unique game codes:
- **12,822** block codes
- **3,713** item codes
- **391** entity codes

These codes are essential for LLM/agent interactions via poliscli, but finding the correct code is challenging due to:
1. Non-intuitive naming (limonite vs iron, galena vs lead)
2. Complex variant patterns (directional, material, state combinations)
3. No fuzzy matching or suggestions on error
4. Large search space with many similar codes

## Current State Analysis

### How poliscli Handles Codes Today

**Commands accepting codes:**
| Command | Accepts | Example |
|---------|---------|---------|
| `spawn` | Entity code | `spawn drifter-normal` |
| `give` | Item code | `give ingot-iron` |
| `equip` | Item code | `equip righthand axe-felling-iron` |
| `place` | Block code | `place planks-oak 100 65 200` |
| `setblock` | Block code | `setblock rock-granite 100 65 200` |
| `targets` | Search query | `targets -s chest` |

**Current search capabilities:**
- `targets -s <term>` - Substring search on nearby blocks/entities
- `targets --query <term>` - Server-side `codeContains` filter
- `targets --filter <term>` - Client-side substring filter
- `targets --exclude-natural` - Removes common terrain

**Limitations:**
1. No validation feedback - "Unknown block: foo" with no suggestions
2. Substring-only matching - No fuzzy/typo tolerance
3. Limited scope - `targets` only searches nearby blocks (32 block radius)
4. No item search - Can only discover items via inventory or wiki
5. No code completion or hints

### Error Messages (from C# harness)

```
Unknown entity type: foo. Use /polis spawn <entitycode> (try /polis entitytypes player).
Unknown block: foo
Unknown item or block code: foo
```

No suggestions, no "did you mean", no list of similar codes.

---

## Recommendations

### Tier 1: Documentation (Low Effort, High Impact)

#### 1.1 Reference Documents (DONE)
Created in this PR:
- `docs/research/vs-block-codes.md` - Quick reference with patterns
- `docs/research/vs-item-codes.md` - Quick reference with patterns
- `docs/research/vs-entity-codes.md` - Quick reference with patterns
- `docs/research/vs-*-codes-raw.txt` - Complete raw lists

**Usage for agents:** Include relevant sections in prompts, or direct agent to consult these files when encountering "Unknown X" errors.

#### 1.2 Common Aliases Cheat Sheet
Create a concise mapping of common names to codes:

```
# Metals (ore → mineral code)
iron ore → limonite, magnetite, hematite
copper ore → nativecopper, malachite
tin ore → cassiterite
lead ore → galena
gold ore → nativegold
silver ore → nativesilver, galena (byproduct)

# Tools (material variants)
pickaxe → pickaxe-{copper|iron|steel}
axe → axe-felling-{copper|iron|steel}

# Workstations
crafting table → (none, use inventory)
furnace → forge (for smelting), firepit-lit (for cooking)
grinder → quern-{granite|basalt|...}
```

### Tier 2: CLI Enhancements (Medium Effort)

#### 2.1 Add `codes` Subcommand for Local Search

```bash
# Search blocks by substring
./poliscli.py codes blocks iron
# Returns: ore-rich-limonite-granite, ingot-iron, ... (top 20)

# Search items
./poliscli.py codes items pick
# Returns: pickaxe-copper, pickaxe-iron, pickaxe-steel, ...

# Search entities
./poliscli.py codes entities bear
# Returns: bear-male-brown, bear-female-polar, ...
```

**Implementation:** Load `vs-*-codes-raw.txt` files and grep locally. ~50 lines of Python.

#### 2.2 Add `--suggest` Flag to Commands

When a code fails, automatically search for similar codes:

```bash
./poliscli.py give iron-ingot
# FAIL: Unknown item: iron-ingot
# Did you mean: ingot-iron, ingot-meteoriciron, ingot-blistersteel?
```

**Implementation:** On error, run local substring search and show top 3 matches.

#### 2.3 Add `--list-codes` to Relevant Commands

```bash
./poliscli.py give --list-codes pickaxe
# Matching item codes:
#   pickaxe-copper
#   pickaxe-iron
#   pickaxe-steel
#   ...
```

### Tier 3: Harness Enhancements (Higher Effort)

#### 3.1 Add `/polis/codes` Endpoint

New harness endpoint for code discovery:

```
GET /polis/codes?type=items&q=iron&limit=20
GET /polis/codes?type=blocks&q=ore
GET /polis/codes?type=entities&q=trader
```

Returns matching codes from game registries (authoritative, not wiki).

**Advantage:** Uses actual loaded game data, catches mod-added items.

#### 3.2 Enhance Error Responses with Suggestions

Modify `TryResolveStack()` and similar to return suggestions:

```json
{
  "Ok": false,
  "Message": "Unknown item: iron-ingot",
  "Suggestions": ["ingot-iron", "ingot-meteoriciron", "metalbit-iron"]
}
```

**Implementation:** On resolution failure, query game registries for substring matches.

#### 3.3 Add Fuzzy Matching

Implement Levenshtein distance matching for typo tolerance:

```bash
./poliscli.py give ingot-irn  # typo
# Resolved to: ingot-iron (closest match)
```

**Caution:** Could cause unintended actions. Consider `--strict` flag to disable.

### Tier 4: Agent-Side Improvements

#### 4.1 Pre-prompt Code Context

For agent runs, inject relevant code subsets into system prompt:

```markdown
## Available Entity Codes (common)
Livestock: chicken-rooster, chicken-hen, pig-wild-male, sheep-bighorn-male
Predators: wolf-male, bear-male-brown, drifter-normal
Traders: humanoid-trader-foods, humanoid-trader-survivalgoods
```

#### 4.2 Error Recovery Pattern

Teach agents to recover from code errors:

```markdown
When you get "Unknown X" errors:
1. Search local reference: ./poliscli.py codes {type} {term}
2. Check pattern in docs/research/vs-{type}-codes.md
3. Retry with corrected code
```

#### 4.3 Code Validation Pre-check

Before executing commands, validate codes exist:

```python
# In agent logic
if not validate_code(code, code_type):
    code = search_similar(code, code_type)[0]  # auto-correct
```

---

## Implementation Priority

| Priority | Enhancement | Effort | Impact |
|----------|------------|--------|--------|
| 1 | Reference docs (DONE) | Low | High |
| 2 | `codes` CLI subcommand | Low | High |
| 3 | `--suggest` on errors | Medium | High |
| 4 | `/polis/codes` endpoint | Medium | Medium |
| 5 | Fuzzy matching | High | Medium |
| 6 | Agent pre-prompts | Low | Medium |

---

## Code Pattern Quick Reference

### Block Codes
```
{type}-{variant}-{material}-{state}-{direction}

Examples:
ore-{grade}-{mineral}-{rock}     → ore-rich-limonite-granite
door-{type}-{wood}-{dir}-{state} → door-plank-oak-north-closed-left
crop-{plant}-{stage}             → crop-carrot-5
torch-basic-{state}-{dir}        → torch-basic-lit-up
```

### Item Codes
```
{type}-{variant}-{material}

Examples:
ingot-{metal}         → ingot-iron
pickaxe-{material}    → pickaxe-steel
axe-felling-{metal}   → axe-felling-copper
ore-{grade}-{mineral} → ore-rich-nativecopper
bread-{grain}-{state} → bread-spelt-perfect
armor-{slot}-{type}-{material} → armor-body-plate-steel
```

### Entity Codes
```
{type}-{variant}-{sex}-{age}

Examples:
bear-{sex}-{color}           → bear-male-brown
deer-{species}-{sex}-{age}   → deer-elk-male-adult
goat-{breed}-{sex}-{age}     → goat-angora-female-adult
drifter-{tier}               → drifter-corrupt
humanoid-trader-{specialty}  → humanoid-trader-foods
```

---

## Appendix: Mineral Names

Common confusion between real-world names and VS codes:

| Common Name | VS Mineral Code | Metal Produced |
|-------------|-----------------|----------------|
| Iron ore | limonite, magnetite, hematite | iron |
| Copper ore | nativecopper, malachite | copper |
| Tin ore | cassiterite | tin |
| Lead ore | galena | lead (+ silver) |
| Gold ore | nativegold | gold |
| Silver ore | nativesilver | silver |
| Zinc ore | sphalerite | zinc |
| Bismuth ore | bismuthinite | bismuth |
| Coal | bituminouscoal, anthracite | fuel |
| Sulfur | sulfur | sulfur |
| Saltpeter | saltpeter | gunpowder ingredient |
