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
| Block / inventory / workstation actions | **live verified** | mine, harvest, pickup, place, equip, the workstation set (grind, press, clayform, knap, seal, forge, anvil); placement is verified by oracle, never by the `ok` flag |
| Temporal-stability control (1.22 "sanity") | **live verified** | the `sanity` harness command: per-player meter query (watched attribute `temporalStability`, the blue gear), set + pin (re-asserted every second, godmode-style), and `storms` / `rifts` world-config switches (persisted AND live-cleared + broadcast). Needed to settle the world under daylock: a frozen clock keeps an active temporal storm open forever and spawned rifts never expire (2026-10-07: the meter sat at 0 and the screen carried the glitch overlay; settled with `sanity storms off; sanity rifts off; sanity 1`) |
| Jev decision loop (v5) | **measured** | three-tier cascade: Laya 421M noul pre-veto → Decider-2B readout → 27B doubt-arbiter; reflex model as of the FT-2 round: `qwen35-decider-2b-ft2`; reports in `docs/reports/` |
| R2 job system | **live verified** (M1 + M2) | goal grammar, 8-job catalog, deterministic compiler, 27B planner (precision 1.000 / coverage ~0.5, 5-way failure attribution). Live: mine 11.4 s, two-job external supply 8.5 s, endogenous harvest→sow 9.6 s |
| Building plan system | **live verified** | a building is data (`builds/*.json`); the executor climbs its own work, per-cell verified; the 25-block hut built in 131 s and looked at |
| Oikistes (settlement agent) | **live** | swappable brains (live switch; current deployment runs the 35B model-mux — the 27B box is on a different LAN, unreachable from the current game host), mod-owned autonomy (`free\|guarded\|strict`), lean tool surface — work only happens through the `mission` tool into R2. Since 2026-10-08 it runs as a **persistent service** (auto-restart; on CT 114 it was a nohup that silently died with the host migration) |
| Web UI | **live** | the instrument panel at `/polis/ui/`; design contract `docs/design/webui-design.md` + the mobile/field variant `docs/design/webui-mobile.md` (bottom tab bar, stage-first, pinned command bar, prominent STOP, GET-based clock — implemented 2026-10-04) |

**Where the models run** (roles — deployment details are operator-side, not
in this repo): Decider-2B FT on the 3060 card (~0.3 s/row), Laya 421M via
the openjev service, the 27B doubt-arbiter on a vLLM box, the 35B alt brain
on the model-mux box.

## Open issues

- **~~Client-side entity reaping~~ RESOLVED (2026-10-07/08) — it was never a client reaper:** the bots-vanishing-after-a-few-minutes symptom was **degradation of the game host's iGPU 3D path** (driver state, not the game): two failure modes (silent entity-pass death; native segfaults in the host log), bisection (old mod / fresh spawn / old world) all innocent, and the same chip + Mesa + binaries on a different host renders entities from the first frame. The pilot world moved to that healthy host the same night (host details in the private `services/polis/`). Lesson for the next host: if entities vanish while the data layer says they're standing still, check the host's 3D/driver state before suspecting the client; a cold full-stack reset (VNC server + game, in order) is the in-place palliative, a host reboot the cure.
- **5x5 ring dead-end (13.13):** single-bot face-placement cannot complete
  ring edges of 5+ at tier 2+ (runs 14–17 each died at a different wall
  cell; all rejections were correct). Options: harness standing-range 2,
  scaffold blocks, or cap single-bot rings at 3x3 (the proven,
  visually-verified building).
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
