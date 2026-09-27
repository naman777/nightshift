# EndpointDown on `nginx`

- alert condition first true: 2026-09-27 05:13:08 UTC
- watcher detected: 2026-09-27 05:13:53 UTC (+45s)
- diagnosis finished: 2026-09-27 05:14:50 UTC (investigation took 56.6s)
- model: gpt-6-luna / prompt v4 · llm calls 43 · tool calls 65 · cost $0.0194

## Root cause (config_change, confidence 0.57, service `nginx`)

nginx :80 endpoint failures were intermittent while nginx.service remained active; proxy_pass changes to shop-api port 5001 (68a8e1b8 and fa5312b9) overlap two failure windows and are the leading trigger, but runtime application is unverified.

## Evidence

- ev_1657
- ev_1662
- ev_1663
- ev_1664
- ev_1669
- ev_1670
- ev_1682
- ev_1683
- ev_1684
- ev_1687

## Ruled out

- Host resource contention or exhaustion caused the nginx failures.
- A sustained nginx process/unit outage explains the endpoint failures.
- The lb :8081 TCP probe failure is the cause of the nginx endpoint failures.
- The proxy_read_timeout change is established as the failure mechanism.

## Alternatives

- nginx proxy_pass was changed to port 5001 immediately before two nginx endpoint-down samples; whether nginx loaded this value and whether port 5001 was unavailable are unverified. (config_change, 0.57)
- Intermittent shop-api endpoint/unit degradation coincided with the latter nginx failure interval, but does not account for the earlier or second intervals. (service_down, 0.22)

## Proposed action (shadow mode: recorded, not executed)

`none` target `nginx` params `{}` tier `read_only`
