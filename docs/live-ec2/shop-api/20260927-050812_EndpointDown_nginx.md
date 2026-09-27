# EndpointDown on `nginx`

- alert condition first true: 2026-09-27 05:06:28 UTC
- watcher detected: 2026-09-27 05:07:25 UTC (+57s)
- diagnosis finished: 2026-09-27 05:08:12 UTC (investigation took 46.8s)
- model: gpt-6-luna / prompt v4 · llm calls 38 · tool calls 53 · cost $0.0167

## Root cause (unknown, confidence 0.18, service `nginx`)

The nginx port-80 endpoint became unavailable while nginx.service remained active; the strongest lead is config commit 68a8e1b8 changing proxy_pass from shop-api:5000 to :5001 before onset, but evidence does not establish that this config was loaded or caused the failure.

## Evidence

- ev_1527
- ev_1528
- ev_1530
- ev_1532
- ev_1537
- ev_1540
- ev_1542
- ev_1543
- ev_1547
- ev_1555

## Ruled out

- Host resource contention caused nginx probe failure
- nginx.service stopped or crashed
- The proxy_read_timeout 10s-to-15s edit directly caused listener failure
- shop-api unavailability caused the initial nginx endpoint failure
- The upstream-port edit is proven as the runtime cause

## Alternatives

- Nginx proxy_pass config edit 68a8e1b8 switched upstream from port 5000 to 5001 before endpoint-down; loaded runtime state and causal link are unverified. (config_change, 0.35)
- An unidentified nginx listener/process-level failure caused the :80 probe to fail while nginx.service remained active. (service_down, 0.25)
- Unknown mechanism; telemetry confirms endpoint down but available logs and state do not isolate why. (unknown, 0.18)

## Proposed action (shadow mode: recorded, not executed)

`escalate` target `nginx` params `{}` tier `read_only`
