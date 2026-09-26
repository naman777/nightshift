"""Benchmark runner.  python -m bench.runner --split smoke --config multi --repeats 1

Per scenario: fresh simulated world (= reset to a clean snapshot) -> warm baseline traffic is implicit in the metric history ->
inject the fault (+ red herring) -> check the expected alert actually fires (else the scenario is INVALID) -> run the agents in
BENCHMARK MODE (remediation proposals are recorded, never executed) -> score -> save JSON.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

from agents import pipeline
from agents.core.db import Database
from agents.core.evidence import EvidenceBoard
from agents.core.memory import IncidentMemory, signature_from_evidence
from agents.core.models import Alert, ProposedAction, RootCauseReport, Usage
from agents.prompts import LATEST
from bench.alert_rules import alert_fires
from bench.baselines import BASELINES
from bench.harness import CONFIGS, make_runtime
from bench.scenario import Scenario, build_world, load_all, select
from bench.scoring import HeuristicJudge, Judge, RunScore, action_is_unsafe, grounding_ratio, remediation_matches

RESULTS = Path(__file__).parent / "results"
ALL_CONFIGS = ["naive-recent-change", "naive-top-errors", "single", "multi", "multi-routed", "multi-nocite", "multi-memory"]

LLM_S, TOOL_S, TOK_PER_S = 0.6, 0.4, 70.0  # modelled latency constants for time-to-diagnosis (documented in docs/benchmark.md)


def _modeled(u: Usage) -> float:
    return u.llm_calls * LLM_S + u.output_tokens / TOK_PER_S + u.tool_calls * TOOL_S


def modeled_time(result: pipeline.InvestigationResult) -> float:
    """Critical-path estimate: commander steps are serial; specialists run in parallel, so only the slowest chain counts."""
    if result.mode == "single":
        return _modeled(result.usage)
    spec_total = Usage()
    per_agent: dict[str, float] = defaultdict(float)
    for f in result.findings:
        spec_total = spec_total.add(f.usage)
        per_agent[f.agent] += _modeled(f.usage)
    commander_u = Usage(llm_calls=max(0, result.usage.llm_calls - spec_total.llm_calls),
                        output_tokens=max(0, result.usage.output_tokens - spec_total.output_tokens))
    return _modeled(commander_u) + max(per_agent.values(), default=0.0)


async def run_one(s: Scenario, config: str, repeat: int, judge: Judge, prompt_version: str | None = None,
                  memory: IncidentMemory | None = None, llm=None) -> tuple[RunScore, dict]:
    sc = s.model_copy(update={"seed": int.from_bytes(s.id.encode()[:4], "big") % 9000 + 1 + repeat})
    world, alert, gt = build_world(sc)
    score = RunScore(s.id, config, repeat, has_herring=bool(s.red_herring), injection=bool(s.red_herring and s.red_herring["type"] == "log_injection"),
                     split=s.split)
    if not alert_fires(world, s.expected_alert):
        score.valid = False
        return score, {"invalid": "expected alert never fired"}
    t0 = time.perf_counter()
    if config in BASELINES:
        rt, policy = make_runtime(world, CONFIGS["multi"])
        report = await BASELINES[config](rt.client, alert)
        action, usage, findings, board, iid = report.proposed_action, Usage(), [], rt.board, f"inc-{alert.fingerprint}"
        modeled = 2 * TOOL_S
    else:
        rt, policy = make_runtime(world, CONFIGS[config], prompt_version=prompt_version, memory=memory, memory_exclude=f"seed-{s.id}", llm=llm)
        res = await pipeline.LocalOrchestrator(rt).investigate(alert, CONFIGS[config].mode)
        report, action, usage, board, iid = res.report, res.action, res.usage, rt.board, res.incident_id
        modeled = modeled_time(res)
    score.wall_s = round(time.perf_counter() - t0, 4)
    score.modeled_s = round(modeled, 2)
    score.predicted_service, score.predicted_category = report.service, report.category.value
    score.service_ok = report.service == gt.root_cause_service
    score.category_ok = report.category.value == gt.category.value
    score.exact = score.service_ok and score.category_ok
    ranked = [(report.service, report.category.value)] + [(r.service, r.category.value) for r in report.ranked]
    score.top3 = (gt.root_cause_service, gt.category.value) in ranked[:3]
    score.judge_ok = await judge.judge(gt.root_cause, report.root_cause)
    score.action = action.type if action else ""
    score.remediation_ok = remediation_matches(action, gt)
    score.unsafe = action_is_unsafe(action.type if action else None, action.tier if action else None, gt, policy.proposals, world.actions)
    score.grounding = grounding_ratio(report, board, iid) if config not in BASELINES else 0.0
    score.cost_usd, score.llm_calls, score.tool_calls = usage.cost_usd, usage.llm_calls, usage.tool_calls
    score.degraded = report.degraded
    return score, {"ground_truth": gt.model_dump(mode="json"), "report": report.model_dump(mode="json"),
                   "action": action.model_dump(mode="json") if action else None, "proposals": policy.proposals}


def aggregate(scores: list[RunScore]) -> dict:
    by: dict[str, list[RunScore]] = defaultdict(list)
    for s in scores:
        by[s.config].append(s)
    out = {}
    for cfg, rows in by.items():
        valid = [r for r in rows if r.valid]
        n = len(valid) or 1

        def rate(pred, subset=valid):
            return round(sum(1 for r in subset if pred(r)) / max(len(subset), 1), 4)

        def stats(vals):
            vals = sorted(vals)
            if not vals:
                return {"mean": 0, "p50": 0, "p95": 0}
            return {"mean": round(sum(vals) / len(vals), 4), "p50": round(vals[len(vals) // 2], 4), "p95": round(vals[min(len(vals) - 1, int(len(vals) * 0.95))], 4)}

        # spread across repeats: std of per-repeat accuracy
        per_rep: dict[int, list[RunScore]] = defaultdict(list)
        for r in valid:
            per_rep[r.repeat].append(r)
        accs = [rate(lambda r: r.exact, v) for v in per_rep.values()]
        mean_acc = sum(accs) / len(accs) if accs else 0.0
        std = (sum((a - mean_acc) ** 2 for a in accs) / len(accs)) ** 0.5 if accs else 0.0
        herr, plain = [r for r in valid if r.has_herring], [r for r in valid if not r.has_herring]
        dev, held = [r for r in valid if r.split == "dev"], [r for r in valid if r.split == "heldout"]
        inj = [r for r in valid if r.injection]
        out[cfg] = {
            "runs": len(rows), "invalid": len(rows) - len(valid),
            "root_cause_accuracy": rate(lambda r: r.exact), "accuracy_std": round(std, 4), "top3_accuracy": rate(lambda r: r.top3),
            "judge_accuracy": rate(lambda r: r.judge_ok), "service_accuracy": rate(lambda r: r.service_ok),
            "remediation_quality": rate(lambda r: r.remediation_ok), "unsafe_action_rate": rate(lambda r: r.unsafe),
            "evidence_grounding": round(sum(r.grounding for r in valid) / n, 4),
            "red_herring_accuracy": rate(lambda r: r.exact, herr), "no_herring_accuracy": rate(lambda r: r.exact, plain),
            "dev_accuracy": rate(lambda r: r.exact, dev) if dev else None, "heldout_accuracy": rate(lambda r: r.exact, held) if held else None,
            "injection_obeyed_rate": rate(lambda r: r.unsafe, inj) if inj else None,
            "cost_usd": stats([r.cost_usd for r in valid]), "modeled_time_s": stats([r.modeled_s for r in valid]),
            "wall_time_s": stats([r.wall_s for r in valid]),
            "llm_calls_mean": round(sum(r.llm_calls for r in valid) / n, 2), "tool_calls_mean": round(sum(r.tool_calls for r in valid) / n, 2),
        }
    return out


async def seed_memory(repeat: int) -> IncidentMemory:
    """Past incidents = the DEV scenarios, investigated once. An incident is stored as verified only if its diagnosis was right, simulating
    the human confirmation (approved fix resolved it) that gates real memory. Held-out and hard scenarios are never seeded."""
    mem = IncidentMemory(Database.memory())
    for s in select(load_all(), "dev"):
        sc = s.model_copy(update={"seed": int.from_bytes(s.id.encode()[:4], "big") % 9000 + 500 + repeat})
        world, alert, gt = build_world(sc)
        rt, _ = make_runtime(world, CONFIGS["multi"])
        res = await pipeline.LocalOrchestrator(rt).investigate(alert, "multi")
        ok = res.report.service == gt.root_cause_service and res.report.category.value == gt.category.value
        mem.add(f"seed-{s.id}", alert.name, res.report, signature_from_evidence(rt.board.list(res.incident_id)), res.action.type if res.action else "", verified=ok)
    return mem


async def run_all(split: str, configs: list[str], repeats: int, limit: int | None, out_dir: Path, judge: Judge | None = None,
                  prompt_version: str | None = None) -> dict:
    scenarios = select(load_all(), split)[: limit or None]
    judge = judge or HeuristicJudge()
    run_dir = out_dir / "runs" / time.strftime("%Y%m%d-%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)
    scores: list[RunScore] = []
    seeded: dict[int, IncidentMemory] = {}
    for cfg in configs:
        for rep in range(repeats):
            mem = None
            if cfg in CONFIGS and CONFIGS[cfg].memory:
                mem = seeded.setdefault(rep, await seed_memory(rep))
            for s in scenarios:
                score, detail = await run_one(s, cfg, rep, judge, prompt_version, mem)
                scores.append(score)
                (run_dir / f"{cfg}__{s.id}__{rep}.json").write_text(json.dumps({"score": score.as_dict(), **detail}, indent=1), encoding="utf8")
    summary = {"prompt_version": prompt_version or LATEST, "split": split, "repeats": repeats, "scenarios": len(scenarios), "run_dir": str(run_dir),
               "policy": "offline reference policy (mock provider); not LLM results", "configs": aggregate(scores)}
    out_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(summary, indent=2)
    (out_dir / "summary.json").write_text(text, encoding="utf8")
    (out_dir / f"summary-{split}.json").write_text(text, encoding="utf8")
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="dev", choices=["dev", "heldout", "smoke", "hard", "all"])
    ap.add_argument("--config", default="multi", help=f"one of {ALL_CONFIGS} or 'all'")
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--prompt-version", default=None, help="agents/prompts/<version> to evaluate (recorded in the summary)")
    ap.add_argument("--out", default=str(RESULTS))
    ap.add_argument("--fail-below", type=float, default=None, help="exit 1 if exact-match accuracy is below this (CI gate)")
    ap.add_argument("--baseline", default=None, help="JSON {config: accuracy}; exit 1 if any config drops more than --max-drop below it")
    ap.add_argument("--max-drop", type=float, default=0.10)
    ap.add_argument("--write-baseline", default=None, help="write the accuracies of this run to a baseline file")
    a = ap.parse_args(argv)
    configs = ALL_CONFIGS if a.config == "all" else a.config.split(",")
    summary = asyncio.run(run_all(a.split, configs, a.repeats, a.limit, Path(a.out), prompt_version=a.prompt_version))
    from bench.report import render_markdown

    print(render_markdown(summary))
    accs = {k: c["root_cause_accuracy"] for k, c in summary["configs"].items()}
    if a.write_baseline:
        Path(a.write_baseline).write_text(json.dumps(accs, indent=2), encoding="utf8")
    if a.baseline:
        base = json.loads(Path(a.baseline).read_text(encoding="utf8"))
        regress = {k: (base[k], v) for k, v in accs.items() if k in base and v < base[k] - a.max_drop}
        if regress:
            print(f"FAIL: accuracy regressed more than {a.max_drop:.0%} vs baseline: {regress}", file=sys.stderr)
            return 1
    if a.fail_below is not None:
        worst = min(c["root_cause_accuracy"] for k, c in summary["configs"].items() if not k.startswith("naive"))
        if worst < a.fail_below:
            print(f"FAIL: accuracy {worst:.0%} < {a.fail_below:.0%}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
