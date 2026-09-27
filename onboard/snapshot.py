"""State snapshot attached to every investigated alert: what each catalogued series is now, what it was 30 minutes ago, and when it last changed.

It is deterministic (no model) and answers the first thing an on-call engineer checks: "what flipped, and when?". Series that did not change are
collapsed into one line so the model is not buried in steady state.
"""
from __future__ import annotations

import json
import os
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

_LABELS = ("service", "instance", "backend", "name")


def _label(metric: str, labels: dict[str, str]) -> str:
    inner = ",".join(f"{k}={labels[k]}" for k in _LABELS if labels.get(k))
    return f"{metric}{{{inner}}}"


def _hhmmss(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%H:%M:%S")


def summarize_series(metric: str, labels: dict[str, str], pts: list[tuple[float, float]]) -> tuple[bool, str]:
    """Returns (changed, line). Compares the median of the first fifth of the window with the median of the newest three samples, so a single-sample blip is not a change; a move counts
    when it exceeds 25% of the larger level and an absolute floor of 0.01 (ignores microsecond latency wobble; a 0/1 flip is always a change)."""
    head = statistics.median(v for _, v in pts[:max(1, len(pts) // 5)])
    tail = statistics.median(v for _, v in pts[-3:])  # the newest ~45 s: recent enough to catch a fresh flip, long enough to ignore a one-sample blip
    tol = max(0.25 * max(abs(head), abs(tail)), 0.01)
    if abs(tail - head) <= tol:
        return False, _label(metric, labels)
    # the change happened after the last sample that still looked like the old level
    moved = pts[-1][0]
    for t, v in reversed(pts):
        if abs(v - head) <= tol:
            break
        moved = t
    return True, f"{_label(metric, labels)} now={pts[-1][1]:.4g}, {int((pts[-1][0] - pts[0][0]) / 60)}m ago={head:.4g}, moved at {_hhmmss(moved)} UTC"


async def build_snapshot(prom_url: str, catalogue_path: str | None = None, window_s: int = 1800, step_s: int = 15, max_lines: int = 30) -> str:
    catalogue: dict[str, list[str]] = json.loads(Path(catalogue_path).read_text(encoding="utf8")) if catalogue_path else {}
    now = time.time()
    changed: list[tuple[float, str]] = []
    steady: list[str] = []
    async with httpx.AsyncClient(timeout=10) as c:
        for metric in catalogue:
            r = await c.get(f"{prom_url}/api/v1/query_range", params={"query": metric, "start": now - window_s, "end": now, "step": step_s})
            r.raise_for_status()
            for s in r.json()["data"]["result"]:
                pts = [(float(t), float(v)) for t, v in s["values"] if v not in ("NaN", "+Inf", "-Inf")]
                if len(pts) < 2:
                    continue
                is_changed, line = summarize_series(metric, s["metric"], pts)
                if is_changed:
                    changed.append((pts[-1][0], line))
                else:
                    steady.append(f"{_label(metric, s['metric'])}={pts[-1][1]:.4g}")
    lines = [f"STATE SNAPSHOT at {_hhmmss(now)} UTC (window {window_s // 60}m; series that moved, newest information first):"]
    lines += [f"  CHANGED {ln}" for _, ln in changed[:max_lines]] or ["  (no catalogued series changed in the window)"]
    if steady:
        lines.append("  STEADY " + "; ".join(steady[:60]))
    return "\n".join(lines)


if __name__ == "__main__":  # python -m onboard.snapshot  (prints the snapshot for the current Prometheus)
    import asyncio

    print(asyncio.run(build_snapshot(os.environ.get("PROMETHEUS_URL", "http://127.0.0.1:9090"), os.environ.get("NIGHTSHIFT_CATALOGUE"))))
