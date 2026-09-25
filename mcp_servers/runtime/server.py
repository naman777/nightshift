from __future__ import annotations

from typing import Any

from agents.core.models import Tier

from ..base import Server, schema
from .backend import RuntimeBackend

R = Tier.REVERSIBLE
D = Tier.DESTRUCTIVE


def build(backend: RuntimeBackend) -> Server:
    srv = Server("runtime", backend)

    @srv.tool("revert_commit", "Revert a config/flag commit in the config repo and reload services. Reversible.",
              schema({"sha": ("string", "commit sha to revert")}, ["sha"]), R)
    async def revert_commit(b: RuntimeBackend, sha: str) -> Any:
        return await b.revert_commit(sha)

    @srv.tool("rollback_deploy", "Roll a service back to a previous build sha. Reversible.",
              schema({"service": ("string", ""), "sha": ("string", "build sha to roll back to")}, ["service", "sha"]), R)
    async def rollback_deploy(b: RuntimeBackend, service: str, sha: str) -> Any:
        return await b.rollback_deploy(service, sha)

    @srv.tool("restart_replica", "Restart ONE replica of a service. Reversible.",
              schema({"service": ("string", ""), "replica": ("string", "replica name, e.g. orders-svc-2")}, ["service"]), R)
    async def restart_replica(b: RuntimeBackend, service: str, replica: str | None = None) -> Any:
        return await b.restart(service, replica)

    @srv.tool("set_flag", "Set a feature flag (committed to the config repo). Reversible.",
              schema({"flag": ("string", ""), "value": ("string", "true|false")}, ["flag", "value"]), R)
    async def set_flag(b: RuntimeBackend, flag: str, value: str) -> Any:
        return await b.set_flag(flag, value)

    @srv.tool("set_config", "Set a service config key (committed to the config repo). Reversible.",
              schema({"service": ("string", ""), "key": ("string", ""), "value": ("string", "")}, ["service", "key", "value"]), R)
    async def set_config(b: RuntimeBackend, service: str, key: str, value: str) -> Any:
        return await b.set_config(service, key, value)

    @srv.tool("scale", "Scale a service to N (>=1) replicas. Reversible.",
              schema({"service": ("string", ""), "replicas": ("number", "target replica count, >= 1")}, ["service", "replicas"]), R)
    async def scale(b: RuntimeBackend, service: str, replicas: int) -> Any:
        if int(replicas) < 1:
            return {"ok": False, "output": "use scale_to_zero (destructive) for zero replicas"}
        return await b.scale(service, int(replicas))

    @srv.tool("scale_to_zero", "Stop all replicas of a service. DESTRUCTIVE: typed confirmation required.",
              schema({"service": ("string", "")}, ["service"]), D)
    async def scale_to_zero(b: RuntimeBackend, service: str) -> Any:
        return await b.destructive("scale_to_zero", service)

    @srv.tool("restart_postgres", "Restart the database. DESTRUCTIVE: typed confirmation required.", schema({}), D)
    async def restart_postgres(b: RuntimeBackend) -> Any:
        return await b.destructive("restart_postgres", "postgres")

    @srv.tool("delete_data", "Delete data from a table. DESTRUCTIVE: typed confirmation required.",
              schema({"table": ("string", "")}, ["table"]), D)
    async def delete_data(b: RuntimeBackend, table: str) -> Any:
        return await b.destructive("delete_data", table)

    return srv
