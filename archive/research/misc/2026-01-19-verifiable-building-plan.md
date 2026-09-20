# Plan: Verifiable Building System

## Problem Statement

Current building approach is unreliable:
1. **No verification** - Commands report `Ok: true` but don't verify blocks actually placed
2. **Haphazard scripting** - Bash loops with hardcoded coordinates, no error handling
3. **No progress tracking** - Can't resume partial builds, no completion percentage
4. **No pre-flight checks** - Doesn't verify inventory, position, or target area before starting
5. **Coordinate confusion** - Easy to build in wrong location without noticing

## Goals

1. **Blueprint-driven builds** - Declarative specification of what to build
2. **Deterministic verification** - Scan world state and compare to blueprint
3. **Step-by-step validation** - Verify each placement before proceeding
4. **Progress tracking** - Know exactly what's built, what's pending, what failed
5. **Resumability** - Continue partial builds from where they left off

---

## Architecture

### 1. Blueprint Format

```yaml
# blueprint.yaml
name: "7x7 Foundation"
origin: [0, 0, 0]  # Relative origin (added to placement position)
blocks:
  - pos: [0, 0, 0]
    code: "game:cobblestone-granite"
  - pos: [1, 0, 0]
    code: "game:cobblestone-granite"
  # ... or use patterns:
patterns:
  - type: "fill"
    from: [0, 0, 0]
    to: [6, 0, 6]
    code: "game:cobblestone-granite"
```

**Expanded form** (after pattern expansion):
```json
{
  "name": "7x7 Foundation",
  "blocks": [
    {"pos": [235, 3, 290], "code": "game:cobblestone-granite"},
    {"pos": [236, 3, 290], "code": "game:cobblestone-granite"},
    // ... 49 total
  ]
}
```

### 2. Harness Endpoints

#### `/polis/scan` - Scan area for block states

**Request:**
```json
{
  "from": [235, 3, 290],
  "to": [241, 3, 296]
}
```

**Response:**
```json
{
  "ok": true,
  "blocks": [
    {"pos": [235, 3, 290], "code": "game:cobblestone-granite"},
    {"pos": [236, 3, 290], "code": "game:air"},
    // ...
  ]
}
```

#### `/polis/verify` - Compare blueprint to world state

**Request:**
```json
{
  "blueprint": [
    {"pos": [235, 3, 290], "code": "game:cobblestone-granite"},
    {"pos": [236, 3, 290], "code": "game:cobblestone-granite"}
  ]
}
```

**Response:**
```json
{
  "ok": true,
  "total": 49,
  "matched": 47,
  "missing": [
    {"pos": [237, 3, 292], "expected": "game:cobblestone-granite", "actual": "game:air"}
  ],
  "wrong": [
    {"pos": [238, 3, 293], "expected": "game:cobblestone-granite", "actual": "game:soil-medium"}
  ],
  "complete": false,
  "completionPct": 95.9
}
```

### 3. CLI Commands

#### `poliscli.py blueprint` - Manage blueprints

```bash
# Create blueprint from pattern
poliscli.py blueprint create --name "foundation" --fill 235,3,290 241,3,296 game:cobblestone-granite

# Load and expand blueprint file
poliscli.py blueprint load foundation.yaml --origin 235,3,290

# List blocks in blueprint
poliscli.py blueprint show foundation.yaml
```

#### `poliscli.py build` - Execute blueprint

```bash
# Build with verification
poliscli.py build foundation.yaml --origin 235,3,290 --verify

# Resume partial build
poliscli.py build foundation.yaml --origin 235,3,290 --resume

# Dry run (show what would be built)
poliscli.py build foundation.yaml --origin 235,3,290 --dry-run
```

**Build process:**
1. Load blueprint, calculate absolute positions
2. Pre-flight: Check bot inventory (has required blocks?)
3. Pre-flight: Scan target area (any obstructions?)
4. For each block:
   a. Check if already placed (skip if matches)
   b. Place block
   c. Verify placement
   d. Update progress
5. Final verification scan
6. Report results

#### `poliscli.py scan` - Scan world area

```bash
# Scan area and show blocks
poliscli.py scan 235,3,290 241,3,296

# Scan and save as blueprint
poliscli.py scan 235,3,290 241,3,296 --save captured.yaml
```

#### `poliscli.py verify` - Verify blueprint against world

```bash
# Verify blueprint matches world
poliscli.py verify foundation.yaml --origin 235,3,290

# Output: 47/49 blocks placed (95.9%), 2 missing
```

### 4. Build Execution Flow

```
┌─────────────────────────────────────────────────────────────┐
│                      BUILD COMMAND                           │
├─────────────────────────────────────────────────────────────┤
│  1. LOAD BLUEPRINT                                          │
│     - Parse YAML/JSON                                       │
│     - Expand patterns to block list                         │
│     - Apply origin offset                                   │
├─────────────────────────────────────────────────────────────┤
│  2. PRE-FLIGHT CHECKS                                       │
│     □ Bot selected and responsive                           │
│     □ Bot has required materials (count by block type)      │
│     □ Target area scanned (identify obstructions)           │
│     □ Bot positioned near build area                        │
├─────────────────────────────────────────────────────────────┤
│  3. EXECUTION LOOP                                          │
│     For each block in blueprint:                            │
│       a. Scan target position                               │
│       b. If already correct → skip, mark complete           │
│       c. If obstructed → warn, skip or fail                 │
│       d. Place block                                        │
│       e. Verify placement (re-scan)                         │
│       f. Update progress: [=====>    ] 23/49 (47%)          │
│       g. Check inventory, warn if running low               │
├─────────────────────────────────────────────────────────────┤
│  4. FINAL VERIFICATION                                      │
│     - Full area scan                                        │
│     - Compare to blueprint                                  │
│     - Report: matched, missing, wrong                       │
├─────────────────────────────────────────────────────────────┤
│  5. RESULT                                                  │
│     ✓ Build complete: 49/49 blocks placed                   │
│     - Screenshot saved: build-result-2026-01-19.png         │
│     - Blueprint verified: 100% match                        │
└─────────────────────────────────────────────────────────────┘
```

---

## Implementation Phases

### Phase 1: Scan/Verify Endpoints (Harness)

**Files:** `PolisBuilderNpcSystem.cs`

1. Add `ExecuteScanCommand`:
   - Input: from/to coordinates (bounding box)
   - Query `BlockAccessor.GetBlock()` for each position
   - Return array of {pos, code}

2. Add `ExecuteVerifyCommand`:
   - Input: blueprint array of {pos, code}
   - Scan each position
   - Compare to expected
   - Return matched/missing/wrong lists

**Estimated scope:** ~100-150 lines C#

### Phase 2: CLI Blueprint Commands

**Files:** `scripts/poliscli.py`

1. Add `blueprint` subcommand group:
   - `create` - Generate blueprint from patterns
   - `load` - Load and expand YAML file
   - `show` - Display blueprint contents

2. Add `scan` command:
   - Call `/polis/scan` endpoint
   - Format output or save to file

3. Add `verify` command:
   - Load blueprint
   - Call `/polis/verify` endpoint
   - Report results

**Estimated scope:** ~200-300 lines Python

### Phase 3: Intelligent Build Command

**Files:** `scripts/poliscli.py`

1. Add `build` command:
   - Load blueprint
   - Pre-flight checks
   - Execution loop with verification
   - Progress reporting
   - Final verification

2. Features:
   - `--verify` flag for per-block verification
   - `--resume` to continue partial builds
   - `--dry-run` to preview
   - Progress bar output

**Estimated scope:** ~300-400 lines Python

### Phase 4: Blueprint Patterns

1. Pattern types:
   - `fill` - Solid rectangular region
   - `outline` - Hollow rectangle (walls)
   - `line` - Single row of blocks
   - `layer` - Single Y-level fill

2. Blueprint composition:
   - Multiple patterns per blueprint
   - Named sub-blueprints for reuse

---

## Data Flow

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Blueprint   │────▶│   poliscli   │────▶│   Harness    │
│    YAML      │     │   build cmd  │     │  /polis/*    │
└──────────────┘     └──────────────┘     └──────────────┘
                            │                    │
                            ▼                    ▼
                     ┌──────────────┐     ┌──────────────┐
                     │   Progress   │     │  World State │
                     │   Tracking   │     │   (VS API)   │
                     └──────────────┘     └──────────────┘
```

---

## Example Usage

### Build a verified 7x7 foundation

```bash
# 1. Create blueprint
cat > foundation.yaml << 'EOF'
name: "7x7 Foundation"
patterns:
  - type: fill
    from: [0, 0, 0]
    to: [6, 0, 6]
    code: "game:cobblestone-granite"
EOF

# 2. Spawn and prepare bot
./scripts/poliscli.py spawn
export POLIS_BOT_ID=$(./scripts/poliscli.py bots -q | tail -1 | cut -d: -f1)
./scripts/poliscli.py select $POLIS_BOT_ID
./scripts/poliscli.py give game:cobblestone-granite 50

# 3. Position bot at build site
./scripts/poliscli.py goto 238 3 300

# 4. Build with verification (origin = bot position)
./scripts/poliscli.py build foundation.yaml --origin 235,3,297 --verify

# Output:
# Pre-flight checks:
#   ✓ Bot #547 selected
#   ✓ Inventory: 50x cobblestone-granite (need 49)
#   ✓ Target area: 49 air blocks (clear)
#   ✓ Bot at (238, 3, 300), 5 blocks from build area
#
# Building: [====================] 49/49 (100%)
#   Row z=297: ✓✓✓✓✓✓✓
#   Row z=298: ✓✓✓✓✓✓✓
#   Row z=299: ✓✓✓✓✓✓✓
#   Row z=300: ✓✓✓✓✓✓✓
#   Row z=301: ✓✓✓✓✓✓✓
#   Row z=302: ✓✓✓✓✓✓✓
#   Row z=303: ✓✓✓✓✓✓✓
#
# Final verification: 49/49 blocks correct (100%)
# Inventory remaining: 1x cobblestone-granite
# Screenshot: build-foundation-2026-01-19.png

# 5. Verify later
./scripts/poliscli.py verify foundation.yaml --origin 235,3,297
# Output: 49/49 blocks match (100%)
```

---

## Success Criteria

1. **Deterministic builds** - Same blueprint + origin = same result
2. **Full verification** - Every placed block confirmed via world scan
3. **Clear progress** - Know exactly what's built at any point
4. **Resumable** - Can stop and continue builds
5. **Pre-flight safety** - Catches problems before building starts
6. **Documented results** - Screenshots and verification reports

---

## Open Questions

1. **Block rotation/orientation** - Some blocks have facing. Include in blueprint?
2. **Multi-material builds** - How to ensure bot has all required block types?
3. **Large builds** - Chunk loading, build in sections?
4. **Undo/rollback** - Save original state, allow reverting?
5. **Concurrent builds** - Multiple bots building same blueprint?
