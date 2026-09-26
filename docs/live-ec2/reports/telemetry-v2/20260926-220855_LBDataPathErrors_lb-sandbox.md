# LBDataPathErrors on `lb-sandbox`

- alert condition first true: 2026-09-26 22:07:20 UTC
- watcher detected: 2026-09-26 22:08:19 UTC (+59s)
- diagnosis finished: 2026-09-26 22:08:55 UTC (investigation took 36.8s)
- model: gpt-6-luna / prompt v3 · llm calls 33 · tool calls 40 · cost $0.0172

## Root cause (dependency_outage, confidence 0.79, service `lb`)

lb-sandbox data-path probes failed after config change d364187f switched the backend pool to 9991–9993, leaving the balancer with no reachable backends; the logs confirm the resulting all-backends-unreachable errors, though destination-port failures were not independently established.

## Evidence

- ev_255
- ev_262
- ev_263
- ev_271
- ev_272
- ev_273
- ev_274

## Ruled out

- Host resource contention caused the data-path probe failures.
- Admin-listener failure caused the data-path alert.
- A deployed code defect is established as the incident cause.

## Alternatives

- lb-sandbox configured to route to 9991–9993 by d364187f, resulting in no reachable backends (dependency_outage, 0.79)
- lb-sandbox probe implementation defect involving blocking or incorrect health-check response handling; code risks are identified but not tied to this alert (bad_deploy, 0.18)

## Proposed action (shadow mode: recorded, not executed)

`set_config` target `lb` params `{"key": "backends", "value": "8093,8094,8095"}` tier `reversible`
