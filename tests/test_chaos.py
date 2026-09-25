from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from chaos import deploylog
from chaos.cli import main as chaos_main
from chaos.faults import NAMES, all_faults
from chaos.gitcfg import ROOT, ConfigRepo
from chaos.live import LiveChaos
from mcp_servers.changes.backend import GitChangesBackend
from mcp_servers.changes.server import build as build_changes

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


@pytest.fixture
def repo(tmp_path):
    work = tmp_path / "config"
    shutil.copytree(ROOT / "target" / "config", work)
    r = ConfigRepo(work, tmp_path / "cfg.git")
    r.init()
    return r


def test_every_fault_has_valid_live_steps():
    live = {n for n in dir(LiveChaos) if not n.startswith("_")}
    assert len(NAMES) == 10
    for name, fault in all_faults().items():
        steps = fault.live_steps({})
        assert steps and all(s["do"] in live for s in steps), name


def test_config_change_is_a_real_git_commit_the_change_agent_can_read(repo, tmp_path):
    chaos = LiveChaos(repo)
    rec = chaos.config("lb", "upstream_timeout_ms", 50, "lb: tune timeouts")
    assert "upstream_timeout_ms: 50" in (repo.work / "lb.yaml").read_text()
    backend = GitChangesBackend(str(repo.work), str(tmp_path / "deploys.jsonl"), git_dir=str(repo.git_dir))
    import asyncio

    server = build_changes(backend)
    out = asyncio.run(server.call(server.tools["config_diff"], {"since_minutes": 60}))
    top = out["commits"][-1]
    assert top["message"] == "lb: tune timeouts" and top["files"] == ["lb.yaml"]
    assert "-upstream_timeout_ms: 2000" in top["diff"] and "+upstream_timeout_ms: 50" in top["diff"]
    # undo restores the healthy value via a revert commit (history is preserved, never rewritten)
    chaos.undo([rec])
    assert "upstream_timeout_ms: 2000" in (repo.work / "lb.yaml").read_text()
    assert repo.git("log", "--oneline").count("\n") >= 2


def test_flag_flip_and_revert(repo):
    chaos = LiveChaos(repo)
    rec = chaos.flag("enable_unbounded_cache", "true")
    assert '"enable_unbounded_cache": true' in (repo.work / "flags.json").read_text()
    chaos.undo([rec])
    assert '"enable_unbounded_cache": false' in (repo.work / "flags.json").read_text()


def test_deploy_log_roundtrip(tmp_path):
    p = tmp_path / "d.jsonl"
    deploylog.record("orders-svc", "abc12345", "orders: batch loader", ts=1000, path=p)
    assert deploylog.read(p) == [{"ts": 1000, "service": "orders-svc", "sha": "abc12345", "author": "dana", "message": "orders: batch loader"}]


def test_cli_lists_faults(capsys):
    assert chaos_main(["list"]) == 0
    out = capsys.readouterr().out
    assert all(n in out for n in NAMES)


def test_go_sources_are_present_and_consistent():
    """Go is not compiled in CI here; at least check the module layout and that every import path resolves to a real package."""
    target = ROOT / "target"
    assert (target / "go.mod").read_text().startswith("module nightshift/target")
    import re

    for f in target.rglob("*.go"):
        for imp in re.findall(r'"nightshift/target/([^"]+)"', f.read_text()):
            assert (target / imp).is_dir(), f"{f}: missing package {imp}"
    for svc in ("orders-svc", "payments-svc", "stubs/lb", "stubs/scheduler"):
        assert "package main" in (target / svc / "main.go").read_text()
