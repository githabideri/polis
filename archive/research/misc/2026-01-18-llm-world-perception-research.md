# LLM World Perception for Game Agents

**Date:** 2026-01-18
**Status:** Research complete, implementation pending
**Purpose:** Inform design of enhanced HTTP harness endpoints for LLM-driven bot control

---

## Executive Summary

This document synthesizes research on how to feed game world information to Large Language Models (LLMs) for understanding and action. The goal is to extend the polis-builder-npc HTTP harness with endpoints that provide spatial, semantic, and strategic context to LLM agents controlling bots.

**Key findings:**
1. Structured text/JSON representations outperform raw visuals for LLM reasoning
2. ASCII maps work well at small scales (≤20x20) with explicit legends
3. Semantic tagging ("container", "harvestable") enables goal-oriented filtering
4. Natural language summaries bridge structured data to LLM understanding
5. Token efficiency matters for agentic loops - support multiple output formats

---

## 1. Existing LLM Game Agent Projects

### 1.1 Voyager (NVIDIA/MineDojo, 2023)

**Repository:** https://github.com/MineDojo/Voyager
**Paper:** "Voyager: An Open-Ended Embodied Agent with Large Language Models" (Wang et al., 2023)

**World State Representation:**
- Uses **Mineflayer** (JS bot framework) to extract structured state
- Does NOT use raw pixels for reasoning - text/JSON only
- Key observation components:
  - Inventory as slot → item:count mapping
  - Nearby entities with name, distance, direction
  - Nearby blocks with type, relative position
  - Bot status: health, hunger, position, equipment
  - Environment: time of day, biome, weather

**Observation Format Example:**
```
Nearby blocks: stone (below), dirt (2 blocks north), oak_log (3 blocks east)
Nearby entities: cow (5 blocks south), zombie (8 blocks north-east)
Inventory (36 slots): [0] iron_pickaxe, [1] cobblestone x64, [2] torch x12
Position: x=127, y=64, z=-89
Health: 20/20, Hunger: 18/20
Time: Day (noon), Biome: plains
```

**Action Interface:**
- LLM generates JavaScript code calling Mineflayer APIs
- Uses a skill library that grows over time (code reuse)
- Self-verification: LLM checks if task completed by comparing pre/post state

**Key Pattern:** Structured state extraction + code generation + skill accumulation

---

### 1.2 GITM - Ghost in the Minecraft (OpenGVLab, 2023)

**Repository:** https://github.com/OpenGVLab/GITM
**Paper:** "Ghost in the Minecraft: Generally Capable Agents for Open-World Environments" (Zhu et al., 2023)

**Architecture:**
- LLM Decomposer: Breaks high-level goals into subgoal chains
- LLM Planner: Creates action sequences for each subgoal
- LLM Interface: Translates to Mineflayer API calls

**World State Representation:**
- Text-based rather than vision
- Decomposes into: self-state, environmental context, goal context
- Presents as structured natural language, not raw JSON

**Observation Format Example:**
```
You are at position (45, 72, -120) in a forest biome.
You have 10 health points and 8 hunger points.
Your inventory contains: wooden_sword, 12 logs, 3 apples.
Nearby: oak tree (2m north), river (10m east), cave entrance (15m south).
Goal: Craft an iron pickaxe.
Progress: Need to find iron ore.
```

**Key Pattern:** Goal decomposition + natural language state

---

### 1.3 MineDojo (OpenAI/NVIDIA, 2022)

**Repository:** https://github.com/MineDojo/MineDojo
**Paper:** "MineDojo: Building Open-Ended Embodied Agents with Internet-Scale Knowledge" (Fan et al., 2022)

**Observation Space (Gym-style):**

| Type | Format | Notes |
|------|--------|-------|
| RGB image | (H, W, 3) array | 160x256 default |
| Inventory | Dictionary | slot_id → (item, count, durability) |
| Equipment | Dictionary | armor slots, held item |
| Location | (x, y, z, pitch, yaw) | Float coordinates |
| Biome ID | Integer | Minecraft biome code |
| **Voxels** | 3D array | Surrounding block types (e.g., 7x7x7) |

**Voxel Observation:** 3D grid centered on agent where each cell contains block type ID. Useful for immediate surroundings understanding.

**Key Pattern:** Multimodal (visual + structured) with voxel grid for local context

---

### 1.4 Smallville / Generative Agents (Stanford, 2023)

**Repository:** https://github.com/joonspk-research/generative_agents
**Paper:** "Generative Agents: Interactive Simulacra of Human Behavior" (Park et al., 2023)

**Memory Architecture:**
```python
memory_stream = [
    {"timestamp": "...", "type": "observation", "content": "...", "importance": 2},
    {"timestamp": "...", "type": "reflection", "content": "...", "importance": 7}
]
# Retrieval: recency + importance + relevance scoring
```

**Key Patterns:**
- Natural language for everything (no JSON state dumps)
- Memory stream with timestamped observations + reflections
- Importance scoring (LLM rates 1-10)
- Periodic reflection to synthesize higher-level insights
- Planning layer: daily/hourly schedules decomposed recursively

---

### 1.5 STEVE-1 (2023)

**Repository:** https://github.com/Shalev-Lifshitz/STEVE-1
**Paper:** "STEVE-1: A Generative Model for Text-to-Behavior in Minecraft" (Lifshitz et al., 2023)

**Approach:**
- Text-conditioned behavior cloning
- Visual input (RGB frames) + text goal
- Generates low-level keyboard/mouse actions directly
- No explicit structured world state - learns from video

**Relevance:** Shows visual-only approaches are possible but require massive training data. For our purposes, structured text is more practical.

---

## 2. LLM Spatial Understanding

### 2.1 What LLMs Understand Well

**2D Grids and Coordinate Systems:**
- Perform reasonably well with small grids (up to ~10x10)
- Better with cardinal directions (N/S/E/W) than degrees
- Coordinate systems work best when:
  - Origin clearly defined
  - Axes labeled consistently
  - Distances in human-readable units

**ASCII Map Comprehension:**
- Can parse and reason about simple ASCII maps
- Best results with:
  - Consistent symbol legend provided
  - Map size under 30x30 characters
  - Clear boundary markers
  - Low information density

**Example of Well-Understood Format:**
```
Legend: @ = you, # = wall, . = floor, D = door, C = chest, E = enemy

Map (N is up):
##########
#........#
#.@......D
#....C...#
#..E.....#
##########

You are at (2,2). The door is at (9,2).
A chest is at (5,3). An enemy is at (3,4).
```

### 2.2 Known Limitations

| Challenge | Description |
|-----------|-------------|
| Path planning | LLMs struggle with optimal pathfinding |
| Occlusion | Understanding what blocks line-of-sight |
| 3D visualization | Vertical relationships harder than horizontal |
| Large scale | Performance degrades rapidly above 20x20 grids |
| Rotation/orientation | Reasoning about facing direction is error-prone |
| Distance estimation | Imprecise without explicit numbers |

**Empirical Findings:**
- GPT-4 achieves ~70% accuracy on simple 8x8 grid navigation tasks
- Performance drops to ~40% on 15x15 grids with obstacles
- Chain-of-thought prompting improves spatial reasoning by ~15-20%
- Providing structured coordinate lists outperforms ASCII maps for precision tasks

### 2.3 Best Representation Formats (Ranked)

1. **Structured coordinate lists** - Most reliable for precise operations
```json
{
  "self": {"x": 100, "y": 65, "z": 200, "facing": "north"},
  "nearby": [
    {"type": "chest", "x": 102, "y": 65, "z": 200, "distance": 2, "direction": "east"}
  ]
}
```

2. **Natural language descriptions** - Good for high-level understanding
```
You are facing north at position (100, 65, 200).
A chest is 2 blocks to your east.
```

3. **Simple ASCII maps with legend** - Good for spatial overview
```
...C..
.@....
...D..
```

4. **Egocentric descriptions** - Intuitive but can be ambiguous
```
To your left: stone wall
Ahead: open corridor with door at the end
```

### 2.4 Relevant Benchmarks

| Benchmark | Focus | Notes |
|-----------|-------|-------|
| SpartQA | Spatial question answering | 60-70% on basic, 40-50% on transitive inference |
| bAbI Tasks 17-20 | Positional reasoning | GPT-4 ~85%, degrades with sequence length |
| CLEVR (text variants) | Compositional spatial reasoning | Struggles with counting and relative positioning |
| StepGame | Multi-hop spatial reasoning | Tests tracking through multiple moves |

---

## 3. ASCII/Text World Rendering

### 3.1 Roguelike Conventions

**Dwarf Fortress:**
- Extended ASCII (CP437) character set
- Multi-layer information via color and character
- Standard symbols:
  - `.` floor, `#` wall, `+` door (closed), `'` door (open)
  - `~` water, `≈` deep water, `▲` up stairs, `▼` down stairs
  - Uppercase = creatures, lowercase = items
  - Color encodes material/status

**NetHack:**
- Single-layer ASCII with extensive vocabulary
- `@` player, `a-z` monsters by type, `A-Z` stronger variants
- Items: `[` armor, `)` weapon, `!` potion, `?` scroll, `/` wand
- Terrain: `.` floor, `#` corridor, `|`/`-` walls

**ADOM/Angband:**
- Similar with variations
- `<` up stairs, `>` down stairs
- `*` glowing/magical items

### 3.2 Multi-Layer Representation for 3D Voxel Games

**Option A: Stacked Layers (Slice Approach)**
```
Layer Y=64 (ground):
################
#.C...........D#
#.@............#
################

Layer Y=65 (above):
################
#.L............#
################

Legend: # wall, . air, @ bot, C chest, D door, L lantern
```

**Option B: Priority Overlay (Single View)**
Show most important element per cell (Entities > Items > Structures > Terrain):
```
Map (Y=63-66, top-down):
################
#EC...........D#
#.@............#
#.....T........#
################

Legend: E=enemy, C=chest, D=door, T=tree, @=bot
Elevation at @: Y=64
```

**Option C: Egocentric Radar (Recommended for Agents)**
```
Radar (radius=8, you=center, N=up):
        N
    . . . . .
  . . T . . . .
  . . . . C . .
W . . . @ . . . E
  . . E . . D .
    . . . . .
        S

Entities:
- @ (you): (0,0), facing N
- E (enemy): (3,0), (2,-2)
- C (chest): (2,1)
```

### 3.3 Scale and Windowing

| Radius | Area | Use Case | Token Cost |
|--------|------|----------|------------|
| 5 blocks | ~100 cells | Immediate combat/interaction | ~100-150 |
| 10 blocks | ~400 cells | Local task context | ~300-400 |
| 16 blocks | 1 chunk | Standard exploration | ~600-800 |
| 32+ blocks | Large | Needs compression | ~1500+ |

**Recommended Default:** 21x21 grid (radius 10) - covers relevant interaction range, fits in ~500 tokens.

### 3.4 Vertical (Y-axis) Handling

**Option 1: Current Slice + Annotations**
```
=== Level Y=64 (ground) ===
[Above: Y=65 has tree canopy]
[Below: Y=63 has cave entrance at (5,3)]
```

**Option 2: Multi-Slice Summary**
```
Y=66: . . T T . .   (canopy)
Y=65: . . T T . .   (trunks)
Y=64: . @ . . X .   (ground, you, hole)
Y=63: . . . . C .   (cave)
```

**Option 3: Cross-Section (for mining/building)**
```
Side view (E-W at Z=5):
Y68 |
Y67 | T T
Y66 | T T
Y65 |   @     ← you
Y64 | # # # #
Y63 | # C # # ← cave
```

---

## 4. Proposed Symbol Scheme for Vintage Story

### 4.1 Core Symbols

| Symbol | Meaning | Category |
|--------|---------|----------|
| `@` | Bot (self) | Agent |
| `P` | Other player | Agent |
| `B` | Other bot | Agent |
| `.` | Passable terrain (floor, grass) | Terrain |
| `#` | Solid block (wall, stone) | Terrain |
| `~` | Water | Terrain |
| `^` | Stairs/ladder up | Terrain |
| `v` | Stairs/ladder down | Terrain |
| `T` | Tree/vegetation | Resource |
| `*` | Ore/mineral | Resource |
| `%` | Crop | Resource |
| `+` | Door (closed) | Interactable |
| `'` | Door (open) | Interactable |
| `C` | Chest/container | Interactable |
| `W` | Workstation | Interactable |
| `i` | Item on ground | Pickup |
| `a` | Animal (passive) | Entity |
| `h` | Hostile creature | Entity |
| `n` | Neutral NPC | Entity |

### 4.2 Block Code Mapping (Implementation Reference)

```csharp
static Dictionary<string, char> BlockSymbols = new() {
    // Terrain
    {"game:air", ' '},
    {"game:soil-*", '.'},
    {"game:grass-*", ','},
    {"game:stone-*", '#'},
    {"game:water-*", '~'},
    {"game:lava-*", '&'},

    // Trees/plants
    {"game:log-*", 'T'},
    {"game:leaves-*", 't'},
    {"game:tallgrass-*", '"'},
    {"game:crop-*", '%'},

    // Structures
    {"game:door-*", '+'},
    {"game:planks-*", '='},

    // Containers
    {"game:chest-*", 'C'},
    {"game:barrel-*", 'U'},

    // Workstations
    {"game:anvil-*", 'A'},
    {"game:forge-*", 'F'},
    {"game:quern-*", 'Q'},
};
```

---

## 5. Recommended HTTP Harness Endpoints

### 5.1 GET /polis/map - ASCII Terrain Map

**Purpose:** Provide spatial overview for navigation decisions

**Parameters:**
- `botId` or `playerUid`: Center point
- `radius`: 1-16 (default 8)
- `layer`: `terrain`, `entities`, `resources`, `all` (default: all)
- `format`: `json` (default), `ascii`, `toon`

**Response Example:**
```json
{
  "ok": true,
  "center": [228, 64, 260],
  "radius": 8,
  "facing": "north",
  "legend": {
    "@": "bot (you)",
    ".": "passable",
    "#": "solid",
    "C": "chest",
    "D": "door",
    "i": "item",
    "a": "animal"
  },
  "map": [
    "..#####..",
    "..#...D..",
    "..#.C.#..",
    "..#...#..",
    "....@....",
    "..i......",
    "...a.....",
    "........."
  ],
  "annotations": [
    {"symbol": "C", "pos": [230, 64, 262], "code": "game:chest-east", "tags": ["container"]},
    {"symbol": "D", "pos": [232, 64, 263], "code": "game:door-solid-oak", "state": "closed"},
    {"symbol": "i", "pos": [227, 64, 258], "code": "game:stone-granite", "qty": 5},
    {"symbol": "a", "pos": [228, 64, 256], "code": "game:chicken-hen", "class": "animal"}
  ]
}
```

### 5.2 GET /polis/surroundings - Natural Language Summary

**Purpose:** High-level description for strategic reasoning

**Response Example:**
```json
{
  "ok": true,
  "summary": "You are outdoors on flat terrain near a small wooden structure. A door to the north leads inside. A chest is visible through the doorway. One chicken is nearby to the south.",
  "terrain": {
    "type": "plains",
    "elevation": "flat",
    "shelter": "partial",
    "light": "daylight"
  },
  "features": [
    {"type": "structure", "direction": "north", "distance": 3, "description": "small wooden building with door"},
    {"type": "resource", "direction": "south", "distance": 5, "description": "loose stone items"},
    {"type": "creature", "direction": "south", "distance": 7, "description": "passive chicken"}
  ],
  "threats": [],
  "opportunities": [
    "container accessible nearby",
    "harvestable chicken if butcher tools available"
  ]
}
```

### 5.3 GET /polis/navigation - Pathfinding Support

**Purpose:** Help LLM make movement decisions

**Parameters:**
- `botId`: Source
- `targetX`, `targetY`, `targetZ`: Destination

**Response Example:**
```json
{
  "ok": true,
  "from": [228, 64, 260],
  "to": [235, 64, 265],
  "reachable": true,
  "distance": 9.2,
  "pathLength": 12,
  "obstacles": ["door at (232, 64, 263) - may need to activate"],
  "waypoints": [
    {"pos": [232, 64, 262], "note": "approach door"},
    {"pos": [232, 64, 263], "note": "door - activate to open"},
    {"pos": [235, 64, 265], "note": "destination"}
  ]
}
```

### 5.4 Enhanced /polis/targets - Semantic Tags

Add `tags` and `actions` fields to existing target entries:

```json
{
  "Pos": [224, 64, 270],
  "Code": "game:chest-east",
  "Dist": 1.23,
  "tags": ["container", "storage", "interactive"],
  "actions": ["activate", "takefrom", "putinto"]
}
```

**Tag Categories:**
- **Functional:** `container`, `workstation`, `door`, `light`, `mechanism`
- **Resource:** `harvestable`, `minable`, `choppable`, `huntable`
- **State:** `open`, `closed`, `lit`, `unlit`, `ripe`, `empty`
- **Interaction:** `interactive`, `usable`, `breakable`

---

## 6. Token Efficiency

### 6.1 Format Comparison

| Format | Tokens | Use Case |
|--------|--------|----------|
| 11x11 ASCII + legend | ~150-200 | Quick spatial check |
| 21x21 ASCII + annotations | ~500-600 | Standard navigation |
| Full state + map + NL summary | ~800-1000 | Strategic planning |
| TOON compact | ~100-150 | Agentic loops |

### 6.2 TOON Format (Token-Optimized Object Notation)

Already implemented in poliscli. Extend to API endpoints:

```
bot:228.5,64.0,260.2|hp:20|rh:knife-copper|lh:null
near:chest@230,262:3m|door@232,263:4m|item@227,258:2m
path:chest:ok:12steps|door:blocked:need-open
```

### 6.3 Compression Strategies

1. **Omit empty rows/columns** - Show only interesting areas
2. **Run-length encoding** - `. x 15, # x 4, . x 2`
3. **Entity-centric only** - Skip full map, just list relative positions
4. **Hierarchical** - Overview grid + detailed focus area
5. **Delta updates** - `"bot1 moved +2x"` instead of full state

---

## 7. Example Agent Workflow

```
1. GET /polis/status           → Verify world ready
2. GET /polis/surroundings     → Understand situation (NL summary)
3. GET /polis/map?radius=10    → See spatial layout (ASCII)
4. GET /polis/targets?mode=all → Get interactables with tags
5. [LLM reasons]: "I see a chest 3 blocks north. I should store items."
6. GET /polis/navigation?targetX=230&targetZ=262 → Check path
7. POST /polis/command {"cmd":"goto","args":["230","64","261"]}
8. POST /polis/command {"cmd":"putinto","args":["230","64","262","0"]}
9. GET /polis/state            → Verify success
```

---

## 8. Implementation Priority

| Priority | Endpoint/Feature | Rationale |
|----------|-----------------|-----------|
| **High** | `/polis/map` | Core spatial understanding |
| **High** | Semantic tags on `/targets` | Goal-oriented filtering |
| Medium | `/polis/surroundings` | Strategic context |
| Medium | `/polis/navigation` | Path planning support |
| Lower | TOON format option | Token optimization |
| Lower | Configurable detail levels | Flexible verbosity |

---

## 9. References and Further Reading

### Papers

| Paper | Authors | Year | Link |
|-------|---------|------|------|
| Voyager: An Open-Ended Embodied Agent with LLMs | Wang et al. | 2023 | https://arxiv.org/abs/2305.16291 |
| Ghost in the Minecraft (GITM) | Zhu et al. | 2023 | https://arxiv.org/abs/2305.17144 |
| MineDojo: Building Open-Ended Embodied Agents | Fan et al. | 2022 | https://arxiv.org/abs/2206.08853 |
| STEVE-1: Text-to-Behavior in Minecraft | Lifshitz et al. | 2023 | https://arxiv.org/abs/2306.00937 |
| Generative Agents (Smallville) | Park et al. | 2023 | https://arxiv.org/abs/2304.03442 |
| Chain-of-Thought Prompting | Wei et al. | 2022 | https://arxiv.org/abs/2201.11903 |
| Language Models as Zero-Shot Planners | Huang et al. | 2022 | https://arxiv.org/abs/2201.07207 |
| PaLM-E: Embodied Multimodal Language Model | Driess et al. | 2023 | https://arxiv.org/abs/2303.03378 |

### Repositories

| Project | URL |
|---------|-----|
| Voyager | https://github.com/MineDojo/Voyager |
| GITM | https://github.com/OpenGVLab/GITM |
| MineDojo | https://github.com/MineDojo/MineDojo |
| STEVE-1 | https://github.com/Shalev-Lifshitz/STEVE-1 |
| Generative Agents | https://github.com/joonspk-research/generative_agents |
| Mineflayer (bot framework) | https://github.com/PrismarineJS/mineflayer |
| NetHack Learning Environment | https://github.com/facebookresearch/nle |

### Spatial Reasoning Benchmarks

| Benchmark | Focus | URL |
|-----------|-------|-----|
| SpartQA | Spatial QA | https://github.com/HLR/SpartQA_generation |
| bAbI Tasks | Positional reasoning | https://github.com/facebookresearch/bAbI-tasks |
| StepGame | Multi-hop spatial | https://github.com/ZhengxiangShi/StepGame |

### Roguelike Symbol References

| Game | Reference |
|------|-----------|
| Dwarf Fortress | http://dwarffortresswiki.org/index.php/Tileset |
| NetHack | https://nethackwiki.com/wiki/Symbol |
| DCSS | https://crawl.develz.org/docs/key_help.txt |

---

## 10. Open Questions

1. **Caching strategy** - How often to regenerate ASCII maps? On-demand vs periodic?
2. **Multi-bot coordination** - How to represent multiple bot positions efficiently?
3. **Memory/history** - Should we track movement history for LLM context?
4. **Chunk boundaries** - How to handle queries near unloaded chunks?
5. **Performance** - Block iteration for large radii may need optimization

---

## Appendix: Sample Combined Observation

A complete observation for LLM consumption combining all formats:

```
=== BOT STATUS ===
Bot "smith-01" at (228, 64, 260) facing NORTH
Health: 20/20 | Hunger: 18/20
Right hand: iron_pickaxe | Left hand: (empty)
Status: idle

=== SITUATION SUMMARY ===
You are outdoors on flat grassland. A small wooden building is 4 blocks
to your north with a closed door. Inside the building is a storage chest.
A chicken is wandering 5 blocks to your south. No threats detected.

=== LOCAL MAP (radius 8) ===
..........#####..
..........#...#..
..........#.C.+..
..........#...#..
..........#####..
.................
........@........
.................
........a........
.................

Legend: @ you, # wall, + door, C chest, a animal, . passable

=== NEARBY TARGETS ===
1. Chest at (230, 64, 262) - 4 blocks N - tags: [container, storage]
2. Door at (234, 64, 262) - 6 blocks NE - tags: [door, closed, interactive]
3. Chicken at (228, 64, 255) - 5 blocks S - tags: [animal, harvestable]
4. Stone item at (226, 64, 259) - 2 blocks SW - tags: [pickup, resource]

=== AVAILABLE ACTIONS ===
- goto <x> <y> <z>: Move to position
- pickup [entityId]: Pick up nearby item
- activate <x> <y> <z>: Interact with block (open door, access chest)
- takefrom <x> <y> <z> <slot>: Take from container
- putinto <x> <y> <z> <slot>: Put into container
```

**Token estimate:** ~400-500 tokens for this complete observation.
