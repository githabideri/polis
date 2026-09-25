#!/usr/bin/env python3
"""tau-rederive.py -- re-derive the v5 cascade thresholds from dual-p rows.

Input: dualp JSONL from dualp-runner.py (one {correct, laya:{p},
decider:{p}, ...} per row). Gates (v5 semantics):

  tau_yes   : Laya p.  p < tau_yes -> judge (always).
  tau_strong: Laya p, among rows with Laya p >= tau_yes AND decider p >=
              tau_dec.  p < tau_strong -> judge (doubt); else short-circuit.
  tau_dec   : Decider p, among rows with Laya p >= tau_yes.
              p < tau_dec -> judge (disagreement).

For each gate: Youden threshold (max TPR - FPR over a fine grid between
the correct and faulty distributions), the margins (min-correct - tau,
tau - max-faulty), and a Wilson rule-of-three upper bound on the faulty
pass-through rate at the current production defaults. Advisory output:
the corpus is small and the fault mix is live-observed (goto_base
skip-goal, give_tool-while-carrying).
"""
import json
import math
import sys

Z95 = 1.959964


def wilson_upper(k, n, z=Z95):
    """Upper 95% Wilson bound on a proportion with k events in n trials
    (0/0 -> rule of three)."""
    if n == 0:
        return float("nan")
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    w = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (c + w) / d


def youden(correct, faulty):
    if not correct or not faulty:
        return None, -1.0
    mn = min(min(correct), min(faulty))
    mx = max(max(correct), max(faulty))
    best, bestt = -1.0, None
    for i in range(401):
        t = mn + (mx - mn) * i / 400
        tp = sum(1 for x in correct if x >= t) / len(correct)
        fp = sum(1 for x in faulty if x >= t) / len(faulty)
        if tp - fp > best:
            best, bestt = tp - fp, t
    return bestt, best


def report(name, correct, faulty, cur_tau):
    print("\n== %s ==" % name)
    print("  n: correct %d, faulty %d" % (len(correct), len(faulty)))
    if not correct or not faulty:
        print("  n/a")
        return None
    print("  correct  p: min %.4f  med %.4f  max %.4f" %
          (min(correct), sorted(correct)[len(correct) // 2], max(correct)))
    print("  faulty   p: min %.4f  med %.4f  max %.4f" %
          (min(faulty), sorted(faulty)[len(faulty) // 2], max(faulty)))
    t, j = youden(correct, faulty)
    passed_f = sum(1 for x in faulty if x >= t)
    passed_c = sum(1 for x in correct if x >= t)
    ub = wilson_upper(passed_f, len(faulty))
    print("  Youden tau: %.4f (J=%.3f)  [current default %.3f]" %
          (t, j, cur_tau))
    print("  margins: min-correct-tau = %+.4f | tau-max-faulty = %+.4f" %
          (min(correct) - t, t - max(faulty)))
    print("  at that tau: faulty pass %d/%d (Wilson UB %.1f%%), correct pass %d/%d" %
          (passed_f, len(faulty), ub * 100, passed_c, len(correct)))
    return t


def main():
    rows = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
    rows = [r for r in rows if r.get("n_ok")]
    print("rows with both readouts: %d (correct %d, faulty %d)" %
          (len(rows),
           sum(1 for r in rows if r["correct"]),
           sum(1 for r in rows if not r["correct"])))

    laya_c = [r["laya"]["p"] for r in rows if r["correct"]]
    laya_f = [r["laya"]["p"] for r in rows if not r["correct"]]

    # current production defaults
    TY, TD, TS = 0.35, 0.50, 0.40

    print("\n--- gate simulation at current defaults (TY=%.2f TD=%.2f TS=%.2f) ---" % (TY, TD, TS))
    sc = [r for r in rows if r["laya"]["p"] >= TY
          and (r["decider"]["p"] or 0) >= TD
          and r["laya"]["p"] >= TS]
    sc_f = [r for r in sc if not r["correct"]]
    print("  short-circuits %d/%d; faulty short-circuits %d (Wilson UB %.1f%%)" %
          (len(sc), len(rows), len(sc_f), wilson_upper(len(sc_f), max(1, len(rows))) * 100))
    esc = [r for r in rows if not (r["laya"]["p"] >= TY
                                   and (r["decider"]["p"] or 0) >= TD
                                   and r["laya"]["p"] >= TS)]
    print("  escalations to judge: %d/%d" % (len(esc), len(rows)))

    t_yes = report("tau_yes (Laya p, all rows)", laya_c, laya_f, TY)

    # decider gate, among Laya-passing rows (use current TY for the stratum,
    # and the candidate if one was found)
    # decider gate, among Laya-passing rows (current TY; the Laya gate on
    # this corpus is the weak link, so a candidate TY doesn't add info)
    tp = [r for r in rows if r["laya"]["p"] >= TY]
    dec_c = [r["decider"]["p"] for r in tp if r["correct"]]
    dec_f = [r["decider"]["p"] for r in tp if not r["correct"]]
    report("tau_dec (Decider p, among Laya >= TY %.2f: n=%d/%d)" % (TY, len(dec_c), len(dec_f)),
           dec_c, dec_f, TD)

    # strong gate: the decider is consulted when Laya >= tau_yes; it then
    # splits short-circuit vs judge on (decider >= tau_dec AND Laya >=
    # tau_strong). Re-derive tau_strong = Youden on Laya p among rows where
    # the decider was called AND agreed (decider >= tau_dec).
    tp = [r for r in rows if r["laya"]["p"] >= TY
          and (r["decider"]["p"] or 0) >= TD]
    st_c = [r["laya"]["p"] for r in tp if r["correct"]]
    st_f = [r["laya"]["p"] for r in tp if not r["correct"]]
    report("tau_strong (Laya p, among Laya >= TY & decider >= TD: n=%d/%d)" % (len(st_c), len(st_f)),
           st_c, st_f, TS)

    # which faulty rows short-circuit at the current defaults, by fault type
    sc_f_rows = [r for r in rows if not r["correct"] and r["laya"]["p"] >= TY
                 and (r["decider"]["p"] or 0) >= TD and r["laya"]["p"] >= TS]
    from collections import Counter
    print("\n--- faulty short-circuits at current defaults: %d ---" % len(sc_f_rows))
    for prop, n in Counter(r["proposed"] for r in sc_f_rows).items():
        ps = sorted(r["laya"]["p"] for r in sc_f_rows if r["proposed"] == prop)
        print("  %-12s %d  (laya p: %.3f .. %.3f)" %
              (prop, n, ps[0], ps[-1]))
    sc_c_rows = [r for r in rows if r["correct"] and r["laya"]["p"] >= TY
                 and (r["decider"]["p"] or 0) >= TD and r["laya"]["p"] >= TS]
    print("  correct short-circuits: %d/%d correct rows" % (len(sc_c_rows), len([r for r in rows if r['correct']])))


if __name__ == "__main__":
    main()
