"""kubectl backend (stretch goal): lets the same agents run against a `kind` cluster. Read verbs are allow-listed; writes are separate tools."""
from __future__ import annotations

import asyncio
import json
from typing import Any, Protocol


class KubectlBackend(Protocol):
    async def get(self, kind: str, namespace: str) -> list[dict[str, Any]]: ...
    async def events(self, namespace: str) -> list[dict[str, Any]]: ...
    async def logs(self, pod: str, namespace: str, tail: int) -> str: ...
    async def rollout_restart(self, deployment: str, namespace: str) -> dict[str, Any]: ...
    async def scale(self, deployment: str, namespace: str, replicas: int) -> dict[str, Any]: ...


READ_KINDS = {"pods", "deployments", "services", "nodes", "configmaps"}


class CliKubectl:
    def __init__(self, context: str | None = None):
        self.base = ["kubectl"] + (["--context", context] if context else [])

    async def _run(self, *args: str) -> str:
        proc = await asyncio.create_subprocess_exec(*self.base, *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        try:
            out, _ = await asyncio.wait_for(proc.communicate(), 30)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            proc.kill()
            raise
        return out.decode(errors="replace")

    async def get(self, kind, namespace):
        if kind not in READ_KINDS:
            raise ValueError(f"kind not allow-listed: {kind}")
        items = json.loads(await self._run("get", kind, "-n", namespace, "-o", "json")).get("items", [])
        return [{"name": i["metadata"]["name"], "status": i.get("status", {}).get("phase") or i.get("status", {}).get("availableReplicas"),
                 "restarts": sum(c.get("restartCount", 0) for c in i.get("status", {}).get("containerStatuses", []))} for i in items]

    async def events(self, namespace):
        items = json.loads(await self._run("get", "events", "-n", namespace, "-o", "json")).get("items", [])
        return [{"reason": e.get("reason"), "object": e["involvedObject"]["name"], "message": e.get("message", "")[:200]} for e in items[-30:]]

    async def logs(self, pod, namespace, tail):
        return (await self._run("logs", pod, "-n", namespace, f"--tail={tail}"))[-6000:]

    async def rollout_restart(self, deployment, namespace):
        return {"output": await self._run("rollout", "restart", f"deployment/{deployment}", "-n", namespace)}

    async def scale(self, deployment, namespace, replicas):
        return {"output": await self._run("scale", f"deployment/{deployment}", f"--replicas={replicas}", "-n", namespace)}
