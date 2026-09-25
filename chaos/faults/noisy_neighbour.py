from __future__ import annotations

from agents.core.models import Category

from .base import Fault, config_commit


class NoisyNeighbour(Fault):
    def apply_sim(self, w, params, t_f):
        p = self.merged(params)
        c = config_commit(w, t_f - 20, "scheduler", "config/scheduler.yaml", "settlement_schedule", p["old"], p["schedule"],
                          p["message"], author="dana")
        w.facts.update(sha=c.sha, schedule=p["schedule"], job="settlement")
        w.alert_name, w.alert_service = "HighLatency_orders", "orders-svc"
        w.add_effect("cpu_ratio", "scheduler", t_f, "set", 0.92, 20)
        w.add_effect("cpu_ratio", "orders-svc", t_f, "mult", 2.4, 30)
        w.add_effect("p99_latency_seconds", "orders-svc", t_f, "mult", 4.5, 30)
        w.add_effect("error_rate", "orders-svc", t_f + 30, "mult", 3, 60)
        w.add_log("scheduler", "info", "job settlement batch={i} started (cpu-bound, schedule={schedule})", t_f, every_s=20)
        w.add_log("orders-svc", "warn", "slow request: /orders took {ms}ms (cpu throttled)", t_f, every_s=4, ms_base=900)

    def live_steps(self, params):
        p = self.merged(params)
        return [{"do": "config", "service": "scheduler", "key": "settlement_schedule", "value": p["schedule"]}]


FAULT = NoisyNeighbour("noisy_neighbour", "HighLatency_orders", Category.RESOURCE_CONTENTION,
                       {"old": "0 3 * * *", "schedule": "*/10 * * * *", "message": "scheduler: run settlement more often"},
                       "The settlement job is scheduled during peak and burns CPU shared with orders.")
