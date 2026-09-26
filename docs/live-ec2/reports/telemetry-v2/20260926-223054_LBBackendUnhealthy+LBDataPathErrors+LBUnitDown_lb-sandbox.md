# LBBackendUnhealthy+LBDataPathErrors+LBUnitDown on `lb-sandbox`

- alert condition first true: 2026-09-26 22:29:10 UTC
- watcher detected: 2026-09-26 22:30:06 UTC (+56s)
- diagnosis finished: 2026-09-26 22:30:54 UTC (investigation took 47.5s)
- model: gpt-6-luna / prompt v3 · llm calls 46 · tool calls 73 · cost $0.0270

## Root cause (bad_deploy, confidence 0.72, service `lb`)

The lb-sandbox blocking socket I/O in its stats/admin and backend health-probe paths can serialize or indefinitely stall probes, causing admin-port failures followed by backend/data-path failures; the available evidence does not identify a deployed commit sha for this defect.

## Evidence

- ev_489
- ev_490
- ev_503
- ev_504
- ev_496

## Ruled out

- H2: sandbox backend configuration mapping directly caused the incident
- H3: host resource contention caused the initial failures

## Alternatives

- LB code-level blocking socket I/O stalls serialized admin/stats handling and can hang backend health probes, preceding backend/data-path errors. (bad_deploy, 0.72)
- A sandbox backend mapping change made the configured backends unavailable; runtime application and causal timing are unverified. (config_change, 0.22)
- Host resource contention caused LB probe failures. (resource_contention, 0.06)

## Proposed action (shadow mode: recorded, not executed)

`none` target `` params `{}` tier `read_only`
