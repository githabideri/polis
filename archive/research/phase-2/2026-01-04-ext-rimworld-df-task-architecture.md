## 1) RimWorld job/work architecture (what talks to what)

### The “shape” of the system

At a high level RimWorld splits **“what should I do?”** from **“how do I do it?”**:

* **WorkType** = a **category** shown on the Work tab (Haul, Clean, Construct, etc.). ([RimWorld Wiki][1])
* **WorkGiver** = a **scanner/selector** inside a WorkType that looks at the world and decides whether there’s an actionable thing to do right now; conceptually “tasks within a work type category” and “executed according to priority.” ([rimworldmodding.wiki.gg][2])
* **Job** (instance) = “do X at target Y” created by a WorkGiver.
* **JobDef** = the **data definition** of a job kind (think “job type”). Typically points at the driver class.
* **JobDriver** = the **executor**: the step-by-step routine (often described in the modding community as a chain of small steps/“toils”) that actually performs the job.

That “scanner vs executor” split is explicitly how people model it when discussing RimWorld-like systems: WorkGiver checks if it’s an appropriate moment / finds a valid target; Job/JobDriver is the actual instruction list. ([rimworldmodding.wiki.gg][2])

### Relationship: JobDef ↔ JobDriver ↔ WorkGiver

A practical way to think about it:

* **WorkGiver** answers: *“Is there a valid target? Is it worth doing now? If yes, create a Job.”* ([rimworldmodding.wiki.gg][2])
* **JobDef** answers: *“What kind of job is this? What driver executes it? What general constraints/metadata apply?”*
* **JobDriver** answers: *“Given this Job instance, run the actual procedure in steps; fail/abort if preconditions break.”* (That stepwise execution is central to how modders talk about JobDrivers and error logs referencing “toilIndex” and “MakeNewToils”. ([Steam Community][3]))

### How jobs are prioritized and assigned to pawns

RimWorld’s selection is layered:

1. **Player priority policy (Work tab)**: per pawn, per work type.
2. **Within a work type**: specific WorkGivers (and their own internal checks/scoring).
3. **Then target choice**: distance/efficiency rules and special-case “natural priority” within the same band.

Two key, externally documented behaviors you can design around:

* **Manual priorities**: each work type can be set **1 (highest) to 4 (lowest)**, blank = don’t do it. For the **same priority number**, *left-to-right ordering matters*. ([RimWorld Wiki][1])
* RimWorld’s wiki also notes an important emergent behavior: “all available work of one priority will be done before the next,” and it can ignore efficiency when a type is set too high. ([RimWorld Wiki][1])

And a widely used mod (Spatial Priorities) summarises the vanilla job selection heuristic as:

* **First by job priority, then by distance** (closest) ([gitplanet.com][4])
* For equal priority & distance, vanilla can still prefer certain task kinds (“natural priority”) ([gitplanet.com][4])

So: **pawns don’t pull from a global FIFO**. They repeatedly *search/score* potential work sources constrained by the pawn’s Work tab settings, then pick the best candidate given priority and efficiency heuristics.

### How the “work tab” priority system functions

From the Work tab description (important design constraints if you’re cloning the feel):

* Standard mode: enable/disable work types; **left-most work types are “more important” than right-most**. ([RimWorld Wiki][1])
* Manual mode: numeric 1–4 per colonist per work type; **for equal numeric priority, left-most wins**; and **finish all work at priority N before doing N+1**. ([RimWorld Wiki][1])
* Direct player order (“Prioritize …”) exists and is immediate *if the pawn is assigned to that work type*. ([RimWorld Wiki][1])

---

## 2) Dwarf Fortress task queues & job assignment (what’s known publicly)

DF is less “continuous scanning WorkGivers” and more **jobs created by designations/work orders, then claimed** by eligible dwarves.

### Labor designation system

* Tasks (jobs) are created by many systems (designations, workshops, hauling needs, etc.).
* An **idle dwarf** who has the relevant **labor enabled** can be **assigned** to that job.

### How tasks get claimed

Public descriptions are intentionally high level, but the core loop is:

* Job exists in a global list.
* Dwarf checks eligibility (labor enabled, can reach, etc.), then **claims** and begins it.

A useful adjacent reference is **DFHack’s “labormanager”** plugin: it exists specifically because naive/mostly-static labor toggles can cause workload imbalance (starvation/overproduction), so it dynamically reassigns labors to keep the fortress functioning.
That’s a strong hint about the underlying problem space: **claim-based systems need balancing/fairness layers** on top.

---

## 3) Open-source systems to study (C#-friendly + generally useful)

### C# / .NET (best match)

* **DwarfCorp (C#)** — open-source colony management game. The developers explicitly separate **task management (assignment across many dwarves)** from **task execution (robustly completing one task despite interruptions)**. ([Game Developer][5])
  This maps almost 1:1 onto what you’re building.

### RimWorld mod codebases (good for “WorkGiver/JobDriver-style” patterns)

Even though RimWorld itself isn’t open-source, many mods are. Examples you can mine for patterns:

* **Spatial Priorities** (Fluffy) – documents (and alters) the vanilla job selection ordering and shows how a modder intercepts that logic. ([gitplanet.com][4])
* **Colony Manager** (Fluffy) – adds a worktype stored in world state and automates resource-management chores (a real-world example of “higher-level manager generates jobs”). ([GitHub][6])

### Engine-agnostic / other languages

* **LibColony (C++/JS)** — explicitly marketed as a task scheduling library for colony sims like RimWorld/DF; even if you don’t use it, its API ideas can be a design reference. ([GitHub][7])
* **Unknown Horizons (Python)** — open-source economy/city builder; less “pawn jobs”, but strong for production chains and agent/workflow thinking. ([GitHub][8])

---

## 4) Common pitfalls (and the design moves that prevent them)

### Deadlocks (A waits for resource held by B, B waits for A…)

**Root cause**: you let multiple agents partially “commit” to a multi-resource plan.

**Fix patterns**

* **Reservation system** (hard requirement for colony sims): reserve *targets*, *input items*, and sometimes *destination tiles* before starting the critical part of the job.
* **Lock ordering**: if a job needs multiple reservations, always acquire them in a stable order (e.g., by entity id) to prevent cyclic waits.
* **Two-phase jobs**:

  1. *Acquire* all prerequisites (or fail fast)
  2. *Execute*
     If phase 1 fails, release everything and backoff.

### Starvation (some tasks never happen)

This happens in both extremes:

* **Strict priority** (RimWorld-like): “finish all priority 1 before doing 2” can starve low-priority maintenance forever. ([RimWorld Wiki][1])
* **Pure opportunism** (distance-only): agents keep doing easy nearby tasks and ignore critical-but-far tasks.

**Fix patterns**

* **Aging**: increase a task’s effective priority the longer it sits unclaimed.
* **Quotas / budgets**: “do at most N hauling jobs in a row” before considering other categories.
* **Role caps**: reserve some agents for critical worktypes (DFHack labormanager exists largely because manual labor toggles don’t self-balance).

### Pathfinding spam (constant rescans + repaths)

**Root cause**: “find job” does expensive world scans and path checks too often.

**Fix patterns**

* **Tick throttling**: only run job-finding every K ticks per NPC; stagger NPCs so they don’t all scan on the same tick.
* **Cache candidates**: WorkGiver-style scanners can keep a short-lived candidate list; invalidate it on relevant world events.
* **Path probes are a budgeted resource**: do cheap filters first, only path-check the final shortlist.

---

## 5) Best practices for interruption & resumption (including “possession” and emergency orders)

### Model jobs as resumable state machines

Whether you call them “toils”, “acts”, or “steps”, the key is:

* Each step has **(a) entry**, **(b) tick/update**, **(c) exit/cleanup**.
* Each step is restartable and can report **Fail**, **Complete**, or **Retry later**.

This matches how JobDrivers are discussed in the RimWorld ecosystem (errors reference specific “toils” / indices). ([Steam Community][3])

### Interruption types (make them explicit)

Have at least three categories:

1. **Soft interrupt** (can finish current atomic step, then switch)
2. **Hard interrupt** (drop immediately, clean up)
3. **Forced** (player command): must preempt almost everything

RimWorld’s UI conceptually supports “prioritize this task now” via right-click context, and queued player orders. ([RimWorld Wiki][1])

### “Drop everything and do this NOW”

Best pattern: a **job stack** / **priority override**

* Push the current job onto a stack with a “resume token” (what was reserved, what was carried, progress marker).
* Start the forced job.
* On completion, attempt to resume:

  * If resume preconditions still hold, continue.
  * Else, gracefully fail and re-plan.

### Player possession (direct control)

You have two sane options; pick one and be consistent:

**Option A — Possession suspends AI**

* Suspend current job (store token), **release reservations** that block others (otherwise you create artificial deadlocks).
* When unpossessed: try resume or replan.

**Option B — Possession becomes a forced job**

* Treat player input as a high-priority JobDriver that runs until released.
* This keeps one unified system: “everything is a job.”

Option B tends to be easier to reason about (one pipeline), Option A can feel more responsive if you want “manual mode” to ignore AI constraints.

---

## If you want a RimWorld/DF-like architecture in Vintage Story (implementation sketch)

A solid, mod-friendly decomposition:

* `WorkType` (category)
* `WorkGiver` (scanner): `IEnumerable<CandidateJob> Scan(World, Pawn)`
* `JobDef` (data): id, driver type, interrupt rules, reservation requirements
* `Job` (instance): def + targets + parameters
* `JobDriver` (executor): coroutine/state machine of `Steps`
* `ReservationManager`: `TryReserve(pawn, thing/tile, purpose)`
* `JobTracker` per NPC: current job + queue/stack + cooldowns + last-scan times

And then implement the “Work tab” semantics exactly as constraints on job selection:

* Per pawn work-type priority 1–4
* Tie-break by left-to-right
* (Optionally) “all priority N before N+1” if you want the same sharp edges as RimWorld ([RimWorld Wiki][1])

---

If you tell me whether you want the system to feel more **RimWorld-like (continuous scanning + per-pawn priorities)** or more **DF-like (global job pool + labor gating + claim)**, I can give you a concrete C# class layout + algorithms for:

* scoring/selection,
* reservations,
* interruption rules,
* and a throttled scanning schedule that won’t melt your pathfinder.

[1]: https://www.rimworldwiki.com/wiki/Work "Work - RimWorld Wiki"
[2]: https://rimworldmodding.wiki.gg/wiki/Def_Types?utm_source=chatgpt.com "Def Types - RimWorld Modding Wiki"
[3]: https://steamcommunity.com/app/294100/discussions/0/4694532035335716225/?utm_source=chatgpt.com "Error JobDriver JobGiver_Work :: RimWorld General Discussions"
[4]: https://www.gitplanet.com/project/rimworldmoddingfiles "Alternatives and detailed information  of Rimworldmoddingfiles - GitPlanet"
[5]: https://www.gamedeveloper.com/programming/how-we-developed-robust-ai-for-dwarfcorp "How we developed Robust AI for DwarfCorp"
[6]: https://github.com/fluffy-mods/ColonyManager?utm_source=chatgpt.com "GitHub - fluffy-mods/ColonyManager: Colony manager for RimWorld"
[7]: https://github.com/mafik/libcolony?utm_source=chatgpt.com "GitHub - mafik/libcolony: LibColony is a C++ (and JavaScript) library ..."
[8]: https://github.com/unknown-horizons/unknown-horizons?utm_source=chatgpt.com "GitHub - unknown-horizons/unknown-horizons: Unknown Horizons official ..."

