# Hillside nav fix — child spec (2026-10-10, from session 2026-10-10_006)

You implement fixes F5–F9 (continuing the F1–F4 numbering from the
2026-10-10 nav-fix) for the hillside navigation failure. Scope is
exactly three files, all in `src/Actions/Navigation/`:

- `PolisGotoAction.cs`
- `PolisAStar.cs`
- `PolisPathNode.cs`

No core (engine) patching. No other files. Read all three files first.

## The failure (evidence, do not re-litigate)

A 66-block goto over the granite hill country (base → forage target
(512098,123,512033), from CT249 world polis-survival-5 journal,
2026-10-10 17:40) did this:

1. PolisAStar found a 105-node path (a gentle +1/-1 staircase).
   Execution: 15 s of yaw-oscillation (40–100° flips per second,
   walk-vector flips, onGround flapping) while the bot made only
   slow progress. Phase 0 timed out.
2. Phase 1 (core A*, 500-iteration, 48 nodes): the bot **fell 3.4
   blocks** off the ridge (y 126 → 122.6) following that path, then
   dropped into a 1-block pocket at (512094,121,512038).
3. The F1 bounded-repath ladder then fired 5 times over ~4 minutes
   (17:40:48, 17:41:10, 17:41:21, 17:42:02, …). Each repath's fresh
   PolisAStar path from the new position was *sensible*, and the bot
   *did* eventually converge — **arrival at 17:42:03, ~98 s after
   start** (baseline). The return goto wedged in the same pocket
   (17:42:08). An estate bot sent the same way wandered 4 minutes.

So the search is mostly fine; **execution quality on multi-step
terrain is the bottleneck**, plus one search blind spot (pockets).

## Root causes (two measured facts from the reference mod)

`research/vsvillage/VSVillage/src/Entity/Pathfinding/` (cloned
reference, 224k downloads, villagers walk hills fine):

- Their `VillagerPathNode` heuristic: `hCost = sqrt(DistanceSqTo)` —
  **linear**. Our `PolisPathNode.Init` uses `DistanceSqTo` (squared,
  non-admissible; f = g + h is dominated by h at distance, so the
  frontier stops widening and the search oscillates around obstacles).
- Their `FollowRoute(waypoints, WalkSpeed, 0.2f, …)` — near-test
  tolerance **0.2**. Ours passes **0.7** to FollowRoute. The core
  `WaypointsTraverser.IsNearTarget` vertical term is
  `max(0, dy² − 0.5)`: with d² = 0.49 (our 0.7), a bot standing a
  full block *below* a waypoint (dy = 1.0 → 0.5) misses by 0.01, but
  a bot 0.99 below *passes*. On a staircase where every waypoint is
  one block above the previous, the 0.7 near-test marks each waypoint
  "reached" before the bot actually climbs it, so the waypoint list
  runs ahead of the bot and the traverser's walk-vector flips every
  second chasing the list. That is the measured oscillation.

## The fixes

**F5 — strict waypoint near-distance.** In
`PolisGotoAction.TryPolisAStarPath`, change the `FollowRoute(
waypoints, WalkSpeed, 0.7f, OnDone, OnStuck)` tolerance from 0.7f to
0.2f (the vsvillage value). The final-arrival logic is already
handled by F2 (`OnDone`: one-step approach when |dy| ≥ 0.75, honest
"one step short" when the approach cannot close 0.4+, snap only
when within 1.5) — that stays untouched. If the 0.2 near-test makes
a flat-terrain test thrash on final-approach stuck (the bot cannot
get within 0.2 of a cell center because of collision), that is a
*measured* outcome: try 0.35 next and record which value the flat
suite actually passes with. Do not guess.

**F6 — admissible heuristic.** In `PolisPathNode`, make the start
node's `Cost` and `Init()` use `sqrt(DistanceSqTo(…))` exactly like
`VillagerPathNode` does (cast to float). Nothing else in the cost
model changes.

**F7 — validate the core-A* path before the bot follows it.** In
`PolisGotoAction`, before/when a *core* path is handed to the
traverser (both the `NavigateTo_Async` path — hook `OnFoundPath` —
and the phase-1 synchronous `NavigateTo`), check the path's
consecutive waypoints: if any step **climbs 2 or more blocks**
(Δy ≥ +2 between consecutive waypoints), the path is a phantom
route (the core A*'s +2 step probe) — stop the traverser and skip
straight to the next ladder phase instead of following it. Falls of
2–5 blocks are legal (MaxFallHeight) and stay allowed. The node
list is already extractable in `OnFoundPath` via
`PolisSystem.TryExtractPathFromTraverser` (currently gated on
debugEnabled — run the check itself unconditionally; keep the debug
logging as-is).

**F8 — no-progress watchdog (action level).** In `OnTick`, sample the
entity's 3-D distance to `hereTarget` on the existing 1 s heartbeat.
Keep `bestDist` (lowest so far, persists across repaths) and the
time it was last improved. If ≥ 20 s have passed without the
distance improving by more than 10 %, force the same bounded-repath
path as `OnStuck` (shares the `stuckTries` / MAX_STUCK_REPATHS
budget — no new unbounded loop). This kills the 12 s wedge-push
window (the 17:40:50–17:41:01 segment: bot pushing a block, walk
vector ~0.1, zero progress) and any slow non-converging wander,
which the traverser's 1 s stuck counter never catches because the
bot is technically still moving.

**F9 — search: slope preference + pocket rejection.** In
`PolisAStar`:
- slope preference: in node cost, add `0.5 * |Δy|` to the g-cost
  when expanding a neighbor (one block up or down costs 1.5, flat
  costs 1). This makes the search prefer gentle gradients over
  zig-zag staircases at equal length.
- pocket rejection: a candidate node is a *trap* when its own
  surface (top-of-solid in its column) is a local minimum from
  which the bot cannot climb out: all four horizontal neighbours
  have surface ≥ 2 above the node's surface. Reject such nodes
  (return false from traversability). The target cell itself is
  never rejected (existing behavior). Keep the existing
  `TryFindGround` / `TryStepUp` logic otherwise.

**Stretch (F10, ONLY if F5–F9 still fail live validation):** a
mod-driven step executor — for route segments with |Δy| ≥ 1, drive
the entity's `WalkVector` directly at the next node's cell center
(physics does the Y) and advance when the bot is within 0.4 of the
node; keep the core traverser for flat runs. Implement only if the
live hillside test still oscillates after F5–F9.

## Ground rules

- Build/deploy: `VSDATA=/opt/vintagestory/extra/vintagestory bash
  build.sh --deploy` on the polis CT (ssh alias `polis2`), then
  `systemctl restart vsgame`, then `scripts/deploy-check.sh`.
  The world must be **daylocked during deploy** (harness daylock
  on → restart → daylock off; no world-time cost).
- After any restart: `scripts/chunkprobe` must be clean
  (gateNanCount=0, gameCaptured=true).
- Do not touch the player entity (dingsdangser, uid
  `d4pJ+Ty1RgaBHrQgQEV8z27E` — use JSON-file curl for the `+`).
  Test with a campaign bot standing near the base (e.g. 352903 /
  352906 / 352908 at y121–122, 512090,511966–67) — the harness
  `goto` command moves them; `polisctl teleport` is a no-op for
  seat-possessed bots (do not use it).
- Do not disturb: clayform table (512096,123,511971), firepit
  (512090,121,511967, cold), cottage walls at base.
- Harness base URL from the CT: `http://127.0.0.1:8585` + `/polis/`
  + endpoint (the runner script prepends the `/polis` segment
  itself; e.g. a raw curl of the vitals endpoint is
  `http://127.0.0.1:8585/pol` + `is/vitals` — the path segment is
  spelled p-o-l-i-s; verify the endpoint answers before relying
  on it).
- The mission runner always exits 0; only the run JSON's `outcome`
  field is truth (`"complete"`).
- Verification order (a fix that fails an earlier gate is reverted
  before moving on — ship nothing half-broken):
  1. **Flat regression**: the 2026-10-10 nav matrix — T1–T7, R2,
     Cliff (target coordinates in `/tmp/nav-baseline-20261010.md`
     on the CT; baseline: T1–T6 PASS with exact arrival ~15 s;
     R2/Cliff = honest `ok:false` "stuck after 3 repaths", one
     block below). A **silent `ok:true` short-arrival is a
     regression** — report it, don't paper over it.
  2. **Hillside round trip** (the 17:40 replay): a base bot →
     `goto (512098, 123, 512033)` → `goto` back to base
     (512090, 512038-area base edge). Measure from the 1 s
     heartbeat journal lines: time-to-arrival (baseline 98 s),
     max no-progress window (baseline 12 s), falls (a Δy > 1.5
     jump between heartbeats, baseline 3.4), stuck events
     (baseline 5 per round trip), final position vs target.
     Run the round trip **twice**.
  3. **Integration**: `python3 scripts/r2-progression.py
     builds/ladder-earlygame.json --start P6 --harness
     http://127.0.0.1:8585` (daylocked) — the pots chain must
     still PASS (`outcome: "complete"`; `any_bot_sat ≥ 1400`).
  4. Report + STATUS.
- Report: write `temp/hillside-nav-report.md` — before/after
  matrix (flat suite + hillside round trip ×2), which of F5–F9
  you shipped (numbered, dated 2026-10-10 in code comments),
  what you reverted and why, and the residual (F10 status).
  If the hillside round trip converces with ≤ 1 stuck event and
  no falls, update the STATUS.md "Hillside navigation" open item
  to reflect the implemented + live-verified state (keep the
  honest caveats; this file is public — no hostnames, IPs,
  internal domains, PII in any file or commit, including author
  metadata; the local git identity is already noreply).
- Commits: one or a few small commits on the polis repo (local
  branch is fine; do NOT push — the parent session pushes and
  mirrors after review).
- You cannot ask the user anything. If you are blocked (build
  environment broken, a gate you cannot pass, world state wrong),
  write the blocking question and exact state into
  `/root/homelab/sessions/pi/2026-10-10_006.progress.md` (append a
  `## CHILD BLOCKED` section) and end your turn.
- If the world is wedged (every goto times out regardless of
  target — the known 1.22 navigational wedge), a clean `systemctl
  restart vsgame` is allowed; a world reload is **not** (it would
  drop player moddata). Say so in the report if you used it.
