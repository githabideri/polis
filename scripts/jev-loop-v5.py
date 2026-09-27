#!/usr/bin/env python3
"""
Jev-loop v5 (optimization-harness form) - polis decision loop.

Three-tier decision (cheapest first):
  policy proposes an action for the current phase
    -> Laya 421M noul pre-filter (anchored yes/no, ~1.5-2.5 s)
         p < TAU_YES -> 27B doubt-arbiter (thinking off, ~0.2-0.7 s)
         p >= TAU_YES -> Decider-2B choice readout (~3-4 s CPU, ~0.3 s GPU)
              p(proposal) < TAU_DEC -> 27B doubt-arbiter
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
  mine : mine the marker block, return to base.
            Success = marker block removed (scan-verified) AND bot at base.
            (1.22 note: set-placed rock has no BE type, so no item drops -
            block removal is the deterministic success criterion.)
  harvest : harvest the crop, return to base.
            Success = bot CARRIES a harvested item (vegetable/seed) AND is
            at base - the agent produced and carried a real item.

Positive controls (fault injection): at chosen phases' FIRST step a
KNOWN-WRONG proposal is injected:
  travel : goto_base (skips the goal)
  mine : tool dropped + mine_target (missing tool)
  harvest : goto_base (skips the goal)

Every step is recorded as a LABELED example (state, proposal, oracle
action, reflex p, path, judge answer, executed, outcome) - the raw
material for re-deriving the threshold when the model or question
changes (calibration protocol, llmlab docs/decision-classifiers.md).

PHASE 0 CONTRACT: build_state_text() (the FT-trained 8-line reflex
prompt) and decide_cascade() (the three-tier decision rule) are pure
functions frozen as the behavioral contract of this loop; golden
fixtures + the replay gate live in tests/reflex/contract.py, the
nightly canary guards the prompt against model drift.

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
import argparse, base64, glob, hashlib, json, os, re, sys, time, urllib.request

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

class Polis:
    def __init__(self, base, uid):
        self.base, self.uid = base
        self.last_scan = None  # last /polis/command scan response (T4 raw context), uid
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
        """All item codes on the bot (see carrying_from)."""
        return carrying_from(self.state(bot))
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
        self.last_scan = r
        return (r.get("Data") or {}).get("blocks", [])
    def marker_present(self, bot, cell, marker=None):
        x, y, z = cell
        codes = ((marker, "game:" + marker) if marker
                 else ("rock-granite", "game:rock-granite"))
        return any(b.get("code") in codes
                   and b.get("pos") == [x, y, z]
                   for b in self.cell_blocks(bot, cell))
    def crop_present(self, bot, cell):
        x, y, z = cell
        return any(str(b.get("code") or "").startswith(("crop-", "game:crop-",
                                                        "crop:"))
                   and b.get("pos") == [x, y, z]
                   for b in self.cell_blocks(bot, cell))
    def site_filled(self, bot, cell):
        """True if the exact cell holds any (non-air) block. Build mission:
 the site starts EMPTY and place_block fills it (inverted fixture
        compared to mine/harvest, where presence is the start state)."""
        x, y, z = cell
        return any(b.get("pos") == [x, y, z]
                   and str(b.get("code") or "") not in ("", "air", "game:air")
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

def llm_judge(llm_url, model, state_text, proposal, mission, frame_b64=None):
    """27B doubt-arbiter. Thinking off (measured 2026-09-22): ~124 ms,
    direct single-word answer; thinking on: ~6.4 s and null content.
    frame_b64 (dashcam): a PNG of the bot's scene rides along - the 27B
    is vision-capable (the video-assist path) and sees what text cannot
    express: terrain, where items actually are, wedges."""
    acts = MISSIONS[mission]["actions"]
    t0 = time.time()
    system = ("You are the action judge of a game-agent safety loop. The "
              "deterministic policy proposed an action; a fast reflex model "
              "was not confident. Given the state, answer with exactly one of: "
              + ", ".join(acts) + ".")
    user = (state_text + "\n\nPolicy proposal: " + proposal +
            " (the reflex was unsure). Which single action should the bot take now?"
            "\n\nOperational rules: " + MISSIONS[mission]["judge_rules"])
    if frame_b64:
        system += (" A screenshot taken at the bot's position accompanies "
                   "the state; use it for what the text channel cannot "
                   "express (terrain, where items actually are, wedges).")
        user = ([{"type": "text", "text": user},
                 {"type": "image_url", "image_url":
                  {"url": "data:image/png;base64," + frame_b64}}])
    r = http_json(llm_url + "/v1/chat/completions", {
        "model": model,
        "temperature": 0,
        "max_tokens": 128,
        "chat_template_kwargs": {"enable_thinking": False},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
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

# --- Dashcam: the visual second line (2026-09-26) --------------------------
# The structured state is the record; the dashcam is what the world LOOKED
# like. Every frame is an observer-screenshot placed at the bot's position
# (explicit x/y/z/yaw/pitch - deterministic placement, no camera
# calibration; the harness briefly moves the idle player to the viewpoint
# and restores it, the bot itself is untouched). Captures are non-fatal:
# a failed shot degrades to "no frame", never to a failed run.

def dashcam_frame(pol, outdir, name, pos, yaw, pitch=-10, timeout=20):
    """One observer frame from the bot's position. Writes name into
    outdir; returns (base64_png_or_None, error_or_None)."""
    q = ("/polis/observer-screenshot?playerUid=%s&x=%g&y=%g&z=%g"
         "&yaw=%g&pitch=%g&save=false" % (pol.uid, pos[0], pos[1] + 1,
                                          pos[2], yaw, pitch))
    try:
        r = http_json(pol.base + q, None, timeout)
    except Exception as e:
        return None, repr(e)[:80]
    b = r.get("base64Png")
    if not r.get("ok") or not b:
        return None, (r.get("error") or "observer capture failed")[:80]
    if outdir and name:
        os.makedirs(outdir, exist_ok=True)
        open(os.path.join(outdir, name), "wb").write(base64.b64decode(b))
    return b, None


def dashcam_yaw_to(pos, cell):
    """Approximate observer yaw facing the mission cell (cosmetic - the
    end-of-run six-view panorama covers all bearings either way)."""
    import math
    return math.degrees(math.atan2(cell[0] - pos[0], cell[2] - pos[2]))


def dashcam_wedge(pol, outdir, tag, pos, yaw, timeout=15):
    """Frozen-world probe (the 2026-09-21 wedge signature, no model):
    two frames 3 s apart from the same viewpoint; identical PNG bytes
    (same scene, deterministic encoder) mean the world rendered no
    change at all. Returns True/False, or None if the capture failed."""
    b1, _ = dashcam_frame(pol, None, None, pos, yaw, timeout=timeout)
    time.sleep(3)
    b2, _ = dashcam_frame(pol, outdir, "wedge-%s.png" % tag, pos, yaw,
                          timeout=timeout)
    if not b2:
        return None
    return b1 == b2


def dashcam_panorama(pol, outdir, pos, prefix, timeout=20):
    """End-of-run six views from the bot's position: four bearings plus
    straight up/down (the canyon check)."""
    files = []
    for yaw, nm in ((0, "v0"), (90, "v90"), (180, "v180"), (270, "v270")):
        b, _ = dashcam_frame(pol, outdir, "%s-%s.png" % (prefix, nm), pos,
                             yaw, timeout=timeout)
        if b:
            files.append("%s-%s.png" % (prefix, nm))
    for pitch, nm in ((-90, "up"), (90, "down")):
        b, _ = dashcam_frame(pol, outdir, "%s-%s.png" % (prefix, nm), pos,
                             0, pitch=pitch, timeout=timeout)
        if b:
            files.append("%s-%s.png" % (prefix, nm))
    return files


def dashcam_sheet(outdir, rows):
    """The annotated contact sheet: open index.html and watch the run.
    Each captured frame gets the decision data of the step that took it."""
    import html as _html
    by_name = {}
    for r in rows:
        if r.get("dashcam"):
            by_name.setdefault(r["dashcam"], r)
    sections = []
    for f in sorted(glob.glob(os.path.join(outdir, "*.png"))):
        name = os.path.basename(f)
        r = by_name.get(name)
        if r:
            cap = ("run %s \u00b7 step %s \u00b7 phase %s \u00b7 path %s \u00b7 p=%s \u00b7 "
                   "p_dec=%s \u00b7 judge=%s \u00b7 executed %s \u00b7 oracle %s%s"
                   % (r.get("run"), r["step"], r["phase"], r["path"],
                      ("%.3f" % r["p"]) if r.get("p") is not None else "?",
                      ("%.3f" % r["p_decider"])
                      if r.get("p_decider") is not None else "n/a",
                      r.get("judge_choice") or "-", r["executed"],
                      r["oracle"],
                      " \u00b7 FROZEN-WORLD" if r.get("dashcam_frozen") else ""))
        elif name.startswith("wedge-"):
            cap = ("wedge probe (two frames 3 s apart; identical bytes = "
                   "the world rendered no change at all)")
        elif "-end-" in name:
            cap = "end-of-run panorama (%s)" % name.split("-end-")[-1]
        else:
            cap = name
        sections.append(
            '<div class="f"><img src="%s"><div class="c">%s</div></div>'
            % (_html.escape(name), _html.escape(cap)))
    page = ('<!doctype html><title>polis dashcam</title>'
            '<style>body{background:#111;color:#eee;font:13px monospace;'
            'margin:24px}.f{display:inline-block;width:31.5%%;margin:0.8%%;'
            'vertical-align:top}img{width:100%%;border:1px solid #444}'
            '.c{color:#9cf;font-size:12px;padding-top:4px;'
            'white-space:pre-wrap}</style>'
            '<h2>polis dashcam \u2014 %d frames</h2>%s'
            % (len(sections), "".join(sections)))
    open(os.path.join(outdir, "index.html"), "w").write(page)
    return len(sections)


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

def execute(pol, bot, action, target, base, mission, autocollect=True,
            marker="rock-granite", crop="crop-carrot-7",
            buildblock="rock-granite"):
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
        # approach first: the 27B's judge rule says the execution moves the
        # bot to the target (goal-first), and the 09-25 pickup3 run showed
        # the mine FATAL-loops out-of-range when the bot is 12+ blocks away
        # (goto stops one cell short of the solid block - exactly in range)
        g = goto_wait(pol, bot, target)
        if not g["ok"] and "arrived" not in str(g.get("msg", "")).lower():
            pass # being out of range is what the action will tell us
        r = pol.cmd("mine", [str(target[0]), str(target[1]), str(target[2]), "true" if autocollect else "false"], bot)
        if not r.get("Ok") and "mining" not in (r.get("Message") or ""):
            return {"ok": False, "msg": r.get("Message") or r.get("error")}
        # mining is async (~8 s with a tool): success = the marker block is
        # gone (1.22: set-placed rock yields no *usable* drops, but the v4
        # run observed the block dropping itself as an item entity - which
        # is exactly what makes the pickup phase reachable without
        # autocollect)
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
        r = pol.cmd("harvestcrop", [str(target[0]), str(target[1]), str(target[2]), "true" if autocollect else "false"], bot)
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
        if mission == "build":
            # the build "tool" is the block itself
            for _ in range(8):
                pol.cmd("give", [buildblock, "1"], bot)
                if any(buildblock in (c or "") for c in pol.carrying(bot)):
                    return {"ok": True, "msg": buildblock + " given"}
                time.sleep(1)
            return {"ok": False, "msg": buildblock + " not carried after 8 gives"}
        # give the phase-required tool (pickaxe for mine) until it is carried
        for _ in range(8):
            pol.cmd("give", ["pickaxe-iron", "1"], bot)
            if any("pickaxe" in (c or "") for c in pol.carrying(bot)):
                return {"ok": True, "msg": "pickaxe given"}
            time.sleep(1)
        return {"ok": False, "msg": "pickaxe not carried after 8 gives"}
    if action == "pickup_item":
        # nearest ground item (harness: goto+pickup sequence); success = the
        # pickup action reports, or the ground-item list shrinks.
        # Approach step: item entities drop where the source block was, so
        # after a ranged harvest/mine they can sit just beyond the 3.0
        # pickup range (observed live 2026-09-26: rye seeds 3.26 out). Go to
        # the item's cell first, then pick up (same pattern as the mine
        # approach step); durable fix = the mod's pickup action self-
        # approaching (PolisPickupItemAction currently Fails on dist>range).
        st0 = pol.state(bot)
        n0 = len(st0.get("Items") or [])
        items = st0.get("Items") or []
        if items and (items[0].get("Dist") or 0) > 2.5:
            ip = items[0].get("Pos") or []
            if len(ip) == 3:
                goto_wait(pol, bot, (int(ip[0]), int(ip[1]), int(ip[2])), timeout=20)
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
        if mission == "build":
            # REAL placement (harness place <block> x y z): finds the block
            # in the bot's inventory, gootos the approach cell, places one.
            r = pol.cmd("place", [buildblock, str(target[0]), str(target[1]),
                                  str(target[2])], bot, timeout=180)
            if not r.get("Ok"):
                return {"ok": False, "msg": r.get("Message") or "place refused"}
            t0 = time.time()
            while time.time() - t0 < 90:
                la = pol.state(bot).get("LastAction") or {}
                if la.get("Name") == "place" and la.get("Ok") is not None:
                    return {"ok": bool(la.get("Ok")), "msg": la.get("Msg") or ""}
                time.sleep(2)
            return {"ok": False, "msg": "place timeout"}
        # non-build: setblock at the target cell (distractor path)
        code = crop if mission == "harvest" else marker
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
        if a.pocket:
            # natural context: stone-limestone cluster around the marker
            # cell (the target cell itself is set last, so the marker wins)
            for dx in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    if (dx, dz) != (0, 0):
                        pol.cmd("setblock", ["stone-limestone", str(target[0] + dx),
                                             str(by), str(target[2] + dz)], a.bot)
        for _ in range(2):
            pol.cmd("setblock", [a.marker, str(target[0]), str(target[1]), str(target[2])], a.bot)
            if pol.marker_present(a.bot, target, a.marker):
                break
            time.sleep(1)
        # verified tool (the bot's default right hand may be occupied by a
        # profession item; give until the pickaxe is in the backpack/hands)
        for _ in range(8):
            pol.cmd("give", ["pickaxe-iron", "1"], a.bot)
            if any("pickaxe" in (c or "") for c in pol.carrying(a.bot)):
                break
            time.sleep(1)
    elif mission == "harvest":
        # farmland at ground level, mature crop one above
        farmland = (bx + dist, by, bz)
        target = (bx + dist, by + 1, bz)
        pol.cmd("setblock", ["farmland-dry-medium", str(farmland[0]), str(farmland[1]), str(farmland[2])], a.bot)
        for _ in range(2):
            pol.cmd("setblock", [a.crop, str(target[0]), str(target[1]), str(target[2])], a.bot)
            if pol.crop_present(a.bot, target):
                break
            time.sleep(1)
    else:
        # build: the target is the air cell at the bot's foot level `dist`
        # east; the cell below is ground (the place action clicks it, face
        # up). Give the bot the block it will place.
        target = (bx + dist, by, bz)
        for _ in range(2):
            if pol.site_filled(a.bot, target):
                pol.cmd("setblock", ["air", str(target[0]), str(target[1]),
                                     str(target[2])], a.bot)
                time.sleep(1)
            else:
                break
        for _ in range(8):
            pol.cmd("give", [a.buildblock, "1"], a.bot)
            if any(a.buildblock in (c or "") for c in pol.carrying(a.bot)):
                break
            time.sleep(1)
    # baseline carry (after tool gives): harvest completion is "something
    # new and non-tool was acquired", not a hardcoded crop code (the old
    # "carrot in carrying" check broke on rye/oat/etc - 2026-09-26 R1b)
    base_carry = set(c for c in pol.carrying(a.bot) if c)
    return base, target, base_carry

def build_state_text(task, phase, pos, near_t, near_b, fixture_label, fixture,
                     carrying, items_line, since, last_action_msg, proposal):
    """The reflex prompt - the 8-line format the 2B decider was fine-tuned on.

    PHASE 0 CONTRACT (docs/design/2026-09-26-job-system-r2.md, §5.4):
    given identical inputs this function must stay BYTE-IDENTICAL. The FT
    model was trained on exactly this representation; changing wording is a
    model regression, not a refactor (gates: tests/reflex/contract.py,
    nightly canary, abstain corpus).
    """
    return (
        "task: %s\n"
        "current phase: %s\n"
        "facts: bot at (%.0f, %d, %.0f), near_target=%s, near_base=%s, %s=%s\n"
        "carrying: %s\nitems: %s\n"
        "since_last_step: %s\nlast_action: %s\nproposed action: %s"
    ) % (
        task, phase, pos[0], pos[1], pos[2],
        "yes" if near_t else "no", "yes" if near_b else "no",
        fixture_label, "yes" if fixture else "no",
        ", ".join((c or "?") for c in carrying[:5]) or "empty",
        items_line,
        since,
        last_action_msg,
        proposal,
    )

def needs_judge(reflex, dref, proposal, tau_yes, tau_dec, tau_strong):
    """True exactly when the original cascade would call the 27B for this
    step (pure predicate over recorded tier outputs; see decide_cascade).
    """
    p = (reflex or {}).get("p")
    if (reflex is None) or (reflex or {}).get("error") \
            or (p is None) or (p < tau_yes):
        return True
    if dref is None or dref.get("error"):
        return False
    p_dec = dref["probs"].get(proposal) if dref.get("probs") is not None else None
    if p_dec is None or p_dec < tau_dec:
        return True
    return p < tau_strong

def decide_cascade(reflex, dref, judge, proposal, valid_actions, last_final,
                   tau_yes, tau_dec, tau_strong):
    """The three-tier decision rule as a PURE function over recorded model
    outputs - the Phase 0 contract (tests/reflex/contract.py replays
    fixtures through this and must reproduce the recorded path/final).

    reflex: {"p": float|None, "error": ...} | None (Laya noul tier)
    dref:   {"probs": dict|None, "error": ...} | None (Decider tier)
    judge:  {"choice": ...} | None (27B; the caller fetches it only when
            needs_judge() says so, so a None here means "not called")

    Returns (path, final, stall_bypass, p_dec).
    """
    p = (reflex or {}).get("p")
    p_dec = None
    path, final = None, proposal
    if (reflex is None) or (reflex or {}).get("error") \
            or (p is None) or (p < tau_yes):
        path = ("reflex-err:" + str((reflex or {}).get("error"))[:16]) \
            if (reflex or {}).get("error") else "judge"
        final = judge["choice"] or proposal if judge is not None else proposal
    elif dref is not None:
        p_dec = dref["probs"].get(proposal) \
            if dref.get("probs") is not None else None
        if dref.get("error"):
            path = "decider-err:" + str(dref["error"])[:16] # service down: execute via Laya only
        elif p_dec is not None and p_dec >= tau_dec:
            if p >= tau_strong:
                path = "reflex+decider" # confident consensus
            else:
                path = "reflex+decider->judge" # Laya borderline: doubt
                final = judge["choice"] or proposal if judge is not None else proposal
        else:
            path = "reflex->judge"
            final = judge["choice"] or proposal if judge is not None else proposal
    else:
        path = "reflex"
    final = final if final in valid_actions else "wait"
    # Max-stall safety valve: after two consecutive executed `wait`s control
    # returns to the deterministic policy (the arbiter latches to `wait`
    # after visible failures - measured, prompt-resistant).
    stall_bypass = False
    if final == "wait" and last_final == "wait":
        stall_bypass = True
        final = proposal
    return path, final, stall_bypass, p_dec

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
    base, target, base_carry = setup_fixture(a, pol, mission, a.dist)
    if mission == "harvest":
        fixture_check = pol.crop_present
    elif mission == "build":
        fixture_check = pol.site_filled
    else:
        fixture_check = lambda bot, cell: pol.marker_present(bot, cell, a.marker)
    has_tool = any("pickaxe" in (c or "") for c in pol.carrying(a.bot))
    setup_note = (("pickaxe=" + str(has_tool)) if mission == "mine"
                  else ("block=" + str(any(a.buildblock in (c or "")
                                           for c in pol.carrying(a.bot)))
                       if mission == "build" else "crop"))
    print("setup: bot #%d base=%s target=%s mission=%s faults=%s %s fixture=%s" % (
        a.bot, base, target, mission, sorted(fault_phases),
        setup_note,
        fixture_check(a.bot, target)), flush=True)

    rows, t_start, fired = [], time.time(), set()
    prev, last_final = None, None
    tool_fails = 0
    goal_step = None
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
        carry_resp = pol.state(a.bot)
        carrying = carrying_from(carry_resp)
        scan_resp = pol.last_scan
        has_harvest = any("carrot" in (c or "") for c in carrying)
        has_block = any(a.buildblock in (c or "") for c in carrying)
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
        elif injected and phase == "build":
            # drop the build block from the hand: the correct answer becomes
            # give_tool (mirror of the mine fault: mine with a missing tool)
            pol.cmd("select", [str(a.bot)], a.bot)
            pol.cmd("drop", [], a.bot)
            t0 = time.time()
            while time.time() - t0 < 10:
                if not any(a.buildblock in (c or "") for c in pol.carrying(a.bot)):
                    drop_done = True
                    break
                pol.cmd("drop", [], a.bot)
                time.sleep(1)

        has_tool = any("pickaxe" in (c or "") for c in pol.carrying(a.bot))
        # recompute after a possible fault injection (a dropped block changes
        # what is correct, same as the mine tool-drop above)
        has_block = any(a.buildblock in (c or "") for c in pol.carrying(a.bot))
        # Oracle: in the mine phase the correct action depends on tool state -
        # a bot without a pickaxe must get one (give_tool) before it can mine.
        # Same for build: a bot without the block must get one before placing.
        if mission == "mine" and phase == "mine" and not has_tool:
            correct = "give_tool"
        elif mission == "build" and phase == "build" and not has_block:
            correct = "give_tool"
        elif phase == "pickup":
            correct = "pickup_item"
        else:
            correct = MISSIONS[mission]["phase_action"][phase]

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
            if mission == "build" and has_block != prev["has_block"]:
                changed.append("granite %s" % ("now carried" if has_block else "dropped"))
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
        if mission == "harvest":
            fixture_label = "crop_present"
        elif mission == "build":
            fixture_label = "build_site_filled"
        else:
            fixture_label = "marker_present"
        items_line = ", ".join(ground_items[:3]) or "none"
        last_msg = (st.get("LastAction") or {}).get("Msg") or "none"
        # T4 (review round 2, 2026-09-27): the reflex-state DTO - the exact
        # inputs build_state_text consumes. Recorded per step together with
        # the raw context ("raw" below) so a later implementation can be
        # proven to construct the SAME state from the SAME observations.
        reflex_state = {
            "task": a.task or MISSIONS[mission]["task"],
            "phase": phase, "pos": pos,
            "near_t": near_t, "near_b": near_b,
            "fixture_label": fixture_label, "fixture": fixture,
            "carrying": carrying, "items_line": items_line,
            "since": since, "last_msg": last_msg,
            "proposal": proposal,
        }
        state_text = build_state_text(
            reflex_state["task"], phase, pos, near_t, near_b,
            fixture_label, fixture, carrying, items_line, since,
            last_msg, proposal)

        # Dashcam (always mode): one frame per step - the scene before
        # this step's decision. Non-fatal; a failed shot is "no frame".
        step_b64 = None
        if a.dashcam == "always":
            step_b64, _ = dashcam_frame(pol, a.dashcam_dir,
                                        "r%02d-step%02d.png" % (a.run, i + 1),
                                        pos, dashcam_yaw_to(pos, target))

        def _judge_frame():
            """The image the doubt-arbiter sees for this step (auto mode
            captures one; always mode reuses the per-step frame)."""
            if getattr(a, "dashcam_dir", None) is None:
                return None
            if a.dashcam == "always" and step_b64:
                return step_b64
            return dashcam_frame(pol, a.dashcam_dir,
                                 "r%02d-judge%02d.png" % (a.run, i + 1),
                                 pos, dashcam_yaw_to(pos, target))[0]

        # Three-tier cascade, cheapest first:
        # 1) Laya noul pre-filter (anchored yes/no on the proposal)
        # p < tau_yes -> 27B doubt-arbiter
        # p >= tau_yes -> 2) Decider-2B choice readout on the proposal
        # p(proposal) >= tau_dec -> execute the proposal
        # p(proposal) < tau_dec -> 27B doubt-arbiter (disagreement)
        # The order is deliberate: Laya's anchored yes/no is the robust veto
        # that catches the Decider's known confident travel-phase error
        # (corpus: the Decider endorses goto_base over goto_target at ~0.76),
        # while the Decider's task-tuned readout is the second confirmation
        # that catches Laya false-yes. The 27B only runs on disagreement.
        reflex = laya_noul(a.openjev, state_text, proposal, mission)
        p, reflex_ms = reflex["p"], reflex["ms"]
        dref = None
        if a.decider or a.decider_fast:
            if a.decider_fast:
                dref = decider_readout_fast(a.prompt or a.decider,
                                            a.decider_fast,
                                            a.decider_fast_model, state_text,
                                            MISSIONS[mission]["actions"])
                if dref["error"] and a.decider:
                    dref = decider_readout(a.decider, state_text,
                                           MISSIONS[mission]["actions"]) # CPU fallback
            else:
                dref = decider_readout(a.decider, state_text, MISSIONS[mission]["actions"])
        judge = None
        if needs_judge(reflex, dref, proposal, a.tau_yes, a.tau_dec, a.tau_strong):
            judge = llm_judge(a.llm, a.llm_model, state_text, proposal,
                              mission, frame_b64=_judge_frame())
        path, final, stall_bypass, p_dec = decide_cascade(
            reflex, dref, judge, proposal, MISSIONS[mission]["actions"],
            last_final, a.tau_yes, a.tau_dec, a.tau_strong)

        # The stall-bypass wedge shot (decide_cascade flagged the bypass).
        dashcam_frozen = None
        if stall_bypass and a.dashcam == "auto":
            dashcam_frozen = dashcam_wedge(
                a.dashcam_dir, "r%02d-s%02d" % (a.run, i + 1),
                pos, dashcam_yaw_to(pos, target))
        last_final = final

        ex = execute(pol, a.bot, final, target, base, mission,
                     autocollect=not a.no_autocollect,
                     marker=a.marker, crop=a.crop, buildblock=a.buildblock)
        dashcam_fail = None
        if a.dashcam == "auto" and not ex["ok"]:
            pos_f = pol.state(a.bot)["Bot"]["Pos"]
            dashcam_fail = "r%02d-fail%02d.png" % (a.run, i + 1)
            dashcam_frame(pol, a.dashcam_dir, dashcam_fail, pos_f,
                          dashcam_yaw_to(pos_f, target))
        if a.dashcam == "always" and step_b64:
            dashcam_name = "r%02d-step%02d.png" % (a.run, i + 1)
        elif a.dashcam == "auto" and judge is not None:
            dashcam_name = "r%02d-judge%02d.png" % (a.run, i + 1)
        else:
            dashcam_name = dashcam_fail
        if (a.drop_after_harvest and mission == "harvest"
                and final == "harvest_target" and ex["ok"]):
            # world event: the harvest's item(s) are dropped at the crop
            # site, so the next state has ground items and the bot empty -
            # the pickup phase becomes mandatory before return.
            time.sleep(1)
            pol.cmd("drop", [], a.bot)
            time.sleep(1)
        elif (a.drop_after_mine and mission == "mine"
                and final == "mine_target" and ex["ok"]):
            # world event: mine drops go to the inventory first, so if none
            # landed on the ground, make one appear (give -> hand -> drop at
            # the mine site) so the pickup phase is reachable.
            time.sleep(1)
            st2 = pol.state(a.bot)
            gi = [i for i in (st2.get("Items") or [])
                  if (i.get("Dist") or 99) <= 5]
            if not gi:
                pol.cmd("give", [a.marker, "1"], a.bot)
                time.sleep(0.5)
                pol.cmd("drop", [], a.bot)
                time.sleep(0.5)
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
            "dashcam": dashcam_name, "dashcam_frozen": dashcam_frozen,
            "run": a.run,
            "oracle": correct, "match": match, "fault_corrected": fault_corrected,
            "last_resort_repair": last_resort,
            "since_last_step": since,
            "options": list(MISSIONS[mission]["actions"]),
            "items": ground_items,
            "state_text": state_text, "laya_ms": reflex_ms,
            "reflex_state": reflex_state,
            "raw": {
                "mission": mission, "task": a.task, "dist": a.dist,
                "marker": a.marker, "crop": a.crop,
                "buildblock": a.buildblock,
                "target": target, "base": base,
                "state": st, "carry_state": carry_resp,
                "scan": scan_resp, "prev": prev,
            },
        })
        prev = {"fixture": fixture, "phase": phase,
                "has_tool": any("pickaxe" in (c or "") for c in carrying),
                "has_block": has_block,
                "has_harvest": has_harvest, "has_items": bool(ground_items)}
        last_final = final

        st = pol.state(a.bot)
        at_base = dist(st["Bot"]["Pos"], base) <= 2.5
        if mission == "mine":
            goal = (not pol.marker_present(a.bot, target)) and at_base
        elif mission == "build":
            goal = pol.site_filled(a.bot, target) and at_base
        else:
            goal = (any("carrot" in (c or "") for c in pol.carrying(a.bot))) and at_base
        if goal:
            goal_step = i + 1
            print("run %d: GOAL at step %d (%.0fs)" % (a.run, i + 1, time.time() - t_start), flush=True)
            break

    st = pol.state(a.bot)
    at_base = dist(st["Bot"]["Pos"], base) <= 2.5
    if mission == "mine":
        complete = (not pol.marker_present(a.bot, target, a.marker)) and at_base
    elif mission == "build":
        complete = pol.site_filled(a.bot, target) and at_base
    else:
        # crop-generic completion: a new non-tool item was acquired
        complete = at_base and any(
            (c not in base_carry)
            and not any(t in (c or "") for t in ("pickaxe", "linensack"))
            for c in pol.carrying(a.bot))
    if getattr(a, "dashcam_dir", None):
        # end-of-run six views from where the bot ended up (the canyon
        # check: up/down included)
        dashcam_panorama(pol, a.dashcam_dir, st["Bot"]["Pos"],
                         "r%02d-end" % a.run)
    return rows, {
        "mission_complete": complete,
        "steps_to_complete": next((r["step"] for r in reversed(rows) if r["match"]), None)
        if complete else None,
        # T2b (review round 2): run-level transitions are part of the
        # frozen contract - a run that decides identically but ends one
        # step early/late (or completes where the oracle didn't) is a
        # gate failure.
        "goal_step": goal_step,
        "steps_run": len(rows),
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
    ap.add_argument("--marker", default="rock-granite",
                    help="mine fixture: block code set at the target cell "
                         "(R1: real block types, e.g. stone-coal)")
    ap.add_argument("--crop", default="crop-carrot-7",
                    help="harvest fixture: crop code set above the farmland "
                         "(R1: real crops, e.g. crop-wheat-12)")
    ap.add_argument("--buildblock", default="rock-granite",
                    help="build mission: the block the bot places and the "
                         "one given by give_tool (1.22: rock-* are the "
                         "placeable stones; item and block share the code)")
    ap.add_argument("--task", default=None,
                    help="override the state-text task line (R1: natural "
                         "mission phrasing, e.g. 'mine the coal ore, then "
                         "return to base')")
    ap.add_argument("--dashcam", choices=["off", "auto", "always"],
                    default="off",
                    help="visual second line: auto = a frame on doubt rows "
                         "(sent to the 27B judge as an image), on failed "
                         "executions, a frozen-world wedge probe on stall "
                         "bypass, and a six-view panorama at run end; "
                         "always = one frame per step as well. Frames go to "
                         "<out>-dashcam/ with an annotated index.html "
                         "contact sheet. off = structured data only.")
    ap.add_argument("--pocket", action="store_true",
                    help="mine fixture: surround the target cell with a 3x3 "
                         "stone-limestone cluster (natural ore-pocket "
                         "context around the marker)")
    ap.add_argument("--no-autocollect", action="store_true",
                    help="mine/harvest: run the mine/harvest action without "
                         "autocollect so the drops land on the ground - the "
                         "pickup phase becomes reachable (a set-placed "
                         "rock-granite drops itself as an item entity; the "
                         "harvest path is covered by --drop-after-harvest "
                         "instead, since harvestcrop inserts the main crop "
                         "into the backpack directly)")
    ap.add_argument("--drop-after-harvest", action="store_true",
                    help="harvest only: after a successful harvest, drop the "
                         "carried items (polis drop) so they land on the "
                         "ground - the pickup phase then becomes mandatory "
                         "before the mission can finish")
    ap.add_argument("--drop-after-mine", action="store_true",
                    help="mine only: after a successful mine, if no ground item "
                         "appeared (mine drops insert into the inventory first; "
                         "ground overflow is non-deterministic), give + drop a "
                         "stone-granite at the mine site so the pickup phase "
                         "becomes reachable")
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
                    help="decider-service.py /readout base URL (CPU fallback for the "
                         "fast path; with only --decider-fast it may stay empty)")
    ap.add_argument("--decider-fast", default=os.environ.get("POLIS_DECIDER_FAST", ""),
                    help="GPU card base URL for the fast path (llama-mux llama-server); inference there, prompt from --prompt")
    ap.add_argument("--prompt", default=os.environ.get("POLIS_PROMPT", ""),
                    help="decider-service base URL for /prompt (fast path); falls back to --decider's service")
    ap.add_argument("--decider-fast-model", default="qwen35-decider-2b-ft2",
                    help="reflex model id on the card (ft2 = 2026-09-26 LoRA round 2: "
                         "build + wait-abstention; ft = round 1; base: qwen35-decider-2b)")
    ap.add_argument("--harness", default="http://127.0.0.1:8585")
    ap.add_argument("--openjev", default=os.environ.get("OPENJEV", "the Laya noul endpoint"),
                    help="Laya noul endpoint (openjev the Laya box on the LAN)")
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

    if a.dashcam != "off":
        if a.out:
            a.dashcam_dir = os.path.join(os.path.dirname(a.out) or ".",
                                         os.path.splitext(
                                             os.path.basename(a.out))[0]
                                         + "-dashcam")
        else:
            a.dashcam_dir = os.path.join(
                "data", "v5-%s-%s-dashcam"
                % (a.mission, time.strftime("%Y-%m-%d")))
        os.makedirs(a.dashcam_dir, exist_ok=True)
        print("dashcam %s on: frames -> %s" % (a.dashcam, a.dashcam_dir),
              flush=True)
    else:
        a.dashcam_dir = None

    all_rows, all_outcomes = [], []
    for a.run in range(1, a.repeat + 1):
        rows, outcome = run_once(a, pol, fault_phases)
        all_rows.extend(rows)
        all_outcomes.append(outcome)

    if a.dashcam_dir:
        nf = dashcam_sheet(a.dashcam_dir, all_rows)
        print("dashcam sheet: %d frames -> %s/index.html"
              % (nf, a.dashcam_dir), flush=True)

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
        "world": "dist=%d%s%s%s" % (a.dist, ", no-autocollect" if a.no_autocollect else "",
                                    ", drop-after-harvest" if a.drop_after_harvest else "",
                                    ", drop-after-mine" if a.drop_after_mine else ""),
        "runs": a.repeat, "bot": a.bot, "steps_total": n,
        "mission_complete": [o["mission_complete"] for o in all_outcomes],
        "goal_steps": [o["goal_step"] for o in all_outcomes],
        "steps_runs": [o["steps_run"] for o in all_outcomes],
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
        "dashcam": a.dashcam + (" -> " + a.dashcam_dir
                                if a.dashcam_dir else ""),
        "dashcam_frames": sum(1 for r in all_rows if r.get("dashcam"))
                          + (2 * sum(1 for r in all_rows
                                     if r.get("dashcam_frozen") is not None)
                             if a.dashcam_dir else 0),
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
