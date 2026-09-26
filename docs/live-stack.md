# Live stack verification (Docker, 2026-09-26)

Everything below was run on Docker Desktop (Windows, WSL2 backend, 7.6 GB), not the simulator.

## What was verified

| Check | Result |
| --- | --- |
| Go services + stub LB/scheduler compile and vet in `golang:1.22` | pass (`go build ./... && go vet ./...`) |
| `docker compose up -d --build`: 19 containers | all up; Postgres and Temporal healthy; 5/5 Prometheus targets up |
| Baseline traffic | ~278 req/s through lb, orders-svc x2, payments-svc; no alerts on a healthy system (after the fix below) |
| Inject `bad-config-push-lb-timeout-00` (`python -m chaos.cli scenario ...`) | error rate rose to 8%; `HighErrorRate_orders` fired ~2 min later; Alertmanager posted to the gateway; incident reached `awaiting_approval` seconds after the alert |
| Diagnosis, offline reference policy | **wrong** on live telemetry: "log_level set to debug ... flooding lb logs" (correct evidence was on the board) |
| Diagnosis, `gpt-6-luna` + prompt `v3` | **correct**: lb `upstream_timeout_ms` 2000 -> 50 (commit 7ec27a95), red herrings and 4 alternatives ruled out, proposed reversible `set_config upstream_timeout_ms=2000` |
| Approve from the dashboard API | audit rows `attempted` then `allowed`; config reverted; error rate 8.4% -> 0 |
| `docker kill nightshift-worker` mid-investigation, then `docker start` | same workflow resumed and completed with a correct cited diagnosis. Temporal history: planning ran once (attempt 1); of 7 specialist activities exactly 2 needed attempt 2 (the two in flight at the kill); every activity completed |

## Bugs found and fixed by running it

* `ServiceMemoryGrowth` fired on a healthy system at startup (memory warm-up > 1.8x its 30-minute minimum). The rule now requires a full 30 minutes of samples (`count_over_time(...[30m]) > 300` at 5 s scrapes).
* The gateway/worker raced Postgres and Temporal on startup and exited. `depends_on` now waits for `service_healthy`, Temporal has a healthcheck, and the gateway restarts on failure.
* Host port 3001 can be taken: the dashboard port is `DASHBOARD_PORT` (default 3001).
* **Dashboard-launched scenarios were investigated against the live stack, not the scenario.** `build_runtime` only used the simulated world when `NIGHTSHIFT_BACKEND=sim`, and the docker gateway is `live`, so a scenario launched from the dashboard saw healthy live telemetry and correctly came back "inconclusive" (evidence showed the real ~0.24 s p99 and ~90 req/s of load-generator traffic). A `scenario` label now always selects the simulated world (`tests/test_scenario_label_backend.py`). After the fix, single-agent `gpt-6-luna` launched from the dashboard: `bad-deploy-n-plus-one-00` correct (orders-svc bad_deploy, deploy ecda8e52, 0.96), `bad-config-push-lb-timeout-00` correct (lb config_change, commit e37cd672, 0.98, correct revert), `hard-02-decoy-config-outage-no-logs` inconclusive (0.15; a hard-set scenario with no logs).
* The runtime had no way to select a prompt version, so live runs silently used `v1`. `NIGHTSHIFT_PROMPT_VERSION`, `NIGHTSHIFT_LLM_PROVIDER` and the model variables are now passed through compose.

## What this changes about the claims

* **The simulator-to-live gap is real, and it is in the reference policy, not the agents' evidence gathering.** The offline policy scores 100% in the simulator and misdiagnosed the first live fault; the real model got it right. Treat offline-policy scores as harness validation only.
* **Single live incident, single fault type.** One correct real-model diagnosis is an existence proof, not an accuracy number. `bench/live.py` runs the benchmark against the live stack.

## Run it

```bash
python -m chaos.cli init
docker compose up -d --build
# real model: NIGHTSHIFT_LLM_PROVIDER=openai NIGHTSHIFT_COMMANDER_MODEL=gpt-6-luna NIGHTSHIFT_SPECIALIST_MODEL=gpt-6-luna NIGHTSHIFT_PROMPT_VERSION=v3 docker compose up -d gateway nightshift-worker
python -m chaos.cli scenario bad-config-push-lb-timeout-00
docker kill nightshift-worker && docker start nightshift-worker
```

## Real components (opt-in overlay: `docker-compose.real.yml`)

`make demo-real` (or `docker compose -f docker-compose.yml -f docker-compose.real.yml up -d --build`) swaps the two stubs for the real thing. The default stack is unchanged.

| Role | Real component | How it plugs in |
| --- | --- | --- |
| `lb` | your C++ load balancer ([Load-Balancer-CPP](https://github.com/naman777/Load-Balancer-CPP)) + `external/patches` | serves traffic on :8080 and Prometheus `/metrics` on :8081; reads `target/config/lb.yaml`; an entrypoint sends SIGHUP when that file changes |
| `scheduler` | your Foreman ([Foreman](https://github.com/naman777/Foreman), TypeScript) | real coordinator + 3 real Docker workers + Postgres/Redis/MinIO; `target/real/foreman/adapter.py` is the `scheduler` service and translates Foreman state into the stub's metric/config contract |

### What had to change in the C++ balancer (patches in `external/patches/`, please upstream them)

* `host:port` backends (it only accepted `127.0.0.1` ports), so it can reach other containers
* `upstream_timeout_ms` (answers 504), `health_check_interval_ms`, `health_check_path`, `max_conn`, `upstream_weight_orders_<n>`, all hot-reloadable; `key: value` YAML config accepted
* Prometheus `/metrics` (request counters by status, latency histogram, `upstream_healthy`, process metrics) and structured JSON logs (`LB_LOG_FORMAT=json`)
* explicit 502/503/504 responses instead of silently dropping the connection
* **bug fixes**: SIGHUP killed the process (the signal was blocked after the thread pool was created, so pool threads received it); stale unit test and `test.sh` bugs; CLI-pinned settings are no longer overwritten by a config reload
* tests: 34 unit + 11 integration, all pass

### What was verified live on the real components

| Fault | Real-component result |
| --- | --- |
| `bad-config-push-lb-timeout-00` on the real C++ balancer | timeout 2000 -> 50 ms reloaded within a second; the balancer produced hundreds of genuine 504s (error rate 4% -> 11%); `HighErrorRate_orders` fired; **`gpt-6-luna` + `v3` diagnosed it correctly** (lb, `upstream_timeout_ms` 2000 -> 50, alternatives ruled out); approved revert restored it and the error rate fell to baseline |
| `scheduler-backlog-workers-1-00` on real Foreman | the adapter stopped 2 of 3 real worker containers; the queue grew from ~3 to 200+; `JobQueueBacklog` fired; **the real model diagnosed it correctly** (scheduler, capacity, commit `95c25dc5` `worker_count` 8 -> 1, confidence 0.91); approved revert restarted the workers |

The offline reference policy, run on the same live Foreman fault, escalated with "commander could not converge" (confidence 0.1). That is the correct safe behaviour for a policy that cannot diagnose it, but it is another data point that the reference policy is only a harness check.

### Facts about the real components that shaped the design

* Foreman workers poll every 3 s and take **one job per poll**: ~0.33 jobs/s per worker, ~1 job/s with three, regardless of declared parallel slots. The adapter's baseline load is therefore 0.9 jobs/s (about 90% utilised). A queue of 100 takes ~3.5 min to build with 1 worker; with 2 workers the arrival rate barely exceeds capacity, so a `workers=2` scenario would take ~13 min to alert (computed, not measured).
* The real balancer fails over on connect errors, so a crashed replica is skipped within one request instead of causing sustained errors (not exercised live).

### Implemented but NOT yet exercised live on the real components

`bad_config_push` weight variant, `crashed_replica`, `noisy_neighbour` (the adapter submits a CPU-burning job to Foreman on the `settlement_schedule` cron), `db_connection_exhaustion` (the adapter submits a Foreman job that runs `psql` and holds N connections on the orders DB). `bench/live.py` has not been run against either stack.
