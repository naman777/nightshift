from __future__ import annotations

import json
import time
from typing import Any, Protocol

import httpx


class LogsBackend(Protocol):
    def now(self) -> float: ...
    async def search(self, service: str | None, contains: str | None, level: str | None,
                     start: float, end: float, limit: int) -> list[dict[str, Any]]: ...


class LokiBackend:
    def __init__(self, url: str = "http://localhost:3100"):
        self.url = url.rstrip("/")

    def now(self) -> float:
        return time.time()

    async def search(self, service, contains, level, start, end, limit):
        sel = f'{{service="{service}"}}' if service else '{service=~".+"}'
        q = sel
        if contains:
            q += f' |= "{contains}"'
        if level:
            q += f' | json | level="{level}"'
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(f"{self.url}/loki/api/v1/query_range", params={
                "query": q, "start": int(start * 1e9), "end": int(end * 1e9), "limit": limit, "direction": "forward"})
            r.raise_for_status()
        out: list[dict[str, Any]] = []
        for stream in r.json()["data"]["result"]:
            for ts, line in stream["values"]:
                try:
                    j = json.loads(line)
                except ValueError:
                    j = {"msg": line, "level": "info"}
                out.append({"ts": int(int(ts) / 1e9), "service": stream["stream"].get("service", service or ""),
                            "level": j.get("level", "info"), "msg": j.get("msg", line)})
        return sorted(out, key=lambda d: d["ts"])[:limit]
