"""Auto-discovery: inspect a Linux host and generate the whole Nightshift host profile, so nothing is written by hand.

    python -m onboard.discover                 # print what was found (read-only)
    python -m onboard.discover --out DIR       # also write prometheus.yml, rules.yml, catalogue.json, service_map.json, config.alloy,
                                               #   blackbox.yml, loki.yml, watch.env, unit_include.txt into DIR (install with PROFILE_DIR=DIR onboard/install_host.sh)

How it works (needs `ss`, `systemctl`, and passwordless sudo for `ss -p`; docker is optional):
  1. listening TCP sockets  ->  (port, pid)          `sudo ss -ltnpH`
  2. pid -> systemd unit    ->  /proc/<pid>/cgroup    (a service = a unit; all its child processes and ports belong to it)
  3. unit -> source repo    ->  WorkingDirectory / ExecStart walked up to the nearest `.git`
  4. each port is classified by talking to it for 2 s: answers HTTP -> `http` probe; connects but silent -> `tcp` probe + a warning
     (a silent port is either a non-HTTP protocol or ALREADY WEDGED, which is worth knowing at onboarding time)
Everything the model needs (service map, metric catalogue, unit map, per-service config/code repos) is generated from that.
"""
from __future__ import annotations

import argparse
import json
import re
import socket
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

# infrastructure we never monitor as a customer service
IGNORE_UNITS = re.compile(r"^(ssh|sshd|systemd-.*|snapd|amazon-ssm-agent|chrony|chronyd|multipathd|ModemManager|udisks2|acpid|nightshift-.*|user@.*|packagekit|polkit)\.service$")
IGNORE_PORTS = {22, 53}
_SS_LINE = re.compile(r"^LISTEN\s+\S+\s+\S+\s+(?P<addr>\S+):(?P<port>\d+)\s+\S+\s*(?P<users>users:.*)?$")
_PID = re.compile(r'\("(?P<proc>[^"]+)",pid=(?P<pid>\d+)')


@dataclass
class Listener:
    port: int
    bind: str
    proc: str
    pid: int


@dataclass
class Endpoint:
    port: int
    probe: str = "tcp"          # http | tcp
    note: str = ""


@dataclass
class Service:
    name: str
    unit: str
    procs: set[str] = field(default_factory=set)
    endpoints: list[Endpoint] = field(default_factory=list)
    repo: str = ""


def parse_ss(text: str) -> list[Listener]:
    out: list[Listener] = []
    for line in text.splitlines():
        m = _SS_LINE.match(line.strip())
        if not m or not m.group("users"):
            continue
        for u in _PID.finditer(m.group("users")):
            out.append(Listener(int(m.group("port")), m.group("addr").strip("[]"), u.group("proc"), int(u.group("pid"))))
    return out


def unit_from_cgroup(text: str) -> str | None:
    """`0::/system.slice/lb.service` -> `lb.service`; user sessions, scopes (docker containers, ssh sessions) -> None."""
    for line in text.splitlines():
        path = line.rsplit(":", 1)[-1]
        for part in reversed(path.strip("/").split("/")):
            if part.endswith(".service") and not part.startswith("user@"):
                return part
    return None


def probe_host(bind: str) -> str:
    return "127.0.0.1" if bind in ("0.0.0.0", "*", "::", "") else bind


def classify_port(bind: str, port: int, timeout: float = 2.0) -> Endpoint:
    host = probe_host(bind)
    try:
        with socket.create_connection((host, port), timeout=timeout) as s:
            s.settimeout(timeout)
            s.sendall(b"GET / HTTP/1.0\r\nHost: localhost\r\n\r\n")
            try:
                data = s.recv(16)
            except socket.timeout:
                return Endpoint(port, "tcp", "accepts connections but sends nothing within 2s: not HTTP, or ALREADY UNRESPONSIVE")
            return Endpoint(port, "http" if data.startswith(b"HTTP/") else "tcp", "" if data.startswith(b"HTTP/") else "answers, but not HTTP")
    except OSError as e:
        return Endpoint(port, "tcp", f"could not connect: {e}")


def git_root(start: str) -> str:
    p = Path(start).resolve() if start else None
    while p and p != p.parent:
        if (p / ".git").exists():
            return str(p)
        p = p.parent
    return ""


def unit_workdir(unit: str) -> str:
    out = subprocess.run(["systemctl", "show", unit, "-p", "WorkingDirectory", "-p", "ExecStart"], capture_output=True, text=True).stdout
    wd = re.search(r"^WorkingDirectory=(.+)$", out, re.M)
    if wd and wd.group(1) not in ("", "/", "!/"):
        return wd.group(1).lstrip("!")
    path = re.search(r"path=(\S+?);", out)
    return str(Path(path.group(1)).parent) if path else ""


def repo_from_etc(procs: set[str], etc: str = "/etc") -> str:
    """Config that lives in a git repo but is deployed by symlink (e.g. /etc/nginx/conf.d/app.conf -> ~/app/nginx/app.conf): follow symlinks under /etc/<process>."""
    for proc in sorted(procs):
        base = Path(etc) / proc
        if not base.is_dir():
            continue
        for depth, pattern in enumerate(("*", "*/*", "*/*/*")):
            for f in base.glob(pattern):
                if f.is_symlink():
                    target = f.resolve()
                    if not str(target).startswith(etc):
                        root = git_root(str(target))
                        if root:
                            return root
    return ""


def discover(repo_overrides: dict[str, str] | None = None) -> list[Service]:
    ss = subprocess.run(["sudo", "-n", "ss", "-ltnpH"], capture_output=True, text=True).stdout
    services: dict[str, Service] = {}
    seen_ports: set[tuple[str, int]] = set()
    for lst in parse_ss(ss):
        if lst.port in IGNORE_PORTS:
            continue
        try:
            unit = unit_from_cgroup(Path(f"/proc/{lst.pid}/cgroup").read_text())
        except OSError:
            continue
        if not unit or IGNORE_UNITS.match(unit):
            continue
        name = unit.removesuffix(".service")
        svc = services.setdefault(name, Service(name, unit, repo=git_root(unit_workdir(unit))))
        svc.procs.add(lst.proc)
        if (name, lst.port) not in seen_ports:
            seen_ports.add((name, lst.port))
            svc.endpoints.append(classify_port(lst.bind, lst.port))
    for s in services.values():
        s.endpoints.sort(key=lambda e: e.port)
        if not s.repo:
            s.repo = repo_from_etc(s.procs)
        if repo_overrides and s.name in repo_overrides:
            s.repo = repo_overrides[s.name]
    return sorted(services.values(), key=lambda s: s.name)


# -- generation ------------------------------------------------------------------------------------------------------------------------------

def render_prometheus(services: list[Service]) -> str:
    def block(job: str, module: str, probe: str, targets: list[tuple[str, Service, Endpoint]], fmt: str) -> str:
        if not targets:
            return ""
        lines = [f"  - job_name: {job}", "    metrics_path: /probe", f"    params: {{module: [{module}]}}", "    static_configs:"]
        for _, s, e in targets:
            lines += [f'      - targets: ["{fmt.format(port=e.port)}"]', f"        labels: {{service: {s.name}, port: \"{e.port}\", probe: {probe}}}"]
        lines += ["    relabel_configs:", "      - {source_labels: [__address__], target_label: __param_target}", "      - {source_labels: [__param_target], target_label: instance}",
                  "      - {target_label: __address__, replacement: \"127.0.0.1:9115\"}"]
        return "\n".join(lines) + "\n"

    http = [(s.name, s, e) for s in services for e in s.endpoints if e.probe == "http"]
    tcp = [(s.name, s, e) for s in services for e in s.endpoints if e.probe == "tcp"]
    return ("global:\n  scrape_interval: 10s\n  scrape_timeout: 5s\n  evaluation_interval: 10s\n\nrule_files:\n  - /__ROOT__/host/rules.yml\n\nscrape_configs:\n"
            "  - job_name: node\n    static_configs:\n      - targets: [\"127.0.0.1:9100\"]\n        labels: {service: host}\n"
            + block("probe-http", "http_2xx", "http", http, "http://127.0.0.1:{port}/") + block("probe-tcp", "tcp_connect", "tcp", tcp, "127.0.0.1:{port}"))


def unit_include(services: list[Service]) -> str:
    """Regex alternation of the discovered units, valid both in a PromQL string and in node_exporter's flag. No backslashes ('.' becomes '[.]'),
    because a backslash is an escape in PromQL strings and in systemd ExecStart lines."""
    if not services:
        return "none[.]service"
    return "(" + "|".join(s.unit.removesuffix(".service").replace(".", "[.]") for s in services) + ")[.]service"


def _promql_path_regex(path: str) -> str:
    """A path as a PromQL-string-safe regex prefix: only '.' is special in a real path, and it must become '[.]' rather than the
    backslash escape re.escape() would use ('\\.'), because a backslash inside a PromQL string literal is itself an escape
    character (the same trap as the unit-name regex in unit_include())."""
    return path.replace(".", "[.]")


def render_disk_expr(services: list[Service]) -> str:
    ratio = '(1 - node_filesystem_avail_bytes{fstype!~"tmpfs|vfat|devtmpfs|overlay"} / node_filesystem_size_bytes{fstype!~"tmpfs|vfat|devtmpfs|overlay"})'
    expr = f'label_replace({ratio}, "service", "host", "mountpoint", ".*")'
    # shortest repo path first, so a longer (more specific) one applied later overrides it for any mount nested under both
    for s in sorted((s for s in services if s.repo), key=lambda s: len(s.repo)):
        pat = _promql_path_regex(s.repo) + ".*"
        expr = f'label_replace({expr}, "service", "{s.name}", "mountpoint", "^{pat}")'
    return expr


def render_rules(services: list[Service]) -> str:
    inc = unit_include(services)
    disk_expr = render_disk_expr(services)
    return f"""groups:
  - name: nightshift-generated-recording
    rules:
      - record: endpoint_up
        # 1 while the endpoint answers its probe; per-port series keep the port label
        expr: probe_success{{probe=~"http|tcp"}}
      - record: endpoint_latency_seconds
        expr: probe_duration_seconds{{probe=~"http|tcp"}}
      - record: unit_active
        expr: label_replace(node_systemd_unit_state{{state="active", name=~"{inc}"}}, "service", "$1", "name", "(.*)\\\\.service")
      - record: host_cpu_ratio
        expr: 1 - avg(rate(node_cpu_seconds_total{{mode="idle"}}[1m]))
        labels: {{service: host}}
      - record: host_memory_used_ratio
        expr: 1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes
        labels: {{service: host}}
      - record: host_disk_used_ratio
        expr: 1 - node_filesystem_avail_bytes{{mountpoint="/"}} / node_filesystem_size_bytes{{mountpoint="/"}}
        labels: {{service: host}}
      - record: disk_used_ratio
        # every REAL mounted filesystem (root plus any data/uploads volume), not virtual ones (tmpfs /run, /boot, EFI) -- a
        # dedicated volume filling up is invisible to endpoint probes and metrics-only checks, so it needs its own signal.
        # A mount under a known service's repo/data path is attributed to that service (best match = longest prefix, checked
        # longest-first so a subdirectory mount doesn't get attributed to a service whose path is merely a parent of it);
        # anything else is "host". Chained label_replace, since PromQL has no direct "does this label start with X" outside regex anchors.
        expr: {disk_expr}
  - name: nightshift-generated-alerts
    rules:
      - alert: DiskFull
        expr: disk_used_ratio > 0.9
        for: 20s
        labels: {{severity: critical}}
        annotations: {{summary: "a mounted filesystem is over 90% full"}}
      - alert: EndpointDown
        expr: endpoint_up == 0
        for: 30s
        labels: {{severity: critical}}
        annotations: {{summary: "an endpoint stopped answering its probe"}}
      - alert: UnitDown
        expr: unit_active == 0
        for: 20s
        labels: {{severity: critical}}
        annotations: {{summary: "systemd unit is not active"}}
      - alert: EndpointSlow
        expr: endpoint_latency_seconds > 1
        for: 1m
        labels: {{severity: warning}}
        annotations: {{summary: "an endpoint takes more than 1s to answer its probe"}}
"""


def render_alloy(services: list[Service]) -> str:
    out = ['loki.write "local" {\n  endpoint {\n    url = "http://127.0.0.1:3100/loki/api/v1/push"\n  }\n}\n']
    for s in services:
        ident = re.sub(r"\W", "_", s.name)
        for suffix, match, extra in (("", f"_SYSTEMD_UNIT={s.unit}", ""), ("_lifecycle", f"UNIT={s.unit}", ', source = "systemd"')):
            out.append(f'loki.source.journal "{ident}{suffix}" {{\n  matches    = "{match}"\n  labels     = {{service = "{s.name}", unit = "{s.unit}"{extra}}}\n'
                       f'  max_age    = "72h"\n  forward_to = [loki.write.local.receiver]\n}}\n')
    return "\n".join(out)


def render_service_map(services: list[Service]) -> dict:
    svc = {s.name: {"role": f"systemd unit {s.unit}; processes: {', '.join(sorted(s.procs))}; listens on " +
                            ", ".join(f":{e.port} ({e.probe})" for e in s.endpoints) + (f"; source repo {s.repo}" if s.repo else ""),
                    "calls": [], **({"config": f"git repo {s.repo}"} if s.repo else {})} for s in services}
    svc["host"] = {"role": "the machine itself; node_exporter metrics", "calls": []}
    return {"services": svc, "notes": "Generated by onboard/discover.py from listening sockets and systemd cgroups. Dependencies between services are NOT inferred; "
                                       "only black-box probes, host metrics and journald logs exist unless the app exports more."}


def render_catalogue(services: list[Service]) -> dict:
    names = [s.name for s in services]
    return {"endpoint_up": names, "endpoint_latency_seconds": names, "unit_active": names,
            "host_cpu_ratio": ["host"], "host_memory_used_ratio": ["host"], "host_disk_used_ratio": ["host"],
            "disk_used_ratio": ["host", *(s.name for s in services if s.repo)]}


def render_watch_env(services: list[Service], root: str) -> str:
    repos = {s.name: s.repo for s in services if s.repo}
    lines = ["PROMETHEUS_URL=http://127.0.0.1:9090", "LOKI_URL=http://127.0.0.1:3100", "LOKI_PLAIN_TEXT=1", "NIGHTSHIFT_BACKEND=live",
             f"NIGHTSHIFT_CATALOGUE={root}/host/catalogue.json", f"NIGHTSHIFT_SERVICE_MAP={root}/host/service_map.json",
             f"DEPLOY_LOG={root}/deploys.jsonl", "NIGHTSHIFT_RUNTIME=systemd",
             "NIGHTSHIFT_SYSTEMD_UNITS='" + json.dumps({s.name: s.unit for s in services}) + "'",
             "NIGHTSHIFT_CONFIG_REPOS='" + json.dumps(repos) + "'", "NIGHTSHIFT_CODE_ROOTS='" + json.dumps(repos) + "'",
             f"NIGHTSHIFT_DB_URL=sqlite:///{root}/nightshift.db", f"NIGHTSHIFT_REPORTS={root}/reports", "NIGHTSHIFT_INCIDENT_BUDGET_USD=1.0", "NIGHTSHIFT_MEMORY=0",
             "NIGHTSHIFT_PROMPT_VERSION=v4"]
    return "\n".join(lines) + "\n"


def report(services: list[Service]) -> str:
    lines = [f"Discovered {len(services)} service(s):"]
    for s in services:
        lines.append(f"  {s.name}  (unit {s.unit}, procs {', '.join(sorted(s.procs))}" + (f", repo {s.repo}" if s.repo else ", no git repo found") + ")")
        for e in s.endpoints:
            lines.append(f"    :{e.port:<6} {e.probe:<5}" + (f"  WARNING: {e.note}" if e.note else ""))
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", help="write the generated profile into this directory")
    ap.add_argument("--repo", action="append", default=[], metavar="SERVICE=PATH", help="set/override a service's source/config git repo (repeatable)")
    ap.add_argument("--root", default=str(Path.home() / "nightshift-run"), help="install root used inside generated paths")
    args = ap.parse_args()
    services = discover(dict(r.split("=", 1) for r in args.repo))
    print(report(services))
    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        # blackbox / loki configs do not depend on what was found: reuse the shipped ones
        here = Path(__file__).parent / "host"
        for f in ("blackbox.yml", "loki.yml"):
            (out / f).write_text((here / f).read_text(encoding="utf8"), encoding="utf8")
        (out / "prometheus.yml").write_text(render_prometheus(services), encoding="utf8")
        (out / "rules.yml").write_text(render_rules(services), encoding="utf8")
        (out / "config.alloy").write_text(render_alloy(services), encoding="utf8")
        (out / "catalogue.json").write_text(json.dumps(render_catalogue(services), indent=1), encoding="utf8")
        (out / "service_map.json").write_text(json.dumps(render_service_map(services), indent=1), encoding="utf8")
        (out / "watch.env").write_text(render_watch_env(services, args.root), encoding="utf8")
        (out / "unit_include.txt").write_text(unit_include(services), encoding="utf8")
        print(f"\nwrote profile to {out}  (install: PROFILE_DIR={out} onboard/install_host.sh)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
