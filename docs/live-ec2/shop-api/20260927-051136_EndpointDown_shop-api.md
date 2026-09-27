# EndpointDown on `shop-api`

- alert condition first true: 2026-09-27 05:09:38 UTC
- watcher detected: 2026-09-27 05:10:37 UTC (+59s)
- diagnosis finished: 2026-09-27 05:11:36 UTC (investigation took 59.0s)
- model: gpt-6-luna / prompt v4 · llm calls 51 · tool calls 76 · cost $0.0320

## Root cause (service_down, confidence 0.48, service `shop-api`)

shop-api experienced repeated process termination by SIGKILL followed by systemd restarts, causing instability of the :5000 endpoint and downstream nginx :80; the evidence does not establish the exact kill source or prove which kill preceded the initial nginx probe failure.

## Evidence

- ev_1595
- ev_1598
- ev_1591
- ev_1594
- ev_1558

## Ruled out

- Host-wide resource contention caused both probe failures.
- nginx proxy_pass change to port 5001 caused the incident.
- shop-api discount-factor deploy SHA 60740e12 is established as the failure cause.
- lb :8081 TCP endpoint failure caused the shop-api/nginx probe failures.
- lb-sandbox all-backends-unreachable errors are tied to this incident.

## Alternatives

- shop-api process repeatedly terminated by SIGKILL and restarted, creating instability at its :5000 endpoint and downstream nginx :80; exact causal timing/source of kills is unverified. (service_down, 0.48)
- nginx :80 endpoint failure not otherwise explained by its lifecycle logs; the endpoint first goes down before shop-api :5000, but the initiating mechanism is unproven. (unknown, 0.25)
- Unidentified host-level trigger causing shop-api process instability; available CPU and memory data do not strongly support contention. (unknown, 0.15)

## Proposed action (shadow mode: recorded, not executed)

`escalate` target `shop-api owning team` params `{"reason": "Investigate the source and timing of repeated SIGKILLs and coordinate controlled recovery; evidence does not establish a safe reversible mitigation."}` tier `read_only`
