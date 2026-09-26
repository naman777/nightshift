# LBDataPathErrors on `lb-sandbox`

- alert condition first true: 2026-09-26 21:51:20 UTC
- watcher detected: 2026-09-26 21:52:02 UTC (+42s)
- diagnosis finished: 2026-09-26 21:52:23 UTC (investigation took 20.9s)
- model: gpt-6-luna / prompt v3 · llm calls 18 · tool calls 27 · cost $0.0082

## Root cause (config_change, confidence 0.66, service `lb`)

lb-sandbox data-path probe failures began after sandbox.conf moved the backend pool to ports 9991–9993, consistent with a bad upstream-pool config change; the evidence does not confirm backend availability or the exact failure mechanism.

## Evidence

- ev_139
- ev_141
- ev_140

## Ruled out

- H1: balancer deployment or code regression caused the onset
- H4: host resource contention or insufficient capacity caused the onset

## Alternatives

- Temporary backend-pool configuration change to ports 9991–9993 directly preceded data-path probe failures; backend status is not confirmed. (config_change, 0.66)
- Probe classification/blocking behavior may misclassify or stall health checks, but incident-specific timing or triggering backend evidence is absent. (bad_deploy, 0.28)

## Proposed action (shadow mode: recorded, not executed)

`set_config` target `lb` params `{"key": "sandbox.conf.backends", "value": "8093,8094,8095"}` tier `reversible`
