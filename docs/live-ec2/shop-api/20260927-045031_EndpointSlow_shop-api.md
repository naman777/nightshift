# EndpointSlow on `shop-api`

- alert condition first true: 2026-09-27 04:47:58 UTC
- watcher detected: 2026-09-27 04:49:55 UTC (+118s)
- diagnosis finished: 2026-09-27 04:50:31 UTC (investigation took 35.2s)
- model: gpt-6-luna / prompt v4 · llm calls 33 · tool calls 44 · cost $0.0126

## Root cause (config_change, confidence 0.78, service `shop-api`)

shop-api's root endpoint is taking about 1.5 seconds, matching the 1500 ms `slow_ms` value introduced by config commit 8da102af shortly before onset; the available evidence does not confirm when the running process loaded it.

## Evidence

- ev_1345
- ev_1346
- ev_1349
- ev_1355
- ev_1360
- ev_1361
- ev_1362
- ev_1357
- ev_1359

## Ruled out

- nginx config/behavior independently caused the latency
- lb:8081 outage caused shop-api/nginx latency
- recent shop-api deploy caused the latency
- nsbox-lb all-backends-unreachable errors explain this shop-api onset
- earlier shop-api/nginx endpoint-up drops caused the sustained latency

## Alternatives

- shop-api slow_ms=1500 config introduced by 8da102af explains the root-path latency; runtime load is unverified. (config_change, 0.78)
- An unobserved shop-api runtime bottleneck; logs provide no direct confirmation and the timing/value match is weaker than the config explanation. (dependency_latency, 0.12)

## Proposed action (shadow mode: recorded, not executed)

`escalate` target `shop-api` params `{}` tier `read_only`
