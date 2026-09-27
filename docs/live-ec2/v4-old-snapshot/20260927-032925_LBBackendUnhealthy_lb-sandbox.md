# LBBackendUnhealthy on `lb-sandbox`

- alert condition first true: 2026-09-27 03:27:50 UTC
- watcher detected: 2026-09-27 03:28:48 UTC (+58s)
- diagnosis finished: 2026-09-27 03:29:25 UTC (investigation took 37.1s)
- model: gpt-6-luna / prompt v4 · llm calls 30 · tool calls 47 · cost $0.0142

## Root cause (service_down, confidence 0.44, service `lb-sandbox`)

The lb-sandbox backend instance 127.0.0.1:8094 became unavailable at the incident onset, causing its health-check state and the aggregate healthy upstream count to drop; the evidence does not identify why that instance became unavailable.

## Evidence

- ev_679
- ev_680
- ev_681
- ev_682
- ev_683
- ev_692
- ev_694
- ev_695
- ev_696
- ev_697
- ev_698

## Ruled out

- H2: A sandbox balancer configuration or deploy change caused the 8094 health check/routing target to be invalid.
- H3: A health-check code defect incorrectly marked a still-available backend unhealthy.
- H4: Host-level resource contention or exhaustion prevented 8094 from accepting connections.

## Alternatives

- The lb-sandbox backend instance 127.0.0.1:8094 became unavailable at onset; reason is not established. (service_down, 0.44)
- The lb-sandbox health probe rejected a non-2xx HEAD response from 127.0.0.1:8094; code behavior can do this, but no response or trigger was observed. (healthcheck_misconfig, 0.18)

## Proposed action (shadow mode: recorded, not executed)

`escalate` target `lb-sandbox owning team` params `{}` tier `read_only`
