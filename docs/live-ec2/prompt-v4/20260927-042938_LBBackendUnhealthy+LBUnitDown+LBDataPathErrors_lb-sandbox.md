# LBBackendUnhealthy+LBUnitDown+LBDataPathErrors on `lb-sandbox`

- alert condition first true: 2026-09-27 04:28:00 UTC
- watcher detected: 2026-09-27 04:28:47 UTC (+47s)
- diagnosis finished: 2026-09-27 04:29:38 UTC (investigation took 50.4s)
- model: gpt-6-luna / prompt v4 · llm calls 40 · tool calls 56 · cost $0.0180

## Root cause (service_down, confidence 0.73, service `lb-sandbox`)

The lb-sandbox instance running nsbox-lb.service (127.0.0.1:9100) went inactive around 04:28:02 UTC, causing its admin port, backends, and data path to fail; the initiating stop/crash mechanism and actor are unverified.

## Evidence

- ev_1243
- ev_1244
- ev_1245
- ev_1246
- ev_1247
- ev_1250
- ev_1240
- ev_1231
- ev_1232

## Ruled out

- A still-active backend-pool configuration change caused the 04:28 failure.
- Host CPU or memory contention/exhaustion stopped the sandbox unit.
- A newly deployed build caused the stop.

## Alternatives

- lb-sandbox nsbox-lb.service became inactive around 04:28:02; actor and precise stop/crash outcome are not established. (service_down, 0.73)
- A latent lb-sandbox backend health-transition defect may contribute to backend-down behavior, but evidence does not connect it to the simultaneous unit/admin failure. (code_defect, 0.18)

## Proposed action (shadow mode: recorded, not executed)

`restart_replica` target `lb-sandbox` params `{"service": "lb-sandbox"}` tier `reversible`
