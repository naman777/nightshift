from __future__ import annotations

import json
import sys

import pytest

from agents.core.mcp_client import CallContext, InProcessClient, StdioMCPClient
from bench.scenario import build_world, load_all
from bench.sim import sim_backends
from mcp_servers.code.backend import FsCodeBackend, SandboxError
from mcp_servers.common import onset, signature, to_ts
from mcp_servers.policy import PolicyEngine
from mcp_servers.registry import build_servers


def world(sid="bad-deploy-n-plus-one-00"):
    return build_world(next(s for s in load_all() if s.id == sid))[0]


async def call(client, name, args=None):
    r = await client.call_tool(name, args or {}, CallContext(agent="test"))
    return json.loads(r.content) if not r.is_error and not r.blocked else r.content


@pytest.fixture
def client(db):
    return InProcessClient(build_servers(sim_backends(world())), PolicyEngine(db, benchmark_mode=True))


def test_time_parsing_and_helpers():
    assert to_ts("-30m", 1000.0) == 1000.0 - 1800 and to_ts("now", 5.0) == 5.0 and to_ts(12, 0) == 12.0
    assert signature("took 1500ms for order_id=abc123 hex deadbeef01") == "took <n> for order_id=<id> hex <hex>"
    pts = [(i * 30.0, 1.0) for i in range(20)] + [(600 + i * 30.0, 9.0) for i in range(10)]
    assert onset(pts) == 600.0
    assert onset([(i, 1.0) for i in range(30)]) is None


async def test_metrics_server_finds_the_anomaly(client):
    out = await call(client, "metrics__top_anomalies")
    top = out["anomalies"][0]
    assert top["metric"] == "p99_latency_seconds" and top["service"] == "orders-svc" and top["change_ratio"] > 5
    rng = await call(client, "metrics__query_range", {"query": 'p99_latency_seconds{service="orders-svc"}', "start": "-30m"})
    assert rng["series"][0]["labels"]["service"] == "orders-svc" and rng["series"][0]["onset_ts"]
    cmp_ = await call(client, "metrics__compare_windows", {"query": 'p99_latency_seconds{service="orders-svc"}', "a_start": "-30m", "a_end": "-10m",
                                                           "b_start": "-3m", "b_end": "now"})
    assert cmp_["ratio_b_over_a"] > 5


async def test_logs_server_clusters_signatures(client):
    out = await call(client, "logs__cluster_errors", {"service": "orders-svc"})
    assert out["clusters"] and out["clusters"][0]["count"] > 10 and "slow query" in out["clusters"][0]["signature"]
    tail = await call(client, "logs__tail", {"service": "orders-svc", "n": 5})
    assert tail["count"] == 5


async def test_changes_and_code_servers(client):
    deploys = (await call(client, "changes__recent_deploys", {"since_minutes": 60}))["deploys"]
    assert deploys and deploys[-1]["service"] == "orders-svc"
    diff = await call(client, "changes__commit_diff", {"sha": deploys[-1]["sha"]})
    assert "loadItems" in diff["diff"]
    grep = await call(client, "code__grep", {"pattern": "loadItems"})
    assert grep["matches"]
    tests = await call(client, "code__run_tests", {"target": "go test ./..."})
    assert tests["passed"] is True  # the N+1 regression is a perf bug the tests do not catch
    assert "escapes sandbox" in str(await client.call_tool("code__read_file", {"path": "../../etc/passwd"}, CallContext()) and
                                    (await client.call_tool("code__read_file", {"path": "../../etc/passwd"}, CallContext())).content)


async def test_write_tools_are_proposals_in_benchmark_mode(client):
    r = await client.call_tool("runtime__rollback_deploy", {"service": "orders-svc", "sha": "abc"}, CallContext(approved_by="x"))
    assert r.dry_run and "PROPOSED" in r.content


async def test_fs_code_backend_sandbox(tmp_path):
    (tmp_path / "a.go").write_text("package a\nfunc A() {}\n")
    b = FsCodeBackend(tmp_path)
    assert (await b.read_file("a.go", 1, 10))["total_lines"] == 2
    assert (await b.grep("func", None, 5))[0]["path"] == "a.go"
    with pytest.raises(SandboxError):
        await b.read_file("../secret", 1, 2)
    assert "not allow-listed" in (await b.run_tests("rm -rf /"))["error"]


async def test_real_mcp_over_stdio(tmp_path):
    (tmp_path / "main.go").write_text("package main\nfunc main() {}\n")
    async with StdioMCPClient(["code"], env={"CODE_ROOT": str(tmp_path), "PYTHONPATH": str(__import__("pathlib").Path(__file__).parent.parent)}) as c:
        tools = {t.name for t in await c.list_tools()}
        assert {"code__read_file", "code__grep", "code__run_tests"} <= tools
        res = await c.call_tool("code__read_file", {"path": "main.go"}, CallContext())
        assert "package main" in res.content
