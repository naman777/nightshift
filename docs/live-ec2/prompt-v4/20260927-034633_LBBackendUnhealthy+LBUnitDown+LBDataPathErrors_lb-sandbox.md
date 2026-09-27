# LBBackendUnhealthy+LBUnitDown+LBDataPathErrors on `lb-sandbox`

- alert condition first true: 2026-09-27 03:44:50 UTC
- watcher detected: 2026-09-27 03:45:47 UTC (+58s)
- diagnosis finished: 2026-09-27 03:46:33 UTC (investigation took 45.5s)
- model: gpt-6-luna / prompt v4 · llm calls 39 · tool calls 50 · cost $0.0165

## Root cause (service_down, confidence 0.34, service `lb-sandbox`)

lb-sandbox experienced backend availability loss on 127.0.0.1:8093–8095 before data-path errors, followed by admin-port loss and nsbox-lb.service becoming inactive; the initiating failure and whether the unit was stopped deliberately or crashed are undetermined.

## Evidence

- ev_795
- ev_796
- ev_797
- ev_798
- ev_793
- ev_794
- ev_813
- ev_815

## Ruled out

- Recent sandbox.conf backend-pool edits caused the onset; both edits changing 8093–8095 to 9991–9993 were reverted before the incident transitions.
- A deploy caused the incident; no lb-sandbox deploys were found in the 240-minute lookback, though this does not rule out operator/system actions.
- The documented failed-connect counter leak explains the incident; no evidence establishes its trigger, and it does not account for admin/stats unavailability at these timestamps.
- The unit stopping first caused all symptoms; backend availability and error-rate transitions precede the unit inactive transition.

## Alternatives

- lb-sandbox backend availability loss on 127.0.0.1:8093–8095 was the earliest observed failure, followed by data-path errors and later LB/admin/unit failure; mechanism and initiator unknown. (dependency_outage, 0.34)
- lb-sandbox process/unit failure contributed to final loss of admin and data-path availability; whether deliberate stop or crash is not established. (service_down, 0.29)

## Proposed action (shadow mode: recorded, not executed)

`escalate` target `lb-sandbox on-call / host operations` params `{}` tier `read_only`
