## 1) Built-in “look-at” / IK in Vintage Story?

**There’s built-in support for “head look” (yaw/pitch), but not a general-purpose IK solver exposed as a standard API.**

What VS *does* give you out of the box:

* **Per-entity head orientation fields**: `EntityPos.HeadYaw` and `EntityPos.HeadPitch` exist directly on an entity’s position/pose state. ([apidocs.vintagestory.at][1])
* **A built-in head/upper-body pose controller**: `EntityHeadController` is a core class with explicit `ElementPose` handles for **Head/Neck/UpperTorso/LowerTorso** (and even some foot poses), plus `yawOffset` / `pitchOffset`, and it ticks via `OnFrame(dt)`. ([apidocs.vintagestory.at][2])
* **Networking hook for head pose**: the base `Entity` class includes `SetHeadPositionToWatchedAttributes()`, documented as relevant for entities “with heads” (implemented in `EntityAgent`), and explicitly mentions `headYaw/headPitch`. That’s the intended mechanism to sync head orientation to clients. ([apidocs.vintagestory.at][3])

So: **for “NPC looks at target” you’re in good shape with built-ins** (head yaw/pitch + head controller). For “arm reaches to block” / “hand on tool” IK: you’ll be implementing your own lightweight solver using bone poses (no obvious built-in IK API surfaced in the docs).

---

## 2) How VS mods typically make entity heads/eyes track targets

Most mods (and vanilla-style entities) tend to do this in one of two layers:

### A) High-level (recommended): drive `HeadYaw` / `HeadPitch`, let the engine pose bones

Conceptually:

1. Pick a target point (block center, player eye pos, enemy torso, etc.)
2. Compute desired yaw/pitch from the entity’s “look origin” to that target
3. Smooth + clamp (so you don’t get snapping / 180° neck spins)
4. Write to the entity’s head pose state (`HeadYaw`, `HeadPitch`) ([apidocs.vintagestory.at][1])
5. Sync to clients through watched attributes (what `SetHeadPositionToWatchedAttributes()` is for) ([apidocs.vintagestory.at][3])

**Why this works well:** `EntityHeadController` exists specifically to turn those kinds of values into bone transforms each frame. ([apidocs.vintagestory.at][2])

### B) Low-level: directly manipulate bone `ElementPose`s

If you need something beyond head/neck (e.g., subtle spine twist, eye bones, multi-bone distribution), you can work at the “poses” level. The built-in controller already exposes key poses (Head/Neck/Torso). ([apidocs.vintagestory.at][2])
Tradeoff: more control, but you’re more likely to fight the animation system / blending unless you integrate carefully.

**Eyes:** VS entity shapes often don’t have separately rigged eye bones; if yours do, eye tracking becomes “just another pose rotation,” but it’s content-dependent (your model rig).

---

## 3) Mods/libraries worth looking at for procedural animation patterns

None of these are guaranteed to be “NPC look-at libraries,” but they’re concrete examples of *procedural* or *runtime-driven* animation/pose systems in the ecosystem:

* **Animation Manager [OBSOLETE] (amlib)** – explicitly claims “procedural animations for items and entities,” but it’s **unmaintained** and its latest release targets older game versions (listed as 1.19.4 era). Still useful as a reference for approach/patterns. ([mods.vintagestory.at][4])
* **Entity Emote Library (EEL)** – a framework for driving entity animations (loop/once/freeze, synced client/server) and is intended to be incorporated into other entity mods (including NPC interactions). Not “look-at” specifically, but very relevant for “runtime animation control infrastructure.” ([mods.vintagestory.at][5])
* **Jaunt (Entity Movement System)** – a library that extends entity movement with gait systems; again not “look-at,” but good reference for how bigger systems patch/extend entity behavior cleanly. ([mods.vintagestory.at][6])
* **VSDOF (6DoF head tracking)** – player-focused, but it’s a very direct example of runtime yaw/pitch/roll-driven viewpoint/pose control and per-frame style updating. ([mods.vintagestory.at][7])

Also: the VS wiki’s “Other Resources” page links to **Nat’s Mod Examples** (kept up to date) and the official API docs—these are often the fastest route to finding a minimal “entity behavior + networking + animation” example you can adapt. ([Vintage Story Wiki][8])

---

## 4) Performance considerations for per-frame procedural updates

The big performance trap is: **“per NPC per frame bone work” scales brutally** if you have many colony entities.

Key points:

### Prefer “cheap state updates” + engine pose work

* If you can express look-at as just **HeadYaw/HeadPitch**, do that and let the engine’s head controller handle the bone distribution each frame. ([apidocs.vintagestory.at][1])

### Watch your animation system choice

* VS explicitly documents that the **Client Animator** does “recursive interpolation… for each frame… for each element… for each active element” and is “significantly more costly for the cpu” than `AnimatorBase`. ([apidocs.vintagestory.at][9])
  If your colony NPC solution pushes lots of entities into heavier animator paths, you’ll feel it.

### Update frequency & LOD

A practical strategy for colony NPCs:

* **Server-authoritative target selection** (so all clients see consistent “attention”), but **don’t broadcast every frame**.
* Send head yaw/pitch at a **fixed rate** (e.g., 5–20 Hz depending on how “snappy” you want), and let client-side smoothing interpolate between updates.
* **Distance-based LOD**:

  * near camera: higher update rate, smaller smoothing window
  * far away / not visible: lower rate or disable entirely
* **Early-outs**: if target hasn’t changed meaningfully (angle delta below threshold), skip updates.

### Avoid allocations

If you’re doing vector math for many NPCs:

* reuse vectors where possible
* avoid per-tick LINQ / new object churn
* cache last target + last angles

---

## A practical implementation shape for your colony NPCs

If you want a robust “NPC look-at target” behavior that plays nice with VS:

1. **Behavior owns “current look target”** (entity / blockpos / worldpos + timeout)
2. Every AI tick:

   * validate target (still exists? still relevant?)
   * compute desired yaw/pitch
   * clamp + smooth
   * write `HeadYaw/HeadPitch` ([apidocs.vintagestory.at][1])
3. Periodically call the syncing path (what `SetHeadPositionToWatchedAttributes()` is for) so clients receive updates ([apidocs.vintagestory.at][3])
4. Let `EntityHeadController.OnFrame(dt)` do the per-frame pose application client-side ([apidocs.vintagestory.at][2])

If you tell me what your NPC base class is (custom `EntityAgent`? reusing vanilla humanoids?) and whether you need **server-authoritative gaze** (all players see the same) vs **client-local cosmetic gaze**, I can outline the cleanest wiring pattern for your setup.

[1]: https://apidocs.vintagestory.at/api/Vintagestory.API.Common.Entities.EntityPos.html "Class EntityPos | VintageStory API "
[2]: https://apidocs.vintagestory.at/api/Vintagestory.API.Common.EntityHeadController.html "Class EntityHeadController | VintageStory API "
[3]: https://apidocs.vintagestory.at/api/Vintagestory.API.Common.Entities.Entity.html "Class Entity | VintageStory API "
[4]: https://mods.vintagestory.at/amlib?utm_source=chatgpt.com "Animation Manager [OBSOLETE] - Vintage Story Mod DB"
[5]: https://mods.vintagestory.at/eel?utm_source=chatgpt.com "Entity Emote Library - Vintage Story Mod DB"
[6]: https://mods.vintagestory.at/jaunt?utm_source=chatgpt.com "Jaunt: Entity Movement System - Vintage Story Mod DB"
[7]: https://mods.vintagestory.at/show/mod/37571?utm_source=chatgpt.com "VSDOF - 6DoF Head Tracking for Vintage Story"
[8]: https://wiki.vintagestory.at/Modding%3AOther_Resources?utm_source=chatgpt.com "Modding:Other Resources - Vintage Story Wiki"
[9]: https://apidocs.vintagestory.at/api/Vintagestory.API.Common.html?utm_source=chatgpt.com "Namespace Vintagestory.API.Common | VintageStory API"

