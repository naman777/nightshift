# EndpointSlow on `shop-api`

- alert condition first true: 2026-09-27 05:16:08 UTC
- watcher detected: 2026-09-27 05:18:11 UTC (+123s)
- diagnosis finished: 2026-09-27 05:18:48 UTC (investigation took 37.4s)
- model: gpt-6-luna / prompt v4 · llm calls 33 · tool calls 49 · cost $0.0163

## Root cause (config_change, confidence 0.62, service `shop-api`)

shop-api's slow_ms=1500 config change (sha 400dd9b2), made 12 seconds before alert onset, likely introduced intermittent 1.5-second request delays; runtime loading of this value is unverified.

## Evidence

- ev_1724
- ev_1729
- ev_1730

## Ruled out

- The 127.0.0.1:8081 lb endpoint became newly unhealthy and caused the delay.
- Host CPU contention caused the probe latency.
- The earlier slow_ms=1500 change, sha 648593a8, caused the onset.
- A downstream dependency became slow and caused the API latency.

## Alternatives

- shop-api config sha 400dd9b2 set slow_ms=1500 just before onset; it plausibly explains the matching intermittent 1.5s shop-api/nginx probe latencies, but runtime effectiveness is unverified. (config_change, 0.62)
- A shop-api application defect involving missing discount_factor caused request errors; available evidence does not establish it caused the 1.5s latency pattern. (code_defect, 0.22)

## Proposed action (shadow mode: recorded, not executed)

`set_config` target `shop-api` params `{"key": "slow_ms", "value": 0}` tier `reversible`
