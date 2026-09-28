#!/usr/bin/env python3
"""
Phase 6 unit tests: the JobQueue (pure state machine).
Run:  python3 tests/reflex/jobqueue-test.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", ".."))

from r2.jobqueue import GoalState
from r2.jobs import Goal, Job, Failure

PASS = 0
FAIL = 0

def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("ok   %s" % name)
    else:
        FAIL += 1
        print("FAIL %s  %s" % (name, detail))


def mk(verbs=()):
    goal = Goal(verb="place", object="granite", at="site-A", n=1)
    jobs = []
    for i, (t, kw) in enumerate(verbs):
        jobs.append(Job("j%d" % (i + 1), t, **kw))
    return GoalState(goal, jobs, "test")


# lifecycle: plan -> run -> per-job -> goal_complete
gs = mk([("give_tool", {"material": "granite", "quantity": 1}),
         ("place", {"target": "site-A", "material": "granite",
                    "quantity": 1, "depends_on": ["j1"]})])
check("starts planned", gs.status == "planned")
j1 = gs.start()
check("first job running", j1.id == "j1" and gs.status == "running")
check("no next while running", gs.next_job() is j1)
j2 = None
gs.job_done(j1, "granite in hand (measured 1)")
check("job1 done, goal still running", gs.job_status["j1"] == "done"
      and gs.status == "running")
# next_job after done:
j2 = gs.next_job()
check("second job started", j2 is not None and j2.id == "j2")
gs.job_done(j2, "site filled")
check("goal complete", gs.status == "complete")
d = gs.to_dict()
check("run-JSON serializes", d["status"] == "complete"
      and d["failure"] is None and len(d["log"]) >= 4
      and d["log"][-1]["event"] == "goal_complete")

# failure path: job abandoned -> goal failed with the failure attached
gs = mk([("mine", {"source": "res-01", "material": "stone", "quantity": 1}),
         ("place", {"target": "site-A", "material": "granite",
                    "quantity": 1})])
gs.start()
f = Failure("job_budget_exhausted", "12 steps, marker still present",
            job_id="j1")
gs.job_failed(gs.jobs[0], f)
check("goal failed on job failure", gs.status == "failed"
      and gs.failure.code == "job_budget_exhausted"
      and gs.job_status["j1"] == "abandoned")

# rejection path: the plan never ran
gs = mk([("place", {"target": "site-A", "material": "granite"})])
gs.reject_plan(Failure("resource_not_found", "no granite in scope"))
check("plan rejection is terminal", gs.status == "rejected"
      and gs.failure.code == "resource_not_found")
try:
    gs.start()
    check("cannot start a rejected goal", False, "no exception")
except RuntimeError:
    check("cannot start a rejected goal", True)

# double-done is an error
gs = mk([("wait", {})])
gs.start()
gs.job_done(gs.jobs[0])
try:
    gs.next_job()          # none left -> None (no job running)
    check("no job left after all done", True)
except Exception as e:
    check("no job left after all done", False, repr(e))

# ledger: measured production replaces the plan's guess
gs = mk([("mine", {"source": "res-01", "material": "stone", "quantity": 3}),
         ("place", {"target": "site-A", "material": "granite",
                    "quantity": 1})])
gs.start()
gs.record_measured("stone", 2)     # measured: only 2 dropped, plan said 3
gs.consume("granite", 1)
check("ledger holds measured values",
      gs.ledger.get("stone") == 2 and gs.ledger.get("granite") == -1)

# goal grammar error surfaces through the queue's intake
try:
    Goal.from_dict({"verb": "fly", "object": "x"})
    check("bad goal never reaches the queue", False, "no exception")
except Exception:
    check("bad goal never reaches the queue", True)

print()
print("jobqueue-test: %d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
