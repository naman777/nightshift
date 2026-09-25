"""Gateway (FastAPI): Alertmanager webhook, incident API, SSE stream for the dashboard, Slack interaction endpoint."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from agents.core.db import Database
from agents.core.evidence import EvidenceBoard
from agents.core.models import Alert
from mcp_servers.policy import PolicyEngine
from orchestrator.api import IncidentRunner, LocalRunner
from slackbot.notify import verify_slack_signature

RESULTS_DIR = Path(os.environ.get("NIGHTSHIFT_RESULTS", "bench/results"))


class ApprovalBody(BaseModel):
    user: str
    confirmation: str = ""
    reason: str = ""


def alertmanager_to_alerts(payload: dict[str, Any]) -> list[Alert]:
    out = []
    for a in payload.get("alerts", []):
        if a.get("status", "firing") != "firing":
            continue
        labels = a.get("labels", {})
        out.append(Alert(fingerprint=a.get("fingerprint") or f"{labels.get('alertname', 'alert')}-{labels.get('service', '')}",
                         name=labels.get("alertname", "unknown"), service=labels.get("service", "unknown"),
                         severity=labels.get("severity", "critical"), labels=labels, annotations=a.get("annotations", {})))
    return out


def create_app(db: Database | None = None, runner: IncidentRunner | None = None, signing_secret: str | None = None) -> FastAPI:
    db = db or Database(os.environ.get("NIGHTSHIFT_DB_URL", "sqlite:///nightshift.db"))
    board = EvidenceBoard(db)
    app = FastAPI(title="Nightshift gateway")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    app.state.runner = runner or LocalRunner(db=db)
    secret = signing_secret if signing_secret is not None else os.environ.get("SLACK_SIGNING_SECRET", "")

    @app.get("/healthz")
    async def healthz() -> dict:
        return {"ok": True}

    @app.post("/webhook/alertmanager")
    async def webhook(payload: dict) -> dict:
        started = []
        for alert in alertmanager_to_alerts(payload):
            iid, new = await app.state.runner.start(alert, os.environ.get("NIGHTSHIFT_MODE", "multi"))
            started.append({"incident_id": iid, "new": new})
        return {"incidents": started}

    @app.get("/incidents")
    async def incidents() -> list[dict]:
        return board.list_incidents()

    @app.get("/incidents/{iid}")
    async def incident(iid: str) -> dict:
        row = board.get_incident(iid)
        if not row:
            raise HTTPException(404, "unknown incident")
        return {
            "incident": {**row, "report": json.loads(row["report_json"]) if row["report_json"] else None, "alert": json.loads(row["alert_json"] or "{}")},
            "evidence": [e.model_dump() for e in board.list(iid)],
            "steps": board.steps(iid),
            "audit": PolicyEngine(db).audit_rows(iid),
        }

    @app.get("/incidents/{iid}/stream")
    async def stream(iid: str, request: Request):
        async def events():
            seen = 0
            while not await request.is_disconnected():
                for s in board.steps(iid, seen):
                    seen = s["seq"]
                    yield {"event": "step", "data": json.dumps(s)}
                row = board.get_incident(iid)
                if row:
                    yield {"event": "status", "data": json.dumps({"status": row["status"]})}
                    if row["status"] in ("resolved", "rejected", "blocked", "escalated"):
                        return
                await asyncio.sleep(0.5)
        return EventSourceResponse(events())

    @app.post("/incidents/{iid}/approve")
    async def approve(iid: str, body: ApprovalBody) -> dict:
        await app.state.runner.approve(iid, body.user, body.confirmation, body.reason)
        return {"ok": True}

    @app.post("/incidents/{iid}/reject")
    async def reject(iid: str, body: ApprovalBody) -> dict:
        await app.state.runner.reject(iid, body.user)
        return {"ok": True}

    @app.post("/slack/interactive")
    async def slack_interactive(request: Request) -> dict:
        raw = await request.body()
        if secret and not verify_slack_signature(secret, request.headers.get("X-Slack-Request-Timestamp", "0"), raw,
                                                 request.headers.get("X-Slack-Signature", "")):
            raise HTTPException(401, "bad signature")
        payload = json.loads(parse_qs(raw.decode())["payload"][0])
        act = payload["actions"][0]
        iid = json.loads(act["value"])["incident_id"]
        user = payload.get("user", {}).get("username", "slack-user")
        if act["action_id"] == "nightshift_approve":
            await app.state.runner.approve(iid, user)
        else:
            await app.state.runner.reject(iid, user)
        return {"ok": True}

    @app.get("/bench/results")
    async def bench_results() -> dict:
        p = RESULTS_DIR / "summary.json"
        return json.loads(p.read_text()) if p.exists() else {"configs": {}, "runs": 0}

    return app


app = create_app() if os.environ.get("NIGHTSHIFT_AUTOSTART_GATEWAY") else None  # `uvicorn gateway.app:create_app --factory`
