# Design — food, hunger, policies & skills (survival pilot)

Status: **proposed** (engine facts below are reflection-verified against
1.22.7; nothing in this doc is implemented yet). Owner: the polis layer.
Constraint that shapes everything: *whatever lands now must let a full
system tie in later without big code rewriting* — so every pillar is
data-driven with one evaluation seam.

## 1. Verified engine facts (1.22.7)

*(Corrected 2026-10-04 after web research — the earlier "no hunger state"
claim was wrong: the probe only covered `EntityAgent`/`EntityPlayer`/
`IPlayer` and missed the behavior that actually holds the state.)*

- **Hunger is real and engine-owned.** The player's **satiety** bar (green,
  above the hotbar; max **1500**) drains continuously — 0.24/s idle, 0.96/s
  moving, 2.46/s sprinting — with modifiers: occupied off-hand +20%, cold
  outdoors up to +25% (below 2 °C, removed inside a room), class trait
  (+30% for Blackguard), slowed healing below 75% satiety. At zero the
  player **starves: damage over time until death**. The state lives in the
  game assembly's `BehaviorHunger` entity behavior (wiki cites
  `Entity/Behavior/BehaviorHunger.cs`), introduced in 1.2.3; it is *not*
  in the public API data types (`IWorldPlayerData` has no satiety member),
  but the API surface around it is: `EnumDamageType.Hunger` (starvation is
  a first-class damage type), `StatModifiers.hungerrate`,
  `GlobalConstants.HungerSpeedModifier`, world config `playerHungerSpeed`.
- **Nutrition is item data — and readable from the API.**
  `CollectibleObject.NutritionProps` / `GetNutritionProperties()`
  (confirmed in 1.22; the XSkills mod calls `Collectible.NutritionProps?.
  Satiety` directly). `FoodNutritionProperties` carries `Satiety`, `Health`,
  `Saturation`, `SaturationLossDelay`, `Intoxication`, `Psychedelic`,
  `FoodCategory` (Fruit, Vegetable, Protein, Grain, Dairy, Unknown,
  NoNutrition), `EatenStack`. A second layer: five **nutrition category
  bars** (character dialog, `C`) — 40% of eaten satiety per category,
  each full bar +2.5 max HP (+12.5 total) — plus **nutrition delay**: claypot
  meals/pies pause satiety drain (hidden bonus satiety per category).
- **Animals:** vanilla tracks **animal weight** (a suggestion thread notes
  weight "is already in game") and has feeding behaviors (pigs eat from
  troughs or the ground; hares eat dropped food), but no explicit hunger
  levels — a mod (Truth and Beauty: Detailed Animals) adds them
  (starving/losing weight, grazing, weaning, hand-feeding).
- **Mods build on top, not around:** *Max's Simple Starvation* (current for
  1.22, 6k downloads) reinterprets the satiety bar as stomach→body weight,
  removes vanilla starvation damage/delay/health coupling, and applies
  weight-based buffs/debuffs **through `StatModifiers`**; *Realistic
  Starvation* (1.19-era) replaces the model with kJ energy balance (BMR,
  METs from animation, weight/BMI).
- 1.22 item-use is still **not a callable API** (only `OnHeldInteract*`
  callbacks; `IPlayer` is thin) — and engine "skills" remain a slot, not a
  model (`ItemSlotSkill` + `ISkillItemRenderer` only).
- Recalled from the craft work: sticks are foraged, not craftable; copper
  melts in a **melting pot** on a campfire (charcoal), not a bloomery;
  bloomery = iron/steel; the world carries 12,995 grid recipes (`/polis/recipes`).

**Consequence:** satiety is *the engine's* state — polis reads it (runtime
reflection on the player entity's `BehaviorHunger`; the game assembly is
opaque to build-time reflection but fully reflectable in-process), treats
low satiety as an interrupt condition, and checks the *item's own*
`NutritionProps` in the food policy. No fake meters. What polis adds: the
*decision* layer (what to eat, when, where to get it, how it feeds skills),
never a second hunger system.

## 2. The three pillars

### A. Food & hunger (read the engine meter, decide in polis)

- **Food state (per bot):** the engine's satiety + nutrition bars are the
  ground truth. Read path (live-verified in the pilot, this is the first
  empirical task): the player entity's `BehaviorHunger` behavior via
  in-process reflection (game assembly — build-time opaque, runtime
  fine); fallback signal: `EnumDamageType.Hunger` damage events + health
  trend. Polis keeps only the *derived* decision state: a `foodPressure`
  threshold (e.g. satiety < 25% or falling) and the last eat event.
- **EAT action.** Harness command `eat [itemCode]` and an r2 job type
  `eat`. Implementation (the seam): pick the best inventory stack the
  policy engine allows → consume it → apply the effect (satiety via the
  engine's state if the behavior field is writable, else our effect)
  reading values from the item's own `NutritionProps` (public API —
  confirmed usable in 1.22 by XSkills) → drop the `EatenStack`.
  Deterministic and version-stable; if a future system wants *authentic*
  engine eating (animations, the client pipeline), it swaps **this one
  method** — held-interact synthesis or a Harmony patch — without touching
  policy, planner or state.
- **Hunger interrupt.** In the mission loop, `foodPressure` above
  threshold preempts the current job at a safe checkpoint (same tier as
  the navigation-wedge interrupt): forage (berry bushes) → carry → eat.
  Thresholds and the "safe checkpoint" rule are data, not code.
- **Starvation is an engine event, not a mystery**: satiety 0 →
  `EnumDamageType.Hunger` damage → death. Polis observes it as a failure
  signal (a bot dying of hunger is a foraging-pipeline bug, reported as
  such); the *Max's Simple Starvation* style re-weighting is out of scope
  but `StatModifiers` is the door if we ever want it.

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

1. **The read path:** can the polis mod read (and write) the player's
   `BehaviorHunger` state in-process (field names/values of the live
   instance)? First implementation task; fallback is `EnumDamageType.Hunger`
   damage events + health trend.
2. What does eating a berry *do* in practice (satiety gain vs. the item's
   declared `Satiety` — the mod's Realistic-Starvation author notes vanilla
   values are often ~2x the calories, so expect rounding/quirks).
3. Is the held-interact route viable for authentic eating (deferred)?
4. Do vanilla animal feeding behaviors (pigs + trough) matter to us yet
   (husbandry milestone, later)?

## 5. Build order

1. `polis-policies.json` + `PolicyEngine` + `eat` action (one small
   session; live-verify on a berry in the pilot world).
2. Food state + forage-eat interrupt inside the first survival pilot
   mission (fresh world is up: normal clock, survival).
3. Skill state + XP + L2 job gates — with the copper/melting-pot
   milestone (the first jobs that want a threshold).
4. `wear`/`behavior` policy domains when the bot actually wears things.
