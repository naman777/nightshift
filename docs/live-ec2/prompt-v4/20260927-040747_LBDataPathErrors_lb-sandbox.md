# LBDataPathErrors on `lb-sandbox`

- alert condition first true: 2026-09-27 04:06:10 UTC
- watcher detected: 2026-09-27 04:07:09 UTC (+59s)
- diagnosis finished: 2026-09-27 04:07:47 UTC (investigation took 38.5s)
- model: gpt-6-luna / prompt v4 · llm calls 31 · tool calls 52 · cost $0.0188

## Root cause (dependency_outage, confidence 0.72, service `lb-sandbox`)

lb-sandbox data-path errors were most likely caused by sha 44a42662 changing sandbox.conf backends to 9991–9993, all of which were logged DOWN shortly before the error-rate rise; runtime config loading is not proven.

## Evidence

- ev_1048
- ev_1058
- ev_1059
- ev_1061
- ev_1064
- ev_1066

## Ruled out

- Earlier sandbox backend-pool config rollouts caused the onset.
- A newly deployed application build caused the failure.
- The intermittent 8094 backend failure itself explains the later error-rate rise.
- The lb-sandbox unit being down caused the data-path failures.
- Host resource contention is the leading explanation.

## Alternatives

- sha 44a42662 changed lb-sandbox's configured backend pool to ports 9991–9993; all three were logged DOWN and the data-path error rate then rose. The exact runtime load event remains unverified. (dependency_outage, 0.72)
- A sandbox balancer code path may have marked all candidates unhealthy after connect failures, but no runtime trigger evidence establishes this mechanism independently of the missing configured backends. (code_defect, 0.18)

## Proposed action (shadow mode: recorded, not executed)

`escalate` target `lb-sandbox` params `{}` tier `read_only`
