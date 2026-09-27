# EndpointDown on `nginx`

- alert condition first true: 2026-09-27 07:48:18 UTC
- watcher detected: 2026-09-27 07:49:18 UTC (+60s)
- diagnosis finished: 2026-09-27 07:49:42 UTC (investigation took 24.6s)
- model: gpt-6-luna / prompt v4 · llm calls 18 · tool calls 28 · cost $0.0107

## Root cause (unknown, confidence 0.18, service `php8.5-fpm`)

Inconclusive: the nginx :8200 WordPress endpoint intermittently returned 500 after FastCGI resets from PHP-FPM, but available evidence cannot determine whether PHP-FPM or nginx initiated the failure or why (ev_2537, ev_2538, ev_2539).

## Evidence

- ev_2537
- ev_2538
- ev_2539
- ev_2541
- ev_2543

## Ruled out

- A recent nginx deploy or port-8200 configuration change caused this incident
- A broad nginx outage affected both listeners
- Host CPU increase is established as the direct cause

## Alternatives

- PHP-FPM may have intermittently reset the FastCGI connection used by nginx :8200, but the mechanism and trigger are not established. (unknown, 0.18)
- An endpoint-specific nginx :8200 failure remains possible; no evidence establishes its listener state or a lifecycle event at onset. (unknown, 0.12)

## Proposed action (shadow mode: recorded, not executed)

`escalate` target `php8.5-fpm` params `{}` tier `read_only`
