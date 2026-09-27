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
