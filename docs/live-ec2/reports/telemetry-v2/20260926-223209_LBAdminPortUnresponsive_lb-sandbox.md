# LBAdminPortUnresponsive on `lb-sandbox`

- alert condition first true: 2026-09-26 22:29:10 UTC
- watcher detected: 2026-09-26 22:31:24 UTC (+134s)
- diagnosis finished: 2026-09-26 22:32:09 UTC (investigation took 45.6s)
- model: gpt-6-luna / prompt v3 · llm calls 41 · tool calls 64 · cost $0.0205

## Root cause (healthcheck_misconfig, confidence 0.18, service `lb`)

The lb-sandbox stats listener may be blocked by its serial blocking read path (a client that connects without sending data can stall subsequent probes), but no evidence establishes that this occurred at the incident onset.

## Evidence

- ev_525
- ev_542
- ev_544

## Ruled out

- H1: lb-sandbox process resource-starved or crashed
- H3: recent sandbox configuration change directly broke admin listener
- H4: newly deployed balancer build regressed admin/stats handling

## Alternatives

- Possible stats request-path stall in the single-threaded listener; incident-specific causal link is unproven. (healthcheck_misconfig, 0.18)
- Sandbox backends became unreachable, a signal that precedes the admin-port failure but is not shown to cause it. (dependency_outage, 0.08)

## Proposed action (shadow mode: recorded, not executed)

`none` target `` params `{}` tier `read_only`
