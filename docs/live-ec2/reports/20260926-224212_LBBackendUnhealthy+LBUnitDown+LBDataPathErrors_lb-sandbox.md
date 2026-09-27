# LBBackendUnhealthy+LBUnitDown+LBDataPathErrors on `lb-sandbox`

- alert condition first true: 2026-09-26 22:40:50 UTC
- watcher detected: 2026-09-26 22:41:37 UTC (+47s)
- diagnosis finished: 2026-09-26 22:42:12 UTC (investigation took 35.7s)
- model: gpt-6-luna / prompt v3 · llm calls 30 · tool calls 49 · cost $0.0148

## Root cause (dependency_outage, confidence 0.67, service `lb`)

The lb-sandbox backend-pool config switch in commit 1aea6206 to ports 9991–9993 immediately preceded repeated all-backends-unreachable errors, consistent with a backend availability/configuration failure; the running process's loaded config is unverified.

## Evidence

- ev_636
- ev_638
- ev_641
- ev_637
- ev_643
- ev_642
- ev_644
- ev_634
- ev_635

## Ruled out

- Host capacity/CPU degradation caused the initial backend and data-path failure.
- A confirmed bad code deploy caused the incident.

## Alternatives

- The lb-sandbox configured backend pool was switched to ports 9991–9993 shortly before all-backends-unreachable errors, suggesting those upstreams were unavailable; runtime config application is not verified. (dependency_outage, 0.67)
- The lb-sandbox backend configuration/healthcheck handling may have failed to handle an unavailable backend (including pre-existing degradation of backend 8094); precise mechanism is not established. (healthcheck_misconfig, 0.42)
- Host CPU/resource contention contributed to later unit/backend failures, but sampled CPU degradation starts after initial errors and first unit failure. (resource_contention, 0.17)

## Proposed action (shadow mode: recorded, not executed)

`set_config` target `lb-sandbox` params `{"key": "backends", "value": "8093,8094,8095"}` tier `reversible`
