from __future__ import annotations

from bench.proactive import evaluate


async def test_proactive_review_finds_every_risky_change_with_no_false_alarms():
    res = await evaluate()
    assert res["changes_reviewed"] > 150 and res["causal_changes"] >= 35
    assert res["recall"] == 1.0 and res["false_positive_rate"] == 0.0
    assert res["precision"] > res["baselines"]["flag_everything"]["precision"]
