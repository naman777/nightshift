# EndpointDown on `nginx`

- alert condition first true: 2026-09-27 05:53:18 UTC
- watcher detected: 2026-09-27 05:54:13 UTC (+55s)
- diagnosis finished: 2026-09-27 05:55:10 UTC (investigation took 56.6s)
- model: gpt-6-luna / prompt v4 · llm calls 37 · tool calls 51 · cost $0.0159

## Root cause (service_down, confidence 0.36, service `nginx`)

The nginx :8200 endpoint/listener stopped answering while nginx.service and the separate :80 endpoint remained up; available evidence does not establish whether the specific failure was in the listener, WordPress/PHP-FPM path, or another backend.

## Evidence

- ev_1995
- ev_1996
- ev_1997
- ev_1999
- ev_2001

## Ruled out

- H2: a nginx config or healthcheck/routing change directly caused :8200 failure
- H3: a newly deployed nginx build caused the failure
- H4: a downstream dependency outage caused the :8200 probe failure
- A whole nginx process/unit outage

## Alternatives

- nginx :8200 endpoint/listener-specific service failure; exact backend/trigger is not established. (service_down, 0.36)
- Unverified nginx/wordpress.conf or healthcheck/routing configuration issue affecting only :8200. (healthcheck_misconfig, 0.20)
- Failure in the PHP-FPM/WordPress backend path serving :8200; no direct state evidence identifies it. (dependency_outage, 0.12)

## Proposed action (shadow mode: recorded, not executed)

`escalate` target `nginx/WordPress on-call` params `{}` tier `read_only`
