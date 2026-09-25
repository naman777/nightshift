"""Everything an agent step needs, in one place (so Temporal activities can rebuild it from env in the worker)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agents.core.evidence import EvidenceBoard
from agents.core.llm import LLM
from agents.core.loop import Budget, StepSink
from agents.core.mcp_client import MCPClient
from agents.prompts import LATEST


@dataclass
class AgentRuntime:
    llm: LLM
    client: MCPClient
    board: EvidenceBoard
    commander_model: str = "mock-strong"
    specialist_model: str = "mock-cheap"
    prompt_version: str = LATEST
    on_step: StepSink | None = None
    require_citations: bool = True
    budget_usd: float = 1.0
    max_rounds: int = 3
    single_agent_tool_budget: int = 10
    extras: dict[str, Any] = field(default_factory=dict)
