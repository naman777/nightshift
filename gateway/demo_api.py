"""Demo endpoints for the dashboard: browse the scenario catalog, launch an investigation, see the ground truth afterwards.

All of this drives the same /webhook/alertmanager path a real alert takes (alert -> runner -> agents); the launcher only builds the alert.
Nothing here is reachable without the gateway token (mutating call) except the read-only catalog.
"""
from __future__ import annotations

import os
import secrets
from functools import lru_cache
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from bench.scenario import Scenario, build_world, load_all, load_hard

FAULTS = {
    "bad_config_push": ("Bad config push", "A config value was changed and traffic started failing."),
    "bad_deploy": ("Bad deploy", "A release introduced a bug (slow queries, crash, off-by-one)."),
    "crashed_replica": ("Crashed replica", "One replica is unhealthy but still receiving traffic."),
    "db_connection_exhaustion": ("DB connections exhausted", "A job is holding every database connection."),
    "dependency_outage": ("Dependency outage", "A downstream service is refusing connections."),
    "log_flood": ("Log flood", "A noisy log level is drowning the system."),
    "memory_leak": ("Memory leak", "A service is growing until it is OOM-killed."),
    "noisy_neighbour": ("Noisy neighbour", "A periodic batch job starves other services of CPU."),
    "scheduler_backlog": ("Scheduler backlog", "Jobs are queueing because workers are gone."),
    "slow_dependency": ("Slow dependency", "A downstream service got slow and callers are timing out."),
}
HERRING = {
    "harmless_deploy": "unrelated deploy right before the incident",
    "harmless_config": "unrelated config change right before the incident",
    "decoy_config": "a plausible-looking config change that is NOT the cause",
    "noisy_404": "a burst of harmless 404 errors",
    "unrelated_spike": "an unrelated metric spike",
    "log_injection": "prompt injection planted in the logs",
}
OUTAGE = {"metrics": "no metrics", "logs": "no logs", "deploys": "no deploy history", "configs": "no config history"}


class LaunchBody(BaseModel):
    scenario: str
    mode: str = "multi"          # multi | single
    provider: str = "mock"       # mock | openai
    pace: bool = True            # slow the offline policy down so the run can be watched


@lru_cache(maxsize=1)
def _all() -> dict[str, tuple[Scenario, bool]]:
    return {**{s.id: (s, False) for s in load_all()}, **{s.id: (s, True) for s in load_hard()}}


def _describe(s: Scenario, hard: bool) -> dict[str, Any]:
    title, blurb = FAULTS.get(s.fault, (s.fault, ""))
    tags = []
    if s.red_herring:
        tags.append(HERRING.get(s.red_herring["type"], s.red_herring["type"]))
    tags += [OUTAGE.get(t, t) for t in s.telemetry_outage]
    if s.also_faults:
        tags.append(f"{len(s.also_faults)} unrelated concurrent fault(s)")
    difficulty = "hard" if hard else ("tricky" if tags else "standard")
    return {"id": s.id, "fault": s.fault, "title": title, "blurb": s.why_hard or blurb, "alert": s.expected_alert, "difficulty": difficulty,
            "tags": tags, "split": s.split, "injection": bool(s.red_herring and s.red_herring["type"] == "log_injection")}


@lru_cache(maxsize=64)
def ground_truth(scenario_id: str) -> dict | None:
    entry = _all().get(scenario_id)
    if not entry:
        return None
    _, alert, gt = build_world(entry[0])
    return {"root_cause": gt.root_cause, "service": gt.root_cause_service, "category": gt.category.value,
            "correct_remediations": gt.correct_remediations, "unsafe_actions": gt.unsafe_actions}


def build_router(get_runner, require_token) -> APIRouter:
    r = APIRouter(prefix="/demo")

    @r.get("/config")
    async def config() -> dict:
        model = os.environ.get("NIGHTSHIFT_DEMO_MODEL", "gpt-6-luna")
        return {"providers": [
            {"id": "mock", "label": "Offline reference policy", "note": "Free, instant, deterministic. Not a language model.", "available": True},
            {"id": "openai", "label": f"Real LLM ({model})", "note": "Calls the OpenAI API; costs a few cents per incident.",
             "available": bool(os.environ.get("OPENAI_API_KEY")), "model": model}]}

    @r.get("/scenarios")
    async def scenarios() -> list[dict]:
        return [_describe(s, hard) for s, hard in _all().values()]

    @r.post("/launch", dependencies=[Depends(require_token)])
    async def launch(body: LaunchBody, request: Request) -> dict:
        from orchestrator.runtime_factory import _world

        entry = _all().get(body.scenario)
        if not entry:
            raise HTTPException(404, "unknown scenario")
        if body.mode not in ("multi", "single"):
            raise HTTPException(400, "mode must be multi or single")
        if body.provider not in ("mock", "openai"):
            raise HTTPException(400, "provider must be mock or openai")
        if body.provider == "openai" and not os.environ.get("OPENAI_API_KEY"):
            raise HTTPException(400, "OPENAI_API_KEY is not set on the gateway")
        s = entry[0]
        _world.cache_clear()  # every launch starts from a clean simulated world (an earlier approve must not leak into it)
        labels = {"alertname": s.expected_alert, "service": "orders-svc", "scenario": s.id, "mode": body.mode, "llm_provider": body.provider}
        if body.provider == "openai":
            labels["llm_model"] = os.environ.get("NIGHTSHIFT_DEMO_MODEL", "gpt-6-luna")
        elif body.pace:
            labels["pace"] = "0.9"
        # Reuse the scenario's own alert: its timestamp lives on the simulated world's clock, which a model reading the alert relies on.
        base = build_world(s)[1]
        alert = base.model_copy(update={"fingerprint": f"demo-{s.id}-{secrets.token_hex(3)}", "labels": {**base.labels, **labels},
                                        "annotations": {**base.annotations, "summary": f"{s.expected_alert} firing"}})
        iid, _ = await get_runner().start(alert, body.mode)
        return {"incident_id": iid}

    return r
