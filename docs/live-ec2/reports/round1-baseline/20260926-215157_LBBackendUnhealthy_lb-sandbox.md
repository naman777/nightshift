# LBBackendUnhealthy on `lb-sandbox`

- alert condition first true: 2026-09-26 21:51:00 UTC
- watcher detected: 2026-09-26 21:51:35 UTC (+35s)
- diagnosis finished: 2026-09-26 21:51:57 UTC (investigation took 22.1s)
- model: gpt-6-luna / prompt v3 · llm calls 25 · tool calls 30 · cost $0.0104

## Root cause (healthcheck_misconfig, confidence 0.68, service `lb`)

lb-sandbox's health-check implementation misclassifies reachable backends returning non-2xx responses as unhealthy (code evidence ev_130); the temporary backend-port config change d74bfb5f was reverted before probe failures began and is not established as the cause (ev_119, ev_120, ev_122).

## Evidence

- ev_130
- ev_122
- ev_123
- ev_119
- ev_120
- ev_124
- ev_129

## Ruled out

- The temporary backend-port config change directly caused the observed probe failure.
- Host CPU or memory pressure caused probe failures.
- A lb-sandbox binary deployment introduced the regression.
- Backend connection refusals are established as the cause.

## Alternatives

- lb-sandbox health-check implementation marks reachable backends unhealthy when they return non-2xx HTTP statuses. (healthcheck_misconfig, 0.68)
- A backend outage or refusal may have reduced the healthy backend count, but available logs and aggregate metrics do not identify failed ports or connection outcomes. (dependency_outage, 0.19)

## Proposed action (shadow mode: recorded, not executed)

`none` target `lb-sandbox` params `{}` tier `read_only`
