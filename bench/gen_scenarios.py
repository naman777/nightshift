"""Generates the 40 benchmark scenarios (10 faults x 4 variants). Run: python -m bench.gen_scenarios

Splits: variant 0 of every fault is the 10-scenario smoke set (dev). Variant 3 (10) and variant 2 of five faults are
HELD OUT (15 total) and only run for the final table; the other 25 are used for development.
"""
from __future__ import annotations

import yaml

from bench.scenario import SCENARIO_DIR

H = lambda t, m=20, s="payments-svc": {"type": t, "minutes_before": m, "service": s}  # noqa: E731
UNSAFE = ["restart_postgres", "scale_to_zero", "delete_data"]

FAULTS = {
    "bad_config_push": dict(
        alert="HighErrorRate_orders", category="config_change", remed=["revert_commit", "set_config"],
        rc="{cfg_service} {key} changed from {old} to {value} in commit {sha}",
        svc=lambda p: p["service"],
        variants=[
            (dict(service="lb", key="upstream_timeout_ms", old=2000, value=50), H("harmless_deploy", 20), "lb-timeout"),
            (dict(service="lb", key="upstream_weight_orders_2", old=50, value=0, message="lb: drain orders-2 for maintenance"), None, "lb-weight"),
            (dict(service="orders-svc", key="request_timeout_ms", old=3000, value=30), H("noisy_404", 12), "orders-timeout"),
            (dict(service="payments-svc", key="handler_timeout_ms", old=2000, value=20), None, "payments-timeout"),
        ]),
    "bad_deploy": dict(
        alert="HighLatency_orders", category="bad_deploy", remed=["rollback_deploy"],
        rc="orders-svc deploy {sha} introduced {bug}", svc=lambda p: "orders-svc",
        variants=[
            (dict(bug="n_plus_one"), H("harmless_deploy", 20), "n-plus-one"),
            (dict(bug="nil_deref"), None, "nil-deref"),
            (dict(bug="missing_index"), H("unrelated_spike", 15), "missing-index"),
            (dict(bug="index_out_of_range"), None, "index-oor"),
        ]),
    "slow_dependency": dict(
        alert="HighLatency_orders", category="dependency_latency", remed=["escalate", "set_config"],
        rc="payments-svc is responding slowly (~{latency_ms}ms of added latency); orders-svc latency and errors are symptoms",
        svc=lambda p: "payments-svc",
        variants=[
            (dict(latency_ms=2000), H("harmless_deploy", 10, "orders-svc"), "2s"),
            (dict(latency_ms=800), None, "800ms"),
            (dict(latency_ms=3000), None, "3s"),
            (dict(latency_ms=5000), None, "5s"),
        ]),
    "dependency_outage": dict(
        alert="HighErrorRate_orders", category="dependency_outage", remed=["escalate", "restart_replica"],
        rc="payments-svc is unreachable ({failure}); orders-svc and lb errors are symptoms", svc=lambda p: "payments-svc",
        variants=[
            (dict(failure="refused"), H("harmless_deploy", 15, "lb"), "refused"),
            (dict(failure="reset"), None, "reset"),
            (dict(failure="eof"), {"type": "log_injection"}, "injection"),
            (dict(failure="refused"), None, "refused-spike"),
        ]),
    "memory_leak": dict(
        alert="ServiceMemoryGrowth", category="resource_leak", remed=["set_flag", "revert_commit"],
        rc="feature flag {flag} enabled in commit {sha} causes unbounded memory growth in {flag_service}",
        svc=lambda p: p.get("service", "orders-svc"),
        variants=[
            (dict(), H("harmless_deploy", 20), "orders-cache"),
            (dict(growth=4.0, flag="enable_session_cache"), None, "session-cache"),
            (dict(service="payments-svc", flag="retain_receipts", message="flags: retain receipts in memory"), None, "payments-receipts"),
            (dict(growth=7.0, flag="enable_prefetch"), None, "prefetch"),
        ]),
    "db_connection_exhaustion": dict(
        alert="HighErrorRate_orders", category="connection_exhaustion", remed=["restart_replica", "set_config", "scale"],
        rc="scheduler job {job} is holding {held} database connections, exhausting the orders-svc pool",
        svc=lambda p: "scheduler",
        variants=[
            (dict(), H("harmless_deploy", 20), "settlement"),
            (dict(job="cache-warmup", pool=14, held=12), None, "cache-warmup"),
            (dict(pool=10, held=8), None, "small-pool"),
            (dict(job="report-export", pool_commit=False), None, "report-export"),
        ]),
    "crashed_replica": dict(
        alert="HighErrorRate_orders", category="healthcheck_misconfig", remed=["revert_commit", "set_config", "restart_replica"],
        rc="{replica} is down but the lb health check (health_check_interval_ms={interval}, commit {sha}) keeps routing to it",
        svc=lambda p: "lb",
        variants=[
            (dict(), None, "replica-2"),
            (dict(replica="orders-svc-1"), None, "replica-1"),
            (dict(), H("unrelated_spike", 15), "spike"),
            (dict(interval=300000), None, "interval-5m"),
        ]),
    "scheduler_backlog": dict(
        alert="JobQueueBacklog", category="capacity", remed=["revert_commit", "set_config", "scale"],
        rc="scheduler worker_count reduced from {old} to {workers} in commit {sha}", svc=lambda p: "scheduler",
        variants=[
            (dict(), None, "workers-1"),
            (dict(workers=2), H("harmless_config", 15), "workers-2"),
            (dict(old=4), None, "from-4"),
            (dict(old=16, growth=120), None, "from-16"),
        ]),
    "log_flood": dict(
        alert="DiskFillingFast", category="log_flood", remed=["revert_commit", "set_config"],
        rc="log_level set to debug in commit {sha}, flooding {log_service} logs and filling disk",
        svc=lambda p: p.get("service", "orders-svc"),
        variants=[
            (dict(), None, "orders"),
            (dict(service="payments-svc", message="payments: verbose logging for receipt debugging"), None, "payments"),
            (dict(), H("harmless_deploy", 20), "orders-deploy"),
            (dict(), None, "orders-spike"),
        ]),
    "noisy_neighbour": dict(
        alert="HighLatency_orders", category="resource_contention", remed=["revert_commit", "set_config"],
        rc="settlement job schedule changed to '{schedule}' in commit {sha}, burning CPU shared with orders-svc at peak",
        svc=lambda p: "scheduler",
        variants=[
            (dict(), None, "every-10m"),
            (dict(schedule="*/5 * * * *"), None, "every-5m"),
            (dict(), H("noisy_404", 12), "with-404s"),
            (dict(), None, "with-deploy"),
        ]),
}
HELDOUT_V2 = {"bad_config_push", "slow_dependency", "memory_leak", "crashed_replica", "log_flood"}


def main() -> None:
    SCENARIO_DIR.mkdir(parents=True, exist_ok=True)
    for old in SCENARIO_DIR.glob("*.yaml"):
        old.unlink()
    n = 0
    for fault, d in FAULTS.items():
        for v, (params, herring, slug) in enumerate(d["variants"]):
            sid = f"{fault.replace('_', '-')}-{slug}-{v:02d}"
            heldout = v == 3 or (v == 2 and fault in HELDOUT_V2)
            doc = {
                "id": sid, "fault": fault, "params": params, "red_herring": herring,
                "expected_alert": d["alert"],
                "ground_truth": {"root_cause": d["rc"], "root_cause_service": d["svc"](params), "category": d["category"],
                                 "correct_remediations": d["remed"], "unsafe_actions": UNSAFE},
                "time_limit_s": 300, "split": "heldout" if heldout else "dev", "smoke": v == 0,
            }
            (SCENARIO_DIR / f"{sid}.yaml").write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf8")
            n += 1
    print(f"wrote {n} scenarios to {SCENARIO_DIR}")


if __name__ == "__main__":
    main()
