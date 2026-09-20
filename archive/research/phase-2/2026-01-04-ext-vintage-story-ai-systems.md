## 1) Mods with NPC job systems / colony-ish gameplay

### **VS Village (vsvillage)**

What it *is*: a big “villages + villagers” mod, focused on worldgen villages, navigation, points-of-interest, and managing/hiring villagers. ([mods.vintagestory.at][1])

What it does that’s relevant to “jobs/tasks”:

* **Two-stage navigation**: regular A* plus a **village waypoint network** to help villagers navigate more reliably. ([mods.vintagestory.at][1])
* **Village POIs (“places”) + villager belongings**: it has tooling/commands to visualize “places relevant to a village” and to highlight which **villager/bed/workstation** belong together. That strongly suggests its “tasking” model is built around *assignments to POIs + ownership links (bed/workstation) + pathing*. ([mods.vintagestory.at][1])
* A **management system** with **hiring by profession** is visible in stack traces (`TryHireVillager(EnumVillagerProfession …)`), so professions are a first-class concept in its villager logic. ([GitHub][2])

If you want to understand “how it handles villager tasks” in practice, the most productive angle is:

* inspect how it defines/links **workstations + beds + POIs**, and
* how profession selection gates “what actions are allowed” (hire + workstation type + POI tags).

### **VS Village tileset ecosystem**

It has multiple *village tileset* addons (industrial, desert, viking, etc.). These mainly expand village generation, not the AI core, but they matter because POIs/waypoints/workstations are often created via those assets. ([mods.vintagestory.at][3])

### **NDL Villagers**

This is another “villagers/town” direction mod (more explicitly town-center-ish / NPC-ish). It’s one of the few other mods I could find that clearly targets “villagers as a system,” not just “more creatures.” ([mods.vintagestory.at][4])

### AI/behavior “building block” mods (useful when you’re building colony NPCs)

These aren’t colony sims by themselves, but they show *how mods extend AI and persistence*:

* **Detailed Animals**: explicitly tells modders to add its **entity behaviors and AI tasks** to more animals. That’s a concrete example of the “extend via behaviors + tasks” pattern. ([GitHub][5])
* Some creature mods ship/mention expanded task sets (e.g. “ExpandedAiTasks” appearing in the ecosystem). ([mods.vintagestory.at][6])

### “RTS / colony sim” mods?

I did not find anything that’s obviously a full **MineColonies-style** “builder/farmer/miner + logistics + construction previews + warehouse couriers” equivalent for Vintage Story. The closest matches in spirit are **VS Village** and **NDL Villagers** as the “villagers as a system” anchors, plus a bunch of smaller mods that extend AI tasks/behaviors rather than implementing a full colony loop. ([mods.vintagestory.at][1])

## 2) EntityActivitySystem and EntityBehaviorTaskAI (how complex NPC behavior is actually built)

Vintage Story’s entity AI is largely *compositional*: entities get **behaviors**, and one of those behaviors can run an AI “scheduler” of **tasks**.

### EntityBehaviorTaskAI / the “taskai” behavior (core creature AI model)

The Vintage Story Wiki’s page for **`taskai`** lays out the essential execution model:

* You attach the `taskai` **entity behavior** (server-side) to an entity.
* You define a list of **AI tasks (`aitasks`)**.
* Tasks are grouped into **slots 0–7**, and **only one task per slot can be active** at once.
* Task selection is **priority-based** (and has a separate **cancel priority** concept). ([wiki.vintagestory.at][7])

So “complex behavior” usually means:

* multiple slots doing different concurrent concerns (e.g., slot for locomotion/targeting, slot for attacking, slot for fleeing, etc.), and/or
* tasks that maintain internal state (cooldowns, targets, “current job”, etc.) in entity attributes.

### How vanilla creatures decide what to do

Vanilla creatures are primarily driven by:

* **entity JSON behaviors** (e.g., physics, task AI)
* **task definitions** like `seekentity`, `meleeattack`, etc. ([wiki.vintagestory.at][8])

Example idea chain (typical):

* `seekentity` moves toward a target under certain conditions. ([wiki.vintagestory.at][9])
* `meleeattack` executes when in range, with timing windows/cooldowns. ([wiki.vintagestory.at][10])
* targeting logic and “who counts as hostile” can be shared via base task types like `AiTaskBaseTargetable`. ([wiki.vintagestory.at][11])

### Can you inject custom tasks?

Yes, in the sense that the system is designed around “behavior runs a list of tasks defined in JSON,” so mods commonly add behaviors/tasks and then attach them via JSON. The wiki explicitly documents behaviors being added via the entity JSON file. ([wiki.vintagestory.at][8])
(Implementation detail: you still need to **register** your behavior/task type in code so the engine can instantiate it from the `code:` string.)

### EntityActivitySystem / EntityBehaviorActivityDriven (vanilla humanoid/villager-style AI)

Separately from “taskai”, there is an **activity-driven** system used by vanilla humanoid NPCs (notably villagers). We can see that:

* **`EntityActivitySystem.Load(activityCollectionPath)`** exists in the survival mod code path,
* **`EntityBehaviorActivityDriven.Initialize()`** triggers loading activity collections,
* villagers go through `EntityVillager.Initialize`, and the activity system loads JSON like `working-villager.json` (seen in error logs). ([GitHub][12])

What this implies architecturally:

* Instead of “pick the highest-priority runnable task in a slot,” an activity system tends to be “choose an **activity** from an **activity collection**,” and the entity runs that higher-level activity (which can internally drive movement, interaction with POIs, etc.). We can’t see the full class code here, but the load/initialize flow and the existence of “activity collections” is unambiguous from the call stack. ([GitHub][12])

**Can custom activities be injected?**
Practically, yes—because the system is loading an **activity collection by asset path**. That usually means:

* create your own activity collection JSON asset, and
* point an entity’s activity-driven behavior at it (or patch the vanilla one to include your activities).
  But the exact “hook points” (how you register new activity types vs. only new data) depends on how the survival mod’s activity system instantiates activities. The stack trace confirms where it loads from, not the full extension API surface. ([GitHub][12])

## 3) VS modding community resources for AI/entity questions

### Official/community Discord

* Official invite: ([Discord][13])
  Channel names/categories can change, but on the official server you’ll want the **Modding** section and any C#/API-help channels for entity/AI work.

### Official forums (good for deep, searchable threads)

A very relevant example thread: **“How should I approach modifying AI tasks?”** ([Vintage Story][14])
If your question is “how do I patch AI without stomping vanilla JSON every spawn,” that thread is exactly the right genre of discussion.

### Wiki pages that are directly “advanced entity behavior” relevant

* **Entity behaviors overview** (how JSON attaches behaviors): ([wiki.vintagestory.at][8])
* **`taskai` behavior deep details** (slots, priority, cancel priority): ([wiki.vintagestory.at][7])
* Individual task pages: `seekentity`, `meleeattack`, etc. ([wiki.vintagestory.at][9])
* Entity creation tutorials (useful once you start making your own NPC entity types): ([wiki.vintagestory.at][15])
* The wiki’s “Understanding the VS Engine” explicitly calls out that the **Essentials mod provides entity AI and pathfinding** (useful context when you’re hunting which assembly/mod owns what). ([wiki.vintagestory.at][16])
* YouTube “Modding Vintage Story” playlist (long-form walkthrough style): ([YouTube][17])

## 4) How VS mods typically handle persistence, custom AI, and interaction

### Persistent NPC data across sessions

You have several “built-in” persistence hooks on entities:

* `Entity.Attributes`: permanently stored attributes that are only client-only or server-only. ([apidocs.vintagestory.at][18])
* `Entity.WatchedAttributes`: permanently stored attributes that also **sync to clients when changed**. ([apidocs.vintagestory.at][18])
* Lifecycle: `OnEntitySpawn()` vs `OnEntityLoaded()` are distinct (spawn vs save-load). ([apidocs.vintagestory.at][18])

Pattern you’ll see in serious NPC mods:

* store stable identity/job/home/workstation IDs in Attributes/WatchedAttributes,
* reconstruct runtime references (resolved POIs, cached path nodes, etc.) in `OnEntityLoaded()`.

### Custom entity behaviors / AI

Two dominant approaches:

1. **TaskAI-driven creatures**: add a new behavior/task type, then attach via entity JSON (`behaviors: … { code: "taskai", aitasks: … }`). The wiki documents this structure and the scheduling model. ([wiki.vintagestory.at][8])

   * Mods like Detailed Animals explicitly instruct adding their behaviors/tasks to entities, showing this is a standard extension route. ([GitHub][5])

2. **Activity-driven humanoids**: hook into (or replace) the activity-collection-driven behavior for villagers/humanoids. We know vanilla villagers go through `EntityBehaviorActivityDriven` + `EntityActivitySystem.Load()` and activity collection JSON. ([GitHub][12])

   * VS Village appears to **replace/spawn its own villager entities** during hiring (`BehaviorReplaceWithEntity.Initialize`, `TryHireVillager`), which is a common way to avoid fighting vanilla villager internals. ([GitHub][2])

### Player-to-NPC interaction systems

Common patterns:

* Override/handle `Entity.OnInteract(...)` for right-click interactions (or custom packet-driven UIs). ([apidocs.vintagestory.at][18])
* Use built-in interaction behaviors where they fit:

  * **`conversable`** behavior opens a conversation dialog on right click, with branching logic and triggers/actions. ([wiki.vintagestory.at][19])

### A useful “sanity checklist” when designing colony/job NPCs in VS

* **Define where state lives**: Attributes vs WatchedAttributes. ([apidocs.vintagestory.at][18])
* **Separate “goal selection” from “execution”**:

  * goal selection: activity system or a high-level “job manager task”
  * execution: a small set of focused tasks (path to POI, operate workstation, deliver item, etc.) ([wiki.vintagestory.at][7])
* **Patch vs replace**: if vanilla villager internals fight you, it can be cleaner to spawn your own entity type (VS Village’s hiring path suggests this is viable). ([GitHub][2])

If you tell me what you’re trying to build (e.g., “workers that haul items between stockpiles” vs “colonists that autonomously expand buildings”), I can map it onto the most fitting approach (taskai vs activity-driven vs hybrid) and point to the exact wiki pages/tasks you’ll end up touching first.

[1]: https://mods.vintagestory.at/vsvillage "VS Village - Vintage Story Mod DB"
[2]: https://github.com/G3rste/vsvillage/issues/60 "Crash when hiring villagers -pre.3 + pre.2 · Issue #60 · G3rste/vsvillage · GitHub"
[3]: https://mods.vintagestory.at/vsvillageindustrial "VS Village Industrial Village Addon - Vintage Story Mod DB"
[4]: https://mods.vintagestory.at/?utm_source=chatgpt.com "Vintage Story Mod DB"
[5]: https://github.com/sekelsta/detailedanimals?utm_source=chatgpt.com "Animal husbandry, behaviour, and genetics for Vintage Story"
[6]: https://mods.vintagestory.at/ndlvillagers?utm_source=chatgpt.com "/ NDL Villagers - Vintage Story Mod DB"
[7]: https://wiki.vintagestory.at/index.php?mobileaction=toggle_view_mobile&title=Modding%3AEntity_Behavior_taskai "Modding:Entity Behavior taskai - Vintage Story Wiki"
[8]: https://wiki.vintagestory.at/index.php/Modding%3AEntity_Behaviors?utm_source=chatgpt.com "Modding:Entity Behaviors - Vintage Story Wiki"
[9]: https://wiki.vintagestory.at/Modding%3AAI_Task_seekentity?utm_source=chatgpt.com "Modding:AI Task seekentity - Vintage Story Wiki"
[10]: https://wiki.vintagestory.at/index.php/Modding%3AAI_Task_meleeattack?utm_source=chatgpt.com "Modding:AI Task meleeattack - Vintage Story Wiki"
[11]: https://wiki.vintagestory.at/Modding%3AAiTaskBaseTargetable?utm_source=chatgpt.com "Modding:AiTaskBaseTargetable - Vintage Story Wiki"
[12]: https://github.com/G3rste/vsvillage/issues/60?utm_source=chatgpt.com "Crash when hiring villagers -pre.3 + pre.2 #60 - GitHub"
[13]: https://discord.com/invite/HQsQTFN?utm_source=chatgpt.com "Vintage Story - Discord"
[14]: https://www.vintagestory.at/forums/topic/15085-how-should-i-approach-modifying-ai-tasks/?utm_source=chatgpt.com "How should I approach modifying AI tasks? - [Legacy] Mods & Mod ..."
[15]: https://wiki.vintagestory.at/Modding%3AContent_Tutorial_Entity_Creation_Part_1/en?utm_source=chatgpt.com "Modding:Content Tutorial Entity Creation Part 1 - Vintage Story Wiki"
[16]: https://wiki.vintagestory.at/Modding%3AUnderstanding_the_VS_Engine?utm_source=chatgpt.com "Modding:Understanding the VS Engine - Vintage Story Wiki"
[17]: https://www.youtube.com/playlist?list=PLkA9Q5ltQPCK-9zPxYAnWKY4TF3YE1e8o&utm_source=chatgpt.com "Modding Vintage Story - YouTube"
[18]: https://apidocs.vintagestory.at/api/Vintagestory.API.Common.Entities.Entity.html "Class Entity | VintageStory API "
[19]: https://wiki.vintagestory.at/Modding%3AEntity_Behavior_conversable "Modding:Entity Behavior conversable - Vintage Story Wiki"

