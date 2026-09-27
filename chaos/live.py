"""Executes a fault's declarative live steps against the real docker-compose stack (and records what to undo)."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from typing import Any

import httpx

from chaos import deploylog
from chaos.faults.bad_deploy import BUGS
from chaos.gitcfg import ROOT, ConfigRepo

TOXIPROXY = os.environ.get("TOXIPROXY_URL", "http://localhost:8474")
SCHEDULER = os.environ.get("SCHEDULER_URL", "http://localhost:8090")


class LiveChaos:
    def __init__(self, repo: ConfigRepo | None = None):
        self.repo = repo or ConfigRepo()

    # -- individual actions; each returns an undo record ------------------------------
    def config(self, service: str, key: str, value: Any, message: str = "", **_: Any) -> dict:
        sha = self.repo.set_yaml_key(service, key, value, message or f"{service}: tune {key}")
        return {"undo": "revert", "sha": sha, "note": f"{service}.{key}={value}"}

    def flag(self, flag: str, value: Any, message: str = "", **_: Any) -> dict:
        sha = self.repo.set_flag(flag, value, message or f"flags: enable {flag}")
        return {"undo": "revert", "sha": sha, "note": f"flag {flag}={value}"}

    def toxiproxy(self, proxy: str, toxic: str, latency_ms: int = 0, **_: Any) -> dict:
        body = {"name": toxic, "type": toxic, "stream": "downstream", "toxicity": 1.0,
                "attributes": {"latency": latency_ms} if toxic == "latency" else {"timeout": 0}}
        httpx.post(f"{TOXIPROXY}/proxies/{proxy}/toxics", json=body, timeout=10).raise_for_status()
        return {"undo": "toxic", "proxy": proxy, "toxic": toxic}

    def kill(self, container: str, **_: Any) -> dict:
        name = f"nightshift-{container}"
        subprocess.run(["docker", "stop", "-t", "0", name], check=True, capture_output=True)  # `stop`, not `kill`: a killed container is revived by restart: unless-stopped
        return {"undo": "start", "container": name}

    def deploy(self, service: str, bug: str = "", sha: str = "", message: str = "", **_: Any) -> dict:
        sha = sha or hashlib.sha1(f"{service}{bug}{time.time()}".encode()).hexdigest()[:8]
        env = {**os.environ, "GIT_SHA": sha, "ORDERS_BUG": bug}
        subprocess.run(["docker", "compose", "up", "-d", "--build", "orders-svc-1", "orders-svc-2"], cwd=ROOT, env=env, check=True, capture_output=True)
        msg = message or (BUGS[bug]["message"] if bug in BUGS else f"{service}: rollback to {sha}")
        deploylog.record(service, sha, msg)
        return {"undo": "deploy", "service": service, "note": f"{service} -> {sha} bug={bug!r}"}

    def foreman_job(self, job: str, hold_connections: int, duration_s: int = 900, **_: Any) -> dict:
        httpx.post(f"{SCHEDULER}/admin/jobs", json={"name": job, "hold_connections": hold_connections, "duration_s": duration_s}, timeout=10).raise_for_status()
        return {"undo": "none", "note": f"job {job} holds {hold_connections} connections for {duration_s}s"}

    # -- orchestration ---------------------------------------------------------------
    def run(self, steps: list[dict[str, Any]]) -> list[dict]:
        undo = []
        for step in steps:
            step = dict(step)
            fn = getattr(self, step.pop("do"))
            undo.append(fn(**step))
        return undo

    def undo(self, records: list[dict]) -> None:
        for r in reversed(records):
            kind = r["undo"]
            if kind == "revert":
                try:
                    self.repo.revert(r["sha"])
                except RuntimeError:
                    # already undone or superseded (e.g. the agent's approved remediation fixed it first): leave the tree clean and carry on
                    try:
                        self.repo.git("revert", "--abort")
                    except RuntimeError:
                        pass
                    print(f"note: {r['sha']} ({r.get('note', '')}) was already superseded; skipped", file=__import__('sys').stderr)
            elif kind == "toxic":
                httpx.delete(f"{TOXIPROXY}/proxies/{r['proxy']}/toxics/{r['toxic']}", timeout=10)
            elif kind == "start":
                subprocess.run(["docker", "start", r["container"]], check=True, capture_output=True)
            elif kind == "deploy":
                self.deploy(r["service"], bug="")
