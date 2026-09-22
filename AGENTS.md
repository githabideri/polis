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
   (`*.home.example`), LAN IPs, passwords, tokens, or ops detail anywhere
   except `ops/` (private-only) and this repo's private remote. The public
   mirror script excludes `ops/` and `archive/` journal material.
5. **Verification vocabulary — use it exactly:** `implemented` / `locally
   verified` (unit/build) / `live verified` (in-game) / `remotely verified`
   (production). Never collapse these into "works".
6. **Game testbed (the game container):** see `ops/the game container-VNC.md`. Never restart Xvnc
   while the game runs (the game auto-pauses; resume via noVNC "Back to
   Game" or restart `vsgame`). A VNC keyboard does not work via synthetic
   events (xdotool) — drive input through noVNC only. The game auto-logs in
   via the cached session key in `/root/.config/VintagestoryData`.
7. **Web UI is the primary interaction surface** — `http://<ct-addr>:8585/polis/ui2/` (LAN-reachable via `POLIS_HARNESS_IP`;
   no ssh tunnel). The noVNC stream pane needs the
   VNC password once per session; the still-image screenshot pane needs
   none. VNC/noVNC is oversight-only, not the control channel.
8. **Player uids contain `+`** (e.g. `d4pJ+Ty1...`). The harness parses raw
   queries (keeps `+`), but client code should still URL-encode (`%2B`) —
   form-decoding turns `+` into a space and every uid lookup silently
   fails. This bug class cost real debugging time; check it first when a
   uid call says "not found" and the player is clearly online.
9. **Game restart ritual:** `systemctl stop vsgame`, wait until port 8585
   is actually released (TIME_WAIT from the old process's own connections
   can make a fresh bind fail for up to ~60s — the harness retries
   12x5s, but the wait makes it deterministic), then `systemctl start
   vsgame`. Verify: `curl -s http://<ct-addr>:8585/polis/status`.

## Workflow
- Branch per feature/fix; PRs to `main`. Commit messages reference the
  issue/task id when one exists.
- After changing mod code: `./build.sh --deploy`, restart `vsgame`, verify
  the mod loaded (journal / `/polis list`), then update `STATUS.md` with the
  honest verification level.
- Test runs go through the harness (`TESTING.md`); raw in-game fiddling is
  for exploration, not evidence.
- Commands are `POST /polis/command` with
  `{"cmd": "...", "args": [...], "context": {"playerUid": "<uid>"}}`
  (JSON, case-insensitive). Notable: `look <x> <y> <z> [pitch]` (turn
  player/bot to face a point — yaw=atan2(dx,dz), pitch preserved unless
  given), `setblock <code> <x> <y> <z>` (1.22 codes are concrete:
  `rock-granite`, `packeddirt`, ...; `fire` is decorative — the ray trace
  skips it), `teleport <uid> <x> <y> <z>`, `goto <x> <y> <z>`.
- **Pitch convention (decoded empirically, 1.22.7):** `pitch = pi` is
  level; increasing pitch looks DOWN (2.5rad ≈ 35deg down, 3pi/2 =
  straight down); `lookVec = (sin(yaw)*cos(p-pi), -sin(p-pi),
  cos(yaw)*cos(p-pi))`. Never assume a convention — `tests/view/aim-verify.py`
  exists to prove aim end-to-end against the game's own ray trace.
- If a change breaks the build, do not ship a "works-ish" commit — leave the
  branch, note the state in `STATUS.md`.

## What agents must NOT do
- Edit `archive/` content.
- Commit secrets (VNC passwords, session keys, SSH keys, API tokens).
- Push to the public mirror directly — only the mirror script does that.
- Restart the PVE host or the backup infrastructure.
