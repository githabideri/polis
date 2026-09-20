# Automation Loop Findings (Client/Server, Flatpak)

## Why this research exists

Polis Builder NPC development is fast on research and code, but slow at the
manual test loop: launch game, load a test world, run a few commands, close,
read logs, repeat. The goal is to automate as much of this loop as possible
while staying compatible with the Flatpak install and the current mod workflow.

## Project context

- Mod: polis-builder-npc (universal client + server mod).
- Target game: Vintage Story 1.21.6 (Flatpak install).
- Host OS: Fedora 41, X11 session (X11 automation is viable).
- User data path (Flatpak): `~/.var/app/at.vintagestory.VintageStory/config/VintagestoryData`
- Logs path (Flatpak default): `.../VintagestoryData/Logs`

## Key findings (local, verified)

### Client entrypoint and CLI flags

- Flatpak command: `flatpak run at.vintagestory.VintageStory`
- Client binary lives at:
  - `/home/mf/.local/share/flatpak/app/at.vintagestory.VintageStory/x86_64/stable/active/files/extra/vintagestory/Vintagestory`
- `--openWorld <worldname>` bypasses the menu and starts loading immediately.
- Client `--help` output (verified) includes:
  - `--openWorld`, `--connect`, `--pw`, `--tracelog`, `--dataPath`, `--logPath`,
    `--addModPath`, `--addOrigin`, `--rndWorld`, `--playStyle`, etc.

### Server entrypoint and CLI flags

- Server binary exists and is runnable via Flatpak:
  - `/app/extra/vintagestory/VintagestoryServer`
- Verified invocation:
  - `flatpak run --command=/app/extra/vintagestory/VintagestoryServer at.vintagestory.VintageStory -- --help`
- Server `--help` output includes:
  - `--genconfig`, `--setconfig`, `--withconfig`, `--dataPath`, `--logPath`,
    `--append`, `--ip`, `--port`, `--maxclients`, `--standby`, etc.

### Server world selection (already configured)

- `serverconfig.json` under Flatpak data path points to:
  - `WorldConfig.SaveFileLocation` = `.../Saves/test-lands.vcdbs`
- Saves exist at:
  - `/home/mf/.var/app/at.vintagestory.VintageStory/config/VintagestoryData/Saves`

### Bundled server control script (reference)

- The shipped `server.sh` (in the Flatpak extra folder) runs:
  - `dotnet VintagestoryServer.dll --dataPath "<path>"`
- It sends `/stop` to the server via `screen` "stuff" commands.
- This is an upstream pattern for server control, useful for automation logic.

### Macros path

- Macros directory exists:
  - `/home/mf/.var/app/at.vintagestory.VintageStory/config/VintagestoryData/Macros`
- No macros present by default (empty directory).

## Why this matters for automation

- Client automation is possible with `--openWorld`, reducing menu time to near
  zero.
- Flatpak exports a server binary, enabling a headless test loop if needed.
- X11 session allows input automation tooling (xdotool, etc.).
- Logs are in a stable path and can be tailed for pass/fail cues.

## Open questions for implementation

- How to detect "world fully loaded" in the client loop (timed wait vs log cue).
- Whether to prefer client automation (xdotool) or server-only harness first.
- How to shutdown the client cleanly in scripted runs (keystroke vs process).

