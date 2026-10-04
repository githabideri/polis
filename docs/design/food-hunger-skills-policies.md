# Design — food, hunger, policies & skills (survival pilot)

Status: **proposed** (engine facts below are reflection-verified against
1.22.7; nothing in this doc is implemented yet). Owner: the polis layer.
Constraint that shapes everything: *whatever lands now must let a full
system tie in later without big code rewriting* — so every pillar is
data-driven with one evaluation seam.

## 1. Verified engine facts (1.22.7, reflection probes 2026-10-04)

- **No hunger state in the engine.** `EntityAgent`, `EntityPlayer`,
  `IPlayer` expose no hunger/satiation/nutrition member (public or
  private). Survival's "food pressure" is not an engine meter we can read.
- **Food is item data.** `FoodNutritionProperties` carries `Satiety`,
  `Health`, `Saturation`, `SaturationLossDelay`, `Intoxication`,
  `Psychedelic`, `FoodCategory` (`Fruit, Vegetable, Protein, Grain, Dairy,
  Unknown, NoNutrition`) and `EatenStack` (what the item becomes when
  consumed, e.g. a used container).
- **1.22 item-use is not a callable API.** Items expose
  `OnHeldInteractStart/Step/Stop/Cancel` callbacks (the engine's eating
  runs through the client's held-interact pipeline); there is no
  `player.UseItem(...)` in the public API. Mods cannot "make the engine
  eat" through a public method.
- **Engine skill surface is a slot, not a model:** `ItemSlotSkill` +
  `ISkillItemRenderer` only — no XP/level data types. (1.22 treats skills
  as carried items; the data model is not in the API.)
- **Content data is not plain JSON assets** in 1.22 (the asset tree ships
  only music/lang/textures/shapes for the game mod) — item definitions are
  bundled, so per-item values must come from the running game or from our
  own tables.
- Recalled from the craft work: sticks are foraged, not craftable; copper
  melts in a **melting pot** on a campfire (charcoal), not a bloomery;
  bloomery = iron/steel; the world carries 12,995 grid recipes (queryable
  via `/polis/recipes`).

**Consequence:** hunger is a *polis abstraction* (decision-layer state),
eating is a *polis action* (mod-privilege effect, not engine plumbing),
and both read their values from data we own.

## 2. The three pillars

### A. Food & hunger (decision-layer state + one action)

- **Food state (per bot, persisted mod state):** `lastEat` (game time) and
  a derived `foodPressure`. No fake engine meter — we track *time since
  last eat* plus health trend (a bot whose health drifts down without a
  visible damage source is hungry, whatever the engine calls it).
- **EAT action.** Harness command `eat [itemCode]` and an r2 job type
  `eat`. Implementation (the seam): pick the best inventory stack the
  policy engine allows → consume it from the bot's inventory → apply the
  item's `FoodNutritionProperties.Health` (falling back to our own value
  table if the attribute is not readable in 1.22) → drop the `EatenStack`.
  This is deterministic, mod-privileged and version-stable. If a future
  system wants *authentic* engine eating (animations, client pipeline),
  it swaps **this one method** — held-interact synthesis or a Harmony
  patch into the compiled food code — without touching the policy,
  planner or state layers.
- **Hunger interrupt.** In the mission loop, `foodPressure` above a
  threshold preempts the current job at a safe checkpoint (same tier as
  the navigation-wedge interrupt): forage (berry bushes) → carry → eat.
  Thresholds and the "safe checkpoint" rule are data, not code.
- **Starvation is an open empirical question** (no engine meter ⇒ unclear
  whether 1.22 kills you at all). The pilot observes it; our policy stays
  conservative either way.

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

1. Does 1.22 survival actually kill a player from not eating?
2. What does eating a berry *do* (health? satiety side-effects? nothing
   observable without a meter)?
3. Is `FoodNutritionProperties` readable from a running item (attribute
   map) or do we need our own value table?
4. Is the held-interact route viable for authentic eating (deferred)?

## 5. Build order

1. `polis-policies.json` + `PolicyEngine` + `eat` action (one small
   session; live-verify on a berry in the pilot world).
2. Food state + forage-eat interrupt inside the first survival pilot
   mission (fresh world is up: normal clock, survival).
3. Skill state + XP + L2 job gates — with the copper/melting-pot
   milestone (the first jobs that want a threshold).
4. `wear`/`behavior` policy domains when the bot actually wears things.
