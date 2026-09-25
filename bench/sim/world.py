"""A deterministic simulated production world: metrics, logs, deploys, config commits, code, runtime actions.

Fault modules (chaos/faults/*) mutate a World through add_effect / add_log / add_commit / ... so the same fault
definition drives both the offline benchmark and (through its live steps) the real docker-compose stack.
"""
from __future__ import annotations

import hashlib
import random
import re
from dataclasses import dataclass, field
from typing import Any

T_ALERT = 1_780_000_000.0

BASELINES: dict[str, dict[str, tuple[float, float]]] = {
    # metric -> service -> (baseline, noise fraction)
    "error_rate": {"orders-svc": (0.004, 0.25), "payments-svc": (0.003, 0.25), "lb": (0.004, 0.25)},
    "request_rate": {"orders-svc": (120, 0.05), "payments-svc": (80, 0.05), "lb": (240, 0.05)},
    "p99_latency_seconds": {"orders-svc": (0.18, 0.06), "payments-svc": (0.09, 0.06), "lb": (0.2, 0.06)},
    "memory_bytes": {"orders-svc": (230e6, 0.01), "payments-svc": (120e6, 0.01)},
    "cpu_ratio": {"orders-svc": (0.25, 0.06), "payments-svc": (0.15, 0.06), "scheduler": (0.1, 0.1)},
    "db_connections_in_use": {"orders-svc": (8, 0.08), "scheduler": (2, 0.1)},
    "restarts_total": {"orders-svc": (0, 0), "payments-svc": (0, 0)},
    "log_lines_per_second": {"orders-svc": (40, 0.05), "payments-svc": (25, 0.05), "lb": (90, 0.05)},
    "disk_used_ratio": {"orders-svc": (0.35, 0.001)},
    "upstream_healthy": {"lb": (2, 0)},
    "queue_depth": {"scheduler": (5, 0.15)},
    "dependency_latency_p99_seconds": {"orders-svc": (0.09, 0.06)},
}
NAMES = sorted(BASELINES, key=len, reverse=True)

BASE_CODE = {
    "handlers/orders.go": '''package handlers

import (
	"database/sql"
	"net/http"
)

// ListOrders returns the caller's recent orders with their line items.
func (h *Handler) ListOrders(w http.ResponseWriter, r *http.Request) {
	rows, err := h.db.Query("SELECT id, customer_id FROM orders WHERE customer_id = $1 LIMIT 50", customerID(r))
	if err != nil {
		http.Error(w, "db error", 500)
		return
	}
	defer rows.Close()
	orders := loadOrders(rows)
	items, err := h.loadItemsBatch(orders) // single query: WHERE order_id = ANY($1)
	if err != nil {
		http.Error(w, "db error", 500)
		return
	}
	writeJSON(w, orders, items)
}
''',
    "client/payments.go": '''package client

import "time"

// Payments wraps calls to payments-svc. Timeout comes from config.
type Payments struct {
	BaseURL string
	Timeout time.Duration
}

func (p *Payments) Charge(orderID string, cents int) error {
	return p.post("/charge", orderID, cents)
}
''',
    "config/defaults.go": '''package config

const (
	DBPoolSize        = 20
	PaymentsTimeoutMS = 1500
	EnableCache       = false
)
''',
}


@dataclass
class Effect:
    metric: str
    service: str
    start: float
    mode: str = "mult"  # mult | add | set
    value: float = 1.0
    ramp: float = 30.0
    end: float | None = None


@dataclass
class LogSource:
    service: str
    level: str
    template: str  # may use {i}, {n}, {ms}
    start: float
    end: float
    every_s: float = 5.0
    ms_base: int = 100


@dataclass
class Commit:
    sha: str
    ts: float
    author: str
    message: str
    kind: str  # deploy | config | flag
    service: str = ""
    files: list[str] = field(default_factory=list)
    diff: str = ""


def _hash01(*parts: Any) -> float:
    h = hashlib.md5("|".join(map(str, parts)).encode()).digest()
    return int.from_bytes(h[:4], "big") / 2**32


def fake_sha(*parts: Any) -> str:
    return hashlib.sha1("|".join(map(str, parts)).encode()).hexdigest()[:8]


class World:
    def __init__(self, seed: int = 0, t_alert: float = T_ALERT):
        self.seed = seed
        self.t_alert = t_alert
        self.effects: list[Effect] = []
        self.sources: list[LogSource] = []
        self.commits: list[Commit] = []
        self.code = dict(BASE_CODE)
        self.test_result: dict[str, Any] = {"passed": True, "output": "ok  \torders-svc/...\t0.412s"}
        self.actions: list[dict[str, Any]] = []
        self.outages: set[str] = set()  # telemetry sources that are down: metrics | logs | deploys | configs
        self.facts: dict[str, Any] = {}
        self.alert_name = ""
        self.alert_service = ""
        self._history()

    # -- clock ------------------------------------------------------------------
    def now(self) -> float:
        return self.t_alert + 60

    # -- baseline history (harmless, days old) -------------------------------------
    def _history(self) -> None:
        rnd = random.Random(self.seed)
        for i, (svc, msg) in enumerate([("payments-svc", "payments: refactor receipt renderer"),
                                        ("orders-svc", "orders: add index hint to list query"),
                                        ("lb", "lb: bump access-log buffer")]):
            ts = self.t_alert - 86400 * (1 + i) - rnd.randint(0, 3600)
            self.add_commit(Commit(fake_sha("hist", i, self.seed), ts, rnd.choice(["dana", "li", "sam"]), msg, "deploy", svc))
        for svc in ("orders-svc", "payments-svc", "lb"):
            self.sources.append(LogSource(svc, "info", "request handled path=/{p} status=200 latency={ms}ms", self.t_alert - 7200,
                                          self.t_alert + 600, every_s=15, ms_base=80))

    # -- mutation API for faults ------------------------------------------------------
    def add_effect(self, metric: str, service: str, start: float, mode: str = "mult", value: float = 1.0,
                   ramp: float = 30.0, end: float | None = None) -> None:
        self.effects.append(Effect(metric, service, start, mode, value, ramp, end))

    def add_log(self, service: str, level: str, template: str, start: float, end: float | None = None,
                every_s: float = 5.0, ms_base: int = 100) -> None:
        self.sources.append(LogSource(service, level, template, start, end or self.now(), every_s, ms_base))

    def add_commit(self, c: Commit) -> Commit:
        self.commits.append(c)
        return c

    # -- metrics ---------------------------------------------------------------------
    def value(self, metric: str, service: str, t: float) -> float:
        base, noise = BASELINES[metric][service]
        v = base * (1 + noise * (2 * _hash01(self.seed, metric, service, int(t // 15)) - 1))
        for e in self.effects:
            if e.metric != metric or e.service != service or t < e.start:
                continue
            prog = min(1.0, (t - e.start) / max(e.ramp, 1.0))
            if e.end is not None and t > e.end:
                prog = max(0.0, 1 - (t - e.end) / max(e.ramp, 1.0))
            if e.mode == "mult":
                v *= 1 + (e.value - 1) * prog
            elif e.mode == "add":
                v += e.value * prog
            else:
                v += (e.value - v) * prog
        return max(v, 0.0)

    def query_range(self, query: str, start: float, end: float, step: float) -> list[tuple[dict[str, str], list[tuple[float, float]]]]:
        metric = next((n for n in NAMES if re.search(rf"\b{n}\b", query)), None)
        if metric is None:
            return []
        m = re.search(r'service\s*(=~?)\s*"([^"]+)"', query)
        wanted = None
        if m:
            wanted = set(m.group(2).split("|"))
        out = []
        step = max(step, 5.0)
        n = int((end - start) / step) + 1
        for svc in BASELINES[metric]:
            if wanted and svc not in wanted:
                continue
            pts = [(start + i * step, self.value(metric, svc, start + i * step)) for i in range(n)]
            out.append(({"__name__": metric, "service": svc}, pts))
        return out

    # -- logs ------------------------------------------------------------------------
    def search_logs(self, service: str | None, contains: str | None, level: str | None, start: float, end: float,
                    limit: int) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for s in self.sources:
            if service and s.service != service:
                continue
            if level and s.level != level:
                continue
            t = max(start, s.start)
            t = s.start + ((t - s.start) // s.every_s) * s.every_s
            i = 0
            while t <= min(end, s.end) and len(rows) < 8000:
                if t >= start:
                    ms = int(s.ms_base * (0.7 + 0.6 * _hash01(self.seed, s.template, int(t))))
                    msg = s.template.format(i=i, n=int(t) % 97, ms=ms, p=("orders", "orders/list", "health")[int(t) % 3],
                                            **{k: v for k, v in self.facts.items() if isinstance(v, (str, int, float))})
                    if not contains or contains.lower() in msg.lower():
                        rows.append({"ts": int(t), "service": s.service, "level": s.level, "msg": msg})
                t += s.every_s
                i += 1
        rows.sort(key=lambda r: r["ts"])
        return rows[:limit] if limit < 500 else rows[-limit:]

    # -- changes ---------------------------------------------------------------------
    def find_commit(self, sha: str) -> Commit | None:
        return next((c for c in self.commits if c.sha.startswith(sha[:8])), None)
