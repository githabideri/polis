#!/usr/bin/env python3
"""
Jev-loop v4: 27B per-step judge + Laya cheap pre-filter (2026-09-22).

v3 measured that at 421M scale the noul veto is a conservative safety net,
not a precision gate (fault and false alarm at the same p), while the 27B
with thinking disabled answers a one-word action choice in ~124 ms. v4
inverts the tiers:

  Laya noul pre-filter:
      p >= 0.6  -> execute the policy proposal directly (cheap path)
      p <  0.6  -> 27B judges the step (full state + proposal, thinking off)
                   execute the 27B's choice (fallback: the proposal)

Faults are injected at chosen steps (skip-goal, tool-drop) to measure
whether the judge corrects what the reflex lets through.

Also fixed vs v3: `drop` removes the HELD item (not the named one), so the
tool fault drops the held slot and verifies; the mine action is confirmed
by polling for the block's item in the backpack (mining is async, ~8s with
a pickaxe), not by the "mining started" ack.

Usage:
  python3 scripts/jev-loop-v4.py [--bot 5] [--steps 8] [--faults 3,6]
      [--harness http://127.0.0.1:8585] [--openjev the Laya noul endpoint]
      [--llm http://the 27B judge] [--llm-model qwen3.8-27b-dual]
      [--tau-yes 0.6] [--out FILE.json]
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
    def cmd(self, cmd, args, bot, timeout=40):
        return http_json(self.base + "/polis/command",
                         {"cmd": cmd, "args": args,
                          "context": {"botId": bot, "playerUid": self.uid}}, timeout)
    def state(self, bot):
        return self.get("/polis/state?botId=%d" % bot)
    def backpack(self, bot):
        return [b.get("Code") for b in (self.state(bot).get("Bot", {}).get("Backpack") or [])]
    def wait_action(self, bot, name, prev_id, timeout=45):
        t0 = time.time()
        while time.time() - t0 < timeout:
            la = (self.state(bot).get("LastAction") or {})
            if la.get("Name") == name and la.get("Ok") is not None and (la.get("id") or 0) > prev_id:
                return la
            time.sleep(0.4)
        return (self.state(bot).get("LastAction") or {})

ACTIONS = ("goto_target", "mine_target", "goto_base", "wait")
PHASE_ACTION = {"travel": "goto_target", "mine": "mine_target",
                "return": "goto_base", "done": "wait"}

def laya_noul(openjev, state_text, proposal):
    t0 = time.time()
    r = http_json(openjev + "/v1/systemone", {
        "state": state_text,
        "questions": {"proposal_ok": {"type": "noul",
            "instructions": (
                "Answer yes only if the proposed action matches the current phase: "
                "travel phase needs goto_target, mine phase needs mine_target, "
                "return phase needs goto_base, done phase needs wait, and the bot "
                "carries the tool the phase needs (mining needs a pickaxe). "
                "No otherwise - a proposed action that contradicts the phase, "
                "skips an unfinished step, or uses a missing tool is no.")}},
    }, timeout=60)
    a = ((r.get("answers") or {}).get("proposal_ok") or {})
    return {"p": a.get("noul"), "ms": int((time.time() - t0) * 1000), "error": r.get("_error")}

def llm_judge(llm_url, model, state_text, proposal):
    """The 27B judge. Thinking off (measured 2026-09-22): ~124ms, direct answer;
    thinking on: ~6.4s and `content` occasionally truncates to null."""
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
                " (the reflex was unsure). Which single action should the bot take now?"},
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

def rock_present(pol, bot, cell, tries=3):
    """Scan the cell's column for the marker rock; re-place up to `tries`x."""
    x, y, z = cell
    for i in range(tries):
        r = pol.cmd("scan", [str(x - 1), "2", str(z - 1), str(x + 1), str(y + 2), str(z + 1)], bot)
        blocks = (r.get("Data") or {}).get("blocks", [])
        if any(b.get("code") in ("rock-granite", "game:rock-granite") and b.get("pos") == [x, y, z] for b in blocks):
            return True
        pol.cmd("setblock", ["rock-granite", str(x), str(y), str(z)], bot)
        time.sleep(1)
    return False


def adjacent_to(pol, bot, cell):
    """Goto stops one cell short of the block (never into the block cell)."""
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


def execute(pol, bot, action, target, base, rock_mined, timeout=45):
    if action in ("goto_target", "goto_base"):
        t = adjacent_to(pol, bot, target) if action == "goto_target" else base
        r = pol.cmd("goto", [str(t[0]), str(t[1]), str(t[2]), "true", "0.02", "true"], bot)
        if not r.get("Ok") and r.get("arrived") is not True:
            return {"ok": False, "msg": r.get("Message") or r.get("error")}
        la = pol.wait_action(bot, "goto",
                             prev_id=((pol.state(bot).get("LastAction") or {}).get("id") or 0) - 1,
                             timeout=timeout)
        return {"ok": bool(la.get("Ok")), "msg": la.get("Msg") or ""}
    if action == "mine_target":
        if not rock_present(pol, bot, target, tries=1):
            return {"ok": False, "msg": "marker rock missing and re-place failed"}
        r = pol.cmd("mine", [str(target[0]), str(target[1]), str(target[2]), "true"], bot)
        if not r.get("Ok") and "mining" not in (r.get("Message") or ""):
            return {"ok": False, "msg": r.get("Message") or r.get("error")}
        # mining is async (~8s with pickaxe): confirm by the item appearing
        # in the backpack, not by the "mining started" ack.
        t0 = time.time()
        while time.time() - t0 < timeout:
            if "rock-granite" in [c or "" for c in pol.backpack(bot)]:
                return {"ok": True, "msg": "mined (item collected)"}
            time.sleep(1)
        return {"ok": False, "msg": "mining did not complete in %ds" % timeout}
    time.sleep(1.5)
    return {"ok": True, "msg": "wait"}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bot", type=int, default=5)
    ap.add_argument("--steps", type=int, default=8)
    ap.add_argument("--faults", default="3,6",
                    help="1-based steps at which to inject a known-wrong proposal")
    ap.add_argument("--harness", default="http://127.0.0.1:8585")
    ap.add_argument("--openjev", default=os.environ.get("OPENJEV", "the Laya noul endpoint"))
    ap.add_argument("--llm", default=os.environ.get("POLIS_LLM", "http://the 27B judge"))
    ap.add_argument("--llm-model", default="qwen3.8-27b-dual")
    ap.add_argument("--tau-yes", type=float, default=0.6)
    ap.add_argument("--uid", default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    fault_steps = set(int(x) for x in a.faults.split(",") if x.strip())

    if a.uid is None:
        p = http_json(a.harness + "/polis/players")
        a.uid = ((p.get("Data") or p).get("players") or [{}])[0].get("uid")
    pol = Polis(a.harness, a.uid)

    # fresh respawn: deterministic start, clean inventory (v3 left bot 5 with
    # a wedged 2-slot inventory that rejected give)
    if a.bot != "auto":
        pol.cmd("despawn", [], int(a.bot))
        time.sleep(1)
        a.bot = int(a.bot)
    r = http_json(a.harness + "/polis/command",
                  {"cmd": "spawn", "args": [], "context": {"playerUid": a.uid}})
    new_id = (r.get("Data") or {}).get("id")
    if new_id:
        a.bot = int(new_id)
    pol = Polis(a.harness, a.uid)
    st = pol.state(a.bot)
    if "Bot" not in st:
        print("bot %s not found after spawn: %s" % (a.bot, st)); sys.exit(1)
    bx, by, bz = [int(v) for v in st["Bot"]["Pos"]]
    print("using fresh bot #%d at (%d, %d, %d)" % (a.bot, bx, by, bz), flush=True)
    base = (bx, by, bz)
    target = (bx + 8, by, bz)  # ground level (a floating target stalls the pathfinder)
    http_json(a.harness + "/polis/command",
              {"cmd": "setblock", "args": ["rock-granite"] + [str(v) for v in target],
               "context": {"botId": a.bot, "playerUid": a.uid}})
    ok = rock_present(pol, a.bot, target)
    print("marker rock verified at", target, "->", ok, flush=True)
    if not ok:
        print("WARNING: marker rock will not persist in this world state; "
              "the loop will re-verify before every mine step", flush=True)
    # give + VERIFY the pickaxe (v3 lesson: unverified tool state made faults
    # ambiguous)
    pol.cmd("give", ["pickaxe-iron", "1"], a.bot)
    t0 = time.time()
    while time.time() - t0 < 8 and "pickaxe-iron" not in [c or "" for c in pol.backpack(a.bot)]:
        pol.cmd("give", ["pickaxe-iron", "1"], a.bot)
        time.sleep(1)
    print("setup: base=%s target=%s faults=%s pickaxe=%s" % (
        base, target, sorted(fault_steps),
        "pickaxe-iron" in [c or "" for c in pol.backpack(a.bot)]), flush=True)

    rock_mined = False
    rows, t_start = [], time.time()
    for i in range(a.steps):
        st = pol.state(a.bot)
        pos = st["Bot"]["Pos"]
        near_t = dist(pos, target) <= 2.5
        near_b = dist(pos, base) <= 2.5
        if not rock_mined and not near_t:
            phase = "travel"
        elif not rock_mined and near_t:
            phase = "mine"
        elif rock_mined and not near_b:
            phase = "return"
        else:
            phase = "done"
        correct = PHASE_ACTION[phase]

        injected = (i + 1) in fault_steps and phase != "done"
        proposal = correct
        drop_done = False
        if injected and phase == "travel":
            proposal = "goto_base"                       # skip the goal
        elif injected and phase == "mine":
            # tool fault: `drop` removes the HELD item - select the pickaxe
            # first, then drop, then verify it is actually gone.
            pol.cmd("select", ["pickaxe-iron"], a.bot)
            time.sleep(0.5)
            pol.cmd("drop", [], a.bot)
            t0 = time.time()
            while time.time() - t0 < 8:
                if "pickaxe-iron" not in [c or "" for c in pol.backpack(a.bot)]:
                    drop_done = True
                    break
                pol.cmd("drop", [], a.bot)
                time.sleep(1)
            proposal = "mine_target"
        state_text = (
            "task: mine a rock, then return to base\n"
            "current phase: %s\n"
            "facts: bot at (%.0f, %d, %.0f), near_target=%s, near_base=%s, rock_mined=%s\n"
            "carrying: %s\nlast_action: %s\nproposed action: %s"
        ) % (
            phase, pos[0], pos[1], pos[2],
            "yes" if near_t else "no", "yes" if near_b else "no",
            "yes" if rock_mined else "no",
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
            pass  # cheap path
        else:
            path = "judge"
            judge = llm_judge(a.llm, a.llm_model, state_text, proposal)
            final = judge["choice"] or proposal
        final = final if final in ACTIONS else "wait"

        ex = execute(pol, a.bot, final, target, base, rock_mined)
        if final == "mine_target" and ex["ok"]:
            rock_mined = True
        # repair the tool after a tool fault so the mission can continue
        if drop_done and "pickaxe-iron" not in [c or "" for c in pol.backpack(a.bot)]:
            pol.cmd("give", ["pickaxe-iron", "1"], a.bot)
            t0 = time.time()
            while time.time() - t0 < 8 and "pickaxe-iron" not in [c or "" for c in pol.backpack(a.bot)]:
                time.sleep(1)

        match = final == correct
        fault_corrected = injected and final != proposal
        print("step %d: phase=%-6s prop=%-12s inj=%-5s p=%s path=%-9s judge=%-12s exec=%-12s %s oracle=%s" % (
            i + 1, phase, proposal, str(injected).lower(),
            ("%.2f" % p) if p is not None else "?", path,
            str(judge["choice"]) if judge else "-", final,
            "OK" if ex["ok"] else "FAIL", "MATCH" if match else "DIFF"), flush=True)
        print("    exec=%s %s | judge raw: %s" % (ex["ok"], (ex["msg"] or "")[:50],
                                                   (judge or {}).get("raw") or (judge or {}).get("error") or "-"), flush=True)
        rows.append({
            "step": i + 1, "phase": phase, "proposal": proposal, "injected": injected,
            "p": p, "path": path, "judge_choice": judge["choice"] if judge else None,
            "judge_raw": judge.get("raw") if judge else None,
            "judge_ms": judge["ms"] if judge else None,
            "executed": final, "exec_ok": ex["ok"], "exec_msg": ex["msg"],
            "oracle": correct, "match": match, "fault_corrected": fault_corrected,
            "laya_ms": reflex["ms"],
        })
        if rock_mined and near_b:
            print("goal complete at step %d" % (i + 1), flush=True)
            break

    n = len(rows)
    faults = [r for r in rows if r["injected"]]
    judge_calls = [r for r in rows if r["path"] == "judge"]
    false_waits = [r for r in judge_calls
                  if not r["injected"] and r["judge_choice"] == "wait" and r["oracle"] != "wait"]
    summary = {
        "loop": "jev-loop-v4 (27b per-step judge + laya pre-filter)",
        "reflex": "laya-rl-agent 421M (noul pre-filter, tau_yes=%s)" % a.tau_yes,
        "judge": a.llm_model + " (thinking off)",
        "bot": a.bot, "steps": n,
        "injected_faults": len(faults),
        "faults_corrected": "%d/%d" % (sum(1 for r in faults if r["fault_corrected"]), len(faults)),
        "reflex_short_circuits": "%d/%d (p>=tau, no 27b call)" % (n - len(judge_calls), n),
        "judge_calls": len(judge_calls),
        "false_waits": len(false_waits),
        "judge_oracle_match": "%d/%d (of judge calls)" % (
            sum(1 for r in judge_calls if r["match"]), len(judge_calls)),
        "exec_oracle_match": "%d/%d" % (sum(1 for r in rows if r["match"]), n),
        "exec_success": "%d/%d" % (sum(1 for r in rows if r["exec_ok"]), n),
        "mission_complete": rock_mined,
        "avg_laya_ms": int(sum(r["laya_ms"] for r in rows) / max(n, 1)),
        "avg_judge_ms": (int(sum(r["judge_ms"] for r in judge_calls) / len(judge_calls))
                         if judge_calls else None),
        "total_sec": int(time.time() - t_start),
        "rows": rows,
    }
    print("\n=== JEVO LOOP v4 SUMMARY ===")
    print(json.dumps({k: v for k, v in summary.items() if k != "rows"}, indent=1))
    if a.out:
        json.dump(summary, open(a.out, "w"), indent=1)
        print("wrote", a.out)

if __name__ == "__main__":
    main()
