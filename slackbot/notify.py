"""Notifications + Slack Block Kit approval messages. Signature verification for Slack interaction callbacks."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from typing import Any, Protocol

import httpx

from agents.core.models import ProposedAction, RootCauseReport, Tier


class Notifier(Protocol):
    async def post_report(self, incident_id: str, report: dict[str, Any], action: dict[str, Any] | None) -> None: ...
    async def request_approval(self, incident_id: str, report: dict[str, Any], action: dict[str, Any]) -> None: ...
    async def post_outcome(self, incident_id: str, text: str) -> None: ...


def report_blocks(incident_id: str, report: RootCauseReport) -> list[dict[str, Any]]:
    ruled = "\n".join(f"• ~{r.hypothesis}~ ({', '.join(r.evidence)})" for r in report.ruled_out) or "none"
    return [
        {"type": "header", "text": {"type": "plain_text", "text": f"Root cause ({incident_id})"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*{report.root_cause}*\nservice: `{report.service}` · category: `{report.category.value}` · confidence: {report.confidence:.0%}"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*Evidence:* {', '.join(report.evidence)}\n*Ruled out:*\n{ruled}"}},
    ]


def approval_blocks(incident_id: str, action: ProposedAction) -> list[dict[str, Any]]:
    value = json.dumps({"incident_id": incident_id})
    desc = f"`{action.type}` target `{action.target}` {json.dumps(action.params) if action.params else ''}"
    if action.tier is Tier.DESTRUCTIVE:
        return [{"type": "section", "text": {"type": "mrkdwn", "text": f":rotating_light: *Destructive action proposed:* {desc}\nThis needs a typed confirmation in the dashboard; it cannot be approved with one click."}}]
    return [
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*Proposed action* ({action.tier.value}): {desc}"}},
        {"type": "actions", "block_id": f"approval:{incident_id}", "elements": [
            {"type": "button", "style": "primary", "action_id": "nightshift_approve", "value": value, "text": {"type": "plain_text", "text": "Approve"}},
            {"type": "button", "style": "danger", "action_id": "nightshift_reject", "value": value, "text": {"type": "plain_text", "text": "Reject"}}]},
    ]


class MemoryNotifier:
    """Collects messages (tests, local demo)."""

    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    async def post_report(self, incident_id, report, action):
        self.messages.append({"kind": "report", "incident_id": incident_id, "report": report, "action": action})

    async def request_approval(self, incident_id, report, action):
        self.messages.append({"kind": "approval", "incident_id": incident_id, "action": action})

    async def post_outcome(self, incident_id, text):
        self.messages.append({"kind": "outcome", "incident_id": incident_id, "text": text})


class SlackNotifier:
    def __init__(self, token: str | None = None, channel: str | None = None, client: httpx.AsyncClient | None = None):
        self.token = token or os.environ.get("SLACK_BOT_TOKEN", "")
        self.channel = channel or os.environ.get("SLACK_CHANNEL", "#incidents")
        self.client = client or httpx.AsyncClient(timeout=15)

    async def _post(self, blocks: list[dict], text: str) -> None:
        r = await self.client.post("https://slack.com/api/chat.postMessage", headers={"Authorization": f"Bearer {self.token}"},
                                   json={"channel": self.channel, "text": text, "blocks": blocks})
        r.raise_for_status()

    async def post_report(self, incident_id, report, action):
        await self._post(report_blocks(incident_id, RootCauseReport(**report)), f"Root cause for {incident_id}: {report['root_cause']}")

    async def request_approval(self, incident_id, report, action):
        await self._post(approval_blocks(incident_id, ProposedAction(**action)), f"Approval needed for {incident_id}")

    async def post_outcome(self, incident_id, text):
        await self._post([{"type": "section", "text": {"type": "mrkdwn", "text": text}}], text)


def default_notifier() -> Notifier:
    return SlackNotifier() if os.environ.get("SLACK_BOT_TOKEN") else MemoryNotifier()


def verify_slack_signature(signing_secret: str, timestamp: str, body: bytes, signature: str, now: float | None = None) -> bool:
    try:
        if abs((now or time.time()) - float(timestamp)) > 300:
            return False
    except ValueError:
        return False
    base = b"v0:" + timestamp.encode() + b":" + body
    expected = "v0=" + hmac.new(signing_secret.encode(), base, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
