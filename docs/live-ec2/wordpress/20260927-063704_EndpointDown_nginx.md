# EndpointDown on `nginx`

- alert condition first true: 2026-09-27 06:35:28 UTC
- watcher detected: 2026-09-27 06:36:14 UTC (+46s)
- diagnosis finished: 2026-09-27 06:37:04 UTC (investigation took 50.0s)
- model: gpt-6-luna / prompt v4 · llm calls 31 · tool calls 42 · cost $0.0142

## Root cause (service_down, confidence 0.34, service `nginx`)

The nginx :8200 endpoint experienced intermittent service-down failures (first sampled down at 1790490052, recovering and failing again) while nginx :80 remained healthy; the specific listener/upstream fault and trigger are unverified.

## Evidence

- ev_2254
- ev_2267
- ev_2268
- ev_2258
- ev_2264

## Ruled out

- H2: a recent nginx configuration or deployment change caused the :8200 failure
- H3: MariaDB stopping caused the nginx :8200 failure
- nginx-wide service outage

## Alternatives

- Intermittent service-down failure localized to nginx :8200; runtime cause is not identified. (service_down, 0.34)
- A MariaDB outage coincided with the first sampled nginx :8200 failure, but causality is not established. (service_down, 0.25)
- An nginx/wordpress.conf configuration change may have affected :8200, but its timing, diff, and active status are unavailable. (config_change, 0.14)

## Proposed action (shadow mode: recorded, not executed)

`escalate` target `nginx on-call team` params `{}` tier `read_only`
