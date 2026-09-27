# EndpointSlow on `nginx`

- alert condition first true: 2026-09-27 05:02:18 UTC
- watcher detected: 2026-09-27 05:03:34 UTC (+77s)
- diagnosis finished: 2026-09-27 05:03:58 UTC (investigation took 23.4s)
- model: gpt-6-luna / prompt v4 · llm calls 16 · tool calls 30 · cost $0.0087

## Root cause (config_change, confidence 0.78, service `shop-api`)

shop-api became slow after config change SHA 648593a8 set `slow_ms=1500`; the synchronous GET / path sleeps for 1.5 seconds, matching the observed shop-api and nginx latency increase.

## Evidence

- ev_1492
- ev_1483
- ev_1486
- ev_1488

## Ruled out

- nginx request-path regression or upstream port misconfiguration caused the incident
- LB 127.0.0.1:8081 failure caused the observed HTTP endpoint latency

## Alternatives

- shop-api slow_ms=1500 config change SHA 648593a8 triggers 1.5-second synchronous delay in GET / and accounts for the shared shop-api/nginx latency rise. (config_change, 0.78)
- An unobserved nginx-side issue independently caused latency; no matching nginx errors or request logs were retrieved and no recent nginx deploy is shown. (unknown, 0.12)
- Pre-existing LB TCP backend 127.0.0.1:8081 is down, but HTTP LB endpoints remain healthy and it does not correlate with onset. (service_down, 0.10)

## Proposed action (shadow mode: recorded, not executed)

`set_config` target `shop-api` params `{"key": "slow_ms", "value": 0}` tier `reversible`
