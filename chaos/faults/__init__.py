from __future__ import annotations

from importlib import import_module

from .base import Fault

NAMES = ["bad_config_push", "bad_deploy", "slow_dependency", "dependency_outage", "memory_leak",
         "db_connection_exhaustion", "crashed_replica", "scheduler_backlog", "log_flood", "noisy_neighbour"]


def get_fault(name: str) -> Fault:
    if name not in NAMES:
        raise KeyError(f"unknown fault: {name}. known: {NAMES}")
    return import_module(f"chaos.faults.{name}").FAULT


def all_faults() -> dict[str, Fault]:
    return {n: get_fault(n) for n in NAMES}
