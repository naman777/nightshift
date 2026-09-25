"""Tiny DB layer: SQLite for local/tests, Postgres in compose. One SQL dialect (`?` placeholders)."""
from __future__ import annotations

import os
import sqlite3
import threading
from typing import Any, Iterable

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS incidents (
        id TEXT PRIMARY KEY, fingerprint TEXT, alert_json TEXT, status TEXT,
        report_json TEXT, created_at REAL, updated_at REAL)""",
    """CREATE TABLE IF NOT EXISTS evidence (
        seq INTEGER PRIMARY KEY AUTOINCREMENT, incident_id TEXT, agent TEXT, claim TEXT,
        evidence_query TEXT, evidence_result_ref TEXT, supports_hypothesis TEXT,
        confidence REAL, created_at REAL)""",
    """CREATE TABLE IF NOT EXISTS artifacts (
        ref TEXT PRIMARY KEY, incident_id TEXT, tool TEXT, arguments TEXT, content TEXT, created_at REAL)""",
    """CREATE TABLE IF NOT EXISTS audit_log (
        seq INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, incident_id TEXT, agent TEXT, tool TEXT,
        tier TEXT, arguments TEXT, decision TEXT, reason TEXT, evidence_ids TEXT, dry_run INTEGER)""",
    """CREATE TABLE IF NOT EXISTS checkpoints (
        key TEXT PRIMARY KEY, incident_id TEXT, value TEXT, created_at REAL)""",
    """CREATE TABLE IF NOT EXISTS incident_memory (
        seq INTEGER PRIMARY KEY AUTOINCREMENT, incident_id TEXT, alert_name TEXT, service TEXT, category TEXT,
        root_cause TEXT, action_type TEXT, tokens TEXT, verified INTEGER, created_at REAL)""",
    """CREATE TABLE IF NOT EXISTS steps (
        seq INTEGER PRIMARY KEY AUTOINCREMENT, incident_id TEXT, agent TEXT, kind TEXT,
        name TEXT, detail TEXT, duration_ms INTEGER, ts REAL)""",
]

PG_FIXUPS = {"INTEGER PRIMARY KEY AUTOINCREMENT": "SERIAL PRIMARY KEY", "REAL": "DOUBLE PRECISION"}


class Database:
    def __init__(self, url: str | None = None):
        self.url = url or os.environ.get("NIGHTSHIFT_DB_URL", "sqlite:///nightshift.db")
        self.is_pg = self.url.startswith("postgres")
        self._lock = threading.RLock()
        if self.is_pg:
            import psycopg

            self._conn = psycopg.connect(self.url, autocommit=True)
        else:
            path = self.url.removeprefix("sqlite:///") or ":memory:"
            self._conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
            self._conn.row_factory = sqlite3.Row
        self.migrate()

    @classmethod
    def memory(cls) -> "Database":
        return cls("sqlite:///:memory:")

    def _sql(self, sql: str) -> str:
        if self.is_pg:
            for a, b in PG_FIXUPS.items():
                sql = sql.replace(a, b)
            return sql.replace("?", "%s")
        return sql

    def migrate(self) -> None:
        for stmt in SCHEMA:
            self.execute(stmt)
        if self.is_pg:
            for op in ("UPDATE", "DELETE"):
                self.execute(f"CREATE OR REPLACE RULE audit_no_{op.lower()} AS ON {op} TO audit_log DO INSTEAD NOTHING")
        else:
            for op in ("UPDATE", "DELETE"):
                self.execute(f"CREATE TRIGGER IF NOT EXISTS audit_no_{op.lower()} BEFORE {op} ON audit_log "
                             "BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END")

    def execute(self, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(self._sql(sql), tuple(params))
            if cur.description is None:
                self._last_id = getattr(cur, "lastrowid", None)
                return []
            cols = [c[0] for c in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]

    def insert(self, table: str, row: dict[str, Any], pk: str = "seq") -> int | None:
        cols = ", ".join(row)
        marks = ", ".join("?" for _ in row)
        with self._lock:
            if self.is_pg:
                out = self.execute(f"INSERT INTO {table} ({cols}) VALUES ({marks}) RETURNING {pk}", row.values())
                return out[0][pk] if out else None
            self.execute(f"INSERT INTO {table} ({cols}) VALUES ({marks})", row.values())
            return self._last_id

    def close(self) -> None:
        self._conn.close()
