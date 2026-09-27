# EndpointSlow on `nginx`

- alert condition first true: 2026-09-27 06:53:18 UTC
- watcher detected: 2026-09-27 06:54:43 UTC (+85s)
- diagnosis finished: 2026-09-27 06:55:47 UTC (investigation took 64.3s)
- model: gpt-6-luna / prompt v4 · llm calls 47 · tool calls 51 · cost $0.0180

## Root cause (unknown, confidence 0.15, service `nginx`)

Unresolved; nginx endpoint http://127.0.0.1:8200/ became slow while remaining up, but the available evidence cannot attribute the slowdown to a mechanism or active change.

## Evidence

- ev_2375
- ev_2367
- ev_2368
- ev_2378
- ev_2383

## Ruled out

- Host resource contention as the established cause: host CPU increase did not demonstrably precede the latency onset, and no per-process attribution is available.
- Nginx bad deploy/config regression: no relevant active-at-onset change was verified.
- lb:8081 outage as the cause: although :8081 was down, the available nginx config search found no reference to lb or 8081, and no request-level dependency evidence links it to :8200.
- MariaDB lifecycle events as the cause, and the unrelated shop-api deploys: no evidence connects either to the nginx latency interval.

## Alternatives

- Unattributed transient slowdown on nginx :8200; available data confirms latency rose but does not distinguish a service-local mechanism from an unobserved dependency or load issue. (unknown, 0.15)

## Proposed action (shadow mode: recorded, not executed)

`none` target `` params `{}` tier `read_only`
