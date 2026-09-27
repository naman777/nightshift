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
  5. unix-socket-only backends (PHP-FPM, uWSGI, ...) -> resolved from an already-discovered nginx-style config's
     `fastcgi_pass unix:...` target, so a daemon with no TCP port still becomes a first-class service
  6. dependencies -> each HTTP endpoint is poked once, then `ss` is sampled a few times for TCP/unix connections from one
     service's process to another's listening address; `service_map.json`'s `calls` is the full transitive closure, so a
     two-hop dependency (nginx -> php-fpm -> mariadb, the last hop over a unix socket MySQL's client library uses invisibly
     for host 'localhost') is listed directly rather than requiring the model to guess which service to check next
Everything the model needs (service map, metric catalogue, unit map, per-service config/code repos) is generated from that.
"""
from __future__ import annotations

import argparse
import json
import re
import socket
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

# infrastructure we never monitor as a customer service
IGNORE_UNITS = re.compile(r"^(ssh|sshd|systemd-.*|snapd|amazon-ssm-agent|chrony|chronyd|multipathd|ModemManager|udisks2|acpid|nightshift-.*|user@.*|packagekit|polkit)\.service$")
IGNORE_PORTS = {22, 53}
_SS_LINE = re.compile(r"^LISTEN\s+\S+\s+\S+\s+(?P<addr>\S+):(?P<port>\d+)\s+\S+\s*(?P<users>users:.*)?$")
_SS_UNIX_LINE = re.compile(r"^u_str\s+LISTEN\s+\S+\s+\S+\s+(?P<path>/\S+)\s+\S+\s+\S+\s+\S+\s*(?P<users>users:.*)?$")
_PID = re.compile(r'\("(?P<proc>[^"]+)",pid=(?P<pid>\d+)')
_UNIX_UPSTREAM = re.compile(r"(?:fastcgi_pass|proxy_pass|uwsgi_pass)\s+unix:(?P<path>/\S+?)(?:;|:)")


@dataclass
class Listener:
    port: int
    bind: str
    proc: str
    pid: int


@dataclass
class Endpoint:
    port: int
    probe: str = "tcp"          # http | tcp | unix (unix: not blackbox-probed, port is 0 and the real address is in `path`)
    note: str = ""
    path: str = ""               # unix socket path, only set when probe == "unix"


@dataclass
class Service:
    name: str
    unit: str
    procs: set[str] = field(default_factory=set)
    endpoints: list[Endpoint] = field(default_factory=list)
    repo: str = ""
    log_files: list[str] = field(default_factory=list)   # app-level log files (journald misses these: MariaDB by default logs to
                                                            # journald, but many daemons -- PHP-FPM, most databases in other
                                                            # configs -- write their own error log instead, invisible otherwise)
    calls: list[str] = field(default_factory=list)         # transitive closure of services this one is observed connecting to


def parse_ss(text: str) -> list[Listener]:
    out: list[Listener] = []
    for line in text.splitlines():
        m = _SS_LINE.match(line.strip())
        if not m or not m.group("users"):
            continue
        for u in _PID.finditer(m.group("users")):
            out.append(Listener(int(m.group("port")), m.group("addr").strip("[]"), u.group("proc"), int(u.group("pid"))))
    return out


def parse_ss_unix(text: str) -> dict[str, tuple[str, int]]:
    """Unix-socket listeners: {socket path -> (process name, pid)}. Used to resolve an nginx `fastcgi_pass unix:...` (or
    `proxy_pass`/`uwsgi_pass`) target to the daemon actually behind it -- PHP-FPM, uWSGI, a unix-socket gunicorn, etc. -- which
    has no TCP port and so is otherwise invisible to `ss -ltnp`-based discovery entirely."""
    out: dict[str, tuple[str, int]] = {}
    for line in text.splitlines():
        m = _SS_UNIX_LINE.match(line.strip())
        if not m or not m.group("users"):
            continue
        u = _PID.search(m.group("users"))
        if u:
            out[m.group("path")] = (u.group("proc"), int(u.group("pid")))
    return out


def unix_backends(nginx_services: list[Service], unix_listeners: dict[str, tuple[str, int]]) -> dict[str, tuple[str, int]]:
    """For each nginx-like service with a discovered config repo, find `unix:` upstream targets in its config files and
    resolve each to a listening (proc, pid) via `unix_listeners`. Returns {socket_path: (proc, pid)}, deduplicated."""
    found: dict[str, tuple[str, int]] = {}
    for s in nginx_services:
        if not s.repo:
            continue
        for f in Path(s.repo).rglob("*.conf"):
            try:
                text = f.read_text(errors="replace")
            except OSError:
                continue
            for m in _UNIX_UPSTREAM.finditer(text):
                path = m.group("path")
                if path in unix_listeners:
                    found[path] = unix_listeners[path]
    return found


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


def discover_log_files(name: str, procs: set[str]) -> list[str]:
    """Best-effort file-log discovery for daemons that write their own error log instead of journald (systemd's default):
    check /var/log/<service-name>* and /var/log/<process-name>* (files and one level of directory), for both the discovered
    service name and each of its process names, since the two often differ (service 'shop-api' vs process 'gunicorn';
    php-fpm's file is /var/log/php8.5-fpm.log while the unit is php8.5-fpm.service, matched via the .service name minus suffix)."""
    found: list[str] = []
    log_dir = Path("/var/log")
    if not log_dir.is_dir():
        return found
    for stem in {name, *procs}:
        for pattern in (f"{stem}*.log", f"{stem}/*.log"):
            for f in log_dir.glob(pattern):
                if f.is_file() and str(f) not in found:
                    found.append(str(f))
    return sorted(found)


def parse_ss_unix_estab(text: str) -> list[dict]:
    """Rows for connected (not listening) unix stream sockets. Columns are the same six ss always prints (state, local
    addr/port, peer addr/port) whether the socket is bound to a path or anonymous ('*'); `port` for a unix socket is really
    its kernel inode number, which is how two ends of the SAME connection are paired up (see `unix_call_edges`)."""
    rows = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 8 or parts[0] != "u_str" or parts[1] != "ESTAB":
            continue
        u = _PID.search(" ".join(parts[8:]))
        rows.append({"local_addr": parts[4], "local_port": parts[5], "peer_port": parts[7],
                     "pid": int(u.group("pid")) if u else None})
    return rows


def unix_call_edges(estab_rows: list[dict]) -> list[tuple[int, str]]:
    """(client_pid, server_socket_path) pairs: for each connected unix-stream row bound to a real path (the accepting side,
    e.g. MariaDB's end of a WordPress DB connection), find its peer by matching inode ('port') numbers and read the PID on
    that side -- the client. A plain destination-port lookup (as for TCP) doesn't work here because unix sockets have no
    ports; correlating by inode is the equivalent operation."""
    by_port = {r["local_port"]: r for r in estab_rows}
    edges = []
    for r in estab_rows:
        if r["local_addr"] == "*" or r["pid"] is None:
            continue
        peer = by_port.get(r["peer_port"])
        if peer and peer["pid"] is not None:
            edges.append((peer["pid"], r["local_addr"]))
    return edges


def discover_dependencies(services: list[Service], rounds: int = 10, delay_s: float = 0.15) -> dict[str, set[str]]:
    """One-hop 'calls' edges actually observed on the wire (not inferred from config): which service's process holds a
    connection -- TCP or unix socket -- to which other service's listening address. Catches dependencies no config file
    states, such as a PHP app's DB connection (MySQL's client library connects over a unix socket for host 'localhost',
    invisible to any wp-config.php/nginx-vhost text search).

    A per-request dependency connection (e.g. a DB connection held only while handling that one HTTP request) can be open
    for a few milliseconds -- far shorter than the gap between "send a request" and "then go sample ss" if those happen one
    after another. So request generation and `ss` sampling run CONCURRENTLY on a background thread for the whole sampling
    window, not sequentially; even then, a connection faster than one full round can still be missed entirely (documented
    as a known limitation, not silently assumed away)."""
    name_by_unit = {s.unit: s.name for s in services}
    tcp_port_to_service = {e.port: s.name for s in services for e in s.endpoints if e.probe in ("http", "tcp")}
    unix_listeners = parse_ss_unix(subprocess.run(["sudo", "-n", "ss", "-lxpH"], capture_output=True, text=True).stdout)

    def svc_of_pid(pid: int) -> str | None:
        try:
            unit = unit_from_cgroup(Path(f"/proc/{pid}/cgroup").read_text())
        except OSError:
            return None
        return name_by_unit.get(unit) if unit else None

    path_to_service = {path: svc_of_pid(pid) for path, (_, pid) in unix_listeners.items()}
    http_ports = [e.port for s in services for e in s.endpoints if e.probe == "http"]

    stop = threading.Event()

    def hammer() -> None:
        while not stop.is_set():
            for port in http_ports:
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.5) as c:
                        c.sendall(b"GET / HTTP/1.0\r\nHost: localhost\r\n\r\n")
                        c.recv(1)  # block briefly on the response so the request (and any DB call it makes) is in flight, not already finished
                except OSError:
                    pass

    threads = [threading.Thread(target=hammer, daemon=True) for _ in range(3)]  # a few concurrent requesters: more chances the
    for t in threads:                                                            # dependency connection is open at any given sample
        t.start()
    try:
        edges: dict[str, set[str]] = {s.name: set() for s in services}
        for _ in range(rounds):
            # `ss -tnp state established` (unlike plain `ss -tn`) prints no Netid/State columns at all:
            # recv-q send-q local-addr:port peer-addr:port users:(...) -- peer is parts[3], not the usual parts[4].
            tcp = subprocess.run(["sudo", "-n", "ss", "-tnpH", "state", "established"], capture_output=True, text=True).stdout
            for line in tcp.splitlines():
                parts = line.split()
                u = _PID.search(line)
                if len(parts) < 4 or not u or ":" not in parts[3]:
                    continue
                src = svc_of_pid(int(u.group("pid")))
                dst = tcp_port_to_service.get(int(parts[3].rsplit(":", 1)[-1]))
                if src and dst and src != dst:
                    edges[src].add(dst)

            ux = subprocess.run(["sudo", "-n", "ss", "-xpH", "state", "connected"], capture_output=True, text=True).stdout
            for client_pid, path in unix_call_edges(parse_ss_unix_estab(ux)):
                src, dst = svc_of_pid(client_pid), path_to_service.get(path)
                if src and dst and src != dst:
                    edges[src].add(dst)
            time.sleep(delay_s)
        return edges
    finally:
        stop.set()
        for t in threads:
            t.join(timeout=2)


def transitive_closure(direct: dict[str, set[str]]) -> dict[str, set[str]]:
    """Full reachability, not just one hop: if nginx calls php-fpm and php-fpm calls mariadb, nginx's closure includes
    mariadb too. A single failed dependency n hops away should not require n rounds of the model guessing which service to
    check next -- the whole chain is listed for it up front."""
    out: dict[str, set[str]] = {}
    for start in direct:
        seen: set[str] = set()
        frontier = set(direct.get(start, ()))
        while frontier:
            seen |= frontier
            nxt: set[str] = set()
            for n in frontier:
                nxt |= direct.get(n, set()) - seen
            frontier = nxt
        out[start] = seen
    return out


def grantable_log_files(services: list[Service]) -> list[str]:
    """Log files this process cannot read now (owned by another user, e.g. root-only application logs) but that a real
    collector needs -- install_host.sh grants group-read via chgrp/chmod (not setfacl: survives simply, at the cost of not
    surviving a logrotate that recreates the file with fresh root-only permissions -- a known, documented limitation)."""
    import os

    return sorted({f for s in services for f in s.log_files if not os.access(f, os.R_OK)})


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

    # unix-socket-only backends (PHP-FPM, uWSGI, ...): no TCP port, so invisible to the loop above. Found by reading any
    # already-discovered service's config for a `unix:` upstream target and resolving it to whichever process is listening there.
    known_units = {s.unit for s in services.values()}
    for path, (proc, pid) in unix_backends(list(services.values()), parse_ss_unix(subprocess.run(["sudo", "-n", "ss", "-lxpH"], capture_output=True, text=True).stdout)).items():
        try:
            unit = unit_from_cgroup(Path(f"/proc/{pid}/cgroup").read_text())
        except OSError:
            continue
        if not unit or unit in known_units or IGNORE_UNITS.match(unit):
            continue
        name = unit.removesuffix(".service")
        known_units.add(unit)
        services[name] = Service(name, unit, procs={proc}, repo=repo_overrides.get(name, "") if repo_overrides else "",
                                 endpoints=[Endpoint(0, "unix", "no TCP port; not blackbox-probed", path=path)])

    for s in services.values():
        if not s.repo and s.name not in (repo_overrides or {}):
            s.repo = repo_from_etc(s.procs)
        s.log_files = discover_log_files(s.name, s.procs)

    closure = transitive_closure(discover_dependencies(list(services.values())))
    for s in services.values():
        s.calls = sorted(closure.get(s.name, ()))
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
        # app-level log files: the daemon's own error log (e.g. PHP-FPM), which systemd's journal never sees because the
        # process writes to a file directly instead of stdout/stderr.
        for i, f in enumerate(s.log_files):
            out.append(f'local.file_match "{ident}_file_{i}" {{\n  path_targets = [{{"__path__" = "{f}", "service" = "{s.name}", "source" = "file"}}]\n}}\n'
                       f'loki.source.file "{ident}_file_{i}" {{\n  targets    = local.file_match.{ident}_file_{i}.targets\n'
                       f'  forward_to = [loki.write.local.receiver]\n}}\n')
    return "\n".join(out)


def render_service_map(services: list[Service]) -> dict:
    def listens(s: Service) -> str:
        if not s.endpoints:
            return "no discovered listener"
        return "listens on " + ", ".join(e.path + " (unix socket)" if e.probe == "unix" else f":{e.port} ({e.probe})" for e in s.endpoints)

    svc = {s.name: {"role": f"systemd unit {s.unit}; processes: {', '.join(sorted(s.procs))}; {listens(s)}"
                            + (f"; source repo {s.repo}" if s.repo else "") + (f"; app log files: {', '.join(s.log_files)}" if s.log_files else ""),
                    "calls": s.calls, **({"config": f"git repo {s.repo}"} if s.repo else {})} for s in services}
    svc["host"] = {"role": "the machine itself; node_exporter metrics", "calls": []}
    return {"services": svc, "notes": "Generated by onboard/discover.py from listening sockets, systemd cgroups, and a few rounds of observed TCP/unix-socket "
                                       "connections after lightly exercising each HTTP endpoint (see discover_dependencies). `calls` is the FULL transitive "
                                       "closure, not just one hop -- if A observably calls B and B calls C, A's `calls` already lists both B and C, so a "
                                       "two-hop dependency does not require guessing which service to check next. A dependency that never opened a new "
                                       "connection during the sampling window (e.g. only uses a long-lived pooled connection) will be missing here."}


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
            addr = e.path if e.probe == "unix" else f":{e.port}"
            lines.append(f"    {addr:<28} {e.probe:<5}" + (f"  WARNING: {e.note}" if e.note else ""))
        if s.log_files:
            lines.append(f"    log files: {', '.join(s.log_files)}")
        if s.calls:
            lines.append(f"    calls (observed, transitive): {', '.join(s.calls)}")
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
        grants = grantable_log_files(services)
        (out / "log_grants.txt").write_text("\n".join(grants) + ("\n" if grants else ""), encoding="utf8")
        if grants:
            print(f"\n{len(grants)} log file(s) found but not readable by this user (install_host.sh will chgrp+chmod them for the adm group): " + ", ".join(grants))
        print(f"\nwrote profile to {out}  (install: PROFILE_DIR={out} onboard/install_host.sh)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
