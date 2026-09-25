from __future__ import annotations

from agents.core.mcp_client import CallContext, InProcessClient
from mcp_servers.kubectl.server import build
from mcp_servers.policy import PolicyEngine


class FakeK8s:
    def __init__(self):
        self.calls = []

    async def get(self, kind, namespace):
        return [{"name": "orders-abc", "status": "Running", "restarts": 7}]

    async def events(self, namespace):
        return [{"reason": "OOMKilled", "object": "orders-abc", "message": "container exceeded memory limit"}]

    async def logs(self, pod, namespace, tail):
        return "panic: nil pointer"

    async def rollout_restart(self, d, ns):
        self.calls.append(("restart", d))
        return {"output": "restarted"}

    async def scale(self, d, ns, r):
        self.calls.append(("scale", d, r))
        return {"output": "scaled"}


async def test_kubectl_server_reads_freely_and_gates_writes(db):
    k = FakeK8s()
    c = InProcessClient([build(k)], PolicyEngine(db, dry_run=False))
    r = await c.call_tool("kubectl__get", {"kind": "pods"}, CallContext())
    assert '"restarts": 7' in r.content
    blocked = await c.call_tool("kubectl__rollout_restart", {"deployment": "orders"}, CallContext())
    assert blocked.blocked and k.calls == []
    ok = await c.call_tool("kubectl__scale", {"deployment": "orders", "replicas": 3}, CallContext(approved_by="alice"))
    assert not ok.blocked and k.calls == [("scale", "orders", 3)]
    zero = await c.call_tool("kubectl__scale", {"deployment": "orders", "replicas": 0}, CallContext(approved_by="alice"))
    assert "destructive" in zero.content and k.calls == [("scale", "orders", 3)]
