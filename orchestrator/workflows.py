"""Durable workflows.

InvestigationWorkflow(alert): plan -> specialists in parallel (one activity each) -> converge, up to 3 rounds -> child RemediationWorkflow.
RemediationWorkflow: waits on a Slack/dashboard signal (approve / reject), 30-minute timeout defaults to reject.

Workflow id = alert fingerprint, so a re-fired alert attaches to the running investigation instead of starting a second one.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from orchestrator import activities as A

AGENT_TIMEOUT = timedelta(seconds=120)
RETRY = RetryPolicy(maximum_attempts=3, initial_interval=timedelta(seconds=1), backoff_coefficient=2.0)
APPROVAL_TIMEOUT = timedelta(minutes=30)
MAX_ROUNDS = 3


def _run(fn, *args):
    return workflow.execute_activity(fn, args=list(args), start_to_close_timeout=AGENT_TIMEOUT, heartbeat_timeout=timedelta(seconds=15),
                                     retry_policy=RETRY)


def _quick(fn, *args):
    return workflow.execute_activity(fn, args=list(args), start_to_close_timeout=timedelta(seconds=30), retry_policy=RETRY)


@dataclass
class Approval:
    user: str = ""
    confirmation: str = ""
    reason: str = ""


@workflow.defn
class RemediationWorkflow:
    def __init__(self) -> None:
        self._decision: str | None = None
        self._approval = Approval()

    @workflow.signal
    def approve(self, user: str, confirmation: str = "", reason: str = "") -> None:
        if self._decision is None:
            self._decision, self._approval = "approved", Approval(user, confirmation, reason)

    @workflow.signal
    def reject(self, user: str = "") -> None:
        if self._decision is None:
            self._decision = "rejected"

    @workflow.query
    def state(self) -> str:
        return self._decision or "waiting"

    @workflow.run
    async def run(self, alert: dict, incident_id: str, report: dict, action: dict) -> dict:
        if action["tier"] == "read_only":
            await _quick(A.set_status_activity, alert, incident_id, "escalated")
            return {"status": "no_action_needed", "action": action}
        await _quick(A.request_approval_activity, incident_id, report, action)
        await _quick(A.set_status_activity, alert, incident_id, "awaiting_approval")
        try:
            await workflow.wait_condition(lambda: self._decision is not None, timeout=APPROVAL_TIMEOUT)
        except asyncio.TimeoutError:
            self._decision = "rejected"  # silence is never consent
        if self._decision != "approved":
            await _quick(A.set_status_activity, alert, incident_id, "rejected")
            return {"status": "rejected", "action": action}
        result = await workflow.execute_activity(  # a write is NOT idempotent: never auto-retry it (a human decides after a failure)
            A.execute_action_activity, args=[alert, incident_id, action, self._approval.user, self._approval.confirmation,
                                             self._approval.reason, report.get("evidence", [])],
            start_to_close_timeout=AGENT_TIMEOUT, heartbeat_timeout=timedelta(seconds=15), retry_policy=RetryPolicy(maximum_attempts=1))
        status = "blocked" if result["blocked"] else "resolved"
        await _quick(A.set_status_activity, alert, incident_id, status)
        return {"status": status, "action": action, "result": result}


@workflow.defn
class InvestigationWorkflow:
    def __init__(self) -> None:
        self._stage = "starting"

    @workflow.query
    def stage(self) -> str:
        return self._stage

    @workflow.run
    async def run(self, alert: dict, mode: str = "multi", budget_usd: float = 1.0) -> dict:
        iid = f"inc-{alert['fingerprint']}"
        await _quick(A.open_incident, alert, iid)
        degraded = False
        if mode == "single":
            self._stage = "single-agent"
            report = await _run(A.single_agent_activity, alert, iid)
        else:
            self._stage = "planning"
            plan = await _run(A.plan_activity, alert, iid)
            spent = plan["usage"]["cost_usd"]
            assignments, report = plan["assignments"], None
            if spent >= budget_usd:  # cost ceiling hit by planning alone: degrade to the cheaper single-agent mode
                self._stage, degraded = "single-agent (cost ceiling)", True
                report = await _run(A.single_agent_activity, alert, iid)
            for rnd in range(1, MAX_ROUNDS + 1):
                if report is not None:
                    break
                self._stage = f"round-{rnd}"
                findings = await asyncio.gather(*[_run(A.specialist_activity, alert, iid, a) for a in assignments])
                spent += sum(f["usage"]["cost_usd"] for f in findings)
                force = spent >= budget_usd and rnd < MAX_ROUNDS  # ceiling hit mid-investigation: no more follow-up rounds
                degraded = degraded or force
                decision = await _run(A.converge_activity, alert, iid, plan, MAX_ROUNDS if force else rnd, list(findings))
                spent += decision["usage"]["cost_usd"]
                if decision["action"] == "report" and decision.get("report"):
                    report = decision["report"]
                    break
                assignments = decision["assignments"]
            if report is None:
                raise RuntimeError("commander never produced a report")
        report = {**report, "degraded": bool(report.get("degraded")) or degraded}
        action = await _run(A.propose_activity, alert, iid, report)
        await _quick(A.record_report_activity, alert, iid, report, "diagnosed")
        await _quick(A.notify_report_activity, iid, report, action)
        self._stage = "remediation"
        outcome = await workflow.execute_child_workflow(RemediationWorkflow.run, args=[alert, iid, report, action],
                                                        id=f"rem-{alert['fingerprint']}")
        self._stage = "done"
        return {"incident_id": iid, "report": report, "action": action, "outcome": outcome}
