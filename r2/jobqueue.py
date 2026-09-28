"""
R2 JobQueue - the authoritative owner of goals, jobs and their status
(design doc section 5.1 ownership table, section 6 queue semantics).

Pure logic: no I/O, no network. The live orchestrator
(scripts/r2-live-mission.py) feeds it plans from the validator and
oracle results from the executor; it decides what happens next.

R2 execution is strictly sequential (one bot, one live job at a time -
section 5.1: no separate reservation service; the claim index is the
whole reservation system). The depends_on field stays validated for the
DAG phase but imposes nothing at execution time in R2.
"""

from .jobs import Job, Failure


class GoalState:
    """A goal plus its plan and the per-job status of its execution."""

    def __init__(self, goal, jobs, plan_source):
        self.goal = goal                 # r2.jobs.Goal
        self.jobs = list(jobs)           # ordered plan (validated)
        self.plan_source = plan_source   # "planner:<model>" | "hand"
        self.status = "planned"          # planned | running | complete
                                         # | failed | rejected
        self.failure = None              # Failure (when failed/rejected)
        self.job_status = {j.id: j.status for j in self.jobs}
        self.job_log = []                # (job_id, event, detail) - run JSON
        self.ledger = {}                 # material -> qty (measured after
                                         # each producing job)

    # ------------------------------------------------------------ events ----

    def log(self, job_id, event, detail):
        self.job_log.append((job_id, event, detail))

    def start(self):
        if self.status != "planned":
            raise RuntimeError("goal already %s" % self.status)
        self.status = "running"
        self.log(None, "goal_start", self.goal.describe())
        return self.next_job()

    def next_job(self):
        """The next not-yet-terminal job in list order (R2: sequential)."""
        for j in self.jobs:
            if self.job_status[j.id] not in ("done", "abandoned"):
                self.job_status[j.id] = "running"
                self.log(j.id, "job_start", j.type)
                return j
        return None

    def job_done(self, job, oracle_detail=""):
        if self.job_status[job.id] != "running":
            raise RuntimeError("job %s not running" % job.id)
        self.job_status[job.id] = "done"
        self.log(job.id, "job_done", oracle_detail)
        if all(s in ("done", "abandoned")
               for s in self.job_status.values()):
            if all(s == "done" for s in self.job_status.values()):
                self.status = "complete"
                self.log(None, "goal_complete", self.goal.describe())
            else:
                self.status = "failed"
                self.failure = Failure(
                    "fixture_failed",
                    "a job was abandoned before goal completion",
                    goal=self.goal.describe())
        return self.status

    def job_failed(self, job, failure):
        if self.job_status[job.id] != "running":
            raise RuntimeError("job %s not running" % job.id)
        self.job_status[job.id] = "abandoned"
        self.log(job.id, "job_abandoned",
                 "%s: %s" % (failure.code, failure.detail))
        self.failure = failure
        self.status = "failed"
        self.log(None, "goal_failed", failure.code)
        return self.status

    def reject_plan(self, failure):
        """The plan never ran (validator/intake rejection)."""
        if self.status != "planned":
            raise RuntimeError("goal already %s" % self.status)
        self.status = "rejected"
        self.failure = failure
        self.log(None, "plan_rejected", "%s: %s"
                 % (failure.code, failure.detail))

    # -------------------------------------------------------- ledger (12.1) ----

    def record_measured(self, material, qty):
        """The post-execution ledger correction: the MEASURED outcome
        replaces the plan's budgeting guess (12.1: planned quantities are
        only a budgeting input)."""
        self.ledger[material] = self.ledger.get(material, 0) + qty

    def consume(self, material, qty):
        """Book a consumption (the place job's effect)."""
        self.ledger[material] = self.ledger.get(material, 0) - qty

    # ------------------------------------------------------- serialization ----

    def to_dict(self):
        """The run-JSON section for this goal (doc section 7)."""
        return {
            "goal": self.goal.to_dict(),
            "plan_source": self.plan_source,
            "status": self.status,
            "failure": self.failure.to_dict() if self.failure else None,
            "jobs": [
                {**j.to_dict(),
                 "status": self.job_status[j.id]}
                for j in self.jobs],
            "log": [{"job": a, "event": b, "detail": c}
                    for (a, b, c) in self.job_log],
            "ledger": self.ledger,
        }
