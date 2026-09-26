# LBBackendUnhealthy on `lb-sandbox`

- alert condition first true: 2026-09-26 22:04:10 UTC
- watcher detected: 2026-09-26 22:05:05 UTC (+55s)
- diagnosis finished: 2026-09-26 22:05:48 UTC (investigation took 43.2s)
- model: gpt-6-luna / prompt v3 · llm calls 38 · tool calls 41 · cost $0.0131

## Root cause (healthcheck_misconfig, confidence 0.18, service `lb`)

The lb backend-selection/health-check path is the leading candidate: a transient connect failure or false-unhealthy probe can exclude a backend, but the evidence does not establish which mechanism occurred or whether this code was deployed.

## Evidence

- ev_241
- ev_245
- ev_248
- ev_249
- ev_250
- ev_231
- ev_232
- ev_238
- ev_239
- ev_233
- ev_237
- ev_243

## Ruled out

- Recent LB bad deploy caused the alert.
- The temporary backend pool change to ports 9991–9993 was active at alert onset.
- A health-check-related config change was active at onset.

## Alternatives

- LB health-check/selection behavior may have falsely excluded a backend; deployment and actual probe result are unverified. (healthcheck_misconfig, 0.18)
- A downstream backend outage or transient connection failure may have made port 8094 unavailable. (dependency_outage, 0.15)
- A newly deployed LB code defect may have caused false backend health state; no matching deployment is evidenced. (bad_deploy, 0.08)

## Proposed action (shadow mode: recorded, not executed)

`none` target `` params `{}` tier `read_only`
