# Agentic Harness Research Plan

**Date:** 2026-01-12  
**Status:** Draft (research kickoff)  
**Roadmap Phase Fit:** Phase 2 (Task/Job System) enablement; cross-phase testing infrastructure

## Context

We need a robust harness that lets agents observe player/bot state, issue commands
relative to the player, and verify outcomes without manual inspection. This plan
breaks the work into parallel research tasks with concrete outputs so multiple
agents can contribute simultaneously.

## Preparation (must complete before research)

1) **Scope:** "Agentic harness can observe player/bot state, resolve coordinates,
   and verify actions without manual inspection."
2) **Success criteria:** agent can spawn/move/verify bots relative to player
   without manual coordinates; harness returns evidence; logs align.
3) **Environment lock:** world `test-lands`, server config, harness port, log
   paths, baseline scripts.
4) **Evidence rules:** every claim must cite a file path, API symbol, or log
   snippet.
5) **No code changes:** research only; do not modify code during this phase.
6) **Research hygiene:** prefer local sources; use `btca` only when needed (see
   `docs/btca_usage.md`).

## Parallel Research Tasks (R1–R7)

Each agent should read `AGENTS.md` and this plan, then deliver one doc for the
assigned task using the mod doc syntax (see "Output Requirements").

### R1 — Player position + look direction APIs

**Goal:** Determine how to query player position, yaw/pitch, and raycast target.
**Sources:** server API usage in codebase; `vsapi`; existing mod patterns.
**Deliverables:**
- API methods/types for position + look vector.
- Server-safe approach (multiplayer context).
- Minimal code sketch (no changes).

### R2 — Coordinate systems and offsets

**Goal:** Explain HUD coords vs server coords and define conversion if any.
**Sources:** logs, debug output, any coordinate conversion in codebase.
**Deliverables:**
- Root cause + evidence.
- Proposed canonical coordinate system for harness output.
- Any conversion formula or warnings.

### R3 — Command surface (server/chat)

**Goal:** Determine which commands can be invoked programmatically vs chat-only.
**Sources:** `/polis` command registrations; server command APIs; mod docs.
**Deliverables:**
- List of viable command channels + constraints (permissions, safety).
- Recommendation on which channel to expose via HTTP.

### R4 — Observability and action verification

**Goal:** Confirm how to verify actions (spawn, move, pickup) programmatically.
**Sources:** bot state, entity events, inventory hooks, pathing APIs.
**Deliverables:**
- Event hooks or polling signals for action completion or failure.
- Suggested fields for structured action results.

### R5 — PlayerBot requirements / game modes

**Goal:** Determine if survival mode or other mods are required for bot usage.
**Sources:** PlayerBot mod code/docs; config flags; local mod references.
**Deliverables:**
- Definitive requirements with evidence.
- Any gating logic (server/client/mode).

### R6 — Harness/UI connectivity & CORS

**Goal:** Identify why `tools/test-ui.html` shows "Disconnected".
**Sources:** `tools/test-ui.html`, JS fetch paths, browser security rules.
**Deliverables:**
- Root cause + evidence.
- Low-risk fixes or recommended usage notes.

### R7 — Automation entry points

**Goal:** Provide reliable launch + map load + log capture sequence.
**Sources:** existing scripts, flatpak flags, log paths, mod config.
**Deliverables:**
- Recommended launch flow.
- How to detect "world ready" for harness.

## Output Requirements (per agent)

Each agent must produce a doc in mod doc syntax under `docs/research/`:

**Required sections:**
- Title (H1)
- Date
- Purpose
- Summary
- Evidence (file paths, API names, or log snippets)
- Open questions
- Implications for harness design

**Placement rules:**
- Default location: `docs/research/misc/` (testing infrastructure).
- If findings clearly belong to a phase, use `docs/research/phase-*`.
- If unsure, investigate by scanning `docs/research/INDEX.md`; when still
  uncertain, place in `misc` and note the ambiguity.
- Always update `docs/research/INDEX.md` with the new doc.

**Naming convention:** `YYYY-MM-DD-<topic>.md`

## Consolidation (after all R tasks)

Once R1–R7 are complete, synthesize a short design spec:
- required endpoints,
- data model,
- error semantics,
- verification flow,
- minimal integration steps.

