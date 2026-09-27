# LBBackendUnhealthy+LBUnitDown+LBDataPathErrors on `lb-sandbox`

- alert condition first true: 2026-09-27 03:59:30 UTC
- watcher detected: 2026-09-27 04:00:20 UTC (+50s)
- diagnosis finished: 2026-09-27 04:00:53 UTC (investigation took 33.1s)
- model: gpt-6-luna / prompt v4 · llm calls 33 · tool calls 45 · cost $0.0172

## Root cause (service_down, confidence 0.56, service `lb-sandbox`)

The lb-sandbox nsbox-lb.service on instance 127.0.0.1:9100 was inactive during the later observed failure, a service-down condition; available evidence does not establish who or what stopped it or confirm a trigger at the alert's reported onset.

## Evidence

- ev_967
- ev_973
- ev_974
- ev_979
- ev_980

## Ruled out

- A still-active backend-pool config change caused the outage.
- A recent deploy introduced a defect causing the unit to exit.
- Host resource contention caused the unit/backend failures.
- A code defect in blocking accept caused the observed stop.

## Alternatives

- nsbox-lb.service on lb-sandbox instance 127.0.0.1:9100 was inactive; stop initiator and exact transition trigger are unconfirmed. (service_down, 0.56)
- Potential blocking-accept shutdown hang in LoadBalancer.cpp, without evidence that its trigger occurred during this incident. (code_defect, 0.15)

## Proposed action (shadow mode: recorded, not executed)

`restart_replica` target `nsbox-lb.service` params `{"service": "lb-sandbox"}` tier `reversible`
