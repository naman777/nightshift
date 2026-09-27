# LBBackendUnhealthy on `lb-sandbox`

- alert condition first true: 2026-09-26 22:18:30 UTC
- watcher detected: 2026-09-26 22:19:25 UTC (+55s)
- diagnosis finished: 2026-09-26 22:20:19 UTC (investigation took 53.6s)
- model: gpt-6-luna / prompt v3 · llm calls 49 · tool calls 57 · cost $0.0239

## Root cause (dependency_outage, confidence 0.55, service `lb`)

The lb-sandbox backend pool on ports 8093–8095 stopped accepting connections before the alert, causing the backend-count alarm; evidence does not identify why those backends became unavailable.

## Evidence

- ev_387
- ev_388
- ev_389
- ev_421
- ev_422

## Ruled out

- A recent LB deploy introduced a connectivity or health-reporting defect.
- The backend config rollout to ports 9991–9993 directly caused this outage.

## Alternatives

- The lb-sandbox backend pool on ports 8093–8095 stopped accepting connections before the alert; the reason for the backend outage is undetermined. (dependency_outage, 0.55)
- An HTTP health-probe classification defect may have marked reachable backends unhealthy when they returned a non-2xx response, but no observed response confirms this mechanism in this incident. (healthcheck_misconfig, 0.25)

## Proposed action (shadow mode: recorded, not executed)

`escalate` target `lb-sandbox backend pool ports 8093–8095` params `{}` tier `read_only`
