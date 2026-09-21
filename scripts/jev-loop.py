#!/usr/bin/env python3
"""
Jev-loop v1: Laya (openjev) as the decision layer for a polis bot.

Architecture:
  deterministic sensing (polis harness) -> short state text -> Laya choice
  question (confidence-gated) -> execute via harness -> measure vs oracle.

The loop does NOT let Laya do arithmetic: near_target/near_base flags and the
mined/completed booleans are computed here (harness data). Laya maps the
pre-digested situation to the next action.

Usage:  python3 scripts/jev-loop.py [--bot 5] [--steps 8] [--openjev http://127.0.0.1:8781 (or its LAN/TS address)]
"""
import os
import argparse, json, sys, time, urllib.request, urllib.error

def http_json(url, payload=None, timeout=30):
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
        self.base = base
        self.uid = uid
    def get(self, path, timeout=15):
        return http_json(self.base + path, None, timeout)
    def cmd(self, cmd, args, bot, timeout=20):
        return http_json(self.base + "/polis/command",
                         {"cmd": cmd, "args": args, "context": {"botId": bot, "playerUid": self.uid}},
                         timeout)
    def state(self, bot):
        return self.get("/polis/state?botId=%d" % bot)
    def wait_action(self, bot, name, prev_id, timeout=30):
        t0 = time.time()
        while time.time() - t0 < timeout:
            la = (self.state(bot).get("LastAction") or {})
            if la.get("Name") == name and la.get("Ok") is not None and (la.get("id") or 0) > prev_id:
                return la
            time.sleep(0.4)
        return (self.state(bot).get("LastAction") or {})

def jev_next_action(openjev, state_text):
    r = http_json(openjev + "/v1/systemone", {
        "state": state_text,
        "questions": {
            "next_action": {
                "type": "choice",
                "instructions": "Pick the single action that serves the current phase of the task.",
                "options": ["goto_target", "mine_target", "goto_base", "wait", "no match"],
            }
        }
    }, timeout=45)
    a = ((r.get("answers") or {}).get("next_action") or {})
    return {
        "choice": a.get("choice"),
        "confidence": a.get("confidence"),
        "probabilities": a.get("probabilities"),
        "ms": r.get("server_ms"),
        "tokens": (r.get("usage") or {}).get("input_tokens"),
        "error": r.get("_error"),
    }

def oracle(state):
    """Deterministic policy over the same pre-digested facts."""
    if not state["rock_mined"]:
        return "mine_target" if state["near_target"] else "goto_target"
    return "wait" if state["near_base"] else "goto_base"

def execute(pol, bot, action, target, base_pos, timeout=30):
    if action in ("goto_target", "goto_base"):
        t = target if action == "goto_target" else base_pos
        r = pol.cmd("goto", [str(t[0]), str(t[1]), str(t[2]), "true", "0.02", "true"], bot)
        if not r.get("Ok") and r.get("arrived") is not True:
            return {"ok": False, "msg": r.get("Message") or r.get("error")}
        la = pol.wait_action(bot, "goto", prev_id=((pol.state(bot).get("LastAction") or {}).get("id") or 0) - 1, timeout=timeout)
        return {"ok": bool(la.get("Ok")), "msg": la.get("Msg")}
    if action == "mine_target":
        r = pol.cmd("mine", [str(target[0]), str(target[1]), str(target[2]), "true"], bot)
        if not r.get("Ok") and r.get("arrived") is not True and "mining" not in (r.get("Message") or ""):
            return {"ok": False, "msg": r.get("Message") or r.get("error")}
        la = pol.wait_action(bot, "mine", prev_id=((pol.state(bot).get("LastAction") or {}).get("id") or 0) - 1, timeout=timeout)
        return {"ok": bool(la.get("Ok")), "msg": la.get("Msg")}
    time.sleep(1.5)  # wait
    return {"ok": True, "msg": "wait"}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bot", type=int, default=5)
    ap.add_argument("--steps", type=int, default=8)
    ap.add_argument("--harness", default="http://127.0.0.1:8585")
    ap.add_argument("--openjev", default=os.environ.get("OPENJEV", "http://127.0.0.1:8781"))
    ap.add_argument("--uid", default=None)
    a = ap.parse_args()

    if a.uid is None:
        p = http_json(a.harness + "/polis/players")
        a.uid = ((p.get("Data") or p).get("players") or [{}])[0].get("uid")
    pol = Polis(a.harness, a.uid)

    # --- setup: base = bot's current pos; target = 8 blocks east, rock on it
    st = pol.state(a.bot)
    if "Bot" not in st:
        print("bot %d not found: %s" % (a.bot, st)); sys.exit(1)
    bx, by, bz = [int(v) for v in st["Bot"]["Pos"]]
    base = (bx, by, bz)
    target = (bx + 8, by + 1, bz)
    http_json(a.harness + "/polis/command", {"cmd": "setblock", "args": ["rock-granite"] + [str(v) for v in target],
                                             "context": {"botId": a.bot, "playerUid": a.uid}})
    http_json(a.harness + "/polis/command", {"cmd": "give", "args": ["pickaxe-iron", "1"],
                                             "context": {"botId": a.bot, "playerUid": a.uid}})
    print("setup: base=%s target=%s" % (base, target))

    rock_mined = False
    rows = []
    t_start = time.time()
    for i in range(a.steps):
        st = pol.state(a.bot)
        pos = st["Bot"]["Pos"]
        near_t = dist(pos, target) <= 2.5
        near_b = dist(pos, base) <= 2.5
        state = {"near_target": near_t, "near_base": near_b, "rock_mined": rock_mined}

        # v2: compute the current phase deterministically; ask for the action
        # that SERVES the phase (kills the goal-word bias measured in v1).
        if not rock_mined and not near_t:
            phase = "travel"
        elif not rock_mined and near_t:
            phase = "mine"
        elif rock_mined and not near_b:
            phase = "return"
        else:
            phase = "done"
        state_text = (
            "task: mine a rock, then return to base\n"
            "current phase: %s\n"
            "facts: bot at (%.0f, %d, %.0f), near_target=%s, near_base=%s, rock_mined=%s\n"
            "phase meanings: travel=go to the rock, mine=mine it, return=go back to base, done=stay\n"
            "carrying: %s\nlast_action: %s"
        ) % (
            phase,
            pos[0], pos[1], pos[2],
            "yes" if near_t else "no", "yes" if near_b else "no",
            "yes" if rock_mined else "no",
            ", ".join(b["Code"] for b in (st["Bot"].get("Backpack") or [])[:4]) or "empty",
            (st.get("LastAction") or {}).get("Msg") or "none",
        )

        jev = jev_next_action(a.openjev, state_text)
        o = oracle(state)
        if jev["choice"] == "mine_target" and near_t and not rock_mined:
            pass  # mined flag flips when the action completes below
        match = jev["choice"] == o
        gated = (jev["confidence"] or 0) < 0.5

        exec_action = jev["choice"] if jev["choice"] in ("goto_target", "mine_target", "goto_base", "wait") else "wait"
        print("step %d: facts=%s phase=%s oracle=%-11s laya=%-11s conf=%.2f %s | exec=%s" % (
            i + 1, state, phase, o, str(jev["choice"]), jev["confidence"] or 0,
            "MATCH" if match else "DIFF", exec_action), flush=True)
        ex = execute(pol, a.bot, exec_action, target, base)
        if exec_action == "mine_target" and ex["ok"]:
            rock_mined = True

        rows.append({
            "step": i + 1,
            "state": state,
            "phase": phase,
            "oracle": o,
            "laya": jev["choice"],
            "confidence": jev["confidence"],
            "gated": gated,
            "match": match,
            "executed": exec_action,
            "exec_ok": ex["ok"],
            "exec_msg": ex["msg"],
            "laya_ms": jev["ms"],
            "tokens": jev["tokens"],
        })
        print("    exec=%s %s" % (ex["ok"], ex["msg"] or ""), flush=True)
        if rock_mined and near_b:
            print("goal complete at step", i + 1)
            break

    n = len(rows)
    matched = sum(1 for r in rows if r["match"])
    gated = sum(1 for r in rows if r["gated"])
    exec_ok = sum(1 for r in rows if r["exec_ok"])
    summary = {
        "loop": "jev-loop-v2",
        "model": "laya-rl-agent (421M, CPU)",
        "openjev": a.openjev,
        "bot": a.bot,
        "steps": n,
        "oracle_match": "%d/%d (%.0f%%)" % (matched, n, 100.0 * matched / max(n, 1)),
        "low_confidence_gates": gated,
        "exec_success": "%d/%d" % (exec_ok, n),
        "avg_laya_ms": int(sum(r["laya_ms"] or 0 for r in rows) / max(n, 1)),
        "total_sec": int(time.time() - t_start),
        "rows": rows,
    }
    print("\n=== JEVO LOOP v1 SUMMARY ===")
    print(json.dumps({k: v for k, v in summary.items() if k != "rows"}, indent=1))
    out = sys.argv and [x for x in sys.argv if x.startswith("--out=")]
    if out:
        path = out[0].split("=", 1)[1]
        json.dump(summary, open(path, "w"), indent=1)
        print("wrote", path)

if __name__ == "__main__":
    main()
