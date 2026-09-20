# Harness Run + Hole Fill Report

**Date:** 2026-01-21

## Purpose
Document the latest harness run, the crash fix validation, and the scripted pothole-filling workflow. Capture what worked, what failed, and implications for future job/task management (per `docs/VISION.md`).

## Environment
- Game: Vintage Story (Flatpak)
- Harness: `/polis` HTTP server on `localhost:8585`
- Tooling: `scripts/vsctl.py`, `scripts/poliscli.py`
- World: `test-lands`

## Summary of Findings
1) **Crash loop resolved by inventory change.** The earlier fatal error (`Supplied slot is not part of this inventory`) stopped after updating backpack insertion logic in `PolisInventoryHelpers.cs`. Mining with autocollect succeeded and no new error bursts appeared in logs.
2) **Autocollect is visually verifiable.** After mining, the bot held `game:soil-medium-none` and the mined block was visibly gone in the screenshot.
3) **Scripted pothole fill works but needs guardrails.** A scan → filter → setblock pipeline successfully filled air holes at Y=2 while preserving water holes. Mis-ordered CLI args and scan output size were pain points.
4) **Harness access required escalated network permissions.** Direct curl/poliscli calls to `localhost:8585` failed in the sandbox, requiring `sandbox_permissions=require_escalated` for checks.
5) **Window-ready timing is fragile.** `vsctl` timed out waiting for client-ready in one run even though the client eventually reached render-ready. Logs confirmed render handler registered, but `vsctl` missed the signal inside its timeout.

## Timeline (Condensed)
- Built and deployed mod with updated backpack insertion.
- `vsctl start --wait --window` succeeded under escalated permission; world reached RunGame.
- Spawned bot #577, mined soil with autocollect, validated via state + screenshot.
- Removed bots, scanned area, filled holes, and validated with screenshots.

## Visual Verification Evidence
- **Pre-mine:** `/home/mf/Pictures/Vintagestory/polis/screenshot-2026-01-20_23-01-25-341.png`
- **Post-mine:** `/home/mf/Pictures/Vintagestory/polis/screenshot-2026-01-20_23-37-06-999.png` (hole visible, bot holds soil).
- **Pre-fill (right-side view):** `/home/mf/Pictures/Vintagestory/polis/screenshot-2026-01-20_23-54-14-821.png`
- **Post-fill (right-side view):** `/home/mf/Pictures/Vintagestory/polis/screenshot-2026-01-21_00-03-05-171.png`
- **Water hole preserved:** `/home/mf/Pictures/Vintagestory/polis/screenshot-2026-01-21_00-04-41-157.png`

## Scripted Pothole Fill Workflow

### What Worked
- **Scan + parse:** `./scripts/poliscli.py scan <x1 y1 z1 x2 y2 z2> --include-air --output /tmp/polis-scan.json --json` reliably produced a block list that included air + water.
- **Filtering logic:** Selecting `air` at Y=2 with soil below and air above correctly targeted potholes and ignored water.
- **Preserve water holes:** Water was present in the scan as `game:water-still-7`, but the fill logic only touched air, so water holes remained intact.
- **Block placement:** `./scripts/poliscli.py setblock <blockcode> <x> <y> <z>` filled holes without needing a bot.

### What Didn’t
- **CLI arg order pitfalls:** I initially used `setblock x y z code` (wrong). Correct order is `setblock blockcode x y z`. This caused repeated CLI failures.
- **Huge scan output:** Printing scan output to stdout produced massive JSON and was noisy. Writing to `--output` is essential for automation.
- **Timeouts:** A long `setblock` loop hit a default timeout mid-run; finishing required a second pass.

### Recommended Programmatic Flow
1) Scan area to a file (never stdout).
2) Build a map of positions → block code.
3) Identify holes as **air at Y=2** where **below is soil/stone** and **above is air**.
4) Skip if below/above includes water.
5) Use `setblock` to fill with the below soil variant or a default soil.

### Observed Holes Filled (Expanded Pass)
Example subset (not exhaustive):
- `(225, 2, 276)` `game:soil-medium-none`
- `(226, 2, 279)` `game:soil-medium-none`
- `(239, 2, 268)` `game:soil-medium-none`
- `(245, 2, 262)` `game:soil-medium-none`
- `(256, 2, 254)` `game:soil-medium-none`

Water holes detected (preserved):
- `(227, 2, 271)` `game:water-still-7`
- `(232, 2, 270)` `game:water-still-7`

## Findings on Other Issues
- **Old bots caused confusion.** The initial `state` without `--bot` pointed to an older bot; explicit `--bot` was necessary. Despawning old bots before runs should be standard.
- **Sandbox network restrictions:** Local harness access requires escalated permissions even though it’s `localhost`.
- **`vsctl` readiness mismatch:** Client logs confirm render handler registration, but `vsctl` timed out once. Might require a longer wait or log-based recovery step.

## Implications for Task/Job Management
- **Tasks need explicit preconditions:** “No existing bots” should be a standard pre-check to prevent state confusion.
- **Task steps must record world context:** Scans should include bounding boxes and filters used, so reruns are deterministic.
- **Automation requires explicit validation:** Visual screenshots are mandatory checkpoints, not optional; job system should enforce view+capture steps.
- **Error classification:** CLI failures (arg order) and timeouts are deterministic and should be surfaced as recoverable errors with exact remediation steps.

## Skill Update Recommendations (do not apply yet)
For `polis-harness-testing` and `polis-webui-debug`:
- Add a **hard rule**: “Always despawn old bots before a test run.”
- Add a **hard rule**: “Always open and visually inspect screenshots after any visual step.”
- Add a **structured scan workflow** for terrain edits: save scan to file, parse, then apply changes.
- Add a **CLI usage gotcha**: `setblock` arg order is `blockcode x y z`.
- Add a **sandbox note**: harness calls require escalated permissions even for localhost.

## Next Steps
- Optionally re-run pothole fill with a larger bounding box if additional holes remain.
- Consider adding a dedicated “terrain cleanup” CLI command to avoid repeated setblock loops.
