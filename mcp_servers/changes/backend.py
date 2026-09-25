"""Change backend: deploy log (JSONL) + config git repo. `chaos/deploylog.py` writes what this reads."""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Protocol


class ChangesBackend(Protocol):
    def now(self) -> float: ...
    async def deploys(self, since: float, service: str | None) -> list[dict[str, Any]]: ...
    async def config_commits(self, since: float, path: str | None) -> list[dict[str, Any]]: ...
    async def commit(self, sha: str) -> dict[str, Any] | None: ...


class GitChangesBackend:
    def __init__(self, repo: str = "target/config", deploy_log: str = "target/deploys.jsonl", git_dir: str | None = None):
        self.repo, self.deploy_log = Path(repo), Path(deploy_log)
        self.git_dir = git_dir or os.environ.get("CONFIG_GIT_DIR", "")

    def now(self) -> float:
        return time.time()

    def _git(self, *args: str) -> str:
        base = ["git", f"--git-dir={self.git_dir}", f"--work-tree={self.repo}"] if self.git_dir else ["git", "-C", str(self.repo)]
        return subprocess.run([*base, *args], capture_output=True, text=True, timeout=15).stdout

    async def deploys(self, since, service):
        if not self.deploy_log.exists():
            return []
        rows = [json.loads(line) for line in self.deploy_log.read_text().splitlines() if line.strip()]
        return [r for r in rows if r["ts"] >= since and (not service or r["service"] == service)]

    async def config_commits(self, since, path):
        fmt = "%H|%ct|%an|%s"
        out = self._git("log", f"--since=@{int(since)}", f"--format={fmt}", "--", *([path] if path else []))
        commits = []
        for line in reversed(out.splitlines()):  # oldest first, so equal-second commits keep their order
            sha, ts, author, msg = line.split("|", 3)
            files = self._git("show", "--name-only", "--format=", sha).split()
            commits.append({"sha": sha[:8], "ts": int(ts), "author": author, "message": msg, "files": files})
        return commits

    async def commit(self, sha):
        diff = self._git("show", "--format=%H|%ct|%an|%s", sha)
        if not diff:
            return None
        head, _, body = diff.partition("\n")
        h, ts, author, msg = head.split("|", 3)
        return {"sha": h[:8], "ts": int(ts), "author": author, "message": msg, "diff": body[:6000]}
