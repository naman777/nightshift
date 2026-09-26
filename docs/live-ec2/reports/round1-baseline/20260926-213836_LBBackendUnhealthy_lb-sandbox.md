# LBBackendUnhealthy on `lb-sandbox`

- alert condition first true: 2026-09-26 21:37:10 UTC
- watcher detected: 2026-09-26 21:37:41 UTC (+31s)
- diagnosis finished: 2026-09-26 21:38:36 UTC (investigation took 55.1s)
- model: gpt-6-luna / prompt v3 · llm calls 43 · tool calls 59 · cost $0.0172

## Root cause (healthcheck_misconfig, confidence 0.42, service `lb`)

The lb-sandbox health-check implementation can block its serial backend checks on a recv() with no receive timeout, potentially leaving later upstreams unchecked; the evidence does not prove this caused the observed drop from three healthy upstreams to two.

## Evidence

- ev_19
- ev_29
- ev_30
- ev_31
- ev_40
- ev_46

## Ruled out

- H2: The new sandbox config concretely misconfigures backend addresses or health-check settings.
- H3: A recent balancer deployment introduced the defect.
- H4: Sustained host resource contention caused backend availability loss.
- H1: A backend process was confirmed down or refusing connections.

## Alternatives

- Serial health-check implementation may block indefinitely on a backend recv() without timeout, preventing checks of subsequent backends; causal link to this alert is unproven. (healthcheck_misconfig, 0.42)
- An echo backend may have become unavailable, reducing healthy upstream count; no per-port status or explicit refusal/process-failure evidence identifies a backend. (dependency_outage, 0.25)
- A sandbox LB configuration mismatch may have caused unhealthy backend checks; actual listener addresses and health-check settings are unavailable for comparison. (config_change, 0.12)

## Proposed action (shadow mode: recorded, not executed)

`none` target `` params `{}` tier `read_only`
