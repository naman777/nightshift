# LBBackendUnhealthy on `lb-sandbox`

- alert condition first true: 2026-09-27 04:03:00 UTC
- watcher detected: 2026-09-27 04:03:59 UTC (+59s)
- diagnosis finished: 2026-09-27 04:04:38 UTC (investigation took 39.8s)
- model: gpt-6-luna / prompt v4 · llm calls 30 · tool calls 55 · cost $0.0174

## Root cause (service_down, confidence 0.74, service `lb-sandbox`)

The exact lb-sandbox backend 127.0.0.1:8094 became unavailable at alert onset while 8093 and 8095 remained available; this is an isolated backend service-down failure, with no evidence identifying its stop/crash trigger.

## Evidence

- ev_1017
- ev_1018
- ev_1022
- ev_1037
- ev_1038
- ev_1033

## Ruled out

- The sandbox backend-pool config change caused the onset; the last move removing 8094 (081d479f) was reverted by 81473653 before onset, and the observed config was restored. Runtime reload status is unconfirmed, so this is not entirely excluded.
- Host resource contention or exhaustion made the backend unavailable; CPU and disk remained low and memory rose only moderately, not to exhaustion.
- The LB service process itself was inactive at the exact backend failure; it was active at the neighboring samples. A separate earlier stop/restart interval was before alert onset.

## Alternatives

- Isolated service-down failure of lb-sandbox backend 127.0.0.1:8094; precise process-level trigger and actor are not established. (service_down, 0.74)
- Runtime configuration application/reload issue involving restoration of the backend pool; repository config was restored before onset, but runtime state is unverified. (config_change, 0.18)
- Host resource contention or exhaustion affecting backend 8094; observed resource levels argue against this. (resource_contention, 0.08)

## Proposed action (shadow mode: recorded, not executed)

`escalate` target `lb-sandbox owning team` params `{}` tier `read_only`
