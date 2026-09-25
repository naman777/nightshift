"""Proactive mode: review every deploy / config / flag change BEFORE an alert fires (stretch goal).

A CI/CD hook posts the change to the gateway (`POST /webhook/change`); a reviewer agent reads the diff and rates its risk. Medium/high changes
are flagged to Slack with cited reasons, so the on-call engineer knows what to suspect if the pager goes off ten minutes later.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from agents.core.loop import AgentLoop, Budget
from agents.core.models import Usage
from agents.prompts import load
from agents.runtime import AgentRuntime

TOOLS = ["changes__commit_diff", "code__read_file", "code__grep"]
RISK_SCHEMA = {
    "name": "submit_risk", "description": "Submit the risk rating for the change; each reason cites the tool call that showed it.",
    "input_schema": {"type": "object", "required": ["risk", "reasons"], "properties": {
        "risk": {"type": "string", "enum": ["low", "medium", "high"]},
        "reasons": {"type": "array", "items": {"type": "object", "required": ["text", "tool_call_ref"], "properties": {
            "text": {"type": "string"}, "tool_call_ref": {"type": "string"}}}}}},
}


class ChangeRisk(BaseModel):
    sha: str
    service: str = ""
    risk: str
    reasons: list[str] = Field(default_factory=list)
    queries: list[str] = Field(default_factory=list)  # the tool calls the reasons cite
    usage: Usage = Field(default_factory=Usage)

    @property
    def flagged(self) -> bool:
        return self.risk in ("medium", "high")


async def review_change(rt: AgentRuntime, change: dict[str, Any], incident_id: str | None = None) -> ChangeRisk:
    sha = change["sha"]
    iid = incident_id or f"review-{sha}"
    rt.board.open_incident(iid, f"review-{sha}", "{}")
    holder: dict[str, Any] = {}

    def handler(args: dict) -> tuple[ChangeRisk | None, str]:
        calls = holder["loop"]._last_state.calls
        reasons = args.get("reasons") or []
        bad = [r.get("tool_call_ref") for r in reasons if r.get("tool_call_ref") not in calls]
        if bad:
            return None, f"reasons cite unknown tool calls {bad}; valid: {sorted(calls)}"
        return ChangeRisk(sha=sha, service=change.get("service", ""), risk=args["risk"], reasons=[r["text"] for r in reasons],
                          queries=[calls[r["tool_call_ref"]].query for r in reasons]), ""

    loop = holder["loop"] = AgentLoop("reviewer", rt.llm, rt.specialist_model, load("reviewer", rt.prompt_version), rt.client,
                                      allowed_tools=TOOLS, budget=Budget(max_tool_calls=4, max_tokens=40_000), board=rt.board,
                                      incident_id=iid, on_step=rt.on_step, final_schema=RISK_SCHEMA, final_handler=handler)
    finding = await loop.run(f"Review this change for incident risk: kind={change.get('kind', 'deploy')} service={change.get('service', '?')} "
                             f"sha={sha} message=\"{change.get('message', '')}\"")
    if loop.output is None:  # could not review: fail safe by flagging for a human
        return ChangeRisk(sha=sha, service=change.get("service", ""), risk="medium", reasons=["automated review inconclusive; needs a human look"],
                          usage=finding.usage)
    out: ChangeRisk = loop.output
    return out.model_copy(update={"usage": finding.usage})
