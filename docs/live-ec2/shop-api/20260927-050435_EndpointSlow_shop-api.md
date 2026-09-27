# EndpointSlow on `shop-api`

- alert condition first true: 2026-09-27 05:02:08 UTC
- watcher detected: 2026-09-27 05:03:58 UTC (+110s)
- diagnosis finished: 2026-09-27 05:04:35 UTC (investigation took 36.8s)
- model: gpt-6-luna / prompt v4 · llm calls 27 · tool calls 40 · cost $0.0128

## Root cause (config_change, confidence 0.76, service `shop-api`)

shop-api GET / is deliberately delayed by the configured slow_ms=1500 setting from commit 648593a8, matching the persistent ~1.502s shop-api and nginx probe latencies; exact runtime activation relative to the onset is not confirmed.

## Evidence

- ev_1500
- ev_1503
- ev_1524
- ev_1526

## Ruled out

- shop-api bad deploy 8cba97a6 caused the latency
- Host resource contention caused the latency
- nginx proxy port change caused the symptoms
- lb listener 127.0.0.1:8081 failure explains shop-api/nginx latency

## Alternatives

- shop-api GET / incurs the configured 1500ms delay from config commit 648593a8, producing the persistent probe timeout-like latency through nginx. (config_change, 0.76)
- An earlier transient shop-api/nginx latency and availability incident preceded the 648593a8 config change; its cause remains undetermined by available evidence. (unknown, 0.15)

## Proposed action (shadow mode: recorded, not executed)

`set_config` target `shop-api` params `{"key": "config/app.json:slow_ms", "value": 0}` tier `reversible`
