"""Static consistency checks across the docker stack, observability configs, Go services and the agents' expectations.
Docker and Go are not available everywhere, so these catch drift between the pieces without running them."""
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from bench.alert_rules import RULES
from bench.scenario import load_all, load_hard
from chaos.gitcfg import ROOT
from mcp_servers.metrics.backend import CATALOGUE

RAW_GAUGES = {"db_connections_in_use", "disk_used_ratio", "upstream_healthy", "queue_depth"}  # exported directly with a `service` label


def load(path: str):
    return yaml.safe_load((ROOT / path).read_text(encoding="utf8"))


def go_source() -> str:
    return "\n".join(p.read_text(encoding="utf8") for p in (ROOT / "target").rglob("*.go"))


def test_compose_parses_and_mounted_paths_exist():
    compose = load("docker-compose.yml")
    services = compose["services"]
    for name in ("postgres", "orders-svc-1", "orders-svc-2", "payments-svc", "lb", "scheduler", "prometheus", "alertmanager", "loki",
                 "grafana", "temporal", "gateway", "nightshift-worker", "dashboard", "toxiproxy"):
        assert name in services, name
    assert services["nightshift-worker"]["container_name"] == "nightshift-worker"  # the crash demo kills this by name
    for name, svc in services.items():
        for vol in svc.get("volumes", []):
            src = vol.split(":")[0]
            if src.startswith("./"):
                assert (ROOT / src).exists(), f"{name}: missing mount source {src}"
        build = svc.get("build")
        if isinstance(build, dict) and "context" in build:
            assert (ROOT / build["context"]).is_dir(), f"{name}: missing build context"
            if "dockerfile" in build:
                assert (ROOT / build["dockerfile"]).exists()


def test_every_metric_the_agents_query_is_produced_by_the_stack():
    recorded = {r["record"] for g in load("observability/prometheus/rules/recording.yml")["groups"] for r in g["rules"]}
    missing = set(CATALOGUE) - recorded - RAW_GAUGES
    assert not missing, f"metrics the MCP server queries but Prometheus never produces: {missing}"
    src = go_source()
    for gauge in RAW_GAUGES | {"process_resident_memory_bytes", "process_cpu_seconds_total", "process_start_time_seconds", "log_lines_total",
                               "http_requests_total", "http_request_duration_seconds", "dependency_latency_seconds"}:
        assert gauge in src, f"Go services never export {gauge}"


def test_alert_rules_match_the_benchmark_rules_and_every_scenario_alert_exists():
    alerts = {r["alert"] for g in load("observability/prometheus/rules/alerts.yml")["groups"] for r in g["rules"]}
    assert alerts == set(RULES)
    for s in load_all() + load_hard():
        assert s.expected_alert in alerts, s.id


def test_prometheus_scrapes_every_service_with_a_service_label():
    prom = load("observability/prometheus/prometheus.yml")
    labelled = {t["labels"]["service"] for job in prom["scrape_configs"] for t in job["static_configs"]}
    assert labelled == {"orders-svc", "payments-svc", "lb", "scheduler"}
    assert load("observability/alertmanager/alertmanager.yml")["receivers"][0]["webhook_configs"][0]["url"].endswith("/webhook/alertmanager")


def test_config_repo_defaults_cover_every_key_the_faults_touch():
    cfg = {p.stem: p.read_text(encoding="utf8") for p in (ROOT / "target" / "config").glob("*.yaml")}
    flags = json.loads((ROOT / "target" / "config" / "flags.json").read_text())
    for fault in ("bad_config_push", "db_connection_exhaustion", "crashed_replica", "scheduler_backlog", "log_flood", "noisy_neighbour", "memory_leak"):
        mod = (ROOT / "chaos" / "faults" / f"{fault}.py").read_text()
        for key in re.findall(r'"(upstream_timeout_ms|request_timeout_ms|handler_timeout_ms|db_pool_size|health_check_interval_ms|worker_count|log_level|settlement_schedule)"', mod):
            assert any(f"{key}:" in text for text in cfg.values()), f"{fault} touches {key} but no config file declares it"
    for flag in ("enable_unbounded_cache", "enable_session_cache", "enable_prefetch", "retain_receipts"):
        assert flag in flags


def test_grafana_dashboard_uses_recorded_metric_names():
    d = json.loads((ROOT / "observability" / "grafana" / "dashboards" / "nightshift.json").read_text())
    exprs = {t["expr"] for p in d["panels"] for t in p["targets"]}
    assert exprs <= (set(CATALOGUE) | {"request_rate"})


def test_loki_and_promtail_configs_parse():
    assert load("observability/loki/loki.yml")["server"]["http_listen_port"] == 3100
    stages = load("observability/promtail/promtail.yml")["scrape_configs"][0]["pipeline_stages"]
    assert {"service", "level"} <= set(stages[0]["json"]["expressions"])


def test_ci_workflow_is_valid_yaml_with_the_eval_gate():
    wf = load(".github/workflows/ci.yml")
    assert {"test", "eval-smoke", "go", "dashboard", "compose-config"} <= set(wf["jobs"])
    gate = " ".join(step.get("run", "") for step in wf["jobs"]["eval-smoke"]["steps"])
    assert "--baseline bench/baseline.json" in gate and "--max-drop 0.10" in gate
