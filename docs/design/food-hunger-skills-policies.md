# Design — food, hunger, policies & skills (survival pilot)

Status: **proposed** (engine facts below verified by decompiling the
1.22.7 assemblies; nothing in this doc is implemented yet). Owner: the
polis layer.
Constraint that shapes everything: *whatever lands now must let a full
system tie in later without big code rewriting* — so every pillar is
data-driven with one evaluation seam.

## 1. Verified engine facts (1.22.7 — decompiled ground truth)

*(Second revision, 2026-10-04. The 1.22.7 assemblies were decompiled
(ilspycmd) and read directly; this section is what the code says.)*

- **The hunger behavior is `EntityBehaviorHunger`, defined in the
  first-party `essentials` mod** (`Mods/VSEssentials.dll` — on disk and
  referenceable, though we do not need to). The state is a **synced
  server-side tree attribute** on the entity: `WatchedAttributes["hunger"]`
  with `currentsaturation` / `maxsaturation` (the player entity JSON
  declares `{ code: "hunger", currentsaturation: 1500, maxsaturation: 1500,
  saturationlossdelay: 180 }`) plus the five nutrition levels
  (`fruitLevel` … `dairyLevel`) and five `saturationlossdelay*` values.
  All changes `MarkPathDirty("hunger")` — the client only renders it
  (the green HUD bar).
- **It is a player-entity mechanism, not a human-client mechanism.** The
  behavior is declared in `assets/game/entities/humanoid/player.json` —
  every server-side player entity gets it. Its `OnGameTick` runs per
  instance and skips **only** non-survival game modes; there is no
  human-vs-bot check. Activity detection reads `EntityControls`
  (TriesToMove / Sprint / mouse buttons) — exactly what our movement code
  sets — so a moving bot drains faster than an idle one. 10-second drain
  cycle: 0.96×counter (+1.5×sprint), ÷4 when idle >3 s, scaled by calendar
  speed and `Stats.GetBlended("hungerrate")` (off-hand, cold, class are
  stat modifiers on the same entity; world config `playerHungerSpeed`).
  In 1.22.7 **no animal entity declares it** (the code is
  EntityAgent-generic — animal hunger is architecturally possible, not
  wired up).
- **Eating is a public-API call.** The API's `Entity` base declares the
  documented virtual
  `OnEntityReceiveSaturation(float saturation, EnumFoodCategory foodCat,
  float saturationLossDelay, float nutritionGainMultiplier)`;
  `EntityBehaviorHunger` implements it (clamps to max, raises the
  matching nutrition level by `saturation/2.5×mult` unless already full,
  keeps the max delay, updates the nutrient health boost, syncs). The
  vanilla eat flow (survival mod decompiled): per-ingredient
  `FoodNutritionProperties` → that method per ingredient → consume the
  stack → drop the `EatenStack` → body-temperature adjustment. A mod can
  make an entity eat **using only `VintagestoryAPI`** — no reflection, no
  reference into game assemblies.
- **Starvation is engine damage**: `Saturation <= 0 →
  ReceiveDamage(DamageSource{ Type = EnumDamageType.Hunger }, 0.125)`
  every 10 s — the same death path for a bot as for a human. A built-in
  server command can print/set a player's satiety/health/oxygen (the
  setter clamps 0–1 of max) — a ready-made debug lever.
- **Item nutrition is public**: `CollectibleObject.NutritionProps` /
  `GetNutritionProperties()` (`Satiety`, `Health`, `FoodCategory`,
  `SaturationLossDelay`, `Intoxication`, `Psychedelic`, `EatenStack`, …);
  XSkills compiles against it in 1.22.
- 1.22 item *use* is still not a callable API (only `OnHeldInteract*`
  callbacks; `IPlayer` is thin) — but the eat action does not need it.
  Engine "skills" remain a slot, not a model (`ItemSlotSkill` +
  `ISkillItemRenderer`).
- Mods for comparison: *Max's Simple Starvation* (1.22-current:
  reinterprets the bar as stomach→weight, `StatModifiers`-based
  weight effects), *Realistic Starvation* (1.19-era, kJ energy balance;
  notes vanilla saturation ≈ 2× calories).
- Recalled from the craft work: sticks are foraged, not craftable; copper
  melts in a **melting pot** on a campfire (charcoal), not a bloomery;
  bloomery = iron/steel; the world carries 12,995 grid recipes
  (`/polis/recipes`).

**Consequence:** the engine already keeps the entire hunger state for our
bots — polis never invents a second meter. Polis (a) **reads**
`WatchedAttributes["hunger"]` on the bot entity (public API types — no
reflection), (b) treats low `currentsaturation` as the interrupt
condition, (c) implements `eat` as inventory ops +
`OnEntityReceiveSaturation` per ingredient (the engine does clamping,
nutrition, delays, the health boost, client sync — the bot's own HUD will
show the bar), and (d) reads food values from the item's `NutritionProps`
in the policy engine. What polis adds is the *decision* layer: what to
eat, when, where to get it, and how it feeds skills.

## 2. The three pillars

### A. Food & hunger (read the engine meter, decide in polis)

- **Food state (per bot):** straight from the engine —
  `entity.WatchedAttributes.GetTreeAttribute("hunger")` on the bot's
  player entity (`currentsaturation`, `maxsaturation`, the five
  `*Level` nutrition bars, the five delay values — all public API types,
  no reflection; the built-in server entity command prints the same for
  quick checks). Polis keeps only derived decision state: a
  `foodPressure` threshold (e.g. `currentsaturation < 25% of max`, or
  falling with nothing in inventory) and the last eat event.
- **EAT action.** Harness command `eat [itemCode]` and an r2 job type
  `eat`. Implementation: pick the best inventory stack the policy engine
  allows → for each ingredient's `NutritionProps`: call the engine's
  `OnEntityReceiveSaturation(satiety, foodCategory, delay, multiplier)`
  on the bot's entity (documented public virtual — the engine applies
  clamping, nutrition levels, delays, the health boost, and client sync)
  → consume the stack → drop the `EatenStack` (optionally the body-
  temperature adjustment vanilla does). No reflection, no references into
  game assemblies, stable across 1.2x while the API keeps the virtual.
  One live check remains: confirm the bot's entity instance actually
  carries the `hunger` tree (expected — player.json declares it for every
  player entity).
- **Hunger interrupt.** In the mission loop, `foodPressure` above
  threshold preempts the current job at a safe checkpoint (same tier as
  the navigation-wedge interrupt): forage (berry bushes) → carry → eat.
  Thresholds and the "safe checkpoint" rule are data, not code.
- **Starvation is an engine event, not a mystery**: satiety 0 →
  `EnumDamageType.Hunger` damage 0.125 per 10 s → death. A bot dying of
  hunger is a foraging-pipeline bug, reportable as such (the damage type
  is unambiguous). *Max's Simple Starvation*-style weight re-weighting is
  out of scope; `StatModifiers` is the door if we ever want it.

### B. Policy engine (the interaction-rules layer)

The RimWorld idea of *rules for what a pawn may consume, wear and do* —
implemented once, domain by domain:

```json
// polis-policies.json (committed, versioned; the mod reads it)
{ "version": 1,
  "domains": {
    "food": {
      "default": "deny",
      "rules": [
        { "match": { "category": "Fruit" },            "allow": true,  "priority": 10 },
        { "match": { "code": "vs:cooked-venison" },    "allow": true,  "priority": 20 },
        { "match": { "code": "vs:raw-*" },             "allow": false, "priority": 30 }
      ]
    },
    "wear":  { "default": "deny", "rules": [] },
    "behavior": { "default": "allow", "rules": [] }
  } }
```

One evaluator: `PolicyEngine.Evaluate(domain, itemOrAction) → (allow,
reason)`. The pilot ships the `food` domain only; `wear` and `behavior`
start empty. A future full system (per-pawn profiles, UI, conditions)
replaces the file schema and the evaluator internals — the call sites
(planner filter, eat action, any future use-check) never change.

### C. Skills (RimWorld-inspired, deliberately lighter)

- **State:** per-bot `SkillSet` (persisted mod state): `{ name, xp,
  level }`. XP curve borrowed from the XSkills mod (its `xlib` framework,
  kept for reference in gitignored `research/xskills/`):
  `xpForLevel(n) = expBase * expMult^(n-1)`.
- **XP source:** completed actions, through a data table
  (`chop→forestry`, `mine→mining`, `craft→crafting`, `forage→foraging`, …).
- **Three gate levels** — RimWorld's "minimum reqs to even do" plus
  "minimum threshold for certain jobs", plus later scaling:
  - **L1 hard requirement** — can the action be done at all (tool in
    hand, recipe unlocked, material available): the existing plancheck
    material ledger already covers most of it.
  - **L2 job threshold** — r2 job types declare
    `"requires": { "skill": "mining", "minLevel": 2 }`; the planner
    filters out ineligible jobs *before* the model sees them.
  - **L3 soft scaling (later)** — level modulates speed/quality/success
    probability, the "how well/fast" part.
- **We do not adopt the XSkills machinery** (its Harmony patches, GUI,
  PlayerSkillSet wiring) — we borrow the *shape* (XP curve, leveled
  abilities, requirement gating). The engine's `ItemSlotSkill`/
  `ISkillItemRenderer` is noted as a future rendering hook if 1.23+
  exposes more of it.

## 3. Tying into the decision system

- **Plan time (deterministic, pre-model):** policy + L1/L2 gates filter
  the job options; `foodPressure` above threshold re-orders the plan with
  a forage-eat prefix. The LLM plans a smaller, already-legal space —
  the same "deterministic before neural" contract as the v5 loop.
- **Outcome writes:** XP gains, eat events, and *policy denials* are all
  logged (denials are labeled rejection data for the later corpus/P5
  program — a pawn repeatedly denied an action is a signal, not noise).
- **Death policy (settled):** in survival, death is permanent — registry
  removal, cargo drops at the body, recovery via the loot command.
  Respawn is a *deity power*: an explicit harness command for
  debugging/testing now, a designed respawn logic later.

## 4. Open empirical questions (the pilot answers them)

1. **The one live check**: does our bot's entity instance carry the
   `hunger` tree (expected yes — player.json declares it for all player
   entities; our bot is a server-side player entity)? One harness command
   prints it.
2. Eating a berry end-to-end: does `OnEntityReceiveSaturation` + stack
   consume produce the expected tree/HUD changes and the `EatenStack`?
   (Vanilla values may be quirky — Realistic-Starvation notes saturation
   ≈ 2× calories.)
3. The operator's own client player is a separate entity with a separate
   meter — irrelevant to the bot; the bot's bar renders in the bot's
   player view (free observability on the possession screen).
4. Animal feeding (pigs + trough) — only when husbandry becomes a
   milestone (no animal declares the hunger behavior in 1.22.7 data).

## 5. Build order

1. `polis-policies.json` + `PolicyEngine` + `eat` action (one small
   session; live-verify on a berry in the pilot world).
2. Food state + forage-eat interrupt inside the first survival pilot
   mission (fresh world is up: normal clock, survival).
3. Skill state + XP + L2 job gates — with the copper/melting-pot
   milestone (the first jobs that want a threshold).
4. `wear`/`behavior` policy domains when the bot actually wears things.
