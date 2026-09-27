# EndpointSlow on `nginx`

- alert condition first true: 2026-09-27 04:47:58 UTC
- watcher detected: 2026-09-27 04:49:25 UTC (+87s)
- diagnosis finished: 2026-09-27 04:49:55 UTC (investigation took 30.2s)
- model: gpt-6-luna / prompt v4 · llm calls 26 · tool calls 45 · cost $0.0130

## Root cause (config_change, confidence 0.78, service `shop-api`)

shop-api's slow_ms setting was changed from 0 to 1500 by commit 8da102af shortly before shop-api and nginx both began exhibiting matching ~1.502s probe latency; this is consistent with a deliberate 1.5-second delay, although runtime loading is unverified.

## Evidence

- ev_1334
- ev_1335
- ev_1336
- ev_1339
- ev_1340
- ev_1341

## Ruled out

- lb latency caused the nginx/shop-api latency jump
- shared-host CPU, memory, or disk contention caused the jump
- a new nginx deployment caused the latency

## Alternatives

- shop-api slow_ms=1500 config change (commit 8da102af) introduced a 1.5s request delay, observed as matching shop-api and nginx probe latency; loaded state unconfirmed. (config_change, 0.78)
- Unobserved shop-api-side delay or mechanism caused both its endpoint and nginx's upstream probe to take ~1.502s; no separate trigger established. (unknown, 0.15)
- Unobserved shared-host contention slowed both services; available CPU/memory/disk signals do not coincide with the onset. (resource_contention, 0.07)

## Proposed action (shadow mode: recorded, not executed)

`set_config` target `shop-api` params `{"key": "slow_ms", "value": 0}` tier `reversible`
