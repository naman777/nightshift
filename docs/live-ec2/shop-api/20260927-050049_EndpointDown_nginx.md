# EndpointDown on `nginx`

- alert condition first true: 2026-09-27 04:59:08 UTC
- watcher detected: 2026-09-27 04:59:57 UTC (+49s)
- diagnosis finished: 2026-09-27 05:00:49 UTC (investigation took 52.2s)
- model: gpt-6-luna / prompt v4 · llm calls 46 · tool calls 59 · cost $0.0198

## Root cause (bad_deploy, confidence 0.55, service `shop-api`)

shop-api deploy 8cba97a6 introduced a home-handler lookup of cfg()["discount_factor"], and shop-api logged KeyError for that key with endpoint degradation during the nginx probe failures; this is the leading explanation, but the evidence does not establish that it caused nginx's earliest failure or that the config key was absent.

## Evidence

- ev_1470
- ev_1473
- ev_1475
- ev_1477
- ev_1465

## Ruled out

- nginx service/process went down
- nginx upstream-port change caused the incident
- slow_ms config change caused the incident
- nsbox-lb/lb-sandbox errors explain the nginx probe failures

## Alternatives

- shop-api deploy 8cba97a6 plausibly caused home-page application errors via cfg()["discount_factor"], with degraded shop-api health overlapping nginx probe failures; causality for nginx's earliest failure is unproven. (bad_deploy, 0.55)
- An unresolved nginx HTTP/probe-path failure while nginx.service remained active; available evidence does not establish a specific nginx mechanism or trigger. (unknown, 0.35)
- Probe/monitoring anomaly affecting nginx :80 while the process remained active; no direct probe-path evidence confirms this. (unknown, 0.10)

## Proposed action (shadow mode: recorded, not executed)

`rollback_deploy` target `shop-api` params `{"deploy": "8cba97a6"}` tier `reversible`
