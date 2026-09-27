from __future__ import annotations

import math
from typing import Any

from agents.core.models import Tier

from ..base import Server, schema
from ..common import downsample, onset, summarize, to_ts
from .backend import MetricsBackend


def build(backend: MetricsBackend) -> Server:
    srv = Server("metrics", backend)

    @srv.tool("query_range", "Query a metric over a time range. `query` is a metric selector such as "
              "error_rate{service=\"orders-svc\"}. Times are unix seconds or relative like '-30m'. Returns per-series summary and a downsampled series.",
              schema({"query": ("string", "metric selector, e.g. p99_latency_seconds{service=\"orders-svc\"}"),
                      "start": ("string", "start time, e.g. '-30m'"), "end": ("string", "end time, default 'now'"),
                      "step": ("number", "step seconds, default 30")}, ["query"]))
    async def query_range(b: MetricsBackend, query: str, start: str = "-30m", end: str = "now", step: float = 30) -> Any:
        now = b.now()
        s, e = to_ts(start, now), to_ts(end, now)
        res = await b.query_range(query, s, e, float(step))
        out = []
        for labels, pts in res:
            o = onset(pts)
            out.append({"labels": labels, "summary": summarize(pts), "onset_ts": o,
                        "points": [[int(t), round(v, 4)] for t, v in downsample(pts)]})
        return {"query": query, "start": int(s), "end": int(e), "series": out}

    @srv.tool("top_anomalies", "Scan all known metrics for series that deviate from their own baseline in the last window. "
              "Returns the most anomalous series with the time the deviation started. Use this first to find where to look.",
              schema({"window_minutes": ("number", "look-back window, default 30")}))
    async def top_anomalies(b: MetricsBackend, window_minutes: float = 30) -> Any:
        now = b.now()
        found: list[dict[str, Any]] = []
        for metric, services in b.catalogue().items():
            for svc in services:
                q = f'{metric}{{service="{svc}"}}'
                for labels, pts in await b.query_range(q, now - window_minutes * 60, now, 30.0):
                    if len(pts) < 8:
                        continue
                    base = summarize(pts[: int(len(pts) * 0.4)])
                    recent = summarize(pts[-max(3, len(pts) // 6):])
                    o = onset(pts)
                    if o is None:
                        continue
                    ratio = min(1000.0, max(0.001, (recent["avg"] + 1e-9) / (base["avg"] + 1e-9)))
                    found.append({"metric": metric, "service": svc, "baseline_avg": base["avg"], "recent_avg": recent["avg"],
                                  "change_ratio": round(ratio, 2), "started_at": int(o)})
        found.sort(key=lambda d: abs(math.log(d["change_ratio"])), reverse=True)
        # known_metrics tells the model which metric names/services exist, so it queries recorded names instead of guessing raw ones
        return {"now": int(now), "anomalies": found[:10], "known_metrics": b.catalogue()}

    @srv.tool("compare_windows", "Compare a metric's average/max between two windows (e.g. before vs after a suspected change time).",
              schema({"query": ("string", "metric selector"), "a_start": ("string", ""), "a_end": ("string", ""),
                      "b_start": ("string", ""), "b_end": ("string", "")}, ["query", "a_start", "a_end", "b_start", "b_end"]))
    async def compare_windows(b: MetricsBackend, query: str, a_start: str, a_end: str, b_start: str, b_end: str) -> Any:
        now = b.now()
        out = {}
        for name, (s, e) in {"a": (a_start, a_end), "b": (b_start, b_end)}.items():
            res = await b.query_range(query, to_ts(s, now), to_ts(e, now), 30.0)
            out[name] = summarize(res[0][1]) if res else {"count": 0}
        if out["a"].get("count") and out["b"].get("count"):
            out["ratio_b_over_a"] = round((out["b"]["avg"] + 1e-9) / (out["a"]["avg"] + 1e-9), 3)
        return {"query": query, **out}

    return srv


if __name__ == "__main__":  # pragma: no cover
    import os
    from .backend import PrometheusBackend

    build(PrometheusBackend(os.environ.get("PROMETHEUS_URL", "http://localhost:9090"))).serve_stdio()
