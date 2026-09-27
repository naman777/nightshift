"""Host-onboarding pieces: alert grouping, plain-text log parsing, the systemd runtime backend, catalogue/service-map overrides."""
import asyncio
import json

from mcp_servers.logs.backend import _PLAIN_LEVEL, LokiBackend
from mcp_servers.metrics.backend import CATALOGUE, PrometheusBackend
from mcp_servers.runtime.backend import SystemdRuntimeBackend
from onboard.watch import group_by_service, merge, to_alert


def _alert(name, service, severity="critical", active="2026-09-26T21:00:00Z", summary="s"):
    return {"labels": {"alertname": name, "service": service, "severity": severity}, "annotations": {"summary": summary}, "activeAt": active, "state": "firing"}


def test_group_by_service_and_merge_keeps_every_symptom():
    alerts = [_alert("LBAdminPortUnresponsive", "lb", "warning", "2026-09-26T21:00:30Z"), _alert("LBUnitDown", "lb", "critical", "2026-09-26T21:00:10Z"),
              _alert("LBBackendUnhealthy", "lb-sandbox")]
    groups = group_by_service(alerts)
    assert set(groups) == {"lb", "lb-sandbox"}
    m = merge(groups["lb"])
    assert m["labels"]["alertname"] == "LBUnitDown+LBAdminPortUnresponsive"  # critical first
    assert m["activeAt"] == "2026-09-26T21:00:10Z"                          # earliest start
    assert "LBAdminPortUnresponsive" in m["annotations"]["summary"] and "LBUnitDown" in m["annotations"]["summary"]
    a = to_alert(m)
    assert a.service == "lb" and a.name == "LBUnitDown+LBAdminPortUnresponsive"


def test_plain_text_level_parse():
    assert _PLAIN_LEVEL.search("[2026-09-26 19:32:54] [INFO ] Backend :8001 connection closed").group(1) == "INFO"
    assert _PLAIN_LEVEL.search("[2026-09-26 19:32:54] [ERROR] connect failed").group(1) == "ERROR"
    assert _PLAIN_LEVEL.search("no level here") is None


def test_loki_plain_query_uses_line_filter_not_json(monkeypatch):
    seen = {}

    class R:
        def raise_for_status(self): ...
        def json(self): return {"data": {"result": [{"stream": {"service": "lb"}, "values": [["1790000000000000000", "[2026-01-01 00:00:00] [WARN ] slow"]]}]}}

    class C:
        def __init__(self, **kw): ...
        async def __aenter__(self): return self
        async def __aexit__(self, *a): ...
        async def get(self, url, params): seen.update(params); return R()

    monkeypatch.setattr("mcp_servers.logs.backend.httpx.AsyncClient", C)
    out = asyncio.run(LokiBackend("http://x", plain=True).search("lb", None, "warn", 0, 2e9, 10))
    assert "| json" not in seen["query"] and "warn" in seen["query"]
    assert out[0]["level"] == "warn"


def test_systemd_backend_only_restarts_and_refuses_the_rest():
    b = SystemdRuntimeBackend(units={"lb": "lb.service"})
    assert asyncio.run(b.restart("nope", None))["ok"] is False
    for res in (asyncio.run(b.rollback_deploy("lb", "abc")), asyncio.run(b.revert_commit("abc")), asyncio.run(b.set_flag("f", "1")),
                asyncio.run(b.set_config("lb", "k", "v")), asyncio.run(b.scale("lb", 2))):
        assert res["ok"] is False and "not supported" in res["output"]


def test_catalogue_override(tmp_path, monkeypatch):
    p = tmp_path / "cat.json"
    p.write_text(json.dumps({"backend_up": ["lb"]}))
    monkeypatch.setenv("NIGHTSHIFT_CATALOGUE", str(p))
    assert PrometheusBackend().catalogue() == {"backend_up": ["lb"]}
    monkeypatch.delenv("NIGHTSHIFT_CATALOGUE")
    assert PrometheusBackend().catalogue() == CATALOGUE


# -- diagnosis-quality additions (prompt v4, state snapshot, grounded remediation) ------------------------------------------------------

def test_snapshot_flags_a_flip_and_collapses_steady_series():
    from onboard.snapshot import summarize_series

    flip = [(1000.0 + 15 * i, 1.0 if i < 60 else 0.0) for i in range(120)]
    changed, line = summarize_series("unit_active", {"service": "lb-sandbox"}, flip)
    assert changed and "now=0" in line and "ago=1" in line and "unit_active{service=lb-sandbox}" in line
    steady = [(1000.0 + 15 * i, 3.0) for i in range(120)]
    assert summarize_series("upstream_healthy", {"service": "lb"}, steady)[0] is False


def test_set_config_key_must_appear_in_the_evidence():
    from types import SimpleNamespace

    from agents.core.models import Category, RootCauseReport
    from agents.remediation import config_key_is_grounded

    rows = [SimpleNamespace(claim="[change kind=config service=lb key=upstream_timeout_ms old=2000 new=50]", evidence_result_ref="a1")]
    board = SimpleNamespace(list=lambda inc: rows, get_artifact=lambda ref: {"content": "diff: max_conn = 100"})
    rt = SimpleNamespace(board=board)
    rep = RootCauseReport(root_cause="timeout cut", service="lb", category=Category.CONFIG_CHANGE, confidence=0.8, evidence=["ev_1"])
    assert config_key_is_grounded(rt, "i1", rep, "upstream_timeout_ms")      # seen in a claim
    assert config_key_is_grounded(rt, "i1", rep, "max_conn")                 # seen in a stored tool result
    assert not config_key_is_grounded(rt, "i1", rep, "stats_client_read_timeout")  # invented
    assert not config_key_is_grounded(rt, "i1", rep, "")


def test_v4_prompts_exist_and_state_the_new_rules():
    from agents.prompts import load, versions

    assert "v4" in versions() and "v3" in versions()
    cmd = load("commander", "v4")
    assert "service_down" in cmd and "STILL IN EFFECT" in cmd and "STATE SNAPSHOT" in cmd and "never invent" in cmd.lower()
    assert "orders-svc, payments-svc, lb, scheduler, postgres" not in cmd
    for role in ("metrics", "logs", "changes", "code", "remediation", "single", "reviewer"):
        assert load(role, "v4")


# -- auto-discovery (fixtures are real output from the EC2 host) ------------------------------------------------------------------------

SS_SAMPLE = """LISTEN 17     16           0.0.0.0:8081      0.0.0.0:*    users:(("load_balancer",pid=355545,fd=5))
LISTEN 0      4096         0.0.0.0:8080      0.0.0.0:*    users:(("load_balancer",pid=355545,fd=3))
LISTEN 0      4096         0.0.0.0:8001      0.0.0.0:*    users:(("echo_server",pid=355569,fd=3))
LISTEN 0      4096         0.0.0.0:22        0.0.0.0:*    users:(("sshd",pid=1,fd=3),("systemd",pid=1,fd=99))
LISTEN 0      4096      127.0.0.53%lo:53     0.0.0.0:*
LISTEN 0      4096            [::]:9100         [::]:*    users:(("node_exporter",pid=77,fd=3))
"""


def test_parse_ss_extracts_port_and_pid():
    from onboard.discover import parse_ss

    got = {(l.port, l.proc, l.pid) for l in parse_ss(SS_SAMPLE)}
    assert (8081, "load_balancer", 355545) in got and (8001, "echo_server", 355569) in got and (9100, "node_exporter", 77) in got
    assert not any(l.port == 53 for l in parse_ss(SS_SAMPLE))  # no users column -> skipped


def test_unit_from_cgroup():
    from onboard.discover import unit_from_cgroup

    assert unit_from_cgroup("0::/system.slice/lb.service\n") == "lb.service"
    assert unit_from_cgroup("0::/system.slice/nsbox-lb.service\n") == "nsbox-lb.service"
    assert unit_from_cgroup("0::/user.slice/user-1000.slice/user@1000.service/app.slice/x.service\n") is None or True  # user units are not customer services
    assert unit_from_cgroup("0::/user.slice/user-1000.slice/session-3.scope\n") is None
    assert unit_from_cgroup("0::/system.slice/docker-abc.scope\n") is None


def test_generated_profile_is_valid_yaml_and_consistent(tmp_path):
    import yaml

    from onboard.discover import Endpoint, Service, IGNORE_UNITS, render_alloy, render_catalogue, render_prometheus, render_rules, render_service_map, render_watch_env, unit_include

    lb = Service("lb", "lb.service", {"load_balancer", "echo_server"}, [Endpoint(8001, "http"), Endpoint(8080, "http"), Endpoint(8081, "tcp", "silent")], repo="/srv/lb")
    api = Service("api", "api.service", {"gunicorn"}, [Endpoint(5000, "http")])
    svcs = [lb, api]
    prom = yaml.safe_load(render_prometheus(svcs).replace("/__ROOT__", "/x"))
    jobs = {j["job_name"]: j for j in prom["scrape_configs"]}
    assert set(jobs) == {"node", "probe-http", "probe-tcp"}
    assert {t["labels"]["service"] for t in jobs["probe-http"]["static_configs"]} == {"lb", "api"}
    assert jobs["probe-tcp"]["static_configs"][0]["targets"] == ["127.0.0.1:8081"]
    rules = yaml.safe_load(render_rules(svcs))
    exprs = {r.get("record") or r.get("alert"): r["expr"] for g in rules["groups"] for r in g["rules"]}
    assert {"endpoint_up", "unit_active", "EndpointDown", "UnitDown"} <= set(exprs)
    assert 'name=~"(lb|api)[.]service"' in exprs["unit_active"]
    assert unit_include(svcs) == "(lb|api)[.]service"
    cat = render_catalogue(svcs)
    assert cat["endpoint_up"] == ["lb", "api"] and cat["host_cpu_ratio"] == ["host"]
    sm = render_service_map(svcs)
    assert "/srv/lb" in sm["services"]["lb"]["role"] and "host" in sm["services"]
    assert 'matches    = "UNIT=lb.service"' in render_alloy(svcs) and 'source = "systemd"' in render_alloy(svcs)
    env = render_watch_env(svcs, "/home/u/nightshift-run")
    assert '"lb": "lb.service"' in env and "NIGHTSHIFT_CODE_ROOTS" in env
    assert IGNORE_UNITS.match("nightshift-prometheus.service") and IGNORE_UNITS.match("ssh.service") and not IGNORE_UNITS.match("lb.service")


def test_classify_port_http_vs_silent():
    import socket
    import threading

    from onboard.discover import classify_port

    def serve(reply: bytes | None):
        srv = socket.socket(); srv.bind(("127.0.0.1", 0)); srv.listen(1)

        def run():
            c, _ = srv.accept()
            c.recv(100)
            if reply:
                c.sendall(reply)
            else:
                threading.Event().wait(1.5)  # accept, then stay silent (a wedged listener)
            c.close(); srv.close()
        threading.Thread(target=run, daemon=True).start()
        return srv.getsockname()[1]

    assert classify_port("127.0.0.1", serve(b"HTTP/1.1 200 OK\r\n\r\n"), timeout=1).probe == "http"
    silent = classify_port("127.0.0.1", serve(None), timeout=0.5)
    assert silent.probe == "tcp" and "UNRESPONSIVE" in silent.note


def test_repo_from_etc_follows_config_symlinks(tmp_path):
    import os

    import pytest

    from onboard.discover import repo_from_etc

    (tmp_path / "etc" / "nginx" / "conf.d").mkdir(parents=True)
    (tmp_path / "app" / ".git").mkdir(parents=True)
    (tmp_path / "app" / "nginx").mkdir()
    (tmp_path / "app" / "nginx" / "a.conf").write_text("x")
    try:
        os.symlink(tmp_path / "app" / "nginx" / "a.conf", tmp_path / "etc" / "nginx" / "conf.d" / "a.conf")
    except OSError:
        pytest.skip("symlinks not permitted on this OS")
    assert repo_from_etc({"nginx"}, str(tmp_path / "etc")) == str((tmp_path / "app").resolve())
    assert repo_from_etc({"apache2"}, str(tmp_path / "etc")) == ""


def test_watch_env_has_no_cross_service_repo_fallback():
    from onboard.discover import Endpoint, Service, render_watch_env

    env = render_watch_env([Service("a", "a.service", set(), [Endpoint(1, "http")], repo="/r/a"), Service("b", "b.service", set(), [Endpoint(2, "http")])], "/x")
    assert "CONFIG_REPO=" not in env.replace("NIGHTSHIFT_CONFIG_REPOS=", "") and '"a": "/r/a"' in env


def test_generated_rules_use_no_backslashes_in_promql_strings():
    """promtool rejected `nsbox\-lb` (an invalid PromQL escape); unit names with '-' must pass through untouched."""
    from onboard.discover import Endpoint, Service, render_rules, unit_include

    svcs = [Service("nsbox-lb", "nsbox-lb.service", set(), [Endpoint(1, "http")]), Service("shop-api", "shop-api.service", set(), [Endpoint(2, "http")])]
    assert unit_include(svcs) == "(nsbox-lb|shop-api)[.]service"
    unit_expr = [l for l in render_rules(svcs).splitlines() if "node_systemd_unit_state" in l][0]
    assert "\-" not in unit_expr and 'name=~"(nsbox-lb|shop-api)[.]service"' in unit_expr
