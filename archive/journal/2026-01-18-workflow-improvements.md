# Workflow Improvements (2026-01-18)

Improvements to the visual testing workflow based on hands-on testing session findings.

## Issues Discovered

| Issue | Root Cause | Solution |
|-------|------------|----------|
| Bot selection doesn't persist | `cmd_select` sends to harness but poliscli has no local state | Print export hint after select |
| Targets radius capped at 16 | Intentional clamp in `PolisTestHarness.cs:349` | Increased cap to 32 |
| Camera positioning forgotten | No convenience command | Added `setup-view` command |
| Agents struggle with `-q` flag | `-q` is global `--quiet`, not query | Renamed to `--search/-s` |

## Changes Made

### 1. Bot Selection Persistence Hint

**File:** `scripts/poliscli.py`

After a successful `select` command, now prints:
```
# To persist: export POLIS_BOT_ID=<id>
```

This is printed to stderr so it doesn't pollute scripted output.

**Design decision:** We chose to print a hint rather than:
- Cache in a file (adds complexity, can get stale)
- Auto-set env var (Python can't modify parent shell environment)

The user can run the export command or wrap in a shell function.

### 2. Targets Radius Cap Increased

**File:** `PolisTestHarness.cs:349`

Changed from:
```csharp
radius = GameMath.Clamp(radius, 1f, 16f);
```

To:
```csharp
radius = GameMath.Clamp(radius, 1f, 32f);
```

**Design decision:** 32 blocks is a reasonable balance:
- Large enough to find things visible in typical screenshots
- Not so large it causes performance issues scanning thousands of blocks
- Still prevents unbounded scans

### 3. New `setup-view` Command

**File:** `scripts/poliscli.py`

New command that positions player camera to view the selected bot:

```bash
./scripts/poliscli.py setup-view              # Position 3m from bot
./scripts/poliscli.py setup-view -d 5         # Position 5m from bot
./scripts/poliscli.py setup-view --screenshot --save  # Position + capture
```

Implementation:
1. Gets bot position from `/polis/state`
2. Calculates viewing position (distance blocks to the south, +1 elevation)
3. Calculates yaw to face the bot
4. Teleports player with calculated yaw
5. Optionally takes screenshot

**Design decision:** Separate command rather than auto-behavior because:
- Explicit is better than implicit
- User may want different viewing angles
- Doesn't break existing workflows

### 4. Renamed `--query` to `--search/-s`

**File:** `scripts/poliscli.py`

Changed from:
```python
p.add_argument("--query", dest="q", help="Search query filter")
```

To:
```python
p.add_argument("--search", "-s", dest="q", help="Search blocks/entities by code substring")
```

**Design decision:** Multiple agents (5+) struggled with `-q` expecting it to be the search flag, but `-q` is the global `--quiet` flag. The new `--search/-s` is intuitive and doesn't conflict (subcommand flags are independent). HTTP API keeps `?q=` as that's idiomatic for REST.

### 5. Documentation Updates

- **AGENTS.md:** Added "Common Workflow Pitfalls" section
- **AGENTS.md:** Updated "Visual Testing Protocol" to use `setup-view`
- **docs/TESTING_HARNESS_TARGETS.md:** Updated radius limit from 16 to 32

## Verification Results

All features tested and working:

```bash
# Test 1: Bot selection hint
./scripts/poliscli.py select 533
# Output: # To persist: export POLIS_BOT_ID=533 ✓

# Test 2: Radius increase
./scripts/poliscli.py targets --radius 30
# Output: Radius: 30 (not capped at 16) ✓

# Test 3: setup-view command
./scripts/poliscli.py setup-view --screenshot --save
# Output: Positioned camera, bot visible in screenshot ✓

# Test 4: Search flag
./scripts/poliscli.py targets -s bauxite --radius 30
# Output: Found 4 bauxite blocks at distances 3.57-14.59 ✓

./scripts/poliscli.py targets -s limonite --radius 32
# Output: Found ore-poor-limonite-shale at (220, 3, 258) ✓
```

## Known Limitation: Ore Naming Mismatch

**Problem:** Vintage Story ore block codes don't always match player-expected names.

Example:
- Player searches for "iron ore"
- Actual block code: `game:ore-poor-limonite-shale`
- "Limonite" is a real-world iron ore, but has no "iron" in the game code

**Impact:** Agents/bots searching for `-s iron` won't find limonite, even though it's the iron ore they're looking for.

**Ore name mappings needed (non-exhaustive):**

| Player Term | Actual Block Code Pattern |
|-------------|---------------------------|
| iron ore | `ore-*-limonite-*`, `ore-*-magnetite-*`, `ore-*-hematite-*` |
| copper ore | `ore-*-malachite-*`, `ore-*-nativecopper-*` |
| tin ore | `ore-*-cassiterite-*` |
| gold ore | `ore-*-nativegold-*` |
| silver ore | `ore-*-nativesilver-*`, `ore-*-galena-*` |

**Future Work:** Consider adding a semantic mapping layer to the targets endpoint or CLI that translates common terms to their VS block codes. Options:
1. Server-side: Add `?alias=iron` parameter that expands to multiple ore types
2. Client-side: Add `--ore iron` flag to poliscli that searches multiple patterns
3. Documentation: Provide a reference table in TESTING_HARNESS_TARGETS.md

This is tracked as a future enhancement, not a bug in the current implementation.
