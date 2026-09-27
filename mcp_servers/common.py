"""Helpers shared by MCP servers: time parsing, series summarisation, log-signature clustering."""
from __future__ import annotations

import re
import statistics
from datetime import datetime, timezone
from typing import Any

_REL = re.compile(r"^-?(\d+(?:\.\d+)?)([smhd])$")
_UNIT = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def to_ts(value: Any, now: float, default: float | None = None) -> float:
    """Accepts unix seconds, relative like '-15m' / '15m' (meaning that long before `now`), or an ISO 8601 date/datetime
    string -- models reach for absolute timestamps despite the docs saying to use relative ones, and rejecting that outright
    (as a bare `float(s)` on a date string does) makes a whole tool call fail instead of just parsing it."""
    if value in (None, ""):
        return now if default is None else default
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if s == "now":
        return now
    m = _REL.match(s)
    if m:
        return now - float(m.group(1)) * _UNIT[m.group(2)]
    try:
        return float(s)
    except ValueError:
        pass
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).timestamp()
    except ValueError:
        raise ValueError(f"unrecognised time value {value!r}: use unix seconds, relative ('-30m'), or ISO 8601") from None


def downsample(points: list[tuple[float, float]], n: int = 24) -> list[tuple[float, float]]:
    if len(points) <= n:
        return points
    step = (len(points) - 1) / (n - 1)
    return [points[round(i * step)] for i in range(n)]


def summarize(points: list[tuple[float, float]]) -> dict[str, Any]:
    if not points:
        return {"count": 0}
    vals = [v for _, v in points]
    return {
        "count": len(vals), "min": round(min(vals), 4), "max": round(max(vals), 4),
        "avg": round(statistics.fmean(vals), 4), "first": round(vals[0], 4), "last": round(vals[-1], 4),
    }


_SIG_SUBS = [
    (re.compile(r"\b[0-9a-f]{7,40}\b"), "<hex>"),
    (re.compile(r"\b\d+(\.\d+)?(ms|s|m|MB|KB|%)?\b"), "<n>"),
    (re.compile(r"(order|user|req|trace)[-_]?id=\S+"), r"\1_id=<id>"),
]


def signature(msg: str) -> str:
    for rx, sub in _SIG_SUBS:
        msg = rx.sub(sub, msg)
    return msg[:160]


def onset(points: list[tuple[float, float]], baseline_frac: float = 0.4, k: float = 3.0) -> float | None:
    """First timestamp where the series leaves its baseline band (mean +/- k*std, with a small floor)."""
    n = max(3, int(len(points) * baseline_frac))
    if len(points) <= n:
        return None
    base = [v for _, v in points[:n]]
    mu = statistics.fmean(base)
    sd = max(statistics.pstdev(base), abs(mu) * 0.05, 1e-9)
    run = 0
    for i in range(n, len(points)):
        if abs(points[i][1] - mu) > k * sd:
            run += 1
            if run >= 2:
                return points[i - 1][0]
        else:
            run = 0
    return None
