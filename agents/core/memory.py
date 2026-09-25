"""Incident memory: "this looks like INC-12".

Past incidents are stored with a signature (which metric/service pairs were anomalous). A new incident's signature is compared with
stored ones by Jaccard similarity and the closest *verified* matches are handed to the commander as context. Only incidents a human
verified (the approved action ran and resolved it) are trusted, so a wrong diagnosis is never remembered as truth.

Memory helps on repeat faults and cannot help on novel ones; it can also mislead when a lookalike had a different cause. Both effects are
measured in the benchmark (config `multi-memory`), not assumed.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Iterable

from mcp_servers.metrics.backend import CATALOGUE

from .db import Database
from .models import EvidenceRow, RootCauseReport

METRICS = sorted(CATALOGUE, key=len, reverse=True)
SERVICES = sorted({s for v in CATALOGUE.values() for s in v}, key=len, reverse=True)


def signature_from_evidence(rows: Iterable[EvidenceRow]) -> list[str]:
    """Tokens like 'error_rate:lb': every (metric, service) pair mentioned together in a claim."""
    tokens: set[str] = set()
    for r in rows:
        for m in METRICS:
            if re.search(rf"\b{m}\b", r.claim):
                for s in SERVICES:
                    if re.search(rf"(?<![\w-]){re.escape(s)}(?![\w-])", r.claim):
                        tokens.add(f"{m}:{s}")
    return sorted(tokens)


def jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


@dataclass
class Match:
    incident_id: str
    similarity: float
    service: str
    category: str
    root_cause: str
    action_type: str
    verified: bool

    def line(self) -> str:
        return (f"MEMORY inc={self.incident_id} sim={self.similarity:.2f} service={self.service} category={self.category} "
                f"action={self.action_type} verified={'yes' if self.verified else 'no'} :: {self.root_cause}")


class IncidentMemory:
    def __init__(self, db: Database):
        self.db = db

    def add(self, incident_id: str, alert_name: str, report: RootCauseReport, tokens: list[str], action_type: str = "",
            verified: bool = False) -> None:
        self.db.insert("incident_memory", dict(incident_id=incident_id, alert_name=alert_name, service=report.service,
                                               category=report.category.value, root_cause=report.root_cause, action_type=action_type,
                                               tokens=json.dumps(tokens), verified=int(verified), created_at=time.time()))

    def verify(self, incident_id: str) -> None:
        self.db.execute("UPDATE incident_memory SET verified = 1 WHERE incident_id = ?", [incident_id])

    def search(self, tokens: list[str], k: int = 3, min_similarity: float = 0.5, exclude: str | None = None,
               verified_only: bool = True) -> list[Match]:
        want = set(tokens)
        out: list[Match] = []
        for r in self.db.execute("SELECT * FROM incident_memory"):
            if r["incident_id"] == exclude or (verified_only and not r["verified"]):
                continue
            sim = jaccard(want, set(json.loads(r["tokens"])))
            if sim >= min_similarity:
                out.append(Match(r["incident_id"], sim, r["service"], r["category"], r["root_cause"], r["action_type"], bool(r["verified"])))
        return sorted(out, key=lambda m: -m.similarity)[:k]
