# Onboarding onto a real host (EC2), and what was actually verified

Run on 2026-09-26/27 against a real Ubuntu 26.04 EC2 instance (2 vCPU, 7.6 GB) that already ran a real service: the author's C++ load
balancer ([Load-Balancer-CPP](https://github.com/naman777/Load-Balancer-CPP)) as `lb.service`, uptime 17 days, three echo backends, no
Docker, no Prometheus, no metrics endpoint that Prometheus can read, logs only in journald. **Real language model (`gpt-6-luna`, prompt `v3`), not the offline reference policy.**

## Short answer

| Question | Answer |
| --- | --- |
| Has it been run against a real, already-running service on AWS? | **Yes, once: one host, one service, the author's own.** Not against anyone else's project, not multi-host, not Kubernetes. |
| Time from "nothing installed" to a real-model diagnosis of a live incident | Collectors installed in **~9 s** (downloads 2 s + `install_host.sh` 6.7 s); first probe data in ~45 s; the first live diagnosis landed **3 m 24 s** after the collectors started (21:27:53 -> 21:31:17 UTC, including my manual launch of the watcher). |
| Is it "two clicks"? | **No.** Repeatable install is one script, but the per-customer config (probe targets, service map, metric catalogue, unit names) was hand-written for this host. There is no auto-discovery. That is the gap to a CodeRabbit-style product. |
| Detection -> diagnosis latency on injected faults (14 runs) | alert fired **36-91 s** after injection (median 50 s); diagnosis report **93-165 s** after injection (median 120 s); investigation itself 20-55 s. |
| Cost | $0.006-$0.027 per investigation (median $0.015); **$0.38 for all 26 investigations** in this run. |
| Diagnosis quality | **Mixed, and reported as such below: 7 correct, 3 partial, 8 wrong of 18 scored investigations, plus 1 fault never detected.** |

## What was installed on the host (all removable with `onboard/uninstall_host.sh --purge`)

Under `~/nightshift-run/`, as systemd units, nothing containerised, the monitored service untouched:

* `blackbox_exporter` - HTTP/TCP probes of each service port (data path, admin/stats port, each backend)
* `node_exporter` (+ systemd collector) - host metrics and `unit_active` for the monitored units
* `prometheus`, `loki`, `alloy` (journald -> Loki, including systemd's own Started/Stopped lines)
* `onboard/lb_stats_exporter.py` - turns the balancer's own JSON `/stats` page into per-backend metrics (adapter pattern for any app with a stats page)
* `onboard/watch.py` (`nightshift-watch.service`) - **shadow mode**: polls Prometheus alerts, groups co-firing alerts per service, investigates with the real model, saves `reports/*.{md,json}`. Write actions are recorded by the policy layer and never executed.
* a **sandbox copy** of the balancer (`nsbox-lb.service`, ports 8090/8091/8093-8095, own config in a git repo) plus a load generator, so faults could be injected without touching the live service

Nightshift's own changes for this: `NIGHTSHIFT_CATALOGUE` / `NIGHTSHIFT_SERVICE_MAP` overrides, plain-text log parsing (this app logs `[LEVEL] msg`, not JSON), a `SystemdRuntimeBackend` (only `restart` is supported; everything else is refused), `top_anomalies` now returns the known metric names.

## Finding on the live service (real, not injected)

The balancer's admin port `:8081` has been **hung for the whole session** (probes time out at 4 s; `admin_port_up = 0` continuously). Cause, confirmed by reading `LoadBalancer.cpp::stats_loop()`: the stats listener is single-threaded and does a blocking `read()` on each accepted client with no timeout, so one client that connects and sends nothing freezes it. The data path on `:8080` is unaffected. `:8081` is open to `0.0.0.0/0` in the security group and `ss` shows connections to it from several unrelated internet hosts (85.217.149.21, 66.132.195.37, 20.169.91.44, 119.73.23.175, 89.21.67.181), i.e. scanners. Fix: restrict `:8081` to your IP (or bind it to 127.0.0.1) and add `SO_RCVTIMEO` to the accepted socket.

Did Nightshift find it? **Sometimes.** Four fresh real-model investigations of this same alert: 2 correctly identified the blocking-read defect from the source (`ev` on `LoadBalancer.cpp`), 1 answered "unknown, transient", 1 guessed a bind/listen failure. It never saw the scanner connections, because nothing exports socket state to it.

## Fault injection on the sandbox (ground truth known)

Telemetry was improved between rounds, so the rounds are reported separately. Grading is mine, against the injected cause: **correct** = the stated root cause names the real mechanism; **partial** = right class or right evidence but wrong scope or hedged; **wrong** = a different cause.

| Fault (injected cause) | v1: probes + host + logs | v2: + per-backend `backend_up`, `unit_active`, alert grouping (2 runs) | v3: + systemd lifecycle log lines (2 runs) |
| --- | --- | --- | --- |
| `config_break`: commit moves the backend pool to dead ports 9991-9993, SIGHUP | partial (found the commit, ranked "dependency outage" 0.34 over "config change" 0.32) | **correct, correct** (names the commit and "all backends unreachable", 0.79 both) | - |
| `idle_client_stats`: a client holds the stats port open | **correct** | **correct, correct** (blocking-read defect; trigger not confirmed) | - |
| `crashed_backend`: `echo_server :8094` killed | wrong (blamed health-check code, ruled out "backend down") | wrong (0.18); partial ("pool stopped accepting", said all three ports, not :8094) | - |
| `service_stopped`: `systemctl stop` | wrong (3 separate conflicting reports) | wrong, wrong (blamed the blocking-read code / an old reverted config commit) | partial (mentions "later graceful unit stop" but blames the backend pool); wrong (blames the old config commit) |
| `hung_backend`: `echo_server :8095` SIGSTOP | **not detected**, at all | not re-run | not re-run |

`hung_backend` is a latent fault under light load: the balancer's least-connections policy never routes to the frozen backend, requests stay at 200 in ~0.25 ms, so there is no user-visible symptom and no alert. That is a real property of black-box monitoring, not a bug, but it means Nightshift cannot see it.

Live-service admin-port alert (the real fault): 2 correct, 2 wrong (see above). Counting everything: 7 correct, 3 partial, 8 wrong of 18 scored investigations.

## Why it fails when it fails (observed, not guessed)

1. **Anchoring on a real code defect.** The code specialist reads the balancer source and finds the genuine blocking-read bug. In `service_stopped` and `crashed_backend` runs the commander then blames that bug for an unrelated outage. Evidence-gathering was fine; the ranking was not.
2. **Stale changes look like causes.** The sandbox config repo keeps the earlier `config_break` commit and its revert. Later faults were sometimes blamed on that reverted commit. Temporal reasoning (was the change still in effect at onset?) is weak.
3. **Metrics agent is often "inconclusive".** It queries at the alert's start time, when there may be a single sample, and early on it guessed raw metric names (`probe_success`, `host_cpu_utilization`) instead of the recorded ones. Returning the catalogue from `top_anomalies` fixed the naming problem, not the sparse-data one.
4. **Fixed cause taxonomy.** The taxonomy has no "blocking I/O bug" class, so a correct diagnosis of the stats bug is filed under `healthcheck_misconfig`, `bad_deploy` or `dependency_outage`. Judge the text, not the label.
5. **Made-up remediations.** Some proposals invent config keys (`stats_client_read_timeout`, `sandbox.conf.backends`). The systemd backend refuses everything except `restart`, and shadow mode never executes, so nothing ran, but the proposals are not trustworthy.
6. **Run-to-run variance.** Identical faults produced different verdicts. n=2 per cell here; this is an existence proof and a list of failure modes, not an accuracy number.

## What was NOT verified

* Any system other than the author's; more than one host; Kubernetes; CloudWatch/Datadog data; IAM/cross-account access.
* The durable Temporal path, Alertmanager, Postgres, the dashboard, approvals and the real remediation write path. The watcher is a single process with SQLite and executes nothing.
* Alert thresholds tuned on anything but this host; log-volume or memory/CPU faults; the `hung_backend` fault under concurrent load.
* Zero-config onboarding: none of the per-customer config is discovered automatically.

## Reproduce

```bash
# on the host (Ubuntu, sudo, python3-venv, curl, jq, unzip); copy the repo to ~/nightshift-run/nightshift first
python3 -m venv ~/nightshift-run/venv && ~/nightshift-run/venv/bin/pip install -e ~/nightshift-run/nightshift
~/nightshift-run/nightshift/onboard/download_binaries.sh     # ~2 s on AWS
~/nightshift-run/nightshift/onboard/install_host.sh
# secrets stay in ~/nightshift-run/nightshift/.env (OPENAI_API_KEY + NIGHTSHIFT_LLM_PROVIDER/COMMANDER_MODEL/SPECIALIST_MODEL/PROMPT_VERSION);
# non-secret settings are in onboard/host/watch.env
sudo cp onboard/host/nightshift-watch.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now nightshift-watch
onboard/run_faults.sh 2                                # sandbox faults: crashed_backend config_break idle_client_stats service_stopped
```

Raw data: `docs/live-ec2/reports/` (every report as `.md` + `.json`, including tool calls and evidence ids), `docs/live-ec2/fault_runs_*.jsonl` (timings per injected fault).
