# LBAdminPortUnresponsive on `lb-sandbox`

- alert condition first true: 2026-09-27 03:44:50 UTC
- watcher detected: 2026-09-27 03:47:03 UTC (+133s)
- diagnosis finished: 2026-09-27 03:47:52 UTC (investigation took 48.9s)
- model: gpt-6-luna / prompt v4 · llm calls 43 · tool calls 71 · cost $0.0217

## Root cause (code_defect, confidence 0.36, service `lb-sandbox`)

The lb-sandbox stats/admin listener became unresponsive while nsbox-lb.service was still active, consistent with stats_loop blocking on a client read; the required idle-client trigger is unobserved, and the later unit-down event is not explained by this mechanism.

## Evidence

- ev_847
- ev_851
- ev_853
- ev_848
- ev_849
- ev_846
- ev_842
- ev_858

## Ruled out

- A sandbox backend config change or deploy caused the onset and remained in effect.
- Host CPU, memory, or disk contention caused the failure.
- The admin-port failure began only because the whole unit had already stopped.

## Alternatives

- lb-sandbox stats_loop may have stalled after accepting an idle admin client, due to its blocking read; trigger not confirmed. (code_defect, 0.36)
- nsbox-lb.service later became inactive at about 03:44:57; logs do not establish whether it was deliberately stopped or why. (service_down, 0.25)
- An unobserved host or operational cause affected the sandbox; no pressure or change evidence establishes it. (resource_contention, 0.08)

## Proposed action (shadow mode: recorded, not executed)

`escalate` target `lb-sandbox` params `{}` tier `read_only`
