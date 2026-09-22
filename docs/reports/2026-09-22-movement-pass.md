
---

## 10. World-wedge incident (2026-09-22, after the movement pass)

The test world `polis-testbed-pristine` entered a **persistent navigation-wedged state**:
no entity of any kind can navigate (bots never move under `goto`), while everything else
(block ops, inventory, state queries, spawn/despawn) works normally. The world is
**currently wedged** and must be deleted and recreated before further live testing
(ops runbook below).

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
