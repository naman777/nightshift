"""Remediation: turn a root-cause report into the safest effective action, then execute it (only after the trust gate)."""
from __future__ import annotations

from typing import Any

from agents.commander import ACTION_TIERS
from agents.core.loop import AgentLoop, Budget
from agents.core.mcp_client import CallContext, MCPClient, ToolResult
from agents.core.models import Alert, ProposedAction, RootCauseReport, Tier
from agents.prompts import load
from agents.runtime import AgentRuntime

ACTION_SCHEMA = {
    "name": "submit_action", "description": "Submit the single safest effective remediation.",
    "input_schema": {"type": "object", "required": ["type", "reason"], "properties": {
        "type": {"type": "string", "enum": sorted(ACTION_TIERS)},
        "target": {"type": "string", "description": "sha, service, replica or flag name depending on type"},
        "params": {"type": "object"}, "reason": {"type": "string"}}},
}


def parse_action(args: dict) -> tuple[ProposedAction | None, str]:
    typ = args.get("type", "")
    if typ not in ACTION_TIERS:
        return None, f"unknown action type {typ!r}; choose one of {sorted(ACTION_TIERS)}"
    params = args.get("params") or {}
    if typ == "scale":
        try:
            if int(params.get("replicas", 1)) < 1:
                return None, "scale needs params.replicas >= 1 (scale_to_zero is a separate destructive action)"
        except (TypeError, ValueError):
            return None, "params.replicas must be an integer"
    return ProposedAction(type=typ, target=str(args.get("target", "")), params=params, tier=ACTION_TIERS[typ]), ""


def config_key_is_grounded(rt: AgentRuntime, incident_id: str, report: RootCauseReport, key: str) -> bool:
    """A set_config proposal is only credible if the key shows up in something the investigation actually saw (a claim, the report, or a
    stored tool result such as a config diff). Models invent plausible-looking keys (`stats_client_read_timeout`); those must not reach the approval queue."""
    if not key:
        return False
    hay = [report.root_cause, *report.evidence, *report.claims]
    for row in rt.board.list(incident_id):
        hay.append(row.claim)
        art = rt.board.get_artifact(row.evidence_result_ref) if row.evidence_result_ref else None
        if art:
            hay.append(str(art.get("content", "")))
    return any(key in h for h in hay)


async def propose(rt: AgentRuntime, alert: Alert, incident_id: str, report: RootCauseReport) -> ProposedAction:
    fallback = report.proposed_action or ProposedAction(type="escalate", target="on-call", tier=Tier.READ_ONLY)
    loop = AgentLoop("remediation", rt.llm, rt.commander_model, load("remediation", rt.prompt_version), None,
                     budget=Budget(max_tool_calls=1, max_tokens=12_000), board=rt.board, incident_id=incident_id, on_step=rt.on_step,
                     final_schema=ACTION_SCHEMA, final_handler=parse_action)
    await loop.run("Choose the safest effective action.", f"Root-cause report:\n{report.model_dump_json(indent=1)}")
    action: ProposedAction = loop.output or fallback
    if action.type == "set_config" and not config_key_is_grounded(rt, incident_id, report, str(action.params.get("key", ""))):
        action = ProposedAction(type="escalate", target="on-call", tier=Tier.READ_ONLY,
                                params={"reason": f"proposed set_config key {action.params.get('key')!r} appears nowhere in the evidence; not proposing an invented setting"})
    # The tier comes from the policy table, never from the model.
    return action.model_copy(update={"tier": ACTION_TIERS.get(action.type, Tier.DESTRUCTIVE)})


def to_tool_call(action: ProposedAction) -> tuple[str, dict[str, Any]] | None:
    p = action.params
    match action.type:
        case "revert_commit":
            return "runtime__revert_commit", {"sha": action.target}
        case "rollback_deploy":
            return "runtime__rollback_deploy", {"service": action.target, "sha": p.get("sha", "previous")}
        case "restart_replica":
            return "runtime__restart_replica", {"service": p.get("service", action.target), "replica": action.target}
        case "set_flag":
            return "runtime__set_flag", {"flag": action.target, "value": str(p.get("value", "false"))}
        case "set_config":
            return "runtime__set_config", {"service": action.target, "key": p.get("key", ""), "value": str(p.get("value", ""))}
        case "scale":
            return "runtime__scale", {"service": action.target, "replicas": int(p.get("replicas", 1))}
        case "scale_to_zero":
            return "runtime__scale_to_zero", {"service": action.target}
        case "restart_postgres":
            return "runtime__restart_postgres", {}
        case "delete_data":
            return "runtime__delete_data", {"table": action.target}
    return None  # escalate / none: nothing to execute


async def execute(client: MCPClient, action: ProposedAction, ctx: CallContext) -> ToolResult:
    call = to_tool_call(action)
    if call is None:
        return ToolResult(f"no infrastructure action needed for '{action.type}'; escalation recorded")
    return await client.call_tool(call[0], call[1], ctx)
