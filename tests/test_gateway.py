from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import httpx
import pytest

from agents.core.db import Database
from gateway.app import alertmanager_to_alerts, create_app
from orchestrator.api import LocalRunner
from orchestrator.runtime_factory import _world
from slackbot.notify import MemoryNotifier, approval_blocks, verify_slack_signature
from agents.core.models import ProposedAction, Tier

SCENARIO = "bad-config-push-lb-timeout-00"


def payload(fp="fp-1", scenario=SCENARIO):
    return {"alerts": [{"status": "firing", "fingerprint": fp, "labels": {"alertname": "HighErrorRate_orders", "service": "orders-svc",
                                                                            "scenario": scenario}, "annotations": {"summary": "errors"}},
                       {"status": "resolved", "fingerprint": "gone", "labels": {"alertname": "x"}}]}


@pytest.fixture
def stack():
    db = Database.memory()
    notifier = MemoryNotifier()
    runner = LocalRunner(notifier=notifier, db=db)
    app = create_app(db=db, runner=runner, signing_secret="s3cret", notifier=notifier)
    return app, runner, notifier


def client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


def test_only_firing_alerts_are_converted():
    alerts = alertmanager_to_alerts(payload())
    assert [a.fingerprint for a in alerts] == ["fp-1"] and alerts[0].service == "orders-svc"


async def test_webhook_investigates_dedupes_and_requires_approval(stack):
    app, runner, notifier = stack
    async with client(app) as c:
        r1 = (await c.post("/webhook/alertmanager", json=payload())).json()
        r2 = (await c.post("/webhook/alertmanager", json=payload())).json()  # same fingerprint while running
        iid = r1["incidents"][0]["incident_id"]
        assert r1["incidents"][0]["new"] is True and r2["incidents"][0]["new"] is False
        for _ in range(200):  # wait for the approval request
            if any(m["kind"] == "approval" for m in notifier.messages):
                break
            await __import__("asyncio").sleep(0.05)
        detail = (await c.get(f"/incidents/{iid}")).json()
        assert detail["incident"]["status"] == "awaiting_approval"
        assert detail["incident"]["report"]["category"] == "config_change" and detail["evidence"] and detail["steps"]
        assert _world(SCENARIO).actions == []  # nothing executed before a human approves
        await c.post(f"/incidents/{iid}/approve", json={"user": "alice"})
        result = await runner.wait(iid)
        assert result["outcome"]["status"] == "resolved"
        assert [a["action"] for a in _world(SCENARIO).actions] == ["revert_commit"]
        audit = (await c.get(f"/incidents/{iid}")).json()["audit"]
        assert any(a["decision"] == "allowed" and a["tool"] == "revert_commit" for a in audit)
        assert json.loads(next(a for a in audit if a["tool"] == "revert_commit" and a["decision"] == "allowed")["evidence_ids"])  # justified by evidence ids


async def test_reject_never_executes():
    db = Database.memory()
    notifier = MemoryNotifier()
    runner = LocalRunner(notifier=notifier, db=db)
    app = create_app(db=db, runner=runner)
    async with client(app) as c:
        iid = (await c.post("/webhook/alertmanager", json=payload("fp-2", "memory-leak-orders-cache-00"))).json()["incidents"][0]["incident_id"]
        for _ in range(200):
            if runner.decisions.get(iid):
                break
            await __import__("asyncio").sleep(0.05)
        await c.post(f"/incidents/{iid}/reject", json={"user": "bob"})
        assert (await runner.wait(iid))["outcome"]["status"] == "rejected"
        assert _world("memory-leak-orders-cache-00").actions == []


async def test_approval_timeout_defaults_to_reject():
    db = Database.memory()
    runner = LocalRunner(notifier=MemoryNotifier(), db=db, approval_timeout_s=0.05)
    from agents.core.models import Alert
    a = Alert(fingerprint="fp-3", name="ServiceMemoryGrowth", service="orders-svc", labels={"scenario": "log-flood-orders-00"})
    iid, _ = await runner.start(a)
    assert (await runner.wait(iid))["outcome"]["status"] == "rejected"


def test_slack_signature_and_blocks():
    body = urlencode({"payload": json.dumps({"x": 1})}).encode()
    ts = str(int(time.time()))
    sig = "v0=" + hmac.new(b"k", b"v0:" + ts.encode() + b":" + body, hashlib.sha256).hexdigest()
    assert verify_slack_signature("k", ts, body, sig)
    assert not verify_slack_signature("k", ts, body, "v0=bad")
    assert not verify_slack_signature("k", str(int(time.time()) - 4000), body, sig)  # replay protection
    blocks = approval_blocks("inc-1", ProposedAction(type="revert_commit", target="abc", tier=Tier.REVERSIBLE))
    assert {e["action_id"] for e in blocks[1]["elements"]} == {"nightshift_approve", "nightshift_reject"}
    destructive = approval_blocks("inc-1", ProposedAction(type="scale_to_zero", target="orders", tier=Tier.DESTRUCTIVE))
    assert all(b["type"] != "actions" for b in destructive)  # no one-click path for destructive actions


async def test_slack_interactive_endpoint_verifies_signature(stack):
    app, runner, notifier = stack
    body = urlencode({"payload": json.dumps({"user": {"username": "carol"}, "actions": [
        {"action_id": "nightshift_reject", "value": json.dumps({"incident_id": "inc-zzz"})}]})}).encode()
    ts = str(int(time.time()))
    good = "v0=" + hmac.new(b"s3cret", b"v0:" + ts.encode() + b":" + body, hashlib.sha256).hexdigest()
    async with client(app) as c:
        hdr = {"X-Slack-Request-Timestamp": ts, "content-type": "application/x-www-form-urlencoded"}
        assert (await c.post("/slack/interactive", content=body, headers={**hdr, "X-Slack-Signature": "v0=nope"})).status_code == 401
        assert (await c.post("/slack/interactive", content=body, headers={**hdr, "X-Slack-Signature": good})).status_code == 200


async def test_change_webhook_flags_risky_changes_before_any_alert(stack):
    from bench.scenario import build_world, load_all

    s = next(x for x in load_all() if x.id == "bad-config-push-lb-timeout-00")
    world, _, _ = build_world(s)
    app, runner, notifier = stack
    risky = next(c for c in world.commits if c.sha in world.risky)
    benign = next(c for c in world.commits if c.sha not in world.risky and c.kind == "deploy" and "chore" in c.message)
    async with client(app) as c:
        r1 = (await c.post("/webhook/change", json={"sha": risky.sha, "service": risky.service, "kind": risky.kind, "message": risky.message,
                                                      "labels": {"scenario": s.id}})).json()
        r2 = (await c.post("/webhook/change", json={"sha": benign.sha, "service": benign.service, "kind": "deploy", "message": benign.message,
                                                      "labels": {"scenario": s.id}})).json()
    assert r1["flagged"] and r1["risk"] == "high" and "upstream_timeout_ms" in r1["reasons"][0] and r1["queries"][0].startswith("changes__commit_diff")
    assert not r2["flagged"] and r2["risk"] == "low"
    assert [m["kind"] for m in notifier.messages] == ["outcome"] and "HIGH risk" in notifier.messages[0]["text"]  # only the risky one paged Slack


async def test_optional_bearer_token_protects_mutating_endpoints(stack, monkeypatch):
    monkeypatch.setenv("NIGHTSHIFT_API_TOKEN", "t0ken")
    app, runner, notifier = stack
    async with client(app) as c:
        assert (await c.post("/incidents/inc-x/approve", json={"user": "mallory"})).status_code == 401
        assert (await c.post("/webhook/alertmanager", json=payload("fp-auth"))).status_code == 401
        assert (await c.get("/incidents")).status_code == 200                       # read-only stays open
        ok = await c.post("/incidents/inc-x/approve", json={"user": "alice"}, headers={"Authorization": "Bearer t0ken"})
        assert ok.status_code == 200


async def test_sse_stream_emits_agent_steps_and_ends_when_resolved(stack):
    app, runner, notifier = stack
    async with client(app) as c:
        iid = (await c.post("/webhook/alertmanager", json=payload("fp-sse", "scheduler-backlog-workers-1-00"))).json()["incidents"][0]["incident_id"]
        for _ in range(200):
            if runner.decisions.get(iid):
                break
            await __import__("asyncio").sleep(0.05)
        await c.post(f"/incidents/{iid}/approve", json={"user": "alice"})
        await runner.wait(iid)
        body = (await c.get(f"/incidents/{iid}/stream")).text
    assert "event: step" in body and "event: status" in body and '"status": "resolved"' in body


async def test_gateway_fails_closed_without_credentials(stack, monkeypatch):
    monkeypatch.delenv("NIGHTSHIFT_ALLOW_INSECURE")
    monkeypatch.delenv("NIGHTSHIFT_API_TOKEN", raising=False)
    app, runner, notifier = stack
    async with client(app) as c:
        r = await c.post("/incidents/inc-x/approve", json={"user": "anyone", "confirmation": "CONFIRM scale_to_zero", "reason": "x"})
        assert r.status_code == 401 and "not configured" in r.text
    app2 = create_app(db=Database.memory(), runner=runner, signing_secret="")  # Slack callback with no signing secret is refused, not skipped
    body = urlencode({"payload": json.dumps({"actions": [{"action_id": "nightshift_approve", "value": json.dumps({"incident_id": "inc-1"})}]})}).encode()
    async with client(app2) as c:
        assert (await c.post("/slack/interactive", content=body)).status_code == 401


def test_slack_signature_rejects_garbage_timestamp():
    assert verify_slack_signature("s", "abc", b"", "") is False
