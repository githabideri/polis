## 1) Rendering custom screen overlays (HUD-style, drag rectangle)

### Where to draw: render stages

Vintage Story exposes render “stages” you can hook into. For a classic RTS selection box you usually want **2D/GUI (screen-space)** rendering:

* **`EnumRenderStage.Ortho`** = “Ortho mode for rendering GUIs and everything 2D” ([apidocs.vintagestory.at][1])
* If you ever need something *after* 3D post-processing but *before* the game’s UI, there are stages like **`AfterBlit`** and **`AfterFinalComposition`** ([apidocs.vintagestory.at][1]) — but the selection rectangle is typically easiest in **Ortho**.

### What you draw with: `IRenderAPI`

In Ortho you can draw simple quads/textures in screen-space. `IRenderAPI` is explicitly “to assist you in rendering pretty stuff onto the screen” ([apidocs.vintagestory.at][2]) and provides:

* Frame dimensions: **`FrameWidth` / `FrameHeight`** ([apidocs.vintagestory.at][2])
* Simple 2D texture drawing: **`Render2DTexture(...)`** (with optional color tint) ([apidocs.vintagestory.at][2])

**Practical selection-rectangle approach (works well):**

* Create (or reuse) a **1×1 white texture** (or a small solid texture).
* When dragging, compute `xMin/xMax/yMin/yMax` in pixels.
* Draw:

  1. A translucent filled quad (scale the 1×1 texture to rect size using `Render2DTexture`)
  2. Four thin quads for the border (or one line-mesh if you prefer)

That avoids Cairo/GUI dialogs entirely and keeps it “HUD overlay”.

### Registering a renderer

The wiki’s rendering/modding materials point you toward registering render hooks for custom drawing (HUD overlays, screen overlays, shaders, etc.) ([wiki.vintagestory.at][3]). The common pattern is:

* Implement an `IRenderer` (for a render stage, render order)
* Register it on the **client side**
* Unregister/dispose on shutdown

Even if you don’t find a perfect “selection box” example, the HUD overlay pattern is the same: keep a little state (dragging? start/end mouse) and draw every frame in Ortho.

---

## 2) Entity picking/selection in VS

### Single-entity under cursor: ray tracing

For click-select (or for issuing commands at a target), you want the built-in ray selection helpers. The **client world accessor** inherits multiple overloads of:

* `RayTraceForSelection(... ref BlockSelection, ref EntitySelection, ...)` including overloads that take:

  * start/end points (`Vec3d, Vec3d`)
  * a `Ray`
  * and variants with filters ([apidocs.vintagestory.at][4])

So a typical click-select flow is:

1. Build a ray from camera position forward (or use an existing helper your mod already has for “what am I looking at?”).
2. Call `RayTraceForSelection(...)`
3. Read back `EntitySelection` (if any), then decide if it’s one of *your* bots.

*(The API gives you the raycast and selection structs; the camera→ray construction is the part you wire from client camera state/input.)*

### Multi-select via drag rectangle: two workable strategies

#### Strategy A (common + simplest): project entities to screen, test against rectangle

Instead of trying to “raycast a rectangle,” do this:

1. **Choose candidates**
   Don’t iterate *every entity in the universe*. Use:

   * `GetEntitiesAround(centerPos, horRange, vertRange, callback)` ([apidocs.vintagestory.at][4])
   * or iterate `LoadedEntities` (client cache) if you already have your own filtering list, but be mindful it’s “internal cache” ([apidocs.vintagestory.at][4])

2. **Project world → screen**
   `IRenderAPI` exposes the **default view/projection matrices** and explicitly mentions using them for projections in Ortho via `MatrixToolsd.Project()`:

   * `PerspectiveViewMat` and `PerspectiveProjectionMat` ([apidocs.vintagestory.at][2])

3. **Rectangle test**
   If projected `screenX/screenY` lies inside your drag rectangle *and* depth indicates it’s in front of the camera, consider it selected.

This is the standard RTS technique and is usually plenty accurate if you project something sensible (entity center or head position).

#### Strategy B (more “correct” but more work): build a selection frustum and test bounding boxes

If you want “true” 3D rectangle selection:

* Convert the 2D rectangle corners into four world-space rays, build frustum planes, then test entity AABBs against it.
* VS exposes a **`DefaultFrustumCuller`** on `IRenderAPI` ([apidocs.vintagestory.at][2]) which hints at the engine’s own frustum-culling utilities you can lean on.

Most mods start with Strategy A because it’s fast to implement and easy to debug.

### Highlighting selected entities

VS has a built-in block highlight mechanism (not entity highlight):

* `HighlightBlocks(...)` exists on the world accessor ([apidocs.vintagestory.at][4])

For **entities**, you typically implement one of these:

* **Ground ring / billboard marker** rendered in-world near the entity feet (custom mesh, simple shader).
* **Particles** around the entity (cheap + obvious).
* **Tinting** via custom entity renderer/shader changes (powerful, but invasive—often more effort than you want early).

If you want “Starcraft-like” clarity, ground rings + optional “healthbar-ish” overlay markers usually read best.

---

## 3) Existing mods with multi-entity selection (what’s close)

I didn’t find an obvious “RTS-style multi-unit selection” mod in the sources I pulled up quickly. What *does* exist and is useful as reference code/approach:

* **Item Pickup Highlighter**: highlights dropped items and demonstrates the general “highlight things in-world” UX pattern (hotkey, render/visual feedback) ([GitHub][5])
* **SpawnHighlight**: highlights spawnable blocks in a radius (again, visual highlight patterns + input toggle) ([GitHub][6])
* The official vanilla modules include **vscreativemod** (world-edit style tooling exists there, even if it’s primarily block/region selection) ([GitHub][7])

So: you may not get a ready-made “unit box select” implementation to copy, but you *can* lift patterns from:

* world-edit style selection UX (creative tools)
* highlight mods for “selected set feedback”

---

## 4) Input handling for drag operations (mouse down → drag → up, modifiers, conflicts)

### Mouse events you can hook

On the client event API you have:

* `MouseDown`, `MouseMove`, `MouseUp` ([apidocs.vintagestory.at][8])

Those are the backbone for drag selection:

* **MouseDown**: if conditions are right, begin drag, store start (x,y)
* **MouseMove**: update current (x,y)
* **MouseUp**: finalize selection, clear drag state

### Preventing conflicts with normal controls

This is the part that usually bites you.

If you start drag-select on plain LMB, you’ll fight:

* block breaking / attacking
* interaction logic
* GUI focus, etc.

Common solutions:

1. **Require a “command mode” modifier** (e.g., hold Alt, or a dedicated hotkey toggles “squad command mode”) before drag-select engages.
2. When you *do* engage drag-select, mark the event handled (VS events support handled-ness; the mouse events are part of the event system you subscribe to) ([apidocs.vintagestory.at][8]) so the game doesn’t also treat it as “break block”.

### Modifier keys: shift add, ctrl toggle

Typical RTS behavior:

* **No modifier**: replace selection
* **Shift**: add-to-selection
* **Ctrl**: toggle membership

Implementation detail:

* On MouseUp, you compute the “hits” set.
* Then apply set logic based on modifier state (from current keyboard state / input API), before storing the final selected-entity IDs.

---

## A concrete implementation sketch (putting it together)

**State you keep client-side**

* `bool isDragging`
* `Vec2i dragStart, dragNow`
* `HashSet<long> selectedEntityIds`

**On MouseDown**

* If not in GUI, and (modifier held OR command-tool active):

  * `isDragging = true`
  * `dragStart = dragNow = mousePos`
  * mark event handled (so the world doesn’t also “attack/mine”) ([apidocs.vintagestory.at][8])

**On MouseMove**

* If `isDragging`: update `dragNow`

**Renderer (Ortho)**

* If `isDragging`: draw the rectangle using `IRenderAPI.Render2DTexture` ([apidocs.vintagestory.at][2]) in `EnumRenderStage.Ortho` ([apidocs.vintagestory.at][1])

**On MouseUp**

* If `isDragging`:

  * `isDragging = false`
  * Compute rect (normalize min/max)
  * Enumerate candidate entities via `GetEntitiesAround` ([apidocs.vintagestory.at][4])
  * Project each candidate with `PerspectiveViewMat` + `PerspectiveProjectionMat` (docs explicitly call out using these for projections in Ortho) ([apidocs.vintagestory.at][2])
  * If inside rect: add to `hits`
  * Apply modifier logic (replace/add/toggle)
  * Update your highlight visuals for entities

That’s enough to get Age-of-Empires style box selection working, then you can iterate on:

* selection filtering (only your bots, only in same “squad”, line-of-sight rules, etc.)
* better visuals (rings/outline/shader)
* command issuing (right-click target point, attack-move, follow, formation)

If you want, I can also outline a “server-safe” command protocol (client selects locally → sends entityId list + command to server → server validates ownership/range → dispatches AI tasks), but the above should get you to the first playable selection box quickly.

[1]: https://apidocs.vintagestory.at/api/Vintagestory.API.Client.EnumRenderStage.html "Enum EnumRenderStage | VintageStory API "
[2]: https://apidocs.vintagestory.at/api/Vintagestory.API.Client.IRenderAPI.html "Interface IRenderAPI | VintageStory API "
[3]: https://wiki.vintagestory.at/index.php/Modding%3ARendering_API/en "Modding:Rendering API - Vintage Story Wiki"
[4]: https://apidocs.vintagestory.at/api/Vintagestory.API.Client.IClientWorldAccessor.html "Interface IClientWorldAccessor | VintageStory API "
[5]: https://github.com/tacf/vs-itempickuphighlighter "GitHub - tacf/vs-itempickuphighlighter: Vintage Story Mod that highlights items dropped on the ground"
[6]: https://github.com/JeanSummers/spawnhighlight "GitHub - JeanSummers/SpawnHighlight: Vintage Story mod for highlighting hostile mob spawn locations"
[7]: https://github.com/anegostudios?utm_source=chatgpt.com "Anego Studios - GitHub"
[8]: https://apidocs.vintagestory.at/api/Vintagestory.API.Client.IClientEventAPI.html "Interface IClientEventAPI | VintageStory API "

