# STATUS.md — current state

The single source of truth for **what is true right now**: verification
levels, open issues, next steps. It is maintained *in place* — this is not
a journal. Pass-level history lives in `docs/reports/` (dated, frozen),
`docs/design/` (the job-system design doc carries the R2 status log), and
the commit log (the commit messages are written as the narrative).

Game target: **Vintage Story 1.22.7** (released 2026-08-16); 1.23 expected
before end of 2026.

## Current state

| Layer | Level | Notes |
|-------|-------|-------|
| 1.22.7 code port | **locally verified** | net10.0, hermetic csproj (`Polis.dll`), builds with 0 errors |
| Core loop (load → spawn → goto → verify) | **live verified** | the fire-and-verify discipline holds; short and long (100-block) gotos arrive; smoke mission PASS |
| Possession (player mounts a bot) | **live verified** | mount-based; the NaN seat crash is closed (the guard also zeroes NaN *motion* — see gotchas) |
| Oikistes agent (the 27B brain) | **live verified** | 2026-10-10 robustness pass: the body is an IDENTITY (persists across missions; one auto-respawn per boot, then it stays dead until the operator rebinds via `POST /oikistes/bot`; it never adopts another bot) and the `crew` tool is the only sanctioned way to size the worker roster (hard cap 8) — the old null-after-mission body contract is what grew an 18-bot swarm in one evening. The boot world scan now re-scans until the block count stabilizes (a fixed 2 s sleep scanned before the server had loaded the box's chunks and counted 4 of 103 soil on a plateau holding 1600+ — the same zero-based-terrain class as the world-pillar false alarm). Missions are HYGIENIC (2026-10-10, a0c7b3d): the boot sweep no longer kills the body or the operator's crew (it takes the pre-mission roster as its keep list) and the worker the mission spawns is despawned when the run ends — the world returns to exactly the pre-mission roster after every mission (the worker's unspent surplus dies with it; the next run re-mines if it needs more) |
| Block / inventory / workstation actions | **live verified** | mine, harvest, pickup, place, equip, the workstation set (grind, press, clayform, knap, seal, forge, anvil); placement is verified by oracle, never by the `ok` flag |
| Temporal-stability control (1.22 "sanity") | **live verified** | the `sanity` harness command: per-player meter query (watched attribute `temporalStability`, the blue gear), set + pin (re-asserted every second, godmode-style), and `storms` / `rifts` world-config switches (persisted AND live-cleared + broadcast). Needed to settle the world under daylock: a frozen clock keeps an active temporal storm open forever and spawned rifts never expire (2026-10-07: the meter sat at 0 and the screen carried the glitch overlay; settled with `sanity storms off; sanity rifts off; sanity 1`) |
| Jev decision loop (v5) | **measured** | three-tier cascade: Laya 421M noul pre-veto → Decider-2B readout → 27B doubt-arbiter; reflex model as of the FT-2 round: `qwen35-decider-2b-ft2`; reports in `docs/reports/` |
| R2 job system | **live verified** (M1 + M2 + J1) | goal grammar, 9-job catalog (knap added 2026-10-10 with its measured oracle - the flint knife/axe the bot now carries at base), deterministic compiler, 27B planner (precision 1.000 / coverage ~0.5, 5-way failure attribution). Live: mine 11.4 s, two-job external supply 8.5 s, endogenous harvest→sow 9.6 s, full P1 flint-tools chain (give×3 scaffolding → 2× knap on the consumed surface → knife + axe) 54 s. The engine's knapping facts measured along the way: the surface block is CONSUMED on completion (one surface per chip), the completion marker is the block going to air (the `LastAction` recorded at start is already `Ok:true` - it must never be the wait condition), and the output goes straight into the bot inventory (`CompleteKnapToBot`). Open: the surface item has no recipe (creative/decorative) - its endogenous source for the no-give P1 run is still to be settled). **J2 clayforming - DONE (2026-10-10):** the `clayform <x> <y> <z> <recipe> [speed]` harness command works end to end (recipe table live-probed: 40+ X-<color>-raw recipes; 1.22 clay items: clay-red / clay-blue only): it places its own game:clayform table via direct SetBlock (the placement check treats soil tufts as blocking - clear the target cell to air first, the only wrinkle on the flat plateau), drives the voxel sculpting (388 voxels ~5 s at speed 8; the bot needs clay in inventory), and on completion the table converts to a groundstorage holding the shaped raw item (4x crucible-red-raw collected live). **J3 pit-kiln firing - DONE (2026-10-10):** the 1.22 pit-kiln pipeline works end-to-end via the `kiln` harness (create/feed/ignite/ff/state driving the game's own BlockEntityPitKiln): floor converted to the game:pitkiln block, 11 build stages fed (5x dry grass, 2x sticks, 4x fuel), 20h burn, fast-forward, OnFired smelted crucible-red-raw -> **crucible-earthyorange-fired** (1.22 renamed red). The whole sequence must run in one live session (the pitkiln block is non-persistent - see open issues); the fired output lands in a persistent storage block in the hole and survives restarts. **J4 cooking - done 2026-10-10 (direct path)**: the 1.22 firepit cooks the INPUT slot (slot 1) via the item's own `DoSmelt` (raw meat -> cooked meat in ~36 s live; the pot is NOT required for single-ingredient food - it only matters for multi-ingredient meals in the cooking slots; a fired pot in the firepit is a no-op for meat). The earlier failed 16-min test had the meat in the wrong slot. Fuel = slot 0 (charcoal 1 per piece cooked), output = slot 2. **J5 eat - done 2026-10-10**: the shared `eat` command (PolisEatService, same core as forage) ate the firepit's cooked meat; two code-resolution bugs fixed on the way: the policy gate saw the unprefixed code ("redmeat-cooked" never matched the "game:redmeat-cooked" allow rule) and IsItem/ConsumeOne compared exact codes - both now resolve through AssetLocation, and the eat command re-counts after its auto-give  **Chain `pots` - live 2026-10-10 (run7, 197 s, all 6 jobs ok):** the whole ladder is now one R2 campaign (give clay + raw meat -> clayform table (raw item) -> pit-kiln fire (fired item) -> firepit cook (cooked meat) -> bot eats), jobs `clayform`/`kiln_fire`/`cook`/`eat` in r2/jobs.py + `_pots_stage` in r2-live-mission.py, template `pots` in r2/chains.py. Engine facts baked in: the campaign bot must WALK to each workstation (4.5 m reach; the engine's long goto declares failure while still walking - the executor polls actual distance and re-issues), `kiln create` only preserves a fireable item that is in the hole storage or passed as `[itemCode qty]` (no other input path exists), and the firepit cook is the item's own DoSmelt on the input slot|
| Building plan system | **live verified** | a building is data (`builds/*.json`); the executor climbs its own work, per-cell verified; the 25-block hut built in 131 s and looked at |
| Oikistes (settlement agent) | **live** | swappable brains (live switch; current deployment runs the 35B model-mux — the 27B box is on a different LAN, unreachable from the current game host), mod-owned autonomy (`free\|guarded\|strict`), lean tool surface — work only happens through the `mission` tool into R2. Since 2026-10-08 it runs as a **persistent service** (auto-restart; on CT 114 it was a nohup that silently died with the host migration) |
| Web UI | **live** | the instrument panel at `/polis/ui/`; design contract `docs/design/webui-design.md` + the mobile/field variant `docs/design/webui-mobile.md` (bottom tab bar, stage-first, pinned command bar, prominent STOP, GET-based clock — implemented 2026-10-04) |

**Where the models run** (roles — deployment details are operator-side, not
in this repo): Decider-2B FT on the 3060 card (~0.3 s/row), Laya 421M via
the openjev service, the 27B doubt-arbiter on a vLLM box, the 35B alt brain
on the model-mux box.

## Open issues

- **Client entity invisibility: resolved for the captured low-FPS failure (2026-10-08), live verified for 15 minutes.** The actual NaN writer is VS 1.22.7's `EntityBehaviorInterpolatePosition.OnRenderFrame`: unclamped speed feedback `Lerp(speed, target, dt * 4)` diverges below 2 FPS, overflows the float interpolation ratio, and writes NaN from finite snapshots. A diagnostic prefix/postfix caught the first write; an isolated regression against the installed engine reproduces it at frame 81. The version-scoped Harmony fix clamps only the speed-feedback factor, preserving elapsed dt and queue/physics behavior. The patched engine passes 280,000 regression frames, and the deployed game passes 31 live samples over 15 minutes with zero invalid client/server positions or interpolation writes. The operator shortened the original hours-long acceptance window; no hours-long live soak is claimed. Earlier hardware-corruption and stopped-packet conclusions are superseded: the probe incorrectly reflected `Attributes` as a property, and the repair query used horizontal radius zero. Both diagnostics are corrected; `/polis/entityhealth` independently reads the server's loaded dictionary. No host reboot, driver changes, or respawn watchdog were needed. Evidence and exact limitations: [root-cause report](docs/reports/2026-10-08-entity-interpolation.md); [upstream draft](docs/reports/2026-10-08-vs-interpolation-bug-report.md); [regression](tests/interpolation/README.md).

- **Campaign-path keep-drop (2026-10-10, fixed + proven): the `--keep-bots` list is now threaded through `run_campaign` too.** The 1cae166 fix had only reached the planner path; the operator-campaign path (`--jobs` / `--chain`) called `boot(pol)` without the keep list, so every chain run killed the Oikistes body and the crew on boot (witnessed 19:10-19:24, run 1's boot sweep). Fixed by a shared `_parse_keep(args)` used by both paths and recorded in the run JSON (`keep_bots`); the fix is PROVEN, not asserted: a 2-second wait campaign with the three canonicals in the keep list left all three standing (the pre-fix probe run killed all of them in the same shape). The body was rebound to the tools-carrying worker (335267) after the incident.

- **Cottage roof through a two-high door (open):** the cottage walls (2-high, 5×5, door) are standing at the base, but the mission's build_plan couldn't stand for the roof layer: the bot could not get inside through the 2-high door (the 30 wall cells went in; the 25 roof cells died `goto stuck`). The stand search is reach-aware but the *entry* problem (a bot pathing into a hollow through a 2-high opening) is a traverser/agent behavior question, not a search-geometry one. Options: single-high doorway + roofed interior (the agent fills the door last from inside), or a `climb`/`stair` job for the door edge, or a manual entry (operator positions the bot inside before the roof phase). The shell is in the world as-is; the roof is the next build-system debug item.

- **1.22 pit-kiln persistence quirk (engine bug report pending):** the `game:pitkiln` block
  is non-persistent (aux-style): `SetBlock` applies it in memory (the BE is created and works),
  but the chunk save reverts the cell to the previous block, so after any vsgame restart the
  kiln BE re-initialises on the soil floor and NREs (BEPitKiln.cs line 74, null Burning
  behavior). `TryCreateKiln` (the vanilla conversion) has no caller in any shipped class and
  the block's creative inventory is empty - the 1.22 hole-kiln flow appears effectively
  unreachable by vanilla means on a dedicated server. Practical rule: run the whole
  `kiln create -> crucible -> feed -> ignite -> ff` sequence in ONE live session; only the
  fired output (persistent storage block in the hole) survives.

- **5x5 ring dead-end (13.13):** single-bot face-placement cannot complete
  ring edges of 5+ at tier 2+ (runs 14–17 each died at a different wall
  cell; all rejections were correct). Options: harness standing-range 2,
  scaffold blocks, or cap single-bot rings at 3x3 (the proven,
  visually-verified building).
- **Roof-layer stand search — fixed (2026-10-10, c1b188f):** the
  stand-candidate search is now reach-aware: any stand cell within 2
  horizontal of the target with the target up to 3 above the feet
  (head room checked), ground-level positions preferred (the walk-in
  through the door) over wall-tops. The hut-flat run confirmed it.
  The hut-flat box itself (a FILLED 5x5 - "just a box full of dirt
  blocks", user-words) was cleaned out of the world (setblock air,
  48 perimeter + 13 interior cells); its successor is the `cottage`
  plan: walls two high + a full 5x5 roof layer, 55 dirt, every cell
  reachable from the ground inside (no wall-top climbs). The gable
  ridge stays a second phase until a stair job exists.
- **Missions run in the background (2026-10-10):** the old blocking
  mission held the agent, the chat lock and - through a 5-deep listen
  backlog - the user's web UI for the entire run (90-minute
  "Oikistes unreachable" windows; the web UI's asyncio proxy was
  never the blocker). Now: Popen + worker thread; dispatch returns at
  once, the digest and a no-goal `mission` call report running or the
  verdict, the 90-min cap and roster hygiene live in the worker. The
  brain choice persists across restarts (OIK_BRAIN=alt = the 27B).
- **Movement physics (top priority, since 1.21):** client prediction writes
  `Pos.Motion` directly, fighting the server's `interpolateposition`;
  smoothness unassessed.
- Tall-grass targeting: `gotolook` can target the grass block instead of
  the ground below → "no path".
- A* reports `no path` across unloaded chunks (spawn nearby for visual tests).
- Goto arrival snap: functionally exact, visually a ~0.5-block jump.
- The `place` command's `ok` signal is unreliable (phantom `ok=True` when
  the bot occupies the target cell); the oracle is the ground truth for
  placement.
- **The 1.22 item→block mapping wall:** mining granite yields
  `stone-granite` but place wants `rock-granite`; no public API maps items
  to blocks (the endogenous sow works around it via rye-on-farmland).
- **27B degeneration:** silent token loop on new vocabulary (e.g. "sow");
  a guard (finish=length / empty content → reject) is wanted.
- Looping animations don't play on the client; several action classes have
  no animation at all.
- Creative-mode caveat: no drops on mine/harvest (vanilla behavior) — run
  drop-dependent tests in survival.

## 1.22.7 environment gotchas (hit by any test/agent work)

- **World migration drops player moddata (field 15).** A 1.21-era world
  loses `createCharacter=true` on first 1.22 boot → the first-run dialog
  reappears every boot and suspends the embedded server's tick (all harness
  commands hang). Rescue: `POST /polis/admin/moddata` (set via the game's
  own `SetModData` — the dialog is unconfirmable headless).
- **Collectible namespaces moved.** `survival:stone`-style codes no longer
  resolve; content lives under plain / `game:` and hyphen-variant codes
  (`rock-granite`, `pickaxe-iron`, `packeddirt`). The harness uses a
  lenient resolver (as-is → stripped → `game:` → `survival:`); plant/
  harvest blocks are still not found under any tried namespace — open.
- **Possession NaN crash (fixed).** The seat exposed a shared mutable
  `EntityPos`; the client entity got a NaN position and the physics tick
  threw. The guard detects NaN in position *and* motion — vanilla's check
  inspects `Motion`, which `pos.ToString()` never prints, which is why the
  2026-09-27 crash looked clean. A NaN event is now a logged sanitize, not
  a death; viewer disconnect is safe.
- In-game the cursor is pointer-locked (re-centered at 512,384): absolute
  noVNC clicks don't land on in-game UI buttons; the keyboard works.
- `observer-screenshot --save` returns `filePath: null` (silent write
  failure; the base64 path works).
- **Temporal stability under a frozen clock (2026-10-07).** 1.22 renamed
  "sanity" to temporal stability (`SystemTemporalStability` +
  `ModSystemRifts`): the per-player meter is the watched attribute
  `temporalStability` (0..1; the blue gear above the hotbar). Temporal
  storms (world config `temporalStorms`) clamp it and drive the full-screen
  glitch; temporal rifts (`temporalRifts`) drain anyone standing near
  them. Both are scheduled on **calendar days**, so under daylock (frozen
  clock) an active storm never ends and spawned rifts never expire — the
  survival world wedged at 0% meter / glitch overlay / rifts piled up.
  Settled with the `sanity` command (persisted config + live zero +
  broadcast + pinned meter); the in-game `/worldconfig` changes the config
  but not the live system state. Public reference: the wiki pages
  "Temporal stability" and "Temporal rift".

## Next (in binding order)

1. **Survival pilot prep (current driver).** Design settled in
   `docs/design/food-hunger-skills-policies.md` (2026-10-04; ground truth
   from decompiling the 1.22.7 assemblies): hunger is a player-entity
   mechanism (`EntityBehaviorHunger`, synced `hunger` tree attribute,
   player.json declares it for every player entity; no human/bot
   distinction) — **it applies to our bots as-is**, and eating is a
   public-API call (`Entity.OnEntityReceiveSaturation`). Polis adds the
   decision layer: policy engine (food/wear/behavior allow-rules, one
   evaluator seam), `eat` action (inventory ops + the engine call — no
   reflection), food-pressure interrupt, light RimWorld-inspired skills
   (L1 hard req / L2 job threshold / L3 scaling). Build order: policies +
   eat → forage-eat in the pilot → skills with the copper milestone.
2. **First survival pilot** — dev-phase run (2026-10-07) in a fresh
   generated survival world with a flat/clear spawn (the barren
   `polis-pilot-1` was superseded by the generated `polis-survival-*`
   worlds on 2026-10-04/05): **bare start** (one approved initial food
   supply; no equipment), Oikistes-instructed missions through R2,
   bot respawn allowed while developing; the FINAL pilot enforces
   **permadeath** — "fresh start" = a new world once all bots are
   dead. Player runs in parallel in the normal player playstyle
   (godmode for now); player-as-stone deity mode is an optional world
   setting (concept under discussion — design doc to follow).
3. **Copper via the crucible** (clay-formed vessel in the firepit,
   charcoal; *not* the bloomery — that is iron/steel) — the first
   endogenous smelting milestone. Same "pot on fire" pattern as the
   food cooking pot: one capability family covers both.
4. **The 13.13 ring decision** (standing-range-2 / scaffold / 3x3 cap) —
   unblocks bigger single-bot buildings.
5. **Cross-mission memory** — persistent world model + episodic record +
   goal stack.
6. **Repair path** — failed mission → re-plan.
7. **27B degeneration guard** (see open issues).

(The 27B build-plan A/B gate and craft-verb work were completed and live-
verified during 2026-10-03/04; craft is in the table above.)

## History

Pass-level narrative: `docs/reports/` (dated, frozen),
`docs/design/job-system-r2.md` (the R2 design doc, §12/13 status log), and
the commit log. The pre-1.22.7 project history (vision, research, journals,
superseded decision loops) is frozen in `archive/`.
