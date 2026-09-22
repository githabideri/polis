#!/usr/bin/env python3
"""
Jev-loop v3: the noul VETO layer.

v1/v2 measured that Laya (421M) cannot SELECT between actions (0/8 in both
versions) but its confidence is honest (v2: 8/8 gated). v3 inverts the
architecture to match: the deterministic policy PROPOSES the action; Laya
answers one calibrated yes/no ("is this proposal consistent with the state?");
a confident "no" vetoes and escalates to the 27B (choice question).

  policy propose -> Laya noul veto -> (vetoed?) 27B choice -> execute

The run injects known-wrong proposals at chosen steps ("faults") so the
alarm is scored like an alarm: recall on the injected faults, precision on
the genuinely-correct proposals, plus escalation cost.

Question design follows the measured openjev rules (usage.md s3):
- noul = most reliable type; one operational sentence of instructions
- explicit default anchor: "no otherwise — <typical no case> is no"
- observable triggers only (phase/action consistency), no abstract judgment
- confidence < 0.5 = undetermined (honest hedge), not a vote

Usage:
  python3 scripts/jev-loop-v3.py [--bot 5] [--steps 8] [--faults 3,6]
      [--harness http://127.0.0.1:8585]
      [--openjev http://openjev-host:8781]
      [--llm http://llm-host:8080] [--llm-model qwen3.8-27b-dual]
      [--tau-yes 0.6] [--tau-no 0.4] [--out FILE.json]
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
    def wait_action(self, bot, name, prev_id, timeout=45):
        t0 = time.time()
        while time.time() - t0 < timeout:
            la = (self.state(bot).get("LastAction") or {})
            if la.get("Name") == name and la.get("Ok") is not None and (la.get("id") or 0) > prev_id:
                return la
            time.sleep(0.4)
        return (self.state(bot).get("LastAction") or {})

ACTIONS = ("goto_target", "mine_target", "goto_base", "wait")
# phase -> the action that SERVES it (the deterministic policy)
PHASE_ACTION = {"travel": "goto_target", "mine": "mine_target",
                "return": "goto_base", "done": "wait"}
# a deliberately wrong action per phase (the injected faults)
FAULT_ACTION = {"travel": "mine_target", "mine": "goto_base",
                "return": "mine_target", "done": "goto_target"}

def laya_noul(openjev, state_text, proposal):
    """The veto: yes only if the proposal is consistent with the phase."""
    t0 = time.time()
    r = http_json(openjev + "/v1/systemone", {
        "state": state_text,
        "questions": {
            "proposal_ok": {
                "type": "noul",
                "instructions": (
                    "Answer yes only if the proposed action matches the current phase: "
                    "travel phase needs goto_target, mine phase needs mine_target, "
                    "return phase needs goto_base, done phase needs wait, and the bot "
                    "carries the tool the phase needs (mining needs a pickaxe). "
                    "No otherwise - a proposed action that contradicts the phase, "
                    "skips an unfinished step, or uses a missing tool is no."
                ),
            },
        },
    }, timeout=60)
    a = ((r.get("answers") or {}).get("proposal_ok") or {})
    return {
        "p_yes": a.get("noul"),
        "confidence": a.get("confidence"),  # = max(p, 1-p) for noul; bands on p only
        "ms": int((time.time() - t0) * 1000),
        "error": r.get("_error"),
    }

def llm_choice(llm_url, model, state_text, proposal):
    """Escalation: the 27B picks the action (OpenAI-compatible chat)."""
    t0 = time.time()
    r = http_json(llm_url + "/v1/chat/completions", {
        "model": model,
        "temperature": 0,
        # Qwen3.8 is a thinking model: with thinking on, the one-word answer
        # costs ~6s and the budget occasionally truncates `content` to null.
        # Thinking off: ~124ms, straight answer. (Measured 2026-09-22.)
        "max_tokens": 128,
        "chat_template_kwargs": {"enable_thinking": False},
        "messages": [
            {"role": "system", "content":
                "You are the action-selecting fallback of a game-agent safety loop. "
                "Answer with exactly one of: goto_target, mine_target, goto_base, wait."},
            {"role": "user", "content":
                state_text + "\n\nThe policy proposed: " + proposal +
                " (the veto gate rejected it). Which single action should the bot take now?"},
        ],
    }, timeout=120)
    ms = int((time.time() - t0) * 1000)
    try:
        msg = r["choices"][0]["message"]
        text = msg.get("content") or msg.get("reasoning_content") or ""
    except Exception:
        return {"choice": None, "ms": ms, "error": str(r)[:120]}
    if not text:
        return {"choice": None, "ms": ms, "error": "empty completion (thinking ate the budget?)"}
    m = re.search(r"\b(" + "|".join(ACTIONS) + r")\b", text)
    return {"choice": m.group(1) if m else None, "ms": ms, "raw": text[:80],
            "error": None if m else "unparseable: " + text[:60]}

def execute(pol, bot, action, target, base, timeout=45):
    if action in ("goto_target", "goto_base"):
        t = target if action == "goto_target" else base
        r = pol.cmd("goto", [str(t[0]), str(t[1]), str(t[2]), "true", "0.02", "true"], bot)
        if not r.get("Ok") and r.get("arrived") is not True:
            return {"ok": False, "msg": r.get("Message") or r.get("error")}
        la = pol.wait_action(bot, "goto",
                             prev_id=((pol.state(bot).get("LastAction") or {}).get("id") or 0) - 1,
                             timeout=timeout)
        return {"ok": bool(la.get("Ok")), "msg": la.get("Msg")}
    if action == "mine_target":
        r = pol.cmd("mine", [str(target[0]), str(target[1]), str(target[2]), "true"], bot)
        if not r.get("Ok") and r.get("arrived") is not True and "mining" not in (r.get("Message") or ""):
            return {"ok": False, "msg": r.get("Message") or r.get("error")}
        la = pol.wait_action(bot, "mine",
                             prev_id=((pol.state(bot).get("LastAction") or {}).get("id") or 0) - 1,
                             timeout=timeout)
        return {"ok": bool(la.get("Ok")), "msg": la.get("Msg")}
    time.sleep(1.5)
    return {"ok": True, "msg": "wait"}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bot", type=int, default=5)
    ap.add_argument("--steps", type=int, default=8)
    ap.add_argument("--faults", default="3,6",
                    help="1-based steps at which to inject a known-wrong proposal")
    ap.add_argument("--harness", default="http://127.0.0.1:8585")
    ap.add_argument("--openjev", default=os.environ.get("OPENJEV", "http://openjev-host:8781"))
    ap.add_argument("--llm", default=os.environ.get("POLIS_LLM", "http://llm-host:8080"))
    ap.add_argument("--llm-model", default="qwen3.8-27b-dual")
    ap.add_argument("--tau-yes", type=float, default=0.6)
    ap.add_argument("--tau-no", type=float, default=0.4)
    ap.add_argument("--uid", default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    fault_steps = set(int(x) for x in a.faults.split(",") if x.strip())

    if a.uid is None:
        p = http_json(a.harness + "/polis/players")
        a.uid = ((p.get("Data") or p).get("players") or [{}])[0].get("uid")
    pol = Polis(a.harness, a.uid)

    st = pol.state(a.bot)
    if "Bot" not in st:
        print("bot %d not found: %s" % (a.bot, st)); sys.exit(1)
    bx, by, bz = [int(v) for v in st["Bot"]["Pos"]]
    base = (bx, by, bz)
    target = (bx + 8, by, bz)  # ground level: a floating target makes the pathfinder 'stuck'
    http_json(a.harness + "/polis/command",
              {"cmd": "setblock", "args": ["rock-granite"] + [str(v) for v in target],
               "context": {"botId": a.bot, "playerUid": a.uid}})
    http_json(a.harness + "/polis/command",
              {"cmd": "give", "args": ["pickaxe-iron", "1"],
               "context": {"botId": a.bot, "playerUid": a.uid}})
    print("setup: base=%s target=%s faults@%s" % (base, target, sorted(fault_steps)), flush=True)

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
        if injected:
            if phase == "mine":
                # tool fault: strip the pickaxe, then propose mining with it
                pol.cmd("drop", ["pickaxe-iron"], a.bot)
                time.sleep(0.5)
                proposal = "mine_target"
            elif phase == "travel":
                proposal = "goto_base"         # skip the whole goal
            elif phase == "return":
                proposal = "goto_target"       # back to the already-mined rock
            else:
                proposal = FAULT_ACTION[phase]
        repair_tool = False
        if injected and phase == "mine":
            inv = [b.get("Code") for b in (pol.state(a.bot).get("Bot", {}).get("Backpack") or [])]
            repair_tool = "pickaxe-iron" not in inv

        state_text = (
            "task: mine a rock, then return to base\n"
            "current phase: %s\n"
            "facts: bot at (%.0f, %d, %.0f), near_target=%s, near_base=%s, rock_mined=%s\n"
            "carrying: %s\nlast_action: %s\n"
            "proposed action: %s"
        ) % (
            phase, pos[0], pos[1], pos[2],
            "yes" if near_t else "no", "yes" if near_b else "no",
            "yes" if rock_mined else "no",
            ", ".join(b["Code"] for b in (st["Bot"].get("Backpack") or [])[:4]) or "empty",
            (st.get("LastAction") or {}).get("Msg") or "none",
            proposal,
        )

        veto = laya_noul(a.openjev, state_text, proposal)
        p, conf = veto["p_yes"], veto["confidence"]
        decision, final = "pass", proposal
        esc = None
        # noul: confidence is max(p,1-p) and adds no information beyond the
        # p bands, so gate on p alone (calibrated 2026-09-22, see report).
        if veto["error"]:
            decision = "error:" + str(veto["error"])[:40]
        elif p is not None and p <= a.tau_no:
            decision = "veto"
            esc = llm_choice(a.llm, a.llm_model, state_text, proposal)
            final = esc["choice"] or correct   # unparseable -> fall back to policy
        elif p is not None and p < a.tau_yes:
            decision = "borderline"            # between taus: execute, record
        if esc and not esc["error"] and not esc["choice"]:
            pass

        executed = final if final in ACTIONS else "wait"
        ex = execute(pol, a.bot, executed, target, base)
        if executed == "mine_target" and ex["ok"]:
            rock_mined = True
        if repair_tool and rock_mined is False:
            pol.cmd("give", ["pickaxe-iron", "1"], a.bot)
            time.sleep(0.5)
        match = executed == correct
        fault_caught = injected and decision == "veto"

        print("step %d: phase=%-6s proposal=%-11s injected=%s p_yes=%s conf=%s -> %s%s | exec=%s %s oracle=%s" % (
            i + 1, phase, proposal, str(injected).lower(),
            ("%.2f" % p) if p is not None else "?",
            ("%.2f" % conf) if conf is not None else "?",
            decision, (" (27b->%s)" % final) if esc else "",
            executed, "OK" if ex["ok"] else "FAIL", "MATCH" if match else "DIFF"), flush=True)
        rows.append({
            "step": i + 1, "phase": phase, "proposal": proposal, "injected": injected,
            "p_yes": p, "confidence": conf, "decision": decision,
            "escalated": bool(esc), "llm_choice": esc["choice"] if esc else None,
            "llm_ms": esc["ms"] if esc else None, "llm_raw": esc.get("raw") if esc else None,
            "executed": executed, "exec_ok": ex["ok"], "oracle": correct, "match": match,
            "fault_caught": fault_caught, "laya_ms": veto["ms"],
        })
        if rock_mined and near_b:
            print("goal complete at step %d" % (i + 1), flush=True)
            break

    n = len(rows)
    faults = [r for r in rows if r["injected"]]
    vetoes = [r for r in rows if r["decision"] == "veto"]
    false_alarms = [r for r in vetoes if not r["injected"]]
    caught = [r for r in vetoes if r["injected"]]
    summary = {
        "loop": "jev-loop-v3 (noul veto + 27b escalation)",
        "veto_model": "laya-rl-agent 421M (noul)",
        "escalation_model": a.llm_model,
        "bot": a.bot, "steps": n,
        "tau": [a.tau_no, a.tau_yes],
        "injected_faults": len(faults),
        "faults_caught": "%d/%d" % (len(caught), len(faults)),
        "false_alarms": "%d/%d (non-fault steps vetoed)" % (len(false_alarms), n - len(faults)),
        "vetoes_total": len(vetoes),
        "escalations": sum(1 for r in rows if r["escalated"]),
        "exec_oracle_match": "%d/%d" % (sum(1 for r in rows if r["match"]), n),
        "exec_success": "%d/%d" % (sum(1 for r in rows if r["exec_ok"]), n),
        "avg_laya_ms": int(sum(r["laya_ms"] for r in rows) / max(n, 1)),
        "avg_llm_ms": (int(sum(r["llm_ms"] for r in rows if r["llm_ms"]) /
                        max(1, sum(1 for r in rows if r["escalated"])))
                       if any(r["escalated"] for r in rows) else None),
        "total_sec": int(time.time() - t_start),
        "rows": rows,
    }
    print("\n=== JEVO LOOP v3 SUMMARY ===")
    print(json.dumps({k: v for k, v in summary.items() if k != "rows"}, indent=1))
    if a.out:
        json.dump(summary, open(a.out, "w"), indent=1)
        print("wrote", a.out)

if __name__ == "__main__":
    main()
