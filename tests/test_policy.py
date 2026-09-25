from __future__ import annotations

import pytest

from agents.core.mcp_client import CallContext, InProcessClient
from mcp_servers.base import Server, schema
from mcp_servers.policy import PolicyEngine
from mcp_servers.runtime.server import build as build_runtime


class FakeRuntime:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        async def f(*a, **k):
            self.calls.append((name, a))
            return {"ok": True}
        return f


def setup(db, **kw):
    rt = FakeRuntime()
    policy = PolicyEngine(db, dry_run=False, **kw)
    return rt, policy, InProcessClient([build_runtime(rt)], policy)


async def test_reversible_needs_approval(db):
    rt, policy, client = setup(db)
    r = await client.call_tool("runtime__revert_commit", {"sha": "abc"}, CallContext(incident_id="i", agent="remediation"))
    assert r.blocked and rt.calls == []
    r = await client.call_tool("runtime__revert_commit", {"sha": "abc"}, CallContext(incident_id="i", approved_by="alice"))
    assert not r.blocked and rt.calls == [("revert_commit", ("abc",))]


async def test_destructive_needs_typed_confirmation_and_reason(db):
    rt, policy, client = setup(db)
    ctx = CallContext(incident_id="i", approved_by="alice")
    assert (await client.call_tool("runtime__restart_postgres", {}, ctx)).blocked
    ctx = CallContext(incident_id="i", approved_by="alice", confirmation="CONFIRM restart_postgres")
    assert (await client.call_tool("runtime__restart_postgres", {}, ctx)).blocked  # reason missing
    ctx.reason = "db wedged"
    assert not (await client.call_tool("runtime__restart_postgres", {}, ctx)).blocked


async def test_benchmark_mode_records_proposals_and_never_executes(db):
    rt, policy, client = setup(db, benchmark_mode=True)
    ctx = CallContext(incident_id="i", approved_by="alice", confirmation="CONFIRM scale_to_zero", reason="x")
    r = await client.call_tool("runtime__scale_to_zero", {"service": "orders-svc"}, ctx)
    assert r.dry_run and rt.calls == []
    assert policy.proposals == [{"tool": "runtime__scale_to_zero".split("__")[1], "args": {"service": "orders-svc"},
                                 "tier": "destructive", "agent": ""}]


async def test_kill_switch_makes_approved_writes_dry_run(db, monkeypatch):
    monkeypatch.setenv("NIGHTSHIFT_DRY_RUN", "1")
    rt = FakeRuntime()
    policy = PolicyEngine(db)  # dry_run=None -> env flag
    client = InProcessClient([build_runtime(rt)], policy)
    r = await client.call_tool("runtime__restart_replica", {"service": "orders-svc"}, CallContext(approved_by="a"))
    assert r.dry_run and rt.calls == []


async def test_every_call_is_audited_and_log_is_append_only(db):
    rt, policy, client = setup(db)
    await client.call_tool("runtime__revert_commit", {"sha": "a"}, CallContext(incident_id="i"))
    await client.call_tool("runtime__revert_commit", {"sha": "a"}, CallContext(incident_id="i", approved_by="bob", evidence_ids=["ev_1"]))
    rows = policy.audit_rows("i")
    assert [r["decision"] for r in rows] == ["blocked", "allowed"]
    assert rows[1]["evidence_ids"] == '["ev_1"]'
    with pytest.raises(Exception):
        db.execute("DELETE FROM audit_log")
    with pytest.raises(Exception):
        db.execute("UPDATE audit_log SET decision='allowed'")


async def test_timeout_is_enforced(db):
    import asyncio

    from agents.core.models import Tier

    srv = Server("slow", None)

    @srv.tool("sleep", "", schema({}))
    async def sleep(b):
        await asyncio.sleep(1)

    policy = PolicyEngine(db, timeouts={Tier.READ_ONLY: 0.05, Tier.REVERSIBLE: 1, Tier.DESTRUCTIVE: 1})
    r = await InProcessClient([srv], policy).call_tool("slow__sleep", {}, CallContext())
    assert r.is_error and "timed out" in r.content
