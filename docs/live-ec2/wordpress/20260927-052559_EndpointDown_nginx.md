# EndpointDown on `nginx`

- alert condition first true: 2026-09-27 05:23:38 UTC
- watcher detected: 2026-09-27 05:25:09 UTC (+91s)
- diagnosis finished: 2026-09-27 05:25:59 UTC (investigation took 51.0s)
- model: gpt-6-luna / prompt v4 · llm calls 42 · tool calls 59 · cost $0.0200

## Root cause (unknown, confidence 0.48, service `nginx`)

The nginx instance serving 127.0.0.1:80 became unavailable to its HTTP probe while nginx.service remained active; the specific listener/probe mechanism is unresolved, and the later shop-api discount_factor defect does not explain the earlier nginx onset.

## Evidence

- ev_1816
- ev_1818
- ev_1829
- ev_1824

## Ruled out

- shop-api dependency outage caused nginx's initial endpoint failure
- nginx bad deploy or config change caused the initial failure
- nginx.service stopped or crashed

## Alternatives

- nginx port-80 endpoint failure with active service unit; listener mechanism unknown (unknown, 0.48)
- shop-api home handler raises KeyError for missing discount_factor after deploy 60740e12, contributing to later shop-api endpoint failures (bad_deploy, 0.32)

## Proposed action (shadow mode: recorded, not executed)

`escalate` target `nginx on-call` params `{}` tier `read_only`
