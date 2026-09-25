"""Fault definition contract. Every fault has a simulated form (benchmark) and live steps (docker-compose stack)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agents.core.models import Category
from bench.sim.world import Commit, World, fake_sha


@dataclass
class Fault:
    name: str
    alert: str
    category: Category
    defaults: dict[str, Any] = field(default_factory=dict)
    description: str = ""

    def apply_sim(self, world: World, params: dict[str, Any], t_f: float) -> None:
        raise NotImplementedError

    def live_steps(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Declarative steps executed by chaos/live.py against the real stack."""
        raise NotImplementedError

    def merged(self, params: dict[str, Any]) -> dict[str, Any]:
        return {**self.defaults, **params}


def config_commit(world: World, ts: float, service: str, file: str, key: str, old: Any, new: Any, message: str,
                  kind: str = "config", author: str = "sam") -> Commit:
    sha = fake_sha(world.seed, ts, file, key, new)
    diff = (f"diff --git a/{file} b/{file}\n--- a/{file}\n+++ b/{file}\n@@ -1,4 +1,4 @@\n"
            f"-{key}: {old}\n+{key}: {new}\n")
    return world.add_commit(Commit(sha, ts, author, message, kind, service, [file], diff))


def deploy_commit(world: World, ts: float, service: str, message: str, files: list[str], diff: str,
                  author: str = "dana") -> Commit:
    sha = fake_sha(world.seed, ts, service, message)
    return world.add_commit(Commit(sha, ts, author, message, "deploy", service, files, diff))
