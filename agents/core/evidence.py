"""Evidence board (claim + raw query + result ref + confidence) and the citation validator."""
from __future__ import annotations

import json
import time
import uuid

from .db import Database
from .models import EvidenceRow, RootCauseReport, Step


class CitationError(ValueError):
    """Raised when a report cites missing/foreign evidence or makes uncited claims."""


class EvidenceBoard:
    def __init__(self, db: Database):
        self.db = db

    # -- incidents ---------------------------------------------------------------
    def open_incident(self, incident_id: str, fingerprint: str = "", alert_json: str = "{}") -> None:
        now = time.time()
        if self.db.execute("SELECT id FROM incidents WHERE id = ?", [incident_id]):
            return
        self.db.insert(
            "incidents",
            dict(id=incident_id, fingerprint=fingerprint, alert_json=alert_json, status="investigating",
                 report_json="", created_at=now, updated_at=now),
            pk="id",
        )

    def set_status(self, incident_id: str, status: str, report: RootCauseReport | None = None) -> None:
        self.db.execute(
            "UPDATE incidents SET status = ?, report_json = ?, updated_at = ? WHERE id = ?",
            [status, report.model_dump_json() if report else "", time.time(), incident_id],
        )

    def get_incident(self, incident_id: str) -> dict | None:
        rows = self.db.execute("SELECT * FROM incidents WHERE id = ?", [incident_id])
        return rows[0] if rows else None

    def list_incidents(self) -> list[dict]:
        return self.db.execute("SELECT id, fingerprint, status, created_at, updated_at FROM incidents ORDER BY created_at DESC")

    # -- artifacts ---------------------------------------------------------------
    def store_artifact(self, incident_id: str, tool: str, arguments: dict, content: str) -> str:
        ref = f"art_{uuid.uuid4().hex[:10]}"
        self.db.insert(
            "artifacts",
            dict(ref=ref, incident_id=incident_id, tool=tool, arguments=json.dumps(arguments, sort_keys=True),
                 content=content, created_at=time.time()),
            pk="ref",
        )
        return ref

    def get_artifact(self, ref: str) -> dict | None:
        rows = self.db.execute("SELECT * FROM artifacts WHERE ref = ?", [ref])
        return rows[0] if rows else None

    # -- evidence ----------------------------------------------------------------
    def add(self, row: EvidenceRow) -> EvidenceRow:
        seq = self.db.insert(
            "evidence",
            dict(incident_id=row.incident_id, agent=row.agent, claim=row.claim, evidence_query=row.evidence_query,
                 evidence_result_ref=row.evidence_result_ref, supports_hypothesis=row.supports_hypothesis,
                 confidence=row.confidence, created_at=row.created_at),
        )
        return row.model_copy(update={"id": f"ev_{seq}"})

    def _to_row(self, r: dict) -> EvidenceRow:
        return EvidenceRow(id=f"ev_{r['seq']}", incident_id=r["incident_id"], agent=r["agent"], claim=r["claim"],
                           evidence_query=r["evidence_query"], evidence_result_ref=r["evidence_result_ref"],
                           supports_hypothesis=r["supports_hypothesis"], confidence=r["confidence"],
                           created_at=r["created_at"])

    def list(self, incident_id: str, hypothesis: str | None = None, agent: str | None = None) -> list[EvidenceRow]:
        sql, params = "SELECT * FROM evidence WHERE incident_id = ?", [incident_id]
        if hypothesis:
            sql += " AND supports_hypothesis = ?"
            params.append(hypothesis)
        if agent:
            sql += " AND agent = ?"
            params.append(agent)
        return [self._to_row(r) for r in self.db.execute(sql + " ORDER BY seq", params)]

    def get(self, incident_id: str, ev_id: str) -> EvidenceRow | None:
        if not ev_id.startswith("ev_") or not ev_id[3:].isdigit():
            return None
        rows = self.db.execute("SELECT * FROM evidence WHERE seq = ? AND incident_id = ?", [int(ev_id[3:]), incident_id])
        return self._to_row(rows[0]) if rows else None

    # -- steps (trace for dashboard/replay) --------------------------------------
    def record_step(self, incident_id: str, step: Step) -> None:
        self.db.insert(
            "steps",
            dict(incident_id=incident_id, agent=step.agent, kind=step.kind, name=step.name,
                 detail=step.detail[:2000], duration_ms=step.duration_ms, ts=step.ts),
        )

    def steps(self, incident_id: str, after: int = 0) -> list[dict]:
        return self.db.execute("SELECT * FROM steps WHERE incident_id = ? AND seq > ? ORDER BY seq", [incident_id, after])

    # -- checkpoints (resume without repeating LLM spend) ------------------------
    def checkpoint_get(self, key: str) -> str | None:
        rows = self.db.execute("SELECT value FROM checkpoints WHERE key = ?", [key])
        return rows[0]["value"] if rows else None

    def checkpoint_put(self, key: str, incident_id: str, value: str) -> None:
        if self.checkpoint_get(key) is None:
            self.db.insert("checkpoints", dict(key=key, incident_id=incident_id, value=value, created_at=time.time()), pk="key")


def validate_report(report: RootCauseReport, board: EvidenceBoard, incident_id: str, require_citations: bool = True) -> float:
    """Reject reports that cite nothing or cite evidence that does not exist for this incident.

    Returns the grounding ratio: share of cited evidence ids that are valid.
    """
    cited = list(report.evidence) + [e for r in report.ruled_out for e in r.evidence]
    if require_citations and not report.evidence:
        raise CitationError("root cause has no evidence citations")
    if not cited:
        return 1.0
    bad = [e for e in cited if board.get(incident_id, e) is None]
    if bad and require_citations:
        raise CitationError(f"unknown evidence ids: {bad}")
    return round((len(cited) - len(bad)) / len(cited), 4)
