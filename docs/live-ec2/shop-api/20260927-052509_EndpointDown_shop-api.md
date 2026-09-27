# EndpointDown on `shop-api`

- alert condition first true: 2026-09-27 05:23:38 UTC
- watcher detected: 2026-09-27 05:24:36 UTC (+58s)
- diagnosis finished: 2026-09-27 05:25:09 UTC (investigation took 32.6s)
- model: gpt-6-luna / prompt v4 · llm calls 31 · tool calls 40 · cost $0.0119

## Root cause (bad_deploy, confidence 0.96, service `shop-api`)

shop-api deploy 04d9f3df introduced a home-page dereference of absent cfg()["discount_factor"], producing repeated KeyError exceptions that broke the endpoint; logs show the failures at onset and a clean restart immediately before it.

## Evidence

- ev_1771
- ev_1782
- ev_1783
- ev_1785
- ev_1786
- ev_1787

## Ruled out

- Host capacity/resource pressure caused the endpoint failure.
- The earlier nginx proxy-port change caused the incident.
- The shop-api process crashed or its listener failed at onset.

## Alternatives

- Deploy 04d9f3df in shop-api dereferences missing discount_factor in the home endpoint, causing recurring request exceptions. (bad_deploy, 0.96)
- Host CPU contention contributed to endpoint problems; no sharp resource change immediately before onset is established. (resource_contention, 0.12)

## Proposed action (shadow mode: recorded, not executed)

`escalate` target `shop-api` params `{}` tier `read_only`
