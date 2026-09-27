from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Protocol

import httpx


class LogsBackend(Protocol):
    def now(self) -> float: ...
    async def search(self, service: str | None, contains: str | None, level: str | None,
                     start: float, end: float, limit: int) -> list[dict[str, Any]]: ...


_PLAIN_LEVEL = re.compile(r"\[(DEBUG|INFO|WARN|WARNING|ERROR|FATAL)\s*\]", re.I)
# a level name as the model/tools use it (short form) -> the bracket-text variants a real app actually writes. MariaDB logs
# "[Warning]", not "[WARN]"; without this a level="warn" query silently excludes every MariaDB warning (an access-denied
# auth failure among them) even though the line is right there in Loki -- a real bug, not a missing capability.
_LEVEL_QUERY_ALIASES = {"warn": "warn(?:ing)?"}
_LEVEL_NORMALIZE = {"warning": "warn"}


class LokiBackend:
    def __init__(self, url: str = "http://localhost:3100", plain: bool | None = None):
        self.url = url.rstrip("/")
        self.plain = os.environ.get("LOKI_PLAIN_TEXT") == "1" if plain is None else plain

    def now(self) -> float:
        return time.time()

    async def search(self, service, contains, level, start, end, limit):
        sel = f'{{service="{service}"}}' if service else '{service=~".+"}'
        q = sel
        if contains:
            q += f' |= "{contains}"'
        if level and not self.plain:
            q += f' | json | level="{level}"'
        elif level:  # plain-text logs: match the bracketed level token, e.g. "[ERROR]" / "[WARN ]" / "[Warning]"
            frag = _LEVEL_QUERY_ALIASES.get(level.lower(), re.escape(level))
            q += f' |~ "(?i)\\\\[{frag}\\\\s*\\\\]|level={level}"'
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
                    m = _PLAIN_LEVEL.search(line)
                    raw = m.group(1).lower() if m else "info"
                    j = {"msg": line, "level": _LEVEL_NORMALIZE.get(raw, raw)}
                out.append({"ts": int(int(ts) / 1e9), "service": stream["stream"].get("service", service or ""),
                            "level": j.get("level", "info"), "msg": j.get("msg", line)})
        return sorted(out, key=lambda d: d["ts"])[:limit]
