from __future__ import annotations

from typing import Any

from ..base import Server, schema
from .backend import ChangesBackend


def build(backend: ChangesBackend) -> Server:
    srv = Server("changes", backend)

    @srv.tool("recent_deploys", "List service deploys (sha, author, message, timestamp) in the last N minutes. Answers 'what shipped?'.",
              schema({"since_minutes": ("number", "look-back, default 120"), "service": ("string", "optional service filter")}))
    async def recent_deploys(b: ChangesBackend, since_minutes: float = 120, service: str | None = None) -> Any:
        now = b.now()
        rows = await b.deploys(now - since_minutes * 60, service)
        return {"now": int(now), "deploys": sorted(rows, key=lambda r: r["ts"])}

    @srv.tool("config_diff", "List config / feature-flag commits in the last N minutes with changed files and the actual diff. "
              "Answers 'what config changed?'.",
              schema({"since_minutes": ("number", "look-back, default 120"), "path": ("string", "optional path filter, e.g. config/lb.yaml")}))
    async def config_diff(b: ChangesBackend, since_minutes: float = 120, path: str | None = None) -> Any:
        now = b.now()
        commits = await b.config_commits(now - since_minutes * 60, path)
        out = []
        for c in sorted(commits, key=lambda c: c["ts"]):
            full = await b.commit(c["sha"])
            out.append({**c, "diff": (full or {}).get("diff", "")})
        return {"now": int(now), "commits": out}

    @srv.tool("commit_diff", "Show a single commit's metadata and full diff.", schema({"sha": ("string", "commit sha")}, ["sha"]))
    async def commit_diff(b: ChangesBackend, sha: str) -> Any:
        c = await b.commit(sha)
        return c if c else {"error": f"unknown commit {sha}"}

    return srv
