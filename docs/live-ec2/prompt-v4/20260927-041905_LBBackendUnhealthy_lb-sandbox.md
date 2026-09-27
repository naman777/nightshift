# LBBackendUnhealthy on `lb-sandbox`

- alert condition first true: 2026-09-27 04:17:30 UTC
- watcher detected: 2026-09-27 04:18:28 UTC (+58s)
- diagnosis finished: 2026-09-27 04:19:05 UTC (investigation took 36.6s)
- model: gpt-6-luna / prompt v4 · llm calls 30 · tool calls 47 · cost $0.0178

## Root cause (service_down, confidence 0.44, service `lb-sandbox`)

The lb-sandbox backend instance 127.0.0.1:8094 became unavailable around 04:17:28 UTC, leaving only two healthy backends; the evidence does not establish whether it was stopped or otherwise failed.

## Evidence

- ev_1156
- ev_1157
- ev_1158
- ev_1150
- ev_1155

## Ruled out

- A newly deployed lb-sandbox build caused a regression.
- The sandbox pool config change to ports 9991–9993 caused the outage.
- The load balancer service itself went down.
- A proven health-check code defect caused port 8094 to be marked unhealthy.

## Alternatives

- Backend instance 127.0.0.1:8094 on lb-sandbox became unavailable; the initiating process or operator action is not established. (service_down, 0.44)
- The lb-sandbox health check marked backend 127.0.0.1:8094 unhealthy before the independent backend_up probe first recorded failure; the cause of that health result is unknown. (healthcheck_misconfig, 0.30)
- A latent HTTP health-status classification defect may have marked an otherwise reachable backend unhealthy, but no event-level trigger evidence ties it to 8094 at onset. (code_defect, 0.12)

## Proposed action (shadow mode: recorded, not executed)

`escalate` target `lb-sandbox/backend operations team` params `{}` tier `read_only`
