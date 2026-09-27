# LBDataPathErrors on `lb-sandbox`

- alert condition first true: 2026-09-27 03:31:00 UTC
- watcher detected: 2026-09-27 03:31:56 UTC (+56s)
- diagnosis finished: 2026-09-27 03:32:20 UTC (investigation took 24.2s)
- model: gpt-6-luna / prompt v4 · llm calls 21 · tool calls 33 · cost $0.0136

## Root cause (dependency_outage, confidence 0.42, service `lb-sandbox`)

lb-sandbox experienced data-path failures with all-backends-unreachable errors after a transient loss of backend 127.0.0.1:8094; the exact trigger is inconclusive.

## Evidence

- ev_703
- ev_704
- ev_707
- ev_708
- ev_709
- ev_710

## Ruled out

- The sandbox unit or admin listener went down as the direct cause.
- A deployed build change caused the incident.
- The pool change to ports 9991-9993 is established as the cause.

## Alternatives

- Transient outage/unreachability of sandbox backend 127.0.0.1:8094 preceded the all-backends-unreachable data-path errors; causal link is plausible but not proven. (dependency_outage, 0.42)
- Sandbox pool config change to 9991-9993 may have temporarily pointed at unavailable backends, but its persistence at error onset is unverified and it was reverted at 1790479882. (config_change, 0.28)
- A balancer probe/forwarding code-path defect is possible, but no runtime evidence establishes that its trigger occurred. (code_defect, 0.16)

## Proposed action (shadow mode: recorded, not executed)

`none` target `lb-sandbox` params `{}` tier `read_only`
