"""No-docker demo: start the gateway (simulated backends); launch scenarios from the dashboard, or fire one from here.

  python -m gateway.demo                     # then open the dashboard: cd dashboard && npm run dev  (http://localhost:3001)
  python -m gateway.demo --scenario bad-deploy-nil-deref-01     # also fire one scenario immediately

Fires the alert through the same /webhook/alertmanager endpoint Alertmanager uses, so what you see is the real code path.
"""
from __future__ import annotations

import argparse
import asyncio
import os

import httpx
import uvicorn


async def fire(port: int, scenario: str) -> None:
    from bench.scenario import load_all

    s = next(x for x in load_all() if x.id == scenario)
    payload = {"alerts": [{"status": "firing", "fingerprint": f"demo-{s.id}", "labels": {
        "alertname": s.expected_alert, "service": "orders-svc", "scenario": s.id}, "annotations": {"summary": f"{s.expected_alert} firing"}}]}
    async with httpx.AsyncClient() as c:
        for _ in range(50):
            try:
                await c.get(f"http://127.0.0.1:{port}/healthz")
                break
            except httpx.HTTPError:
                await asyncio.sleep(0.2)
        r = await c.post(f"http://127.0.0.1:{port}/webhook/alertmanager", json=payload)
        print(f"alert fired -> {r.json()}\nincident page: http://localhost:3001/incidents/inc-demo-{s.id}  (approve it to execute the simulated revert)", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default=None, help="also fire this scenario at start-up (otherwise use the dashboard launcher)")
    ap.add_argument("--port", type=int, default=8000)
    a = ap.parse_args()
    from bench.real_llm import load_env

    load_env()  # OPENAI_API_KEY from .env enables the "real LLM" option in the dashboard
    os.environ.setdefault("NIGHTSHIFT_BACKEND", "sim")
    os.environ.setdefault("NIGHTSHIFT_ALLOW_INSECURE", "1")  # local demo only: real deployments set NIGHTSHIFT_API_TOKEN
    os.environ.setdefault("NIGHTSHIFT_DB_URL", "sqlite:///nightshift-demo.db")
    from gateway.app import create_app

    config = uvicorn.Config(create_app(), host="127.0.0.1", port=a.port, log_level="warning")
    server = uvicorn.Server(config)

    async def run() -> None:
        task = asyncio.create_task(server.serve())
        if a.scenario:
            await fire(a.port, a.scenario)
        await task

    asyncio.run(run())


if __name__ == "__main__":
    main()
