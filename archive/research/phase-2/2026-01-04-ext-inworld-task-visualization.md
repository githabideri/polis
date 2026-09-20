Below are the main patterns VS mods use for “UI in the world” (health bars, nameplates, icons), plus what to copy for billboard sprites and what to watch for at 50 NPCs.

## 1) How VS mods render UI elements attached to entities (health bars, names)

### Pattern A — Piggyback on the built-in nameplate system (fastest to ship)

If your “task indicator” can be expressed as **extra text** (e.g., `🛠 Smithing 42%`), the simplest route is to **extend/patch nameplate rendering** rather than inventing a new renderer.

Evidence this route is common:

* **NameTag Tweak** exists specifically to customize entity/player nameplates (“nametags visible above players and entities”). ([mods.vintagestory.at][1])
* **RPG Overlay** shows extra info “after the entity name” (levels/tiers), i.e., it’s clearly hooking the same “text above head” pathway. ([GitHub][2])

Upside: you inherit distance scaling, layout, etc.
Downside: **graphics** (icons/bars) are harder unless you start drawing textures yourself (or use special glyph fonts).

---

### Pattern B — Client-side custom renderer (`IRenderer`) + draw in screen-space (classic “Sims-like overlay”)

Mods can register a renderer that runs **every frame** via `IClientEventAPI.RegisterRenderer(IRenderer renderer, EnumRenderStage renderStage, ...)`. ([Vintage Story API Docs][3])
The `IRenderAPI` then gives you “GUI-mode” draw helpers like `Render2DTexture(...)` / `Render2DLoadedTexture(...)`. ([Vintage Story API Docs][4])

Workflow:

1. Register your renderer in a suitable render stage (often an “ortho/UI” stage).
2. Each frame, gather NPCs you want to show (distance + FOV filters).
3. Convert each NPC head position to a 2D screen position (projection step).
4. Draw icon + progress bar using `Render2DTexture` at that screen position. ([Vintage Story API Docs][4])

Upside: easiest to do “thought bubbles” (pure 2D overlay).
Downside: you must do your own projection + clutter management.

---

### Pattern C — World-space quads (a real “billboard mesh” in 3D)

VS’s matrix + render pipeline supports drawing textured quads in the world, very similar to how the game draws chest labels. The wiki’s ChestLabelRenderer example shows:

* building a `ModelMatrix` with translate/rotate/scale
* setting `ViewMatrix = rpi.CameraMatrixOriginf`
* then `rpi.RenderMesh(quadModelRef)` ([Vintage Story Wiki][5])

This pattern is ideal for an **icon panel floating above the head** that still lives in the 3D scene.

Upside: feels “in-world”; no explicit world→screen math needed.
Downside: you must implement billboarding (rotate to face camera) and handle transparency ordering.

---

## 2) Billboarded sprites/icons in VS — existing patterns to copy

### “2D overlay billboard” (always faces camera by definition)

Draw a 2D icon at the entity’s projected screen position using `IRenderAPI.Render2DTexture(...)`. ([Vintage Story API Docs][4])
This is essentially a billboard because it never rotates: it’s in screen space.

### “3D billboard quad” (faces camera in-world)

Copy the ChestLabelRenderer-style approach:

* use **player-relative coordinates** for precision (`CameraMatrixOriginf`) ([Vintage Story Wiki][5])
* construct `ModelMatrix` as: translate-to-entity-head → rotate-to-camera → scale
* draw a quad via `RenderMesh(...)` ([Vintage Story API Docs][4])

VS uses **column-major matrices**, and the order you write transforms is “backwards” relative to how they apply—worth remembering when your billboard rotates wrong. ([Vintage Story Wiki][5])

---

## 3) Performance expectations for many in-world UI elements (e.g., 50 NPCs)

### What existing mods do to stay sane

A lot of “over-head UI” mods **limit scope aggressively**:

* HealthBar mod shows bars above the head, but *only for the currently selected/hovered mob* (not every entity). ([mods.vintagestory.at][6])
* Simple Entity HealthBar added a nameplate feature but caps configurable max distance at **50 blocks** (explicitly citing usefulness/quality issues beyond that). ([mods.vintagestory.at][7])
* Extra Overlays describes itself as “only adds a health bar above the mob you are looking at.” ([mods.vintagestory.at][8])

So: 50 always-on indicators is doable, but you’ll want LOD rules.

### Practical guidance (based on VS API hooks you can leverage)

* **Distance/FOV culling**: hard cutoffs like 30–50 blocks match what other overlay mods do. ([mods.vintagestory.at][7])
* **Throttle updates**: keep rendering every frame, but recompute layouts/state (strings, widths) at e.g. 5–10 Hz.
* **Texture/atlas caching**: VS explicitly warns that rendering itemstacks into an atlas is “rather costly” and should be cached. ([Vintage Story API Docs][4])
* **Measure it**: `RegisterRenderer` lets you pass a `profilingName` so the frame profiler records renderer cost. ([Vintage Story API Docs][3])
* **Batching strategy**: prefer a small set of icon textures (atlas) and reuse meshes; avoid per-NPC allocations each frame.

Rule of thumb: the GPU usually won’t mind 50 tiny quads; the CPU cost comes from *per-entity logic*, projection, string measuring, and creating/updating textures.

---

## 4) VS mods with “thought bubble” / status indicator systems (what I found)

I didn’t find a ModDB entry explicitly advertising “thought bubbles” in the VS ecosystem from the searches above, but there are several strong “status indicator above head” references you can mine:

* **HealthBar** – clean HP bar above head, scales with distance, smooth animation; (currently) only for hovered/selected entity. ([mods.vintagestory.at][6])
* **Simple Entity HealthBar** – includes “Target Entity Nameplate” feature and explicit max-distance cap reasoning. ([mods.vintagestory.at][7])
* **Extra Overlays** – lightweight, “health bar above the mob you are looking at.” ([mods.vintagestory.at][8])
* **NameTag Tweak** – customization of nametags/nameplates over players and entities. ([mods.vintagestory.at][1])
* **RPG Overlay** – adds level info after the entity name (nameplate augmentation pattern). ([GitHub][2])
* **Item Pickup Highlighter** – has an “experimental feature to display names over items on the ground (when sneaking)”, i.e., another example of “world labels.” ([mods.vintagestory.at][9])

---

## A solid implementation direction for your NPC task indicators

If you want **Sims/Prison-Architect style** icons + progress:

* Start with **Pattern B (screen-space)** for speed: `IRenderer` + `Render2DTexture` for icon + bar. ([Vintage Story API Docs][3])
* Add culling (distance, on-screen) and consider “only show for selected NPC” as a fallback mode (mirrors existing mods). ([mods.vintagestory.at][6])
* If you want the indicator to feel physically “in the world” (occlusion, depth), migrate to **Pattern C** with a world-space quad and camera-facing rotation (ChestLabelRenderer-style). ([Vintage Story Wiki][5])

If you paste your current NPC/task data model (what you can access client-side, and how task progress is represented), I can sketch a concrete renderer structure (data sync + caching + culling + draw calls) that fits VS’s API patterns.

[1]: https://mods.vintagestory.at/nametagtweak?utm_source=chatgpt.com "NameTag Tweak - Vintage Story Mod DB"
[2]: https://github.com/LeandroTheDev/rpg_overlay "GitHub - LeandroTheDev/rpg_overlay: RPG HUD Overlay for Vintage Story"
[3]: https://apidocs.vintagestory.at/api/Vintagestory.API.Client.IClientEventAPI.html?utm_source=chatgpt.com "Interface IClientEventAPI | VintageStory API"
[4]: https://apidocs.vintagestory.at/api/Vintagestory.API.Client.IRenderAPI.html "Interface IRenderAPI | VintageStory API "
[5]: https://wiki.vintagestory.at/Modding%3AMatrix_Operations "Modding:Matrix Operations - Vintage Story Wiki"
[6]: https://mods.vintagestory.at/healthbar?utm_source=chatgpt.com "HealthBar - Vintage Story Mod DB"
[7]: https://mods.vintagestory.at/simplehealthbar?utm_source=chatgpt.com "/ Simple Entity HealthBar - Vintage Story Mod DB"
[8]: https://mods.vintagestory.at/extraoverlays?utm_source=chatgpt.com "Extra Overlays - Vintage Story Mod DB"
[9]: https://mods.vintagestory.at/show/mod/25352?utm_source=chatgpt.com "Item Pickup Highlighter - Vintage Story Mod DB"

