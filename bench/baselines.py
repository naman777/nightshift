"""No-LLM floor baselines. They show the benchmark can tell a real investigation from a lazy rule of thumb.

  naive-recent-change : blame whatever changed most recently ("it was the last deploy")
  naive-top-errors    : blame the service that logs the most errors ("the noisiest service is broken")
"""
from __future__ import annotations

import json
from collections import Counter

from agents.core.mcp_client import CallContext, MCPClient
from agents.core.models import Alert, Category, ProposedAction, RankedCause, RootCauseReport, Tier, Usage


async def _call(client: MCPClient, name: str, args: dict) -> dict:
    res = await client.call_tool(name, args, CallContext(agent="baseline"))
    try:
        return json.loads(res.content)
    except ValueError:
        return {}


def _report(cause: str, service: str, category: Category, action: ProposedAction) -> RootCauseReport:
    return RootCauseReport(root_cause=cause, service=service, category=category, confidence=0.5, evidence=[], proposed_action=action,
                           ranked=[RankedCause(root_cause=cause, service=service, category=category, confidence=0.5)], usage=Usage())


async def naive_recent_change(client: MCPClient, alert: Alert) -> RootCauseReport:
    d = (await _call(client, "changes__recent_deploys", {"since_minutes": 360})).get("deploys", [])
    c = (await _call(client, "changes__config_diff", {"since_minutes": 360})).get("commits", [])
    events = [("deploy", x) for x in d] + [("config", x) for x in c]
    if not events:
        return _report("no recent change found", alert.service, Category.UNKNOWN, ProposedAction(type="escalate", target="on-call", tier=Tier.READ_ONLY))
    kind, e = max(events, key=lambda kv: kv[1]["ts"])
    if kind == "deploy":
        return _report(f"deploy {e['sha']} of {e['service']} ({e['message']})", e["service"], Category.BAD_DEPLOY,
                       ProposedAction(type="rollback_deploy", target=e["service"], params={"sha": "previous"}, tier=Tier.REVERSIBLE))
    f = (e.get("files") or [""])[0]
    svc = f.removeprefix("config/").split(".")[0] or "orders-svc"
    return _report(f"config commit {e['sha']}: {e['message']}", svc, Category.CONFIG_CHANGE,
                   ProposedAction(type="revert_commit", target=e["sha"], tier=Tier.REVERSIBLE))


async def naive_top_errors(client: MCPClient, alert: Alert) -> RootCauseReport:
    clusters = (await _call(client, "logs__cluster_errors", {"start": "-30m"})).get("clusters", [])
    tally: Counter[str] = Counter()
    for c in clusters:
        tally[c["service"]] += c["count"]
    if not tally:
        return _report("no errors found", alert.service, Category.UNKNOWN, ProposedAction(type="escalate", target="on-call", tier=Tier.READ_ONLY))
    svc = tally.most_common(1)[0][0]
    return _report(f"{svc} is logging the most errors", svc, Category.BAD_DEPLOY,
                   ProposedAction(type="restart_replica", target=svc, tier=Tier.REVERSIBLE))


BASELINES = {"naive-recent-change": naive_recent_change, "naive-top-errors": naive_top_errors}
