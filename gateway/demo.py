"""No-docker demo: start the gateway on a simulated incident and print where to look.

  python -m gateway.demo                     # then open the dashboard: cd dashboard && npm run dev  (http://localhost:3001)
  python -m gateway.demo --scenario bad-deploy-nil-deref-01 --serve-only

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
    ap.add_argument("--scenario", default="bad-config-push-lb-timeout-00")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--serve-only", action="store_true")
    a = ap.parse_args()
    os.environ.setdefault("NIGHTSHIFT_BACKEND", "sim")
    os.environ.setdefault("NIGHTSHIFT_ALLOW_INSECURE", "1")  # local demo only: real deployments set NIGHTSHIFT_API_TOKEN
    os.environ.setdefault("NIGHTSHIFT_DB_URL", "sqlite:///nightshift-demo.db")
    from gateway.app import create_app

    config = uvicorn.Config(create_app(), host="127.0.0.1", port=a.port, log_level="warning")
    server = uvicorn.Server(config)

    async def run() -> None:
        task = asyncio.create_task(server.serve())
        if not a.serve_only:
            await fire(a.port, a.scenario)
        await task

    asyncio.run(run())


if __name__ == "__main__":
    main()
