# Onboarding onto a real host (EC2), and what was actually verified

Two rounds, both on the same real Ubuntu 26.04 EC2 instance (2 vCPU, 7.6 GB). **Round 1** (2026-09-26/27, prompts v1-v3): the box already
ran the author's C++ load balancer ([Load-Balancer-CPP](https://github.com/naman777/Load-Balancer-CPP)) as `lb.service`, no Docker, no
Prometheus, logs only in journald; diagnosis quality was mixed (7 correct / 3 partial / 8 wrong of 18). **Round 2** (2026-09-27, prompt
v4): the diagnosis logic was fixed (state-first reasoning, a generic service vocabulary, a grounded-config-key guard) and auto-discovery
was added, then re-tested on the same LB target plus a **second, previously-unseen target** (an nginx + gunicorn + Flask "shop" API with
its own config schema) to check the fixes generalise rather than being tuned to the LB. **Real language model throughout (`gpt-6-luna`),
not the offline reference policy.**

## Short answer

| Question | Answer |
| --- | --- |
| Has it been run against a real, already-running service on AWS? | **Yes: two services on one host** (the author's own LB, plus a second app deployed for this test). Not against anyone else's project, not multi-host, not Kubernetes. |
| Time from "nothing installed" to a real-model diagnosis of a live incident | Collectors installed in **~9 s**; auto-discovery + install of the generated profile in **~10 s** (2.2 s discover + 7.9 s install); first live diagnosis landed **3 m 24 s** after the collectors started in round 1. |
| Is it "two clicks"? | **Closer, not there.** `onboard/discover.py` now reads listening ports, systemd units and git repos (following `/etc/*` config symlinks) and generates the whole profile with no hand-written config; `onboard/install_host.sh --profile-dir` installs it. What's still missing: an install wrapper the customer runs as one command, a webhook/IAM-based alert intake, and dependency inference between services (discovery finds services and ports, not who calls whom). |
| Detection -> diagnosis latency on injected faults (28 runs total) | alert fired **37-91 s** after injection (median 51 s); diagnosis report **93-186 s** after injection (median 122 s). |
| Cost | $0.006-$0.027 per investigation (median $0.016); **$0.38 (round 1) + ~$0.35 (round 2)** for 44 investigations. |
| Diagnosis quality, round 1 (prompts v1-v3, hand-written config) | Mixed: 7 correct, 3 partial, 8 wrong of 18 scored, plus 1 fault (frozen backend) never detected. |
| Diagnosis quality, round 2 (prompt v4, auto-discovered config) — **same LB target** | **15 correct, 1 partial, 0 wrong of 16** (4 fault types x 4 rounds). |
| Diagnosis quality, round 2 — **held-out shop-API target** (never seen while writing v4) | **9 correct, 1 partial, 2 wrong of 12** (3 rounds x 4 fault types), plus **1 run produced no report at all**. All 3 misses are the same fault type: see "The one fault type it still misses" below. |

## What was installed on the host (all removable with `onboard/uninstall_host.sh --purge`)

Under `~/nightshift-run/`, as systemd units, nothing containerised, the monitored services untouched:

* `blackbox_exporter` - HTTP/TCP probes of each service port (data path, admin/stats port, each backend)
* `node_exporter` (+ systemd collector) - host metrics and `unit_active` for the monitored units
* `prometheus`, `loki`, `alloy` (journald -> Loki, including systemd's own Started/Stopped lines)
* `onboard/discover.py` - **auto-discovery**: reads listening TCP sockets (`ss`), maps each pid to its systemd unit via `/proc/<pid>/cgroup`, classifies each port (answers HTTP -> probe as `http`; connects but stays silent -> probe as `tcp`, and flags a WARNING because a silent port may already be wedged), and finds each service's source/config repo (its `WorkingDirectory`, or by following `/etc/<process>/...` config symlinks to a git repo, e.g. nginx's `/etc/nginx/conf.d/*.conf`). Generates `prometheus.yml`, `rules.yml`, `catalogue.json`, `service_map.json`, `config.alloy` and `watch.env` with no hand-written config. `onboard/install_host.sh` accepts `PROFILE_DIR=<discover output>` to install a generated profile instead of the shipped hand-written one.
* `onboard/lb_stats_exporter.py` - turns the balancer's own JSON `/stats` page into per-backend metrics (adapter pattern for any app with a stats page; not part of the generated profile)
* `onboard/watch.py` (`nightshift-watch.service`) - **shadow mode**: polls Prometheus alerts, groups co-firing alerts per service, attaches a deterministic **state snapshot** (below), investigates with the real model, saves `reports/*.{md,json}`. Write actions are recorded by the policy layer and never executed.
* a **sandbox copy** of the balancer (`nsbox-lb.service`, ports 8090/8091/8093-8095, own config in a git repo) plus a load generator, and a **second real app** (`onboard/testapp/`: nginx -> gunicorn -> Flask -> SQLite "shop" API, `onboard/testapp/faults.sh`) used only as a held-out test target, so faults could be injected without touching the author's LB

Round-1 changes: `NIGHTSHIFT_CATALOGUE` / `NIGHTSHIFT_SERVICE_MAP` overrides, plain-text log parsing, a `SystemdRuntimeBackend` (only `restart` is supported; everything else is refused), `top_anomalies` returns the known metric names. **Round-2 changes** (diagnosis quality): prompt version `v4` (state-first rules, a generic `service`/`category` vocabulary instead of hard-coded demo names, two new categories — `service_down`, `code_defect`), `onboard/snapshot.py` (a deterministic "what changed and when" summary computed from Prometheus before the model runs, attached to every alert), and `agents/remediation.py::config_key_is_grounded` (a `set_config` proposal whose key never appears in any evidence is downgraded to `escalate`, so an invented setting cannot reach the approval queue).

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

## Round 2 (prompt v4): re-run on the same LB target, plus a held-out target

Same grading rule (correct / partial / wrong against the injected cause). Prompt v4 was written and tuned using only the LB target above; the "held-out" column is a second app it never saw during that work.

| Fault | Same LB target, 4 rounds | Held-out shop-API target, 3 rounds |
| --- | --- | --- |
| Process/backend killed directly (`crashed_backend` / `app_crash`) | **correct x4** (names the exact dead backend `127.0.0.1:8094` every time) | **0/3**: one round produced no report at all; the other two blamed a stale deploy commit and a stale nginx config change instead of the kill. **This is the one fault type v4 still misses; see below.** |
| Config change breaks routing (`config_break` / `bad_upstream`) | **correct x4**, and `set_config` proposals now use the real key (`backends`) and correct value, grounded in the evidence | 2 correct (names the exact commit and reverts it correctly), 1 wrong (`unknown`, 0.18) |
| Slow/blocking behaviour from config (`idle_client_stats` / `slow_config`) | **correct x4** (names the blocking-read code path, or the exact `slow_ms` setting) | **correct x3/3** (all six investigations name `slow_ms=1500` and the exact commit; `set_config slow_ms=0` proposed and grounded) |
| Service/unit stopped (`service_stopped`) / bad deploy (`bad_deploy`) | 3 correct + 1 partial (correctly identifies the unit went inactive; one run gets the causal order backwards) | 2 correct + 1 partial-wrong (`bad_deploy`: 2 rounds correctly name the exact code defect, a `KeyError` on a missing `discount_factor` config key, from the source; 1 round blames an unrelated SIGKILL) |

**Totals: same target 15 correct / 1 partial / 0 wrong of 16 (up from 7/3/8 of 18 in round 1). Held-out target 9 correct / 1 partial / 2 wrong of 12, plus 1 missing report.** The improvement is not just "tuned to the one target it was built against": `slow_config` and `bad_upstream` on a Flask/nginx app it had never seen scored as well as on the LB.

### The one fault type it still misses: a process killed outright

`crashed_backend` (an echo server killed) and `app_crash` (gunicorn's master killed with `SIGKILL`) are the same failure shape and both fail. The likely reason: a clean `systemctl stop` leaves an unambiguous `Stopping.../Stopped.../Deactivated successfully` lifecycle log the model can read (that is what made `service_stopped` improve so much between rounds). A hard kill leaves no such message — systemd just detects the exit and, for `shop-api` (`RestartSec=45`), the unit can still be down or freshly restarted by the time the investigation runs 40-120s later, with no log line saying why. This is a real gap in what black-box monitoring can see, not obviously a prompting problem: fixing it needs either a `systemd --failed`/exit-code/core-dump signal in the snapshot, or accepting `service_down` with unknown trigger as the correct, honest answer for this class (which several `crashed_backend` runs already gave, with a named instance and low confidence).

## Why it fails when it fails (v4, and what changed from v1-v3)

1. ~~Anchoring on a real code defect for unrelated outages~~ **fixed for `service_stopped`**: the systemd-lifecycle log lines plus the "commit to a mechanism" state-first rule stopped the code defect from swallowing unrelated failures in that fault; it still happens for `bad_deploy` r2 (SIGKILL blamed) and is the residual pattern for hard kills generally.
2. **Stale changes still occasionally look like causes** (`bad_upstream` r2 answered `unknown` after apparently discounting the real commit). The "still in effect at onset" rule reduced but did not eliminate this.
3. **Metrics agent is still often the weak link.** The state snapshot fixed the "no data at alert-start" problem for series that changed; it is silent by design for series that didn't (a crash that leaves everything else steady gives it nothing to point at).
4. **Fixed cause taxonomy**, now with `service_down` and `code_defect` added; judge the root-cause text, not only the label — v4's `service_down` answers are frequently correct even at low confidence.
5. **Made-up remediations are now blocked mechanically**, not just discouraged by the prompt: `config_key_is_grounded` downgrades an ungrounded `set_config` to `escalate`. All `set_config` proposals in round 2 used real keys (`backends`, `slow_ms`) seen in the evidence.
6. **Run-to-run variance is lower but not gone.** n=3-4 per cell; still not enough for an accuracy number, but the improvement (7/18 -> 15/16 on the same target) is large enough to be a real signal, not noise.

## What was NOT verified

* Any system other than the author's and the one test app deployed for this run; more than one host; Kubernetes; CloudWatch/Datadog data; IAM/cross-account access.
* The durable Temporal path, Alertmanager, Postgres, the dashboard, approvals and the real remediation write path. The watcher is a single process with SQLite and executes nothing.
* Alert thresholds tuned on anything but this host; log-volume or memory/CPU faults; the `hung_backend` fault under concurrent load; dependency inference between discovered services (discovery finds services and ports, not call graphs).
* True one-command onboarding: discovery + install is two commands and still needs `sudo`, a Python venv and manually-placed LLM credentials.

## Reproduce

```bash
# on the host (Ubuntu, sudo, python3-venv, curl, jq, unzip); copy the repo to ~/nightshift-run/nightshift first
python3 -m venv ~/nightshift-run/venv && ~/nightshift-run/venv/bin/pip install -e ~/nightshift-run/nightshift
~/nightshift-run/nightshift/onboard/download_binaries.sh     # ~2 s on AWS

# option A: auto-discovered profile (recommended)
~/nightshift-run/venv/bin/python -m onboard.discover --out ~/nightshift-run/host-generated   # read-only; prints what it found
PROFILE_DIR=~/nightshift-run/host-generated ~/nightshift-run/nightshift/onboard/install_host.sh

# option B: the shipped hand-written LB profile
~/nightshift-run/nightshift/onboard/install_host.sh

# secrets stay in ~/nightshift-run/nightshift/.env (OPENAI_API_KEY + NIGHTSHIFT_LLM_PROVIDER/COMMANDER_MODEL/SPECIALIST_MODEL/PROMPT_VERSION=v4);
# non-secret settings are in ~/nightshift-run/host/watch.env (option A writes this for you; option B copies onboard/host/watch.env)
sudo cp onboard/host/nightshift-watch.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now nightshift-watch

onboard/run_faults.sh 4                                                          # LB sandbox: crashed_backend config_break idle_client_stats service_stopped
FAULT_SCRIPT=onboard/testapp/faults.sh ALERT_SELECT='.labels.service=="nginx" or .labels.service=="shop-api"' \
  REPORT_RE='_(nginx|shop-api)[.]json$' FAULTS="app_crash slow_config bad_upstream bad_deploy" onboard/run_faults.sh 3   # shop-API held-out target
```

Raw data: `docs/live-ec2/reports/` and `docs/live-ec2/prompt-v4/` (round 1 / round 2 on the LB, every report as `.md` + `.json`), `docs/live-ec2/shop-api/` (round 2 held-out target), `docs/live-ec2/fault_runs_*.jsonl` (timings per injected fault).
