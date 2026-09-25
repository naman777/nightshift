"""Live benchmark runner: the same scenarios against the REAL docker-compose stack (needs `make up` and a provider).

  python -m bench.live bad-config-push-lb-timeout-00 --config multi --provider anthropic

Per scenario: reset (revert faults, restore the baseline config commit, redeploy a clean orders build) -> 60 s of normal traffic so the
metrics have a baseline -> inject via the chaos CLI -> wait for Prometheus to report the expected alert (if it never fires the scenario is
INVALID) -> investigate in benchmark mode (write tools are recorded, never executed) -> score -> save JSON.

NOTE: written against the compose stack but not exercised in the environment it was authored in (no docker daemon there).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import time
from pathlib import Path

import httpx

from agents.core.models import Alert
from agents.pipeline import LocalOrchestrator
from bench.runner import RESULTS, modeled_time
from bench.scenario import build_world, load_all
from bench.scoring import HeuristicJudge, RunScore, action_is_unsafe, grounding_ratio
from chaos.cli import herring_steps
from chaos.faults import get_fault
from chaos.gitcfg import ConfigRepo
from chaos.live import LiveChaos
from orchestrator.runtime_factory import build_runtime

PROM = os.environ.get("PROMETHEUS_URL", "http://localhost:9090")


def reset_stack(chaos: LiveChaos) -> None:
    chaos.repo.reset_to_baseline()
    subprocess.run(["docker", "compose", "up", "-d", "--build", "orders-svc-1", "orders-svc-2"], check=True, capture_output=True,
                   env={**os.environ, "ORDERS_BUG": "", "GIT_SHA": "clean"})
    subprocess.run(["docker", "start", "nightshift-orders-svc-1", "nightshift-orders-svc-2"], capture_output=True)


async def wait_for_alert(name: str, timeout_s: int) -> dict | None:
    end = time.time() + timeout_s
    async with httpx.AsyncClient(timeout=10) as c:
        while time.time() < end:
            for a in (await c.get(f"{PROM}/api/v1/alerts")).json()["data"]["alerts"]:
                if a["labels"].get("alertname") == name and a["state"] == "firing":
                    return a
            await asyncio.sleep(5)
    return None


async def run_live(scenario_id: str, config: str, repeat: int = 0) -> RunScore:
    s = next(x for x in load_all() if x.id == scenario_id)
    _, _, gt = build_world(s)
    chaos = LiveChaos(ConfigRepo())
    reset_stack(chaos)
    await asyncio.sleep(60)  # warm-up
    t_inject = time.time()
    chaos.run((herring_steps(s.red_herring) if s.red_herring else []) + get_fault(s.fault).live_steps(s.params))
    fired = await wait_for_alert(s.expected_alert, s.time_limit_s)
    score = RunScore(s.id, config, repeat, has_herring=bool(s.red_herring), split=s.split)
    if fired is None:
        score.valid = False
        return score
    labels = fired["labels"]
    alert = Alert(fingerprint=f"live-{s.id}-{int(t_inject)}", name=s.expected_alert, service=labels.get("service", "orders-svc"),
                  started_at=time.time(), labels={k: str(v) for k, v in labels.items()}, annotations=fired.get("annotations", {}))
    rt, policy = build_runtime(alert.labels, benchmark_mode=True)
    t0 = time.perf_counter()
    res = await LocalOrchestrator(rt).investigate(alert, "single" if config == "single" else "multi")
    score.wall_s = round(time.perf_counter() - t0, 2)
    score.modeled_s = round(modeled_time(res), 2)
    r = res.report
    score.predicted_service, score.predicted_category = r.service, r.category.value
    score.service_ok, score.category_ok = r.service == gt.root_cause_service, r.category.value == gt.category.value
    score.exact = score.service_ok and score.category_ok
    score.top3 = (gt.root_cause_service, gt.category.value) in [(r.service, r.category.value)] + [(x.service, x.category.value) for x in r.ranked][:3]
    score.judge_ok = await HeuristicJudge().judge(gt.root_cause, r.root_cause)
    score.action = res.action.type if res.action else ""
    score.remediation_ok = bool(res.action and res.action.type in gt.correct_remediations)
    score.unsafe = action_is_unsafe(res.action.type if res.action else None, res.action.tier if res.action else None, gt, policy.proposals, [])
    score.grounding = grounding_ratio(r, rt.board, res.incident_id)
    score.cost_usd, score.llm_calls, score.tool_calls = res.usage.cost_usd, res.usage.llm_calls, res.usage.tool_calls
    chaos.undo(json.loads(Path("target/.chaos_state.json").read_text()) if Path("target/.chaos_state.json").exists() else [])
    return score


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("scenario")
    ap.add_argument("--config", default="multi", choices=["single", "multi"])
    ap.add_argument("--provider", default=os.environ.get("NIGHTSHIFT_LLM_PROVIDER", "mock"))
    a = ap.parse_args()
    os.environ["NIGHTSHIFT_LLM_PROVIDER"], os.environ["NIGHTSHIFT_BACKEND"] = a.provider, "live"
    score = asyncio.run(run_live(a.scenario, a.config))
    out = RESULTS / "live"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{a.config}__{a.scenario}.json").write_text(json.dumps(score.as_dict(), indent=1), encoding="utf8")
    print(json.dumps(score.as_dict(), indent=1))
    return 0 if score.valid else 2


if __name__ == "__main__":
    raise SystemExit(main())
