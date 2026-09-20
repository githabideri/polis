# Claims enforcement patterns for interaction

Date: 2026-01-13

Purpose
Confirm how vanilla enforces land-claim checks for Use vs BuildOrBreak, and map those checks to bot actions (activate/use vs place/break).

Summary
- btca queries failed because the tool could not `git fetch` (network-restricted). Findings below rely on local `vsapi` and local `vssurvivalmod` sources.
- In the API layer, land-claim access is represented by `EnumBlockAccessFlags` with `BuildOrBreak`, `Use`, and `Traverse`.
- Player block interaction uses `EnumBlockAccessFlags.Use` in `Block.OnBlockInteractStart(...)` before running behaviors.
- Block placement uses `EnumBlockAccessFlags.BuildOrBreak` in `Block.CanPlaceBlock(...)` before allowing placement.
- Vanilla survival content consistently uses `Use` for container/open/activate interactions and `BuildOrBreak` for placement/break/reshape actions.
- For bot actions, mirror vanilla by using `Use` for activate/open/containers and `BuildOrBreak` for placement/breaking. Break enforcement details are in engine code (not present in `vsapi`), so treat this as an assumption until `btca` or engine sources confirm.

Evidence
- `vsapi/Common/API/EnumBlockAccessFlags.cs` defines the flags: `BuildOrBreak`, `Use`, `Traverse`.
- `vsapi/Common/API/ILandClaimAPI.cs` defines `TestAccess(...)` and `TryAccess(...)`; `TryAccess` also sends an error to the player and marks the block dirty.
- `vsapi/Common/Collectible/Block/Block.cs`:
  - `Block.OnBlockInteractStart(...)` calls `world.Claims.TryAccess(byPlayer, blockSel.Position, EnumBlockAccessFlags.Use)`.
  - `Block.CanPlaceBlock(...)` calls `world.Claims.TryAccess(byPlayer, blockSel.Position, EnumBlockAccessFlags.BuildOrBreak)`.
- `vssurvivalmod/BlockEntity/BEOpenableContainer.cs` uses `TryAccess(..., EnumBlockAccessFlags.Use)` before opening containers.
- `vssurvivalmod/Systems/Barrel/BlockBarrel.cs` uses `TryAccess(..., EnumBlockAccessFlags.Use)` on barrel interactions.
- `vssurvivalmod/Block/BlockGroundStorage.cs` uses `TryAccess(..., EnumBlockAccessFlags.Use)` for open/interaction and `TryAccess(..., EnumBlockAccessFlags.BuildOrBreak)` for placing/adding.
- `vssurvivalmod/Item/ItemWrench.cs` uses `TryAccess(..., EnumBlockAccessFlags.BuildOrBreak)` for wrench actions.
- `vssurvivalmod/Systems/Microblock/BEChisel.cs` uses `TryAccess(..., EnumBlockAccessFlags.BuildOrBreak)` for chisel modifications and `TryAccess(..., EnumBlockAccessFlags.Use)` for opening the chisel interface.

Example code paths (file + method)
- `vsapi/Common/Collectible/Block/Block.cs`: `OnBlockInteractStart(...)` → `TryAccess(..., EnumBlockAccessFlags.Use)`
- `vsapi/Common/Collectible/Block/Block.cs`: `CanPlaceBlock(...)` → `TryAccess(..., EnumBlockAccessFlags.BuildOrBreak)`
- `vsapi/Common/API/ILandClaimAPI.cs`: `TestAccess(...)` / `TryAccess(...)` (access API and messaging semantics)
- `vssurvivalmod/BlockEntity/BEOpenableContainer.cs`: container open/interaction path → `TryAccess(..., EnumBlockAccessFlags.Use)`
- `vssurvivalmod/Systems/Barrel/BlockBarrel.cs`: barrel interact path → `TryAccess(..., EnumBlockAccessFlags.Use)`
- `vssurvivalmod/Block/BlockGroundStorage.cs`: open interaction → `TryAccess(..., EnumBlockAccessFlags.Use)`; place/add → `TryAccess(..., EnumBlockAccessFlags.BuildOrBreak)`
- `vssurvivalmod/Systems/Microblock/BEChisel.cs`: chisel edits → `TryAccess(..., EnumBlockAccessFlags.BuildOrBreak)`; chisel UI open → `TryAccess(..., EnumBlockAccessFlags.Use)`

Which flag to use
- Activate/use (block interaction, containers, doors, right-click behaviors): `EnumBlockAccessFlags.Use`.
- Place/break (block placement or destruction): `EnumBlockAccessFlags.BuildOrBreak`.

Open questions
- Where exactly is claim enforcement for block breaking implemented (engine-side `BlockAccessor`/`BreakBlock`), and does it always use `BuildOrBreak`?
- Are there vanilla container interactions that use `BuildOrBreak` instead of `Use` for any edge cases (e.g., chiseling/reshaping blocks)?

Implications for harness design
- Bot action validation should call `ILandClaimAPI.TryAccess(player, pos, EnumBlockAccessFlags.Use)` for activation/interaction flows, and `EnumBlockAccessFlags.BuildOrBreak` for placement/breaking.
- Use `TryAccess` rather than `TestAccess` when you want vanilla-style player-facing failure messaging and block dirtying; otherwise use `TestAccess` for pure checks.
