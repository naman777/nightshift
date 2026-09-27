# EndpointDown on `nginx`

- alert condition first true: 2026-09-27 04:55:18 UTC
- watcher detected: 2026-09-27 04:56:53 UTC (+96s)
- diagnosis finished: 2026-09-27 04:57:26 UTC (investigation took 33.0s)
- model: gpt-6-luna / prompt v4 · llm calls 29 · tool calls 43 · cost $0.0156

## Root cause (bad_deploy, confidence 0.78, service `shop-api`)

shop-api deploy 8cba97a6 introduced a home-page discount_factor lookup absent from the observed app.json, plausibly causing repeated GET / exceptions and shop-api's endpoint failure; nginx :80 also failed at onset, consistent with upstream impact but not directly proven. [ev_1417, ev_1440, ev_1444, ev_1427]

## Evidence

- ev_1417
- ev_1440
- ev_1442
- ev_1444
- ev_1427
- ev_1429

## Ruled out

- Host-wide resource contention caused both endpoint failures.
- The earlier shop-api slow_ms change caused onset.
- The nginx upstream port change caused onset.
- nginx had a new deploy at onset or was stopped then.

## Alternatives

- shop-api deploy 8cba97a6 caused application exceptions on GET / through the missing discount_factor lookup; upstream impact on nginx is plausible but not fully traced. (bad_deploy, 0.78)
- A separate nginx-local endpoint failure with no retrieved error details. (unknown, 0.15)

## Proposed action (shadow mode: recorded, not executed)

`rollback_deploy` target `shop-api` params `{"sha": "previous good deploy before 8cba97a6"}` tier `reversible`
