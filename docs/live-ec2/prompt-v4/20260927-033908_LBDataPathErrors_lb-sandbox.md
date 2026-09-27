# LBDataPathErrors on `lb-sandbox`

- alert condition first true: 2026-09-27 03:37:50 UTC
- watcher detected: 2026-09-27 03:38:47 UTC (+57s)
- diagnosis finished: 2026-09-27 03:39:08 UTC (investigation took 20.9s)
- model: gpt-6-luna / prompt v4 · llm calls 19 · tool calls 29 · cost $0.0115

## Root cause (dependency_outage, confidence 0.97, service `lb-sandbox`)

lb-sandbox data-path failures were caused by config commit 27f30d26 changing the configured backend pool from ports 8093–8095 to 9991–9993, which remained active at incident onset and made the configured pool unreachable.

## Evidence

- ev_754
- ev_760
- ev_764
- ev_765
- ev_766

## Ruled out

- An earlier identical pool change was responsible for onset.
- A newly deployed lb-sandbox build caused the regression.
- A latent probe-code defect or admin-port issue explains the data-path failure.
- The deliberate systemd stop/restart itself explains the failing data path.

## Alternatives

- The active lb-sandbox backend pool configuration points to 9991–9993 instead of 8093–8095, leaving the data path without reachable backends. (dependency_outage, 0.97)
- Backend 8094 experienced intermittent health/up failures before the later all-backend data-path errors. (service_down, 0.48)

## Proposed action (shadow mode: recorded, not executed)

`set_config` target `lb-sandbox` params `{"key": "backends", "value": "8093, 8094, 8095"}` tier `reversible`
