"""Investigate a benchmark scenario in the terminal, with live agent steps.

  python -m agents.cli investigate bad-deploy-n-plus-one-00
  python -m agents.cli investigate bad-deploy-n-plus-one-00 --mode single
  python -m agents.cli investigate memory-leak-orders-cache-00 --provider anthropic \
      --commander-model claude-opus-4-5 --specialist-model claude-haiku-4-5      (needs ANTHROPIC_API_KEY)
  python -m agents.cli scenarios                                                  list scenario ids
"""
from __future__ import annotations

import argparse
import asyncio
import sys

from agents.core.llm import make_llm
from agents.core.models import Step
from agents.pipeline import LocalOrchestrator
from agents.scripted import heuristic_responder
from bench.harness import CONFIGS, Config, make_runtime
from bench.scenario import build_world, load_all


def _print_step(s: Step) -> None:
    if s.kind == "tool":
        print(f"  [{s.agent:11}] tool  {s.name} ({s.duration_ms}ms)")
    elif s.kind == "finding":
        print(f"  [{s.agent:11}] done  {s.name}: {s.detail[:110]}")


async def investigate(args: argparse.Namespace) -> int:
    scenario = next((s for s in load_all() if s.id == args.scenario), None)
    if scenario is None:
        print(f"unknown scenario '{args.scenario}'. Try: python -m agents.cli scenarios", file=sys.stderr)
        return 2
    world, alert, gt = build_world(scenario)
    base = CONFIGS["single" if args.mode == "single" else "multi"]
    cfg = Config(base.name, base.mode, args.commander_model or base.commander_model, args.specialist_model or args.commander_model or base.specialist_model)
    llm = make_llm(args.provider, responder=heuristic_responder)
    rt, policy = make_runtime(world, cfg, llm=llm, on_step=_print_step)
    print(f"alert: {alert.name} on {alert.service}  (provider={args.provider}, mode={args.mode})")
    res = await LocalOrchestrator(rt).investigate(alert, cfg.mode)
    r = res.report
    print(f"\nROOT CAUSE  {r.root_cause}\n  service={r.service} category={r.category.value} confidence={r.confidence:.0%} evidence={r.evidence}")
    for x in r.ruled_out:
        print(f"  ruled out: {x.hypothesis} ({', '.join(x.evidence)})")
    if res.action:
        print(f"PROPOSED    {res.action.type} {res.action.target} [{res.action.tier.value}]  (benchmark mode: not executed)")
    print(f"COST        ${res.usage.cost_usd:.4f}  {res.usage.llm_calls} LLM calls, {res.usage.tool_calls} tool calls, {res.duration_s:.2f}s")
    ok = (r.service, r.category.value) == (gt.root_cause_service, gt.category.value)
    print(f"GROUND TRUTH {gt.root_cause}\n  -> {'CORRECT' if ok else 'WRONG'}")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="nightshift")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("scenarios")
    p = sub.add_parser("investigate")
    p.add_argument("scenario")
    p.add_argument("--mode", choices=["multi", "single"], default="multi")
    p.add_argument("--provider", choices=["mock", "anthropic", "openai"], default="mock")
    p.add_argument("--commander-model", default=None)
    p.add_argument("--specialist-model", default=None)
    a = ap.parse_args(argv)
    if a.cmd == "scenarios":
        for s in load_all():
            print(f"{s.id:48} {s.split:8} {'smoke' if s.smoke else '':5} {'herring:' + s.red_herring['type'] if s.red_herring else ''}")
        return 0
    return asyncio.run(investigate(a))


if __name__ == "__main__":
    raise SystemExit(main())
