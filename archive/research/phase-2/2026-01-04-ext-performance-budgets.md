## 1) What successful colony sims actually do (RimWorld, Dwarf Fortress)

### RimWorld (pawns, tick rates, threading)

* **“Smooth” is usually defined by TPS, not FPS.** RimWorld’s simulation runs in **ticks**; at **1× it targets 60 ticks/sec**, at 2× 180, at 3× 360 (and more in dev speed). ([GitHub][1])
* **They explicitly avoid updating everything every tick.** Vanilla exposes **Normal (60 Hz), Rare (every 250 ticks ≈ 4.16s), Long (every 2000 ticks ≈ 33.33s)** ticking intervals. ([GitHub Wiki][2])
* **They spread work to avoid herds.** A common vanilla idiom is “do work every N ticks + a per-thing hash offset” specifically to avoid stalls when many instances run on the same tick. ([GitHub Wiki][2])
* **Recent RimWorld (1.6) moved heavy systems off-thread + reduced tick frequency for distant/off-camera entities.** Ludeon states **pathfinding is “fully multithreaded and batched”** and that they “spread out workload”; the 1.6 wiki notes variable tick rates where some logic can run as low as **~4 Hz instead of 60 Hz** depending on state/view. ([ludeon.com][3])
* **Pawn-count “benchmarks” are mostly community anecdote** (huge variance with mods, map size, wealth, animal counts). People report running **~60 pawns plus many guests/animals** on “mid tier” modern CPUs with acceptable stutter—useful as a sanity check, not as a guarantee. ([Steam Community][4])

**Takeaway:** RimWorld’s scalability isn’t “fast per-pawn AI every frame”; it’s **multi-rate ticking + distributed scheduling + batching + (now) threaded pathfinding**.

### Dwarf Fortress (100+ dwarves, FPS cap, what they optimize)

* DF exposes an **FPS cap default of 100** in init settings (simulation speed is tied to how fast it can process frames up to that cap).
* The DF wiki’s classic performance advice focuses heavily on **pathfinding and unit counts**, especially **bottlenecks** that trigger repeated path recomputation; and it repeatedly calls out “sheer numbers matter” for pets/animals. ([Dwarf Fortress Wiki][5])
* DF also has a **multithreading setting** in init (historically most simulation was effectively single-core; treat this setting as “some work can be parallelized,” not “AI scales linearly with cores”).

**Takeaway:** DF-style “FPS death” is what happens when you allow **unbounded unit AI + pathing + global scans**. Their practical fixes are *mostly design constraints* (reduce units / reduce recompute / avoid bottlenecks), not micro-optimizing a single function.

---

## 2) Reasonable CPU budgets for NPC AI (what numbers actually imply)

You want **< 2ms total for NPC AI** with **50 NPCs** at **60 FPS**.

That budget is easiest to reason about as **CPU per second**:

* 2ms/frame × 60 frames/sec = **120ms/sec total AI time**
* 120ms/sec ÷ 50 NPCs = **2.4ms/sec per NPC**

So you *cannot* afford “full brain” work at 60 Hz. But you *can* afford, per NPC, for example:

* **5 Hz** “brain update” (job selection / replanning): 2.4ms/sec ÷ 5 ≈ **0.48ms per brain update**
* **1 Hz** expensive scan (global job search): **2.4ms per scan**
* Pathfinding must be **globally rate-limited** (more below), because one A* can easily eat your entire per-NPC slice.

### Practical update frequencies (multi-rate like RimWorld)

A good starting split for colony NPCs:

* **30–60 Hz (cheap):** locomotion/path following, animation state, “am I stuck?”, local avoidance (O(1) work)
* **5–10 Hz (medium):** need decay, short-range perception, task progress, reservation heartbeat
* **0.5–2 Hz (expensive):** job reselection, replanning, path requests, long-range perception
* **Event-driven (best):** “new job became available”, “reservation failed”, “path invalidated”, “building completed”

This mirrors what RimWorld formalizes via tick intervals and what 1.6 further pushed via variable tick rates. ([GitHub Wiki][2])

### How often should expensive ops run?

Rules of thumb that tend to work in practice:

* **“Find new job” scan:** *only* when (a) idle, (b) task failed, or (c) relevant world event fired. Otherwise, run at **≤ 1 Hz** with jitter.
* **Pathfinding:** request only on **goal change** or **path invalidation**, not “every time I think.” Add a **token bucket** like “max 2–5 paths per tick globally” (and queue the rest).
* **Reservation checks:** avoid scanning. Use a **central reservation table** keyed by target ID/position with O(1) lookups; do *periodic validation* (e.g., 2–5 Hz) not continuous scanning.

### Amortization patterns that scale

* **Distributed scheduling by stable hash** (RimWorld-style): each NPC gets a “slot” so only N/slots update per tick. ([GitHub Wiki][2])
* **Work queues with budgets:** each tick you process queued AI jobs until you hit (say) **1.5ms**, then defer the rest.
* **Incremental algorithms:** split long operations (pathfinding, flood fill, job scoring) across ticks.

---

## 3) Common colony-sim pitfalls and fixes that actually work

### Pitfall: thundering herd (all NPCs re-evaluate together)

**Symptoms:** periodic spikes, “every second hitch”.
**Fixes:**

* **Per-NPC jitter/hash offsets** for any periodic work. (This is explicitly recommended in RimWorld modding patterns.) ([GitHub Wiki][2])
* **Central scheduler** that meters expensive categories (“job scan”, “pathfinding”, “reservation audit”).

### Pitfall: pathfinding spam

DF explicitly warns about **narrow bottlenecks** causing repeated recomputation and about unit counts compounding costs. ([Dwarf Fortress Wiki][5])
**Fixes:**

* **Path request deduplication:** if 10 NPCs want the same destination, compute once (or compute “to region” + local finalize).
* **Cache by (startChunk, goalChunk, navVersion)** with short TTL.
* **Hierarchical pathing:** coarse route on a chunk/region graph, then local A* for the final segment.
* **Backoff when blocked:** if a path fails, don’t retry every tick—retry in 0.5–2s with jitter.

### Pitfall: job selection thrashing (NPCs constantly switching)

**Fixes:**

* **Commitment windows:** minimum time-on-task unless a higher-priority interrupt occurs.
* **Hysteresis in scoring:** don’t switch unless new job beats current by margin M.
* **Reservation-first:** reserve target early; if you can’t reserve, don’t “half-choose” the job.

---

## 4) Multiplayer networking optimization (and Vintage Story constraints)

### Architecture baseline

Vintage Story is **server-authoritative** for “drops, crafting, entity simulation, chunk loading, and so on.” ([Vintage Story Wiki][6])
So: treat NPC AI as **server-owned truth**. Clients mostly render/interpolate.

### Batching NPC updates

* **Send state deltas, not full snapshots.** Batch per tick (or every 2–3 ticks) into one packet per interest area.
* **Interest management:** only send NPCs in/near the client’s loaded chunks (VS already unloads entities when you aren’t near them). ([mods.vintagestory.at][7])
* **Separate channels by criticality:**

  * **Realtime-ish:** position/velocity, “currently possessed” NPC input echo
  * **Eventual:** job assignment, inventory/needs, “plan changed”, emotes, etc.

### UDP vs TCP in VS mods (hard constraint)

VS exposes custom UDP channels, but **UDP messages should be ≤ 508 bytes** to avoid fragmentation drops for clients behind NAT/firewalls. ([Vintage Story API Docs][8])
So if you use UDP for frequent NPC motion/state, you *must* keep packets tiny (bitpacking, per-entity masks, quantized coords) and accept loss; everything else goes over reliable (TCP) channels.

### Client prediction for possessed NPCs

If a player can “possess” an NPC, treat it like a player:

* client sends **inputs** at 20–30 Hz
* client predicts locally, server corrects
* everyone else gets interpolated server snapshots
  This keeps bandwidth and CPU predictable.

---

## 5) Vintage Story-specific performance considerations for 20–50 autonomous NPCs

### Tick rate reality in VS

* VS physics/simulation commonly runs at **~30 ticks/sec**. ([Vintage Story API Docs][9])
* VS event callbacks are tied to **fixed-interval game ticks**. ([Vintage Story API Docs][10])
  So your mental model should be “30 Hz sim” plus **your own scheduled AI frequencies**.

### Entity update batching patterns (what to do in a mod)

* Prefer a **single AI system** that ticks and schedules NPC work (instead of 50 independent heavy OnTick handlers).
* Use **staggered `RegisterGameTickListener`-style intervals** for medium/low-frequency work (and add per-NPC jitter).
* If you use entity behaviors, note VS has a concept of **ThreadSafe** behaviors intended to allow multi-threading for performance—only mark it true if you truly avoid unsafe world access.

### Chunks, simulation range, and “NPCs across the map”

* VS gameplay is largely **time-based for unloaded chunks** (things update based on elapsed time when reloaded). ([Vintage Story][11])
* Entities also get **unloaded/despawned during chunk unload**, and are reinitialized when chunks load again. ([Vintage Story API Docs][12])

So a colony spread over large distances should not try to “live simulate” all NPCs everywhere. Instead:

* **Active simulation** only in loaded/nearby chunks
* **Offline simulation** for far colonies: advance needs, crops, production, etc. via coarse time-step when the area loads again (cheap, deterministic, no pathfinding)

---

## A scalable architecture for 50 NPCs under ~2ms AI

If I had to boil it down to a design that matches your target:

1. **Central scheduler + budgets**

* Each tick: budget e.g. **1.5ms** for AI jobs
* Categories: perception, job assignment, pathfinding, reservation audit
* Process queues until budget exhausted; defer remainder

2. **Multi-rate brains**

* Per NPC:

  * 30 Hz: movement follow + stuck detection (tiny)
  * 5–10 Hz: task execution + local perception
  * 0.5–2 Hz: job selection / replanning (only when needed)

3. **Global rate limits**

* Pathfinding token bucket (e.g. 2–5 per tick), dedupe identical requests, cache results

4. **Event-driven job system**

* Jobs are posted; NPCs subscribe by skill/role/zone
* Recompute candidates on events, not constant scanning

5. **Networking**

* Server authoritative; send deltas + batch
* Keep UDP packets **≤ 508 bytes** if you use them at all ([Vintage Story API Docs][8])
* Everything non-critical is eventual consistency

If you want, describe how your NPC “job selection” works today (global scan? local scan? zones?), and I’ll map it onto a concrete scheduler layout (queues, tick slots, budgets, and what data structures avoid O(N×M) scans).

[1]: https://github.com/simplyWiri/Dubs-Performance-Analyzer "GitHub - simplyWiri/Dubs-Performance-Analyzer: Profiling tool for the game Rimworld"
[2]: https://github-wiki-see.page/m/UnlimitedHugs/RimworldHugsLib/wiki/Custom-Tick-Scheduling " Custom Tick Scheduling - UnlimitedHugs/RimworldHugsLib GitHub Wiki "
[3]: https://ludeon.com/blog/2025/06/announcing-odyssey-and-update-1-6/?utm_source=chatgpt.com "Ludeon Studios − Announcing Odyssey and update 1.6!"
[4]: https://steamcommunity.com/app/294100/discussions/0/3792632220364286706/ "How many pawns do you generally have? :: RimWorld General Discussions"
[5]: https://dwarffortresswiki.org/index.php/23a%3AMaximizing_framerate "23a:Maximizing framerate - Dwarf Fortress Wiki"
[6]: https://wiki.vintagestory.at/Modding%3ASynchronization?utm_source=chatgpt.com "Modding:Synchronization - Vintage Story Wiki"
[7]: https://mods.vintagestory.at/show/mod/6178?utm_source=chatgpt.com "Block Overlay - Vintage Story Mod DB"
[8]: https://apidocs.vintagestory.at/api/Vintagestory.API.Server.IServerNetworkAPI.html?utm_source=chatgpt.com "Interface IServerNetworkAPI | VintageStory API"
[9]: https://apidocs.vintagestory.at/api/Vintagestory.API.Common.Entities.EntityBehavior.html?utm_source=chatgpt.com "Class EntityBehavior | VintageStory API"
[10]: https://apidocs.vintagestory.at/api/Vintagestory.API.Common.IEventAPI.html?utm_source=chatgpt.com "Interface IEventAPI | VintageStory API"
[11]: https://www.vintagestory.at/forums/topic/3074-how-to-keep-chunks-loaded/?utm_source=chatgpt.com "How to keep chunks loaded? - Questions - Vintage Story"
[12]: https://apidocs.vintagestory.at/api/Vintagestory.API.Common.Entities.Entity.html?utm_source=chatgpt.com "Class Entity | VintageStory API"

