# EndpointSlow on `nginx`

- alert condition first true: 2026-09-27 05:16:18 UTC
- watcher detected: 2026-09-27 05:17:35 UTC (+77s)
- diagnosis finished: 2026-09-27 05:18:11 UTC (investigation took 35.5s)
- model: gpt-6-luna / prompt v4 · llm calls 32 · tool calls 49 · cost $0.0166

## Root cause (config_change, confidence 0.78, service `shop-api`)

shop-api’s slow_ms=1500 configuration (SHA 648593a8) imposed a 1.5-second response delay, matching the elevated nginx and shop-api probe latencies; an earlier activation of the same setting was also active at the first measured latency rise.

## Evidence

- ev_1704
- ev_1706
- ev_1692

## Ruled out

- lb 127.0.0.1:8081 outage caused the nginx/shop-api latency
- nginx proxy_pass change to port 5001 caused continuing latency
- shop-api deploy at 1790484899 caused the initial latency rise

## Alternatives

- shop-api slow_ms=1500 configuration (SHA 648593a8) deliberately adds latency; same setting was active during the first measured rise. (config_change, 0.78)
- shop-api service lifecycle stop/start at 1790484899 contributed to later request errors, although it does not explain the earlier 1.5-second latency onset. (service_down, 0.35)
- lb TCP endpoint 127.0.0.1:8081 was persistently unavailable in the sample window, but its onset is unknown and no dependency path to nginx was observed. (dependency_outage, 0.20)

## Proposed action (shadow mode: recorded, not executed)

`set_config` target `shop-api` params `{"key": "slow_ms", "value": 0}` tier `reversible`
