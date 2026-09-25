from __future__ import annotations

import pytest

from agents.core.db import Database
from agents.core.memory import IncidentMemory, jaccard, signature_from_evidence
from agents.core.models import Category, EvidenceRow, RootCauseReport
from agents.pipeline import LocalOrchestrator
from bench.harness import CONFIGS, make_runtime
from bench.runner import seed_memory
from bench.scenario import build_world, load_all, load_hard

ALL = {s.id: s for s in load_all() + load_hard()}


def report(service="payments-svc", category=Category.DEPENDENCY_OUTAGE):
    return RootCauseReport(root_cause="payments-svc is unreachable", service=service, category=category, confidence=0.9, evidence=["ev_1"])


def rows(*claims):
    return [EvidenceRow(id=f"ev_{i}", incident_id="i", agent="metrics", claim=c, evidence_query="q") for i, c in enumerate(claims)]


def test_signature_pairs_metrics_with_services():
    sig = signature_from_evidence(rows("request_rate on payments-svc is 0.01x baseline", "error_rate on lb is 45x baseline, error_rate on orders-svc too"))
    assert "request_rate:payments-svc" in sig and "error_rate:lb" in sig and "error_rate:orders-svc" in sig
    assert jaccard({"a", "b"}, {"b", "c"}) == pytest.approx(1 / 3) and jaccard(set(), {"a"}) == 0.0


def test_only_verified_incidents_are_recalled_and_leave_one_out_works():
    mem = IncidentMemory(Database.memory())
    mem.add("inc-1", "A", report(), ["error_rate:lb", "request_rate:payments-svc"], "escalate", verified=False)
    assert mem.search(["error_rate:lb", "request_rate:payments-svc"]) == []          # unverified: never trusted
    mem.verify("inc-1")
    hit = mem.search(["error_rate:lb", "request_rate:payments-svc"])[0]
    assert hit.incident_id == "inc-1" and hit.similarity == 1.0 and "verified=yes" in hit.line()
    assert mem.search(["error_rate:lb", "request_rate:payments-svc"], exclude="inc-1") == []
    assert mem.search(["memory_bytes:orders-svc"]) == []                              # dissimilar


async def test_memory_solves_a_repeat_fault_the_evidence_alone_cannot():
    s = ALL["hard-03-outage-no-logs"]  # payments is down and the log pipeline is down
    world, alert, gt = build_world(s)
    rt, _ = make_runtime(world, CONFIGS["multi"])
    plain = await LocalOrchestrator(rt).investigate(alert)
    assert plain.report.category != Category.DEPENDENCY_OUTAGE

    world, alert, gt = build_world(s)
    rt, _ = make_runtime(world, CONFIGS["multi-memory"], memory=await seed_memory(0))
    withmem = await LocalOrchestrator(rt).investigate(alert)
    assert (withmem.report.service, withmem.report.category) == (gt.root_cause_service, Category.DEPENDENCY_OUTAGE)
    assert "past incident" in withmem.report.root_cause
    assert withmem.action.tier.value == "read_only"   # memory alone never supplies a write-action target


async def test_poisoned_memory_does_not_override_strong_evidence():
    s = ALL["bad-config-push-lb-timeout-00"]
    world, alert, gt = build_world(s)
    rt, _ = make_runtime(world, CONFIGS["multi"])
    base = await LocalOrchestrator(rt).investigate(alert)
    tokens = signature_from_evidence(rt.board.list(base.incident_id))
    mem = IncidentMemory(Database.memory())  # a verified but WRONG past incident with an identical signature
    mem.add("bad-1", alert.name, report("payments-svc", Category.DEPENDENCY_OUTAGE), tokens, "escalate", verified=True)
    world, alert, gt = build_world(s)
    rt, _ = make_runtime(world, CONFIGS["multi-memory"], memory=mem)
    res = await LocalOrchestrator(rt).investigate(alert)
    assert (res.report.service, res.report.category) == (gt.root_cause_service, gt.category)


async def test_memory_write_and_verify_roundtrip():
    world, alert, gt = build_world(ALL["memory-leak-orders-cache-00"])
    rt, _ = make_runtime(world, CONFIGS["multi-memory"], memory=IncidentMemory(Database.memory()))
    rt.memory_write = True
    res = await LocalOrchestrator(rt).investigate(alert)
    assert rt.memory.search(signature_from_evidence(rt.board.list(res.incident_id)), verified_only=False)   # remembered, but unverified
    assert rt.memory.search(signature_from_evidence(rt.board.list(res.incident_id))) == []
    rt.memory.verify(res.incident_id)
    assert rt.memory.search(signature_from_evidence(rt.board.list(res.incident_id)))[0].category == "resource_leak"
