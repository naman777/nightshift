from __future__ import annotations

from typing import Any

from agents.core.models import Tier

from ..base import Server, schema
from .backend import KubectlBackend

NS = ("string", "namespace, default 'default'")


def build(backend: KubectlBackend) -> Server:
    srv = Server("kubectl", backend)

    @srv.tool("get", "List pods/deployments/services/nodes/configmaps with status and restart counts (read-only).",
              schema({"kind": ("string", "pods|deployments|services|nodes|configmaps"), "namespace": NS}, ["kind"]))
    async def get(b: KubectlBackend, kind: str, namespace: str = "default") -> Any:
        return {"items": await b.get(kind, namespace)}

    @srv.tool("events", "Recent cluster events (OOMKilled, BackOff, FailedScheduling...).", schema({"namespace": NS}))
    async def events(b: KubectlBackend, namespace: str = "default") -> Any:
        return {"events": await b.events(namespace)}

    @srv.tool("logs", "Tail a pod's logs.", schema({"pod": ("string", ""), "namespace": NS, "tail": ("number", "lines, default 100")}, ["pod"]))
    async def logs(b: KubectlBackend, pod: str, namespace: str = "default", tail: int = 100) -> Any:
        return {"logs": await b.logs(pod, namespace, int(tail))}

    @srv.tool("rollout_restart", "Rolling restart of a deployment. Reversible.", schema({"deployment": ("string", ""), "namespace": NS}, ["deployment"]), Tier.REVERSIBLE)
    async def rollout_restart(b: KubectlBackend, deployment: str, namespace: str = "default") -> Any:
        return await b.rollout_restart(deployment, namespace)

    @srv.tool("scale", "Scale a deployment to N (>=1) replicas. Reversible.",
              schema({"deployment": ("string", ""), "replicas": ("number", ">= 1"), "namespace": NS}, ["deployment", "replicas"]), Tier.REVERSIBLE)
    async def scale(b: KubectlBackend, deployment: str, replicas: int, namespace: str = "default") -> Any:
        if int(replicas) < 1:
            return {"ok": False, "output": "scaling to zero is a destructive action and is not offered here"}
        return await b.scale(deployment, namespace, int(replicas))

    return srv
