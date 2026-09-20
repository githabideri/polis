# TASK: NPC Physics & Behavior Investigation

**Agent Instruction Document**
**Date:** 2026-01-06
**For:** Parallel research agent
**Output:** `docs/journal/2026-01-06-npc-physics-investigation.md`

---

## Context

**Project:** polis-builder-npc (Vintage Story mod for controllable NPCs)
**Phase:** Phase 1 - Possession System Polish
**Current Issue:** Possessed NPC moves like horse (smooth, tilting) instead of player (responsive, bipedal)

### What We Know

1. **Movement architecture identified:**
   - Server: `UpdatePossessions()` sets `npcControls.WalkVector` via `CalcMovementVectors()` but doesn't apply motion directly
   - Client: `PredictNpcMovement()` directly sets `possessedNpc.Pos.Motion` to WalkVector (WRONG - bypasses physics)

2. **Research findings (from mount-movement-findings.md):**
   - Player movement: WalkVector consumed by physics modules (`PModuleOnGround`, etc.) with drag/acceleration
   - Mount movement: Gait-based with smoothing and angular velocity
   - `CalcMovementVectors()` just computes input vector - feel comes from downstream physics

3. **Root cause hypothesis:**
   - NPC is using mount/rideable physics instead of player physics modules
   - OR client prediction bypassing physics is creating the smooth feel
   - Need to identify what behaviors/physics the NPC actually has

### What We Need

Investigate the NPC entity's actual behaviors and physics pipeline to determine:
- Which physics behaviors are active
- What's consuming WalkVector server-side
- Whether we can invoke player physics modules
- Whether rideable behaviors are interfering

---

## Required Reading

Before starting, read these for context:

1. **Current analysis:**
   - `docs/research/phase-1/2026-01-06-phase-1-polish-findings.md` - Full analysis of both issues

2. **Current implementation:**
   - `PolisBuilderNpcSystem.cs` (lines 377-431) - `UpdatePossessions()` method
   - `PolisClientPossessionHandler.cs` (lines 85-122) - `PredictNpcMovement()` method
   - `PolisPossessableSeat.cs` - Seat implementation

3. **Research background:**
   - `docs/journal/2026-01-06-mount-movement-findings.md` - Player vs mount physics research

---

## Research Questions

### Primary Questions

**Q1: What entity behaviors does the NPC have?**
- What is the NPC entity type/class being used?
- What behaviors are registered on `npc.SidedProperties.Behaviors`?
- Specifically: Is there `EntityBehaviorRideable`, `EntityBehaviorPassivePhysics`, or player physics modules?

**Q2: What consumes WalkVector server-side?**
- `UpdatePossessions()` only sets `npcControls.WalkVector` but doesn't apply motion
- What behavior/system actually reads WalkVector and updates `ServerPos.Motion`?
- Is it automatic (engine tick) or explicit (behavior tick)?

**Q3: Is rideable behavior active during mounting?**
- Does mounting automatically activate `EntityBehaviorRideable`?
- Is there a `SeatsToMotion` call happening that we're not controlling?
- Can we detect/disable rideable movement during possession?

**Q4: Can we access/invoke NPC physics modules?**
- Is there a public API to invoke physics modules directly?
- Can we programmatically add player physics modules to NPC?
- Or must we reimplement physics manually?

### Secondary Questions

- What's the NPC entity's collision box and eye height configuration?
- Does the NPC have walk speed multipliers or stats affecting movement?
- Are there any animation-driven movement hooks?

---

## Investigation Method

This is a **code investigation task** - you will read source files and add diagnostic code, but NOT implement the fix. The goal is to gather information for decision-making.

### Approach

1. **Read source code** to understand NPC entity structure
2. **Search for entity types** used for NPCs in this mod
3. **Add diagnostic logging** to reveal runtime behavior/physics state
4. **Run in-game test** (or simulate based on code analysis if testing not available)
5. **Document findings** with evidence (code references, log output)

---

## Investigation Steps

### Step 1: Identify NPC Entity Type

**Files to examine:**
- Search for entity spawning/creation code in the mod
- Look for `EntityAgent`, `EntityHumanoid`, or custom entity classes
- Find where NPCs are instantiated

**What to find:**
- Entity class name
- Entity type code (string identifier)
- Entity properties file reference (if JSON-defined)

**Diagnostic code to add:**
```csharp
// In PolisBuilderNpcSystem.cs:UpdatePossessions() around line 388
// After: var npc = seat.Entity as EntityAgent;

sapi.Logger.Notification($"[polis-diag] NPC Entity Type: {npc?.GetType().FullName}");
sapi.Logger.Notification($"[polis-diag] NPC Code: {npc?.Code}");
sapi.Logger.Notification($"[polis-diag] NPC Properties.Code: {npc?.Properties?.Code}");
```

### Step 2: List Entity Behaviors

**What to find:**
- All behaviors attached to NPC entity
- Specifically look for physics-related behaviors

**Diagnostic code to add:**
```csharp
// In UpdatePossessions() after Step 1 diagnostics

if (npc?.SidedProperties?.Behaviors != null)
{
    sapi.Logger.Notification("[polis-diag] NPC Behaviors:");
    foreach (var behavior in npc.SidedProperties.Behaviors)
    {
        sapi.Logger.Notification($"  - {behavior.GetType().FullName}");
    }
}

// Check for specific behaviors
var rideableBehavior = npc?.GetBehavior<EntityBehaviorRideable>();
sapi.Logger.Notification($"[polis-diag] Has EntityBehaviorRideable: {rideableBehavior != null}");

// Try to get physics behavior (may need to try different names)
var physicsBehavior = npc?.GetBehavior("passivephysics");
sapi.Logger.Notification($"[polis-diag] Has PassivePhysics: {physicsBehavior != null}");
```

### Step 3: Trace WalkVector Consumption

**What to find:**
- What code path consumes `npcControls.WalkVector`
- When/where does `ServerPos.Motion` get updated

**Diagnostic code to add:**
```csharp
// In UpdatePossessions() after CalcMovementVectors call (around line 424)

// Log before and after any motion updates
sapi.Logger.Notification($"[polis-diag] Before: Motion=({npc.ServerPos.Motion.X:F3},{npc.ServerPos.Motion.Z:F3})");
sapi.Logger.Notification($"[polis-diag] WalkVector=({npcControls.WalkVector.X:F3},{npcControls.WalkVector.Z:F3})");

// Check if Motion changes during this tick
// (Motion update might happen in entity tick, not in UpdatePossessions)
```

**Additional investigation:**
- Search for where `Entity.ServerControls.WalkVector` is read in VS API
- Check if `EntityAgent` has an automatic physics tick that consumes WalkVector
- Look for `entity.OnGameTick()` or similar methods

### Step 4: Check Mount Angle Mode

**What to find:**
- Whether seat's `AngleMode` prevents mount rotation
- Whether mount behaviors override this

**Code reference:**
```csharp
// In PolisPossessableSeat.cs line 126
public EnumMountAngleMode AngleMode => EnumMountAngleMode.Unaffected;
```

**Verification:**
- Check if this is being respected during possession
- Log actual yaw changes during movement

**Diagnostic code:**
```csharp
// In UpdatePossessions() track yaw changes
double prevYaw = npc.ServerPos.Yaw;
// [after any motion/behavior updates]
double yawDelta = npc.ServerPos.Yaw - prevYaw;
if (Math.Abs(yawDelta) > 0.001)
{
    sapi.Logger.Notification($"[polis-diag] NPC Yaw changed by {yawDelta:F3} (automatic?)");
}
```

### Step 5: Check for Gait/Seat Motion

**What to find:**
- Whether mount's `SeatsToMotion` is being called
- Whether gait system is active

**Investigation:**
- Search for `SeatsToMotion` calls in codebase
- Check if `PolisPossessableSeat` needs to implement motion control
- Look at `IMountable` interface requirements

---

## Deliverables

Create output file: `docs/journal/2026-01-06-npc-physics-investigation.md`

### Required Format

```markdown
# NPC Physics & Behavior Investigation

**Date:** 2026-01-06
**Researcher:** [Your agent name]
**Task:** TASK-npc-physics-investigation.md

---

## Summary

[1-2 paragraph summary of key discoveries about NPC physics pipeline]

---

## Investigation Step 1: NPC Entity Type

### Findings
- **Entity Class:** [Full class name]
- **Entity Code:** [Type identifier string]
- **Entity Properties:** [Reference to JSON or code definition]

### Evidence
[Code references, file locations]

---

## Investigation Step 2: Entity Behaviors

### Findings
- **All Behaviors:** [Complete list with full type names]
- **Physics Behaviors:** [Which ones relate to movement/physics]
- **Rideable Behavior:** [Present? Active?]

### Evidence
[Code references, behavior class locations]

### Analysis
[What these behaviors suggest about movement pipeline]

---

## Investigation Step 3: WalkVector Consumption

### Findings
- **Where WalkVector is read:** [Code path]
- **Where Motion is updated:** [Code path]
- **Automatic vs Explicit:** [Engine tick or behavior tick?]

### Evidence
[Code references, tick order]

### Analysis
[How WalkVector becomes Motion]

---

## Investigation Step 4: Mount Angle Mode

### Findings
- **Angle Mode Setting:** [Value from PolisPossessableSeat]
- **Is it respected?:** [Yes/No with evidence]
- **Yaw behavior:** [Does NPC yaw change automatically?]

### Evidence
[Log output or code analysis]

---

## Investigation Step 5: Gait/Seat Motion

### Findings
- **SeatsToMotion calls:** [Found? Where?]
- **Gait system active:** [Yes/No]
- **Mount motion override:** [Is mount controlling motion?]

### Evidence
[Code references]

---

## Conclusions

### Physics Pipeline Identified
[Describe the complete flow from controls to motion]

### Root Cause Confirmed/Refined
[Based on evidence, what's causing horse-like movement?]

### Player Physics vs NPC Physics
[Specific differences found]

---

## Recommendations

### Option A: Manual Physics Implementation
**Description:** Reimplement player physics modules in UpdatePossessions
**Feasibility:** [Based on findings]
**Complexity:** [Estimated]
**Reasoning:** [Why this approach fits the evidence]

### Option B: Use NPC Physics Modules
**Description:** Invoke existing NPC physics directly
**Feasibility:** [Based on findings]
**Complexity:** [Estimated]
**Reasoning:** [Why this approach fits the evidence]

### Option C: Disable Mount Physics
**Description:** Prevent rideable/mount behaviors from interfering
**Feasibility:** [Based on findings]
**Complexity:** [Estimated]
**Reasoning:** [Why this approach fits the evidence]

### Recommended Approach
[Which option, why, and specific implementation guidance]

---

## Code References

**Files examined:**
- [List all files analyzed]

**Key code locations:**
- [Entity type definition: file:line]
- [Behavior registration: file:line]
- [Physics tick: file:line]
- [Motion update: file:line]

---

## Diagnostic Code Added

[Paste the complete diagnostic code snippets added for testing]

---

## Testing Notes

[If in-game testing was performed, describe:
- How to reproduce
- What to look for in logs
- Expected vs actual behavior]

---

## Open Questions

[Any remaining unknowns that need further investigation]
```

---

## Success Criteria

Your investigation is complete when:
- ✅ NPC entity type identified with full class name and properties
- ✅ All entity behaviors listed and analyzed
- ✅ WalkVector consumption path traced
- ✅ Clear understanding of what's updating ServerPos.Motion
- ✅ Rideable behavior status confirmed (present/active/dormant)
- ✅ Physics pipeline documented from controls → motion
- ✅ Concrete recommendation made for implementation approach
- ✅ Diagnostic code provided for runtime testing
- ✅ Output file follows format above

---

## Notes

- **Primary focus:** INVESTIGATE, don't implement the fix yet
- **Be thorough:** Document all findings with evidence (code references, file:line)
- **If testing not available:** Analyze code paths and make reasoned deductions
- **Mark assumptions:** Clearly distinguish found evidence from assumptions
- **Provide diagnostic code:** Ready-to-use logging code for runtime verification
- **Think like a debugger:** What would you need to log to understand the behavior?

---

## Important Context

From the findings document (2026-01-06-phase-1-polish-findings.md):

**Client-side problem identified:**
```csharp
// PolisClientPossessionHandler.cs:118
possessedNpc.Pos.Motion.Set(predictControls.WalkVector);
```
This directly sets Motion to WalkVector, bypassing ALL physics modules. This alone could cause smooth continuous motion.

**Server-side unknown:**
```csharp
// PolisBuilderNpcSystem.cs:424
npcControls.CalcMovementVectors(npc.ServerPos, dt);
// [What happens next? Something must consume WalkVector...]
```

**Key insight from research:**
Player physics modules (PModuleOnGround) apply drag and acceleration to WalkVector:
```csharp
motionDeltaX += (walkX - motionDeltaX) * belowBlockDragMultiplier;
motion.X *= groundDrag;
```

This acceleration/drag is what makes player movement feel responsive. If NPC doesn't have these modules, or they're not being invoked, we'll get smooth motion instead.

**Your mission:** Find out what's actually happening to the NPC's WalkVector and Motion.
