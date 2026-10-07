# AGENTS.md — rules for AI agents working in this repo

## Hard rules
1. **One target version:** the mod tracks a single game version (currently
   1.22.7). Keep version-specific API usage isolated (from the next port
   through `src/Compat/<version>/` facades) so a version bump is a bounded
   change, not a repo-wide rewrite. (See README "Porting to a new game
   version".)
2. **One status source:** status, verification levels, and open issues live
   in `STATUS.md` only. Journals/research/roadmaps are frozen in `archive/` —
   read them, do not update them.
3. **Hermetic build:** `./build.sh` must work from a clean checkout using
   only `.env` values (no machine-specific paths hardcoded in csproj or
   scripts).
4. **Sanitization (standing rule):** never commit internal hostnames, LAN/
   Tailscale IPs, private domains, or credentials. Measurement environments
   are written as *roles* ("the game testbed", "the CPU batch box", "the
   3060 card"); endpoints come from env vars and arguments. Deployment-
   specific operational knowledge (how our own testbed is wired up) lives in
   the operator's private service docs, never in this repo.
5. **Verification vocabulary — use it exactly:** `implemented` / `locally
   verified` (unit/build) / `live verified` (in-game) / `remotely verified`
   (production). Never collapse these into "works".
6. **Game testbed:** a headless container running Vintage Story with VNC.
   Its deployment (services, display stack, the TLS front for the UI) is
   operator-specific and documented *outside* this repo. Never restart Xvnc
   while the game runs (the game dies on X disconnect — restart the game
   service afterwards). Drive input through noVNC, not synthetic events
   (xdotool does not fire in-game key events). The game auto-logs in from
   the cached session key in VSDATA (`clientsettings.json`); the key is
   refreshed by a human at the login screen now and then.
7. **Web UI is the primary interaction surface** — the harness serves it
   from the mod folder under `/polis/ui/` (loopback by default; LAN via
   `POLIS_HARNESS_IP` in `.env`). VNC/noVNC is oversight-only, not the
   control channel.
8. **Player uids contain `+`** (e.g. `Ab3x+Yz9...`). The harness parses raw
   queries (keeps `+`), but client code should still URL-encode (`%2B`) —
   form-decoding turns `+` into a space and every uid lookup silently
   fails. This bug class cost real debugging time; check it first when a
   uid call says "not found" and the player is clearly online.
9. **Game restart ritual:** stop the game service, wait until the harness
   port is actually released (TIME_WAIT from the old process's own
   connections can make a fresh bind fail for up to ~60s — the harness
   retries 12x5s, but the wait makes it deterministic), then start it
   again. Verify: `curl -s http://<harness-bind>:8585/polis/status`.
10. **Research references:** `research/` (gitignored) holds source clones
    of third-party systems we design against — currently **XSkills**
    (CRuppert/XSkillsModSet), the Vintage Story skill mod, referenced for
    the polis skill/food-policy design (2026-10-04). Read it as reference
    material; never build it into the mod, never commit it.
11. **The C# toolchain is old (C# 7 era, .NET Framework-era Roslyn).**
    Four build cycles of the 2026-10-07 run hit its edges:
    a logical-not on a reference type (`!zoneBounds`) does not compile —
    write `== null` / `!= null`; an interpolated-string hole containing a
    `?:` ternary over string literals fails (a `??` with a string literal
    is fine) — hoist the ternary into a local variable; `Cuboidi` is a
    **class** (`Vintagestory.API.MathTools`), not a struct — nullable-
    annotation patterns (`.Value` / `.HasValue`) do not exist, plain null
    checks do; JSON is `JsonObject` (a `JToken` wrapper, `Vintagestory.
    API.Datastructures`) — read values with `AsString()` / `AsInt()` /
    `AsBool()` / `AsObject<T>()` / the `this[key]` indexer, never
    `.Value<T>()`. When in doubt, read the decompiled API in the testbed
    (`/tmp/vssurv-real/`) — the 1.22.7 shapes are not the 1.21 ones.

## Workflow
- Commits go to `main` from the workstation copy; the testbed clone is a
  mirror consumer (`git fetch && git reset --hard origin/main`). Commit
  messages reference the issue/task id when one exists.
- After changing mod code: `./build.sh --deploy`, restart `vsgame`, verify
  the mod loaded (journal / `/polis list`), then update `STATUS.md` with the
  honest verification level. **A failed build does not update the deployed
  DLL** — the deploy step copies whatever sits in the build output, so
  after a compile failure a restart silently runs the *previous* code.
  Confirm the build actually succeeded (and the deployed DLL is newer
  than the source) before restarting.
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
- Restart the host machine of the game testbed or any backup infrastructure.
