# TASK: [Task Name]

**Agent Instruction Document**
**Date:** [YYYY-MM-DD]
**For:** Parallel research agent
**Output:** `docs/journal/[YYYY-MM-DD-topic-findings].md`

---

## Context

**Project:** polis-builder-npc (Vintage Story mod for controllable NPCs)
**Phase:** [Phase number and name]
**Current Issue:** [Brief description of the problem]

### What We Know

[Numbered list of confirmed facts about current state]

1. **[Fact 1]:** [Description]
2. **[Fact 2]:** [Description]

### What We Need

[Clear statement of research goal]

---

## Required Reading

Before starting, read these for context:

1. **Project structure:**
   - `ROADMAP.md` - [What to look for]
   - `docs/TECHNICAL.md` - [Relevant section]

2. **Current implementation:**
   - [File1.cs] - [What it does]
   - [File2.cs] - [What it does]
   - `docs/research/phase-X/[relevant-doc].md` - [Context]

3. **Reference repos:**
   - `../vsapi` - VS API source (for btca searches)
   - `../vsessentialsmod` - VS Essentials mod source
   - `../vssurvivalmod` - VS Survival mod source

---

## Research Questions

### Primary Question
**[Main question to answer]**

Specifically:
- [Sub-question 1]
- [Sub-question 2]
- [Sub-question 3]

### Secondary Questions
- [Supporting question 1]
- [Supporting question 2]

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

**Common resources:**
- `vsapi` - Canonical API behavior and semantics
- `vssurvivalmod` - Vanilla usage patterns and examples
- `vsessentialsmod` - Official patterns and integration
- `jaunt` - Mount/riding/travel mechanics
- `vsquest` - Quest systems
- `vsvillage` - Villager/NPC systems

**Example:**
```bash
btca ask -r vsapi -q "How does EntityPos work in Vintage Story?"
```

### Troubleshooting

**If btca takes too long or times out:**
- Complex queries can take 2-3 minutes - be patient
- Break very complex questions into smaller, focused queries
- Try a more specific resource (-r flag)

**If btca syntax error:**
- Check `docs/btca_usage.md` for correct syntax
- Ensure question is in quotes after `-q` flag
- Verify resource name is valid (see btca_usage.md resource map)

---

## btca Queries to Run

Use the `btca` tool with these queries (copy/paste exactly):

### Query 1: [Query Name]
```bash
btca ask -r [resource] -q "[Your detailed question here.
Include:
1. Specific aspects you need to understand
2. Context about why you need this info
3. What specific information to look for (class names, methods, patterns)

Please provide code references and examples.]"
```

### Query 2: [Query Name]
```bash
btca ask -r [resource] -q "[Another question]"
```

### Query 3: [If needed]
```bash
btca ask -r [resource] -q "[Another question]"
```

---

## Deliverables

Create output file: `docs/journal/[YYYY-MM-DD-topic-findings].md`

### Required Format

```markdown
# [Topic] Research Findings

**Date:** [YYYY-MM-DD]
**Researcher:** [Your agent name]
**Task:** [TASK file you read]

---

## Summary

[1-2 paragraph summary of key findings]

---

## btca Query 1: [Query Name]

### Query
[Paste the exact query you ran, including the -r flag and full question]

### Results
[Full btca output - include ALL results, don't truncate]

### Key Findings
- [Bullet point 1 - specific discovery]
- [Bullet point 2 - class/method names found]
- [Bullet point 3 - patterns identified]

---

## btca Query 2: [Query Name]

### Query
[Paste the query]

### Results
[Full output]

### Key Findings
- [Bullet points]

---

[Repeat for all queries]

---

## Analysis

### [Aspect 1]
[Explain findings about this aspect]

### [Aspect 2]
[Explain findings]

### [Connections/Implications]
[How findings relate to the problem]

---

## Recommendations

### Option 1: [Name of approach]
**Description:** [How it would work]
**Pros:** [Benefits]
**Cons:** [Drawbacks]
**Implementation complexity:** [Low/Medium/High]
**Feasibility:** [Can this actually work? Any blockers?]

### Option 2: [Name of approach]
**Description:** [Alternative approach]
**Pros:** [Benefits]
**Cons:** [Drawbacks]
**Implementation complexity:** [Low/Medium/High]
**Feasibility:** [Assessment]

### Recommended Approach
[Which option and detailed reasoning why]

---

## Code References

**Files/Classes/Methods discovered:**
- [File path] - [What it does]
- [Class name] - [Purpose]
- [Method signature] - [Behavior]

---

## Implementation Notes

[Specific guidance for whoever implements the solution]
- [What needs to change]
- [What to watch out for]
- [Edge cases to consider]
- [Testing strategy]

---

## Open Questions

[Any remaining unknowns that need further investigation]
- [Question 1]
- [Question 2]
```

---

## Success Criteria

Your research is complete when:
- ✅ All btca queries executed and fully documented (no truncated results)
- ✅ [Specific understanding goal 1]
- ✅ [Specific understanding goal 2]
- ✅ At least 2 concrete implementation options proposed
- ✅ Recommendation made with detailed reasoning
- ✅ Output file follows format above exactly

---

## Notes

- **Use btca for all API/code research** (it's the primary source)
- **Be thorough** - include full results, don't summarize too aggressively
- **Focus on understanding before proposing solutions**
- **Document all assumptions** and mark them clearly
- **If btca doesn't answer something,** note it in "Open Questions"
- **Code references matter** - include file paths, line numbers, method signatures
- **Test your recommendations** - are they actually feasible?
