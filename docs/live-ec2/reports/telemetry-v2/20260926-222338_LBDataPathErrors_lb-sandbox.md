# LBDataPathErrors on `lb-sandbox`

- alert condition first true: 2026-09-26 22:21:50 UTC
- watcher detected: 2026-09-26 22:22:49 UTC (+59s)
- diagnosis finished: 2026-09-26 22:23:38 UTC (investigation took 48.6s)
- model: gpt-6-luna / prompt v3 · llm calls 39 · tool calls 52 · cost $0.0159

## Root cause (healthcheck_misconfig, confidence 0.79, service `lb`)

lb-sandbox data-path errors were most likely caused by the backend-pool configuration change 1aea6206, which switched traffic from healthy ports 8093–8095 to ports 9991–9993 that were all reported unhealthy at onset.

## Evidence

- ev_425
- ev_440
- ev_443
- ev_450
- ev_452

## Ruled out

- H1: A bad balancer code deploy caused the errors.
- H3: Balancer overload or host resource pressure caused the errors.
- H4: A confirmed downstream backend outage caused the errors.

## Alternatives

- lb-sandbox backend-pool configuration change 1aea6206 directed the data path to newly configured ports 9991–9993, all reporting unhealthy as errors rose. (healthcheck_misconfig, 0.79)
- Unhealthy or unavailable listeners on ports 9991–9993 caused backend failures; the evidence does not identify their owning service or establish listener state directly. (dependency_outage, 0.37)

## Proposed action (shadow mode: recorded, not executed)

`set_config` target `lb` params `{"key": "backends", "value": "8093,8094,8095"}` tier `reversible`
