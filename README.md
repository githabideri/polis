# Polis

A Vintage Story mod for a **"Deity RTS with Possession"**: spawn controllable
humanoid NPCs (polisbots), direct them with `/polis` chat commands or hotkeys,
and *possess* one to control it directly — with an autonomous-behavior layer
around it (jobs, building plans, a settlement agent).

- **Mod id:** `polis` (renamed from the working title `polis-builder-npc`; the old id only ever existed in private test worlds)
- **Game version:** Vintage Story **1.22.7** (port target; see `STATUS.md`)
- **License:** MIT (`LICENSE`)
- **Side:** universal (client + server; possession is client-side)

## What this repo is

Polis is the substrate of a research project into one-pass, calibrated
decision models (the "Jev" model class) driving in-game agents. The repo
therefore contains the whole stack, not just the mod:

| Path | What |
|------|------|
| `src/` | **All** C# source (the csproj stays at the root — that root *is* the mod folder: `modinfo.json` + `assets/` + the built DLL, which is what Vintage Story loads and what a `.vspackage` zips). In `src/`: the mod entry, bot entity, possession, network, event-stream and screen-capture backbone files, plus `src/Actions/` (mine, harvest, pickup, place, workstations, A* navigation), `src/Core/`, `src/Commands/`, `src/Harness/` (the in-game HTTP harness — the agent-facing API), `src/Gui/`, `src/Helpers/`. The Oikistes agent is Python (`scripts/oikistes.py`) driving that API; version-porting facades (`src/Compat/<ver>/`) are the stated future discipline — see DESIGN |
| `modinfo.json`, `assets/` | Mod manifest + entity definitions |
| `r2/` | The **R2 job system**: the pure Python decision/execution core (reflex-state projection, job queue, building plans, embodiment checks, world model), pinned by the contract gate in `tests/reflex/` |
| `scripts/` | Live tooling: `poliscli.py` (harness CLI), `jev-loop-v5.py` (the three-tier decision loop: reflex model → 2B decider readout → 27B doubt-arbiter), `oikistes.py` (the settlement agent with swappable model brains), `r2-live-mission.py`, `jevab/` (model A/B + fine-tuning measurement harness) |
| `tools/webui/` | The web UI — the instrument panel over the harness (state, commands, live view, Oikistes chat) |
| `builds/` | Buildings as data: JSON plans the executor compiles into per-cell verified builds |
| `data/` | Frozen measurement data: decision-loop runs, labeled corpora, fine-tune rows, A/B results — the scientific record behind `docs/reports/` |
| `models/decider-2b/` | Inference subset of the public Decider 2B (config, tokenizer, Python engine; weights live on Hugging Face — see its README) |
| `tests/` | Contract gate (decision replays, prompt byte-identity) and aim verification |
| `docs/` | Living reference: command surface, harness API, design docs, dated reports, `proofs/` visual evidence |
| `archive/` | **Frozen** history: pre-1.22.7 vision/technical/roadmap, dev journals, research notes, superseded decision loops (v1–v4) |
| `STATUS.md` | Current state, verification levels, open issues — **the single status source** |
| `DESIGN.md` / `TESTING.md` / `AGENTS.md` | Architecture contract / how we verify / rules for AI agents working in this repo |

## Quick start (dev)

```sh
cp .env.example .env   # point VINTAGE_STORY / VSDATA at your Vintage Story install
./build.sh             # dotnet build -> bin/Release/Mods/polis
./build.sh --deploy    # + copy into the game's Mods dir
```

The build is hermetic: only `.env` values, no machine-specific paths in the
csproj or scripts. Start the game and the mod loads; the in-game harness
listens on loopback by default (set `POLIS_HARNESS_IP` to expose it on the
LAN — that is what the web UI uses). Then:

```sh
scripts/poliscli.py status          # worldReady?
scripts/poliscli.py spawn
scripts/poliscli.py goto 100 64 -200 --wait 10
scripts/poliscli.py state           # ALWAYS re-read after actions
```

The web UI is served by the harness from the mod folder under `/polis/ui/`
(no build step; files are read per request, so a copy + refresh is a deploy).
Testing methodology, the mission protocol and the verification vocabulary:
`TESTING.md`.

## Porting to a new game version

The mod targets one game version at a time (currently 1.22.7; 1.23 is
expected before end of 2026). The 1.22 port was done against the API
directly (five small drift fixes); from the next port, version-specific API
usage is isolated in `src/Compat/<ver>/` facades so a version bump is a new
facade directory + a csproj TFM bump, not a repo-wide rewrite (the "version
shim law" — `DESIGN.md`).

## Publishing

One tree, three views:

1. **Gitea (primary):** `gitea/polis` — the development repository.
2. **GitHub (community mirror):** `githabideri/polis` — the same sanitized
   tree; the mod is MIT-licensed.
3. **Vintage Story Mod DB** (`mods.vintagestory.at`) — the distribution
   channel for the mod package, built from this source.

**Sanitization is a standing rule of this repo:** no internal hostnames,
network addresses, or credentials anywhere in the tree or the history.
Measurement environments are written as *roles* ("the game testbed", "the
CPU batch box", "the 3060 card"); endpoints come from env vars and
arguments. Deployment-specific operational knowledge (how *our* testbed
container is wired up) deliberately lives outside this repo.
