"""One interface for starting investigations and delivering approvals; two implementations.

  TemporalRunner - durable (production / docker compose)
  LocalRunner    - asyncio tasks + in-process approval events (dev without Temporal; same steps, same trust gate)
"""
from __future__ import annotations

import asyncio
import os
from typing import Any, Protocol

from agents import pipeline, remediation
from agents.core.mcp_client import CallContext
from agents.core.models import Alert
from orchestrator.runtime_factory import build_runtime
from slackbot.notify import Notifier, default_notifier


class IncidentRunner(Protocol):
    async def start(self, alert: Alert, mode: str = "multi") -> tuple[str, bool]: ...  # (incident_id, newly_started)
    async def approve(self, incident_id: str, user: str, confirmation: str = "", reason: str = "") -> None: ...
    async def reject(self, incident_id: str, user: str) -> None: ...


def workflow_id(fingerprint: str) -> str:
    return f"inv-{fingerprint}"


class TemporalRunner:
    def __init__(self, client: Any):
        self.client = client

    @classmethod
    async def connect(cls, address: str | None = None) -> "TemporalRunner":
        from temporalio.client import Client

        return cls(await Client.connect(address or os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")))

    async def start(self, alert: Alert, mode: str = "multi") -> tuple[str, bool]:
        from temporalio.common import WorkflowIDConflictPolicy

        from orchestrator.worker import TASK_QUEUE
        from orchestrator.workflows import InvestigationWorkflow

        wid = workflow_id(alert.fingerprint)
        try:
            await self.client.get_workflow_handle(wid).describe()
            existing = True
        except Exception:
            existing = False
        await self.client.start_workflow(InvestigationWorkflow.run, args=[alert.model_dump(mode="json"), mode, float(os.environ.get("NIGHTSHIFT_INCIDENT_BUDGET_USD", "1.0"))], id=wid,
                                         task_queue=TASK_QUEUE, id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING)
        return f"inc-{alert.fingerprint}", not existing

    async def approve(self, incident_id: str, user: str, confirmation: str = "", reason: str = "") -> None:
        from orchestrator.workflows import RemediationWorkflow

        await self.client.get_workflow_handle(f"rem-{incident_id.removeprefix('inc-')}").signal(RemediationWorkflow.approve, args=[user, confirmation, reason])

    async def reject(self, incident_id: str, user: str) -> None:
        from orchestrator.workflows import RemediationWorkflow

        await self.client.get_workflow_handle(f"rem-{incident_id.removeprefix('inc-')}").signal(RemediationWorkflow.reject, args=[user])


class LocalRunner:
    """Same steps and same trust gate as the Temporal path, without durability."""

    def __init__(self, notifier: Notifier | None = None, approval_timeout_s: float = 1800.0, db: Any = None):
        self.db = db
        self.notifier = notifier or default_notifier()
        self.timeout = approval_timeout_s
        self.tasks: dict[str, asyncio.Task] = {}
        self.decisions: dict[str, asyncio.Future] = {}
        self.results: dict[str, dict] = {}

    async def start(self, alert: Alert, mode: str = "multi") -> tuple[str, bool]:
        iid = f"inc-{alert.fingerprint}"
        if iid in self.tasks and not self.tasks[iid].done():
            return iid, False  # dedupe: attach to the running investigation
        self.tasks[iid] = asyncio.create_task(self._run(alert, mode, iid))
        return iid, True

    async def wait(self, incident_id: str) -> dict:
        await self.tasks[incident_id]
        return self.results[incident_id]

    async def _run(self, alert: Alert, mode: str, iid: str) -> None:
        rt, _ = build_runtime(alert.labels, db=self.db)
        result = await pipeline.LocalOrchestrator(rt).investigate(alert, mode)
        report, action = result.report.model_dump(mode="json"), result.action.model_dump(mode="json") if result.action else None
        await self.notifier.post_report(iid, report, action)
        outcome: dict[str, Any] = {"status": "no_action_needed"}
        if action and action["tier"] != "read_only":
            fut = self.decisions[iid] = asyncio.get_running_loop().create_future()
            rt.board.set_status(iid, "awaiting_approval", result.report)
            await self.notifier.request_approval(iid, report, action)
            try:
                decision = await asyncio.wait_for(fut, self.timeout)
            except asyncio.TimeoutError:
                decision = {"approved": False}
            if decision["approved"]:
                ctx = CallContext(incident_id=iid, agent="remediation", approved_by=decision["user"], confirmation=decision["confirmation"],
                                  reason=decision["reason"], evidence_ids=result.report.evidence)
                res = await remediation.execute(rt.client, result.action, ctx)
                await self.notifier.post_outcome(iid, f"executed {action['type']}: {res.content[:200]}")
                outcome = {"status": "blocked" if res.blocked else "resolved", "content": res.content}
            else:
                outcome = {"status": "rejected"}
            rt.board.set_status(iid, outcome["status"], result.report)
        self.results[iid] = {"incident_id": iid, "report": report, "action": action, "outcome": outcome}

    async def approve(self, incident_id: str, user: str, confirmation: str = "", reason: str = "") -> None:
        fut = self.decisions.get(incident_id)
        if fut and not fut.done():
            fut.set_result({"approved": True, "user": user, "confirmation": confirmation, "reason": reason})

    async def reject(self, incident_id: str, user: str) -> None:
        fut = self.decisions.get(incident_id)
        if fut and not fut.done():
            fut.set_result({"approved": False, "user": user})


class LazyTemporalRunner:
    """Connects on first use so the gateway can start before Temporal is up (compose start-up ordering)."""

    def __init__(self, address: str | None = None):
        self.address, self._inner = address, None

    async def _get(self) -> TemporalRunner:
        if self._inner is None:
            self._inner = await TemporalRunner.connect(self.address)
        return self._inner

    async def start(self, alert: Alert, mode: str = "multi") -> tuple[str, bool]:
        return await (await self._get()).start(alert, mode)

    async def approve(self, incident_id: str, user: str, confirmation: str = "", reason: str = "") -> None:
        await (await self._get()).approve(incident_id, user, confirmation, reason)

    async def reject(self, incident_id: str, user: str) -> None:
        await (await self._get()).reject(incident_id, user)


def default_runner(db: Any = None) -> IncidentRunner:
    return LazyTemporalRunner() if os.environ.get("NIGHTSHIFT_ORCH", "local") == "temporal" else LocalRunner(db=db)
