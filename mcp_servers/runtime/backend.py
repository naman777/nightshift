"""Runtime backend: the only code that mutates infrastructure. Reached only through the policy layer."""
from __future__ import annotations

import asyncio
import json
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
        try:
            out, _ = await proc.communicate()
        except asyncio.CancelledError:
            proc.kill()  # never leave an orphaned docker/git process running after a timeout or cancellation
            raise
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


class SystemdRuntimeBackend(DockerRuntimeBackend):
    """Plain Linux host (EC2) with services under systemd. Only `restart` is supported; every other action is refused so a proposal
    for it can be approved but never silently mutates the host. `NIGHTSHIFT_SYSTEMD_UNITS` maps a service name to its unit,
    e.g. {"lb": "lb.service"}."""

    def __init__(self, units: dict[str, str] | None = None):
        super().__init__()
        self.units = units if units is not None else json.loads(os.environ.get("NIGHTSHIFT_SYSTEMD_UNITS", "{}"))

    def _refuse(self, what: str) -> dict[str, Any]:
        return {"ok": False, "output": f"{what}: not supported by the systemd backend; do it manually"}

    async def restart(self, service, replica):
        unit = self.units.get(service)
        if not unit:
            return {"ok": False, "output": f"no systemd unit configured for service {service!r}"}
        return await self._run("sudo", "-n", "systemctl", "restart", unit)

    async def rollback_deploy(self, service, sha):
        return self._refuse(f"rollback_deploy {service} {sha}")

    async def revert_commit(self, sha):
        return self._refuse(f"revert_commit {sha}")

    async def set_flag(self, flag, value):
        return self._refuse(f"set_flag {flag}")

    async def set_config(self, service, key, value):
        return self._refuse(f"set_config {service}.{key}")

    async def scale(self, service, replicas):
        return self._refuse(f"scale {service}")
