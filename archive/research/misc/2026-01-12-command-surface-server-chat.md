# Command Surface (Server/Chat)

**Date:** 2026-01-12

## Purpose
Document which polis-builder-npc commands are chat-only vs programmatically invokable, and recommend the command channel for the agentic harness.

## Summary
- `/polis` chat commands are registered server-side and require a live player (`RequiresPlayer`) with a required privilege (`RequiresPrivilege`), so they are not suitable for headless or server-only automation.
- The HTTP test harness exposes a smaller, explicit command surface (`spawn`, `select`, `stop`, `give`, `drop`, `pickup`, `goto`, `teststate`, `bots`) that executes on the server thread without a player context.
- A local-only escape hatch (`POST /polis/servercmd`) now executes raw server/chat commands via `ChatCommands.ExecuteUnparsed` with wildcard privileges.
- Client hotkeys map to chat commands; they are convenience wrappers and still require a connected client.
- Recommendation: expose harness automation via the HTTP command surface and expand its explicit command list as needed rather than invoking chat commands directly.

## Evidence
- Chat command registration and constraints: `polis-builder-npc/PolisBuilderNpcSystem.cs` (RegisterCommands, `RequiresPrivilege(Privilege.chat)`, `RequiresPlayer()`), subcommands including `spawn`, `list`, `select`, `selectlook`, `despawn`, `goto`, `gotolook`, `preview`, `stop`, `activate`, `break`, `place`, `placeon`, `placeheld`, `equip`, `give`, `interact`, `pickup`, `drop`, `validate`, `debug`, `pathdump`, `entitytypes`, `manage`, `panic`, `possess`, `unpossess`, `teststate`.
- HTTP harness routing and local-only listener: `polis-builder-npc/PolisTestHarness.cs` (`HttpListener` on `http://localhost:8585/`, routes `/polis/state`, `/polis/bots`, `/polis/command`, `/polis/servercmd`).
- HTTP command mapping: `polis-builder-npc/PolisBuilderNpcSystem.cs` (`ExecuteHarnessCommand` switch with available commands list).
- Client hotkeys send chat commands: `polis-builder-npc/PolisBuilderNpcHotkeys.cs` (e.g., `RegisterHotkey(..., "/polis spawn")`).
- Harness documentation listing endpoints and commands: `polis-builder-npc/docs/TECHNICAL.md` (HTTP Test Harness section).
- VS API definitions (btca: `vsapi`): `vsapi/Common/API/ICoreAPI.cs` (`IChatCommandApi ChatCommands { get; }`), `vsapi/Common/API/ChatCommand/IChatCommand.cs` (`RequiresPlayer()` and `RequiresPrivilege(string)` defined on `IChatCommand`), `vsapi/Common/API/ChatCommand/IChatCommandApi.cs` (`TextCommandCallingArgs`, `TextCommandResult`, and chat command API surface).

## Open questions
- Should the HTTP harness expand to include `activate`, `break`, `place`, and `interact`, or keep those chat-only until selection/LOS rules are formalized?
- Is localhost-only access sufficient, or should an explicit auth token be added before exposing additional destructive commands?
- Should HTTP commands honor the same land-claim/permission checks used by chat commands (currently some harness paths bypass player context)?

## Implications for harness design
- Use HTTP as the primary automation surface; it is server-side, playerless, and already returns structured results.
- Keep the command list explicit and minimal to reduce unintended side effects and to enforce safety constraints separately from chat.
- Treat chat commands and hotkeys as manual/debug tools, not as automation entry points.
- Maintain a local reference snapshot of vanilla server commands in `docs/SERVER_COMMANDS.md` for quick lookup.
