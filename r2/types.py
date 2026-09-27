"""R2 types + pure reflex-state helpers (T4 seam).

Extracted VERBATIM from scripts/jev-loop-v5.py (Phase 1-A, 2026-09-28).
Side-effect free: no network, no game state, no globals written. The v5
loop and the r2 executor both import from here - ONE implementation, so
drift between the two entry points is impossible.

Frozen contract (tests/reflex/contract.py): T1 prompt, T2 decision,
T3 readout, T4 state construction, T2b run transitions. The reflex-state
DTO shape is FROZEN - the fine-tuned decider model consumes the 8-line
projection of it.
"""
import math


def dist(a, b):
    return ((a[0] - b[0]) ** 2 + (a[2] - b[2]) ** 2) ** 0.5

def carrying_from(state_resp):
    """All item codes on the bot: hands + cargo grid (state Backpack
    only covers grid slots - hands are separate fields). Pure over the
    /polis/state payload (2026-09-27: split out of Polis.carrying for the
    T4 state-construction golden - the construction must be replayable
    from the recorded raw context alone)."""
    b = (state_resp or {}).get("Bot", {})
    items = []
    for k in ("RightHand", "LeftHand"):
        it = b.get(k)
        if it and it.get("Code"):
            items.append(it["Code"])
    items += [x.get("Code") for x in (b.get("Backpack") or [])]
    return items


MISSIONS = {
    "mine": {
        "task": "mine the marker block, then return to base",
        "actions": ("goto_target", "mine_target", "pickup_item", "place_block",
                    "give_tool", "goto_base", "wait"),
        "phase_action": {"travel": "goto_target", "mine": "mine_target",
                         "pickup": "pickup_item", "return": "goto_base",
                         "done": "wait"},
        "laya_instructions": (
            "Answer yes only if the proposed action matches the current phase: "
            "travel phase needs goto_target, mine phase needs mine_target, "
            "pickup phase needs pickup_item (while an item is still on the "
            "ground), return phase needs goto_base, done phase needs wait, and "
            "the bot carries the tool the phase needs (mining needs a "
            "pickaxe). give_tool is correct only when the bot lacks the tool "
            "its phase needs. place_block is never correct for this mining "
            "task. No otherwise - a proposed action that contradicts the "
            "phase, skips an unfinished step, or uses a missing tool is no."),
        "judge_rules": (
            "Decide in this order. (1) First check the bot's inventory: if "
            "it does NOT contain a pickaxe, answer give_tool - never "
            "mine_target, even if a mine attempt just failed and even if "
            "mine_target is the proposed action. A failed mine with no "
            "pickaxe in the inventory means the tool was lost; retrying "
            "mine is wrong. (2) If a pickaxe IS in the inventory and the "
            "marker is still present, answer mine_target (retrying after a "
            "failed mine is correct in that case). (3) If the marker is gone "
            "and the items line lists a ground item the bot is not carrying "
            "yet, answer pickup_item. (4) place_block is only correct for "
            "build tasks - never for this mining task. (5) Otherwise follow "
            "the phase. Only answer wait when the facts are contradictory."),
    },
    "harvest": {
        "task": "harvest the crop, then return to base",
        "actions": ("goto_target", "harvest_target", "pickup_item", "place_block",
                    "give_tool", "goto_base", "wait"),
        "phase_action": {"travel": "goto_target", "harvest": "harvest_target",
                         "pickup": "pickup_item", "return": "goto_base",
                         "done": "wait"},
        "laya_instructions": (
            "Answer yes only if the proposed action matches the current phase: "
            "travel phase needs goto_target, harvest phase needs "
            "harvest_target, pickup phase needs pickup_item (while a "
            "harvested item is still on the ground), return phase needs "
            "goto_base, done phase needs wait. place_block is never correct "
            "for this harvesting task. No otherwise - a proposed action that "
            "contradicts the phase or skips an unfinished step is no "
            "(returning to base while the crop is still present skips the "
            "goal)."),
        "judge_rules": (
            "harvesting a present crop needs no tool. While the crop is "
            "present and the phase is harvest, the correct action is "
            "harvest_target - the execution moves the bot there first if it "
            "is not adjacent yet. If the crop is gone and the items line "
            "lists a ground item the bot is not carrying yet, answer "
            "pickup_item. Proposing goto_base while the crop is still "
            "present skips the goal - answer harvest_target instead. "
            "place_block is only correct for build tasks - never for this "
            "harvesting task. Only answer wait when the facts are "
            "contradictory."),
    },
    "build": {
        # 7-option tuple deliberately identical to harvest's (same letter
        # positions) so the fine-tuned reflex sees an in-distribution option
        # list; the novel parts are the task wording, the phase name "build"
        # and the inverted fixture (site starts empty).
        "task": "place a granite stone at the build site, then return to base",
        "actions": ("goto_target", "harvest_target", "pickup_item", "place_block",
                    "give_tool", "goto_base", "wait"),
        "phase_action": {"travel": "goto_target", "build": "place_block",
                         "return": "goto_base", "done": "wait"},
        "laya_instructions": (
            "Answer yes only if the proposed action matches the current "
            "phase: travel phase needs goto_target, build phase needs "
            "place_block (while the build site is still empty), return "
            "phase needs goto_base, done phase needs wait, and the bot "
            "carries the granite stone the phase needs. give_tool is "
            "correct only when the bot lacks the granite stone its phase "
            "needs. harvest_target, pickup_item and the other actions are "
            "never correct for this building task. No otherwise - a "
            "proposed action that contradicts the phase, skips an "
            "unfinished step, or uses a missing item is no."),
        "judge_rules": (
            "Decide in this order. (1) First check the bot's inventory: if "
            "it does NOT contain a granite stone (rock-granite), answer "
            "give_tool - placing needs the block. (2) If the build site is "
            "still empty: near it, answer place_block - the execution moves "
            "the bot there first if it is not adjacent yet; far from it, "
            "answer goto_target. (3) If the build site is filled: near the "
            "base answer wait, otherwise answer goto_base - the mission is "
            "the placement, and returning home is the last step. (4) "
            "Proposing goto_target after the site is filled skips the "
            "return - answer goto_base instead. Only answer wait when the "
            "facts are contradictory."),
    },
}


def fixture_bool(mission, scan_resp, cell, marker=None):
    """(T4, 2026-09-27) Pure fixture predicate over a recorded
    /polis/command scan response - the same checks the harness methods
    apply (marker_present / crop_present / site_filled), split out so
    state construction is replayable from the recorded raw context.
    cell is [x, y, z]."""
    blocks = (scan_resp.get("Data") or {}).get("blocks", [])
    x, y, z = cell
    if mission == "harvest":
        return any(str(b.get("code") or "").startswith(("crop-", "game:crop-",
                                                         "crop:"))
                   and b.get("pos") == [x, y, z]
                   for b in blocks)
    if mission == "build":
        # the exact cell holds any (non-air) block - the build site starts
        # EMPTY; place_block fills it (inverted fixture vs mine/harvest).
        return any(b.get("pos") == [x, y, z]
                   and str(b.get("code") or "") not in ("", "air", "game:air")
                   for b in blocks)
    codes = ((marker, "game:" + marker) if marker
             else ("rock-granite", "game:rock-granite"))
    return any(b.get("code") in codes and b.get("pos") == [x, y, z]
               for b in blocks)

def oracle_action(mission, phase, has_tool, has_block):
    """(T4, 2026-09-27) The per-phase correct action (the labeled oracle
    the loop records per step). In the mine phase the correct action
    depends on tool state - a bot without a pickaxe must get one
    (give_tool) before it can mine. Same for build: a bot without the
    block must get one before placing."""
    if mission == "mine" and phase == "mine" and not has_tool:
        return "give_tool"
    if mission == "build" and phase == "build" and not has_block:
        return "give_tool"
    if phase == "pickup":
        return "pickup_item"
    return MISSIONS[mission]["phase_action"][phase]

def build_reflex_state(ctx, prev, injected=False, oracle_carry=None):
    """(T4, review round 2, 2026-09-27) THE state-construction contract.

    Pure over its inputs: the recorded raw context (ctx), the previous
    step's summary (prev), and two flags. Returns the reflex-state DTO -
    the exact dict build_state_text consumes.

    ctx: mission, task, target, base, marker, crop, buildblock, and the
         observation triple - state (1st /polis/state fetch), carry_state
         (2nd fetch), post_state (3rd fetch, taken after a possible fault
         injection), plus the fixture scan response.
    oracle_carry: the carry list the ORACLE derives from; defaults to the
         3rd fetch when present, else the 2nd.

    Deliberate quirks pinned by the contract (exactly what the
    pre-extraction inline code did):
      - the DTO's carrying/items/last_msg display comes from the 1st/2nd
        (pre-injection) fetches;
      - the oracle and the build-branch since-diff use the post-injection
        3rd fetch;
      - the mine-branch since-diff uses the 2nd fetch (not the 3rd);
      - the original code made two separate refetches (has_tool, then
        has_block); they are merged into the single 3rd fetch - one
        instant is at least as consistent as two.
    The T4 golden was captured from the pre-extraction code, so any
    implementation that must stay behavior-identical has to reproduce
    this DTO from the same ctx (gate: tests/reflex/contract.py).
    """
    mission = ctx["mission"]
    st = ctx["state"]
    pos = st["Bot"]["Pos"]
    # mine: the target is a solid block and goto stops one cell short,
    # so the "near" radius must cover that; harvest: the bot walks the
    # air cell next to the crop and arrives exactly.
    radius = 3.5 if mission == "mine" else 2.5
    near_t = dist(pos, ctx["target"]) <= radius
    near_b = dist(pos, ctx["base"]) <= 2.5
    fixture = fixture_bool(mission, ctx["scan"], ctx["target"],
                           ctx.get("marker"))
    fixture_gone = not fixture
    c2 = carrying_from(ctx["carry_state"])
    co = (oracle_carry if oracle_carry is not None
          else carrying_from(ctx.get("post_state") or ctx["carry_state"]))
    has_tool2 = any("pickaxe" in (c or "") for c in c2)
    has_block2 = any(ctx["buildblock"] in (c or "") for c in c2)
    has_harvest2 = any("carrot" in (c or "") for c in c2)
    has_toolO = any("pickaxe" in (c or "") for c in co)
    has_blockO = any(ctx["buildblock"] in (c or "") for c in co)
    # ground items within pickup reach (harness state Items, radius 5)
    ground_items = [i.get("Code") for i in (st.get("Items") or [])
                    if (i.get("Dist") or 99) <= 5]
    need_pickup = fixture_gone and not near_b and bool(ground_items) \
        and (mission == "mine" or not has_harvest2)
    if mission == "mine":
        if not fixture_gone:
            phase = "mine" if near_t else "travel"
        elif need_pickup:
            phase = "pickup"
        else:
            phase = "done" if near_b else "return"
    elif mission == "build":
        # the build site starts EMPTY: while empty it needs travel/build
        # (fixture = site_filled), once filled it needs return/done.
        # No pickup phase - the placed block is consumed, never dropped.
        if not fixture:
            phase = "build" if near_t else "travel"
        else:
            phase = "done" if near_b else "return"
    else:
        if not fixture_gone:
            phase = "harvest" if near_t else "travel"
        elif need_pickup:
            phase = "pickup"
        else:
            phase = "done" if near_b else "return"
    correct = oracle_action(mission, phase, has_toolO, has_blockO)
    proposal = correct
    if injected and (phase == "travel" or phase == "harvest"):
        proposal = "goto_base" # skip-goal
    elif injected and phase == "mine":
        proposal = "mine_target" # mine with a missing tool
    elif injected and phase == "build":
        proposal = "place_block" # place with a missing block
    changed = []
    if prev is not None:
        if fixture != prev["fixture"]:
            if mission == "build":
                changed.append("build site %s" % ("filled" if fixture else "emptied"))
            else:
                what = "marker" if mission == "mine" else "crop"
                changed.append("%s %s" % (what, "gone" if not fixture else "re-appeared"))
        if mission == "build" and has_blockO != prev["has_block"]:
            changed.append("granite %s" % ("now carried" if has_blockO else "dropped"))
        if mission == "mine":
            if has_tool2 != prev["has_tool"]:
                changed.append("pickaxe %s" % ("re-given" if has_tool2 else "dropped"))
        if has_harvest2 != prev["has_harvest"]:
            changed.append("harvested item %s" % ("now carried" if has_harvest2 else "lost"))
        if bool(ground_items) != prev["has_items"]:
            changed.append("ground item %s" % ("appeared" if ground_items else "picked up"))
        if phase != prev["phase"]:
            changed.append("phase %s -> %s" % (prev["phase"], phase))
    since = ", ".join(changed) if changed else "no change"
    if mission == "harvest":
        fixture_label = "crop_present"
    elif mission == "build":
        fixture_label = "build_site_filled"
    else:
        fixture_label = "marker_present"
    items_line = ", ".join(ground_items[:3]) or "none"
    last_msg = (st.get("LastAction") or {}).get("Msg") or "none"
    return {
        "task": ctx["task"],
        "phase": phase, "pos": pos,
        "near_t": near_t, "near_b": near_b,
        "fixture_label": fixture_label, "fixture": fixture,
        "carrying": c2, "items_line": items_line,
        "since": since, "last_msg": last_msg,
        "proposal": proposal,
    }

