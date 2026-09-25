from __future__ import annotations

from agents.core.models import Assignment, Finding
from agents.runtime import AgentRuntime

from . import changes, code, logs, metrics
from .base import SpecialistSpec, run_specialist

SPECIALISTS: dict[str, SpecialistSpec] = {m.SPEC.name: m.SPEC for m in (metrics, logs, changes, code)}


async def run(rt: AgentRuntime, incident_id: str, assignment: Assignment, context: str = "") -> Finding:
    return await run_specialist(rt, SPECIALISTS[assignment.agent], incident_id, assignment, context)
