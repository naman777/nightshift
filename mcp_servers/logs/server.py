from __future__ import annotations

from collections import defaultdict
from typing import Any

from ..base import Server, schema
from ..common import signature, to_ts
from .backend import LogsBackend

_COMMON = {"service": ("string", "service name, e.g. orders-svc; omit for all"),
           "start": ("string", "e.g. '-30m'"), "end": ("string", "default 'now'")}


def build(backend: LogsBackend) -> Server:
    srv = Server("logs", backend)

    @srv.tool("search", "Search log lines. Filter by service, substring and level (error|warn|info). Returns up to `limit` lines.",
              schema({**_COMMON, "contains": ("string", "substring to match"), "level": ("string", "error|warn|info"),
                      "limit": ("number", "max lines, default 20")}))
    async def search(b: LogsBackend, service: str | None = None, contains: str | None = None, level: str | None = None,
                     start: str = "-30m", end: str = "now", limit: int = 20) -> Any:
        now = b.now()
        lines = await b.search(service, contains, level, to_ts(start, now), to_ts(end, now), int(limit))
        return {"count": len(lines), "lines": lines}

    @srv.tool("cluster_errors", "Group error/warn lines by message signature (numbers and ids normalised). Shows count, first_seen and a sample "
              "for each signature: use it to spot NEW error types and when they began.",
              schema({**_COMMON}))
    async def cluster_errors(b: LogsBackend, service: str | None = None, start: str = "-30m", end: str = "now") -> Any:
        now = b.now()
        s, e = to_ts(start, now), to_ts(end, now)
        rows = [*await b.search(service, None, "error", s, e, 2000), *await b.search(service, None, "warn", s, e, 2000)]
        groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
        for r in rows:
            groups[(r["service"], signature(r["msg"]))].append(r)
        out = []
        for (svc, sig), rs in groups.items():
            rs.sort(key=lambda d: d["ts"])
            out.append({"service": svc, "signature": sig, "count": len(rs), "first_seen": rs[0]["ts"],
                        "last_seen": rs[-1]["ts"], "level": rs[0]["level"], "sample": rs[0]["msg"][:300]})
        out.sort(key=lambda d: d["count"], reverse=True)
        return {"clusters": out[:12]}

    @srv.tool("tail", "Most recent log lines for a service.",
              schema({"service": ("string", "service name"), "n": ("number", "number of lines, default 20")}, ["service"]))
    async def tail(b: LogsBackend, service: str, n: int = 20) -> Any:
        now = b.now()
        lines = await b.search(service, None, None, now - 600, now, 5000)
        return {"count": min(int(n), len(lines)), "lines": lines[-int(n):]}

    return srv
