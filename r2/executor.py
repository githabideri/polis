"""R2 executor: the pure decision cascade (T2).

Extracted verbatim from scripts/jev-loop-v5.py (Phase 1-A, 2026-09-28).
needs_judge() + decide_cascade() are the loop's only stateful-looking
pieces and are pure in (tiers, proposal, options, last_final, tau*):
the live loop and the r2 executor must both call these exact functions
(gate T2 replays recorded live decisions through them).
"""
import math


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

