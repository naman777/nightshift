from __future__ import annotations

import asyncio
import uuid
from datetime import timedelta

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from agents.core.models import Alert
from orchestrator import activities as A
from orchestrator.runtime_factory import _world, shared_db
from orchestrator.worker import TASK_QUEUE
from orchestrator.workflows import InvestigationWorkflow, RemediationWorkflow
from slackbot.notify import MemoryNotifier

SCENARIO = "memory-leak-orders-cache-00"


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("NIGHTSHIFT_DB_URL", f"sqlite:///{tmp_path / 'ns.db'}")
    shared_db.cache_clear()
    notifier = MemoryNotifier()
    A.set_notifier(notifier)
    yield notifier
    shared_db.cache_clear()


def make_alert(scenario=SCENARIO):
    return Alert(fingerprint=f"fp-{uuid.uuid4().hex[:8]}", name="ServiceMemoryGrowth", service="orders-svc",
                 labels={"scenario": scenario, "service": "orders-svc"})


def worker(env, acts=None):
    return Worker(env.client, task_queue=TASK_QUEUE, workflows=[InvestigationWorkflow, RemediationWorkflow], activities=acts or A.ALL,
                  max_cached_workflows=0)  # no sticky queues: the time-skipping server cannot expire a dead worker's sticky queue


async def wait_for(pred, timeout=20.0):
    end = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < end:
        if await pred():
            return
        await asyncio.sleep(0.05)
    raise TimeoutError


def llm_steps(fp: str) -> int:
    return len(shared_db().execute("SELECT seq FROM steps WHERE incident_id = ? AND kind = 'llm'", [f"inc-{fp}"]))


async def run_to_approval(env, alert):
    handle = await env.client.start_workflow(InvestigationWorkflow.run, args=[alert.model_dump(mode="json"), "multi"],
                                             id=f"inv-{alert.fingerprint}", task_queue=TASK_QUEUE)
    rem = env.client.get_workflow_handle(f"rem-{alert.fingerprint}")

    async def waiting():
        try:
            return await rem.query(RemediationWorkflow.state) == "waiting"
        except Exception:
            return False

    await wait_for(waiting)
    return handle, rem


async def test_investigation_then_signal_approval_executes_action(isolated_db):
    alert = make_alert()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with worker(env):
            handle, rem = await run_to_approval(env, alert)
            assert _world(SCENARIO).actions == []  # gated until a human signals
            await rem.signal(RemediationWorkflow.approve, args=["alice", "", ""])
            out = await handle.result()
    assert out["report"]["category"] == "resource_leak" and out["outcome"]["status"] == "resolved"
    assert [a["action"] for a in _world(SCENARIO).actions] == ["set_flag"]
    assert {m["kind"] for m in isolated_db.messages} == {"report", "approval", "outcome"}


async def test_approval_timeout_rejects(isolated_db):
    alert = make_alert("log-flood-orders-00")
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with worker(env):
            handle = await env.client.start_workflow(InvestigationWorkflow.run, args=[alert.model_dump(mode="json"), "multi"],
                                                     id=f"inv-{alert.fingerprint}", task_queue=TASK_QUEUE)
            out = await handle.result()  # time-skipping fast-forwards the 30 minute approval timer
    assert out["outcome"]["status"] == "rejected"
    assert _world("log-flood-orders-00").actions == []


async def test_duplicate_alert_attaches_to_running_workflow(isolated_db):
    from temporalio.common import WorkflowIDConflictPolicy
    alert = make_alert("crashed-replica-replica-2-00")
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with worker(env):
            h1 = await env.client.start_workflow(InvestigationWorkflow.run, args=[alert.model_dump(mode="json"), "multi"],
                                                 id=f"inv-{alert.fingerprint}", task_queue=TASK_QUEUE,
                                                 id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING)
            h2 = await env.client.start_workflow(InvestigationWorkflow.run, args=[alert.model_dump(mode="json"), "multi"],
                                                 id=f"inv-{alert.fingerprint}", task_queue=TASK_QUEUE,
                                                 id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING)
            assert h1.first_execution_run_id == h2.first_execution_run_id
            await h1.result()


async def test_worker_crash_mid_incident_resumes_without_repeating_llm_calls(isolated_db):
    reached = asyncio.Event()

    @activity.defn(name="converge_activity")
    async def stuck_converge(*args):
        reached.set()
        await asyncio.Event().wait()  # the worker "dies" here, after specialists finished

    crash_alert = make_alert("bad-config-push-lb-timeout-00")
    baseline_alert = make_alert("bad-config-push-lb-timeout-00")
    stuck = [stuck_converge if a is A.converge_activity else a for a in A.ALL]
    async with await WorkflowEnvironment.start_time_skipping() as env:
        # uninterrupted reference run
        async with worker(env):
            h = await env.client.start_workflow(InvestigationWorkflow.run, args=[baseline_alert.model_dump(mode="json"), "multi"],
                                                id=f"inv-{baseline_alert.fingerprint}", task_queue=TASK_QUEUE)
            await h.result()
        expected = llm_steps(baseline_alert.fingerprint)

        # crash run: worker A dies inside converge
        w1 = worker(env, stuck)
        t1 = asyncio.create_task(w1.run())
        h = await env.client.start_workflow(InvestigationWorkflow.run, args=[crash_alert.model_dump(mode="json"), "multi"],
                                            id=f"inv-{crash_alert.fingerprint}", task_queue=TASK_QUEUE)
        await asyncio.wait_for(reached.wait(), 30)
        await w1.shutdown()
        t1.cancel()
        before = llm_steps(crash_alert.fingerprint)
        assert 0 < before < expected  # specialists + plan done, converge not yet

        # worker B takes over once the server notices the missed heartbeat; nothing already completed is re-run
        async with worker(env):
            await env.sleep(timedelta(seconds=20))
            await h.result()
    assert llm_steps(crash_alert.fingerprint) == expected  # zero repeated LLM calls across the crash
