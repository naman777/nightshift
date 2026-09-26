"""Baseline: ONE agent with ALL read tools and a shared tool budget (for the single-vs-multi comparison)."""
from __future__ import annotations

from agents.commander import DECISION_SCHEMA, parse_report, alert_text
from agents.core.loop import AgentLoop, Budget
from agents.core.models import Alert, Category, EvidenceRow, ProposedAction, RootCauseReport, Tier, Usage
from agents.prompts import load
from agents.runtime import AgentRuntime

READ_TOOLS = ["metrics__query_range", "metrics__top_anomalies", "metrics__compare_windows", "logs__search", "logs__cluster_errors",
              "logs__tail", "changes__recent_deploys", "changes__config_diff", "changes__commit_diff", "code__read_file",
              "code__grep", "code__run_tests"]

_REPORT = DECISION_SCHEMA["input_schema"]["properties"]["report"]
SUBMIT_REPORT = {
    "name": "submit_report",
    "description": "Submit the final ranked root cause. `claims` are the facts you observed; each cites the tool call that produced it.",
    "input_schema": {"type": "object", "required": ["report", "claims"], "properties": {
        "report": _REPORT,
        "claims": {"type": "array", "items": {"type": "object", "required": ["claim", "tool_call_ref"], "properties": {
            "claim": {"type": "string"}, "tool_call_ref": {"type": "string"}, "confidence": {"type": "number"}}}}}},
}


async def investigate(rt: AgentRuntime, alert: Alert, incident_id: str) -> tuple[RootCauseReport, Usage]:
    holder: dict = {}

    def handler(args: dict):
        # Ground claims in real tool calls, then let the shared report parser validate citations.
        loop_calls = holder["loop_calls"]()
        bad = [c.get("tool_call_ref") for c in args.get("claims", []) if c.get("tool_call_ref") not in loop_calls]
        if bad:
            return None, f"claims cite unknown tool calls {bad}; valid: {sorted(loop_calls)}"
        ids = []
        minted = holder.setdefault("minted", {})  # a rejected submission that is retried must not duplicate evidence rows
        for c in args.get("claims", []):
            q, ref = loop_calls[c["tool_call_ref"]]
            key = (c["claim"], c["tool_call_ref"])
            if key not in minted:
                minted[key] = rt.board.add(EvidenceRow(incident_id=incident_id, agent="single", claim=c["claim"], evidence_query=q,
                                                       evidence_result_ref=ref, confidence=float(c.get("confidence", 0.6)))).id
            ids.append(minted[key])
        rep = dict(args["report"])
        rep["evidence"] = ids  # evidence ids are minted from the grounded claims
        # The model cannot know the minted ids, so ids it invents for `ruled_out` are unverifiable: keep only real ones, and drop
        # a ruled-out entry left with no citation at all (an uncited "ruled out" must not stand).
        real = {e.id for e in rt.board.list(incident_id)}
        rep["ruled_out"] = [{**x, "evidence": [e for e in x.get("evidence", []) if e in real]} for x in rep.get("ruled_out", []) if isinstance(x, dict)]
        rep["ruled_out"] = [x for x in rep["ruled_out"] if x["evidence"]]
        report, err = parse_report({"report": rep}, rt, incident_id)
        return (report, "") if report else (None, err)

    loop = AgentLoop("single", rt.llm, rt.commander_model, load("single", rt.prompt_version), rt.client, allowed_tools=READ_TOOLS,
                     budget=Budget(max_tool_calls=rt.single_agent_tool_budget, max_tokens=60_000, max_llm_calls=30),
                     board=rt.board, incident_id=incident_id, on_step=rt.on_step, final_schema=SUBMIT_REPORT, final_handler=handler)
    holder["loop_calls"] = lambda: {k: (v.query, v.ref) for k, v in loop._last_state.calls.items()}
    finding = await loop.run(f"Investigate this alert end to end and submit a report.\n{alert_text(alert)}")
    if loop.output is None:
        rows = rt.board.list(incident_id)
        rep = RootCauseReport(root_cause="Inconclusive: single agent ran out of budget", service=alert.service,
                              category=Category.UNKNOWN, confidence=0.1, evidence=[r.id for r in rows[:1]] or [],
                              proposed_action=ProposedAction(type="escalate", target="on-call", tier=Tier.READ_ONLY), degraded=True,
                              usage=finding.usage)
        return rep, finding.usage
    rep: RootCauseReport = loop.output
    return rep.model_copy(update={"usage": finding.usage}), finding.usage
