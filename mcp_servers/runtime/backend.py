"""Runtime backend: the only code that mutates infrastructure. Reached only through the policy layer."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any, Protocol


class RuntimeBackend(Protocol):
    async def restart(self, service: str, replica: str | None) -> dict[str, Any]: ...
    async def rollback_deploy(self, service: str, sha: str) -> dict[str, Any]: ...
    async def revert_commit(self, sha: str) -> dict[str, Any]: ...
    async def set_flag(self, flag: str, value: str) -> dict[str, Any]: ...
    async def set_config(self, service: str, key: str, value: str) -> dict[str, Any]: ...
    async def scale(self, service: str, replicas: int) -> dict[str, Any]: ...
    async def destructive(self, action: str, target: str) -> dict[str, Any]: ...


class DockerRuntimeBackend:
    def __init__(self, project: str = "nightshift", config_repo: str = "target/config"):
        self.project, self.config_repo = project, Path(config_repo)

    async def _run(self, *cmd: str) -> dict[str, Any]:
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        out, _ = await proc.communicate()
        return {"ok": proc.returncode == 0, "output": out.decode(errors="replace")[-1000:]}

    async def restart(self, service, replica):
        return await self._run("docker", "restart", f"{self.project}-{replica or service}")

    async def rollback_deploy(self, service, sha):
        return await self._run("python", "-m", "chaos.cli", "deploy", service, "--sha", sha)

    async def revert_commit(self, sha):
        gd = os.environ.get("CONFIG_GIT_DIR", "")
        base = ["git", f"--git-dir={gd}", f"--work-tree={self.config_repo}"] if gd else ["git", "-C", str(self.config_repo)]
        return await self._run(*base, "revert", "--no-edit", sha)

    async def set_flag(self, flag, value):
        return await self._run("python", "-m", "chaos.cli", "flag", flag, value)

    async def set_config(self, service, key, value):
        return await self._run("python", "-m", "chaos.cli", "config", service, key, value)

    async def scale(self, service, replicas):
        return await self._run("docker", "compose", "-p", self.project, "up", "-d", "--scale", f"{service}={replicas}", service)

    async def destructive(self, action, target):
        return {"ok": False, "output": f"{action} {target}: refused by backend; run manually"}
