# EndpointDown on `nginx`

- alert condition first true: 2026-09-27 04:52:18 UTC
- watcher detected: 2026-09-27 04:53:16 UTC (+58s)
- diagnosis finished: 2026-09-27 04:53:49 UTC (investigation took 32.6s)
- model: gpt-6-luna / prompt v4 · llm calls 29 · tool calls 39 · cost $0.0110

## Root cause (config_change, confidence 0.67, service `nginx`)

nginx endpoint 127.0.0.1:80 stopped answering its probe shortly after config commit 68a8e1b8 changed proxy_pass from port 5000 to 5001; this is most consistent with a faulty upstream configuration, although the live port-5001 state is unconfirmed.

## Evidence

- ev_1368
- ev_1386
- ev_1384
- ev_1389

## Ruled out

- nginx process crashed or was stopped at the onset
- The earlier shop slow_ms delay caused the current failure
- The latency spike immediately caused the endpoint-down transition
- A recent nginx deploy caused the failure

## Alternatives

- nginx proxy_pass config commit 68a8e1b8 changed upstream to 127.0.0.1:5001, plausibly leaving the endpoint unable to serve probes if that listener was unavailable. (config_change, 0.67)
- Unidentified nginx listener/probe-path fault; metrics show the process active but endpoint down, with no detailed probe response or onset logs available. (service_down, 0.20)

## Proposed action (shadow mode: recorded, not executed)

`revert_commit` target `68a8e1b8` params `{}` tier `reversible`
