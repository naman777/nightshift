# EndpointDown on `nginx`

- alert condition first true: 2026-09-27 05:50:18 UTC
- watcher detected: 2026-09-27 05:51:15 UTC (+57s)
- diagnosis finished: 2026-09-27 05:51:53 UTC (investigation took 37.7s)
- model: gpt-6-luna / prompt v4 · llm calls 31 · tool calls 42 · cost $0.0138

## Root cause (service_down, confidence 0.38, service `nginx`)

Nginx's separate listener at http://127.0.0.1:8200/ stopped answering at Unix 1790487964 while port 80 remained healthy; the evidence does not establish whether the listener or its PHP-FPM backend failed, and no triggering change is confirmed.

## Evidence

- ev_1950
- ev_1953
- ev_1954
- ev_1944
- ev_1955
- ev_1957

## Ruled out

- A demonstrated nginx configuration/deploy change caused the outage.
- Host CPU contention is established as the cause.
- A full nginx service-unit shutdown caused the port 8200 failure.
- shop-api errors caused the nginx port 8200 outage.

## Alternatives

- Nginx's separate :8200 endpoint/listener or its PHP-FPM backend became unavailable; exact failing component and trigger are unconfirmed. (service_down, 0.38)
- Host CPU contention may have contributed to intermittent :8200 latency, but available evidence does not establish it as the cause of the endpoint-down state. (resource_contention, 0.20)

## Proposed action (shadow mode: recorded, not executed)

`escalate` target `nginx/on-call operations team` params `{}` tier `read_only`
