#!/usr/bin/env python3
"""
Jev-loop v4 (optimization-harness form) — polis decision loop.

Two-tier decision:
  policy proposes an action for the current phase
    -> Laya 421M noul pre-filter (anchored yes/no, one call ~1.5-2.5 s)
         p >= TAU_YES  -> execute the proposal (cheap path)
         p <  TAU_YES  -> 27B doubt-arbiter (thinking off, ~0.2-0.7 s)
                          answers the same 4-action choice; execute its
                          answer (fallback: the proposal)

Mission (one pass): mine the marker block, return to base.
Success = marker block removed from the world (verified by scan) AND bot
back at base. (1.22 note: loot from plain/cracked rock set via setblock has
no block-entity type, so items do not drop - block removal is the
deterministic success criterion. See report 2026-09-22.)

Positive controls (fault injection): at chosen steps a KNOWN-WRONG proposal
is injected (skip-goal during travel; tool-drop + mine during mine) to see
whether the tiers catch it.

Every step is recorded as a LABELED example (state, proposal, oracle action,
reflex p, path, judge answer, executed, outcome) - the raw material for
re-deriving the threshold when the model or question changes (calibration
protocol, llmlab docs/decision-classifiers.md).

Usage:
  python3 scripts/jev-loop-v4.py [--bot 5] [--steps 8] [--faults travel,mine]
      [--repeat 1] [--tau-yes 0.6]
      [--harness http://127.0.0.1:8585] [--openjev the Laya noul endpoint]
      [--llm http://the 27B judge] [--llm-model qwen3.8-27b-dual]
      [--out FILE.json]
"""
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
    def backpack(self, bot):
        return [b.get("Code") for b in (self.state(bot).get("Bot", {}).get("Backpack") or [])]
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
    def marker_present(self, bot, cell):
        x, y, z = cell
        r = self.cmd("scan", [str(x - 1), "2", str(z - 1), str(x + 1), str(y + 2), str(z + 1)], bot)
        blocks = (r.get("Data") or {}).get("blocks", [])
        return any(b.get("code") in ("rock-granite", "game:rock-granite") and b.get("pos") == [x, y, z]
                   for b in blocks)

ACTIONS = ("goto_target", "mine_target", "goto_base", "wait")
PHASE_ACTION = {"travel": "goto_target", "mine": "mine_target",
                "return": "goto_base", "done": "wait"}

LAYA_QUESTION = {
    "type": "noul",
    "instructions": (
        "Answer yes only if the proposed action matches the current phase: "
        "travel phase needs goto_target, mine phase needs mine_target, "
        "return phase needs goto_base, done phase needs wait, and the bot "
        "carries the tool the phase needs (mining needs a pickaxe). "
        "No otherwise - a proposed action that contradicts the phase, "
        "skips an unfinished step, or uses a missing tool is no."),
}

def laya_noul(openjev, state_text, proposal):
    t0 = time.time()
    r = http_json(openjev + "/v1/systemone", {
        "state": state_text,
        "questions": {"proposal_ok": LAYA_QUESTION},
    }, timeout=60)
    a = ((r.get("answers") or {}).get("proposal_ok") or {})
    return {"p": a.get("noul"), "ms": int((time.time() - t0) * 1000), "error": r.get("_error")}

def llm_judge(llm_url, model, state_text, proposal):
    """27B doubt-arbiter. Thinking off (measured 2026-09-22): ~124 ms,
    direct single-word answer; thinking on: ~6.4 s and null content."""
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
                "goto_target, mine_target, goto_base, wait."},
            {"role": "user", "content":
                state_text + "\n\nPolicy proposal: " + proposal +
                " (the reflex was unsure). Which single action should the bot take now?" +
                "\n\nOperational rules: mining requires a pickaxe in the bot's "
                "hands/bag - if it is proposed to mine without a pickaxe, answer "
                "wait. If a previous mine failed but the bot now carries a "
                "pickaxe and the marker is still present, retry mine_target. "
                "Only answer wait when a required tool is missing or the facts "
                "are contradictory."},
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
    m = re.search(r"\b(" + "|".join(ACTIONS) + r")\b", text)
    return {"choice": m.group(1) if m else None, "ms": ms, "raw": text[:80],
            "error": None if m else "unparseable: " + text[:60]}

def adjacent_to(pol, bot, cell):
    x, y, z = cell
    try:
        pos = pol.state(bot)["Bot"]["Pos"]
    except Exception:
        return [x - 1, y, z]
    if pos[0] < x:
        return [x - 1, y, z]
    if pos[0] > x:
        return [x + 1, y, z]
    return [x, y, z - 1] if pos[2] < z else [x, y, z + 1]

def execute(pol, bot, action, target, base, timeout=45):
    if action in ("goto_target", "goto_base"):
        t = adjacent_to(pol, bot, target) if action == "goto_target" else base
        r = pol.cmd("goto", [str(t[0]), str(t[1]), str(t[2]), "true", "0.02", "true"], bot)
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
    if action == "mine_target":
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

def run_once(a, pol, fault_phases):
    # fresh respawn: deterministic start, clean inventory
    if a.bot != "auto":
        pol.cmd("despawn", [], int(a.bot))
        time.sleep(1)
    r = http_json(a.harness + "/polis/command",
                  {"cmd": "spawn", "args": [], "context": {"playerUid": a.uid}})
    new_id = (r.get("Data") or {}).get("id")
    if new_id:
        a.bot = int(new_id)
    pol = Polis(a.harness, a.uid)
    st = pol.state(a.bot)
    bx, by, bz = [int(v) for v in st["Bot"]["Pos"]]
    base = (bx, by, bz)
    target = (bx + 8, by, bz)
    http_json(a.harness + "/polis/command",
              {"cmd": "setblock", "args": ["rock-granite"] + [str(v) for v in target],
               "context": {"botId": a.bot, "playerUid": a.uid}})
    if not pol.marker_present(a.bot, target):
        pol.cmd("setblock", ["rock-granite", str(target[0]), str(target[1]), str(target[2])], a.bot)
        time.sleep(1)
    # verified tool (the bot's default right hand may be occupied by a
    # profession item; give until the pickaxe is in the backpack/hands)
    for _ in range(8):
        pol.cmd("give", ["pickaxe-iron", "1"], a.bot)
        if any("pickaxe" in (c or "") for c in pol.carrying(a.bot)):
            break
        time.sleep(1)
    print("setup: bot #%d base=%s target=%s faults=%s pickaxe=%s marker=%s" % (
        a.bot, base, target, sorted(fault_phases),
        any("pickaxe" in (c or "") for c in pol.carrying(a.bot)),
        pol.marker_present(a.bot, target)), flush=True)

    rows, t_start, fired = [], time.time(), set()
    for i in range(a.steps):
        st = pol.state(a.bot)
        pos = st["Bot"]["Pos"]
        near_t = dist(pos, target) <= 2.5
        near_b = dist(pos, base) <= 2.5
        marker = pol.marker_present(a.bot, target)
        rock_mined = not marker
        if not rock_mined:
            phase = "mine" if near_t else "travel"
        else:
            phase = "done" if near_b else "return"
        correct = PHASE_ACTION[phase]

        injected = phase in fault_phases and phase not in fired
        proposal = correct
        drop_done = False
        if injected and phase == "travel":
            proposal = "goto_base"
        elif injected and phase == "mine":
            pol.cmd("select", [str(a.bot)], a.bot)  # ensure held slot = pickaxe? (no-op if usage differs)
            pol.cmd("drop", [], a.bot)
            t0 = time.time()
            while time.time() - t0 < 10:
                if not any("pickaxe" in (c or "") for c in pol.carrying(a.bot)):
                    drop_done = True
                    break
                pol.cmd("drop", [], a.bot)
                time.sleep(1)
            proposal = "mine_target"
        state_text = (
            "task: mine the marker block, then return to base\n"
            "current phase: %s\n"
            "facts: bot at (%.0f, %d, %.0f), near_target=%s, near_base=%s, marker_present=%s\n"
            "carrying: %s\nlast_action: %s\nproposed action: %s"
        ) % (
            phase, pos[0], pos[1], pos[2],
            "yes" if near_t else "no", "yes" if near_b else "no",
            "yes" if marker else "no",
            ", ".join((b.get("Code") or "?") for b in (st["Bot"].get("Backpack") or [])[:4]) or "empty",
            (st.get("LastAction") or {}).get("Msg") or "none",
            proposal,
        )

        reflex = laya_noul(a.openjev, state_text, proposal)
        p = reflex["p"]
        path, judge, final = "reflex", None, proposal
        if reflex["error"]:
            path = "reflex-error:" + str(reflex["error"])[:30]
        elif p is not None and p >= a.tau_yes:
            pass
        else:
            path = "judge"
            judge = llm_judge(a.llm, a.llm_model, state_text, proposal)
            final = judge["choice"] or proposal
        final = final if final in ACTIONS else "wait"

        ex = execute(pol, a.bot, final, target, base)
        # repair the tool after a tool fault so the mission can continue
        if drop_done and not any("pickaxe" in (c or "") for c in pol.carrying(a.bot)):
            for _ in range(8):
                pol.cmd("give", ["pickaxe-iron", "1"], a.bot)
                if any("pickaxe" in (c or "") for c in pol.carrying(a.bot)):
                    break
                time.sleep(1)

        if injected:
            fired.add(phase)
        match = final == correct
        fault_corrected = injected and final != proposal
        print("run %d step %d: phase=%-6s prop=%-12s inj=%-5s p=%s path=%-9s judge=%-12s exec=%-12s %s oracle=%s" % (
            a.run, i + 1, phase, proposal, str(injected).lower(),
            ("%.2f" % p) if p is not None else "?", path,
            str(judge["choice"]) if judge else "-", final,
            "OK" if ex["ok"] else "FAIL", "MATCH" if match else "DIFF"), flush=True)
        rows.append({
            "step": i + 1, "phase": phase, "proposal": proposal, "injected": injected,
            "p": p, "path": path, "judge_choice": judge["choice"] if judge else None,
            "judge_raw": judge.get("raw") if judge else None,
            "judge_ms": judge["ms"] if judge else None,
            "executed": final, "exec_ok": ex["ok"], "exec_msg": ex["msg"],
            "oracle": correct, "match": match, "fault_corrected": fault_corrected,
            "state_text": state_text, "laya_ms": reflex["ms"],
        })

        st = pol.state(a.bot)
        if (not pol.marker_present(a.bot, target)) and dist(st["Bot"]["Pos"], base) <= 2.5:
            print("run %d: GOAL at step %d (%.0fs)" % (a.run, i + 1, time.time() - t_start), flush=True)
            break

    st = pol.state(a.bot)
    complete = (not pol.marker_present(a.bot, target)) and dist(st["Bot"]["Pos"], base) <= 2.5
    return rows, {
        "mission_complete": complete,
        "steps_to_complete": next((r["step"] for r in reversed(rows) if r["match"]), None)
        if complete else None,
        "total_sec": int(time.time() - t_start),
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bot", type=int, default=5)
    ap.add_argument("--steps", type=int, default=8)
    ap.add_argument("--faults", default="travel,mine",
                    help="phases whose FIRST step gets a known-wrong proposal")
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--tau-yes", type=float, default=0.6)
    ap.add_argument("--harness", default="http://127.0.0.1:8585")
    ap.add_argument("--openjev", default=os.environ.get("OPENJEV", "the Laya noul endpoint"))
    ap.add_argument("--llm", default=os.environ.get("POLIS_LLM", "http://the 27B judge"))
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
    judge_calls = [r for r in all_rows if r["path"] == "judge"]
    false_waits = [r for r in judge_calls
                   if not r["injected"] and r["judge_choice"] == "wait" and r["oracle"] != "wait"]
    summary = {
        "loop": "jev-loop-v4 harness (27B doubt-arbiter + Laya noul pre-filter)",
        "reflex": "laya 421M noul, tau_yes=%s" % a.tau_yes,
        "judge": a.llm_model + " (thinking off)",
        "runs": a.repeat, "bot": a.bot, "steps_total": n,
        "mission_complete": [o["mission_complete"] for o in all_outcomes],
        "mission_complete_rate": "%d/%d" % (sum(1 for o in all_outcomes if o["mission_complete"]), len(all_outcomes)),
        "avg_steps_to_complete": (sum(o["steps_to_complete"] or a.steps for o in all_outcomes
                                       if o["mission_complete"]) / max(sum(1 for o in all_outcomes if o["mission_complete"]), 1)),
        "injected_faults": len(faults),
        "faults_corrected": "%d/%d" % (sum(1 for r in faults if r["fault_corrected"]), len(faults)),
        "reflex_short_circuits": "%d/%d" % (n - len(judge_calls), n),
        "judge_calls": len(judge_calls),
        "false_waits": len(false_waits),
        "judge_oracle_match": "%d/%d" % (sum(1 for r in judge_calls if r["match"]), len(judge_calls)) if judge_calls else "0/0",
        "exec_oracle_match": "%d/%d" % (sum(1 for r in all_rows if r["match"]), n),
        "exec_success": "%d/%d" % (sum(1 for r in all_rows if r["exec_ok"]), n),
        "avg_laya_ms": int(sum(r["laya_ms"] for r in all_rows) / max(n, 1)),
        "avg_judge_ms": (int(sum(r["judge_ms"] for r in judge_calls) / len(judge_calls))
                         if judge_calls else None),
        "threshold_derivation": derive_threshold(all_rows),
        "laya_question": LAYA_QUESTION,
        "rows": all_rows,
    }
    print("\n=== JEVO LOOP v4 SUMMARY (harness) ===")
    print(json.dumps({k: v for k, v in summary.items() if k != "rows"}, indent=1))
    if a.out:
        json.dump(summary, open(a.out, "w"), indent=1)
        print("wrote", a.out)

if __name__ == "__main__":
    main()
