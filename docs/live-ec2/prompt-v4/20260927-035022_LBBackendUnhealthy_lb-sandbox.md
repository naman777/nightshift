# LBBackendUnhealthy on `lb-sandbox`

- alert condition first true: 2026-09-27 03:48:40 UTC
- watcher detected: 2026-09-27 03:49:37 UTC (+57s)
- diagnosis finished: 2026-09-27 03:50:22 UTC (investigation took 45.1s)
- model: gpt-6-luna / prompt v4 · llm calls 35 · tool calls 55 · cost $0.0177

## Root cause (service_down, confidence 0.24, service `lb-sandbox`)

The lb-sandbox upstream entry for 127.0.0.1:8094 became unavailable and was marked unhealthy; the evidence does not determine whether its listener/process failed or a balancer probe/client-connect failure caused the health state.

## Evidence

- ev_883
- ev_884
- ev_887
- ev_890

## Ruled out

- The sandbox pool config change caused the incident at onset.
- A newly deployed lb-sandbox build caused the onset.
- A host CPU, memory, or disk resource shift caused the onset.

## Alternatives

- The 127.0.0.1:8094 backend process/listener was unavailable, causing lb-sandbox to report backend_up=0 and mark it unhealthy; direct process/listener evidence is absent. (service_down, 0.24)
- A lb-sandbox health-check or client-connect failure marked only backend 8094 unhealthy; code supports this mechanism, but no incident-time trigger is observed. (healthcheck_misconfig, 0.18)
- A defect in the lb-sandbox health-check path caused a backend-specific false unhealthy state; the code path is plausible but incident-time linkage is absent. (code_defect, 0.12)

## Proposed action (shadow mode: recorded, not executed)

`escalate` target `echo-backends owning team` params `{}` tier `read_only`
