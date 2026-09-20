# Known Issues

## Pathfinding

- **Tall Grass Targeting:** While bots can pathfind *through* tall grass (thanks to the Harmony patch), selecting a target via `/polis gotolook` or clicking on tall grass might result in the bot trying to navigate to the grass block itself rather than the ground below. This is partially mitigated but can still cause "no path" errors if the target is technically "in the air" (the grass block).
- **~~Goto overshoot~~:** FIXED. Increased arrival threshold to 0.7 blocks and added position snap on arrival (zeroes momentum, snaps X/Y/Z to exact target). Previously bot would slide ~0.5-1 block past target or climb onto adjacent obstacles. Now bot stops exactly at target position.
- **Goto arrival snap (low priority):** The fix above causes the bot to visually "snap" or "teleport" the last ~0.5 blocks to the target position. Functionally correct but not visually smooth. Revisit when walking code is revised.
- Straight-line fallback can route into holes or steep drops. Default is off; use only for debugging.
- A* can report `no path` when bots are far away or in unloaded chunks. Spawn nearby for visual testing.

## Debug Visualization

- Path visualization uses block highlights (semi-transparent blocks), not a line mesh.
- Bot highlight is a block outline at the bot's current block; there is no entity glow.
- No server-side screenshot command; add a client hook or harness hotkey to trigger screenshots for automated visual tests.
- Polisbot renders as a flat, pale humanoid because `extraskinnable` is disabled and the base texture is `seraph-naked-hairless`.

## Interactions

- Place actions require a valid block source. `placeheld` uses the player's active hotbar block or the bot's right-hand block; otherwise it fails.
- `/polis activate` via `servercmd` can return `No block at target position` if coordinates are not absolute (`=x =y =z`) or if `l[]` selection is unavailable server-side.
- `/polis activate` LOS validation can return `No line of sight to target` for doors or other partial blocks even when the bot is adjacent (raytrace hits non-target blocks).
- **Creative mode prevents drops:** When the controlling player is in Creative mode, `mine`, `harvestcrop`, and similar block-breaking actions will remove blocks but **not spawn drops**. This is vanilla VS behavior (`Block.OnBlockBroken` skips drops for Creative players). Switch to Survival mode for drop-dependent testing.
- Creative mode can make bot damage/kill tests confusing; validate deaths in survival or by inspecting `/polis/state` health.
- Lantern activation via `/polis activate` succeeds but does **not** toggle lantern light on/off (observed in-game).
- Open question: chairs appear to be activatable but may not have a visible sit interaction (player can sit via keybind). Need to confirm whether chairs are meant to be interactable and whether vanilla/vsvillage NPCs can sit.
- Open question: bot activation of containers opens the UI for the player (caller is player). For VISION, we may want a bot-only activation path that does not open player UI.
- Open question: berry bushes (`BlockBehaviorHarvestable`) did not visibly change or drop items when activated in creative mode. Likely same cause as "Creative mode prevents drops" above; re-test in Survival to confirm.
- Open question: player corpse (EntityPlayerCorpse) interaction via `/polis interact` does not open inventory UI; may require a different interaction path or entity-id based harness command. Interact actions do not record `LastAction` yet.

## Coordinates + Visibility

- Player HUD coordinates may be offset from server world coordinates (observed ~+256 on X/Z). Use `/polis list` or the F3 debug overlay for absolute coordinates when spawning or moving bots.

## Mine Autocollect

- **~~Autocollect timing bug~~:** FIXED. Added 1.2s delay before `CollectDrops()` in mine/harvest/harvestcrop actions. Items now spawn and become collectible before collection attempt.

## Pickup/Drop

- Pickup can fail with `inventory full, nothing transferred` even after a drop. Playerbot inventory constraints need investigation.
- Pickup can fail with `CanCollect returned false` for ~1s after an item spawns; wait before retrying.
- Pickup succeeds reliably in survival mode (granite drop/pickup, flax harvest/pickup verified). Creative mode failures are due to drops not spawning (see Interactions section).
- Dropped items can leave the search radius quickly, causing `No item entity found nearby` unless you sample soon after drop or increase range.

## Harvest

- **~~Berry bush harvest drops go to player inventory~~:** FIXED. When `autocollect` is enabled, `harvest` now bypasses vanilla `OnBlockInteractStop` (which gave items to player) and directly inserts items into bot inventory. Tested with resin and ripe blueberry bushes - items correctly go to bot's hands/backpack.

## Animations

- **Looping animations don't play visually:** The `animate <code> <speed> loop` command returns success but the animation doesn't play on the client. One-shot animations work correctly (both API and visual). The looping flag may not be properly applied or synced.
- **Action classes have no animations:** `PolisMineBlockAction`, `PolisHarvestBlockAction`, and `PolisHarvestCropAction` do not trigger any animations. Only `PolisGotoAction` (walk/run) and `PolisButcherEntityAction` (looping hit) have animation support.
- **PolisPressAction bot animation not visible:** The press action triggers the fruit press block animation correctly, but the bot's "hit" animation doesn't play visibly. The code calls `AnimManager.StartAnimation("hit")` but it may not sync to clients. Needs research into existing animations (vanilla and mods like vsvillage) before implementing a proper workstation interaction animation.

## Block Placement

- **~~Bot `place` command returns "notreplaceable"~~:** FIXED. Was passing clicked surface position instead of target air position to `BlockSelection.Position`.
- **~~Bot walks into target position~~:** FIXED. The `GetApproachPosition` calculation was sending the bot to the target (air) position instead of the surface. Now calculates approach position as the clicked surface block position.
- **~~LOS validation too strict~~:** FIXED. Removed LOS validation for place command since `PolisPlaceBlockAction` already validates distance and VS's `TryPlaceBlock` has its own validation.

## Inventory

- **~~Backpack slots not shown in state~~:** FIXED. The `/polis/state` endpoint now queries inventory slots 17 and 18 (backpack equipment slots) and reports equipped backpacks in the `Backpack` array.
- **~~Place command doesn't consume blocks~~:** FIXED. `PolisPlaceBlockAction` was using `TakeOut()` which doesn't reliably modify entity inventory slots. Changed to direct stack size modification matching `PolisDropItemAction` pattern.

## CLI (poliscli.py)

- **targets --query doesn't filter:** The `--query` parameter on the targets command doesn't filter results by block code. Workaround: use jq filtering on raw curl output.
- **Global flags must come after subcommand:** Use `polis look --player UID`, not `polis --player UID look`. This is an argparse limitation with subparsers.
- **~~container-contents coordinate parsing~~:** FIXED. Use positional args for coordinates (`container-contents 224 3 270`) or `-c` flag for names (`container-contents -c main-chest`).

## Agentic Workflow Issues

- **~~Silent action failures for range~~:** FIXED. `takefrom`, `putinto`, `harvest`, and `harvestcrop` now pre-validate range and return immediate "Out of range" errors instead of starting then failing.
- **Other silent failures:** Some actions may still return `Ok: true` on start then fail later. Always check `state` after actions to verify success.

## Entity Discovery

- **~~targets excludes dead entities~~:** FIXED. `GET /polis/targets?mode=entities&includeDead=true` now includes dead entities. Each entity result includes an `Alive` field.
- **~~No loot corpse action~~:** FIXED. Use `loot <entityId>` command to transfer remaining items from a dead entity's harvestable inventory to bot inventory. Works on already-butchered corpses.

## State Visibility

- **~~Backpack contents not shown in state~~:** FIXED. The `/polis/state` endpoint now includes `BackpackContents` field showing items inside equipped backpacks. Format is `[[{Code, Qty}, ...], ...]` (array per backpack).

## Butcher/Loot

- **~~Carcass transformation not triggered by bot loot~~:** FIXED. The `loot` command now calls `EntityBehaviorDeadDecay.DecayNow()` after emptying the corpse inventory, triggering the same transformation VS does when a player closes an empty corpse UI. The response includes `carcassSpawned` and `carcassBlockCode` fields.
- **Carcass is a block, not entity:** After transformation, the carcass is a block (`game:carcass-tiny`) that can be mined to yield `game:bone-tiny`. Use `targets --mode blocks -s carcass` to find them.
- **Missing meat drops:** Butchering chickens via bot only yields feathers, not meat. Needs investigation - may be related to the butcher action not fully replicating player behavior.
- **Bot doesn't face target or crouch during butcher:** The butcher action now plays a looping hit animation for ~1s before harvesting, but the bot doesn't turn to face the corpse or crouch. Facing/crouching still TODO.
- **Player corpses not harvestable:** Player corpses from the `playercorpse` mod (`playercorpse:playercorpse` entity) cannot be butchered or looted - they use a different interaction system than animal corpses with `EntityBehaviorHarvestable`.
