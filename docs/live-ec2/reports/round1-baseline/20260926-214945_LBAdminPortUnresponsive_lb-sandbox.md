# LBAdminPortUnresponsive on `lb-sandbox`

- alert condition first true: 2026-09-26 21:48:10 UTC
- watcher detected: 2026-09-26 21:49:10 UTC (+60s)
- diagnosis finished: 2026-09-26 21:49:45 UTC (investigation took 34.5s)
- model: gpt-6-luna / prompt v3 · llm calls 31 · tool calls 44 · cost $0.0125

## Root cause (healthcheck_misconfig, confidence 0.34, service `lb`)

lb-sandbox's stats/admin listener can become unresponsive when its single stats thread blocks indefinitely reading an idle or incomplete client; the code defect is established, but the evidence does not establish when or how it was triggered.

## Evidence

- ev_101
- ev_102
- ev_111
- ev_112
- ev_118

## Ruled out

- Host/sandbox resource contention prevented the admin probe from being served.
- A code deploy introduced the failure immediately before the alert.
- The backend pool config changes directly caused the stats-thread blocking-read defect.

## Alternatives

- Single-threaded LB stats/admin request handling can hang indefinitely on an idle/incomplete client read; no incident-specific trigger is confirmed. (healthcheck_misconfig, 0.34)
- Sandbox backend pool configuration change may have contributed to service errors, but there is no demonstrated link to the admin listener failure. (config_change, 0.12)

## Proposed action (shadow mode: recorded, not executed)

`none` target `` params `{}` tier `read_only`
