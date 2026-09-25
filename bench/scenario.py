"""Scenario file format, loader, and World builder."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from agents.core.models import Alert, Category
from bench.sim.world import World
from chaos.faults import get_fault
from chaos.herrings import apply_herring

SCENARIO_DIR = Path(__file__).parent / "scenarios"


class GroundTruth(BaseModel):
    root_cause: str
    root_cause_service: str
    category: Category
    correct_remediations: list[str]
    unsafe_actions: list[str] = Field(default_factory=lambda: ["restart_postgres", "scale_to_zero", "delete_data"])


class Scenario(BaseModel):
    id: str
    fault: str
    params: dict[str, Any] = Field(default_factory=dict)
    red_herring: dict[str, Any] | None = None
    expected_alert: str
    ground_truth: GroundTruth
    time_limit_s: int = 300
    split: str = "dev"  # dev | heldout
    smoke: bool = False
    alert_delay_s: int = 300
    seed: int = 0


class _Safe(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def load_scenario(path: Path) -> Scenario:
    return Scenario(**yaml.safe_load(path.read_text(encoding="utf8")))


def load_all(directory: Path = SCENARIO_DIR) -> list[Scenario]:
    return [load_scenario(p) for p in sorted(directory.glob("*.yaml"))]


def select(scenarios: list[Scenario], split: str = "all") -> list[Scenario]:
    if split == "all":
        return scenarios
    if split == "smoke":
        return [s for s in scenarios if s.smoke]
    return [s for s in scenarios if s.split == split]


def build_world(s: Scenario) -> tuple[World, Alert, GroundTruth]:
    w = World(seed=s.seed or int(hashlib.md5(s.id.encode()).hexdigest()[:6], 16) % 10_000)
    t_f = w.t_alert - s.alert_delay_s
    fault = get_fault(s.fault)
    fault.apply_sim(w, s.params, t_f)
    if s.red_herring:
        apply_herring(w, s.red_herring, t_f)
    w.facts.update({k: v for k, v in fault.merged(s.params).items() if isinstance(v, (str, int, float))} | w.facts)
    gt = s.ground_truth.model_copy(update={"root_cause": s.ground_truth.root_cause.format_map(_Safe(w.facts))})
    alert = Alert(fingerprint=f"fp-{s.id}", name=w.alert_name or s.expected_alert, service=w.alert_service or "orders-svc",
                  started_at=w.t_alert, labels={"alertname": w.alert_name or s.expected_alert, "service": w.alert_service},
                  annotations={"summary": f"{w.alert_name} firing for {w.alert_service}"})
    return w, alert, gt
