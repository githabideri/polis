
---

## 10. World-wedge incident (2026-09-22, after the movement pass)

The test world `polis-testbed-pristine` entered a **persistent navigation-wedged state**:
no entity of any kind can navigate (bots never move under `goto`), while everything else
(block ops, inventory, state queries, spawn/despawn) works normally. The world was wedged all morning and
**self-healed by 09-22 ~07:00** after repeated clean save/load cycles (full trace, external
corroboration, and defenses: section 11).

### Timeline
- **≤ 02:00**: world healthy; pass 6 (stall fix) and the harvest mission both green.
- **01:44**: game restarted *while a goto was running* (to deploy the fallback ladder).
  The running bot persisted its interrupted navigation state into its chunk.
- **01:5x onward**: new bots no longer move. `goto` returns "moving to…" and then
  nothing; `lastAction` stays null; no exceptions in any log.
- **Morning**: full instrumentation pass (below). All recovery attempts failed.

### Root-cause chain (established by file-based tracing inside the mod)
1. Harness runs accumulated **idle persisted bots** (`StoreWithChunk = true`, no
   despawn) — 19 at the first incident.
2. **A restart mid-goto** leaves the bot's waypoint traverser with an interrupted
   async path search. VS's `NavigateTo_Async` has a one-shot guard
   (`if (this.asyncSearchObject != null) return false;`) — the traverser then
   **silently rejects every future navigation** for that entity.
3. The persisted bot reloads every boot carrying that state, and — established this
   session — **the wedge survives bot elimination entirely**:
   - Traces show: the goto action *starts* correctly (SEQ-OK, `finished=false`), the
     activity ticks ~4 s (4× ACT-TICK), then the **traverser's own stuck-detector**
     fires (`OnStuck` → `ExecutionHasFailed` → activity self-terminates → the
     `ActiveActivitiesBySlot` slot clears and stays empty forever: `slots=0` on every
     subsequent tick).
   - The activity system is **not** a persisted entity component (fresh instance per
     load) and the mod's `polis-bots` registry is **memory-only** (verified absent
     from every `.vcdbs` on the box) — so neither is the wedge carrier.
   - The wedge therefore lives in **world-level state persisted in the chunk blobs**
     (compressed protobuf; not string-searchable) or in world-level pathfinder
     state. Candidate mechanisms (unverified, ordered by plausibility):
     (A) the world's A*/pathfinder pool persisting an interrupted search that
     serialises all navigations; (B) a persisted world-paused flag; (C) a wedged
     entity stalling the entity-simulation subsystem.
4. **Silence is the signature**: no exception anywhere; the only observable is
   "traverser stuck → action aborted → slot cleared → bot inert", which looks
   indistinguishable from a bot that simply decided to stand still.

### Recovery attempts (all failed)
| Attempt | Result |
|---|---|
| Despawn all bots + restart | **Despawn does not remove the entity from the chunk** — all despawned bots returned on the next load. New 1.22 finding: `Entity.Die(EnumDespawnReason.Removed)` does not de-persist here. |
| Fresh world via headless `--openWorld <new>` | The `.vcdbs` is created but the game **hangs in the load phase** (game thread unresponsive > 10 min). New-world creation is not reliable headless. |
| Restore the original world (after the fresh-world attempt) | Wedge returned with it, as expected. |
| X11 focus trick (`xdotool windowactivate` + mouse move on the Xvnc display) | No effect — rules out simple window-focus auto-pause as the whole story. |

### Operational runbook (next session / user)
1. **Delete the wedged world**: with a **noVNC viewer connected**, open the world
   list and delete `polis-testbed-pristine`; or stop the game and
   `rm -rf Worlds/polis-testbed-pristine Saves/polis-testbed-pristine.vcdbs*`.
2. **Create the new testbed with the VNC viewer connected** (headless new-world
   creation hangs). Suggested name: `polis-testbed-2`. Update `VSGAME_WORLD` in
   `/etc/vsgame.env`.
3. Re-verify: spawn + `goto` 3 blocks, expect movement within ~2 s.
4. If a *fresh* world is also wedged, the wedge is not world-persistent — re-run the
   instrumented build (traces in `/tmp/polis-trace.log`) and check
   `gamedata`-blob pathfinder keys.

### Prevention (implemented this session)
- Harness **sweeps all bots before each run** (and should at shutdown).
- Goto action: **bounded 3-phase fallback ladder** (async A* → sync A* → straight
  line; 15 s phase timeouts; honest failure instead of silent hang).
- Decision loop: **max-stall valve** (2 consecutive waits → policy resumes).
- **Rule: never restart the game while a goto is in flight; always sweep bots before
  stopping.**

### vcdbs schema (first documentation)
`Saves/<world>.vcdbs` (SQLite): `chunk` (~4.8k rows, **compressed** binary blobs —
entities live here, not string-searchable), `mapchunk`, `mapregion`, `gamedata`
(1 row, one blob), `playerdata` (1 row: name/uid), `sqlite_sequence`. The mod's
`WorldManager.SaveGame` registry (`polis-bots`) is **not** stored in the per-world
vcdbs nor in any other DB on the box — it is memory-only and rebuilt from chunk
scan on load.

## 11. Wedge resolved — full trace and external corroboration (09-22 morning)

**Status: the world is healthy again.** Full mine mission green end-to-end
(bot traveled, mined, returned to base; GOAL at step 7, 64 s; 1/1 complete;
0 false waits, 0 stalls; 6/7 reflex short-circuits, 0 judge calls).

### What the morning instrumentation established
1. **The `ai-pathfinding` server thread is alive and functional.** A
   `PathfinderTask` enqueued directly from the mod (`PathfindingAsync`
   system, reachable via `sapi.World.Api.ModLoader.GetModSystem`) completed
   within 10 s with a valid 2-waypoint path. The off-thread processor
   (dedicated server thread, `OffThreadInterval = 5`) works; the
   main-thread overflow path (queue > 1) is the documented fallback. The
   thread-dead theory is dead.
2. **The world is not paused.** Two observer screenshots 78 s apart
   differ by ~165 k pixel-sum (dawn breaking); the in-game day (~10 real
   minutes) is running.
3. **The per-entity latch is real and source-proven** (this is the part
   we *can* fully explain): `WaypointsTraverser.OnGameTick` returns
   without moving while `asyncSearchObject != null && !Finished`, and
   `NavigateTo_Async` refuses new navigations while a search is pending
   (one-shot guard). Any bot whose search never completes is inert
   forever — silently, with no log line.

### The world-level component: a known, open, vanilla VS failure
The public record matches our symptom set exactly:
- **anegostudios/VintageStory-Issues #5422** ("Monsters are frozen in
  place", 1.20.4): entities "spawn without moving or reacting to
  anything at all. They can be punched, your tool's durability lowers,
  but they don't react at all." Repro note: *"The issue is hard to
  replicate and may be the result of saving and reloading a save within
  a vertical distance."* — that is precisely our trigger (restart
  mid-goto). A dev (radfast) asked for long-session logs looking for
  "juicy errors"; **no root cause was ever identified; the issue is
  still open.**
- **#5334** ("1.20.4 Monster Issues"): same freeze; one commenter:
  "relogging makes them disappear" — i.e. it can be transient per
  process, consistent with our world-level component clearing over
  repeated clean save/load cycles.
- **#5875** (1.20.9, still open, 0 dev comments): after systematic mod
  removal, repair mode, chunk unload, kill-all-entities: animals "will
  spawn, Emote and make noise, be attackable and drop loot, **but not
  move or react to players in any way**", and mob spawning stops.
  Confirmed in that thread with **zero mods installed** — pure vanilla.
- **1.22 release notes** (wiki Version history; 1.22.0 2026-04-21 →
  1.22.7 2026-08-16): fishing, mechanisms/mechanical power, metalworking
  rework, shelf storage. **No entity-AI or pathfinding rework** — the
  `PathfindingAsync`/`WaypointsTraverser` architecture decompiles
  identically in the 1.22.7 VSEssentials.dll, so the old failure mode
  plausibly carries forward.
- **VS Village** (the mod the owner asked about): v6.0.1, current for
  1.22.3 (mods.vintagestory.at/vsvillage). The maintainer states they are
  "cleaning up and refining the pathfinding" on top of the same vanilla
  system; a 1.22.3 user report describes a "safeonhurt" error spam on
  village chunks that disconnected them. Relevant prior art for later
  villager-like work, not a cure for this wedge.

### Best reconstruction of this incident
1. 09-21 14:01: a bot's position became **NaN** (observed
   `Given pos contained NaN ... for entity polis-builder-npc:polisbot`
   in client-crash.log — a hard client crash; the *last clean save* was
   whatever preceded it, possibly mid-navigation).
2. The world kept working (the bad state was latent), until **09-22
   01:44: a restart mid-goto** — exactly the #5422 repro — wrote a
   save that, on load, re-created the frozen condition world-wide.
3. Each subsequent **clean** shutdown/load cycle repaired the save a bit
   more (entity states re-serialized from healthy in-memory objects);
   after ~6 cycles the world converged to clean. This matches the
   "relogging makes them disappear" / self-healing behavior in the
   public tickets.

### Defenses (in code)
- **Never restart mid-goto** (ops rule; the harness's `sweep_bots` plus
  the bounded goto ladder make a long in-flight goto impossible).
- **`POLIS_PATH_PROBE=1`** env flag: the 10 s heartbeat now optionally
  enqueues a 3-block probe task and reports queue depth + task
  completion — a one-line check that distinguishes "pathfinding thread
  dead" from "entity physics frozen" in future wedges.
- **Dawn-screenshot check** (observer screenshots 60-120 s apart must
  differ) distinguishes "world paused" from everything else.
- With those two discriminators, any future wedge can be triaged to
  {thread dead | world paused | entity-physics frozen (vanilla bug)}
  in a few minutes.
