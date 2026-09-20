## 1) Open-source colony sim implementations (Unity / Godot) worth mining

### Godot

* **`davisbrandon02/colony-sim-tutorial` (Godot 4)** – tutorial repo explicitly targeting a colony sim, with code pushed “episode by episode” and folders separated into `data/`, `scenes/`, `scripts/`, `ui/`. Good if you want a *clean, didactic baseline* rather than a mature production architecture. ([GitHub][1])

### Unity

* **Project Porcupine (Unity)** – one of the most-discussed open-source “colony sim / RimWorld-like” codebases, and (crucially) it contains extensive design discussions around jobs in Issues. The implementation details are scattered, but the *architecture decisions* are unusually explicit in the tracker. ([GitHub][2])
* **FyWorld (Unity)** – an open-source RimWorld-inspired base-building/sim project, positioned as a “mega-tutorial” in Unity. This is useful if you want a *whole-game context* (defs, world, agents) instead of isolated AI demos. ([GitHub][3])
* **`zoreslavs/ColonySimulation` (Unity)** – explicitly a colony simulation project; includes behavior-tree usage (less “classic colony job board”, more “agent behavior scaffolding”). ([GitHub][4])

If you only pick one to study for “jobs like RimWorld”: **Project Porcupine’s job-system issue threads** are the highest signal-to-noise for concrete scheduling + priority debates. ([GitHub][2])

---

## 2) Patterns you asked for (with “what to look for” in real codebases)

### A) Task definition: data-driven vs code-driven

**Common hybrid that scales best in colony sims:**

* **Data-driven “TaskDef”**: *what* the task is (tags/skills required, base priority, allowed tools, reservation policy, interruptibility, timeouts, animation hooks, etc.)
* **Code-driven “TaskRunner/JobDriver”**: *how* to do it (state machine / coroutine / BT subtree / GOAP action executor)

In Porcupine discussions, you can see tension between “simple global queue” and richer representations (e.g., task weights, caching, “suspended” states)—which is basically the same tension between keeping tasks as simple objects vs building a richer data model for scheduling. ([GitHub][2])

### B) Task queue management (priority queues, interruption)

Typical colony-sim queues become **more than one queue**:

1. **Ready queue** (doable now)
2. **Blocked/suspended queue** (waiting on materials, access, construction prereqs, etc.)
3. **Claimed/in-progress** (to prevent duplicate work)
4. Optional: **Emergency/preemptive lane** (fire, medical, combat, “player forced”)

Porcupine explicitly discusses:

* **Global job queue** (jobs added globally; units select best match) ([GitHub][2])
* **Priority / weighting schemes** (so selection isn’t “first come”) ([GitHub][5])
* **Suspended jobs** and the pain of “when do we wake them?” (materials arrived, tile freed, etc.) ([GitHub][6])
* **Caching current/best job** to avoid expensive rescans every frame ([GitHub][7])
* A “new job system” proposal with a manager distributing per-unit task lists ([GitHub][8])

### C) Worker–task matching algorithms

You’ll see three broad families:

**1) Decentralized greedy (most common)**

* Each idle worker scans jobs and picks the “best” by a scoring function.
* Pros: simple, robust, easy to mod.
* Cons: can thrash (everyone retargets), can be unfair, can be O(N_workers × N_jobs).

Porcupine’s “global queue, unit finds best match” is this model. ([GitHub][2])

**2) Central dispatcher**

* A scheduler assigns jobs to workers (often in batches), can enforce fairness and reduce thrash.
* This is what Porcupine’s proposed “threaded job manager distributing task lists” is gesturing toward. ([GitHub][8])

**3) Market/auction/negotiation (excellent for multi-agent coordination)**

* Jobs are “auctioned”; agents bid based on distance, skill, urgency, current commitments.
* Great when you care about coordination and avoiding duplicated effort.
* This connects directly to academic **Multi-Agent Task Allocation (MATA)** and auction mechanisms. ([GitHub][9])

If you want something battle-tested outside Unity/Godot: **DwarfCorp’s dev writeup** is a good “colony-ish AI task management in practice” reference (even though it’s not Unity/Godot).

### D) Blackboard systems for NPC knowledge

A useful mental model for colony sims is **two-layer blackboards**:

* **World blackboard (shared)**: known hazards, reserved resources, discovered ores, global alerts, reachable paths status, etc.
* **Agent blackboard (private)**: current intention, remembered failures, last tool used, local perceptions, “don’t retry this for 20s”, etc.

GDQuest’s blackboard glossary is a concise grounding reference. ([school.gdquest.com][10])
If you want a longer explainer focused on multi-agent coordination with a shared memory structure, this is one example (blog-level, not academic): ([Toño Game Consultants][11])

---

## 3) ECS approaches to colony sims (job assignment in data-oriented form)

### How ECS typically handles job assignment

In ECS you generally model **jobs as entities too**:

* `JobRequest` / `JobAvailable` components on job entities
* `WorkerIdle`, `WorkerSkill`, `WorkerPosition`, `WorkerCarrying`, etc. on worker entities
* A **JobAssignmentSystem** runs periodically:

  1. query idle workers
  2. query available jobs
  3. compute scores (distance, skill fit, urgency, reservations)
  4. write `AssignedTo(workerId)` on job and `CurrentJob(jobId)` on worker

Structural changes (adding/removing components to mark assigned/unassigned) are often queued and played back safely using an **Entity Command Buffer (ECB)**. ([Unity Documentation][12])
If you want per-entity “task lists” in ECS, **dynamic buffers** are one standard tool. ([Unity Documentation][13])

For learning by comparison, Unity’s DOTS training samples explicitly provide “classic Unity vs DOTS ports” of simulation-y patterns. ([DeepWiki][14])
Unity also publishes ECS samples repos you can mine for idioms (queries, ECB usage, etc.). ([GitHub][15])

### Pros/cons vs traditional OOP (in colony-sim terms)

**ECS Pros**

* Scaling: lots of agents + lots of jobs becomes more feasible.
* Clear dataflow: easy to instrument (“why did nobody haul food?” becomes “query shows no `JobAvailable` with tag=HaulFood”).
* Parallelization opportunities.

**ECS Cons (especially relevant to colony sims)**

* The tricky part isn’t pathfinding; it’s *coordination state* (reservations, interrupts, dependencies). ECS can do it, but you must design those components carefully or you’ll create racey/oscillating systems.
* Debugging intention can feel harder than OOP unless you build great tooling/logging.

If you’re in Godot land and want ECS infrastructure: GECS is an ECS framework for Godot 4.x that integrates with nodes/resources (handy for hybrid approaches). ([GitHub][16])

---

## 4) Papers + technical talks/blogs for scheduling + coordination + AI style choices

### Multi-agent scheduling / coordination (directly applicable to “colony jobs”)

* **Contract Net Protocol (classic)** – foundational negotiation model for distributed task allocation.
* **Multi-agent task allocation (survey-ish / modern)** – useful vocabulary + taxonomy (centralized vs distributed, auctions, etc.). ([GitHub][9])
* **Auction/market mechanisms + Behavior Trees** (research paper) – directly bridges “game-style BT control” with auction allocation.

### Behavior Trees vs Utility AI vs GOAP (decision layer)

* **GOAP in practice (F.E.A.R.)** – Jeff Orkin’s GDC paper/talk material is still the canonical “practical planning shipped in a game” reference. ([gamedevs.org][17])
* **GameDeveloper article summarizing GOAP + Orkin context** – readable bridge if you don’t want to start with the PDF. ([Game Developer][18])
* **Game AI Pro chapter: Behavior Selection Algorithms** – solid overview of BTs/FSMs/etc. from an industry perspective. ([gameaipro.com][19])
* **Game AI Pro 2 chapter on optimizing practical planning** – deeper on GOAP-style planning, costs, search direction, debugging tradeoffs. ([gameaipro.com][20])
* **Utility theory @ GDC Vault** – decision modeling through utility; useful when you want smooth “importance” gradients instead of brittle if/else. ([gdcvault.com][21])
* **Dave Mark / IAUS overview** – pointer to the “utility-first architecture” lineage. ([gameai.com][22])
* **BT vs GOAP discussion (blog-level but pragmatic)** – good for framing when planning actually pays off. ([Davide Aversa's Blog][23])

---

## Practical takeaway: the “colony sim job system” blueprint that survives growth

If you’re building a mod/project and want something you won’t rip out later, aim for:

1. **TaskDef (data)** + **TaskRunner (code)** hybrid
2. **Reservations** as first-class (resource, tile, target, tool)
3. **Blocked/Suspended jobs** with explicit wake-up triggers (inventory change, build complete, path reopened)
4. **Scoring-based matching** (even if you start greedy) + **anti-thrash** (cooldowns, commitment windows, cached best-job)
5. **Blackboard split** (world shared + agent private)
6. If you go ECS: jobs as entities + assignment system + ECB for safe structural changes ([Unity Documentation][12])

If you tell me your constraints (single-threaded vs multi-threaded, expected pawn count, “player forced jobs” yes/no, modding goals), I can translate that into a concrete job-data schema + matching strategy (greedy vs dispatcher vs auction) that fits.

[1]: https://github.com/davisbrandon02/colony-sim-tutorial "GitHub - davisbrandon02/colony-sim-tutorial: This is the code for the YouTube tutorial series for creating a colony sim game in Godot 4, which you can find here: https://www.youtube.com/playlist?list=PLM-hFhoXjVl1hq0j9lxgRCzxkBpDZhDlT"
[2]: https://github.com/TeamPorcupine/ProjectPorcupine/issues/482?utm_source=chatgpt.com "Sometimes characters will wait a long time before taking on a job"
[3]: https://github.com/Fy-/FyWorld?utm_source=chatgpt.com "GitHub - Fy-/FyWorld: FyWorld - Base-Building / Simulation Game ..."
[4]: https://github.com/zoreslavs/ColonySimulation?utm_source=chatgpt.com "GitHub - zoreslavs/ColonySimulation: Unity colony simulation with ..."
[5]: https://github.com/TeamPorcupine/ProjectPorcupine/issues/86?utm_source=chatgpt.com "Using GOAP system for jobs · Issue #86 - GitHub"
[6]: https://github.com/TeamPorcupine/ProjectPorcupine/pull/517?utm_source=chatgpt.com "Better way of fixing the (pathing/job) performance issues#517"
[7]: https://github.com/Microsoft/vstest/blob/master/src/Microsoft.TestPlatform.CoreUtilities/Utilities/JobQueue.cs?utm_source=chatgpt.com "vstest/src/Microsoft.TestPlatform.CoreUtilities/Utilities/JobQueue.cs ..."
[8]: https://github.com/TeamPorcupine/ProjectPorcupine/issues/63?utm_source=chatgpt.com "Reworking the job system · Issue #63 · TeamPorcupine ... - GitHub"
[9]: https://github.com/Erag0n001/Colony-Sim?utm_source=chatgpt.com "GitHub - Erag0n001/Colony-Sim: Unity Colony sim"
[10]: https://school.gdquest.com/glossary/ai_blackboard?utm_source=chatgpt.com "Blackboard Pattern (Game AI) | Glossary | GDQuest"
[11]: https://tonogameconsultants.com/ai-blackboard/?utm_source=chatgpt.com "AI Blackboard Architecture for Tactical Game AI"
[12]: https://docs.unity3d.com/Packages/com.unity.entities%401.0/manual/systems-entity-command-buffers.html?utm_source=chatgpt.com "Entity command buffer overview | Entities | 1.0.16"
[13]: https://docs.unity3d.com/Packages/com.unity.entities%401.0/manual/components-buffer-introducing.html?utm_source=chatgpt.com "Introducing dynamic buffer components | Entities | 1.0.16 - Unity"
[14]: https://deepwiki.com/Unity-Technologies/DOTS-training-samples?utm_source=chatgpt.com "Unity-Technologies/DOTS-training-samples | DeepWiki"
[15]: https://github.com/Unity-Technologies/EntityComponentSystemSamples?utm_source=chatgpt.com "GitHub - Unity-Technologies/EntityComponentSystemSamples"
[16]: https://github.com/csprance/gecs?utm_source=chatgpt.com "csprance/gecs: Godot Entity Component System - GitHub"
[17]: https://www.gamedevs.org/uploads/three-states-plan-ai-of-fear.pdf?utm_source=chatgpt.com "gdc2006_orkin_jeff_fear - GameDevs.org"
[18]: https://www.gamedeveloper.com/design/building-the-ai-of-f-e-a-r-with-goal-oriented-action-planning?utm_source=chatgpt.com "Building the AI of F.E.A.R. with Goal Oriented Action Planning"
[19]: https://www.gameaipro.com/GameAIPro/GameAIPro_Chapter04_Behavior_Selection_Algorithms.pdf?utm_source=chatgpt.com "Behavior Selection Algorithms - Game AI Pro"
[20]: https://www.gameaipro.com/GameAIPro2/GameAIPro2_Chapter13_Optimizing_Practical_Planning_for_Game_AI.pdf?utm_source=chatgpt.com "Optimizing Practical Planning for Game AI"
[21]: https://gdcvault.com/play/1012410/Improving-AI-Decision-Modeling-Through?utm_source=chatgpt.com "GDC Vault - Improving AI Decision Modeling Through Utility Theory"
[22]: https://gameai.com/iaus.php?utm_source=chatgpt.com "Intrinsic Algorithm Game Techs - IAUS"
[23]: https://www.davideaversa.it/blog/choosing-behavior-tree-goap-planning/?utm_source=chatgpt.com "Choosing between Behavior Tree and GOAP (Planning)"

