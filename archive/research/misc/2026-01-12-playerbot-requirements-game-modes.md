# PlayerBot requirements and game modes

Date: 2026-01-12

Purpose
Determine whether survival mode or other mods are required for PlayerBot usage, and note any game mode gating.

Summary
btca verification in the `vssurvivalmod` repo confirms `EntityPlayerBot` exists and includes Creative-only inventory-clearing logic on interact. btca verification in `vsapi` found no references to `EntityPlayerBot` or `playerbot.json`, indicating the bot is not an engine/API entity. The entity JSON definition (`playerbot.json`) is not present in the Survival mod repo, which suggests the entity definition is shipped via game assets rather than the mod repo itself. In `polis-builder-npc`, the default entity is `survival:playerbot`; if Survival assets are missing, spawn resolution fails and the user is instructed to enable Survival or provide a different entity code. There is no hard Survival dependency in `modinfo.json`, and the spawn logic falls back to any entity with path `playerbot`, so another mod could provide a compatible entity. Game mode is not required for bot usage beyond the Creative-only inventory clear in `EntityPlayerBot`.

Evidence
- Default bot code is `survival:playerbot` and spawn resolution errors tell users to enable the Survival mod: `polis-builder-npc/PolisBuilderNpcSystem.cs`
- README notes that `spawn` defaults to `survival:playerbot` and requires Survival mod: `polis-builder-npc/README.md`
- btca verification: PlayerBot implementation in Survival mod code: `docs/vssurvivalmod/Entities/EntityPlayerBot.cs`
- btca verification: Creative-only inventory clearing on interact: `docs/vssurvivalmod/Entities/EntityPlayerBot.cs`
- btca verification: `playerbot.json` not found in `vssurvivalmod` repo; likely defined in game assets (see local copy): `/home/mf/.local/share/flatpak/app/at.vintagestory.VintageStory/x86_64/stable/active/files/extra/vintagestory/assets/survival/entities/humanoid/playerbot.json`
- btca verification: `vsapi` contains no references to `EntityPlayerBot` or `playerbot.json` (not an engine/API entity)
- Mod metadata does not declare Survival as a dependency: `polis-builder-npc/modinfo.json`

Open questions
- Should the harness explicitly detect Survival mod presence via `World.EntityTypes` or mod list and surface a clearer error?
- Do we want a fallback custom bot entity if Survival is unavailable on target servers?

Implications for harness design
- Assume `survival:playerbot` exists only when Survival mod assets are loaded; validate entity type before spawning.
- Provide an option to specify a custom entity code in harness commands to avoid hard dependency on Survival.
- Do not gate harness usage on game mode, but document that some convenience actions (inventory clearing) are Creative-only.
