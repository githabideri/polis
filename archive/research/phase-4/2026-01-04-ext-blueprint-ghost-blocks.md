Below is what I found about how Vintage Story typically does (and exposes) “ghost / preview” rendering, what existing mods do, and what that implies for a blueprint→NPC construction system.

---

## 1) How Vintage Story renders block placement previews

### What the engine exposes (and what it doesn’t)

Vintage Story’s modding API **does expose a general-purpose client rendering hook**, not a “ghost block” feature specifically:

* You can register a per-frame renderer via `api.Event.RegisterRenderer(IRenderer, EnumRenderStage, ...)`. ([apidocs.vintagestory.at][1])
* There is a dedicated render stage for transparency: `EnumRenderStage.OIT` (Order Independent Transparency). ([apidocs.vintagestory.at][2])
* The standard shader path is accessible via `IRenderAPI.PreparedStandardShader(...)`, explicitly meant for custom rendering and mentions controlling things like `ColorMul`. ([apidocs.vintagestory.at][3])

So: **there isn’t a “ghost block API” as a first-class concept** in the docs I found; the building blocks are **(a)** “render a mesh at positions” + **(b)** “choose transparent stage / shader parameters”.

### The semi-transparent preview and red “invalid” indicator

Mechanically, both “valid vs invalid placement” previews boil down to:

1. Determine *what would be placed* and *where* (block + orientation + target position), and whether it’s valid (game rules / collision / replaceability / support checks).
2. Render that block mesh with a **tint**:

* “valid” → normal/white-ish translucent
* “invalid” → red translucent

This exact pattern is mirrored by popular building-QoL mods that implement their own preview: **VanillaBuildingExpanded** explicitly advertises a “real-time ghost preview” and “invalid placement positions highlighted in red”. ([mods.vintagestory.at][4])

A useful historical gotcha: at least in older versions, placement preview behavior was sometimes attributed to mods (e.g., VSHUD) rather than core; a GitHub issue thread literally notes “VSHUD adds the placement preview.” ([GitHub][5])
So if your mental model is “the vanilla preview is surely a neat reusable subsystem,” that may be a shaky assumption across versions/modpacks. The safe plan is: **implement your own preview renderer**.

### “Can I invoke the vanilla preview programmatically at arbitrary positions?”

I didn’t find a documented “call vanilla placement preview renderer at position X” API. What *is* clearly supported is the lower-level approach:

* register your own renderer (`RegisterRenderer`) ([apidocs.vintagestory.at][1])
* draw meshes using the standard shader (PreparedStandardShader / ColorMul control) ([apidocs.vintagestory.at][3])
* draw them in `EnumRenderStage.OIT` for translucency ([apidocs.vintagestory.at][2])

That’s exactly how the “schematic projection / ghost blocks” mods do it conceptually.

---

## 2) Existing VS mods with schematics / blueprints (what to learn from)

### WorldEdit-style tooling (built-in + ecosystem)

* **World Edit** is a built-in toolset in Vintage Story (commands + GUI). ([wiki.vintagestory.at][6])
* Export/import is commonly **JSON-based** in practice: a forum answer describes copying a selection “into external json file” and pasting later. ([Vintage Story][7])
* Under the hood, WorldEdit uses `BlockSchematic` packing/transforming in the call stack (useful as a hint for format/structure and transforms). ([GitHub][8])
* **Carbon Copy** exists to export builds to WorldEdit-compatible formats outside pure creative workflows. ([mods.vintagestory.at][9])

This matters for you because it suggests: you can likely reuse *ideas* / formats / transforms, but vanilla WorldEdit workflows are “place blocks,” not “survival blueprint highlight.”

### Actual “ghost block projection” mod (closest to your goal)

**[Beta]Schematica** is almost exactly what you described: it loads schematics and renders **translucent ghost blocks** to guide placement, with **color-coded state** (white empty spot, red incorrect block) and even a layer-by-layer mode. ([mods.vintagestory.at][10])

Even if you don’t copy code, its feature list is a blueprint (pun intended) of UX patterns that players already accept in VS.

### “Builder’s guide” / placement preview mods

* **VanillaBuildingExpanded**: build hammer adds “block preview rendering” + snapping + red invalid highlights. ([mods.vintagestory.at][4])
* **Building Gadgets**: bulk building helper inspired by Minecraft’s Building Gadgets (not exactly blueprints, but relevant for previewing lots of placements). ([mods.vintagestory.at][11])

Takeaway: the community norm is “client-side ghost visualization layered over the world,” not “place special non-solid ghost blocks into the actual chunk data.”

---

## 3) Rendering many ghost blocks simultaneously (100+ blocks)

### The performance lever you really want: instancing + batching

Vintage Story’s render API includes `RenderMeshInstanced(...)`, explicitly for drawing “a given mesh” many times with per-instance custom data. ([apidocs.vintagestory.at][3])

Practical implication for a 100–10,000 block blueprint:

* **Group by mesh key**: (block type + variant + rotation) → one MeshRef
* For each group, draw all instances via **one instanced call** (or a small number of calls), instead of 1000 individual draws.

### Opacity / color for multiple states

At the API level you can rely on:

* **standard shader + `ColorMul`** style tinting to encode state (planned / invalid / missing mats / in progress). ([apidocs.vintagestory.at][3])
* Or, if you go instanced, push per-instance state in custom instance attributes (so you don’t need one draw call per color).

Schematica demonstrates a proven UX mapping already: white = missing/empty, red = wrong. ([mods.vintagestory.at][10])
You can extend that:

* green/blue = “assigned / ready”
* yellow = “missing materials”
* purple = “reserved by worker”
  …but keep it configurable for accessibility.

### Memory/resource pitfalls

If you generate/upload lots of meshes dynamically, you **must manage MeshRef lifetime**. There’s at least one report of memory leaks when MeshRefs aren’t disposed. ([wiki.vintagestory.at][12])
So: cache meshes aggressively, and dispose on unload / blueprint removal.

### Showing construction progress

VS blocks are discrete, so “partially built block” usually needs one of these patterns:

1. **Replace target with a custom “construction frame” block** (server-side) that visually progresses (variants/meshes) until it becomes the real block.
2. **Keep world unchanged, overlay progress** (client-side) by rendering a second overlay (e.g., wireframe fill amount, or a tint intensity proportional to progress).
3. **Hybrid**: only place a single “blueprint anchor” block entity; everything else is overlay until completion.

Given you also want NPCs to “gradually build,” #1 tends to feel best in-game (players see a scaffold), but #2 is cheapest technically.

---

## 4) Client-side vs server-side blueprint architecture (recommended split)

### Don’t confuse “visualization” with “authority”

A robust multiplayer setup usually separates:

* **Client-only preview**: while the player is still positioning/rotating the blueprint before committing.
* **Server-authoritative blueprint**: once committed, the server owns the blueprint + job list so NPC workers and all players agree.

This matches how VS rendering hooks work: renderers are client-side (`RegisterRenderer` on the client API). ([apidocs.vintagestory.at][1])

### Syncing between players

Once committed:

* Server stores blueprint data (anchor position, list of planned blocks, per-block state).
* Server broadcasts deltas (added/removed blocks, state changes like “reserved,” “built”) to nearby clients / relevant players.
* Clients render ghost blocks from replicated state.

### Saving/loading blueprints to files

You have three pragmatic options:

1. **Reuse the “WorldEdit external JSON” idea**
   The community already uses exported JSON selections via WorldEdit workflows. ([Vintage Story][7])

2. **Adopt an existing schematic mod format**
   Schematica already “save selections to schematic files” and supports rotate/mirror and chiseled voxel preservation. ([mods.vintagestory.at][10])
   If your mod can import that format, you instantly gain an ecosystem.

3. **Define your own format**
   If NPC construction needs extra metadata (required tool tier, work time, material staging, forbidden blocks), a custom format may be cleaner—while still allowing import/export bridges.

---

## What this implies for your end goal (blueprint → translucent blocks → NPC jobs)

The least brittle approach in Vintage Story looks like:

* **Blueprint = data model on server** (authoritative task list + persistence)
* **Ghost rendering = client renderer** registered in `EnumRenderStage.OIT` ([apidocs.vintagestory.at][1])
* **Rendering scale**: batch by mesh and use `RenderMeshInstanced` when blueprints get large ([apidocs.vintagestory.at][3])
* **State coloring**: shader tint (`ColorMul`) + conventions proven by Schematica (white vs red) ([apidocs.vintagestory.at][3])
* **File I/O**: start by supporting WorldEdit-esque JSON exports (known demand), then optionally import Schematica format ([Vintage Story][7])

If you want, I can turn this into a concrete technical plan with:

* a suggested blueprint data schema (including rotation/mirroring),
* a renderer batching strategy (mesh cache keys + per-instance attributes),
* and a multiplayer message protocol (commit / delta updates / permissions / chunk-range streaming).

[1]: https://apidocs.vintagestory.at/api/Vintagestory.API.Client.IClientEventAPI.html?utm_source=chatgpt.com "Interface IClientEventAPI | VintageStory API"
[2]: https://apidocs.vintagestory.at/api/Vintagestory.API.Client.EnumRenderStage.html?utm_source=chatgpt.com "Enum EnumRenderStage | VintageStory API"
[3]: https://apidocs.vintagestory.at/api/Vintagestory.API.Client.IRenderAPI.html "Interface IRenderAPI | VintageStory API "
[4]: https://mods.vintagestory.at/vanillabuildingexpanded?utm_source=chatgpt.com "VanillaBuilding: Expanded - Vintage Story Mod DB"
[5]: https://github.com/anegostudios/VintageStory-Issues/issues/777?utm_source=chatgpt.com "1.14.7 stable - object placement preview issue with lantern in ... - GitHub"
[6]: https://wiki.vintagestory.at/How_to_use_WorldEdit?utm_source=chatgpt.com "How to use WorldEdit - Vintage Story Wiki"
[7]: https://www.vintagestory.at/forums/topic/8903-save-or-schematic-files-of-builds/ "Save or schematic files of builds? - Questions - Vintage Story"
[8]: https://github.com/anegostudios/VintageStory-Issues/issues/885?utm_source=chatgpt.com "World edit copy/paste doesn't work for bigger selections (75* ... - GitHub"
[9]: https://mods.vintagestory.at/show/mod/1574?utm_source=chatgpt.com "Carbon Copy - Vintage Story Mod DB"
[10]: https://mods.vintagestory.at/show/mod/29880 "[Beta]Schematica - Vintage Story Mod DB"
[11]: https://mods.vintagestory.at/show/mod/3262?utm_source=chatgpt.com "Building Gadgets - Vintage Story Mod DB"
[12]: https://wiki.vintagestory.at/Modding%3ASchematics?utm_source=chatgpt.com "Modding:Schematics - Vintage Story Wiki"

