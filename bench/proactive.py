"""Evaluate proactive change review: does the reviewer flag the change that will cause the incident, and leave benign changes alone?

For every scenario (the 40 plus the hard set) each commit in the simulated history is reviewed in isolation, exactly as a deploy hook would
present it, BEFORE any alert. Label: risky iff the simulator made that commit cause an incident (the blamed commit, or the cause of a concurrent fault). Everything else (old
history, red herrings, decoys, comment-only changes) is benign. Reports precision / recall / false-positive rate against two trivial baselines.

  python -m bench.proactive
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from agents.proactive import review_change
from bench.harness import CONFIGS, make_runtime
from bench.scenario import build_world, load_all, load_hard

OUT = Path(__file__).parent / "results" / "proactive.json"


async def evaluate() -> dict:
    tp = fp = fn = tn = 0
    cost = 0.0
    misses: list[str] = []
    false_alarms: list[str] = []
    n_changes = 0
    for s in load_all() + load_hard():
        world, _, _ = build_world(s)
        skip = world.facts.get("pool_sha")  # a contributing (not causal) change in the connection-exhaustion scenarios
        for c in world.commits:
            if c.sha == skip:
                continue
            rt, _ = make_runtime(world, CONFIGS["multi"])
            risk = await review_change(rt, {"sha": c.sha, "service": c.service, "kind": c.kind, "message": c.message})
            cost += risk.usage.cost_usd
            n_changes += 1
            is_causal = c.sha in world.risky
            if risk.flagged and is_causal:
                tp += 1
            elif risk.flagged:
                fp += 1
                false_alarms.append(f"{s.id}:{c.sha}:{c.message[:40]}")
            elif is_causal:
                fn += 1
                misses.append(f"{s.id}:{c.sha}")
            else:
                tn += 1
    pos, neg = tp + fn, fp + tn
    return {
        "changes_reviewed": n_changes, "causal_changes": pos,
        "recall": round(tp / pos, 4) if pos else None, "precision": round(tp / (tp + fp), 4) if tp + fp else None,
        "false_positive_rate": round(fp / neg, 4) if neg else None, "cost_per_review_usd": round(cost / max(n_changes, 1), 5),
        "baselines": {"flag_everything": {"recall": 1.0, "precision": round(pos / n_changes, 4), "false_positive_rate": 1.0},
                      "flag_nothing": {"recall": 0.0, "precision": None, "false_positive_rate": 0.0}},
        "missed": misses, "false_alarms": false_alarms,
        "policy": "offline reference policy (mock provider); not LLM results",
    }


def main() -> None:
    res = asyncio.run(evaluate())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, indent=2), encoding="utf8")
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
