"""Builds an AgentRuntime for an alert from environment config (worker, gateway and CLI all share this).

NIGHTSHIFT_BACKEND=sim   -> tools read a simulated World built from the alert's `scenario` label (no docker, no keys needed)
NIGHTSHIFT_BACKEND=live  -> tools talk to Prometheus / Loki / git / docker
"""
from __future__ import annotations

import asyncio
import os
from functools import lru_cache

from agents.core.db import Database
from agents.core.evidence import EvidenceBoard
from agents.core.llm import make_llm
from agents.core.mcp_client import InProcessClient
from agents.core.memory import IncidentMemory
from agents.runtime import AgentRuntime
from agents.scripted import heuristic_responder
from mcp_servers.changes.backend import GitChangesBackend
from mcp_servers.code.backend import FsCodeBackend
from mcp_servers.logs.backend import LokiBackend
from mcp_servers.metrics.backend import PrometheusBackend
from mcp_servers.policy import PolicyEngine
from mcp_servers.registry import build_servers
from mcp_servers.runtime.backend import DockerRuntimeBackend


class PacedLLM:
    """Adds latency to each model call (demo only). Wraps any LLM; the offline reference policy is otherwise instantaneous."""

    def __init__(self, inner, delay_s: float):
        self.inner, self.delay_s = inner, delay_s

    async def complete(self, *args, **kwargs):
        await asyncio.sleep(self.delay_s)
        return await self.inner.complete(*args, **kwargs)


@lru_cache(maxsize=1)
def shared_db() -> Database:
    return Database(os.environ.get("NIGHTSHIFT_DB_URL", "sqlite:///nightshift.db"))


@lru_cache(maxsize=64)
def _world(scenario_id: str):
    from bench.scenario import build_world, load_all, load_hard

    s = next(x for x in [*load_all(), *load_hard()] if x.id == scenario_id)
    return build_world(s)[0]


def live_backends() -> dict:
    return {"metrics": PrometheusBackend(os.environ.get("PROMETHEUS_URL", "http://localhost:9090")),
            "logs": LokiBackend(os.environ.get("LOKI_URL", "http://localhost:3100")),
            "changes": GitChangesBackend(os.environ.get("CONFIG_REPO", "target/config"), os.environ.get("DEPLOY_LOG", "target/deploys.jsonl")),
            "code": FsCodeBackend(os.environ.get("CODE_ROOT", "target/orders-svc")),
            "runtime": DockerRuntimeBackend()}


def build_runtime(labels: dict[str, str] | None = None, benchmark_mode: bool = False,
                  db: Database | None = None) -> tuple[AgentRuntime, PolicyEngine]:
    labels = labels or {}
    db = db or shared_db()
    if os.environ.get("NIGHTSHIFT_BACKEND", "sim") == "sim" and labels.get("scenario"):
        from bench.sim import sim_backends

        backends = sim_backends(_world(labels["scenario"]))
    else:
        backends = live_backends()
    policy = PolicyEngine(db, benchmark_mode=benchmark_mode)
    client = InProcessClient(build_servers(backends), policy)
    provider = labels.get("llm_provider") or os.environ.get("NIGHTSHIFT_LLM_PROVIDER", "mock")
    llm = make_llm(provider, responder=heuristic_responder)
    if labels.get("pace"):  # demo pacing for the instant offline policy, so the audience can watch the agents work
        llm = PacedLLM(llm, float(labels["pace"]))
    model = labels.get("llm_model")
    board = EvidenceBoard(db)
    rt = AgentRuntime(llm=llm, client=client, board=board, on_step=lambda st: board.record_step(st.incident_id, st),
                      commander_model=model or os.environ.get("NIGHTSHIFT_COMMANDER_MODEL", "mock-strong"),
                      specialist_model=model or os.environ.get("NIGHTSHIFT_SPECIALIST_MODEL", "mock-cheap"),
                      budget_usd=float(os.environ.get("NIGHTSHIFT_INCIDENT_BUDGET_USD", "1.0")),
                      memory=IncidentMemory(db) if os.environ.get("NIGHTSHIFT_MEMORY", "1") == "1" else None, memory_write=True)
    return rt, policy
