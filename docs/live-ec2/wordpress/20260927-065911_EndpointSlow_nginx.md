# EndpointSlow on `nginx`

- alert condition first true: 2026-09-27 06:57:08 UTC
- watcher detected: 2026-09-27 06:58:33 UTC (+85s)
- diagnosis finished: 2026-09-27 06:59:11 UTC (investigation took 37.7s)
- model: gpt-6-luna / prompt v4 · llm calls 26 · tool calls 40 · cost $0.0094

## Root cause (unknown, confidence 0.18, service `nginx`)

nginx's WordPress endpoint at 127.0.0.1:8200 became persistently slow; the evidence does not establish whether PHP-FPM waiting or another mechanism caused the delay, and no trigger is identified.

## Evidence

- ev_2387
- ev_2390
- ev_2392
- ev_2399
- ev_2400
- ev_2405
- ev_2406
- ev_2409

## Ruled out

- lb :8081 outage caused the nginx :8200 slowdown
- nginx-specific deploy/config change caused the onset
- host resource contention caused the endpoint delay

## Alternatives

- Unidentified mechanism affecting nginx WordPress listener at 127.0.0.1:8200; PHP-FPM waiting is a possible but unconfirmed path. (unknown, 0.18)

## Proposed action (shadow mode: recorded, not executed)

`escalate` target `nginx/WordPress and PHP-FPM on-call` params `{}` tier `read_only`
