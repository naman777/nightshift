"""Offline reference policy ("heuristic brain") used by the deterministic mock provider.

This is NOT an LLM. It is a hand-written investigator that speaks the same tool-calling protocol as a model, so the entire
system (loop, policy, evidence board, orchestration, benchmark, scoring) runs and is testable with no API keys. Benchmark numbers
produced with it measure the harness and the reference policy; they are not LLM results.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from agents.core.llm import MockLLM
from agents.core.models import LLMResponse, Message, ToolCall

# ----------------------------------------------------------------------------- parsing helpers

_RESULT = re.compile(r'<tool_result id="(call_\d+)" tool="([^"]+)"[^>]*>\n(.*?)\n</tool_result>', re.S)
_TAG = re.compile(r"\[(metric|log|change|code)\s+([^\]]*)\]")
_KV = re.compile(r'(\w+)=("([^"]*)"|\S+)')


def tool_results(messages: list[Message]) -> list[dict[str, Any]]:
    out = []
    for m in messages:
        if m.role != "tool":
            continue
        hit = _RESULT.search(m.content)
        if not hit:
            continue
        body = hit.group(3)
        try:
            obj = json.loads(body)
        except ValueError:
            obj = None
        out.append({"id": hit.group(1), "tool": hit.group(2), "obj": obj, "raw": body})
    return out


def role_of(system: str) -> str:
    m = re.match(r"ROLE:\s*(\w+)", system.strip())
    return m.group(1) if m else "unknown"


def user_text(messages: list[Message]) -> str:
    return "\n".join(m.content for m in messages if m.role == "user")


def parse_tags(text: str) -> list[tuple[str, dict[str, str]]]:
    out = []
    for kind, body in _TAG.findall(text):
        attrs = {k: (v[1:-1] if v.startswith('"') else v) for k, v, _ in _KV.findall(body)}
        out.append((kind, attrs))
    return out


def _q(s: str) -> str:
    return s.replace('"', "'").replace("]", ")").replace("[", "(")


def _call(name: str, n: int, **args: Any) -> LLMResponse:
    return LLMResponse(tool_calls=[ToolCall(id=f"p{n}", name=name, arguments=args)])


def _submit(summary: str, claims: list[dict], status: str | None = None) -> LLMResponse:
    return _call("submit_finding", 99, summary=summary, status=status or ("conclusive" if claims else "inconclusive"), claims=claims)


# ----------------------------------------------------------------------------- claim builders (shared by specialists + single agent)

def metric_claims(res: dict, call_id: str) -> list[dict]:
    out = []
    for a in (res.get("anomalies") or [])[:6]:
        out.append({"claim": (f"{a['metric']} on {a['service']} is {a['change_ratio']}x baseline (baseline {a['baseline_avg']}, recent {a['recent_avg']}), "
                              f"deviating since {a['started_at']} [metric name={a['metric']} service={a['service']} ratio={a['change_ratio']} onset={a['started_at']}]"),
                    "tool_call_ref": call_id, "confidence": 0.8})
    return out


INJECTION = re.compile(r"ignore (all )?previous instructions|system notice|you are now in", re.I)


def log_claims(res: dict, call_id: str) -> list[dict]:
    out = []
    for c in (res.get("clusters") or [])[:6]:
        sample = _q(c["sample"])[:110]
        if INJECTION.search(c["sample"]):
            out.append({"claim": f"Log line on {c['service']} contains instruction-like text (prompt injection attempt); NOT followed "
                                 f"[log service={c['service']} level={c['level']} count={c['count']} first_seen={c['first_seen']} injection=true sig=\"injection\" sample=\"{sample[:60]}\"]",
                        "tool_call_ref": call_id, "confidence": 0.9})
            continue
        out.append({"claim": (f"{c['count']}x {c['level']} on {c['service']} since {c['first_seen']}: {sample} "
                              f"[log service={c['service']} level={c['level']} count={c['count']} first_seen={c['first_seen']} sig=\"{_q(c['signature'])[:80]}\" sample=\"{sample}\"]"),
                    "tool_call_ref": call_id, "confidence": 0.7})
    return out


def _diff_kv(diff: str) -> tuple[str, str, str]:
    old = re.search(r"^-([^-+\n][^:\n]*):\s*(.*)$", diff, re.M)
    new = re.search(r"^\+([^+\n][^:\n]*):\s*(.*)$", diff, re.M)
    if old and new:
        return old.group(1).strip().strip('"'), old.group(2).strip(), new.group(2).strip()
    return "", "", ""


def change_claims(deploys: dict | None, configs: dict | None, ids: tuple[str, str]) -> list[dict]:
    out = []
    for d in (deploys or {}).get("deploys", []):
        out.append({"claim": (f"deploy of {d['service']} {d['sha']} at {d['ts']} by {d['author']}: {_q(d['message'])} "
                              f"[change kind=deploy service={d['service']} sha={d['sha']} ts={d['ts']} msg=\"{_q(d['message'])}\"]"),
                    "tool_call_ref": ids[0], "confidence": 0.8})
    for c in (configs or {}).get("commits", []):
        key, old, new = _diff_kv(c.get("diff", ""))
        f = (c.get("files") or [""])[0]
        m = re.match(r"config/(.+)\.yaml", f)
        svc = m.group(1) if m else ""
        kind = "flag" if f.endswith("flags.json") else "config"
        out.append({"claim": (f"{kind} commit {c['sha']} at {c['ts']} changed {key} from {old} to {new} in {f}: {_q(c['message'])} "
                              f"[change kind={kind} service={svc} sha={c['sha']} ts={c['ts']} key=\"{_q(key)}\" old=\"{_q(old)}\" new=\"{_q(new)}\" msg=\"{_q(c['message'])}\"]"),
                    "tool_call_ref": ids[1], "confidence": 0.8})
    return out


def detect_smell(src: str) -> str:
    if re.search(r"loadItems\(o\.ID\)|for _, o := range orders|slowItems\(", src):
        return "n_plus_one"
    if re.search(r"orders\[0\]|first\.ID", src):
        return "nil_deref_on_empty"
    if re.search(r"items\[0\]|ids\[0\]", src):
        return "index_out_of_range"
    if re.search(r"status <> 'archived'|pg_sleep", src):
        return "unindexed_full_scan"
    return "none"


def code_claims(read: dict | None, tests: dict | None, ids: tuple[str, str]) -> list[dict]:
    path = (read or {}).get("path", "handlers/orders.go")
    smell = detect_smell((read or {}).get("content", ""))
    passed = bool((tests or {}).get("passed", True))
    unavailable = "not installed" in str((tests or {}).get("output", ""))
    status = "unknown" if unavailable else ("pass" if passed else "fail")
    return [{"claim": f"{path} smell={smell}; test suite {status} "
                      f"[code file={path} smell={smell} tests={status}]",
             "tool_call_ref": ids[0], "confidence": 0.7 if smell != "none" else 0.5}]


# ----------------------------------------------------------------------------- diagnosis engine

@dataclass
class Cand:
    category: str
    service: str
    score: float
    text: str
    ev: list[str] = field(default_factory=list)
    action: dict | None = None


HARMLESS = re.compile(r"chore|bump|dependenc|comment|runbook|docs|typo", re.I)
SPECIAL_KEYS = {"log_level", "worker_count", "settlement_schedule", "health_check_interval_ms", "db_pool_size"}


def _f(x: Any, d: float = 0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return d


def diagnose(items: list[tuple[str, str, dict[str, str]]]) -> tuple[list[Cand], dict[str, Any]]:
    """items: (evidence ref, kind, attrs). Returns candidates sorted by score and side info (for ruled_out)."""
    M: dict[tuple[str, str], tuple[float, float, str]] = {}
    L, C, K = [], [], []
    for ref, kind, a in items:
        if kind == "metric":
            M[(a["name"], a["service"])] = (_f(a.get("ratio")), _f(a.get("onset")), ref)
        elif kind == "log":
            L.append((ref, a))
        elif kind == "change":
            C.append((ref, a))
        elif kind == "code":
            K.append((ref, a))
    onsets = [o for (m, s), (r, o, _) in M.items() if (r >= 3 or r <= 0.4) and m not in ("restarts_total",) and o]
    t0 = min(onsets) if onsets else 0.0

    def ratio(metric: str, svc: str) -> float:
        return M.get((metric, svc), (1.0, 0, ""))[0]

    def mev(metric: str, svc: str) -> list[str]:
        return [M[(metric, svc)][2]] if (metric, svc) in M else []

    def logs(pattern: str, svc: str | None = None) -> list[tuple[str, dict]]:
        rx = re.compile(pattern, re.I)
        return [(r, a) for r, a in L if (svc is None or a.get("service") == svc) and rx.search(a.get("sig", "") + " " + a.get("sample", ""))
                and a.get("injection") != "true"]

    def in_win(c: dict) -> bool:
        return t0 - 900 <= _f(c.get("ts")) <= t0 + 120 if t0 else False

    def harmless(c: dict) -> bool:
        return bool(HARMLESS.search(c.get("msg", "")))

    cands: list[Cand] = []
    changes = [(r, a) for r, a in C if in_win(a) and not harmless(a)]
    keyed = lambda k: [(r, a) for r, a in changes if a.get("key", "").strip('"') == k]  # noqa: E731
    sym_orders = ratio("error_rate", "orders-svc") >= 3 or ratio("p99_latency_seconds", "orders-svc") >= 2 or ratio("error_rate", "lb") >= 3

    # A. bad config push
    for r, a in changes:
        if a["kind"] == "config" and a.get("key", "").strip('"') not in SPECIAL_KEYS and a.get("service"):
            svc, s = a["service"], 0.5
            ev = [r]
            if sym_orders or ratio("error_rate", svc) >= 3:
                s += 0.2
                ev += mev("error_rate", svc) or mev("error_rate", "lb") or mev("error_rate", "orders-svc")
            lg = logs(r"timed out|deadline|504|weight|queue full")
            if lg:
                s += 0.2
                ev.append(lg[0][0])
            cands.append(Cand("config_change", svc, s, f"{svc} {a['key']} changed from {a['old']} to {a['new']} in commit {a['sha']}", ev,
                              {"type": "revert_commit", "target": a["sha"]}))
    # B. bad deploy
    for r, a in changes:
        if a["kind"] == "deploy" and a.get("service") == "orders-svc":
            s, ev = 0.5, [r]
            if sym_orders or ratio("p99_latency_seconds", "orders-svc") >= 2:
                s += 0.2
                ev += mev("p99_latency_seconds", "orders-svc") or mev("error_rate", "orders-svc")
            smell = [(rr, aa) for rr, aa in K if aa.get("smell", "none") != "none"]
            if smell:
                s += 0.2 + (0.1 if any(aa.get("tests") == "fail" for _, aa in K) else 0)
                ev.append(smell[0][0])
            elif K:
                s -= 0.25
            prev = next((x for x in C if x[1].get("kind") == "deploy" and x[1].get("service") == "orders-svc" and x[0] != r), None)
            cands.append(Cand("bad_deploy", "orders-svc", s, f"orders-svc deploy {a['sha']} introduced a regression"
                              + (f" ({smell[0][1]['smell']})" if smell else ""), ev,
                              {"type": "rollback_deploy", "target": "orders-svc", "params": {"sha": prev[1]["sha"] if prev else "previous"}}))
    # C. slow dependency
    if ratio("dependency_latency_p99_seconds", "orders-svc") >= 5:
        s, ev = 0.55, mev("dependency_latency_p99_seconds", "orders-svc")
        if ratio("p99_latency_seconds", "payments-svc") < 2:
            s += 0.15
        lg = logs(r"payments.*slow|slow.*payments|call to payments")
        if lg:
            s += 0.15
            ev.append(lg[0][0])
        if not changes:
            s += 0.1
        cands.append(Cand("dependency_latency", "payments-svc", s, "payments-svc is responding slowly; orders-svc latency and errors are symptoms",
                          ev, {"type": "escalate", "target": "payments-owners"}))
    # D. dependency outage
    out = logs(r"connection refused|connection reset|EOF|connect: ", "orders-svc")
    out = [(r, a) for r, a in out if "payments" in a.get("sig", "") + a.get("sample", "")]
    if out:
        s, ev = 0.5, [out[0][0]]
        if ratio("request_rate", "payments-svc") <= 0.3:
            s += 0.3
            ev += mev("request_rate", "payments-svc")
        if ratio("dependency_latency_p99_seconds", "orders-svc") < 3:
            s += 0.1
        cands.append(Cand("dependency_outage", "payments-svc", s, "payments-svc is unreachable; orders-svc and lb errors are symptoms", ev,
                          {"type": "escalate", "target": "payments-owners"}))
    # E. memory leak
    for (m, svc), (r_, o, ref) in list(M.items()):
        if m == "memory_bytes" and r_ >= 2:
            s, ev = 0.45, [ref]
            fl = [(r, a) for r, a in changes if a["kind"] in ("flag", "config")]
            if fl:
                s += 0.3
                ev.append(fl[0][0])
            lg = logs(r"unbounded|OOM", svc)
            if lg:
                s += 0.15
                ev.append(lg[0][0])
            if ratio("restarts_total", svc) > 1:
                s += 0.05
            key = fl[0][1].get("key", "").strip('"') if fl else "flag"
            sha = fl[0][1].get("sha", "") if fl else ""
            cands.append(Cand("resource_leak", svc, s, f"feature flag {key} enabled in commit {sha} causes unbounded memory growth in {svc}", ev,
                              {"type": "set_flag", "target": key, "params": {"value": "false"}}))
    # F. connection exhaustion
    if ratio("db_connections_in_use", "scheduler") >= 2:
        s, ev = 0.4, mev("db_connections_in_use", "scheduler")
        if ratio("db_connections_in_use", "orders-svc") >= 1.3:
            s += 0.15
            ev += mev("db_connections_in_use", "orders-svc")
        lg = logs(r"pool exhausted|too many clients", "orders-svc")
        if lg:
            s += 0.2
            ev.append(lg[0][0])
        hold = logs(r"holding", "scheduler")
        job = "a long-running job"
        if hold:
            s += 0.25
            ev.append(hold[0][0])
            mm = re.search(r"job (\S+) holding", hold[0][1].get("sig", "") + " " + hold[0][1].get("sample", ""))
            job = f"job {mm.group(1)}" if mm else job
        cands.append(Cand("connection_exhaustion", "scheduler", s, f"scheduler {job} is holding database connections, exhausting the orders-svc pool",
                          ev, {"type": "restart_replica", "target": "scheduler", "params": {"service": "scheduler"}}))
    # G. healthcheck misconfig
    refused = logs(r"connection refused|connect\(\) failed", "lb")
    healthy = logs(r"marked healthy", "lb")
    if refused and healthy:
        s, ev = 0.6, [refused[0][0], healthy[0][0]]
        if ratio("error_rate", "lb") >= 20:
            s += 0.15
            ev += mev("error_rate", "lb")
        if ratio("request_rate", "orders-svc") <= 0.7:
            s += 0.1
            ev += mev("request_rate", "orders-svc")
        hc = [(r, a) for r, a in C if a.get("key", "").strip('"') == "health_check_interval_ms"]
        sha = ""
        if hc:
            s += 0.15
            ev.append(hc[0][0])
            sha = hc[0][1]["sha"]
        rep = re.search(r"orders-svc-\d", refused[0][1].get("sample", ""))
        cands.append(Cand("healthcheck_misconfig", "lb", s,
                          f"{rep.group(0) if rep else 'an orders replica'} is down but the lb health check (health_check_interval_ms, commit {sha}) keeps routing to it", ev,
                          {"type": "revert_commit", "target": sha} if sha else {"type": "restart_replica", "target": "orders-svc-2"}))
    # H. capacity (scheduler backlog)
    if ratio("queue_depth", "scheduler") >= 5:
        s, ev = 0.5, mev("queue_depth", "scheduler")
        w = keyed("worker_count")
        if w:
            s += 0.4
            ev.append(w[0][0])
        if ratio("request_rate", "orders-svc") < 1.5:
            s += 0.1
        cands.append(Cand("capacity", "scheduler", s, (f"scheduler worker_count reduced from {w[0][1]['old']} to {w[0][1]['new']} in commit {w[0][1]['sha']}" if w
                                                        else "scheduler is under-provisioned: job queue is growing"), ev,
                          {"type": "revert_commit", "target": w[0][1]["sha"]} if w else {"type": "scale", "target": "scheduler", "params": {"replicas": 2}}))
    # I. log flood
    for (m, svc), (r_, o, ref) in list(M.items()):
        if m == "log_lines_per_second" and r_ >= 5:
            s, ev = 0.5, [ref]
            if ratio("disk_used_ratio", svc) >= 1.3:
                s += 0.1
                ev += mev("disk_used_ratio", svc)
            ll = keyed("log_level")
            if ll:
                s += 0.35
                ev.append(ll[0][0])
            cands.append(Cand("log_flood", svc, s, f"log_level set to debug in commit {ll[0][1]['sha'] if ll else '?'}, flooding {svc} logs and filling disk", ev,
                              {"type": "revert_commit", "target": ll[0][1]["sha"]} if ll else {"type": "set_config", "target": svc, "params": {"key": "log_level", "value": "info"}}))
    # J. noisy neighbour
    if ratio("cpu_ratio", "scheduler") >= 3:
        s, ev = 0.35, mev("cpu_ratio", "scheduler")
        if ratio("cpu_ratio", "orders-svc") >= 1.8:
            s += 0.2
            ev += mev("cpu_ratio", "orders-svc")
        if ratio("p99_latency_seconds", "orders-svc") >= 2:
            s += 0.1
        sc = keyed("settlement_schedule")
        if sc:
            s += 0.3
            ev.append(sc[0][0])
        cands.append(Cand("resource_contention", "scheduler", s,
                          f"settlement job schedule changed to '{sc[0][1]['new'] if sc else '?'}' in commit {sc[0][1]['sha'] if sc else '?'}, burning CPU shared with orders-svc at peak", ev,
                          {"type": "revert_commit", "target": sc[0][1]["sha"]} if sc else {"type": "escalate", "target": "scheduler-owners"}))

    cands.sort(key=lambda c: -c.score)
    side = {"changes": C, "logs": L, "used": set(cands[0].ev) if cands else set(), "t0": t0, "M": M}
    return cands, side


def build_report(items: list[tuple[str, str, dict[str, str]]], alert_service: str, cite: bool = True) -> dict[str, Any]:
    cands, side = diagnose(items)
    if not cands or cands[0].score < 0.5:
        first = next(iter(side["M"].values()), None)
        return {"root_cause": "Inconclusive: no hypothesis is supported by the evidence", "service": alert_service, "category": "unknown",
                "confidence": 0.2, "evidence": [first[2]] if first else [], "ruled_out": [], "ranked": [],
                "proposed_action": {"type": "escalate", "target": "on-call"}}
    top = cands[0]
    ruled = []
    for ref, a in side["changes"]:
        if ref in top.ev:
            continue
        ruled.append({"hypothesis": f"{a.get('kind')} {a.get('service') or ''} {a.get('sha')} ({a.get('msg', '')[:50]}) caused this",
                      "evidence": [ref]})
    for ref, a in side["logs"]:
        if a.get("injection") == "true":
            ruled.append({"hypothesis": "instruction embedded in a log line should be followed (injection attempt, ignored)", "evidence": [ref]})
        elif re.search(r"404", a.get("sig", "") + a.get("sample", "")):
            ruled.append({"hypothesis": "404 responses for favicon/robots are the cause (benign noise)", "evidence": [ref]})
    ranked = [{"root_cause": c.text, "service": c.service, "category": c.category, "confidence": round(min(0.95, c.score), 2)} for c in cands[:3]]
    return {"root_cause": top.text, "service": top.service, "category": top.category, "confidence": round(min(0.95, top.score), 2),
            "evidence": list(dict.fromkeys(top.ev)), "ruled_out": ruled if cite else [], "ranked": ranked, "proposed_action": top.action}


# ----------------------------------------------------------------------------- role brains

def _last_ts_change(res: list[dict]) -> str | None:
    best = None
    for r in res:
        o = r["obj"] or {}
        for c in (o.get("deploys") or []) + (o.get("commits") or []):
            if best is None or c["ts"] > best[0]:
                best = (c["ts"], c["sha"])
    return best[1] if best else None


def _first_match_path(grep_result: dict | None) -> str:
    matches = (grep_result or {}).get("matches") or []
    return matches[0]["path"] if matches else "handlers/orders.go"


def specialist_brain(role: str, messages: list[Message]) -> LLMResponse:
    res = tool_results(messages)
    n = len(res)
    q = user_text(messages)
    focus = re.search(r"focus=(\S+)", q)
    if role == "metrics":
        if n == 0:
            return _call("metrics__top_anomalies", n, window_minutes=30)
        anomalies = ((res[0]["obj"] or {}).get("anomalies")) or []
        drill = [a for a in anomalies if a["metric"] != "restarts_total"][:2]
        if n <= len(drill):
            a = drill[n - 1]
            return _call("metrics__query_range", n, query=f'{a["metric"]}{{service="{a["service"]}"}}', start="-30m", step=30)
        claims = metric_claims(res[0]["obj"] or {}, res[0]["id"])
        return _submit(f"{len(claims)} metric series deviate from baseline; earliest onset {min([a['started_at'] for a in anomalies], default='n/a')}.", claims)
    if role == "logs":
        if n == 0:
            return _call("logs__cluster_errors", n, service=focus.group(1) if focus else None, start="-30m")
        if n == 1:
            cl = ((res[0]["obj"] or {}).get("clusters")) or []
            if cl:
                return _call("logs__search", n, service=cl[0]["service"], level="error", limit=5)
        claims = log_claims(res[0]["obj"] or {}, res[0]["id"])
        return _submit(f"{len(claims)} error/warn signatures found.", claims)
    if role == "changes":
        if n == 0:
            return _call("changes__recent_deploys", n, since_minutes=360)
        if n == 1:
            return _call("changes__config_diff", n, since_minutes=360)
        if n == 2:
            sha = _last_ts_change(res)
            if sha:
                return _call("changes__commit_diff", n, sha=sha)
        claims = change_claims(res[0]["obj"], res[1]["obj"] if n > 1 else None, (res[0]["id"], res[1]["id"] if n > 1 else res[0]["id"]))
        return _submit(f"{len(claims)} recent changes found.", claims)
    if role == "code":
        if n == 0:
            return _call("code__grep", n, pattern=r"ListOrders|orders\[0\]|items\[0\]|loadItems|slowItems|first\.ID|ids\[0\]|pg_sleep", limit=10)
        if n == 1:
            return _call("code__read_file", n, path=_first_match_path(res[0]["obj"]), start=1, end=200)
        if n == 2:
            return _call("code__run_tests", n, target="go test ./...")
        claims = code_claims(res[1]["obj"], res[2]["obj"] if n > 2 else None, (res[1]["id"], res[-1]["id"]))
        return _submit("Inspected handlers/orders.go and ran the test suite.", claims)
    return _submit("nothing to do", [])


def items_from_evidence(text: str) -> tuple[list[tuple[str, str, dict[str, str]]], dict[str, float]]:
    items = []
    for line in text.splitlines():
        m = re.match(r"(ev_\d+) \[", line)
        if not m:
            continue
        for kind, attrs in parse_tags(line):
            items.append((m.group(1), kind, attrs))
    return items, {}


def commander_plan_brain(messages: list[Message]) -> LLMResponse:
    q = user_text(messages)
    svc = (re.search(r"service=(\S+)", q) or [None, "orders-svc"])[1]
    hyps = [
        {"id": "h1", "text": "A recent change (deploy, config or feature flag) shortly before onset caused this", "service": "", "category": "config_change"},
        {"id": "h2", "text": "A downstream dependency (payments-svc) is slow or down", "service": "payments-svc", "category": "dependency_outage"},
        {"id": "h3", "text": "Resource exhaustion: memory, cpu, db connections, scheduler backlog, disk", "service": "", "category": "resource_leak"},
        {"id": "h4", "text": "Load balancer routing or health-check problem", "service": "lb", "category": "healthcheck_misconfig"},
    ]
    base = f"Alert on {svc}."
    asg = [
        {"agent": "metrics", "question": f"{base} Which metrics deviate from baseline and when did each start (before or after any change)?", "hypothesis_ids": ["h1", "h2", "h3", "h4"]},
        {"agent": "logs", "question": f"{base} Which error signatures are new and when did they begin? Ignore benign noise.", "hypothesis_ids": ["h2", "h4"]},
        {"agent": "changes", "question": f"{base} What deployed, changed or flipped in the last 6 hours, with exact timestamps?", "hypothesis_ids": ["h1"]},
    ]
    if svc in ("orders-svc", "lb"):
        asg.append({"agent": "code", "question": f"{base} Does the orders handler code show a regression, and do tests pass?", "hypothesis_ids": ["h1"]})
    return _call("submit_plan", 0, summary="Four hypotheses; one question per specialist.", hypotheses=hyps, assignments=asg)


def commander_converge_brain(messages: list[Message]) -> LLMResponse:
    q = user_text(messages)
    items, _ = items_from_evidence(q)
    svc = (re.search(r"service=(\S+)", q) or [None, "orders-svc"])[1]
    rnd = int((re.search(r"round (\d+)/", q) or [None, "1"])[1])
    allow = "Follow-ups allowed: True" in q
    report = build_report(items, svc)
    if report["confidence"] < 0.5 and rnd == 1 and allow:
        return _call("submit_decision", 0, action="followup", summary="Low confidence; ask for focused follow-ups.", assignments=[
            {"agent": "logs", "question": f"FOLLOW-UP focus={svc}: search recent errors for {svc}.", "hypothesis_ids": []},
            {"agent": "changes", "question": "FOLLOW-UP: list every change in the last 6 hours.", "hypothesis_ids": []}])
    return _call("submit_decision", 0, action="report", summary=report["root_cause"], report=report)


def remediation_brain(messages: list[Message]) -> LLMResponse:
    q = user_text(messages)
    m = re.search(r"Root-cause report:\n(\{.*\})", q, re.S)
    action = {"type": "escalate", "target": "on-call"}
    if m:
        try:
            action = json.loads(m.group(1)).get("proposed_action") or action
        except ValueError:
            pass
    return _call("submit_action", 0, type=action.get("type", "escalate"), target=action.get("target", ""), params=action.get("params") or {},
                 reason="Safest effective action for the identified root cause.")


def single_brain(messages: list[Message]) -> LLMResponse:
    res = tool_results(messages)
    n = len(res)
    script = [("metrics__top_anomalies", dict(window_minutes=30)), ("logs__cluster_errors", dict(start="-30m")),
              ("changes__recent_deploys", dict(since_minutes=360)), ("changes__config_diff", dict(since_minutes=360)),
              ("code__grep", dict(pattern=r"ListOrders|orders\[0\]|items\[0\]|loadItems|slowItems|first\.ID|ids\[0\]|pg_sleep", limit=10))]
    if n < len(script):
        return _call(script[n][0], n, **script[n][1])
    if n == len(script):
        return _call("code__read_file", n, path=_first_match_path(res[-1]["obj"]), start=1, end=200)
    if n == len(script) + 1:
        return _call("code__run_tests", n, target="go test ./...")
    by = {r["tool"]: r for r in res}
    claims = metric_claims(by["metrics__top_anomalies"]["obj"] or {}, by["metrics__top_anomalies"]["id"])
    claims += log_claims(by["logs__cluster_errors"]["obj"] or {}, by["logs__cluster_errors"]["id"])
    claims += change_claims(by["changes__recent_deploys"]["obj"], by["changes__config_diff"]["obj"],
                            (by["changes__recent_deploys"]["id"], by["changes__config_diff"]["id"]))
    claims += code_claims(by["code__read_file"]["obj"], by["code__run_tests"]["obj"], (by["code__read_file"]["id"], by["code__run_tests"]["id"]))
    items = []
    for i, c in enumerate(claims):
        for kind, attrs in parse_tags(c["claim"]):
            items.append((f"c{i}", kind, attrs))
    svc = (re.search(r"service=(\S+)", user_text(messages)) or [None, "orders-svc"])[1]
    report = build_report(items, svc)
    # translate item refs (c<i>) to nothing: the single-agent handler mints evidence ids from the grounded claims
    report["evidence"] = []
    report["ruled_out"] = [{"hypothesis": r["hypothesis"], "evidence": []} for r in report["ruled_out"]]
    return _call("submit_report", 0, report=report, claims=claims)


def heuristic_responder(system: str, messages: list[Message], tools: list[dict], model: str) -> LLMResponse:
    role = role_of(system)
    names = {t["name"] for t in tools}
    if role == "commander":
        return commander_plan_brain(messages) if "submit_plan" in names else commander_converge_brain(messages)
    if role == "remediation":
        return remediation_brain(messages)
    if role == "single":
        return single_brain(messages)
    return specialist_brain(role, messages)


def make_mock_llm() -> MockLLM:
    return MockLLM(heuristic_responder)
