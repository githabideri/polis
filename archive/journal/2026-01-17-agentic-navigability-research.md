# Agentic Navigability Research & Project Restructuring

**Date:** 2026-01-17
**Goal:** Evaluate and improve project structure for AI agent navigability
**Status:** ✅ Phase 1 Complete (core restructuring), Phase 2 pending (additional docs)

---

## Executive Summary

This document captures research into how AI agents navigate codebases and what documentation patterns work best for "agentic development" workflows. The investigation was prompted by concerns that the project's growing documentation might be difficult for AI agents to navigate, leading to issues like duplicate research.

**Key Finding:** The project's existing structure (AGENTS.md, research INDEX.md) was already better than average. The main gaps were convention file naming (CLAUDE.md), machine-specific path handling (.env), and outdated status information (ROADMAP.md).

---

## Part 1: Internal Navigability Testing

### Methodology

Spawned 5 Haiku subagents with minimal context to simulate fresh agent sessions. Each was given a specific task and asked to report confidence level and pain points.

### Test Results

| Agent Task | Confidence | Key Finding |
|------------|------------|-------------|
| Quick project overview | 5/5 | "Exceptionally well-documented" - AGENTS.md + ROADMAP.md excellent |
| Find butchering research | 5/5 | Found immediately via grep on docs/research/ |
| Find build commands | 4/5 | Confusion about deployment paths, multiple options unclear |
| Find container test docs | 4/5 | Docs comprehensive but scattered across 4 files |
| Plan patrol feature | 4/5 | Struggled with persistence architecture, doc structure navigation |

### Pain Points Identified

1. **Build/Deploy Path Confusion**
   - Multiple deployment paths mentioned (symlink, copy, VS Mod Tools)
   - VSDATA path not clearly explained
   - Hardcoded paths that are machine-specific

2. **Architecture Documentation Scattered**
   - Shadow Registry pattern documented in TECHNICAL.md but not easily discoverable
   - "How to add a new action" workflow not centralized
   - VISION.md comprehensive but too long (19.8KB) - agents avoid reading large files

3. **Testing Workflow Fragmented**
   - Test docs in `docs/testing/`
   - Test results in `docs/testing/test-results/`
   - Guide in `AGENT_TESTING_GUIDE.md`
   - Agents need to connect multiple files

4. **No "Quick Reference" for Implementation**
   - Planning agent couldn't quickly find "how does X work in this codebase"
   - Had to read large files or guess based on patterns

5. **Outdated Status Information**
   - ROADMAP.md showed Phase 1 "IN PROGRESS" when it was actually complete
   - Caused agents to report inconsistent project status

---

## Part 2: External Best Practices Research

### Methodology

Spawned 5 research agents to gather community wisdom on agentic development:
1. Context management strategies
2. Documentation patterns for AI consumption
3. Complexity management in agentic workflows
4. Tool-specific conventions (CLAUDE.md, .cursorrules, etc.)
5. Community lessons learned

Note: Web access was limited; agents provided summaries from training knowledge.

### Convention Files by Tool

| Tool | Convention File | Location | Format |
|------|-----------------|----------|--------|
| **Claude Code** | `CLAUDE.md` | Root, `~/.claude/`, `.claude/` | Markdown |
| **Cursor** | `.cursor/rules/*.mdc` | `.cursor/rules/` | MDC (Markdown + frontmatter) |
| **Cursor (legacy)** | `.cursorrules` | Root | Plain text |
| **GitHub Copilot** | `copilot-instructions.md` | `.github/` | Markdown |
| **Universal** | `llms.txt` | Root | Plain text (emerging standard) |

### Claude Code Memory Hierarchy

1. **Enterprise Policy** - Organization-wide (`/etc/claude-code/CLAUDE.md`)
2. **Project Memory** - Team/Repository (`./CLAUDE.md`)
3. **Project Rules** - Modular (`.claude/rules/*.md`)
4. **User Memory** - Personal, all projects (`~/.claude/CLAUDE.md`)
5. **Project Local** - Personal, per-project (`./CLAUDE.local.md`, gitignored)

### Documentation Patterns That Work

**Do:**
- Front-load critical information (first 500 tokens most important)
- Use explicit structure (headings, lists, code blocks)
- Include copy-paste ready commands
- Keep instruction files under 2000 tokens
- Provide concrete examples over abstract descriptions

**Don't:**
- Rely on "see also" links without inline summaries
- Use prose-heavy instructions (agents skim)
- Scatter information about one topic across multiple files
- Use ambiguous commands ("run the dev command")
- Include machine-specific paths in version-controlled files

### The `llms.txt` Standard

Emerging convention (similar to `robots.txt`) for AI-optimized project summaries:

```
# Project Name
> Brief one-line description

## Quick Facts
- Language: X
- Framework: Y

## Key Files
- path/to/main.cs - Description

## Common Tasks
- Build: `command here`
- Test: `command here`
```

### Complexity Management Strategies

**Scale Thresholds:**
| Project Size | What Works | What Breaks |
|--------------|------------|-------------|
| <10K LOC | Direct commands, minimal overhead | N/A |
| 10K-100K LOC | Module-focused work, curated context | Cross-cutting changes (>10 files) |
| >100K LOC | Highly decomposed subsystems | System-wide understanding |

**Key Strategies:**
1. **Curated context files** (<2000 tokens each)
2. **Hierarchical documentation** (overview → details)
3. **Task Registry** (single source of truth for work items)
4. **Session handoff patterns** (structured summaries)
5. **Golden patterns** (reference implementations to follow)

### Anti-Patterns to Avoid

1. Overloading instruction files (keep <500 lines)
2. Including secrets in instruction files
3. Ignoring path-specific rules for large codebases
4. Not versioning team instructions
5. Vague instructions ("format code properly" vs "use 2-space indent")
6. Monolithic instruction files (break into focused topics)

---

## Part 3: Actions Taken

### Files Created

| File | Purpose |
|------|---------|
| `llms.txt` | Universal AI-readable project overview (~400 tokens) |
| `.env.example` | Template for machine-specific paths |
| `CLAUDE.md` | Symlink → AGENTS.md (Claude Code auto-loads this) |

### Files Modified

| File | Changes |
|------|---------|
| `.gitignore` | Added `.env` and `CLAUDE.local.md` |
| `AGENTS.md` | Build commands now use `$VSDATA` env var instead of hardcoded paths |
| `ROADMAP.md` | Updated to reflect actual project status (Phase 1 complete, Phase 2.0 in progress) |

### Structure After Changes

```
polis-builder-npc/
├── llms.txt              # NEW: AI-optimized overview
├── CLAUDE.md             # NEW: Symlink → AGENTS.md
├── AGENTS.md             # UPDATED: Uses env vars
├── ROADMAP.md            # UPDATED: Accurate status
├── .env.example          # NEW: Path template
├── .env                  # GITIGNORED: Local paths
├── .gitignore            # UPDATED
└── docs/
    └── journal/
        └── 2026-01-17-agentic-navigability-research.md  # This file
```

### Environment Variable Pattern

**Before:** Hardcoded paths in AGENTS.md
```bash
VINTAGE_STORY="/home/mf/.local/share/flatpak/..."  # Machine-specific!
```

**After:** Environment variables + template
```bash
# .env.example (tracked)
VINTAGE_STORY=/path/to/your/vintagestory
VSDATA=/path/to/your/VintagestoryData

# .env (gitignored, created by each developer)
VINTAGE_STORY=/home/mf/.local/share/flatpak/...
VSDATA=/home/mf/Code/polis-builder/vsdata
```

---

## Part 4: Remaining Work (Phase 2)

### Recommended but Not Yet Implemented

| Item | Priority | Effort | Description |
|------|----------|--------|-------------|
| `docs/QUICKREF.md` | Medium | 20 min | Token-efficient architecture cheat sheet |
| `docs/testing/README.md` | Medium | 10 min | Single entry point for testing docs |
| Section markers in `.cs` | Low | 5 min | Navigation comments in large code files |
| `.cursorrules` | Low | 5 min | If using Cursor editor |

### QUICKREF.md Template (for future implementation)

```markdown
# Quick Reference

## Adding a New Action
1. Create class deriving from `EntityActionBase`
2. Implement `Start()`, `OnTick()`, `Succeed()`/`Fail()`
3. Register in command handler (~line 1025)
4. Template: `PolisMineBlockAction` (line 4508)

## Key Patterns
- **Persistence**: Always use `PolisGlobalData`, not just WatchedAttributes
- **Validation**: Check range, LOS, claims before actions
- **Logging**: Prefix with `[polis]`, check debug flag

## Build Commands
source .env && dotnet build -c Release && cp -r bin/Release/Mods/polis-builder-npc "$VSDATA/Mods/"
```

---

## Part 5: Lessons Learned

### Why Agents Struggle with "Good" Documentation

1. **Token efficiency** - Agents avoid reading 19KB files even when relevant
2. **Search vs Browse** - Agents grep well but don't "browse" directory structures
3. **Implicit knowledge** - Humans infer "VSDATA means VS data folder"; agents don't
4. **Connection-making** - Agents don't automatically connect AGENTS.md → TECHNICAL.md → implementation

### What This Project Did Right (Keep Doing)

1. **AGENTS.md as entry point** - Comprehensive, well-structured
2. **Research INDEX.md** - Makes finding existing research trivial (prevented duplicate butchering research)
3. **Phase-based organization** - Clear mental model
4. **Test harness documentation** - Comprehensive and accurate
5. **Journal entries** - Good for session handoffs

### Recommendations for Future Work

1. **Keep `llms.txt` updated** - Update when major features complete or phase changes
2. **Keep ROADMAP.md accurate** - Update immediately when phase status changes
3. **Use `.env` for all machine-specific paths** - Never hardcode paths in tracked files
4. **Create `CLAUDE.local.md`** for personal preferences - Gitignored, per-developer
5. **Consider creating QUICKREF.md** when architecture patterns are finalized

---

## Part 6: References

### External Resources (from research)

- `llms.txt` specification: https://llmstxt.org/
- Claude Code docs: https://code.claude.com/docs/
- Cursor rules: https://docs.cursor.com/context/rules-for-ai
- GitHub Copilot instructions: `.github/copilot-instructions.md`

### Internal Research Files

- Phase 1 completion: `docs/research/phase-1/2026-01-06-phase1-completion-status.md`
- Phase 2 roadmap: `docs/research/phase-2/2026-01-06-phase-2-roadmap.md`
- Research index: `docs/research/INDEX.md`

### Test Agent Transcripts

Full transcripts from navigability test agents available at:
- `/tmp/claude/-home-mf-Code-polis-builder/tasks/a3cf80c.output` (overview)
- `/tmp/claude/-home-mf-Code-polis-builder/tasks/afb4332.output` (research lookup)
- `/tmp/claude/-home-mf-Code-polis-builder/tasks/a530a29.output` (build)
- `/tmp/claude/-home-mf-Code-polis-builder/tasks/a2e7544.output` (testing)
- `/tmp/claude/-home-mf-Code-polis-builder/tasks/a8fd153.output` (planning)

---

## Appendix A: Complete `llms.txt` Created

```
# polis-builder-npc
> Vintage Story mod: Controllable humanoid NPCs ("Deity RTS with Possession")

## Project Status
- Phase 0 (Foundation): ✅ COMPLETE - Bot spawning, pathfinding, basic commands
- Phase 1 (Possession): ✅ CORE COMPLETE - Player can possess NPCs (2026-01-06)
- Phase 1.5 (Smoothing): ⏳ DEFERRED - Client-side movement polish
- Phase 2.0 (Action Primitives): 🚧 IN PROGRESS - World interaction actions
  - Container transfer: ✅ Done
  - Mine/Harvest: ✅ Done (2026-01-16)
  - Other primitives: see phase-2 roadmap
- Phase 2.1+ (Job System): 📋 PLANNED - Autonomous task execution

## Quick Facts
- Language: C# (.NET 7)
- Game: Vintage Story (Flatpak or native)
- Main file: PolisBuilderNpcSystem.cs (~5000 lines)
- Test harness: HTTP on port 8585

## Entry Points (Read Order)
1. AGENTS.md - Agent workflow guide (READ FIRST)
2. docs/research/phase-2/2026-01-06-phase-2-roadmap.md - Current work
3. docs/TECHNICAL.md - Architecture details
4. docs/research/INDEX.md - Research index (check before researching!)

## Environment Setup
Copy `.env.example` to `.env` and set your paths:
- VINTAGE_STORY: Path to VS installation (for API references)
- VSDATA: Path to VintagestoryData folder (mods, saves, logs)

## Build & Deploy
source .env  # Load paths
dotnet build -c Release
cp -r bin/Release/Mods/polis-builder-npc "$VSDATA/Mods/"

## Key Architecture Patterns
- **Shadow Registry**: Bot persistence via PolisGlobalData (survives chunk unloads)
- **Action Pattern**: Derive from EntityActionBase with Start()/OnTick()/Succeed()/Fail()
- **Template**: PolisMineBlockAction (line ~4508 in PolisBuilderNpcSystem.cs)

## Testing
- Harness auto-starts on port 8585 when mod loads
- Guide: docs/testing/AGENT_TESTING_GUIDE.md
- POST /polis/command for actions, GET /polis/state for verification

## Before Implementing New Features
1. Check docs/research/INDEX.md - research may already exist
2. Use `btca` tool for VS API questions (see docs/btca_usage.md)
3. Follow workflow in AGENTS.md
```

---

## Appendix B: `.env.example` Created

```bash
# polis-builder-npc Environment Configuration
# Copy this file to .env and fill in your local paths
# .env is gitignored - your paths stay private

# Path to Vintage Story installation (where VintagestoryLib.dll lives)
# Examples:
#   Flatpak: ~/.local/share/flatpak/app/at.vintagestory.VintageStory/x86_64/stable/active/files/extra/vintagestory
#   Native Linux: /opt/vintagestory
#   Windows: C:\Program Files\Vintage Story
VINTAGE_STORY=/path/to/your/vintagestory/installation

# Path to VintagestoryData folder (mods, saves, logs)
# Examples:
#   Flatpak: ~/.var/app/at.vintagestory.VintageStory/config/VintagestoryData
#   Native Linux: ~/.config/VintagestoryData
#   Windows: %APPDATA%/VintagestoryData
#   Custom (this project uses): ../vsdata
VSDATA=/path/to/your/VintagestoryData

# Test harness settings (optional)
HARNESS_URL=http://localhost:8585
HARNESS_TIMEOUT=10
```

---

**Document Author:** Claude (Opus 4.5)
**Session Date:** 2026-01-17
**Tokens Used:** ~50K (research) + ~10K (implementation)
