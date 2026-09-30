# Superseded decision loops (v1–v4)

Frozen history of the Jev decision loop, kept for the measurement record
the reports in `docs/reports/` rely on:

- `jev-loop.py` — v1/v2: single small-model choice (goal-word bias, phase-split variants)
- `jev-loop-v3.py` — noul veto (Laya as conservative pre-filter) + 27B escalation
- `jev-loop-v4.py` — 27B per-step judge + Laya obvious-yes pre-filter

All superseded by `scripts/jev-loop-v5.py` (the live three-tier cascade:
Laya noul pre-veto → Decider-2B readout → 27B doubt-arbiter), which imports
the pure decision core from `r2/`. Read-only: do not modify or update
these files.
