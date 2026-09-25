"""The investigation as a sequence of small, JSON-in / JSON-out steps.

Both orchestrators drive the same steps:
  * orchestrator/workflows.py  - Temporal: each step is an activity (retries, timeouts, resume without repeated LLM spend)
  * LocalOrchestrator (below)  - in-process, checkpointing every step in the DB (used by the benchmark and tests)
"""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from agents import commander, remediation, single_agent, specialists
from agents.core.memory import signature_from_evidence
from agents.core.models import Alert, Assignment, Finding, ProposedAction, RootCauseReport, Usage
from agents.runtime import AgentRuntime


# -- individual steps (pure functions of their JSON input + the runtime) ---------------

async def step_plan(rt: AgentRuntime, alert: dict, incident_id: str) -> dict:
    p = await commander.plan(rt, Alert(**alert), incident_id)
    return p.model_dump(mode="json")


async def step_specialist(rt: AgentRuntime, incident_id: str, assignment: dict, context: str = "") -> dict:
    f = await specialists.run(rt, incident_id, Assignment(**assignment), context)
    return f.model_dump(mode="json")


async def step_converge(rt: AgentRuntime, alert: dict, incident_id: str, plan: dict, round_no: int, findings: list[dict]) -> dict:
    d = await commander.converge(rt, Alert(**alert), incident_id, commander.Plan(**plan), round_no, [Finding(**f) for f in findings])
    return d.model_dump(mode="json")


async def step_single(rt: AgentRuntime, alert: dict, incident_id: str) -> dict:
    rep, _ = await single_agent.investigate(rt, Alert(**alert), incident_id)
    return rep.model_dump(mode="json")


async def step_propose(rt: AgentRuntime, alert: dict, incident_id: str, report: dict) -> dict:
    a = await remediation.propose(rt, Alert(**alert), incident_id, RootCauseReport(**report))
    return a.model_dump(mode="json")


# -- local orchestrator ------------------------------------------------------------------

@dataclass
class InvestigationResult:
    incident_id: str
    report: RootCauseReport
    action: ProposedAction | None
    usage: Usage
    findings: list[Finding] = field(default_factory=list)
    duration_s: float = 0.0
    mode: str = "multi"
    rounds: int = 1


class LocalOrchestrator:
    """Runs the investigation in-process with per-step checkpoints: a re-run after a crash skips completed steps
    (no repeated LLM calls), which mirrors what Temporal gives us in production."""

    def __init__(self, rt: AgentRuntime, crash_after: Callable[[str], bool] | None = None):
        self.rt = rt
        self.crash_after = crash_after  # tests: raise after a named step completes
        self.executed: list[str] = []

    async def _step(self, key: str, incident_id: str, fn: Callable[[], Awaitable[dict]]) -> dict:
        cached = self.rt.board.checkpoint_get(f"{incident_id}:{key}")
        if cached is not None:
            return json.loads(cached)
        out = await fn()
        self.rt.board.checkpoint_put(f"{incident_id}:{key}", incident_id, json.dumps(out))
        self.executed.append(key)
        if self.crash_after and self.crash_after(key):
            raise RuntimeError(f"simulated crash after {key}")
        return out

    async def investigate(self, alert: Alert, mode: str = "multi") -> InvestigationResult:
        rt, iid = self.rt, f"inc-{alert.fingerprint}"
        rt.board.open_incident(iid, alert.fingerprint, alert.model_dump_json())
        t0, a = time.perf_counter(), alert.model_dump(mode="json")
        usage = Usage()
        findings: list[Finding] = []
        if mode == "single":
            rep = RootCauseReport(**await self._step("single", iid, lambda: step_single(rt, a, iid)))
            usage = rep.usage
            rounds = 1
        else:
            plan = await self._step("plan", iid, lambda: step_plan(rt, a, iid))
            usage = usage.add(Usage(**plan["usage"]))
            assignments = plan["assignments"]
            report_dict: dict | None = None
            degraded = False
            rounds = 0
            if usage.cost_usd >= rt.budget_usd:  # ceiling hit by planning alone: degrade to the cheaper single-agent mode
                rep = RootCauseReport(**await self._step("single", iid, lambda: step_single(rt, a, iid)))
                usage = usage.add(rep.usage)
                report_dict, degraded, rounds = rep.model_dump(mode="json"), True, 1
                assignments = []
            for rnd in range(1, rt.max_rounds + 1):
                if report_dict is not None:
                    break
                rounds = rnd
                fs = await asyncio.gather(*[
                    self._step(f"r{rnd}:{i}:{x['agent']}", iid, (lambda x=x: step_specialist(rt, iid, x)))
                    for i, x in enumerate(assignments)])
                for f in fs:
                    usage = usage.add(Usage(**f["usage"]))
                    findings.append(Finding(**f))
                if usage.cost_usd >= rt.budget_usd and rnd < rt.max_rounds:  # ceiling hit mid-investigation: no more follow-up rounds
                    degraded = True
                    rnd_force = rt.max_rounds
                else:
                    rnd_force = rnd
                dec = await self._step(f"r{rnd}:converge", iid, lambda: step_converge(rt, a, iid, plan, rnd_force, [f for f in fs]))
                usage = usage.add(Usage(**dec["usage"]))
                if dec["action"] == "report" and dec.get("report"):
                    report_dict = dec["report"]
                    break
                assignments = dec["assignments"]
            if report_dict is None:
                raise RuntimeError("commander never produced a report")
            rep = RootCauseReport(**report_dict)
            rep = rep.model_copy(update={"degraded": rep.degraded or degraded})
        action = None
        if rep.proposed_action is not None or rep.category.value != "unknown":
            act = await self._step("propose", iid, lambda: step_propose(rt, a, iid, rep.model_dump(mode="json")))
            action = ProposedAction(**act)
        rep = rep.model_copy(update={"usage": usage, "rounds": rounds})
        rt.board.set_status(iid, "diagnosed", rep)
        if rt.memory is not None and rt.memory_write:
            rt.memory.add(iid, alert.name, rep, signature_from_evidence(rt.board.list(iid)), action.type if action else "")
        return InvestigationResult(iid, rep, action, usage, findings, time.perf_counter() - t0, mode, rounds)
