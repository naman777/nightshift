from __future__ import annotations

from agents.core.models import Category

from .base import Fault, config_commit


class LogFlood(Fault):
    def apply_sim(self, w, params, t_f):
        p = self.merged(params)
        svc = p["service"]
        c = config_commit(w, t_f - 20, svc, f"config/{svc}.yaml", "log_level", "info", "debug", p["message"], author="li")
        w.facts.update(sha=c.sha, log_service=svc)
        w.alert_name, w.alert_service = "DiskFillingFast", svc
        w.add_effect("log_lines_per_second", svc, t_f, "mult", 32, 30)
        w.add_effect("disk_used_ratio", svc, t_f, "add", 0.42, 300)
        w.add_effect("p99_latency_seconds", svc, t_f, "mult", 1.35, 60)
        w.add_effect("cpu_ratio", svc, t_f, "mult", 1.3, 60)
        w.add_log(svc, "debug", "cache lookup key=order:{i} hit=false layer=l2 ({ms}us)", t_f, every_s=1, ms_base=30)

    def live_steps(self, params):
        p = self.merged(params)
        return [{"do": "config", "service": p["service"], "key": "log_level", "value": "debug"}]


FAULT = LogFlood("log_flood", "DiskFillingFast", Category.LOG_FLOOD,
                 {"service": "orders-svc", "message": "orders: verbose logging for cache investigation"},
                 "Debug logging is enabled on a hot path.")
