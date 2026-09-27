"""Shadow-mode watcher for a real host: polls Prometheus for firing alerts and investigates each new one.

No Alertmanager, Postgres or Temporal needed: one process, one SQLite file. Write actions are RECORDED by the policy layer
(benchmark_mode) and never executed, so pointing this at a production box cannot change it. Each investigation is saved to
`reports/<timestamp>_<alert>_<service>.{json,md}` with the timings that matter for onboarding:

  fired_at      Prometheus `activeAt` (when the condition first became true)
  detected_at   when this watcher first saw the alert firing
  reported_at   when the diagnosis was finished

    python -m onboard.watch            # run forever
    python -m onboard.watch --once     # investigate whatever is firing now, then exit
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from agents.core.models import Alert
from agents.pipeline import LocalOrchestrator
from onboard.snapshot import build_snapshot
from orchestrator.runtime_factory import build_runtime

PROM = os.environ.get("PROMETHEUS_URL", "http://127.0.0.1:9090")
REPORTS = Path(os.environ.get("NIGHTSHIFT_REPORTS", "reports"))


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _parse_active_at(s: str) -> float:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


async def firing_alerts() -> list[dict]:
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(f"{PROM}/api/v1/alerts")
        r.raise_for_status()
    return [a for a in r.json()["data"]["alerts"] if a["state"] == "firing"]


def _key(a: dict) -> str:
    return f"{a['labels'].get('alertname')}|{a['labels'].get('service')}|{a['activeAt']}"


def group_by_service(alerts: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for a in alerts:
        out.setdefault(a["labels"].get("service", "unknown"), []).append(a)
    return out


def merge(members: list[dict]) -> dict:
    """One alert for several that fired for the same service: names joined, earliest start, every summary kept."""
    members = sorted(members, key=lambda m: (m["labels"].get("severity") != "critical", m["activeAt"]))
    names = [m["labels"].get("alertname", "unknown") for m in members]
    summaries = "; ".join(f"{m['labels'].get('alertname')}: {m.get('annotations', {}).get('summary', '')}" for m in members)
    return {"labels": {**members[0]["labels"], "alertname": "+".join(names)}, "annotations": {"summary": summaries},
            "activeAt": min(m["activeAt"] for m in members), "state": "firing"}


def to_alert(a: dict) -> Alert:
    labels = {k: str(v) for k, v in a["labels"].items()}
    return Alert(fingerprint=f"{labels.get('alertname')}-{labels.get('service', '')}-{int(_parse_active_at(a['activeAt']))}",
                 name=labels.get("alertname", "unknown"), service=labels.get("service", "unknown"), severity=labels.get("severity", "warning"),
                 started_at=_parse_active_at(a["activeAt"]), labels=labels, annotations={k: str(v) for k, v in a.get("annotations", {}).items()})


def render_md(alert: Alert, res, timings: dict) -> str:
    r = res.report
    lines = [f"# {alert.name} on `{alert.service}`", "",
             f"- alert condition first true: {_iso(timings['fired_at'])}",
             f"- watcher detected: {_iso(timings['detected_at'])} (+{timings['detected_at'] - timings['fired_at']:.0f}s)",
             f"- diagnosis finished: {_iso(timings['reported_at'])} (investigation took {timings['investigation_s']:.1f}s)",
             f"- model: {os.environ.get('NIGHTSHIFT_COMMANDER_MODEL', 'mock')} / prompt {os.environ.get('NIGHTSHIFT_PROMPT_VERSION', 'latest')}"
             f" · llm calls {res.usage.llm_calls} · tool calls {res.usage.tool_calls} · cost ${res.usage.cost_usd:.4f}", "",
             f"## Root cause ({r.category.value}, confidence {r.confidence:.2f}, service `{r.service}`)", "", r.root_cause, "", "## Evidence", ""]
    lines += [f"- {e}" for e in r.evidence]
    if r.ruled_out:
        lines += ["", "## Ruled out", ""] + [f"- {x.hypothesis}" for x in r.ruled_out]
    if r.ranked:
        lines += ["", "## Alternatives", ""] + [f"- {x.root_cause} ({x.category.value}, {x.confidence:.2f})" for x in r.ranked]
    a = res.action
    lines += ["", "## Proposed action (shadow mode: recorded, not executed)", "",
              f"`{a.type}` target `{a.target}` params `{json.dumps(a.params)}` tier `{a.tier.value}`" if a else "none"]
    return "\n".join(lines) + "\n"


async def investigate(a: dict, detected_at: float, mode: str) -> Path:
    try:  # deterministic "what flipped and when" summary; the investigation still runs without it
        snap = await build_snapshot(PROM, os.environ.get("NIGHTSHIFT_CATALOGUE"))
        a = {**a, "annotations": {**a.get("annotations", {}), "state_snapshot": snap}}
    except Exception as e:
        print(f"snapshot failed: {type(e).__name__}: {e}", flush=True)
    alert = to_alert(a)
    # each service can have its own change history (e.g. the live repo vs. the sandbox's config repo)
    repos = json.loads(os.environ.get("NIGHTSHIFT_CONFIG_REPOS", "{}"))
    if alert.service in repos:
        os.environ["CONFIG_REPO"] = repos[alert.service]
    roots = json.loads(os.environ.get("NIGHTSHIFT_CODE_ROOTS", "{}"))
    if alert.service in roots:
        os.environ["CODE_ROOT"] = roots[alert.service]
    rt, _policy = build_runtime(alert.labels, benchmark_mode=True)
    t0 = time.time()
    res = await LocalOrchestrator(rt).investigate(alert, mode)
    t1 = time.time()
    timings = {"fired_at": alert.started_at, "detected_at": detected_at, "reported_at": t1, "investigation_s": t1 - t0}
    REPORTS.mkdir(parents=True, exist_ok=True)
    stem = REPORTS / f"{datetime.fromtimestamp(t1).strftime('%Y%m%d-%H%M%S')}_{alert.name}_{alert.service}"
    stem.with_suffix(".json").write_text(json.dumps({
        "alert": alert.model_dump(mode="json"), "timings": timings, "incident_id": res.incident_id, "mode": mode,
        "report": res.report.model_dump(mode="json"), "action": res.action.model_dump(mode="json") if res.action else None,
        "usage": res.usage.model_dump(mode="json"),
        "findings": [f.model_dump(mode="json") for f in res.findings],
        "llm": {"provider": os.environ.get("NIGHTSHIFT_LLM_PROVIDER", "mock"), "commander": os.environ.get("NIGHTSHIFT_COMMANDER_MODEL", ""),
                "specialist": os.environ.get("NIGHTSHIFT_SPECIALIST_MODEL", ""), "prompt": os.environ.get("NIGHTSHIFT_PROMPT_VERSION", "")},
    }, indent=1, default=str), encoding="utf8")
    stem.with_suffix(".md").write_text(render_md(alert, res, timings), encoding="utf8")
    print(f"[{_iso(t1)}] {alert.name}/{alert.service}: {res.report.category.value} conf={res.report.confidence:.2f} "
          f"cost=${res.usage.cost_usd:.4f} -> {stem.name}", flush=True)
    return stem


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--mode", default=os.environ.get("NIGHTSHIFT_WATCH_MODE", "multi"), choices=["single", "multi"])
    ap.add_argument("--poll", type=float, default=5)
    ap.add_argument("--group-wait", type=float, default=25, help="seconds to wait for co-firing alerts before investigating a service")
    args = ap.parse_args()
    seen: dict[str, float] = {}  # one investigation per alert *occurrence* (alertname+service+activeAt), so a long-firing alert is not re-run
    print(f"nightshift watch: prometheus={PROM} provider={os.environ.get('NIGHTSHIFT_LLM_PROVIDER', 'mock')} mode={args.mode} (shadow: no writes executed)", flush=True)

    def fresh(alerts: list[dict]) -> list[dict]:
        return [a for a in alerts if time.time() >= seen.get(_key(a), 0)]

    while True:
        try:
            new = fresh(await firing_alerts())
            if new:
                await asyncio.sleep(args.group_wait)  # let co-firing alerts of the same outage arrive, then investigate them together
                groups = group_by_service(fresh(await firing_alerts()))
                for members in groups.values():
                    keys = [_key(m) for m in members]
                    for k in keys:
                        seen[k] = float("inf")
                    try:
                        await investigate(merge(members), detected_at=time.time(), mode=args.mode)
                    except Exception as e:  # one failed investigation must not stop the watcher
                        print(f"investigation failed for {keys}: {type(e).__name__}: {e}", flush=True)
                        for k in keys:
                            seen[k] = time.time() + 300  # retry in 5 min
        except httpx.HTTPError as e:
            print(f"prometheus unreachable: {e}", flush=True)
        if args.once:
            return 0
        await asyncio.sleep(args.poll)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
