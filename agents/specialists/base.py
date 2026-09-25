from __future__ import annotations

from dataclasses import dataclass

from agents.core.loop import AgentLoop, Budget
from agents.core.models import Assignment, Finding
from agents.prompts import load
from agents.runtime import AgentRuntime


@dataclass(frozen=True)
class SpecialistSpec:
    name: str
    tools: tuple[str, ...]
    max_tool_calls: int


async def run_specialist(rt: AgentRuntime, spec: SpecialistSpec, incident_id: str, assignment: Assignment, context: str = "") -> Finding:
    loop = AgentLoop(
        name=spec.name, llm=rt.llm, model=rt.specialist_model, system_prompt=load(spec.name, rt.prompt_version),
        client=rt.client, allowed_tools=list(spec.tools), budget=Budget(max_tool_calls=spec.max_tool_calls, max_tokens=60_000),
        board=rt.board, incident_id=incident_id, on_step=rt.on_step)
    return await loop.run(assignment.question, context)
