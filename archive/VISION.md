# Polis Builder Vision Document

**Last Updated:** 2026-01-19
**Status:** Living document - evolves with development

## Core Concept

**"Deity RTS with Possession"** - A Vintage Story mod blending:
- **Rimworld**: Colony management, job system, NPC autonomy
- **Populous**: God-game perspective, population growth, divine intervention
- **Settlers 2**: Resource chains, construction, worker assignment
- **Abe's Oddysee**: Possession mechanic - jump into NPCs for direct control

## The Core Loop

```
┌─────────────────────────────────────────────────────────────┐
│  DEITY VIEW (RTS Mode)                                      │
│  • Oversee multiple NPCs                                    │
│  • Issue high-level commands                                │
│  • Manage economy/building                                  │
│  ───────────────────────────────────────────────────────    │
│           ↓ POSSESS ↓              ↑ RELEASE ↑              │
│  ───────────────────────────────────────────────────────    │
│  EMBODIED VIEW (Action Mode)                                │
│  • Direct control of one NPC                                │
│  • Precise tasks (combat, crafting, exploration)            │
│  • "Do it yourself" when AI isn't good enough               │
└─────────────────────────────────────────────────────────────┘
```

**Key Insight:** Possession becomes powerful when there's autonomous behavior to fall back to. NPCs should be *doing things* when not possessed, so possession feels like "tactical intervention" rather than "mandatory micromanagement."

---

## Development Phases

### Phase 0: Foundation (✅ COMPLETE)
- [x] Bot spawning and selection
- [x] A* pathfinding with tall grass patch
- [x] Block interactions (activate, break, place)
- [x] Debug visualization (path highlights)
- [x] Bot persistence (Shadow Registry pattern)
- [x] Bot Manager GUI

### Phase 1: Possession System (✅ COMPLETE)
**Goal:** Player can "jump into" an NPC and control them directly

| Component | Description | Status |
|-----------|-------------|--------|
| `PolisPossessableBehavior` | IMountable implementation | **✅ Implemented** |
| `PolisPossessableSeat` | IMountableSeat at NPC eyes | **✅ Implemented** |
| Input routing | Controls property → NPC locomotion | **✅ Implemented** |
| Camera placement | LocalEyePos property | **✅ Implemented** |
| Player hiding | RenderTransform.Scale(0,0,0) | **✅ Implemented** |
| Client Smoothing | Render frame prediction | **✅ Implemented (Phase 1.5)** |

**Research:**
- `docs/research/phase-1/2026-01-04-vintage-story-mounting-analysis.md` ← **Key technical reference**
- `docs/research/phase-1/2026-01-02-possession-implementation-plan.md`
- `docs/research/phase-1/2026-01-04-ext-possession-mechanics-design.md`

### Phase 2: Task/Job System (📋 PLANNED)
**Goal:** NPCs execute queued tasks autonomously

#### Architecture: RimWorld-style Scanner/Executor Split

```
┌──────────────────────────────────────────────────────────────┐
│  WorkType (category)                                         │
│    └── WorkGiver (scanner) → "Is there work? Create Job"    │
│          └── Job (instance) → "Do X at target Y"            │
│                └── JobDriver (executor) → State machine     │
│                      └── Toils/Steps → Atomic actions       │
└──────────────────────────────────────────────────────────────┘
```

**Mapped to VS/Polis:**
- **WorkType** → Job category (Haul, Build, Harvest)
- **WorkGiver** → Scanner that finds valid work targets
- **Job** → `EntityActivity` with target + parameters
- **JobDriver** → Sequential `IEntityAction` list
- **Toils** → Individual actions (GotoAction, ActivateBlockAction, etc.)

#### Critical Systems (from research)

| System | Purpose | Priority |
|--------|---------|----------|
| **Reservation Manager** | Prevent deadlocks - reserve targets/items before starting | Critical |
| **Task Queues** | Ready / Blocked / Claimed / Emergency lanes | Critical |
| **Scoring-based matching** | Distance + skill + urgency, not just FIFO | High |
| **Anti-thrash** | Cooldowns, commitment windows, cached best-job | High |
| **Aging priorities** | Old tasks get priority boost (prevent starvation) | Medium |
| **Tick throttling** | Stagger job-finding across NPCs | Medium |

#### Task Types (Initial Set)

| Task | Description | Actions Involved |
|------|-------------|------------------|
| Goto | Move to location | GotoAction |
| Harvest | Gather resource | Goto → Break → Collect |
| Haul | Move items A→B | Goto → Pickup → Goto → Drop |
| Build | Place block | Goto → (get materials) → Place |
| Craft | Use workstation | Goto → Activate (with args) |
| Idle | Wait/wander | Wait or random Goto |

**Research:**
- `docs/research/phase-2/2026-01-04-task-system-research.md`
- `docs/research/phase-2/2026-01-04-ext-rimworld-df-task-architecture.md`
- `docs/research/phase-2/2026-01-04-ext-colony-sim-implementations.md`

### Phase 3: Multi-Bot Commands (📋 PLANNED) — **Research Complete**
**Goal:** RTS-style control of multiple NPCs

| Feature | Priority | Description | Status |
|---------|----------|-------------|--------|
| Multi-select | Critical | Box select, shift-click | **Implementation ready** |
| Group commands | Critical | All selected → goto | Planned |
| Bot groups/squads | Medium | Save named selections | Planned |
| Minimap | Medium | Strategic overview | Planned |
| Rally points | Low | New bots spawn here | Planned |

**Technical Approach (from research):**
```csharp
// Selection box rendering:
EnumRenderStage.Ortho          → 2D overlay stage
IRenderAPI.Render2DTexture()   → Draw selection rectangle

// Entity picking:
RayTraceForSelection()         → Single entity under cursor
GetEntitiesAround()            → Candidates for box select
PerspectiveViewMat/ProjectionMat → World→screen projection

// Input handling:
IClientEventAPI.MouseDown/Move/Up → Drag state machine
```

**Research:** `docs/research/phase-3/2026-01-04-ext-multi-select-ui-rendering.md`

### Phase 4: Construction System (📋 PLANNED) — **Research Complete**
**Goal:** Blueprint-based building with NPC workers

| Feature | Priority | Description | Status |
|---------|----------|-------------|--------|
| Blueprint placement | Medium | Ghost blocks for planned structures | **Implementation ready** |
| Construction tasks | Medium | NPCs assigned to build | Planned |
| Material requirements | Medium | Need X stone, Y wood | Planned |
| Build priority | Low | Which blueprints first | Planned |

**Technical Approach (from research):**
```csharp
// Ghost block rendering:
EnumRenderStage.OIT              → Transparent rendering stage
PreparedStandardShader + ColorMul → Tinting (white=valid, red=invalid)
RenderMeshInstanced()            → Batch 100+ ghost blocks efficiently

// Architecture:
Client-side preview → Server-authoritative blueprint → NPC job list

// File format:
WorldEdit JSON compatible for ecosystem interop
```

**Reference mod:** `[Beta]Schematica` - exact feature we want (ghost blocks, color-coded states, layer mode)

**Research:** `docs/research/phase-4/2026-01-04-ext-blueprint-ghost-blocks.md`

### Phase 5+: Depth Layers (🔮 FUTURE) — **Design Validated**

#### Resource Economy (Settlers-style)
- Hauling tasks and storage zones
- Production chains (Ore → Ingot → Tool)
- Resource tracking UI

#### NPC Survival Needs — **Research Complete**
**Design Decision:** "Pantry system" - alive without babysitting

| Feature | Approach | Status |
|---------|----------|--------|
| Hunger | Attach `EntityBehaviorHunger`, NPCs eat from **village pantry** (not individual feeding) | **Pattern found** (vs-farmlife) |
| Temperature | Performance/mood modifier, not constant damage (vanilla only does cold, no heat stroke) | Design ready |
| Death | `reviveondeath` behavior → downed state first, respawn at TownCenter in 24-72h | **Vanilla pattern** |

**Reference mod:** `vs-farmlife` - livestock hunger + autonomous eating AI

**Research:** `docs/research/phase-5/2026-01-04-ext-npc-survival-integration.md`

#### NPC Personality (Rimworld-style)
- Skill levels (mining, combat, crafting)
- Mood and morale
- Social relationships

#### Population Growth (Populous-style)
- Recruitment/spawning mechanics
- Housing requirements
- Population caps

#### NPC Polish Features — **Research Complete**

| Feature | Approach | Research |
|---------|----------|----------|
| **Look-at targets** | Use `EntityPos.HeadYaw/Pitch` + `EntityHeadController` (built-in) | `ext-procedural-animation-lookat.md` |
| **Task indicators** | Pattern B: `IRenderer` + `Render2DTexture` (screen-space overlay) | `ext-inworld-task-visualization.md` |

Reference mods: Entity Emote Library (EEL), HealthBar, Simple Entity HealthBar

---

## Development & Agent Infrastructure

Beyond the in-game systems, the project includes tooling for development, testing, and LLM/agent integration.

### HTTP Test Harness

Server-side HTTP API (`localhost:8585`) for external control:
- Full command execution (all bot/player actions)
- State queries (bots, players, targets, world)
- Screenshot capture from player view
- Event streaming via WebSocket or polling

**Components:**
- `PolisTestHarness.cs` - HTTP/WebSocket server
- `scripts/poliscli.py` - CLI wrapper (40+ commands, TOON output for LLM efficiency)
- `scripts/vsctl.py` - Game lifecycle control (start/stop/restart)

### Web UI v2: Observation Platform

**Status:** Design complete, implementation planned

The web UI is evolving from a simple test panel into an **observation and analysis platform** for VS + LLM agent development.

**Three-Layer World View:**
```
┌─────────────────────────────────────────────────────────────┐
│  SCREENSHOT            │  STRUCTURED 3D VIEW               │
│  (pixel ground truth)  │  (same FOV, data-driven render)   │
├────────────────────────┴────────────────────────────────────┤
│  LLM TEXT VIEW                                              │
│  "You are at (102, 65, -200) facing north. Ahead: flat     │
│   grassland. Right: wooden chest (2m). Left: oak tree..."  │
└─────────────────────────────────────────────────────────────┘
```

**Key capabilities:**
- **Visual verification** - Screenshot + structured view side-by-side
- **LLM-friendly representation** - Text descriptions for agent consumption
- **Context-driven UI** - Actions shown based on selected entity
- **Agent integration** - WebSocket for LLM/agent command streaming
- **Historical analysis** - IndexedDB storage for replay/debugging

This enables treating VS as a "text adventure with ground truth" - the structured world model can be verified against actual game state, making it suitable for LLM agent training and testing.

**Design document:** `docs/design/webui-v2-design.md`

---

## Technical Architecture

### Current Components
```
PolisBuilderNpcSystem.cs           - Server: partial class — persistence, entity lifecycle
PolisBuilderNpcHotkeys.cs          - Client: hotkey bindings
PolisBuilderNpcHarmony.cs          - Harmony patches (tall grass A*)
PolisNetworkPackets.cs             - Protobuf packets, data structures
Gui/GuiDialogBotManager.cs        - Bot management UI

src/Actions/
├── Blocks/                        - Block interaction actions
├── Entities/PolisInteractEntityAction.cs - Entity interaction/attack
├── Harvesting/                    - Harvest actions
├── Inventory/                     - Pickup, drop, container transfer
├── Navigation/PolisGotoAction.cs  - A* and straight-line movement
└── Workstations/                  - Anvil, clay, grind, knap, press, barrel

src/Commands/PolisCommandRegistry.cs    - All /polis command registration
src/Core/PolisConstants.cs              - Shared constants
src/Core/PolisValidation.cs             - Validation helpers
src/Harness/PolisHarnessCommandHandlers.cs - HTTP API handlers (partial class)
src/Helpers/PolisAnimationHelpers.cs    - Animation utilities
src/Helpers/PolisInventoryHelpers.cs    - Bot inventory helpers
```

### Planned Components (Updated from Research)
```
# Phase 1: Possession
PolisPossessableBehavior.cs - IMountable + brain snapshot/restore
PolisPossessableSeat.cs     - Invisible seat at NPC eyes

# Phase 2: Task System
PolisJobDef.cs              - Data definition of job types
PolisJobDriver.cs           - State machine executor base
PolisWorkGiver.cs           - Scanner/selector base class
PolisReservationManager.cs  - Resource/target reservations
PolisJobTracker.cs          - Per-bot: current job + queue + cooldowns
PolisBlackboard.cs          - World shared + agent private knowledge

# Phase 3+
Gui/GuiDialogTaskAssign.cs  - Task assignment UI
Gui/GuiDialogWorkTab.cs     - Priority configuration (Rimworld-style)
Gui/GuiDialogOverview.cs    - Colony overview / minimap
```

### VS AI System Integration

VS has **two parallel AI systems** we can leverage:

| System | Used By | Our Use |
|--------|---------|---------|
| **AiTaskBase / taskai** | Animals, creatures | Could use for idle behaviors |
| **EntityActivitySystem** | Humanoid NPCs | **Primary** - action sequences |

**Decision:** Build on `EntityActivitySystem` for action execution, add our own `PolisJobTracker` layer for task management and RimWorld-style selection.

### Key Patterns

| Pattern | Description | Source |
|---------|-------------|--------|
| **Shadow Registry** | Persist data in world save, sync with entity lifecycle | vsvillage |
| **Scanner/Executor Split** | Separate "find work" from "do work" | RimWorld |
| **Reservation System** | TryReserve(pawn, target, purpose) before committing | RimWorld/DF |
| **Two-Phase Jobs** | Acquire all prereqs OR fail fast, then execute | Research |
| **Job Stack** | Push current job, run forced job, attempt resume | Research |
| **Body/Brain Separation** | Possession snapshots brain, drives body | Messiah/Abe's |

---

## Possession Design (from Research)

### Architecture: Body vs Brain Separation

```
┌─────────────────────────────────────────┐
│  BODY (always present)                  │
│  • Physics, animation state             │
│  • Inventory/equipment                  │
│  • Health/status effects                │
│  • Position, facing                     │
├─────────────────────────────────────────┤
│  BRAIN (swappable controller)           │
│  • Current job/task chain               │
│  • Blackboard/memory                    │
│  • Reservations (claimed resources)     │
│  • Path target, schedule                │
└─────────────────────────────────────────┘
```

### Possession Flow

1. **On Possess:**
   - Snapshot brain state into "suspend token"
   - Release reservations that would block others
   - Swap controller: AI stops, player drives body
   - Optional: push current job onto stack

2. **While Possessed:**
   - Player inputs route to NPC locomotion
   - NPC uses their own capabilities (not player's)
   - Body state (inventory, health) is live

3. **On Release:**
   - Enter "reentry state" (1-5 seconds)
   - Re-validate: Is old job still valid? Target reachable?
   - If valid → resume, else → replan
   - Optional: confusion/reorientation animation

### Capability Philosophy

**Chosen: Same capabilities, better precision**
- Player can do what AI can do, just more accurately
- Balance via cost/risk (Abe's body vulnerability, cooldowns)
- Avoids exploit concerns of "player kit" approach

---

## Anti-Pattern Avoidance (from Research)

### Deadlocks
**Problem:** A waits for resource held by B, B waits for A

**Solutions:**
- Reservation system with lock ordering (acquire by entity ID)
- Two-phase jobs: acquire all OR fail fast
- Timeout and backoff on reservation failure

### Starvation
**Problem:** Some tasks never get done

**Solutions:**
- Aging priorities (old tasks get boosted)
- Quotas ("do max N hauls before considering other work")
- Role caps (reserve some NPCs for critical work)

### Pathfinding Spam
**Problem:** Constant rescans + repaths tank performance

**Solutions:**
- Tick throttling (job-find every K ticks, staggered per NPC)
- Cache candidate lists, invalidate on world events
- Path probes as budgeted resource (cheap filters first)
- **Token bucket:** max 2-5 path requests per tick globally

---

## Performance Architecture (from Research)

**Target:** 50 NPCs, <2ms AI per frame, 60 FPS

### VS Tick Rate Reality
- VS runs at **~30 ticks/sec** (not 60)
- Budget: 2ms/frame × 60fps = 120ms/sec ÷ 50 NPCs = **2.4ms/sec per NPC**

### Multi-Rate Brain Architecture

| Frequency | Operations | Cost |
|-----------|------------|------|
| **30 Hz** | Locomotion, path following, stuck detection | Tiny (O(1)) |
| **5-10 Hz** | Task execution, local perception, reservation heartbeat | Low |
| **0.5-2 Hz** | Job selection, replanning, path requests | High |
| **Event-driven** | Job available, reservation failed, path invalidated | Best |

### Central Scheduler Pattern
```
Each tick:
  1. Budget = 1.5ms
  2. Process queues: perception → job assignment → pathfinding → audit
  3. Stop when budget exhausted, defer remainder
  4. Use per-NPC hash offset to stagger expensive work (avoid thundering herd)
```

### Networking Constraints
- Server-authoritative, clients interpolate
- **UDP packets ≤508 bytes** (VS hard constraint for NAT traversal)
- Batch state deltas, separate realtime (position) from eventual (job assignment)

**Research:** `docs/research/phase-2/2026-01-04-ext-performance-budgets.md`

---

## Design Principles

1. **Possession is the differentiator** - Make it feel powerful and seamless
2. **Autonomy enables possession** - NPCs must do things on their own
3. **Scanner/Executor split** - Separate "find work" from "do work"
4. **Reservations are first-class** - Prevent deadlocks from day one
5. **Iterate visibly** - Debug visualization helps development
6. **Build on VS patterns** - Use EntityActivitySystem, not fight it
7. **Server authoritative** - All game logic server-side, client renders

---

## Reference Games (Design Inspiration)

| Game | What to Learn |
|------|---------------|
| Rimworld | WorkType/WorkGiver/Job split, priority system, Work Tab UI |
| Dwarf Fortress | Global job pool + labor gating, DFHack labormanager for balance |
| Settlers 2 | Resource chains, road networks, specialized workers |
| Abe's Oddysee | Possession feel, body vulnerability, host destruction on release |
| Messiah | Body/brain separation, AI coping with displacement |
| Dishonored | Possession cost/balance, capability constraints |
| Oxygen Not Included | Task queues, errands, duplicant AI |

---

## Open Questions (Updated)

### Possession
- [ ] Duration/stamina limits on possession?
- [ ] Cost to possess (mana, cooldown, risk)?
- [ ] What happens if possessed NPC dies?
- [ ] Should some NPCs be un-possessable?

### Task System
- [ ] RimWorld-style Work Tab, or simpler per-bot priorities?
- [ ] How to visualize task queues in-world?
- [ ] Workstation/POI system like vsvillage?

### Multiplayer
- [ ] Who can possess which NPCs? (ownership)
- [ ] Shared task queues or per-player colonies?
- [ ] Conflict resolution for reservations?

### Integration
- [ ] Hook into vanilla VS needs (hunger, temperature)?
- [ ] Use vanilla crops/crafting or custom?

---

## Research Documents Index

### Internal (btca-based)
| File | Topic |
|------|-------|
| `2026-01-04-vintage-story-mounting-analysis.md` | **IMountable/IMountableSeat API** (key for possession) |
| `2026-01-04-task-system-research.md` | VS EntityActivitySystem deep dive |
| `2026-01-03-bot-tracking-analysis.md` | Shadow Registry pattern (vsvillage) |
| `2026-01-02-possession-implementation-plan.md` | IMountable approach |

### External (deep research)
| File | Topic |
|------|-------|
| `2026-01-04-ext-rimworld-df-task-architecture.md` | RimWorld/DF job systems |
| `2026-01-04-ext-possession-mechanics-design.md` | Abe's, Messiah, Dishonored patterns |
| `2026-01-04-ext-vintage-story-ai-systems.md` | VS taskai, activity system, mods |
| `2026-01-04-ext-colony-sim-implementations.md` | Open source references, ECS, patterns |
| `2026-01-04-ext-multi-select-ui-rendering.md` | **RTS box selection** (implementation ready) |
| `2026-01-04-ext-blueprint-ghost-blocks.md` | **Ghost blocks, Schematica** (implementation ready) |
| `2026-01-04-ext-npc-survival-integration.md` | Hunger, temperature, death handling |
| `2026-01-04-ext-performance-budgets.md` | **Multi-rate architecture, budgets** |
| `2026-01-04-ext-procedural-animation-lookat.md` | HeadYaw/Pitch, EntityHeadController |
| `2026-01-04-ext-inworld-task-visualization.md` | Task indicators, overlays |

### Legacy
| File | Topic |
|------|-------|
| `2026-01-02-tall-grass-pathfinding.md` | Harmony patch research |
| `2026-01-02-path-line-renderer.md` | Client-side line rendering |
| `2026-01-02-waypoints-traverser-surface.md` | Path extraction |

---

## Related Documents

- `TECHNICAL.md` - Implementation details
- `ROADMAP.md` - Immediate next steps
- `KNOWN_ISSUES.md` - Current bugs and limitations
- `design/webui-v2-design.md` - Web UI observation platform design
