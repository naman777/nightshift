from __future__ import annotations

import json
from pathlib import Path

import pytest

from agents.core.models import Tier
from bench.alert_rules import alert_fires
from bench.report import inject_readme, render_markdown, render_svg
from bench.runner import run_all
from bench.scenario import GroundTruth, build_world, load_all
from bench.scoring import HeuristicJudge, action_is_unsafe, calibrate

SCENARIOS = load_all()


@pytest.mark.parametrize("s", SCENARIOS, ids=lambda s: s.id)
def test_every_scenario_fires_its_expected_alert(s):
    world, alert, gt = build_world(s)
    assert alert_fires(world, s.expected_alert), "invalid scenario: the alert rules would never page for this fault"
    assert alert.name == s.expected_alert
    assert "{" not in gt.root_cause  # ground-truth template fully resolved


def test_ground_truth_is_stable_and_specific():
    _, _, gt = build_world(next(s for s in SCENARIOS if s.id == "bad-config-push-lb-timeout-00"))
    assert "upstream_timeout_ms" in gt.root_cause and "2000" in gt.root_cause and "50" in gt.root_cause


async def test_judge_calibration_meets_threshold():
    res = await calibrate(HeuristicJudge())
    assert res["cases"] == 20 and res["agreement"] >= 0.9, res


def test_action_safety_scoring():
    gt = GroundTruth(root_cause="x", root_cause_service="lb", category="config_change", correct_remediations=["revert_commit"])
    assert not action_is_unsafe("revert_commit", Tier.REVERSIBLE, gt, [], [])
    assert action_is_unsafe("restart_postgres", Tier.DESTRUCTIVE, gt, [], [])
    assert action_is_unsafe("scale", Tier.REVERSIBLE, gt, [{"tool": "scale_to_zero", "tier": "destructive"}], [])
    assert action_is_unsafe("revert_commit", Tier.REVERSIBLE, gt, [], [{"action": "delete_data"}])


async def test_runner_smoke_and_report(tmp_path):
    summary = await run_all("smoke", ["naive-recent-change", "single", "multi", "multi-routed"], 2, None, tmp_path)
    c = summary["configs"]
    assert c["multi"]["root_cause_accuracy"] > c["naive-recent-change"]["root_cause_accuracy"]
    assert c["multi"]["unsafe_action_rate"] == 0 and c["single"]["unsafe_action_rate"] == 0
    assert c["multi"]["evidence_grounding"] == 1.0
    assert c["multi-routed"]["cost_usd"]["mean"] < c["multi"]["cost_usd"]["mean"]
    assert all(v["invalid"] == 0 for v in c.values())
    runs = list((Path(summary["run_dir"])).glob("*.json"))
    assert len(runs) == 4 * 10 * 2 and "score" in json.loads(runs[0].read_text())
    table = render_markdown(summary)
    assert "| Multi-agent |" in table and "Naive" in table
    assert "<svg" in render_svg(summary)


def test_heldout_split_is_disjoint_from_dev():
    dev = {s.id for s in SCENARIOS if s.split == "dev"}
    held = {s.id for s in SCENARIOS if s.split == "heldout"}
    assert dev.isdisjoint(held) and len(dev) == 25 and len(held) == 15


def test_readme_injection(tmp_path, monkeypatch):
    import bench.report as r

    readme = tmp_path / "README.md"
    readme.write_text("a\n<!-- BENCH:START -->\nold\n<!-- BENCH:END -->\nb\n", encoding="utf8")
    monkeypatch.setattr(r, "README", readme)
    assert inject_readme("NEW TABLE")
    assert "NEW TABLE" in readme.read_text() and "old" not in readme.read_text()
