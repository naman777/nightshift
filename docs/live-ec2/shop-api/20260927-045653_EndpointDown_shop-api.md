# EndpointDown on `shop-api`

- alert condition first true: 2026-09-27 04:55:18 UTC
- watcher detected: 2026-09-27 04:56:14 UTC (+56s)
- diagnosis finished: 2026-09-27 04:56:53 UTC (investigation took 39.4s)
- model: gpt-6-luna / prompt v4 · llm calls 29 · tool calls 49 · cost $0.0163

## Root cause (bad_deploy, confidence 0.66, service `shop-api`)

shop-api deploy 8cba97a6 introduced a GET / KeyError by unconditionally reading the absent `discount_factor` config key, and matching exceptions began immediately after deploy; this explains failures when probes request `/`, but the evidence does not confirm probe paths or establish why nginx’s endpoint also failed.

## Evidence

- ev_1401
- ev_1405
- ev_1407
- ev_1408
- ev_1409
- ev_1406

## Ruled out

- The nginx proxy_pass change caused the endpoint failures.
- Host-wide resource contention explains both endpoint failures.
- A simultaneous nginx unit stop caused nginx endpoint failure.
- The earlier shop-api process KILL caused the 04:55 endpoint failure.
- The steadily-down lb :8081 or nsbox-lb transition is established as causal.

## Alternatives

- shop-api deploy 8cba97a6 causes GET / to raise KeyError for missing `discount_factor`; it is the best-supported explanation for shop-api failure, with probe routing unconfirmed and the concurrent nginx failure unexplained. (bad_deploy, 0.66)
- An unobserved host/network or probe-path issue could account for both endpoint failures, but retrieved evidence does not establish it. (unknown, 0.18)

## Proposed action (shadow mode: recorded, not executed)

`rollback_deploy` target `shop-api` params `{"sha": "previous good deployment"}` tier `reversible`
