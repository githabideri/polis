# AGENTS.md — rules for AI agents working in this repo

## Hard rules
1. **Version shim law:** version-specific Vintage Story API calls only through
   `src/Compat/<version>/` facades. Never call a version-specific API from
   feature code. (See README "Version shim law".)
2. **One status source:** status, verification levels, and open issues live
   in `STATUS.md` only. Journals/research/roadmaps are frozen in `archive/` —
   read them, do not update them.
3. **Hermetic build:** `./build.sh` must work from a clean checkout using
   only `.env` values (no machine-specific paths hardcoded in csproj or
   scripts).
4. **Sanitization for public mirror:** never commit internal hostnames
   (`*.`), LAN IPs, passwords, tokens, or ops detail anywhere
   except `ops/` (private-only) and this repo's private remote. The public
   mirror script excludes `ops/` and `archive/` journal material.
5. **Verification vocabulary — use it exactly:** `implemented` / `locally
   verified` (unit/build) / `live verified` (in-game) / `remotely verified`
   (production). Never collapse these into "works".
6. **Game testbed (the game testbed):** see `ops/CT114-VNC.md`. Never restart Xvnc
   while the game runs. A VNC keyboard does not work via synthetic events
   (xdotool) — drive input through noVNC only. The game auto-logs in via the
   cached session key in `/root/.config/VintagestoryData`.

## Workflow
- Branch per feature/fix; PRs to `main`. Commit messages reference the
  issue/task id when one exists.
- After changing mod code: `./build.sh --deploy`, restart `vsgame`, verify
  the mod loaded (journal / `/polis list`), then update `STATUS.md` with the
  honest verification level.
- Test runs go through the harness (`TESTING.md`); raw in-game fiddling is
  for exploration, not evidence.
- If a change breaks the build, do not ship a "works-ish" commit — leave the
  branch, note the state in `STATUS.md`.

## What agents must NOT do
- Edit `archive/` content.
- Commit secrets (VNC passwords, session keys, SSH keys, API tokens).
- Push to the public mirror directly — only the mirror script does that.
- Restart the PVE host or the backup infrastructure.
