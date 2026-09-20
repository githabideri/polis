Below is what I found (with sources) and what it implies for “NPCs that feel alive but aren’t babysitting-sims”.

---

## 1) Giving custom entities survival needs (hunger, temperature)

### How VS expects you to do it: **Entity Behaviors**

Vintage Story’s entity system is component-based: you attach **behaviors** to an entity type, and the engine calls their lifecycle hooks every tick. ([DeepWiki][1])

#### Add behaviors via JSON (the normal way)

Entity behaviors are typically attached in the entity type JSON (`entityBehaviors`). The VS wiki also notes a newer pattern: define behavior configs once in `behaviorConfigs` and reference them from both client+server behavior blocks to avoid duplication. ([Vintage Story Wiki][2])

#### Add behaviors via code (for custom behavior classes)

If you write your own `EntityBehavior` subclass, you register the behavior name → class mapping with `ICoreAPICommon.RegisterEntityBehaviorClass(...)` (and do this on both client and server).
After that, you can attach it in JSON by name (or patch JSON to add it).

> Practically: **JSON is how entities get behaviors**, while **code is how you define/register new behavior types** (and you can use JSON patching to inject behaviors into existing entity types). ([Vintage Story Wiki][3])

---

### Hunger / saturation on custom entities

#### Can you reuse vanilla hunger/saturation behaviors?

Yes—there is a vanilla hunger behavior in the core game content namespace: `Vintagestory.GameContent.EntityBehaviourHunger`. It ticks (`OnGameTick`) and reduces saturation (`ReduceSaturation`). ([Vintage Story API Docs][4])

#### Is it designed for reuse by mods?

It appears to be:

* It’s part of the public game content API surface (not “private internal only”), and issues/discussions reference it directly by class name. ([Vintage Story API Docs][4])
* Mods interact with hunger/nutrition in ways that strongly suggest the behavior has reusable state/methods (e.g., mods that *expand hunger* mention manipulating **nutrient levels** and **saturation**). ([The Escapist][5])

**Important catch:** hunger behavior gives you a *meter/system*, not an NPC’s *decision-making*. Players eat by input; your NPC must have AI/tasks to obtain and consume food.

So “reuse vanilla hunger” usually means:

1. attach the hunger behavior, and
2. implement (or reuse) an AI task that periodically checks hunger and eats from allowed sources.

---

### Temperature effects (hypothermia / heat stroke)

#### Vanilla “body temperature” exists as a behavior (player-focused)

The built-in behavior list includes `bodytemperature` (used by the player) and describes it as tracking temperature sensitivity. ([Vintage Story Wiki][2])
So yes, you *can* attach temperature logic to a custom entity by behavior, if compatible.

#### Does vanilla do heat stroke?

As of the recent 1.21-era discussions, **overheating penalties aren’t implemented in vanilla**; the only stated body-temperature damage mechanic is freezing/cold damage (and players discuss that overheating currently has no penalty). ([DeepWiki][6])

Also: VS 1.21.x added a `warmth` attribute used by armor (mods note they became “content-only” because warmth is now supported natively). ([mods.vintagestory.at][7])
And there’s a server/world config command that sets how much cold an undressed player can bear (`/worldConfig bodyTemperatureResistance`). ([Vintage Story Wiki][8])

**Implication for NPCs:** If you want *heat stroke*, you’ll likely implement it yourself (either an extra behavior or an extension to bodytemperature logic), because vanilla emphasis is cold.

---

## 2) NPC food consumption patterns in existing mods

### Do any mods have entities that automatically eat?

Yes—there are mods that implement *animal* hunger + autonomous eating:

* **vs-farmlife** explicitly adds saturation to livestock, drains it daily, and says animals “continue to eat until they are full”, with AI prioritizing finding food. ([GitHub][9])

That’s very relevant to your NPC goal: it demonstrates a pattern of **AI-driven feeding tied to saturation** in the VS ecosystem.

There are also “auto-feed the player” mechanics (e.g., Lunchbox auto-feeds the player from a container), which is conceptually similar to “NPC consumes from inventory/container,” just applied to the player. ([moddb2.vintagestory.at][10])

### VSVillage / NDL Villagers: do they advertise survival needs?

From their mod pages:

* **VS Village**: focuses on villages, routines, workstations, beds, happiness, quests—no mention of hunger/temperature needs in the feature list shown. ([mods.vintagestory.at][11])
  (Also: the comments show lifecycle issues like repeated spawn/despawn/respawn causing lag in some versions, which matters if you plan to add per-tick survival logic.) ([mods.vintagestory.at][12])

* **NDL Villagers**: focuses on a TownCenter you supply with “resources” to bring villagers/guards, plus spawning traders and wandering villagers—again, nothing in the snippet indicating villagers track hunger or autonomously eat. ([mods.vintagestory.at][13])

So: **existing “villager” mods tend to make NPCs busy/social**, not simulate metabolism—at least as advertised.

### Food preference / nutrition systems

Vanilla hunger is tied to more than “a bar”: mods talk about manipulating **nutrient levels** (the nutrition system players use for bonuses). ([The Escapist][5])
But vanilla does **not** hand you a ready-made “NPC diet preference engine.” If you want preferences, you’ll implement:

* which foods count as edible for NPCs,
* priority rules (cheap calories vs balanced nutrition),
* and how they source food (inventory vs village pantry vs trough/stockpile).

A practical warning from the hunger-mod ecosystem: supporting every food item (including modded foods) can become a maintenance trap—authors explicitly complain that manually supporting many foods is hard and makes mods brittle. ([mods.vintagestory.at][14])
That warning applies even more to NPC diets.

---

## 3) NPC death, respawn, unconscious states, corpses

### Vanilla NPC respawn patterns

* **Villagers**: if a villager dies, it respawns “no sooner than 24 game-hours, but no later than 72 game-hours.” ([Vintage Story Wiki][15])
* **Traders**: killing a trader doesn’t remove wagon protections, and the trader respawns at the cart in **24–72 hours**. ([Vintage Story Wiki][16])

So the vanilla game already uses a **“important NPCs come back”** model.

### Drops, despawning, corpse decay: behavior-driven

The built-in behavior list includes:

* `deathdrops` (drop tables),
* `despawn` (remove entity),
* `deaddecay` (dead body decays after time),
* and `reviveondeath` (used by trader/villager). ([Vintage Story Wiki][2])

Also, the behavior framework includes a `EntityBehaviorHarvestable` concept for “post-death resource harvesting” (think: the carcass you harvest), supporting the idea that “corpse entity exists for a while, then decays.” ([DeepWiki][1])

### “Unconscious instead of dead”

Vanilla includes `reviveondeath` as a behavior name used for villager/trader in the behavior list. ([Vintage Story Wiki][2])
And there’s a popular mod explicitly saying: **since 1.21 it disables vanilla revive behavior and replaces it** with its own “Unconscious” behavior. ([mods.vintagestory.at][17])
That’s strong evidence the community wants “downed state” mechanics and that swapping death handling via behaviors is feasible.

### Player-initiated revival / resurrection

Vanilla 1.21 added reviving other players with a poultice. ([info.vintagestory.at][18])
Even if that mechanic is player-only, it’s a good design anchor for “revive colonist” gameplay that feels native.

---

## 4) Existing villager/colonist mods and community “tedious vs alive” tension

### VS Village (vsvillage)

* Core pitch: villages + inhabitants with routines; villagers want workstations and beds; daily schedule; optional quests integration. ([mods.vintagestory.at][11])
  No explicit survival needs described in the visible feature section, so assume “alive via behavior/routines,” not “alive via metabolism.”

### NDL Villagers

* Core pitch: TownCenter; supply it with resources to bring villagers/guards; wandering villagers; spawning traders. ([mods.vintagestory.at][13])
  Again, no explicit hunger/temperature integration in the snippet.

### Community consensus: survival is cool, upkeep is controversial

You can see the broader pattern in hunger discussions/mods:

* Players explicitly ask for hunger systems that are “less tedious” and more predictable. ([Vintage Story][19])
* There are mods whose stated purpose is basically “reduce hunger because I don’t have time to eat my days away.” ([mods.vintagestory.at][20])

So if you give NPCs survival needs, you’ll want “logistics gameplay” (stockpiles, meal production) rather than “babysit each NPC”.

---

# What this implies for your design goal (alive, not babysitting)

You’re implicitly assuming “vanilla creatures have survival needs like hunger/temperature.” The reality is closer to: **players have deep survival meters; many creatures/NPC-like entities are driven by AI + simpler rules**, and even vanilla NPCs (villagers/traders) already lean on **respawn** rather than strict mortality. ([Vintage Story Wiki][15])

A low-tedium blueprint that fits VS patterns:

1. **Attach vanilla hunger behavior**, but don’t require individual feeding:

   * Make a **village pantry** (one or a few designated containers/stockpiles).
   * NPCs “eat” by consuming from pantry (like livestock mods do for animals, conceptually). ([GitHub][9])
   * If pantry empty → NPC enters “hungry” state (slower work, worse morale), only much later severe consequences.

2. **Use temperature mostly as “performance/mood”**, not constant damage:

   * Cold should push behavior: seek shelter/heat sources, wear warm clothing, gather near fires.
   * Consider keeping actual HP damage rare (only extreme exposure), because vanilla already avoids overheating penalties and players argue about tedium. ([DeepWiki][6])

3. **Death handling:** copy vanilla’s “important NPCs come back”

   * Use a “downed/unconscious” state first (reviveondeath-style), with rescue gameplay (bring to bed, apply poultice-equivalent), and only make “true death” possible in extreme cases. ([Vintage Story Wiki][2])
   * Even if they die, respawn them on a timer at TownCenter (mirrors villager/trader 24–72h). ([Vintage Story Wiki][15])

4. **Avoid food-preference complexity** early:

   * Start with broad edible categories (grain/veg/protein) and a simple “balanced diet gives buffs” rule.
   * Otherwise you’ll hit the same maintenance pain hunger-mod authors complain about when supporting many foods/mod foods. ([mods.vintagestory.at][14])

If you want, I can turn this into a concrete implementation plan (behaviors to attach, minimal AI tasks needed, and a “pantry contract” so players interact with *systems* rather than *individual NPC hunger bars*).

[1]: https://deepwiki.com/anegostudios/vsessentialsmod/3.2-entity-behaviors "Entity Behaviors | anegostudios/vsessentialsmod | DeepWiki"
[2]: https://wiki.vintagestory.at/index.php/Modding%3AEntity_Behaviors "Modding:Entity Behaviors - Vintage Story Wiki"
[3]: https://wiki.vintagestory.at/Modding%3AContent_Mods?utm_source=chatgpt.com "Modding:Content Mods - Vintage Story Wiki"
[4]: https://apidocs.vintagestory.at/api/Vintagestory.API.Common.Entities.Entity.html?utm_source=chatgpt.com "Class Entity | VintageStory API"
[5]: https://www.escapistmagazine.com/best-mods-for-vintage-story/?utm_source=chatgpt.com "10 Best Mods for Vintage Story - The Escapist"
[6]: https://deepwiki.com/anegostudios/vssurvivalmod/4.2-meal-management-and-food-containers?utm_source=chatgpt.com "Meal Management and Food Containers | anegostudios/vssurvivalmod | DeepWiki"
[7]: https://mods.vintagestory.at/warmarmor?utm_source=chatgpt.com "Warm Armor - Vintage Story Mod DB"
[8]: https://wiki.vintagestory.at/World_Configuration/en?utm_source=chatgpt.com "World Configuration - Vintage Story Wiki"
[9]: https://github.com/91loocekaj/vs-farmlife?utm_source=chatgpt.com "A Vintage Story mod adding a livestock hunger system - GitHub"
[10]: https://moddb2.vintagestory.at/lunchbox?utm_source=chatgpt.com "Lunchbox - Vintage Story Mod DB"
[11]: https://mods.vintagestory.at/vsvillage "VS Village - Vintage Story Mod DB"
[12]: https://mods.vintagestory.at/vsvillage?utm_source=chatgpt.com "VS Village - Vintage Story Mod DB"
[13]: https://mods.vintagestory.at/ndlvillagers?utm_source=chatgpt.com "/ NDL Villagers - Vintage Story Mod DB"
[14]: https://mods.vintagestory.at/realisticstarvationfixed?utm_source=chatgpt.com "Realistic Starvation - Fixed for 1.20 + Support for Combat Overhaul"
[15]: https://wiki.vintagestory.at/Villager?utm_source=chatgpt.com "Villager - Vintage Story Wiki"
[16]: https://wiki.vintagestory.at/index.php?title=Trading&utm_source=chatgpt.com "Trading - Vintage Story Wiki"
[17]: https://mods.vintagestory.at/unconscious?utm_source=chatgpt.com "/ Unconscious (Revive) - Vintage Story Mod DB"
[18]: https://info.vintagestory.at/v1dot21?utm_source=chatgpt.com "v1.21 - Vintage Story"
[19]: https://www.vintagestory.at/forums/topic/14832-a-hunger-mod-that-slightly-simplifies-and-makes-more-sense-of-hunger-nothing-major/?utm_source=chatgpt.com "A hunger mod that slightly simplifies and makes more sense of hunger ..."
[20]: https://mods.vintagestory.at/show/mod/21472?utm_source=chatgpt.com "ReducedHunger - Vintage Story Mod DB"

