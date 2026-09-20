# Polis

A Vintage Story mod for a **"Deity RTS with Possession"**: spawn controllable
humanoid NPCs (polisbots), direct them with `/polis` chat commands or hotkeys,
and *possess* one to control it directly — with an autonomous-behavior layer
planned around it (colony management, jobs, economy).

- **Mod id:** `polis-builder-npc` (keep this id; it is what worlds and servers reference)
- **Game version:** Vintage Story **1.22.7** (port target; see `STATUS.md`)
- **License:** MIT (`LICENSE`)
- **Side:** universal (client + server; possession is client-side)

## Repo map

| Path | What |
|------|------|
| `src/` | Mod code. `src/Compat/` = **version shim** (see below) |
| `src/Harness/` | In-game test harness command handlers |
| `scripts/` | `poliscli.py` (CLI), `vsctl.py`, test runners, smoke tests |
| `tools/` | Web UI + browser test assets |
| `tests/world/` | Pristine testbed world (`.vcdbs`) |
| `docs/` | Living reference docs (commands, harness, radar map plan) |
| `ops/` | CT-114 testbed operations (VNC/game stack) — private detail, sanitized |
| `archive/` | **Frozen** history: pre-1.22.7 vision/technical/roadmap, journals, research, old issue tracker |
| `DESIGN.md` | Architecture & design contract |
| `STATUS.md` | Current state, verification levels, open issues — **the single status source** |
| `TESTING.md` | How to test (harness, missions, verification vocabulary) |
| `AGENTS.md` | Rules for AI agents working in this repo |

## Quick start (dev on the CT-114 testbed)

```sh
source .env          # VINTAGE_STORY=/opt/vintagestory/extra/vintagestory, VSDATA=...
./build.sh           # dotnet build -> bin/Release/Mods/polis-builder-npc
./build.sh --deploy  # + copy into the game's Mods dir
systemctl restart vsgame   # then connect via noVNC (see ops/CT114-VNC.md)
```

## Version shim law

The mod targets one game version at a time. **All version-dependent API
usage goes through `src/Compat/`** — one namespace per game version
(currently `Compat/VS122/`). Mod code never calls a version-specific API
directly; it calls a Compat facade. When VS ships 1.23 (expected before
end of 2026), the port = new `Compat/VS123/` facade + csproj TFM bump,
**not** a repo-wide rewrite.

## Publishing

Two tracks, kept separate:
1. **Private:** Gitea `gitea/polis` (primary, all history, ops docs).
2. **Public:** GitHub mirror + VS mod store listing — sanitized copy only
   (no host names, IPs, ops docs, session details). The public copy's
   `ops/` and any machine-specific content is excluded by the mirror
   script.
