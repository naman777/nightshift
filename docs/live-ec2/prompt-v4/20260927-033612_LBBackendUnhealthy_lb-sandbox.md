# LBBackendUnhealthy on `lb-sandbox`

- alert condition first true: 2026-09-27 03:34:20 UTC
- watcher detected: 2026-09-27 03:35:19 UTC (+59s)
- diagnosis finished: 2026-09-27 03:36:12 UTC (investigation took 52.6s)
- model: gpt-6-luna / prompt v4 · llm calls 43 · tool calls 63 · cost $0.0251

## Root cause (service_down, confidence 0.18, service `lb-sandbox`)

The lb-sandbox backend at 127.0.0.1:8094 became unavailable, reducing the healthy pool to two; available evidence does not establish whether this was a backend process/port failure or a health-check failure.

## Evidence

- ev_734
- ev_735
- ev_737
- ev_749
- ev_750
- ev_751
- ev_752

## Ruled out

- The sandbox.conf backend-pool rollout caused the current loss of 8094.
- A recent service deploy caused a regression at backend 8094.
- The entire lb-sandbox LB unit or its admin port went down at the reported onset.

## Alternatives

- The lb-sandbox backend at 127.0.0.1:8094 became unavailable; precise mechanism is unresolved between a process/port failure and an LB health-check failure. (service_down, 0.18)
- The lb-sandbox health-check path incorrectly marked backend 127.0.0.1:8094 unhealthy; no evidence confirms a health-check fault. (healthcheck_misconfig, 0.12)

## Proposed action (shadow mode: recorded, not executed)

`escalate` target `lb-sandbox backend owner` params `{}` tier `read_only`
