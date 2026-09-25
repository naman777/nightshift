"""Adapters that expose a simulated World through the same Backend protocols the live servers use."""
from __future__ import annotations

from typing import Any

from mcp_servers.metrics.backend import CATALOGUE
from mcp_servers.code.backend import SandboxError

from .world import World


class SimMetrics:
    def __init__(self, w: World):
        self.w = w

    def now(self) -> float:
        return self.w.now()

    def catalogue(self):
        return CATALOGUE

    async def query_range(self, query, start, end, step):
        return self.w.query_range(query, start, end, step)


class SimLogs:
    def __init__(self, w: World):
        self.w = w

    def now(self) -> float:
        return self.w.now()

    async def search(self, service, contains, level, start, end, limit):
        return self.w.search_logs(service, contains, level, start, end, limit)


class SimChanges:
    def __init__(self, w: World):
        self.w = w

    def now(self) -> float:
        return self.w.now()

    async def deploys(self, since, service):
        return [{"ts": int(c.ts), "service": c.service, "sha": c.sha, "author": c.author, "message": c.message}
                for c in self.w.commits if c.kind == "deploy" and c.ts >= since and (not service or c.service == service)]

    async def config_commits(self, since, path):
        return [{"sha": c.sha, "ts": int(c.ts), "author": c.author, "message": c.message, "files": c.files}
                for c in self.w.commits if c.kind in ("config", "flag") and c.ts >= since
                and (not path or any(path in f for f in c.files))]

    async def commit(self, sha):
        c = self.w.find_commit(sha)
        if not c:
            return None
        return {"sha": c.sha, "ts": int(c.ts), "author": c.author, "message": c.message, "diff": c.diff}


class SimCode:
    def __init__(self, w: World):
        self.w = w

    async def read_file(self, path, start, end):
        if ".." in path or path.startswith("/"):
            raise SandboxError(f"path escapes sandbox: {path}")
        src = self.w.code.get(path)
        if src is None:
            return {"error": f"no such file: {path}"}
        lines = src.splitlines()
        s, e = max(1, start), min(len(lines), end)
        return {"path": path, "start": s, "end": e, "total_lines": len(lines),
                "content": "\n".join(f"{i}: {lines[i - 1]}" for i in range(s, e + 1))}

    async def grep(self, pattern, path, limit):
        import re

        rx = re.compile(pattern)
        out: list[dict[str, Any]] = []
        for p, src in sorted(self.w.code.items()):
            if path and not p.startswith(path):
                continue
            for i, line in enumerate(src.splitlines(), 1):
                if rx.search(line):
                    out.append({"path": p, "line": i, "text": line.strip()[:200]})
        return out[:limit]

    async def run_tests(self, target):
        return dict(self.w.test_result)


class SimRuntime:
    def __init__(self, w: World):
        self.w = w

    async def _rec(self, action: str, **kw: Any) -> dict[str, Any]:
        self.w.actions.append({"action": action, **kw})
        return {"ok": True, "output": f"{action} applied (simulated)"}

    async def restart(self, service, replica):
        return await self._rec("restart_replica", service=service, replica=replica)

    async def rollback_deploy(self, service, sha):
        return await self._rec("rollback_deploy", service=service, sha=sha)

    async def revert_commit(self, sha):
        return await self._rec("revert_commit", sha=sha)

    async def set_flag(self, flag, value):
        return await self._rec("set_flag", flag=flag, value=value)

    async def set_config(self, service, key, value):
        return await self._rec("set_config", service=service, key=key, value=value)

    async def scale(self, service, replicas):
        return await self._rec("scale", service=service, replicas=replicas)

    async def destructive(self, action, target):
        return await self._rec(action, target=target)


def sim_backends(w: World) -> dict[str, Any]:
    return {"metrics": SimMetrics(w), "logs": SimLogs(w), "changes": SimChanges(w), "code": SimCode(w), "runtime": SimRuntime(w)}
