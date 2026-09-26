"""A `scenario` label must select the simulated world even when the process is configured for the live stack.

Regression: the dashboard launcher on the docker gateway (NIGHTSHIFT_BACKEND=live) investigated the running, healthy stack instead of the
launched scenario, so every launched incident came back inconclusive.
"""
from __future__ import annotations

import pytest

from agents.core.db import Database
from orchestrator import runtime_factory


def _boom():
    raise AssertionError("live backends must not be built for a scenario-labelled alert")


@pytest.mark.parametrize("backend", ["sim", "live"])
def test_scenario_label_uses_simulated_world(monkeypatch, backend):
    monkeypatch.setenv("NIGHTSHIFT_BACKEND", backend)
    monkeypatch.setenv("NIGHTSHIFT_LLM_PROVIDER", "mock")
    monkeypatch.setattr(runtime_factory, "live_backends", _boom)
    rt, policy = runtime_factory.build_runtime({"scenario": "bad-deploy-n-plus-one-00"}, db=Database("sqlite:///:memory:"))
    assert rt is not None and policy is not None


def test_unlabelled_alert_uses_live_backends_when_live(monkeypatch):
    monkeypatch.setenv("NIGHTSHIFT_BACKEND", "live")
    monkeypatch.setenv("NIGHTSHIFT_LLM_PROVIDER", "mock")
    called = {}
    real = runtime_factory.live_backends

    def spy():
        called["live"] = True
        return real()

    monkeypatch.setattr(runtime_factory, "live_backends", spy)
    runtime_factory.build_runtime({}, db=Database("sqlite:///:memory:"))
    assert called.get("live")
