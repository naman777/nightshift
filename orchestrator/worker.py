"""Temporal worker. Run: python -m orchestrator.worker   (docker kill nightshift-worker mid-incident to demo crash-and-resume)"""
from __future__ import annotations

import asyncio
import os

from temporalio.client import Client
from temporalio.worker import Worker

from agents.core.telemetry import init_tracing
from orchestrator import activities
from orchestrator.workflows import InvestigationWorkflow, RemediationWorkflow

TASK_QUEUE = "nightshift"


def make_worker(client: Client) -> Worker:
    return Worker(client, task_queue=TASK_QUEUE, workflows=[InvestigationWorkflow, RemediationWorkflow], activities=activities.ALL)


async def main() -> None:
    init_tracing("nightshift-worker")
    client = await Client.connect(os.environ.get("TEMPORAL_ADDRESS", "localhost:7233"))
    print(f"nightshift worker connected, task queue={TASK_QUEUE}", flush=True)
    await make_worker(client).run()


if __name__ == "__main__":
    asyncio.run(main())
