## 1) Abe’s Oddysee / Abe’s Exoddus possession (Mudokon “chant”)

### What the mechanic *does* (player-facing rules that imply implementation)

* **Scope:** In *Abe’s Exoddus*, possession is explicitly described as taking control of “certain characters in the same screen” by chanting. ([Wikipedia][1])

  * This “same screen” constraint is a huge design+tech simplifier: it strongly suggests possession was built around their **screen-based camera/level streaming** (each area is a discrete screen that swaps when you cross the edge). ([Wikipedia][1])
* **Risk:** While possessing, **Abe’s body remains immobile and vulnerable**. ([Wikipedia][1])
* **Counterplay / hard limitations:** In *Abe’s Oddysee*, “chant suppressors” prevent chanting/possession in their effect radius. ([Wikipedia][2])
* **Exit behavior (key for state preservation):**

  * In *Exoddus*, the player can abandon possession at any time; **Scrabs/Paramites are released without harm**, but **Industrialists (Sligs/Glukkons) burst into pieces** when abandoned. ([Wikipedia][1])
  * That’s an important “design doing tech work” move: if the host is destroyed on release, you **avoid needing to restore** a complex AI state for those enemies (or worry about “what did the player make them do?”). (Inference based on the described behavior.) ([Wikipedia][1])
* **Host capabilities are host-limited:** Possession lets Abe use the host’s movement/attacks/commands (e.g., *Exoddus* mentions using Slig voice commands for puzzles). ([Wikipedia][1])

  * Oddworld Library also calls out concrete limitations like possessed Sligs being unable to crouch. ([Oddworld Library][3])

### Likely technical shape (what’s *strongly suggested*, even if the original team didn’t publish engine docs)

Because the games are **screen-based**, possession can be implemented with minimal systemic disruption:

* **Camera:** keep the camera locked to the current screen; possession targets are constrained to that screen (explicit in *Exoddus*). ([Wikipedia][1])
* **Input routing:** swap the “active controller” from Abe to the possessed actor (host). Abe is put in a “chanting” state (immobile), host AI disabled, host becomes player-driven. (This is the standard architecture implied by “Abe remains immobile and vulnerable” while control transfers.) ([Wikipedia][1])
* **AI state preservation:**

  * For hosts that **explode on release** (Sligs/Glukkons in *Exoddus*), you don’t need preservation at all. ([Wikipedia][1])
  * For hosts that **survive release** (Scrabs/Paramites), you can restore a simpler “resume AI” state (idle/hunt) rather than reconstructing a long task chain. (Inference; consistent with the “released without harm” behavior.) ([Wikipedia][1])

## 2) Other possession / body-swap games + shared patterns

### Messiah (2000)

* Core loop: Bob (the cherub) is **weak/vulnerable**, so possession is central. ([MobyGames][4])
* **Camera:** mostly third-person, but you can go **“behind the eyes”** of possessed characters. ([game-over.net][5])
* **AI complexity:** devs explicitly call out that because you can possess/de-possess at will and move characters far from where they “belong,” NPCs must react intelligently after release (their example: de-possessing a character in a totally different area and the AI must cope). ([game-over.net][5])
* **Host differentiation:** each character has an RPG-like stat sheet (speed, jump height, armor, etc.). ([game-over.net][5])

### Geist (2005)

* Design intent (from interviews): the concept was “if you need a weapon you possess a person that has a gun… if you need hands you possess someone,” then later animal possession, and **Miyamoto suggested object possession**. ([nsidr][6])
* They explicitly say they didn’t consciously model it after *Messiah* (they “didn’t even remember” it until later). ([Nintendo World Report][7])

### Dishonored (2012)

* It’s framed as a high-cost, high-impact power (mana/potions gating higher-cost abilities like Possession). ([Wikipedia][8])
* Dev iteration note: an earlier version let you control victims **remotely without inhabiting their body**, but the team felt that offered less challenge; balancing powers like Possession was difficult. ([Wikipedia][8])
* (Also, Bethesda support clarifies Possession is **exclusive to Corvo** in *Dishonored 2*—useful as a “character kit identity” example.) ([Bethesda Support][9])

### Shared patterns across these games (useful for your colony-management context)

1. **A tradeoff triangle:** power ↔ vulnerability/cost ↔ constraints

   * Abe: body is helpless + chant suppressors + “same screen.” ([Wikipedia][1])
   * Messiah: base form is helpless; possession forces AI edge cases. ([game-over.net][5])
   * Dishonored: high-cost ability; tuned for challenge. ([Wikipedia][8])
2. **Host-as-moveset:** possession is compelling when hosts have *meaningfully different affordances* (weapons, traversal, access). ([game-over.net][5])
3. **Constraint-driven implementation:** screen/area limits (Abe), duration/cost (Dishonored), or systemic AI investment (Messiah). ([Wikipedia][1])

## 3) Design considerations for a colony-management possession mechanic

### Preserving NPC state during possession (practical architecture)

A robust approach is to separate **“body”** from **“controller/brain”**:

* **Body:** physics, animation state, inventory/equipment, health/status effects.
* **Brain:** current job/task chain, blackboard/memory, reservations (claimed resources), path target, schedule/needs, social relationships/alerts.

On possession:

1. **Snapshot the brain layer** into a “suspend token”:

   * current goal + subgoal index
   * pathfinding intent (destination, path corridor if you keep it)
   * reservations/locks (so you don’t orphan claimed resources)
   * perception context (last seen threat / suspicion meter)
2. **Swap controller**: AI brain stops ticking; player controller begins driving the same body locomotion API.

Why this matters: *Messiah*’s dev interview basically describes the failure mode if you don’t—after de-possession, the character must “realize where she is now and figure her own way out.” ([game-over.net][5])

### Releasing back to AI smoothly

Have a dedicated **“reentry” state** for the AI (1–5 seconds of simulation time) instead of snapping straight back to the old behavior tree node:

* Re-validate: “Is my reserved job still valid? Is the target still reachable?”
* If invalid, **replan** rather than forcing continuation (prevents pathing into walls, using missing tools, etc.).
* Optionally add a short “confusion”/“reorientation” animation or debuff (also a balance lever).

If you want an *Abe-like* simplification: consider making some host types **non-persistent on release** (e.g., they “stun,” flee, or even die), which reduces restoration complexity—this is exactly what *Exoddus* achieves by having certain possessed Industrialists burst on release. ([Wikipedia][1])

### Should possessed units have different capabilities than AI-controlled?

Usually yes—but pick *one* of these philosophies and be consistent:

**A) Same capabilities, better precision (low rules complexity):**
Player can do what AI can do, just more accurately/creatively. Balance via cost/risk.

**B) Host exposes a “player kit” subset (prevents exploits):**
Dishonored community guides commonly note you can’t fully “use” a human host like a full combat avatar (e.g., you can’t just make them fight like you’re playing them as a main character). ([Steam Community][10])
Even if you don’t copy that exact rule, the principle is good for colony sims: possession shouldn’t trivially replace your whole combat/control system.

**C) Host becomes *more* capable while possessed (power fantasy):**
Messiah leans into “different bodies = different stats/weapons.” ([game-over.net][5])
If you do this in a colony game, you’ll likely need stronger constraints (cooldowns, time limit, detection risk, or opportunity cost).

## 4) Talks / postmortems / articles worth pulling from

Here are a few concrete “implementation-relevant” references surfaced in the research:

* **Super Mario Odyssey (possession as a core mechanic discovered via prototyping):** Koizumi describes iterating through prototypes and sticking with capturing/possessing enemies because it “worked well.” ([Game Developer][11])
* **Dishonored (edge-case explosion + feature cost):** Harvey Smith is quoted describing how many edge cases Possession creates and how much work it takes to support. ([Op Attack][12])
* **Dishonored (design iteration on possession):** Wikipedia’s development section notes they tried a remote-control version and changed it because it reduced challenge; also highlights how hard balancing powers was. ([Wikipedia][8])
* **General postmortem hunting ground:** Game Developer’s postmortem archives are a good index for classic deep dives (not possession-specific, but useful methodology-wise). ([Game Developer][13])
* **Free talk indexes:** the “awesome-gametalks” list is a big curated directory (useful for finding camera/control-system talks that often overlap with possession problems). ([GitHub][14])

---

If you tell me what your possession is *for* in the colony loop (combat? infiltration? emergency override? productivity boost?), I can map these patterns into a tighter rule set (costs, duration, detection, and what state you must snapshot vs can safely recompute).

[1]: https://en.wikipedia.org/wiki/Oddworld%3A_Abe%27s_Exoddus?utm_source=chatgpt.com "Oddworld: Abe's Exoddus"
[2]: https://en.wikipedia.org/wiki/Oddworld%3A_Abe%27s_Oddysee "Oddworld: Abe's Oddysee - Wikipedia"
[3]: https://oddworldlibrary.net/wiki/Oddworld%3A_Abe%27s_Oddysee "Oddworld: Abe’s Oddysee - Oddworld Library"
[4]: https://www.mobygames.com/game/1307/messiah/?utm_source=chatgpt.com "Messiah (2000) - MobyGames"
[5]: https://www.game-over.net/feature/feb99/messiah/ "GameOver - Messiah Interview"
[6]: https://www.nsidr.com/archive/interview-n-space/ "Interview: n-Space / nsidr"
[7]: https://www.nintendoworldreport.com/interview/2260/the-geist-interview "The Geist Interview - Interview - Nintendo World Report"
[8]: https://en.wikipedia.org/wiki/Dishonored?utm_source=chatgpt.com "Dishonored"
[9]: https://help.bethesda.net/app/answers/detail/a_id/36755/~/why-does-the-tutorial-tell-me-to-possess-a-rat-and-find-a-small-passage-to-get?utm_source=chatgpt.com "Why does the tutorial tell me to possess a rat and ... - Bethesda Support"
[10]: https://steamcommunity.com/sharedfiles/filedetails/?id=153448861&utm_source=chatgpt.com "All-Encompassing Guide to Dishonored - Steam Community"
[11]: https://www.gamedeveloper.com/design/mad-hatter-i-super-mario-odyssey-i-producer-explains-possession-mechanic "Mad hatter: Super Mario Odyssey producer explains possession mechanic"
[12]: https://opattack.com/possession-dishonored-arkane/ "Arkane Studios Game Director Talks About Implementation of Possession Power in Dishonored | Op Attack"
[13]: https://www.gamedeveloper.com/audio/10-seminal-game-postmortems-every-developer-should-read "10 seminal game postmortems every developer should read"
[14]: https://github.com/hzoo/awesome-gametalks "GitHub - hzoo/awesome-gametalks: :speech_balloon: A curated list of gaming talks (development, design, etc)"

