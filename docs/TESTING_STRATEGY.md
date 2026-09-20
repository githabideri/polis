# Testing Strategy

Long-term vision for deterministic, repeatable test runs.
Distinct from `TESTING_HARNESS.md` (which documents the existing HTTP/CLI infrastructure).

Tracked by: `polis-1so`

---

## Phase 1: Deterministic Test World + Regression Suite

### Test World

A flat (superflat) world with a single dirt layer. All test structures are pre-placed
at known coordinates. The world is saved and restored before each run, guaranteeing
identical starting conditions.

The layout is also stored as a blueprint (via scan/verify) in the repo, so the world
can be reconstructed from scratch if the save is lost.

**Crop/growth handling:** Mature crops are placed directly via `setblock` with the
final growth stage code (e.g., `crop-carrot-7`). No time manipulation needed.
Farmland must be placed underneath first (`farmland-moist-medium`).

### Layout

Road runs **north-south** (for unobstructed midday sun along the full length).
Two rows of 5x5 test pads flank the road — west row and east row.
Watchtower at center for oversight.

```
                          W ---- E

                    West Row          East Row
                   (6 pads)          (7 pads)

              N    .--------.   .-.   .--------.
              |    | Block  |   | |   | Knap   |
              |    |  Ops   |   | |   |        |
              |    '--------'   | |   '--------'
              |    .--------.   | |   .--------.
              |    | Activ- |   | |   | Grind  |
              |    |  ate   |   | |   |        |
              |    '--------'   | |   '--------'
              |    .--------.   | |   .--------.
              |    | Harv-  |   |R|   | Press  |
              |    |  est   |   |o|   |        |
              |    '--------'   |a|   '--------'
              |    .--------.   |d|   .--------.
              |    | Furn-  |   | |   | Seal   |
              |    |  ace   |   |5|   |        |
              |    '--------'   |w|   '--------'
              |    .--------.   |i|   .--------.
              |    | Smith- |   |d|   | Cont-  |
              |    |  ing   |   |e|   | ainer  |
              |    '--------'   | |   '--------'
              |    .--------.   | |   .--------.
              |    | Clay   |   |[T]  | Inv    |
              |    | Form   |   |[o]  | Drop   |
              |    '--------'   |[w]  '--------'
              |                 | |   .--------.
              S                 | |   | Entity |
                                | |   |  Pen   |
                                '-'   '--------'

              [Tow] = Watchtower (3x3 base, 5 high)
              Pad   = 5x5 each, 1-block gap between
              Road  = 5 blocks wide, runs full N-S length
              Total = ~17 W-E  x  ~50 N-S
```

### World Creation

VS has a built-in "superflat" preset. Configure via `serverconfig.json`:

```json
"WorldConfig": {
  "WorldName": "polis-test-flat",
  "WorldType": "superflat",
  "PlayStyle": "creativebuilding",
  "AllowCreativeMode": true
}
```

Delete existing save files and restart server for changes to take effect.

**Note:** Default superflat is only 2-3 blocks deep. For underground testing, install
the "More Creative World Layers" mod which adds 32 layers.

### Structure Building

**Method 1: WorldEdit (built-in)**
- Press `~` in creative mode to open WorldEdit GUI
- `/we ms` / `/we me` — mark start/end of selection
- `/we mfill` — fill selection with block in hotbar
- `/we export filename` — save schematic to `%APPDATA%/VintagestoryData/WorldEdit/`
- `/we imp filename` — import schematic at player position

**Method 2: Harness setblock**
```bash
./scripts/poliscli.py setblock cobblestone-granite 100 64 100
```

**Method 3: Blueprint build** (for scripted placement)
```bash
./scripts/poliscli.py build blueprint.json --origin 100 64 100
```

### Mature Crop Codes

Place mature crops directly — no time manipulation needed:

| Crop | Max Stage | Block Code |
|------|-----------|------------|
| Carrot | 7 | `crop-carrot-7` |
| Flax | 9 | `crop-flax-9` |
| Onion | 7 | `crop-onion-7` |
| Turnip | 5 | `crop-turnip-5` |
| Spelt | 9 | `crop-spelt-9` |
| Rye | 9 | `crop-rye-9` |
| Rice | 10 | `crop-rice-10` |

**Example:**
```bash
./scripts/poliscli.py setblock farmland-moist-medium 100 63 100
./scripts/poliscli.py setblock crop-carrot-7 100 64 100
```

### Scan/Verify Limitations

The `polis scan` and `polis verify` commands capture block codes only:

| Captured | NOT Captured |
|----------|--------------|
| Block positions | Block rotations/orientations |
| Block codes | Container contents |
| | Block entity state (fuel, progress) |
| | Entity positions |

**Workaround:** Use a setup script that:
1. `polis build` — places structure from blueprint
2. `putinto` — populates containers
3. `activate` — sets up mechanisms (light firepits, etc.)
4. `spawnentity` — spawns test creatures in pens

### Test World Artifacts

Store in `tests/world/`:
- `polis-test-flat.blueprint.json` — structure scan (block codes only)
- `setup-stations.sh` — script for container/entity/state setup
- `README.md` — coordinate reference and station descriptions

The world save itself is large (~50MB+) and should be gitignored with a download link
or generated from blueprint + setup script.

### Test Stations (13)

| # | Row | Station | Actions Tested | Pre-placed |
|---|-----|---------|---------------|------------|
| 1 | W | Block Ops | place, mine, break | Stone, ore, air slots |
| 2 | W | Activation | activate, ignite | Door, chest, fueled firepit |
| 3 | W | Harvest | harvest block/crop | Ripe berry bush, mature crop on farmland |
| 4 | W | Furnace | forge heat | Firepit + fuel + ingot |
| 5 | W | Smithing | anvil smith | Anvil |
| 6 | W | Clay Form | clayform | Clay stacks |
| 7 | E | Knapping | knap | Stone surface, flint |
| 8 | E | Grinding | grind | Quern + grain |
| 9 | E | Pressing | press | Fruit press + mash + bucket |
| 10 | E | Fermentation | seal barrel | Barrel w/ sealing recipe contents |
| 11 | E | Containers | put, take | Pre-loaded chest |
| 12 | E | Inventory | drop, pickup | Open ground |
| 13 | E | Entity Pen | interact, butcher | 2-deep pit w/ animals |

**Design notes:**
- Entity pen uses a 2-block-deep pit (no fence pathfinding issues).
- Smithing tested both in isolation (pre-give hot ingot) and as chain (furnace -> smith).
- Navigation (goto) is implicitly tested as bot moves between stations.

### Zones

Each test pad is a named **zone** — an axis-aligned bounding box (AABB) that defines
the valid area for a given test. This is foundational infrastructure, not just a test
convenience.

**Implementation:** A `PolisZoneRegistry` holding `Dictionary<string, Cuboidi>` entries,
persisted via `PolisGlobalData`. Uses VS's built-in `Cuboidi.Contains(BlockPos)` for
membership checks. Lightweight (~50 lines), no dependency on the VS room system or
land claims.

**Zone visualization:** Zones can be highlighted in-game for ~4 seconds:
```bash
./scripts/poliscli.py zone-define station-blockops 100 63 200 105 68 205
./scripts/poliscli.py zone-show station-blockops  # re-show existing zone
```

**Why not VS rooms?** Rooms are auto-detected from physical enclosure — can't be defined
programmatically. Not useful for open-air test pads or arbitrary named areas.

**Why not land claims?** Ownership/permission semantics we don't need. The zone registry
is simpler and purpose-built.

**During test runs, zones enable:**
- Logging when bot leaves the expected zone ("bot exited zone: block-ops")
- Validating that actions happen within the correct station area
- Detecting spatial confusion (bot pathfinds to wrong station)

**Future mod-level uses (not implemented now, but the architecture supports):**
- Per-occupation area constraints ("smiths stay in smithy during work")
- Time-of-day rules ("all bots indoors at night")
- Task cancellation triggers ("bot left work zone -> pause task")
- The zone concept maps directly to RimWorld-style "allowed areas"

### Test Manifest

JSON file defining setup and expectations per station:

```json
{
  "station": "block-ops",
  "zone": "test-block-ops",
  "setup": {
    "botPosition": [100, 71, 200],
    "camera": {"position": [102, 73, 198], "yaw": 1.57, "pitch": 0.3},
    "giveItems": ["game:pickaxe-copper"]
  },
  "steps": [
    {
      "action": "mine",
      "args": {"x": 101, "y": 71, "z": 201},
      "expect": {"blockGone": true, "inventoryContains": "game:stone-granite"}
    },
    {
      "action": "place",
      "args": {"blockCode": "game:cobblestone", "x": 101, "y": 71, "z": 201},
      "expect": {"blockPresent": "game:cobblestone"}
    }
  ],
  "zoneViolation": "fail"
}
```

The `zoneViolation` field controls behavior when the bot leaves the station zone
during a test sequence: `"fail"` (abort test), `"warn"` (log and continue),
or `"ignore"`.

### Script Runner

Extends `scripts/polis-http-smoke.py` into a full regression suite:

1. Restore saved world (reset to known state)
2. For each station in manifest:
   - Spawn/teleport bot to station
   - Set camera position for screenshots
   - Execute action steps
   - Verify outcomes (block state, inventory, entity state)
   - Check zone compliance
3. On failure: screenshot + expected vs actual + zone log
4. Final report: pass/fail per station, zone violations, total coverage

An agent (large model) oversees the run, interprets failures, and can
flag flaky vs real regressions. The scripted steps themselves are deterministic;
the agent layer handles interpretation and reporting.

---

## Phase 2: Agent-Evaluated Testing (Future)

This section documents ideas. Do not implement until Phase 1 is solid.

### Teacher-Student Model

A large model oversees test runs conducted by a smaller model.

**Two modes:**

1. **Capability evaluation (post-hoc, preferred):** Small model runs a task
   (e.g., "smelt an iron ingot given raw materials and a forge"). Full action
   log is recorded. Large model analyzes the log afterward and produces a
   structured capability report.

2. **Coaching (real-time):** Large model watches the event stream during a
   small model's run and can inject hints via the harness. Use sparingly —
   the feedback loop makes runs harder to reproduce.

Post-hoc is strongly preferred. Recorded logs can be re-analyzed with different
prompts, compared across model versions, and don't have the reproducibility
problem of real-time intervention.

### Zone Awareness for Agents

In agent-evaluated runs, zone violations become **immediate feedback**:
- Bot leaves expected zone -> agent is notified in real time
- Agent can decide: re-navigate, abort, or investigate
- Zone awareness serves as spatial guardrails for less capable models

This is the same `PolisZoneRegistry` from Phase 1, now surfaced through
the WebSocket event stream as zone entry/exit events.

### Standardized Capability Reports

```json
{
  "task": "smelt-iron-ingot",
  "model": "haiku-3",
  "result": "partial",
  "steps_completed": 4,
  "steps_total": 7,
  "failure_point": "Failed to identify correct fuel slot in firepit",
  "category": "spatial-reasoning",
  "zone_violations": 1,
  "suggestion": "Add explicit slot numbering to poliscli output",
  "action_log": "path/to/full-log.jsonl"
}
```

These feed back into prompt improvements, tooling changes, and documentation
of model capability boundaries across versions.
