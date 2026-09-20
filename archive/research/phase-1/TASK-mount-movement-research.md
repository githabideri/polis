# TASK: Mount vs Player Movement Research

**Agent Instruction Document**
**Date:** 2026-01-06
**For:** Parallel research agent
**Output:** `docs/journal/2026-01-06-mount-movement-findings.md`

---

## Context

**Project:** polis-builder-npc (Vintage Story mod for controllable NPCs)
**Phase:** Phase 1 - Possession System Polish
**Current Issue:** Possessed NPC moves like a horse/vehicle instead of bipedal player movement

### What We Know

1. **Possession works:** Player mounts NPC via `PolisPossessableSeat` → controls route to NPC
2. **Movement works:** NPC responds to WASD input and moves
3. **Movement FEELS WRONG:**
   - Too smooth (vehicular feel, not bipedal)
   - NPC tilts sideways when moving in curves (like riding a horse)
   - This suggests we're getting horse/mount movement physics instead of player physics

4. **Current implementation:** Uses `EntityControls.CalcMovementVectors()` in client prediction handler

### What We Need

Understand the difference between:
- **Player movement physics** (bipedal walking with acceleration/deceleration)
- **Mount/animal movement physics** (smooth, tilting, vehicular)

So we can either:
- Switch to player movement behavior
- Bypass mounting system for movement if needed

---

## Required Reading

Before starting, read these for context:

1. **Project structure:**
   - `ROADMAP.md` - We're in Phase 1 (Possession System)
   - `docs/TECHNICAL.md` - Section on possession mechanics and control routing

2. **Current implementation:**
   - `PolisPossessableSeat.cs` - Our seat implementation
   - `PolisClientPossessionHandler.cs` - Client-side prediction (uses CalcMovementVectors)
   - `PolisBuilderNpcSystem.cs:UpdatePossessions()` - Server-side control routing
   - `docs/research/phase-1/2026-01-06-phase-1_5-client-smoothing.md` - Recent work

3. **Key observation from logs:**
   ```
   [polis] Controls: F=False B=False L=False R=False
   [polis] WalkVec: X=-0.000 Z=-0.000
   ```
   CalcMovementVectors produces smooth WalkVectors - is this the issue?

---

## Research Questions

### Primary Question
**What is the difference between player movement physics and mount/animal movement physics in Vintage Story?**

Specifically:
- How does player movement work? (Acceleration curves, friction, animation-driven?)
- How does mount movement work? (Continuous motion, tilting behavior?)
- What causes the "smooth vehicular" feel vs "responsive bipedal" feel?

### Secondary Questions
- Does `EntityControls.CalcMovementVectors()` apply to both player and mounts the same way?
- Are there different movement modes or physics systems?
- How do player entities handle movement start/stop (the "discrete" feel)?
- What makes mounts tilt sideways in curves?

### Critical Question for Our Use Case
**Can we make a mounted entity move like a player instead of like a horse?**
- Is there a way to switch movement physics mode?
- Do we need to bypass mounting for movement control?
- Or is there a different API we should use?

---

## Tool Usage

### btca Command Syntax

```bash
btca ask -r <resource> -q "<your question>"
```

**Parameters:**
- `-r <resource>`: Which repo to search (see `docs/btca_usage.md` for full resource map)
- `-q "<question>"`: Your question in quotes (must be quoted!)
- **Important:** For complex queries, these may take 2-3 minutes to complete

**Recommended resources for this task:**
- Primary: `vsapi` (for movement physics and EntityControls)
- Secondary: `vssurvivalmod` (for player movement implementation)
- Alternative: `jaunt` (for mount/riding movement mechanics)

**Example:**
```bash
btca ask -r vsapi -q "How does EntityControls.CalcMovementVectors work?"
```

### Troubleshooting

**If btca takes too long or times out:**
- Complex queries can take 2-3 minutes - be patient
- Break very complex questions into smaller, focused queries
- Try a more specific resource (-r flag)

**If btca syntax error:**
- Check `docs/btca_usage.md` for correct syntax
- Ensure question is in quotes after `-q` flag
- Verify resource name is valid

---

## btca Queries to Run

Use the `btca` tool with these queries (copy/paste exactly):

### Query 1: Player Movement Mechanics
```bash
btca ask -r vssurvivalmod -q "How does player movement work in Vintage Story? I need to understand:
1. The physics/movement system for player entities (acceleration, deceleration, friction)
2. How player movement differs from entity movement
3. Whether players use EntityControls.CalcMovementVectors() or a different system
4. What gives player movement its responsive, discrete feel (vs smooth vehicular movement)
5. How movement start/stop is handled (does it use animation-driven movement?)

Context: Building NPC possession system where possessed NPC should move exactly like the player does, not like riding a horse.

Please provide code references, class names, and specific mechanisms."
```

### Query 2: Mount/Animal Movement Mechanics
```bash
btca ask -r jaunt -q "How does mount/rideable entity movement work in Vintage Story (e.g., horses)? I need to understand:
1. The movement physics for rideable entities
2. Why mounts have smooth, vehicular movement (vs bipedal player movement)
3. What causes the tilting behavior when turning in curves
4. How EntityBehaviorRideable controls mounted entity movement
5. The relationship between rider controls and mount motion

Context: NPC possession uses mounting system (IMountableSeat) but we're getting horse-like movement instead of player-like movement.

Please provide code references and examples from vanilla rideable entities."
```

### Query 3: EntityControls and Movement Vectors
```bash
btca ask -r vsapi -q "How does EntityControls.CalcMovementVectors() work in Vintage Story? I need to understand:
1. What this method does (how it calculates WalkVector from control inputs)
2. Whether it behaves differently for players vs other entities
3. Whether it produces continuous smooth motion or discrete movement
4. If there are alternative movement APIs for bipedal entities
5. How to achieve player-like movement instead of mount-like movement

Context: Using CalcMovementVectors in client prediction for possessed NPC, but getting smooth vehicular motion instead of responsive bipedal motion.

Please provide specific API details and alternatives."
```

### Query 4: Movement Modes/Systems
```bash
btca ask -r vsapi -q "Are there different movement modes or physics systems in Vintage Story for different entity types? Looking for:
1. Whether there's a 'player movement mode' vs 'mount movement mode'
2. How to switch or select movement behavior
3. Any flags, properties, or configurations that control movement physics
4. EntityBehavior classes that affect movement (besides BehaviorRideable)

Context: Need to make mounted NPC move like player, not like horse.

Please provide code references and configuration options."
```

---

## Deliverables

Create output file: `docs/journal/2026-01-06-mount-movement-findings.md`

### Required Format

```markdown
# Mount vs Player Movement Research Findings

**Date:** 2026-01-06
**Researcher:** [Your agent name]
**Task:** TASK-mount-movement-research.md

---

## Summary

[1-2 paragraph summary of key findings about the movement difference]

---

## btca Query 1: Player Movement Mechanics

### Query
[Paste the query you ran]

### Results
[Full btca output]

### Key Findings
- [How player movement works]
- [What makes it feel responsive/bipedal]
- [Code references]

---

## btca Query 2: Mount/Animal Movement Mechanics

### Query
[Paste the query you ran]

### Results
[Full btca output]

### Key Findings
- [How mount movement works]
- [Why it feels smooth/vehicular]
- [Tilting mechanism]

---

## btca Query 3: EntityControls and Movement Vectors

### Query
[Paste the query you ran]

### Results
[Full btca output]

### Key Findings
- [CalcMovementVectors behavior]
- [Alternatives]

---

## btca Query 4: Movement Modes/Systems

### Query
[Paste the query you ran]

### Results
[Full btca output]

### Key Findings
- [Different movement systems]
- [How to switch modes]

---

## Analysis

### Player Movement System
[Explain how player movement works mechanically]

### Mount Movement System
[Explain how mount movement works mechanically]

### Why They Feel Different
[Specific technical reasons for the feel difference]

### What Causes Our Issue
[Root cause of horse-like movement in possessed NPCs]

---

## Solutions

### Option 1: [Name of approach]
**Description:** [How to implement player-like movement]
**Pros:** [Benefits]
**Cons:** [Drawbacks]
**Feasibility:** [Can this actually work?]
**Implementation complexity:** [Low/Medium/High]

### Option 2: [Name of approach]
**Description:** [Alternative approach]
**Pros:** [Benefits]
**Cons:** [Drawbacks]
**Feasibility:** [Can this actually work?]
**Implementation complexity:** [Low/Medium/High]

### Option 3: [If applicable]
[Another approach]

### Recommended Approach
[Which option and detailed reasoning]

---

## Code References

[List of all relevant files, classes, methods discovered]

---

## Implementation Notes

[Specific guidance for whoever implements the solution]
- [What needs to change]
- [What to watch out for]
- [Testing strategy]

---

## Open Questions

[Any remaining unknowns that need further investigation]
```

---

## Success Criteria

Your research is complete when:
- ✅ All 4 btca queries executed and documented
- ✅ Clear understanding of player movement mechanics
- ✅ Clear understanding of mount movement mechanics
- ✅ Root cause of "horse-like" movement identified
- ✅ At least 2 concrete solutions proposed
- ✅ Recommendation made with detailed reasoning
- ✅ Output file follows format above

---

## Notes

- Use btca for all API/code research (primary source)
- Focus on MECHANICAL differences, not just code differences
- We need actionable solutions, not just analysis
- Mark any assumptions clearly
- If btca doesn't answer something, note it in "Open Questions"
- The goal is to make possessed NPCs move EXACTLY like the player would
