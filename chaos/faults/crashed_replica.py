from __future__ import annotations

from agents.core.models import Category

from .base import Fault, config_commit


class CrashedReplica(Fault):
    def apply_sim(self, w, params, t_f):
        p = self.merged(params)
        replica = p["replica"]
        c = config_commit(w, t_f - 3 * 3600, "lb", "config/lb.yaml", "health_check_interval_ms", 2000, p["interval"],
                          "lb: reduce health-check noise", author="li")
        w.facts.update(sha=c.sha, replica=replica, interval=p["interval"], hc_key="health_check_interval_ms")
        w.alert_name, w.alert_service = "HighErrorRate_orders", "orders-svc"
        w.add_effect("error_rate", "lb", t_f, "set", 0.46, 10)
        w.add_effect("request_rate", "orders-svc", t_f, "mult", 0.55, 10)
        w.add_effect("error_rate", "orders-svc", t_f, "mult", 1.1, 10)
        w.add_log("lb", "error", "connect() failed (111: Connection refused) while connecting to upstream {replica}:8080", t_f, every_s=2)
        w.add_log("lb", "warn", "upstream {replica} marked healthy (last check {interval}ms ago)", t_f, every_s=30)
        w.add_log("orders-svc", "warn", "received SIGKILL; {replica} exited", t_f, t_f + 1, every_s=5)

    def live_steps(self, params):
        p = self.merged(params)
        return [{"do": "kill", "container": p["replica"]}]


FAULT = CrashedReplica("crashed_replica", "HighErrorRate_orders", Category.HEALTHCHECK_MISCONFIG,
                       {"replica": "orders-svc-2", "interval": 600000},
                       "One orders replica dies; the LB health check is too lax to notice.")
