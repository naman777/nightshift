from __future__ import annotations

from agents.core.models import Category

from .base import Fault


class SlowDependency(Fault):
    def apply_sim(self, w, params, t_f):
        p = self.merged(params)
        lat = p["latency_ms"] / 1000
        w.facts.update(latency_ms=p["latency_ms"], dep=p["dependency"])
        w.alert_name, w.alert_service = "HighLatency_orders", "orders-svc"
        w.add_effect("dependency_latency_p99_seconds", "orders-svc", t_f, "set", lat + 0.09, 15)
        w.add_effect("p99_latency_seconds", "orders-svc", t_f, "set", lat + 0.3, 15)
        w.add_effect("error_rate", "orders-svc", t_f, "mult", 6 if lat < 3 else 25, 45)
        w.add_effect("request_rate", "orders-svc", t_f, "mult", 0.8, 60)
        w.add_log("orders-svc", "warn", "call to {dep} slow: {ms}ms (path=/charge)", t_f, every_s=3, ms_base=int(lat * 1000))
        if lat >= 2:
            w.add_log("orders-svc", "error", "context deadline exceeded calling {dep} /charge", t_f + 30, every_s=3)

    def live_steps(self, params):
        p = self.merged(params)
        return [{"do": "toxiproxy", "proxy": "payments", "toxic": "latency", "latency_ms": p["latency_ms"]}]


FAULT = SlowDependency("slow_dependency", "HighLatency_orders", Category.DEPENDENCY_LATENCY,
                       {"latency_ms": 2000, "dependency": "payments-svc"}, "Toxiproxy adds latency to payments.")
