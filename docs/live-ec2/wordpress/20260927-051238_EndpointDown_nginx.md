# EndpointDown on `nginx`

- alert condition first true: 2026-09-27 05:09:38 UTC
- watcher detected: 2026-09-27 05:11:36 UTC (+118s)
- diagnosis finished: 2026-09-27 05:12:38 UTC (investigation took 61.8s)
- model: gpt-6-luna / prompt v4 · llm calls 37 · tool calls 74 · cost $0.0233

## Root cause (unknown, confidence 0.18, service `nginx`)

The nginx endpoint at http://127.0.0.1:80/ was the earliest observed failing endpoint, but evidence does not establish whether its listener/proxy behavior or another nginx-local mechanism caused the failure; shop-api:5000 went down later.

## Evidence

- ev_1624
- ev_1625
- ev_1627
- ev_1633
- ev_1637
- ev_1647

## Ruled out

- The persistent lb backend at 127.0.0.1:8081 initiated this incident.
- Host CPU contention caused the initial endpoint failures.
- The reverted nginx upstream move to port 5001 caused the failure at onset.
- The reverted shop-api slow_ms delay caused the failure at onset.

## Alternatives

- An unidentified nginx-local failure of the exact endpoint http://127.0.0.1:80/; it was sampled down before shop-api:5000, and no matching nginx error or listener evidence identifies the mechanism. (unknown, 0.18)
- Shop-api:5000 became unavailable after nginx’s first observed drop; deploy 60740e12 was shortly before its transition, but the changed home handler does not establish a cause for /health failure. (unknown, 0.14)
- Host CPU rose after the endpoints had already dropped, so resource contention is a weak candidate for the onset. (resource_contention, 0.05)

## Proposed action (shadow mode: recorded, not executed)

`escalate` target `nginx owning team` params `{}` tier `read_only`
