# LBAdminPortUnresponsive on `lb-sandbox`

- alert condition first true: 2026-09-27 03:41:30 UTC
- watcher detected: 2026-09-27 03:42:58 UTC (+88s)
- diagnosis finished: 2026-09-27 03:43:32 UTC (investigation took 33.8s)
- model: gpt-6-luna / prompt v4 · llm calls 29 · tool calls 43 · cost $0.0166

## Root cause (code_defect, confidence 0.48, service `lb-sandbox`)

The lb-sandbox stats listener on :8091 became unresponsive while nsbox-lb.service remained active; the best-supported mechanism is stats_loop's serial blocking client read without a timeout, although no runtime evidence proves a stalled client triggered it.

## Evidence

- ev_776
- ev_786
- ev_787
- ev_778
- ev_779
- ev_782

## Ruled out

- A sandbox.conf change caused the admin listener failure.
- Host CPU, memory, or disk contention caused the admin probe timeout.
- The lb-sandbox process stopped or crashed.
- A deployed lb-sandbox build immediately triggered the failure.

## Alternatives

- The :8091 stats endpoint's serial blocking read without a timeout may have stalled subsequent requests; actual triggering client is unobserved. (code_defect, 0.48)
- An unobserved listener-specific service failure caused the :8091 probe timeout while the process stayed active. (service_down, 0.20)

## Proposed action (shadow mode: recorded, not executed)

`escalate` target `lb-sandbox` params `{}` tier `read_only`
