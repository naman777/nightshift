"""nightshift-chaos: inject and revert faults on the live stack.

  python -m chaos.cli init                                     create the config git repo (baseline commit)
  python -m chaos.cli list                                     the 10 fault types
  python -m chaos.cli inject slow_dependency --param latency_ms=2000
  python -m chaos.cli scenario bad-config-push-lb-timeout-00   inject a benchmark scenario (fault + red herring)
  python -m chaos.cli revert                                   undo everything injected so far
  python -m chaos.cli flag|config|deploy ...                   primitives (also used by the runtime MCP server)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from chaos import deploylog
from chaos.faults import NAMES, get_fault
from chaos.gitcfg import ROOT, ConfigRepo
from chaos.live import LiveChaos

STATE = ROOT / "target" / ".chaos_state.json"


def _state() -> list[dict]:
    return json.loads(STATE.read_text()) if STATE.exists() else []


def _save(records: list[dict]) -> None:
    STATE.write_text(json.dumps(records, indent=1))


def _coerce(v: str) -> Any:
    for cast in (int, float):
        try:
            return cast(v)
        except ValueError:
            pass
    return {"true": True, "false": False}.get(v.lower(), v)


def herring_steps(spec: dict[str, Any]) -> list[dict[str, Any]]:
    kind = spec["type"]
    if kind == "harmless_deploy":
        deploylog.record(spec.get("service", "payments-svc"), "b" * 8, "chore: bump log format and update dependencies")
        return []
    if kind == "harmless_config":
        return [{"do": "config", "service": "payments-svc", "key": "# runbook", "value": "updated", "message": "payments: update runbook link in comment"}]
    print(f"note: red herring '{kind}' is simulation-only for now; skipping on the live stack", file=sys.stderr)
    return []


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="nightshift-chaos")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    sub.add_parser("list")
    sub.add_parser("revert")
    p = sub.add_parser("inject")
    p.add_argument("fault", choices=NAMES)
    p.add_argument("--param", action="append", default=[], help="k=v overrides")
    p = sub.add_parser("scenario")
    p.add_argument("scenario_id")
    p = sub.add_parser("flag")
    p.add_argument("flag")
    p.add_argument("value")
    p = sub.add_parser("config")
    p.add_argument("service")
    p.add_argument("key")
    p.add_argument("value")
    p = sub.add_parser("deploy")
    p.add_argument("service")
    p.add_argument("--sha", default="")
    p.add_argument("--bug", default="")
    a = ap.parse_args(argv)
    chaos = LiveChaos()

    if a.cmd == "init":
        print("config repo at", chaos.repo.init())
    elif a.cmd == "list":
        from chaos.faults import all_faults

        for n, f in all_faults().items():
            print(f"{n:28} alert={f.alert:22} {f.description}")
    elif a.cmd == "inject":
        params = {k: _coerce(v) for k, v in (kv.split("=", 1) for kv in a.param)}
        records = chaos.run(get_fault(a.fault).live_steps(params))
        _save(_state() + records)
        print(json.dumps(records, indent=1))
    elif a.cmd == "scenario":
        from bench.scenario import load_all

        s = next((x for x in load_all() if x.id == a.scenario_id), None)
        if s is None:
            print(f"unknown scenario {a.scenario_id}", file=sys.stderr)
            return 2
        steps = (herring_steps(s.red_herring) if s.red_herring else []) + get_fault(s.fault).live_steps(s.params)
        records = chaos.run(steps)
        _save(_state() + records)
        print(f"injected {s.id}; expect alert {s.expected_alert}\n" + json.dumps(records, indent=1))
    elif a.cmd == "revert":
        chaos.undo(_state())
        _save([])
        print("reverted")
    elif a.cmd == "flag":
        print(chaos.repo.set_flag(a.flag, a.value, message=f"nightshift: set flag {a.flag}={a.value}", author="nightshift"))
    elif a.cmd == "config":
        print(chaos.repo.set_yaml_key(a.service, a.key, a.value, message=f"nightshift: set {a.service}.{a.key}={a.value}", author="nightshift"))
    elif a.cmd == "deploy":
        print(json.dumps(chaos.deploy(a.service, bug=a.bug, sha=a.sha)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
