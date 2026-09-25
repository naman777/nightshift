"""Voice paging (stretch): a short spoken summary of a root-cause report, delivered to a voice provider webhook.

The provider is pluggable: set PAGER_WEBHOOK_URL to any service that accepts {"to": ..., "say": ...} (a Twilio Function, your own voice runtime, ...).
The summary is written to be heard: no ids or shas read aloud, the decision required stated last.
"""
from __future__ import annotations

import os

import httpx

from agents.core.models import RootCauseReport


def spoken_summary(incident_id: str, report: RootCauseReport) -> str:
    conf = "high" if report.confidence >= 0.8 else "moderate" if report.confidence >= 0.5 else "low"
    text = f"Nightshift incident. Likely root cause: {report.root_cause.split(' in commit')[0].rstrip('.')}. Service {report.service}. Confidence {conf}."
    if report.ruled_out:
        text += f" {len(report.ruled_out)} alarming signals were ruled out."
    a = report.proposed_action
    if a and a.tier.value != "read_only":
        text += f" Proposed fix: {a.type.replace('_', ' ')}. It needs your approval in Slack or the dashboard."
    else:
        text += " No automated fix is proposed; this needs a human."
    return text


async def page(to: str, incident_id: str, report: RootCauseReport, client: httpx.AsyncClient | None = None) -> bool:
    url = os.environ.get("PAGER_WEBHOOK_URL")
    if not url:
        return False
    async with (client or httpx.AsyncClient(timeout=15)) as c:
        r = await c.post(url, json={"to": to, "say": spoken_summary(incident_id, report), "incident_id": incident_id})
        r.raise_for_status()
    return True
