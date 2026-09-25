"""Metrics backend: Protocol + live Prometheus implementation."""
from __future__ import annotations

import time
from typing import Protocol

import httpx

Point = tuple[float, float]
# name -> services it exists for. Mirrors observability/prometheus/rules/recording.yml
CATALOGUE: dict[str, list[str]] = {
    "error_rate": ["orders-svc", "payments-svc", "lb"],
    "request_rate": ["orders-svc", "payments-svc", "lb"],
    "p99_latency_seconds": ["orders-svc", "payments-svc", "lb"],
    "memory_bytes": ["orders-svc", "payments-svc"],
    "cpu_ratio": ["orders-svc", "payments-svc", "scheduler"],
    "db_connections_in_use": ["orders-svc", "scheduler"],
    "restarts_total": ["orders-svc", "payments-svc"],
    "log_lines_per_second": ["orders-svc", "payments-svc", "lb"],
    "disk_used_ratio": ["orders-svc"],
    "upstream_healthy": ["lb"],
    "queue_depth": ["scheduler"],
    "dependency_latency_p99_seconds": ["orders-svc"],
}


class MetricsBackend(Protocol):
    def now(self) -> float: ...
    async def query_range(self, query: str, start: float, end: float, step: float) -> list[tuple[dict[str, str], list[Point]]]: ...
    def catalogue(self) -> dict[str, list[str]]: ...


class PrometheusBackend:
    def __init__(self, url: str = "http://localhost:9090"):
        self.url = url.rstrip("/")

    def now(self) -> float:
        return time.time()

    def catalogue(self) -> dict[str, list[str]]:
        return CATALOGUE

    async def query_range(self, query, start, end, step):
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(f"{self.url}/api/v1/query_range", params={"query": query, "start": start, "end": end, "step": step})
            r.raise_for_status()
            data = r.json()["data"]["result"]
        return [(s["metric"], [(float(t), float(v)) for t, v in s["values"]]) for s in data]
