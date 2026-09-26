"""Run the benchmark against a real LLM (OpenAI by default).  Needs OPENAI_API_KEY in the environment / .env.

  python -m bench.real_llm --model gpt-6-luna --split smoke --config single,multi

Same simulated worlds, scoring and benchmark mode (remediation proposals only) as bench.runner; only the model is real.
Results go to bench/results/real-llm/ and are NOT mixed into the offline-policy README table.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from dataclasses import replace
from pathlib import Path

from agents.core.llm import make_llm
from bench.harness import CONFIGS
from bench.runner import aggregate, run_one
from bench.scenario import load_all, select
from bench.scoring import HeuristicJudge

OUT = Path(__file__).parent / "results" / "real-llm"


def load_env() -> None:
    env = Path(__file__).resolve().parent.parent / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.split("#")[0].strip())


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default="openai")
    ap.add_argument("--model", default="gpt-6-luna")
    ap.add_argument("--split", default="smoke", choices=["dev", "heldout", "smoke", "hard", "all"])
    ap.add_argument("--config", default="single,multi")
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--prompt-version", default=None, help="agents/prompts/<version>; default is the latest (v1)")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--concurrency", type=int, default=4)
    a = ap.parse_args()
    load_env()
    llm = make_llm(a.provider)
    scenarios = select(load_all(), a.split)[: a.limit or None]
    sem = asyncio.Semaphore(a.concurrency)
    run_dir = OUT / "runs" / time.strftime("%Y%m%d-%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)
    scores = []

    async def one(cfg_name: str, s, rep: int):
        real = f"{cfg_name}@{a.model}"
        CONFIGS[real] = replace(CONFIGS[cfg_name], name=real, commander_model=a.model, specialist_model=a.model)
        async with sem:
            try:
                score, detail = await run_one(s, real, rep, HeuristicJudge(), a.prompt_version, llm=llm)
            except Exception as e:  # a failed run counts as invalid, not as a crash of the whole benchmark
                print(f"  ERROR {real} {s.id}: {type(e).__name__}: {e}")
                return
        scores.append(score)
        (run_dir / f"{real}__{s.id}__{rep}.json").write_text(json.dumps({"score": score.as_dict(), **detail}, indent=1), encoding="utf8")
        print(f"  {real:24} {s.id:44} {'OK ' if score.exact else 'BAD'} pred={score.predicted_service}/{score.predicted_category} "
              f"rem={'ok' if score.remediation_ok else 'no'} ${score.cost_usd:.3f} {score.wall_s:.0f}s")

    await asyncio.gather(*[one(c, s, r) for c in a.config.split(",") for r in range(a.repeats) for s in scenarios])
    summary = {"model": a.model, "provider": a.provider, "split": a.split, "prompt_version": a.prompt_version or "v1", "repeats": a.repeats, "scenarios": len(scenarios),
               "note": "real LLM; cost uses fallback pricing if the model is not in agents/core/llm.py PRICES", "configs": aggregate(scores)}
    (OUT).mkdir(parents=True, exist_ok=True)
    (OUT / f"summary-{a.split}-{a.prompt_version or 'v1'}.json").write_text(json.dumps(summary, indent=2), encoding="utf8")
    print(json.dumps({k: {m: v[m] for m in ("runs", "invalid", "root_cause_accuracy", "top3_accuracy", "service_accuracy", "remediation_quality",
                                              "unsafe_action_rate", "evidence_grounding", "red_herring_accuracy", "cost_usd", "wall_time_s")}
                       for k, v in summary["configs"].items()}, indent=1))


if __name__ == "__main__":
    asyncio.run(main())
