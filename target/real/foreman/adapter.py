#!/usr/bin/env python3
"""Nightshift <-> Foreman adapter: makes the REAL Foreman (github.com/naman777/Foreman) play the `scheduler` role.

It is the `scheduler` service in docker-compose.real.yml, so Prometheus, Loki, the chaos CLI and the agents see the same
names as with the stub, while the work is done by a real Foreman coordinator and real Docker workers.

  contract (target/stubs/scheduler)         real behaviour
  ---------------------------------------   -------------------------------------------------------------------------
  config  worker_count                      number of Foreman worker containers kept running (docker start/stop)
  config  settlement_schedule (cron)        a CPU-bound "settlement" job is submitted TO FOREMAN on that schedule
  POST /admin/jobs {hold_connections,..}    a Foreman job (postgres image) that holds N connections on the orders DB
  metrics queue_depth                       queued + scheduled jobs in Foreman
  metrics db_connections_in_use             connections held on the orders DB by Foreman jobs (pg_stat_activity)
  metrics process_*                         the Foreman coordinator container (docker stats)
  metrics http_requests_total/duration      the adapter's own probes/submissions against the Foreman API
  logs                                      Foreman coordinator + worker lines re-emitted as JSON with service=scheduler

A steady synthetic workload (JOB_RATE jobs/s, each `sleep JOB_SECONDS`) keeps the queue meaningful; it is submitted through
Foreman's public API like any other client. Standard library only; the docker CLI is used through the mounted socket.
"""
from __future__ import annotations

import http.server
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

FOREMAN_URL = os.environ.get("FOREMAN_URL", "http://foreman-coordinator:8080").rstrip("/")
FOREMAN_SECRET = os.environ.get("FOREMAN_SECRET", "dev-secret-change-in-prod")
WORKERS = [w for w in os.environ.get("WORKER_CONTAINERS", "").split(",") if w]
COORDINATOR_CONTAINER = os.environ.get("COORDINATOR_CONTAINER", "nightshift-foreman-coordinator-1")
ORDERS_DB_CONTAINER = os.environ.get("ORDERS_DB_CONTAINER", "nightshift-postgres-1")
ORDERS_DB_URL_FOR_JOBS = os.environ.get("ORDERS_DB_URL_FOR_JOBS", "postgres://nightshift:nightshift@host.docker.internal:15432/orders")
CONFIG_PATH = os.environ.get("CONFIG_PATH", "/config/scheduler.yaml")
JOB_RATE = float(os.environ.get("JOB_RATE", "1.5"))          # baseline jobs per second
JOB_SECONDS = int(os.environ.get("JOB_SECONDS", "4"))        # each baseline job sleeps this long
MAX_QUEUE = int(os.environ.get("MAX_QUEUE", "600"))           # stop submitting the baseline workload beyond this
PORT = int(os.environ.get("PORT", "8090"))
REPLICA = os.environ.get("REPLICA", "scheduler-1")
BURN_CORES = int(os.environ.get("SETTLEMENT_BURN_CORES", "6"))

START = time.time()
LOCK = threading.Lock()
STATE = {"worker_count": None, "schedule": "", "queue_depth": 0.0, "running": 0.0, "workers_online": 0.0,
         "capacity_slots": 0.0, "failed": 0.0, "completed": 0.0, "oldest_queued_s": 0.0, "db_conns": 0.0,
         "cpu_seconds": 0.0, "rss_bytes": 0.0, "coordinator_start": START, "submitted": 0}
REQS: dict[tuple[str, int], int] = {}
BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
HIST = {"buckets": [0] * len(BUCKETS), "count": 0, "sum": 0.0}
LOG_LINES = 0


def log(level: str, msg: str, service: str = "scheduler") -> None:
    global LOG_LINES
    LOG_LINES += 1
    print(json.dumps({"ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "level": level, "service": service,
                      "replica": REPLICA, "msg": msg}), flush=True)


def observe(path: str, status: int, seconds: float) -> None:
    with LOCK:
        REQS[(path, status)] = REQS.get((path, status), 0) + 1
        for i, b in enumerate(BUCKETS):
            if seconds <= b:
                HIST["buckets"][i] += 1
        HIST["count"] += 1
        HIST["sum"] += seconds


# ----------------------------------------------------------------------------------------------- Foreman API client
class Foreman:
    def __init__(self) -> None:
        self.token = ""

    def call(self, method: str, path: str, body: dict | None = None, auth: bool = True, record: str | None = None):
        url = FOREMAN_URL + path
        for attempt in (0, 1):
            headers = {"Content-Type": "application/json"}
            if auth:
                if not self.token:
                    self.login()
                headers["Authorization"] = "Bearer " + self.token
            req = urllib.request.Request(url, json.dumps(body).encode() if body is not None else None, headers, method=method)
            t0 = time.time()
            status, data = 0, None
            try:
                with urllib.request.urlopen(req, timeout=5) as r:
                    status, data = r.status, json.loads(r.read() or b"null")
            except urllib.error.HTTPError as e:
                status = e.code
                data = None
            except Exception:
                status = 502
            if record:
                observe(record, status, time.time() - t0)
            if status == 401 and auth and attempt == 0:
                self.token = ""
                continue
            return status, data
        return 0, None

    def login(self) -> None:
        s, d = self.call("POST", "/auth/login", {"api_key": FOREMAN_SECRET}, auth=False)
        if s == 200 and d:
            self.token = d["token"]

    def submit(self, name: str, image: str, command: str, cpu: int = 1, memory: int = 64, timeout: int = 60, priority: int = 5):
        return self.call("POST", "/jobs", {"name": name, "image_name": image, "command": command, "required_cpu": cpu,
                                           "required_memory": memory, "timeout_seconds": timeout, "max_retries": 0,
                                           "priority": priority}, record="/jobs")


FM = Foreman()


# ----------------------------------------------------------------------------------------------- docker helpers
def docker(*args: str, timeout: int = 20) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout)


def parse_yaml(path: str) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        for line in open(path, encoding="utf8"):
            line = line.split("#", 1)[0].strip()
            if ":" in line:
                k, v = line.split(":", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return out


def cron_due(expr: str, now: datetime) -> bool:
    """Supports the two forms the fault library uses: '*/N * * * *' and 'M H * * *'."""
    f = expr.split()
    if len(f) != 5:
        return False
    m = re.fullmatch(r"\*/(\d+)", f[0])
    if m and f[1:] == ["*", "*", "*", "*"]:
        return now.minute % max(1, int(m.group(1))) == 0
    if f[0].isdigit() and f[1].isdigit() and f[2:] == ["*", "*", "*"]:
        return now.minute == int(f[0]) and now.hour == int(f[1])
    return False


# ----------------------------------------------------------------------------------------------- background loops
def loop(fn, every: float):
    def run():
        while True:
            try:
                fn()
            except Exception as e:  # never let one bad iteration kill the adapter
                log("error", f"adapter loop {fn.__name__} failed: {type(e).__name__}: {e}")
            time.sleep(every)
    threading.Thread(target=run, daemon=True, name=fn.__name__).start()


def apply_worker_count() -> None:
    cfg = parse_yaml(CONFIG_PATH)
    try:
        want = max(0, min(int(cfg.get("worker_count", len(WORKERS))), len(WORKERS)))
    except ValueError:
        return
    with LOCK:
        changed = STATE["worker_count"] != want
        STATE["worker_count"] = want
        STATE["schedule"] = cfg.get("settlement_schedule", "")
    if not changed:
        return
    log("info", f"config reloaded: worker_count={cfg.get('worker_count')} (running {want} of {len(WORKERS)} Foreman workers)")
    for i, name in enumerate(WORKERS):
        r = docker("start" if i < want else "stop", *(() if i < want else ("-t", "1")), name)
        if r.returncode != 0:
            log("error", f"docker {'start' if i < want else 'stop'} {name} failed: {r.stderr.strip()[:120]}")
        else:
            log("info", f"worker {name} {'started' if i < want else 'stopped'} (worker_count={want})")


def submit_baseline() -> None:
    """Steady synthetic workload, submitted through Foreman's public API."""
    interval = 1.0 / JOB_RATE
    end = time.time() + 1.0
    while time.time() < end:
        if STATE["queue_depth"] < MAX_QUEUE:
            s, _ = FM.submit("nightshift-baseline", "alpine:3.20", f"sleep {JOB_SECONDS}", timeout=JOB_SECONDS + 30)
            if s == 201:
                with LOCK:
                    STATE["submitted"] += 1
        time.sleep(interval)


def settlement_cron() -> None:
    now = datetime.now(timezone.utc)
    sched = STATE["schedule"]
    if sched and cron_due(sched, now) and now.second < 5 and int(time.time() // 60) != STATE.get("last_settlement"):
        STATE["last_settlement"] = int(time.time() // 60)
        cmd = "for i in $(seq %d); do (timeout 75 sh -c 'while :; do :; done' &) ; done; sleep 75" % BURN_CORES
        s, _ = FM.submit("settlement-batch", "alpine:3.20", cmd, cpu=BURN_CORES, memory=128, timeout=90, priority=8)
        log("info", f"job settlement batch={int(time.time())} submitted to Foreman (cpu-bound x{BURN_CORES}, schedule={sched}) status={s}")


def collect_foreman() -> None:
    s, d = FM.call("GET", "/health", auth=False, record="/health")
    s2, summ = FM.call("GET", "/metrics/summary")
    s3, workers = FM.call("GET", "/workers")
    if s2 == 200 and summ:
        with LOCK:
            STATE["queue_depth"] = float(summ.get("queued", 0) + summ.get("scheduled", 0))
            STATE["running"] = float(summ.get("running", 0))
            STATE["failed"] = float(summ.get("failed", 0) + summ.get("timed_out", 0))
            STATE["completed"] = float(summ.get("completed", 0))
    if s3 == 200 and isinstance(workers, list):
        online = [w for w in workers if w.get("status") == "online"]
        with LOCK:
            STATE["workers_online"] = float(len(online))
            STATE["capacity_slots"] = float(sum(min(4, int(w.get("cpu_cores", 1))) for w in online))
    s4, queued = FM.call("GET", "/jobs?status=queued&limit=200", record="/jobs")
    if s4 == 200 and isinstance(queued, list) and queued:
        try:
            oldest = min(datetime.fromisoformat(j["submitted_at"].replace("Z", "+00:00")).timestamp() for j in queued)
            with LOCK:
                STATE["oldest_queued_s"] = max(0.0, time.time() - oldest)
        except Exception:
            pass
    else:
        with LOCK:
            STATE["oldest_queued_s"] = 0.0


_last_cpu_ts = [time.time()]


def collect_containers() -> None:
    r = docker("stats", "--no-stream", "--format", "{{.CPUPerc}}|{{.MemUsage}}", COORDINATOR_CONTAINER)
    if r.returncode == 0 and "|" in r.stdout:
        cpu, mem = r.stdout.strip().split("|", 1)
        now = time.time()
        with LOCK:
            STATE["cpu_seconds"] += float(cpu.strip().rstrip("%") or 0) / 100.0 * (now - _last_cpu_ts[0])
            m = re.match(r"([\d.]+)\s*([KMG]i?B)", mem.strip())
            if m:
                STATE["rss_bytes"] = float(m.group(1)) * {"KiB": 1024, "MiB": 1024 ** 2, "GiB": 1024 ** 3, "KB": 1e3, "MB": 1e6, "GB": 1e9}[m.group(2)]
        _last_cpu_ts[0] = now
    r = docker("inspect", "-f", "{{.State.StartedAt}}", COORDINATOR_CONTAINER)
    if r.returncode == 0:
        try:
            with LOCK:
                STATE["coordinator_start"] = datetime.fromisoformat(r.stdout.strip()[:26].rstrip("Z") + "+00:00").timestamp()
        except ValueError:
            pass
    r = docker("exec", ORDERS_DB_CONTAINER, "psql", "-U", "nightshift", "-d", "orders", "-tAc",
               "select count(*) from pg_stat_activity where datname='orders' and application_name='foreman-job'")
    if r.returncode == 0 and r.stdout.strip().isdigit():
        with LOCK:
            STATE["db_conns"] = float(r.stdout.strip())


def follow_logs(container: str, label: str) -> None:
    while True:
        try:
            p = subprocess.Popen(["docker", "logs", "-f", "--since", "0s", container], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            for line in p.stdout:  # type: ignore[union-attr]
                line = line.strip()
                if not line:
                    continue
                low = line.lower()
                level = "error" if any(k in low for k in ("error", "fail", "timed out", "exception")) else ("warn" if "warn" in low else "info")
                log(level, f"[{label}] {line[:300]}")
        except Exception as e:
            log("warn", f"log follower for {container} restarting: {e}")
        time.sleep(3)


# ----------------------------------------------------------------------------------------------- HTTP: /metrics, /healthz, /admin/jobs
def render_metrics() -> str:
    with LOCK:
        s = dict(STATE)
        reqs = dict(REQS)
        h = {"buckets": list(HIST["buckets"]), "count": HIST["count"], "sum": HIST["sum"]}
    o = []
    o.append("# TYPE queue_depth gauge\nqueue_depth %s" % s["queue_depth"])
    o.append("# TYPE jobs_running gauge\njobs_running %s" % s["running"])
    o.append("# TYPE workers_online gauge\nworkers_online %s" % s["workers_online"])
    o.append("# TYPE worker_capacity_slots gauge\nworker_capacity_slots %s" % s["capacity_slots"])
    o.append("# TYPE oldest_queued_age_seconds gauge\noldest_queued_age_seconds %s" % s["oldest_queued_s"])
    o.append("# TYPE db_connections_in_use gauge\ndb_connections_in_use %s" % s["db_conns"])
    o.append("# TYPE job_failures_total counter\njob_failures_total %s" % s["failed"])
    o.append("# TYPE jobs_completed_total counter\njobs_completed_total %s" % s["completed"])
    o.append("# TYPE process_cpu_seconds_total counter\nprocess_cpu_seconds_total %s" % s["cpu_seconds"])
    o.append("# TYPE process_resident_memory_bytes gauge\nprocess_resident_memory_bytes %s" % s["rss_bytes"])
    o.append("# TYPE process_start_time_seconds gauge\nprocess_start_time_seconds %s" % s["coordinator_start"])
    o.append("# TYPE log_lines_total counter\nlog_lines_total %s" % LOG_LINES)
    o.append("# TYPE http_requests_total counter")
    for (path, status), n in sorted(reqs.items()):
        o.append('http_requests_total{path="%s",status="%d"} %d' % (path, status, n))
    o.append("# TYPE http_request_duration_seconds histogram")
    for b, n in zip(BUCKETS, h["buckets"]):
        o.append('http_request_duration_seconds_bucket{le="%s"} %d' % (b, n))
    o.append('http_request_duration_seconds_bucket{le="+Inf"} %d' % h["count"])
    o.append("http_request_duration_seconds_sum %s\nhttp_request_duration_seconds_count %d" % (h["sum"], h["count"]))
    return "\n".join(o) + "\n"


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):  # keep stdout for structured logs only
        pass

    def _send(self, code: int, body: str, ctype: str = "application/json") -> None:
        data = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/metrics":
            self._send(200, render_metrics(), "text/plain; version=0.0.4")
        elif self.path in ("/healthz", "/health"):
            self._send(200, '{"status":"ok"}')
        else:
            self._send(404, '{"error":"not found"}')

    def do_POST(self):
        if self.path != "/admin/jobs":
            self._send(404, '{"error":"not found"}')
            return
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0)) or 0) or b"{}")
        except ValueError:
            self._send(400, '{"error":"invalid json"}')
            return
        name = str(body.get("name", "admin-job"))
        held = int(body.get("hold_connections", 0))
        dur = int(body.get("duration_s", 300))
        if held > 0:
            # A REAL Foreman job: a postgres client container that holds `held` connections on the orders DB for `dur` seconds.
            cmd = ('sh -c \'export PGAPPNAME=foreman-job; for i in $(seq %d); do psql "%s" -c "select pg_sleep(%d)" >/dev/null 2>&1 & done; wait\''
                   % (held, ORDERS_DB_URL_FOR_JOBS, dur))
            s, d = FM.submit(name, "postgres:16-alpine", cmd, cpu=1, memory=128, timeout=dur + 30, priority=8)
            log("info", f"job {name} submitted to Foreman: holds {held} orders-DB connections for {dur}s (status={s})")
            self._send(201 if s == 201 else 502, json.dumps({"submitted": s == 201, "job": d}))
        else:
            s, d = FM.submit(name, "alpine:3.20", f"sleep {dur}", timeout=dur + 30)
            self._send(201 if s == 201 else 502, json.dumps({"submitted": s == 201, "job": d}))


def main() -> None:
    log("info", f"scheduler adapter starting: Foreman at {FOREMAN_URL}, workers={WORKERS}, baseline {JOB_RATE} jobs/s x {JOB_SECONDS}s")
    for _ in range(60):  # wait for the coordinator
        s, _ = FM.call("GET", "/health", auth=False)
        if s == 200:
            break
        time.sleep(2)
    loop(apply_worker_count, 1.0)
    loop(collect_foreman, 2.0)
    loop(collect_containers, 5.0)
    loop(settlement_cron, 1.0)
    threading.Thread(target=lambda: [submit_baseline() or time.sleep(0) for _ in iter(int, 1)], daemon=True, name="baseline").start()
    threading.Thread(target=follow_logs, args=(COORDINATOR_CONTAINER, "coordinator"), daemon=True).start()
    for w in WORKERS:
        threading.Thread(target=follow_logs, args=(w, w.split("-", 1)[-1]), daemon=True).start()
    http.server.ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
