from __future__ import annotations

from agents.core.models import Category

from .base import Fault, config_commit


class DbConnectionExhaustion(Fault):
    def apply_sim(self, w, params, t_f):
        p = self.merged(params)
        w.facts.update(job=p["job"], pool=p["pool"])
        w.alert_name, w.alert_service = "HighErrorRate_orders", "orders-svc"
        if p.get("pool_commit"):
            c = config_commit(w, t_f - 3600, "orders-svc", "config/orders.yaml", "db_pool_size", 20, p["pool"],
                              "orders: right-size db pool", author="li")
            w.facts["pool_sha"] = c.sha
        w.add_effect("db_connections_in_use", "orders-svc", t_f, "set", p["pool"], 30)
        w.add_effect("db_connections_in_use", "scheduler", t_f, "add", p["held"], 30)
        w.add_effect("error_rate", "orders-svc", t_f + 20, "mult", 18, 40)
        w.add_effect("error_rate", "lb", t_f + 20, "mult", 15, 40)
        w.add_effect("p99_latency_seconds", "orders-svc", t_f, "mult", 6, 40)
        w.add_log("orders-svc", "error", "pool exhausted: {pool}/{pool} connections in use, waited 5000ms", t_f + 20, every_s=2)
        w.add_log("orders-svc", "error", "pq: sorry, too many clients already", t_f + 20, every_s=6)
        w.add_log("scheduler", "warn", "job {job} holding {held} db connections; transaction open for {ms}ms", t_f - 30, every_s=10, ms_base=180000)
        w.facts["held"] = p["held"]

    def live_steps(self, params):
        p = self.merged(params)
        return [{"do": "config", "service": "orders-svc", "key": "db_pool_size", "value": p["pool"]},
                {"do": "foreman_job", "job": p["job"], "hold_connections": p["held"]}]


FAULT = DbConnectionExhaustion("db_connection_exhaustion", "HighErrorRate_orders", Category.CONNECTION_EXHAUSTION,
                               {"job": "nightly-settlement", "pool": 12, "held": 10, "pool_commit": True},
                               "A long-running scheduler job holds most of the database connections.")
