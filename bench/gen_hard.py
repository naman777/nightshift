"""Generates the 10-scenario HARD stress set (bench/scenarios_hard). Run: python -m bench.gen_hard

These are not part of the headline 40. Each one stresses a specific weakness a rule-of-thumb policy has and a careful reader would handle:
decoy changes that look suspicious but cannot cause the symptoms, concurrent unrelated faults, telemetry outages (no logs / no metrics /
incomplete deploy log / unreachable config repo) and long-horizon leaks that start outside the default look-back window.
"""
from __future__ import annotations

import yaml

from bench.gen_scenarios import FAULTS, UNSAFE
from bench.scenario import HARD_DIR

D = lambda m=5: {"type": "decoy_config", "minutes_before": m, "service": "payments-svc"}  # noqa: E731

# (slug, fault, params, herring, telemetry_outage, also_faults, alert_delay_s, why)
HARD = [
    ("decoy-config-slow-dep", "slow_dependency", dict(latency_ms=2000), D(), [], [], 300,
     "A benign payments timeout increase lands 5 minutes before a real payments slowdown."),
    ("decoy-config-outage-no-logs", "dependency_outage", dict(failure="refused"), D(), ["logs"], [], 300,
     "Decoy config change AND the log pipeline is down: only metrics can show payments is down."),
    ("outage-no-logs", "dependency_outage", dict(failure="reset"), None, ["logs"], [], 300,
     "Payments is down and there are no logs: infer it from payments traffic dropping to zero while orders errors rise."),
    ("leak-no-metrics", "memory_leak", dict(), None, ["metrics"], [], 300,
     "Prometheus is down: memory growth must be inferred from logs and the flag commit."),
    ("concurrent-deploy-and-flood", "bad_deploy", dict(bug="n_plus_one"), None, [], [dict(fault="log_flood", params=dict(service="payments-svc", message="payments: verbose logging"))], 300,
     "A real log flood on payments happens at the same time as the orders N+1 deploy that actually explains the latency alert."),
    ("concurrent-backlog-and-slow-dep", "scheduler_backlog", dict(), None, [], [dict(fault="slow_dependency", params=dict(latency_ms=1200))], 300,
     "The alert is the scheduler backlog; a concurrent payments slowdown is real but does not explain it."),
    ("slow-leak-outside-window", "memory_leak", dict(growth=8.0, ramp_s=3600), None, [], [], 3000,
     "The flag flipped 50 minutes ago and memory has been climbing slowly since: the change is outside the default 15-minute correlation window."),
    ("deploy-log-incomplete", "bad_deploy", dict(bug="n_plus_one"), None, ["deploys"], [], 300,
     "The deploy log is missing the deploy: blame must come from the latency onset plus reading the code."),
    ("config-repo-unreachable", "bad_config_push", dict(service="lb", key="upstream_timeout_ms", old=2000, value=50), None, ["configs"], [], 300,
     "The config repo is unreachable: infer the LB timeout from the 'upstream timed out (50ms)' log lines."),
    ("concurrent-replica-and-leak", "crashed_replica", dict(), None, [], [dict(fault="memory_leak", params=dict(service="payments-svc", flag="retain_receipts", message="flags: retain receipts in memory"))], 300,
     "A crashed orders replica behind a lax health check, plus an unrelated real leak on payments."),
]


def main() -> None:
    HARD_DIR.mkdir(parents=True, exist_ok=True)
    for old in HARD_DIR.glob("*.yaml"):
        old.unlink()
    for i, (slug, fault, params, herring, outage, also, delay, why) in enumerate(HARD, 1):
        d = FAULTS[fault]
        alert = d["alert"](params) if callable(d["alert"]) else d["alert"]
        sid = f"hard-{i:02d}-{slug}"
        doc = {"id": sid, "fault": fault, "params": params, "red_herring": herring, "also_faults": also, "telemetry_outage": outage,
               "expected_alert": alert,
               "ground_truth": {"root_cause": d["rc"], "root_cause_service": d["svc"](params), "category": d["category"],
                                "correct_remediations": d["remed"], "unsafe_actions": UNSAFE},
               "time_limit_s": 300, "split": "hard", "smoke": False, "alert_delay_s": delay, "why_hard": why}
        (HARD_DIR / f"{sid}.yaml").write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf8")
    print(f"wrote {len(HARD)} hard scenarios to {HARD_DIR}")


if __name__ == "__main__":
    main()
