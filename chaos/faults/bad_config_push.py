from __future__ import annotations

from agents.core.models import Category

from .base import Fault, config_commit

VARIANTS = {
    # (service, key) -> (old, description-of-effect)
    ("lb", "upstream_timeout_ms"): "timeout",
    ("lb", "upstream_weight_orders_2"): "weight",
    ("orders-svc", "request_timeout_ms"): "timeout_orders",
    ("payments-svc", "handler_timeout_ms"): "timeout_payments",
}


class BadConfigPush(Fault):
    def apply_sim(self, w, params, t_f):
        p = self.merged(params)
        svc, key, val, old = p["service"], p["key"], p["value"], p["old"]
        kind = VARIANTS.get((svc, key), "timeout")
        c = config_commit(w, t_f - 20, svc, f"config/{svc}.yaml", key, old, val, p.get("message", f"{svc}: tune {key}"))
        w.facts.update(sha=c.sha, key=key, value=val, old=old, cfg_service=svc)
        w.alert_name, w.alert_service = "HighErrorRate_orders", "orders-svc"
        if kind == "timeout":
            w.add_effect("error_rate", "lb", t_f, "mult", 40, 20)
            w.add_effect("p99_latency_seconds", "lb", t_f, "mult", 1.6, 20)
            w.add_log("lb", "error", "upstream timed out ({value}ms) while reading response from upstream orders-svc-{n} path=/orders",
                      t_f, every_s=2)
        elif kind == "weight":
            w.add_effect("cpu_ratio", "orders-svc", t_f, "mult", 3.0, 30)
            w.add_effect("p99_latency_seconds", "orders-svc", t_f, "mult", 5.0, 30)
            w.add_effect("error_rate", "orders-svc", t_f, "mult", 25, 60)
            w.add_effect("error_rate", "lb", t_f, "mult", 20, 60)
            w.add_log("lb", "warn", "upstream orders-svc-2 weight={value}: all traffic routed to orders-svc-1", t_f, every_s=20)
            w.add_log("orders-svc", "error", "request queue full, shedding load (queue=512/512)", t_f + 20, every_s=2)
        elif kind == "timeout_orders":
            w.add_effect("error_rate", "orders-svc", t_f, "mult", 60, 20)
            w.add_log("orders-svc", "error", "context deadline exceeded after {value}ms handling /orders (request_timeout_ms={value})",
                      t_f, every_s=2)
        else:
            w.add_effect("error_rate", "payments-svc", t_f, "mult", 80, 20)
            w.add_effect("error_rate", "orders-svc", t_f, "mult", 30, 30)
            w.add_log("payments-svc", "error", "handler exceeded handler_timeout_ms={value}: returning 504 for /charge", t_f, every_s=2)
            w.add_log("orders-svc", "error", "payments-svc returned 504 Gateway Timeout for /charge", t_f, every_s=2)

    def live_steps(self, params):
        p = self.merged(params)
        return [{"do": "config", "service": p["service"], "key": p["key"], "value": p["value"], "message": p.get("message", "")}]


FAULT = BadConfigPush("bad_config_push", "HighErrorRate_orders", Category.CONFIG_CHANGE,
                      {"service": "lb", "key": "upstream_timeout_ms", "value": 50, "old": 2000},
                      "A bad configuration value is committed and reloaded.")
