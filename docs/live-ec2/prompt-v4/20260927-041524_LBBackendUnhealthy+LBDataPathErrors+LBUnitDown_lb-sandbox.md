# LBBackendUnhealthy+LBDataPathErrors+LBUnitDown on `lb-sandbox`

- alert condition first true: 2026-09-27 04:13:40 UTC
- watcher detected: 2026-09-27 04:14:39 UTC (+59s)
- diagnosis finished: 2026-09-27 04:15:24 UTC (investigation took 44.7s)
- model: gpt-6-luna / prompt v4 · llm calls 24 · tool calls 38 · cost $0.0136

## Root cause (service_down, confidence 0.62, service `lb-sandbox`)

The lb-sandbox service, specifically the nsbox-lb.service instance using admin endpoint 127.0.0.1:9100, became inactive by 04:14:00 UTC; this service-down event best explains the simultaneous loss of backend probes, but the exact initiator or exit reason is not established.

## Evidence

- ev_1105
- ev_1106
- ev_1107
- ev_1112
- ev_1098

## Ruled out

- A sandbox backend config rollout caused the incident
- Host resource contention/exhaustion caused the service and backends to fail
- An admin-listener code defect alone explains the whole-unit/data-path failure

## Alternatives

- nsbox-lb.service on lb-sandbox became inactive at the incident boundary, with stop/crash initiator unconfirmed. (service_down, 0.62)
- A main-listener bind/listen failure could terminate the lb-sandbox process, but there is no evidence this path triggered. (code_defect, 0.15)

## Proposed action (shadow mode: recorded, not executed)

`restart_replica` target `lb-sandbox` params `{"service": "lb-sandbox"}` tier `reversible`
