# Automation Loop Implementation Approach (Client-First)

## Goal

Automate the mod test loop so the agent can launch the game, auto-load the test
world, execute a fixed set of `/polis` commands, collect logs, and exit with
minimal manual interaction.

This document is a proposed implementation approach and will be the basis for
code/scripts after approval.

## Approach summary

Client-first automation using:

- `flatpak run at.vintagestory.VintageStory --openWorld "<world>"` to skip menus
- X11 input scripting (xdotool) to:
  - focus the game window
  - open chat
  - run a command sequence
  - optionally exit to desktop
- Log scraping (`client-main.log` / `server-main.log`) for success signals

Server-only automation remains a fallback or phase-2 improvement.

## Inputs needed

- World name (string passed to `--openWorld`).
- Command list to run (ordered set of `/polis ...` commands).
- Chat key (default `t`, confirm if remapped).
- Preferred log location:
  - default Flatpak logs under `~/.var/app/.../VintagestoryData/Logs`
  - or explicit `--logPath` (absolute path, with Flatpak filesystem override).
- Window identification:
  - `WM_CLASS` or window title for reliable `xdotool search`.

## Proposed script flow (high-level)

1) Build + deploy mod (existing workflow).
2) Launch client with `--openWorld "<world>"`.
3) Wait for world load:
   - Option A: fixed delay (fast to implement, brittle).
   - Option B: wait until a log line appears in `client-main.log`.
4) Focus the client window (xdotool by class/title).
5) Open chat and submit commands:
   - send chat key, type `/polis ...`, send Enter
   - repeat for each command with short delays
6) Optional: capture screenshots or dump debug state via commands.
7) Exit the client (keystroke or kill process).
8) Tail logs and surface key `[polis]` lines in output.

## Reliability considerations

- Window focus: prefer `xdotool search --class` if WM_CLASS is stable.
- Timing: consider log-based "world ready" detection to avoid brittle sleeps.
- Chat input: ensure chat field is focused before typing commands (send key,
  then small delay).
- Avoid destructive commands; keep tests idempotent.

## Failure handling

- If the game doesn't appear, report and stop (no repeated launches).
- If logs do not contain expected markers within a timeout, report failure.
- If commands are rejected (permissions or missing bot), record log snippet and
  halt for manual review.

## Server-only fallback (future)

If client automation proves too brittle:

- Use `VintagestoryServer` directly via Flatpak.
- Point `serverconfig.json` to the test save.
- Run test commands from a server-side mod hook on world-ready.
- Exit server after tests complete and parse server logs.

