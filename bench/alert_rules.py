"""Alert rules evaluated against the simulated world. Mirrors observability/prometheus/alerts.yml so that a scenario
whose expected alert never fires is flagged INVALID (a bug in the alert rules, not the agent)."""
from __future__ import annotations

from bench.sim.world import World

RULES = {
    "HighErrorRate_orders": lambda v, t: max(v("error_rate", "lb", t), v("error_rate", "orders-svc", t)) > 0.05,
    "HighLatency_orders": lambda v, t: v("p99_latency_seconds", "orders-svc", t) > 0.6,
    "ServiceMemoryGrowth": lambda v, t: any(v("memory_bytes", s, t) / v("memory_bytes", s, t - 1800) > 1.8 for s in ("orders-svc", "payments-svc")),
    "JobQueueBacklog": lambda v, t: v("queue_depth", "scheduler", t) > 100,
    "DiskFillingFast": lambda v, t: any(v("log_lines_per_second", s, t) > 400 for s in ("orders-svc", "payments-svc")),
}


def alert_fires(world: World, name: str) -> bool:
    rule = RULES.get(name)
    if rule is None:
        return False
    # must hold continuously for the last 2 minutes (Prometheus `for: 2m`)
    return all(rule(world.value, world.t_alert - d) for d in (0, 30, 60, 90, 120))
