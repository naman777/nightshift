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
