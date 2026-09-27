# LBAdminPortUnresponsive on `lb`

- alert condition first true: 2026-09-26 22:36:40 UTC
- watcher detected: 2026-09-27 03:27:19 UTC (+17439s)
- diagnosis finished: 2026-09-27 03:27:19 UTC (investigation took 0.0s)
- model: gpt-6-luna / prompt v4 · llm calls 17 · tool calls 27 · cost $0.0076

## Root cause (bad_deploy, confidence 0.68, service `lb`)

The lb stats listener’s single synchronous handler can block indefinitely on a client read without a timeout, stalling :8081 while the separate :8080 accept loop remains available; no triggering deploy or config change was found in the queried window.

## Evidence

- ev_580
- ev_582
- ev_585
- ev_586
- ev_578
- ev_579

## Ruled out

- LB host resource saturation prevented admin responses
- A known recent LB deploy or lb.conf change directly caused the listener failure
- Backend reachability errors explain the admin endpoint failure

## Alternatives

- LB stats listener blocks its sole handler indefinitely on a client that connects without sending a request, leaving admin :8081 unresponsive while frontend :8080 has a separate accept loop. (bad_deploy, 0.68)
- LB resource contention or host saturation stalls the admin listener. (resource_contention, 0.16)
- LB admin listener or health-check configuration is incorrect. (healthcheck_misconfig, 0.10)

## Proposed action (shadow mode: recorded, not executed)

`none` target `` params `{}` tier `read_only`
