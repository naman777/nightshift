# LBAdminPortUnresponsive on `lb-sandbox`

- alert condition first true: 2026-09-26 22:26:00 UTC
- watcher detected: 2026-09-26 22:27:28 UTC (+89s)
- diagnosis finished: 2026-09-26 22:27:51 UTC (investigation took 22.4s)
- model: gpt-6-luna / prompt v3 · llm calls 22 · tool calls 28 · cost $0.0107

## Root cause (bad_deploy, confidence 0.78, service `lb`)

The lb-sandbox admin/stats listener is vulnerable to a blocking-read handler defect: a silent or incomplete client can monopolize its single stats thread and leave later probes unserved; no deployment/build change was observed in the queried window.

## Evidence

- ev_462
- ev_457
- ev_456
- ev_465
- ev_459
- ev_467

## Ruled out

- H2: sandbox backend-pool config change caused the admin endpoint failure
- H3: host resource contention prevented admin responses
- H4: process/listener outage caused the endpoint failure

## Alternatives

- The lb-sandbox stats handler can block indefinitely reading one client on its sole listener thread, starving subsequent admin requests; code defect, with no corresponding deploy observed. (bad_deploy, 0.78)
- The stats handler can wait for the shared connection mutex while backend connection paths hold it, delaying admin responses. (resource_contention, 0.48)
- Temporary backend-pool configuration change may have affected balancer behavior, but evidence does not link it to the admin listener and it was reverted before alert start. (config_change, 0.20)

## Proposed action (shadow mode: recorded, not executed)

`none` target `` params `{}` tier `read_only`
