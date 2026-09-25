from __future__ import annotations

from agents.core.models import Category

from .base import Fault, config_commit


class MemoryLeak(Fault):
    def apply_sim(self, w, params, t_f):
        p = self.merged(params)
        svc, flag = p["service"], p["flag"]
        c = config_commit(w, t_f - 20, svc, "config/flags.json", f'"{flag}"', "false", "true", p["message"], kind="flag")
        w.facts.update(sha=c.sha, flag=flag, flag_service=svc)
        w.alert_name, w.alert_service = "ServiceMemoryGrowth", svc
        w.add_effect("memory_bytes", svc, t_f, "mult", p["growth"], 480)
        w.add_effect("cpu_ratio", svc, t_f, "mult", 1.4, 480)
        w.add_effect("restarts_total", svc, w.t_alert - 90, "add", 1, 1)
        w.add_log(svc, "warn", "cache size={i}00000 entries (unbounded); evictions=0", t_f, every_s=20)
        w.add_log(svc, "error", "OOMKilled: container exceeded memory limit 1024MiB; restarting", w.t_alert - 90, w.t_alert - 89, every_s=10)

    def live_steps(self, params):
        p = self.merged(params)
        return [{"do": "flag", "flag": p["flag"], "value": "true"}]


FAULT = MemoryLeak("memory_leak", "ServiceMemoryGrowth", Category.RESOURCE_LEAK,
                   {"service": "orders-svc", "flag": "enable_unbounded_cache", "growth": 5.5, "message": "flags: enable order cache"},
                   "A feature flag enables an unbounded cache.")
