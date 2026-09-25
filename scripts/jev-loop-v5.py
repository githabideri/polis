#!/usr/bin/env python3
"""
Jev-loop v5 (optimization-harness form) - polis decision loop.

Three-tier decision (cheapest first):
  policy proposes an action for the current phase
    -> Laya 421M noul pre-filter (anchored yes/no, ~1.5-2.5 s)
         p < TAU_YES  -> 27B doubt-arbiter (thinking off, ~0.2-0.7 s)
         p >= TAU_YES -> Decider-2B choice readout (~3-4 s CPU, ~0.3 s GPU)
              p(proposal) < TAU_DEC        -> 27B doubt-arbiter
              p(proposal) >= TAU_DEC and Laya p < TAU_STRONG -> 27B (doubt)
              both confident (>= TAU_STRONG / >= TAU_DEC) -> execute the proposal

The 27B runs on *any doubt* (a low, or merely borderline, reflex score), not
only on outright disagreement: the 2026-09-25 mine pass showed the Decider
cannot veto its own confident travel-phase error (p~0.76 for the injected
goto_base) and a Laya yes at 0.37 (barely over tau_yes 0.35) let it through
- both reflexes wrong in consensus. Requiring a STRONG Laya score for the
skip-the-judge path closes that hole while keeping short-circuits for the
genuinely confident steps.

Missions (one pass each, --mission):
  mine    : mine the marker block, return to base.
            Success = marker block removed (scan-verified) AND bot at base.
            (1.22 note: set-placed rock has no BE type, so no item drops -
            block removal is the deterministic success criterion.)
  harvest : harvest the crop, return to base.
            Success = bot CARRIES a harvested item (vegetable/seed) AND is
            at base - the agent produced and carried a real item.

Positive controls (fault injection): at chosen phases' FIRST step a
KNOWN-WRONG proposal is injected:
  travel  : goto_base (skips the goal)
  mine    : tool dropped + mine_target (missing tool)
  harvest : goto_base (skips the goal)

Every step is recorded as a LABELED example (state, proposal, oracle
action, reflex p, path, judge answer, executed, outcome) - the raw
material for re-deriving the threshold when the model or question
changes (calibration protocol, llmlab docs/decision-classifiers.md).

Max-stall safety valve: after two consecutive executed `wait`s control
returns to the deterministic policy (the 27B arbiter latches to `wait`
after visible failures - measured pass 3/4, prompt-resistant).

Usage:
  python3 scripts/jev-loop-v5.py [--mission mine|harvest] [--bot 5]
      [--steps 8] [--faults travel,mine] [--repeat 1]
      [--tau-dec 0.5] [--tau-yes 0.35]
      [--decider http://decider-host:8091]
      [--harness http://127.0.0.1:8585] [--openjev http://openjev-host:8781]
      [--llm http://llm-host:8080] [--llm-model qwen3.8-27b-dual]
      [--out FILE.json]
"""

DECIDER_Q = ("Given the bot's current game state, choose the single best "
             "action for the bot to execute next.")
import argparse, json, os, re, sys, time, urllib.request

def http_json(url, payload=None, timeout=60):
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except Exception as e:
        return {"_error": str(e)}

def dist(a, b):
    return ((a[0] - b[0]) ** 2 + (a[2] - b[2]) ** 2) ** 0.5

class Polis:
    def __init__(self, base, uid):
        self.base, self.uid = base, uid
    def get(self, path, timeout=15):
        return http_json(self.base + path, None, timeout)
    def cmd(self, cmd, args, bot, timeout=60):
        return http_json(self.base + "/polis/command",
                         {"cmd": cmd, "args": args,
                          "context": {"botId": bot, "playerUid": self.uid}}, timeout)
    def state(self, bot, tries=10):
        for _ in range(tries):
            r = self.get("/polis/state?botId=%d" % bot)
            if "Bot" in r:
                return r
            time.sleep(1)
        return r
    def carrying(self, bot):
        """All item codes on the bot: hands + cargo grid (state Backpack
        only covers grid slots - hands are separate fields)."""
        b = self.state(bot).get("Bot", {})
        items = []
        for k in ("RightHand", "LeftHand"):
            it = b.get(k)
            if it and it.get("Code"):
                items.append(it["Code"])
        items += [x.get("Code") for x in (b.get("Backpack") or [])]
        return items
    def sweep_bots(self, keep=None):
        """Despawn all other bots. Persisted idle bots accumulate across
        runs (StoreWithChunk) and a large batch of them was measured to
        wedge the action/traverser system (goto freeze, 2026-09-22) - keep
        the world clean between passes."""
        d = self.get("/polis/bots")
        raw = d.get("Data") or d
        items = raw.get("bots") if isinstance(raw, dict) else raw
        for b in (items or []):
            i = b.get("id") if isinstance(b, dict) else None
            if i is None or i == keep:
                continue
            self.cmd("despawn", [], i)
    def cell_blocks(self, bot, cell, pad=1):
        x, y, z = cell
        r = self.cmd("scan", [str(x - pad), "2", str(z - pad),
                              str(x + pad), str(y + 2), str(z + pad)], bot)
        return (r.get("Data") or {}).get("blocks", [])
    def marker_present(self, bot, cell):
        x, y, z = cell
        return any(b.get("code") in ("rock-granite", "game:rock-granite")
                   and b.get("pos") == [x, y, z]
                   for b in self.cell_blocks(bot, cell))
    def crop_present(self, bot, cell):
        x, y, z = cell
        return any(str(b.get("code") or "").startswith(("crop-", "game:crop-",
                                                        "crop:"))
                   and b.get("pos") == [x, y, z]
                   for b in self.cell_blocks(bot, cell))

# --------------------------------------------------------------------------
# Mission specs. The question text is part of the (model, question, state)
# calibration unit: changing a mission's wording re-derives its threshold.
# --------------------------------------------------------------------------
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
}

def decider_readout(decider_url, state_text, options):
    """Decider-2B choice readout via the live service (decider-service.py):
    one prefill, T=1.3 option-letter softmax. Returns p for each option and
    the argmax choice."""
    t0 = time.time()
    r = http_json(decider_url + "/readout",
                  {"state": state_text, "options": list(options),
                   "question": DECIDER_Q}, timeout=120)
    ms = int((time.time() - t0) * 1000)
    if not r.get("ok"):
        return {"probs": None, "choice": None, "ms": ms,
                "error": r.get("note") or str(r)[:80]}
    return {"probs": r.get("probs"), "choice": r.get("choice"), "ms": ms,
            "error": None}


def decider_readout_fast(prompt_url, card_url, model, state_text, options):
    """Fast path: prompt built by the decider-service (/prompt), inference on
    the GPU card (the 3060 host mux) over the tailnet. decider-fast-client.py."""
    import importlib.util, os
    spec = importlib.util.spec_from_file_location(
        "decider_fast_client",
        os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "jevab", "decider-fast-client.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    t0 = time.time()
    r = mod.fast_readout(prompt_url, card_url, model, state_text,
                         list(options), timeout=60)
    ms = int((time.time() - t0) * 1000)
    if not r.get("ok"):
        return {"probs": None, "choice": None, "ms": ms, "error": r.get("error")}
    return {"probs": r.get("probs"), "choice": r.get("choice"), "ms": ms,
            "error": None}

def laya_noul(openjev, state_text, proposal, mission):
    q = {"type": "noul", "instructions": MISSIONS[mission]["laya_instructions"]}
    t0 = time.time()
    r = http_json(openjev + "/v1/systemone", {
        "state": state_text,
        "questions": {"proposal_ok": q},
    }, timeout=60)
    a = ((r.get("answers") or {}).get("proposal_ok") or {})
    return {"p": a.get("noul"), "ms": int((time.time() - t0) * 1000), "error": r.get("_error")}

def llm_judge(llm_url, model, state_text, proposal, mission):
    """27B doubt-arbiter. Thinking off (measured 2026-09-22): ~124 ms,
    direct single-word answer; thinking on: ~6.4 s and null content."""
    acts = MISSIONS[mission]["actions"]
    t0 = time.time()
    r = http_json(llm_url + "/v1/chat/completions", {
        "model": model,
        "temperature": 0,
        "max_tokens": 128,
        "chat_template_kwargs": {"enable_thinking": False},
        "messages": [
            {"role": "system", "content":
                "You are the action judge of a game-agent safety loop. The "
                "deterministic policy proposed an action; a fast reflex model "
                "was not confident. Given the state, answer with exactly one of: "
                + ", ".join(acts) + "."},
            {"role": "user", "content":
                state_text + "\n\nPolicy proposal: " + proposal +
                " (the reflex was unsure). Which single action should the bot take now?"
                "\n\nOperational rules: " + MISSIONS[mission]["judge_rules"]},
        ],
    }, timeout=120)
    ms = int((time.time() - t0) * 1000)
    try:
        msg = r["choices"][0]["message"]
        text = msg.get("content") or msg.get("reasoning_content") or ""
    except Exception:
        return {"choice": None, "ms": ms, "error": str(r)[:120]}
    if not text:
        return {"choice": None, "ms": ms, "error": "empty completion"}
    m = re.search(r"\b(" + "|".join(acts) + r")\b", text)
    return {"choice": m.group(1) if m else None, "ms": ms, "raw": text[:80],
            "error": None if m else "unparseable: " + text[:60]}

def adjacent_to(pol, bot, cell, ground_y=None):
    x, y, z = cell
    y = ground_y if ground_y is not None else y
    try:
        pos = pol.state(bot)["Bot"]["Pos"]
    except Exception:
        return [x - 1, y, z]
    if pos[0] < x:
        return [x - 1, y, z]
    if pos[0] > x:
        return [x + 1, y, z]
    return [x, y, z - 1] if pos[2] < z else [x, y, z + 1]

def goto_wait(pol, bot, cell, timeout=45):
    r = pol.cmd("goto", [str(cell[0]), str(cell[1]), str(cell[2]), "true", "0.02", "true"], bot)
    if not r.get("Ok") and r.get("arrived") is not True:
        return {"ok": False, "msg": r.get("Message") or r.get("error")}
    t0 = time.time()
    while time.time() - t0 < timeout:
        st = pol.state(bot)
        la = st.get("LastAction") or {}
        if la.get("Name") == "goto" and la.get("Ok") is not None:
            return {"ok": bool(la.get("Ok")), "msg": la.get("Msg") or ""}
        time.sleep(0.5)
    return {"ok": False, "msg": "goto timeout"}

def execute(pol, bot, action, target, base, mission):
    if action in ("goto_target", "goto_base"):
        if action == "goto_target":
            if mission == "harvest":
                # the crop sits one block above the ground; walk the
                # ground-level neighbour (range 4.5 covers the crop)
                cell = (target[0] - 1, base[1], target[2])
            else:
                cell = tuple(adjacent_to(pol, bot, target))
            return goto_wait(pol, bot, cell)
        return goto_wait(pol, bot, base)
    if action == "mine_target":
        timeout = 45
        r = pol.cmd("mine", [str(target[0]), str(target[1]), str(target[2]), "true"], bot)
        if not r.get("Ok") and "mining" not in (r.get("Message") or ""):
            return {"ok": False, "msg": r.get("Message") or r.get("error")}
        # mining is async (~8 s with a tool): success = the marker block is
        # gone (1.22: set-placed rock yields no item drops)
        t0 = time.time()
        while time.time() - t0 < timeout:
            if not pol.marker_present(bot, target):
                return {"ok": True, "msg": "marker removed"}
            time.sleep(1)
        return {"ok": False, "msg": "marker still present after %ds" % timeout}
    if action == "harvest_target":
        # move to a ground-level neighbour first (harvest range is 4.5),
        # then harvest; success = a harvested item ends up on the bot
        cell = (target[0] - 1, base[1], target[2])
        g = goto_wait(pol, bot, cell)
        if not g["ok"] and "arrived" not in str(g.get("msg", "")).lower():
            # being out of range is what the action will tell us; try anyway
            pass
        r = pol.cmd("harvestcrop", [str(target[0]), str(target[1]), str(target[2]), "true"], bot)
        if not r.get("Ok") and "harvesting" not in (r.get("Message") or ""):
            return {"ok": False, "msg": r.get("Message") or r.get("error")}
        t0 = time.time()
        while time.time() - t0 < 45:
            st = pol.state(bot)
            la = st.get("LastAction") or {}
            if la.get("Name") == "harvestcrop" and la.get("Ok") is not None:
                if la.get("Ok"):
                    return {"ok": True, "msg": la.get("Msg") or ""}
                return {"ok": False, "msg": la.get("Msg") or ""}
            time.sleep(1)
        return {"ok": False, "msg": "harvest timeout"}
    if action == "give_tool":
        # give the phase-required tool (pickaxe for mine) until it is carried
        for _ in range(8):
            pol.cmd("give", ["pickaxe-iron", "1"], bot)
            if any("pickaxe" in (c or "") for c in pol.carrying(bot)):
                return {"ok": True, "msg": "pickaxe given"}
            time.sleep(1)
        return {"ok": False, "msg": "pickaxe not carried after 8 gives"}
    if action == "pickup_item":
        # nearest ground item (harness: goto+pickup sequence); success = the
        # pickup action reports, or the ground-item list shrinks
        st0 = pol.state(bot)
        n0 = len(st0.get("Items") or [])
        r = pol.cmd("pickup", [], bot)
        if not r.get("Ok") and "No item entity found" not in (r.get("Message") or ""):
            return {"ok": False, "msg": r.get("Message") or r.get("error") or "pickup refused"}
        t0 = time.time()
        while time.time() - t0 < 30:
            st = pol.state(bot)
            la = st.get("LastAction") or {}
            if la.get("Name") == "pickup" and la.get("Ok") is not None:
                return {"ok": bool(la.get("Ok")), "msg": la.get("Msg") or ""}
            if len(st.get("Items") or []) < n0:
                return {"ok": True, "msg": "ground item removed"}
            time.sleep(1)
        return {"ok": False, "msg": "pickup timeout"}
    if action == "place_block":
        # setblock at the target cell (the fixture's marker block type)
        if mission == "harvest":
            code = "crop-carrot-7"
        else:
            code = "rock-granite"
        r = pol.cmd("setblock", [code, str(target[0]), str(target[1]),
                                 str(target[2])], bot)
        ok = bool(r.get("Ok")) or (r.get("arrived") is True)
        return {"ok": ok, "msg": r.get("Message") or r.get("error") or "setblock"}
    time.sleep(1.5)
    return {"ok": True, "msg": "wait"}

def derive_threshold(rows):
    """From the labeled set: pick TAU that lets the most correct proposals
    through while blocking the most faulty ones. Small-N advisory only."""
    correct = sorted(r["p"] for r in rows if r["p"] is not None and not r["injected"])
    faulty = sorted(r["p"] for r in rows if r["p"] is not None and r["injected"])
    best = None
    cands = sorted(set(correct + faulty) | {0.5, 0.6})
    for tau in cands:
        pass_c = sum(1 for p in correct if p >= tau) / max(len(correct), 1)
        block_f = 1.0 - (sum(1 for p in faulty if p >= tau) / max(len(faulty), 1))
        score = pass_c + block_f
        if best is None or score > best[1]:
            best = (tau, score)
    return {
        "correct_p": correct,
        "faulty_p": faulty,
        "suggested_tau": round(best[0], 3) if best else None,
        "note": "advisory - small N; re-derive as the labeled set grows",
    }

def setup_fixture(a, pol, mission, dist=8):
    """Deterministic start: fresh bot at the player position, fixture placed
    `dist` blocks east. Returns (base, target_cell)."""
    st = pol.state(a.bot)
    bx, by, bz = [int(v) for v in st["Bot"]["Pos"]]
    base = (bx, by, bz)
    if mission == "mine":
        target = (bx + dist, by, bz)
        for _ in range(2):
            pol.cmd("setblock", ["rock-granite", str(target[0]), str(target[1]), str(target[2])], a.bot)
            if pol.marker_present(a.bot, target):
                break
            time.sleep(1)
        # verified tool (the bot's default right hand may be occupied by a
        # profession item; give until the pickaxe is in the backpack/hands)
        for _ in range(8):
            pol.cmd("give", ["pickaxe-iron", "1"], a.bot)
            if any("pickaxe" in (c or "") for c in pol.carrying(a.bot)):
                break
            time.sleep(1)
    else:
        # farmland at ground level, mature crop (stage 7/7) one above
        farmland = (bx + dist, by, bz)
        target = (bx + dist, by + 1, bz)
        pol.cmd("setblock", ["farmland-dry-medium", str(farmland[0]), str(farmland[1]), str(farmland[2])], a.bot)
        for _ in range(2):
            pol.cmd("setblock", ["crop-carrot-7", str(target[0]), str(target[1]), str(target[2])], a.bot)
            if pol.crop_present(a.bot, target):
                break
            time.sleep(1)
    return base, target

def run_once(a, pol, fault_phases):
    mission = a.mission
    # sweep all persisted bots first (accumulated idle bots can wedge the
    # action/traverser system - measured 2026-09-22), then fresh respawn
    pol.sweep_bots(keep=None)
    time.sleep(2)
    if a.bot != "auto":
        pol.cmd("despawn", [], int(a.bot))
        time.sleep(1)
    r = http_json(a.harness + "/polis/command",
                  {"cmd": "spawn", "args": [], "context": {"playerUid": a.uid}})
    new_id = (r.get("Data") or {}).get("id")
    if new_id:
        a.bot = int(new_id)
    pol = Polis(a.harness, a.uid)
    time.sleep(2)
    base, target = setup_fixture(a, pol, mission, a.dist)
    fixture_check = pol.crop_present if mission == "harvest" else pol.marker_present
    has_tool = any("pickaxe" in (c or "") for c in pol.carrying(a.bot))
    print("setup: bot #%d base=%s target=%s mission=%s faults=%s %s fixture=%s" % (
        a.bot, base, target, mission, sorted(fault_phases),
        ("pickaxe=" + str(has_tool)) if mission == "mine" else "crop",
        fixture_check(a.bot, target)), flush=True)

    rows, t_start, fired = [], time.time(), set()
    prev, last_final = None, None
    tool_fails = 0
    for i in range(a.steps):
        st = pol.state(a.bot)
        pos = st["Bot"]["Pos"]
        # mine: the target is a solid block and goto stops one cell short,
        # so the "near" radius must cover that; harvest: the bot walks the
        # air cell next to the crop and arrives exactly.
        radius = 3.5 if mission == "mine" else 2.5
        near_t = dist(pos, target) <= radius
        near_b = dist(pos, base) <= 2.5
        fixture = fixture_check(a.bot, target)
        fixture_gone = not fixture
        carrying = pol.carrying(a.bot)
        has_harvest = any("carrot" in (c or "") for c in carrying)
        # ground items within pickup reach (harness state Items, radius 5)
        ground_items = [i.get("Code") for i in (st.get("Items") or [])
                        if (i.get("Dist") or 99) <= 5]
        need_pickup = fixture_gone and not near_b and bool(ground_items) \
            and (mission == "mine" or not has_harvest)
        if mission == "mine":
            if not fixture_gone:
                phase = "mine" if near_t else "travel"
            elif need_pickup:
                phase = "pickup"
            else:
                phase = "done" if near_b else "return"
        else:
            if not fixture_gone:
                phase = "harvest" if near_t else "travel"
            elif need_pickup:
                phase = "pickup"
            else:
                phase = "done" if near_b else "return"
        # Inject a known-wrong proposal at the FIRST step of chosen phases,
        # BEFORE deriving the oracle (a dropped tool changes what is correct).
        injected = phase in fault_phases and phase not in fired
        drop_done = False
        if injected and phase == "travel":
            pass
        elif injected and phase == "harvest":
            pass
        elif injected and phase == "mine":
            pol.cmd("select", [str(a.bot)], a.bot)
            pol.cmd("drop", [], a.bot)
            t0 = time.time()
            while time.time() - t0 < 10:
                if not any("pickaxe" in (c or "") for c in pol.carrying(a.bot)):
                    drop_done = True
                    break
                pol.cmd("drop", [], a.bot)
                time.sleep(1)

        has_tool = any("pickaxe" in (c or "") for c in pol.carrying(a.bot))
        # Oracle: in the mine phase the correct action depends on tool state -
        # a bot without a pickaxe must get one (give_tool) before it can mine.
        if mission == "mine" and phase == "mine" and not has_tool:
            correct = "give_tool"
        elif phase == "pickup":
            correct = "pickup_item"
        else:
            correct = MISSIONS[mission]["phase_action"][phase]

        proposal = correct
        if injected and (phase == "travel" or phase == "harvest"):
            proposal = "goto_base"      # skip-goal
        elif injected and phase == "mine":
            proposal = "mine_target"    # mine with a missing tool
        changed = []
        if prev is not None:
            if fixture != prev["fixture"]:
                what = "marker" if mission == "mine" else "crop"
                changed.append("%s %s" % (what, "gone" if not fixture else "re-appeared"))
            if mission == "mine":
                has_tool = any("pickaxe" in (c or "") for c in carrying)
                if has_tool != prev["has_tool"]:
                    changed.append("pickaxe %s" % ("re-given" if has_tool else "dropped"))
            if has_harvest != prev["has_harvest"]:
                changed.append("harvested item %s" % ("now carried" if has_harvest else "lost"))
            if bool(ground_items) != prev["has_items"]:
                changed.append("ground item %s" % ("appeared" if ground_items else "picked up"))
            if phase != prev["phase"]:
                changed.append("phase %s -> %s" % (prev["phase"], phase))
        since = ", ".join(changed) if changed else "no change"
        fixture_label = "crop_present" if mission == "harvest" else "marker_present"
        items_line = ", ".join(ground_items[:3]) or "none"
        state_text = (
            "task: %s\n"
            "current phase: %s\n"
            "facts: bot at (%.0f, %d, %.0f), near_target=%s, near_base=%s, %s=%s\n"
            "carrying: %s\nitems: %s\n"
            "since_last_step: %s\nlast_action: %s\nproposed action: %s"
        ) % (
            MISSIONS[mission]["task"], phase, pos[0], pos[1], pos[2],
            "yes" if near_t else "no", "yes" if near_b else "no",
            fixture_label, "yes" if fixture else "no",
            ", ".join((c or "?") for c in carrying[:5]) or "empty",
            items_line,
            since,
            (st.get("LastAction") or {}).get("Msg") or "none",
            proposal,
        )

        # Three-tier cascade, cheapest first:
        #   1) Laya noul pre-filter (anchored yes/no on the proposal)
        #        p < tau_yes  -> 27B doubt-arbiter
        #        p >= tau_yes -> 2) Decider-2B choice readout on the proposal
        #              p(proposal) >= tau_dec -> execute the proposal
        #              p(proposal) <  tau_dec -> 27B doubt-arbiter (disagreement)
        #   The order is deliberate: Laya's anchored yes/no is the robust veto
        #   that catches the Decider's known confident travel-phase error
        #   (corpus: the Decider endorses goto_base over goto_target at ~0.76),
        #   while the Decider's task-tuned readout is the second confirmation
        #   that catches Laya false-yes. The 27B only runs on disagreement.
        reflex = laya_noul(a.openjev, state_text, proposal, mission)
        p, reflex_ms = reflex["p"], reflex["ms"]
        judge, final = None, proposal
        path = None
        if reflex["error"] or p is None or p < a.tau_yes:
            path = ("reflex-err:" + str(reflex["error"])[:16]) if reflex["error"] else "judge"
            judge = llm_judge(a.llm, a.llm_model, state_text, proposal, mission)
            final = judge["choice"] or proposal
        elif a.decider:
            if a.decider_fast and (a.prompt or a.decider):
                dref = decider_readout_fast(a.prompt or a.decider,
                                            a.decider_fast,
                                            a.decider_fast_model, state_text,
                                            MISSIONS[mission]["actions"])
                if dref["error"]:
                    dref = decider_readout(a.decider, state_text,
                                           MISSIONS[mission]["actions"])  # CPU fallback
            else:
                dref = decider_readout(a.decider, state_text, MISSIONS[mission]["actions"])
            p_dec = (dref["probs"].get(proposal)
                     if dref and dref["probs"] is not None else None)
            if dref and dref["error"]:
                path = "decider-err:" + dref["error"][:16]   # service down: execute via Laya only
            elif p_dec is not None and p_dec >= a.tau_dec:
                if p >= a.tau_strong:
                    path = "reflex+decider"                 # confident consensus
                else:
                    path = "reflex+decider->judge"          # Laya borderline: doubt
                    judge = llm_judge(a.llm, a.llm_model, state_text, proposal, mission)
                    final = judge["choice"] or proposal
            else:
                path = "reflex->judge"
                judge = llm_judge(a.llm, a.llm_model, state_text, proposal, mission)
                final = judge["choice"] or proposal
        else:
            path = "reflex"
        p_dec = locals().get("p_dec")   # None unless the decider tier ran
        final = final if final in MISSIONS[mission]["actions"] else "wait"

        # Max-stall safety valve: after two consecutive executed `wait`s
        # control returns to the deterministic policy (the arbiter latches
        # to `wait` after visible failures - measured, prompt-resistant).
        stall_bypass = False
        if final == "wait" and last_final == "wait":
            stall_bypass = True
            final = proposal
        last_final = final

        ex = execute(pol, a.bot, final, target, base, mission)
        # Last-resort tool repair (two strikes): the loop's own tiers get the
        # first chance to choose give_tool; only after two consecutive failed
        # mine attempts without a pickaxe does the deterministic repair fire
        # (keeps missions completable; recorded so it stays visible).
        last_resort = False
        if mission == "mine" and not any("pickaxe" in (c or "") for c in pol.carrying(a.bot)):
            if final == "mine_target" and not ex["ok"]:
                tool_fails += 1
            else:
                tool_fails = 0
            if tool_fails >= 2:
                last_resort = True
                for _ in range(8):
                    pol.cmd("give", ["pickaxe-iron", "1"], a.bot)
                    if any("pickaxe" in (c or "") for c in pol.carrying(a.bot)):
                        break
                    time.sleep(1)
                tool_fails = 0
        else:
            tool_fails = 0

        if injected:
            fired.add(phase)
        match = final == correct
        fault_corrected = injected and final != proposal
        dref_rec = locals().get("dref")
        print("run %d step %d: phase=%-7s prop=%-15s inj=%-5s pl=%-5s pdec=%s path=%-16s judge=%-15s exec=%-15s %s oracle=%s" % (
            a.run, i + 1, phase, proposal, str(injected).lower(),
            ("%.2f" % p) if p is not None else "?",
            ("%.2f" % p_dec) if p_dec is not None else "?", path,
            str(judge["choice"]) if judge else "-", final,
            "OK" if ex["ok"] else "FAIL", "MATCH" if match else "DIFF"), flush=True)
        rows.append({
            "step": i + 1, "phase": phase, "proposal": proposal, "injected": injected,
            "p": p,
            "p_decider": p_dec,
            "decider_choice": dref_rec["choice"] if dref_rec else None,
            "decider_ms": dref_rec["ms"] if dref_rec else None,
            "path": path, "judge_choice": judge["choice"] if judge else None,
            "judge_raw": judge.get("raw") if judge else None,
            "judge_ms": judge["ms"] if judge else None,
            "executed": final, "exec_ok": ex["ok"], "exec_msg": ex["msg"],
            "stall_bypass": stall_bypass,
            "oracle": correct, "match": match, "fault_corrected": fault_corrected,
            "last_resort_repair": last_resort,
            "since_last_step": since,
            "options": list(MISSIONS[mission]["actions"]),
            "items": ground_items,
            "state_text": state_text, "laya_ms": reflex_ms,
        })
        prev = {"fixture": fixture, "phase": phase,
                "has_tool": any("pickaxe" in (c or "") for c in carrying),
                "has_harvest": has_harvest, "has_items": bool(ground_items)}
        last_final = final

        st = pol.state(a.bot)
        at_base = dist(st["Bot"]["Pos"], base) <= 2.5
        if mission == "mine":
            goal = (not pol.marker_present(a.bot, target)) and at_base
        else:
            goal = (any("carrot" in (c or "") for c in pol.carrying(a.bot))) and at_base
        if goal:
            print("run %d: GOAL at step %d (%.0fs)" % (a.run, i + 1, time.time() - t_start), flush=True)
            break

    st = pol.state(a.bot)
    at_base = dist(st["Bot"]["Pos"], base) <= 2.5
    if mission == "mine":
        complete = (not pol.marker_present(a.bot, target)) and at_base
    else:
        complete = (any("carrot" in (c or "") for c in pol.carrying(a.bot))) and at_base
    return rows, {
        "mission_complete": complete,
        "steps_to_complete": next((r["step"] for r in reversed(rows) if r["match"]), None)
        if complete else None,
        "total_sec": int(time.time() - t_start),
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mission", choices=list(MISSIONS), default="mine")
    ap.add_argument("--bot", type=int, default=5)
    ap.add_argument("--steps", type=int, default=8)
    ap.add_argument("--dist", type=int, default=8,
                    help="fixture distance in blocks east of the player (world "
                         "variety: the 29%% travel-phase bias says longer "
                         "travels are the under-represented regime)")
    ap.add_argument("--faults", default="travel,mine",
                    help="phases whose FIRST step gets a known-wrong proposal")
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--tau-dec", type=float, default=0.5,
                    help="Decider reflex gate on p(proposal); corpus: correct "
                         "rows >=0.66, systematic errors <0.5")
    ap.add_argument("--tau-strong", type=float, default=0.40,
                    help="27B on borderline consensus: even a decider-confirm is escalated "
                         "when Laya's noul p is below this (default 0.40, re-derived 2026-09-25 "
                         "overnight from the 15 dual-p rows: false-yes ceiling 0.371 vs correct "
                         "floor 0.400 - thin gap, advisory until the labeled set grows). "
                         "Closes the consensus hole: Laya yes + decider-confirm can still be "
                         "a confidently-wrong pair (the travel bias at 0.37/0.76).")
    ap.add_argument("--tau-yes", type=float, default=0.35,
                    help="Laya-noul confidence below which a proposed action is NOT trusted "
                         "and goes straight to the 27B. Derived 2026-09-22 from the labeled set: "
                         "faulty yes 0.29-0.32 vs correct yes 0.36-0.39 (gap 0.32-0.36).")
    ap.add_argument("--decider", default=os.environ.get("POLIS_DECIDER", ""),
                    help="decider-service.py /readout base URL (empty = v4 behavior)")
    ap.add_argument("--decider-fast", default=os.environ.get("POLIS_DECIDER_FAST", ""),
                    help="GPU card base URL for the fast path (llama-mux llama-server); inference there, prompt from --prompt")
    ap.add_argument("--prompt", default=os.environ.get("POLIS_PROMPT", ""),
                    help="decider-service base URL for /prompt (fast path); falls back to --decider's service")
    ap.add_argument("--decider-fast-model", default="qwen35-decider-2b")
    ap.add_argument("--harness", default="http://127.0.0.1:8585")
    ap.add_argument("--openjev", default=os.environ.get("OPENJEV", "the Laya noul endpoint"),
                    help="Laya noul endpoint (openjev the Laya box on the  LAN)")
    ap.add_argument("--llm", default=os.environ.get("POLIS_LLM", "http://the 27B judge"),
                    help="27B doubt-arbiter endpoint (vLLM the 27B box on the 5600X host)")
    ap.add_argument("--llm-model", default="qwen3.8-27b-dual")
    ap.add_argument("--uid", default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    a.run = 0
    fault_phases = set(x.strip() for x in a.faults.split(",") if x.strip())

    if a.uid is None:
        p = http_json(a.harness + "/polis/players")
        a.uid = ((p.get("Data") or p).get("players") or [{}])[0].get("uid")
    pol = Polis(a.harness, a.uid)

    all_rows, all_outcomes = [], []
    for a.run in range(1, a.repeat + 1):
        rows, outcome = run_once(a, pol, fault_phases)
        all_rows.extend(rows)
        all_outcomes.append(outcome)

    n = len(all_rows)
    faults = [r for r in all_rows if r["injected"]]
    judge_calls = [r for r in all_rows if r["path"].endswith("judge") or r["path"] == "judge"]
    false_waits = [r for r in judge_calls
                   if not r["injected"] and r["judge_choice"] == "wait" and r["oracle"] != "wait"]
    dec_calls = [r for r in all_rows if r.get("p_decider") is not None]
    summary = {
        "loop": "jev-loop-v5 harness (Decider-2B choice reflex + Laya noul + 27B doubt-arbiter)",
        "mission": a.mission,
        "reflex": "decider 2B choice, tau_dec=%s" % a.tau_dec,
        "reflex2": "laya 421M noul, tau_yes=%s tau_strong=%s" % (a.tau_yes, a.tau_strong),
        "judge": a.llm_model + " (thinking off)",
        "runs": a.repeat, "bot": a.bot, "steps_total": n,
        "mission_complete": [o["mission_complete"] for o in all_outcomes],
        "mission_complete_rate": "%d/%d" % (sum(1 for o in all_outcomes if o["mission_complete"]), len(all_outcomes)),
        "avg_steps_to_complete": (sum(o["steps_to_complete"] or a.steps for o in all_outcomes
                                       if o["mission_complete"]) / max(sum(1 for o in all_outcomes if o["mission_complete"]), 1)),
        "injected_faults": len(faults),
        "faults_corrected": "%d/%d" % (sum(1 for r in faults if r["fault_corrected"]), len(faults)),
        "reflex_short_circuits": "%d/%d" % (sum(1 for r in all_rows if r["path"] in ("reflex", "reflex+decider")), n),
        "decider_confirms": "%d/%d" % (sum(1 for r in all_rows if r["path"] == "reflex+decider"), n),
        "avg_decider_ms": (int(sum(r["decider_ms"] or 0 for r in dec_calls) / len(dec_calls))
                           if dec_calls else None),
        "stall_bypasses": sum(1 for r in all_rows if r.get("stall_bypass")),
        "judge_calls": len(judge_calls),
        "false_waits": len(false_waits),
        "judge_oracle_match": "%d/%d" % (sum(1 for r in judge_calls if r["match"]), len(judge_calls)) if judge_calls else "0/0",
        "exec_oracle_match": "%d/%d" % (sum(1 for r in all_rows if r["match"]), n),
        "exec_success": "%d/%d" % (sum(1 for r in all_rows if r["exec_ok"]), n),
        "avg_laya_ms": int(sum(r["laya_ms"] for r in all_rows if r["laya_ms"] is not None)
                           / max(sum(1 for r in all_rows if r["laya_ms"] is not None), 1)),
        "avg_judge_ms": (int(sum(r["judge_ms"] for r in judge_calls) / len(judge_calls))
                         if judge_calls else None),
        "threshold_derivation": derive_threshold(all_rows),
        "laya_question": MISSIONS[a.mission]["laya_instructions"],
        "rows": all_rows,
    }
    print("\n=== JEVO LOOP v5 SUMMARY (harness) ===")
    print(json.dumps({k: v for k, v in summary.items() if k != "rows"}, indent=1))
    if a.out:
        json.dump(summary, open(a.out, "w"), indent=1)
        print("wrote", a.out)

if __name__ == "__main__":
    main()
