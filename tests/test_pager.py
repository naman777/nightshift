from __future__ import annotations

import json

import httpx

from agents.core.models import Category, ProposedAction, RootCauseReport, Tier
from slackbot.pager import page, spoken_summary


def report(tier=Tier.REVERSIBLE):
    return RootCauseReport(root_cause="lb upstream_timeout_ms changed from 2000 to 50 in commit e37cd672", service="lb", category=Category.CONFIG_CHANGE,
                           confidence=0.9, evidence=["ev_1"], proposed_action=ProposedAction(type="revert_commit", target="e37cd672", tier=tier))


def test_summary_is_speakable_and_states_the_decision():
    s = spoken_summary("inc-1", report())
    assert "e37cd672" not in s and "ev_1" not in s and "revert commit" in s and "approval" in s and "high" in s
    assert "needs a human" in spoken_summary("inc-1", report(Tier.READ_ONLY))


async def test_page_posts_to_the_configured_provider(monkeypatch):
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen.update(json.loads(req.content))
        return httpx.Response(200, json={})

    monkeypatch.delenv("PAGER_WEBHOOK_URL", raising=False)
    assert await page("+15550100", "inc-1", report()) is False
    monkeypatch.setenv("PAGER_WEBHOOK_URL", "http://voice.example/say")
    assert await page("+15550100", "inc-1", report(), httpx.AsyncClient(transport=httpx.MockTransport(handler))) is True
    assert seen["to"] == "+15550100" and "Nightshift incident" in seen["say"]
