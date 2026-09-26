# LBBackendUnhealthy+LBUnitDown+LBDataPathErrors on `lb-sandbox`

- alert condition first true: 2026-09-26 22:14:50 UTC
- watcher detected: 2026-09-26 22:15:40 UTC (+50s)
- diagnosis finished: 2026-09-26 22:16:27 UTC (investigation took 47.1s)
- model: gpt-6-luna / prompt v3 · llm calls 42 · tool calls 70 · cost $0.0188

## Root cause (dependency_latency, confidence 0.36, service `lb`)

lb-sandbox's sequential health-check loop can stall on a blocking backend recv without a read timeout, plausibly causing the observed admin-probe degradation before the unit/backend outage; the available evidence does not prove this mechanism directly caused unit deactivation.

## Evidence

- ev_339
- ev_353
- ev_321
- ev_322
- ev_342
- ev_358

## Ruled out

- The sandbox backend-pool config change caused the alert-time outage.
- Host resource contention caused the LB unit/backend outage.
- A newly deployed build caused the incident.

## Alternatives

- Sequential LB health probes block indefinitely on recv without a read timeout, potentially delaying probe/admin responsiveness; direct linkage to the unit deactivation is unproven. (dependency_latency, 0.36)
- An unobserved LB process/unit failure caused simultaneous LB and backend probe loss; logs do not identify its trigger. (unknown, 0.18)

## Proposed action (shadow mode: recorded, not executed)

`none` target `` params `{}` tier `read_only`
