# VintageStoryLib Decompile Notes (Phase 2 Prep)

This document summarizes closed-source engine findings from decompiling `VintagestoryLib.dll` for interaction pipelines.

## How to reproduce (short guide)

1) Locate the assembly (Flatpak install):
   - `/home/mf/.local/share/flatpak/app/at.vintagestory.VintageStory/x86_64/stable/*/files/extra/vintagestory/VintagestoryLib.dll`

2) Ensure `ilspycmd` is installed:
   - `which ilspycmd` should return a path (e.g., `/home/mf/.dotnet/tools/ilspycmd`).

3) List classes to find target types:
   ```bash
   ilspycmd -l c /path/to/VintagestoryLib.dll | rg -i "SystemMouseInWorldInteractions|ServerSystemInventory|ServerSystemBlockSimulation|ServerSystemEntitySimulation"
   ```

4) Decompile specific types to temp files:
   ```bash
   ilspycmd -t "Vintagestory.Client.NoObf.SystemMouseInWorldInteractions" /path/to/VintagestoryLib.dll > /tmp/vs_SystemMouseInWorldInteractions.cs
   ilspycmd -t "Vintagestory.Server.ServerSystemInventory" /path/to/VintagestoryLib.dll > /tmp/vs_ServerSystemInventory.cs
   ilspycmd -t "Vintagestory.Server.ServerSystemBlockSimulation" /path/to/VintagestoryLib.dll > /tmp/vs_ServerSystemBlockSimulation.cs
   ilspycmd -t "Vintagestory.Server.ServerSystemEntitySimulation" /path/to/VintagestoryLib.dll > /tmp/vs_ServerSystemEntitySimulation.cs
   ```

**Optional local shortcut (machine-specific, not for git):**
```bash
mkdir -p /path/to/repo/.external
ln -sf /path/to/VintagestoryLib.dll /path/to/repo/.external/VintagestoryLib.dll
```
Then decompile from `/path/to/repo/.external/VintagestoryLib.dll`.

5) Grep for key methods:
   ```bash
   rg -n "TryBeginUseActiveSlotItem|TryBeginUseBlock|HandleBlockPlaceOrBreak|TryModifyBlockInWorld|HandleEntityInteraction" /tmp/vs_*.cs
   ```

## Findings (engine-level)

### Client: item use vs block use
**Type:** `Vintagestory.Client.NoObf.SystemMouseInWorldInteractions`

- `TryBeginUseActiveSlotItem(...)`:
  - Calls `Collectible.OnHeldUseStart(...)`.
  - If `handling != NotHandled`, sets `controls.HandUse`, resets timers, and sends `SendHandInteraction(... StartHeldItemUse ...)`.
  - If stack empties, clears slot and `MarkDirty()`.

- `TryBeginUseBlock(...)`:
  - Calls `game.tryAccess(... Use)` before interacting.
  - If `OnBlockInteractStart` returns true:
    - sets `controls.HandUse = BlockInteract`
    - stores `HandUsingBlockSel`
    - sends `SendHandInteraction(... StartBlockUse ...)`

### Client: entity interaction
**Type:** `Vintagestory.Client.NoObf.SystemMouseInWorldInteractions`

- When right-clicking an entity and no block is selected:
  - Calls `Entity.OnInteract(...)` client-side with `EntitySelection.HitPosition`.
  - Sends `ClientPackets.EntityInteraction(...)` with `HitPosition` and `SelectionBoxIndex`.

**Decompile confirm (2026-01-06):**
- `SystemMouseInWorldInteractions` uses `entitySelection.HitPosition` for both local `OnInteract` and the packet payload.

### Server: held-use lifecycle
**Type:** `Vintagestory.Server.ServerSystemInventory`

- `OnUsingTick(...)`:
  - While `controls.HandUse != None`, calls `Collectible.OnHeldUseStep(...)`.
  - If step ends, calls `Collectible.OnHeldUseStop(...)`.

### Server: block placement / breaking
**Type:** `Vintagestory.Server.ServerSystemBlockSimulation`

- `HandleBlockPlaceOrBreak(...)`:
  - Builds `BlockSelection` from packet.
  - Enforces `TestBlockAccess(... BuildOrBreak)` and reverts client state on failure.

- `TryModifyBlockInWorld(...)` placement:
  - Range check uses `PickingRange + 0.7` unless `pickingrange` privilege.
  - Validates active slot + `EnumItemClass.Block`.
  - Rejects non-replaceable targets unless `ignoreServerReplaceableTest` or decor.
  - Rejects if another player intersects the placement.
  - Calls `Block.TryPlaceBlock(...)` and decrements stack (non-creative).

- `TryModifyBlockInWorld(...)` break:
  - Checks tool mining tier vs `RequiredMiningTier`.
  - Triggers `EventManager.TriggerBreakBlock(...)` (can modify `dropQuantityMultiplier`).
  - Calls `OnBlockBrokenWith(...)` or `OnBlockBroken(...)` depending on held item.

### Server: entity interaction validation
**Type:** `Vintagestory.Server.ServerSystemEntitySimulation`

- `HandleEntityInteraction(...)`:
  - Finds entity within `PickingRange + 10`.
  - Range check uses `SelectionBox` distance vs `GetAttackRange` (or default).
  - Uses packet `HitX/Y/Z` directly for `Entity.OnInteract(...)`.
  - Runs `TriggerPlayerInteractEntity(...)` before `OnInteract`.

**Decompile confirm (2026-01-06):**
- `HandleEntityInteraction` deserializes `HitX/Y/Z` into `Vec3d` and passes that directly to `OnInteract`.
- It also writes `EntitySelection.Position = val5` (packet hit position) when setting `CurrentEntitySelection`.

## Implications for bot interaction pipeline

- Use `OnHeldUseStart` and emulate `OnHeldUseStep/Stop` for held interactions.
- For block use, call `OnBlockInteractStart` and respect its return value.
- For entity interactions, pass `EntitySelection.HitPosition` unchanged (matches vanilla).
- For placement/break, follow the same validation order and use `TryPlaceBlock` / `OnBlockBrokenWith`.
