from __future__ import annotations

from agents.core.models import Category

from .base import Fault, config_commit


class SchedulerBacklog(Fault):
    def apply_sim(self, w, params, t_f):
        p = self.merged(params)
        c = config_commit(w, t_f - 20, "scheduler", "config/scheduler.yaml", "worker_count", p["old"], p["workers"],
                          p["message"], author="sam")
        w.facts.update(sha=c.sha, workers=p["workers"], old=p["old"])
        w.alert_name, w.alert_service = "JobQueueBacklog", "scheduler"
        w.add_effect("queue_depth", "scheduler", t_f, "mult", p["growth"], 240)
        w.add_effect("cpu_ratio", "scheduler", t_f, "mult", 0.3, 30)
        w.add_log("scheduler", "warn", "job queue depth={i}0 oldest_wait={ms}ms workers={workers}/{workers} busy", t_f, every_s=10, ms_base=90000)
        w.add_log("scheduler", "info", "config reloaded: worker_count={workers}", t_f, t_f + 1, every_s=5)

    def live_steps(self, params):
        p = self.merged(params)
        return [{"do": "config", "service": "scheduler", "key": "worker_count", "value": p["workers"]}]


FAULT = SchedulerBacklog("scheduler_backlog", "JobQueueBacklog", Category.CAPACITY,
                         {"workers": 1, "old": 8, "growth": 90, "message": "scheduler: reduce worker footprint"},
                         "Foreman worker count is cut and the job queue grows.")
