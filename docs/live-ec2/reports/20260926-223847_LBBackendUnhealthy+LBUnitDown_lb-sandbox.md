# LBBackendUnhealthy+LBUnitDown on `lb-sandbox`

- alert condition first true: 2026-09-26 22:37:30 UTC
- watcher detected: 2026-09-26 22:38:05 UTC (+35s)
- diagnosis finished: 2026-09-26 22:38:47 UTC (investigation took 41.6s)
- model: gpt-6-luna / prompt v3 · llm calls 37 · tool calls 54 · cost $0.0182

## Root cause (dependency_outage, confidence 0.43, service `lb`)

The lb-sandbox backend pool became unavailable, causing the LB to report all backends unreachable; the backend-side failure mechanism and cause of the later graceful unit stop are unconfirmed.

## Evidence

- ev_559
- ev_560
- ev_555
- ev_556
- ev_561
- ev_567

## Ruled out

- Host resource contention or exhaustion caused the backend/LB failures.
- A recent deployment caused the LB failure.
- The recorded sandbox config switch is established as causal.

## Alternatives

- Independent unavailability of the lb-sandbox backend pool led to LB connection failures; mechanism is not established. (dependency_outage, 0.43)
- The lb-sandbox unit received a graceful shutdown signal, but the initiator is unknown and timing places it after backend errors began. (dependency_outage, 0.22)

## Proposed action (shadow mode: recorded, not executed)

`escalate` target `sandbox backend / LB owning team` params `{}` tier `read_only`
