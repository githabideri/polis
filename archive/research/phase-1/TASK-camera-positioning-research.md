# TASK: Player Camera Positioning Research

**Agent Instruction Document**
**Date:** 2026-01-06
**For:** Parallel research agent
**Output:** `docs/journal/2026-01-06-camera-positioning-findings.md`

---

## Context

**Project:** polis-builder-npc (Vintage Story mod for controllable NPCs)
**Phase:** Phase 1 - Possession System Polish
**Current Issue:** First-person camera positioned INSIDE NPC head (see face from inside)

### What We Know

1. **Possession works:** Player can mount NPC via `PolisPossessableSeat` (IMountable implementation)
2. **Camera height OK:** Not in torso, roughly at head level
3. **Camera position WRONG:** Centered inside head geometry instead of at eye position
4. **Third-person works:** F5 view doesn't have this issue (expected - different camera mode)

### What We Need

Understand how Vintage Story positions first-person camera for player entities, so we can:
- Either copy that exact pattern for possessed NPCs
- Or find alternative route if direct copy doesn't work

---

## Required Reading

Before starting, read these for context:

1. **Project structure:**
   - `ROADMAP.md` - We're in Phase 1 (Possession System)
   - `docs/TECHNICAL.md` - Section on possession mechanics

2. **Current implementation:**
   - `PolisPossessableSeat.cs` - Our seat implementation (IMountableSeat)
   - `docs/research/phase-1/2026-01-06-phase-1_5-client-smoothing.md` - Recent work on client prediction

3. **Reference repos:**
   - `../vsapi` - VS API source (for btca searches)
   - `../vsessentialsmod` - VS Essentials mod source
   - `../vssurvivalmod` - VS Survival mod source

---

## Research Questions

### Primary Question
**How does Vintage Story position the first-person camera for player entities?**

Specifically:
- What is the camera attachment point? (Entity.Pos? Head offset?)
- Is there an eye-level offset calculation?
- How is first-person camera different from third-person?
- Is camera position different when mounted vs unmounted?

### Secondary Questions
- How do mounts (horses) position the rider camera?
- Is there a standard pattern for "eye position" calculation?
- Are there any camera positioning utilities/helpers in the API?

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
- Primary: `vsapi` (for API behavior and camera positioning)
- Secondary: `vssurvivalmod` (for vanilla usage examples)
- Alternative: `jaunt` (for mount/riding camera mechanics)

**Example:**
```bash
btca ask -r vsapi -q "How does entity camera positioning work?"
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

### Query 1: Player Camera Positioning
```bash
btca ask -r vsapi -q "In the Vintage Story API and game code, how is the first-person camera positioned for player entities? I need to understand:
1. The exact attachment point (entity position, head offset, eye position)
2. Any offset calculations used for first-person view
3. How camera positioning differs between first-person and third-person
4. Any relevant classes, methods, or properties that control camera position

Context: Building a mod where player can possess NPC entities (via mounting), and need the camera positioned correctly at NPC eye level for first-person view. Currently camera is centered inside head geometry.

Please provide specific code references, class names, and method signatures."
```

### Query 2: Mount Camera Positioning
```bash
btca ask -r jaunt -q "In Vintage Story, how is the rider camera positioned when mounted on an entity (like a horse)? I need to understand:
1. How IMountableSeat controls camera position
2. The calculation for rider eye position on mounted entities
3. Any differences between first-person and third-person camera when mounted
4. Relevant properties or methods in IMountableSeat/IMountable

Context: Implementing NPC possession via mounting system, need to understand how mounts position rider camera.

Please provide code references and examples from vanilla rideable entities."
```

### Query 3: Camera Utilities
```bash
btca ask -r vsapi -q "Are there any camera positioning utilities, helpers, or standard patterns in the Vintage Story API for calculating eye-level or view position for entities? Looking for:
1. Standard offset calculations for entity eye position
2. Any EntityPos properties related to camera/view
3. Helpers for first-person view positioning
4. How different entity types (player, humanoid, animal) handle camera attachment

Please provide specific API references."
```

---

## Deliverables

Create output file: `docs/journal/2026-01-06-camera-positioning-findings.md`

### Required Format

```markdown
# Camera Positioning Research Findings

**Date:** 2026-01-06
**Researcher:** [Your agent name]
**Task:** TASK-camera-positioning-research.md

---

## Summary

[1-2 paragraph summary of key findings]

---

## btca Query 1: Player Camera Positioning

### Query
[Paste the query you ran]

### Results
[Full btca output]

### Key Findings
- [Bullet points of important discoveries]
- [Class names, method signatures]
- [Code patterns identified]

---

## btca Query 2: Mount Camera Positioning

### Query
[Paste the query you ran]

### Results
[Full btca output]

### Key Findings
- [Bullet points]

---

## btca Query 3: Camera Utilities

### Query
[Paste the query you ran]

### Results
[Full btca output]

### Key Findings
- [Bullet points]

---

## Analysis

### How Player Camera Works
[Explain the mechanism based on findings]

### How Mount Camera Works
[Explain the mechanism]

### Differences & Implications
[What's different, what matters for our use case]

---

## Recommendations

### Option 1: [Name of approach]
**Description:** [How it would work]
**Pros:** [Benefits]
**Cons:** [Drawbacks]
**Implementation complexity:** [Low/Medium/High]

### Option 2: [Name of approach]
**Description:** [How it would work]
**Pros:** [Benefits]
**Cons:** [Drawbacks]
**Implementation complexity:** [Low/Medium/High]

### Recommended Approach
[Which option and why]

---

## Code References

[List of all relevant files, classes, methods discovered]

---

## Open Questions

[Any remaining unknowns that need further investigation]
```

---

## Success Criteria

Your research is complete when:
- ✅ All 3 btca queries executed and documented
- ✅ Clear understanding of player camera positioning mechanism
- ✅ Clear understanding of mount camera positioning mechanism
- ✅ At least 2 concrete implementation options proposed
- ✅ Recommendation made with reasoning
- ✅ Output file follows format above

---

## Notes

- Use btca for all API/code research (primary source)
- If btca doesn't cover something, note it in "Open Questions"
- Be thorough with code references (file paths, line numbers if available)
- Focus on UNDERSTANDING before proposing solutions
- Document assumptions and mark them clearly
