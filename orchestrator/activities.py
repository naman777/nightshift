"""Temporal activities. Every LLM call and tool call happens here, never in workflow code (which must be deterministic).

Each activity is a thin wrapper over agents.pipeline steps, so the in-process LocalOrchestrator and Temporal run identical logic.
Completed activities are never re-run on resume, so a crash mid-incident costs no duplicate LLM spend.
"""
from __future__ import annotations

import asyncio
import functools
from typing import Any

from temporalio import activity

from agents import pipeline, remediation
from agents.core.mcp_client import CallContext
from agents.core.models import Alert, ProposedAction, RootCauseReport
from orchestrator.runtime_factory import build_runtime
from slackbot.notify import default_notifier

_notifier = default_notifier()


def heartbeating(fn):
    """Heartbeat while an agent runs so a dead worker is detected in seconds (heartbeat_timeout), not after the full activity timeout."""
    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        async def beat():
            while True:
                activity.heartbeat()
                await asyncio.sleep(3)
        task = asyncio.create_task(beat())
        try:
            return await fn(*args, **kwargs)
        finally:
            task.cancel()
    return wrapper


def set_notifier(n) -> None:  # tests / worker bootstrap
    global _notifier
    _notifier = n


@activity.defn
async def open_incident(alert: dict, incident_id: str) -> None:
    rt, _ = build_runtime(alert.get("labels"))
    a = Alert(**alert)
    rt.board.open_incident(incident_id, a.fingerprint, a.model_dump_json())


@activity.defn
@heartbeating
async def plan_activity(alert: dict, incident_id: str) -> dict:
    rt, _ = build_runtime(alert.get("labels"))
    return await pipeline.step_plan(rt, alert, incident_id)


@activity.defn
@heartbeating
async def specialist_activity(alert: dict, incident_id: str, assignment: dict) -> dict:
    rt, _ = build_runtime(alert.get("labels"))
    return await pipeline.step_specialist(rt, incident_id, assignment)


@activity.defn
@heartbeating
async def converge_activity(alert: dict, incident_id: str, plan: dict, round_no: int, findings: list[dict]) -> dict:
    rt, _ = build_runtime(alert.get("labels"))
    return await pipeline.step_converge(rt, alert, incident_id, plan, round_no, findings)


@activity.defn
@heartbeating
async def single_agent_activity(alert: dict, incident_id: str) -> dict:
    rt, _ = build_runtime(alert.get("labels"))
    return await pipeline.step_single(rt, alert, incident_id)


@activity.defn
@heartbeating
async def propose_activity(alert: dict, incident_id: str, report: dict) -> dict:
    rt, _ = build_runtime(alert.get("labels"))
    return await pipeline.step_propose(rt, alert, incident_id, report)


@activity.defn
async def record_report_activity(alert: dict, incident_id: str, report: dict, status: str) -> None:
    rt, _ = build_runtime(alert.get("labels"))
    rt.board.set_status(incident_id, status, RootCauseReport(**report))


@activity.defn
async def notify_report_activity(incident_id: str, report: dict, action: dict | None) -> None:
    await _notifier.post_report(incident_id, report, action)


@activity.defn
async def request_approval_activity(incident_id: str, report: dict, action: dict) -> None:
    await _notifier.request_approval(incident_id, report, action)


@activity.defn
@heartbeating
async def execute_action_activity(alert: dict, incident_id: str, action: dict, approved_by: str, confirmation: str, reason: str,
                                  evidence_ids: list[str]) -> dict[str, Any]:
    rt, policy = build_runtime(alert.get("labels"))
    ctx = CallContext(incident_id=incident_id, agent="remediation", approved_by=approved_by, confirmation=confirmation,
                      reason=reason, evidence_ids=evidence_ids)
    res = await remediation.execute(rt.client, ProposedAction(**action), ctx)
    text = f"{'Blocked' if res.blocked else 'Executed'} `{action['type']}` for {incident_id}: {res.content[:300]}"
    await _notifier.post_outcome(incident_id, text)
    return {"blocked": res.blocked, "dry_run": res.dry_run, "error": res.is_error, "content": res.content}


@activity.defn
async def set_status_activity(alert: dict, incident_id: str, status: str) -> None:
    rt, _ = build_runtime(alert.get("labels"))
    row = rt.board.get_incident(incident_id)
    report = RootCauseReport.model_validate_json(row["report_json"]) if row and row["report_json"] else None
    rt.board.set_status(incident_id, status, report)


ALL = [open_incident, plan_activity, specialist_activity, converge_activity, single_agent_activity, propose_activity,
       record_report_activity, notify_report_activity, request_approval_activity, execute_action_activity, set_status_activity]
