"""Typed domain models shared by agents, orchestrator, gateway and benchmark."""
from __future__ import annotations

import time
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class Tier(StrEnum):
    READ_ONLY = "read_only"
    REVERSIBLE = "reversible"
    DESTRUCTIVE = "destructive"


class Category(StrEnum):
    CONFIG_CHANGE = "config_change"
    BAD_DEPLOY = "bad_deploy"
    DEPENDENCY_LATENCY = "dependency_latency"
    DEPENDENCY_OUTAGE = "dependency_outage"
    RESOURCE_LEAK = "resource_leak"
    CONNECTION_EXHAUSTION = "connection_exhaustion"
    HEALTHCHECK_MISCONFIG = "healthcheck_misconfig"
    CAPACITY = "capacity"
    LOG_FLOOD = "log_flood"
    RESOURCE_CONTENTION = "resource_contention"
    UNKNOWN = "unknown"


class Alert(BaseModel):
    fingerprint: str
    name: str
    service: str
    severity: str = "critical"
    started_at: float = Field(default_factory=time.time)
    labels: dict[str, str] = Field(default_factory=dict)
    annotations: dict[str, str] = Field(default_factory=dict)


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    llm_calls: int = 0
    tool_calls: int = 0

    def add(self, other: "Usage") -> "Usage":
        return Usage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cost_usd=round(self.cost_usd + other.cost_usd, 6),
            llm_calls=self.llm_calls + other.llm_calls,
            tool_calls=self.tool_calls + other.tool_calls,
        )


class EvidenceRow(BaseModel):
    id: str = ""
    incident_id: str
    agent: str
    claim: str
    evidence_query: str
    evidence_result_ref: str = ""
    supports_hypothesis: str = ""
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    created_at: float = Field(default_factory=time.time)


class Hypothesis(BaseModel):
    id: str
    text: str
    service: str = ""
    category: Category = Category.UNKNOWN


class Assignment(BaseModel):
    agent: str  # metrics | logs | changes | code
    question: str
    hypothesis_ids: list[str] = Field(default_factory=list)


class ClaimIn(BaseModel):
    claim: str
    tool_call_ref: str = Field(description="id of the tool call that produced the evidence, e.g. 'call_2'")
    supports_hypothesis: str = ""
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class Finding(BaseModel):
    agent: str
    question: str
    summary: str
    status: str = "conclusive"  # conclusive | inconclusive
    evidence_ids: list[str] = Field(default_factory=list)
    usage: Usage = Field(default_factory=Usage)
    stop_reason: str = "submitted"  # submitted | budget | stalled | tokens | error


class ProposedAction(BaseModel):
    type: str  # revert_commit | rollback_deploy | restart_replica | set_flag | ...
    target: str = ""
    params: dict[str, Any] = Field(default_factory=dict)
    tier: Tier = Tier.REVERSIBLE


class RuledOut(BaseModel):
    hypothesis: str
    evidence: list[str] = Field(default_factory=list)


class RankedCause(BaseModel):
    root_cause: str
    service: str
    category: Category
    confidence: float


class RootCauseReport(BaseModel):
    root_cause: str
    service: str
    category: Category
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[str]
    ruled_out: list[RuledOut] = Field(default_factory=list)
    ranked: list[RankedCause] = Field(default_factory=list)
    proposed_action: ProposedAction | None = None
    claims: list[str] = Field(default_factory=list)
    usage: Usage = Field(default_factory=Usage)
    rounds: int = 1
    degraded: bool = False


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class Message(BaseModel):
    role: str  # user | assistant | tool
    content: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_call_id: str = ""
    tool_name: str = ""


class LLMResponse(BaseModel):
    text: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    usage: Usage = Field(default_factory=Usage)
    model: str = ""


class Step(BaseModel):
    """One observable unit inside an agent run (for tracing and the dashboard)."""

    agent: str
    kind: str  # llm | tool | finding
    name: str = ""
    detail: str = ""
    duration_ms: int = 0
    ts: float = Field(default_factory=time.time)
