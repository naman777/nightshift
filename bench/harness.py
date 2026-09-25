"""Wires a simulated World into a full agent runtime (used by the benchmark, tests and the dashboard demo)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agents.core.db import Database
from agents.core.evidence import EvidenceBoard
from agents.core.llm import LLM
from agents.core.memory import IncidentMemory
from agents.core.mcp_client import InProcessClient
from agents.runtime import AgentRuntime
from agents.scripted import make_mock_llm
from bench.sim import World, sim_backends
from mcp_servers.policy import PolicyEngine
from mcp_servers.registry import build_servers


@dataclass(frozen=True)
class Config:
    name: str
    mode: str = "multi"  # multi | single
    commander_model: str = "mock-strong"
    specialist_model: str = "mock-strong"
    require_citations: bool = True
    memory: bool = False  # give the commander verified similar past incidents


CONFIGS: dict[str, Config] = {
    "single": Config("single", mode="single"),
    "multi": Config("multi"),
    "multi-routed": Config("multi-routed", specialist_model="mock-cheap"),
    "multi-nocite": Config("multi-nocite", require_citations=False),
    "multi-memory": Config("multi-memory", memory=True),
}


def make_runtime(world: World, config: Config, db: Database | None = None, llm: LLM | None = None, benchmark_mode: bool = True,
                 prompt_version: str | None = None, on_step: Any = None, memory: IncidentMemory | None = None,
                 memory_exclude: str | None = None) -> tuple[AgentRuntime, PolicyEngine]:
    db = db or Database.memory()
    board = EvidenceBoard(db)
    policy = PolicyEngine(db, benchmark_mode=benchmark_mode, dry_run=False)
    client = InProcessClient(build_servers(sim_backends(world)), policy)
    kw = {"prompt_version": prompt_version} if prompt_version else {}
    rt = AgentRuntime(llm=llm or make_mock_llm(), client=client, board=board, commander_model=config.commander_model,
                      specialist_model=config.specialist_model, require_citations=config.require_citations, on_step=on_step,
                      memory=memory if config.memory else None, memory_exclude=memory_exclude, **kw)
    return rt, policy
