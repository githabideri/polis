"""R2 projection: the frozen 8-line reflex prompt (T1).

Extracted verbatim from scripts/jev-loop-v5.py (Phase 1-A, 2026-09-28).
The fine-tuned 2B decider was trained on EXACTLY this representation -
a wording change is a model regression, not a refactor (gate T1).
"""


def build_state_text(task, phase, pos, near_t, near_b, fixture_label, fixture,
                     carrying, items_line, since, last_action_msg, proposal):
    """The reflex prompt - the 8-line format the 2B decider was fine-tuned on.

    PHASE 0 CONTRACT (docs/design/job-system-r2.md, §5.4):
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

