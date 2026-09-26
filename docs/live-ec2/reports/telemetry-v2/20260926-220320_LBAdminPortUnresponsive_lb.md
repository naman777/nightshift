# LBAdminPortUnresponsive on `lb`

- alert condition first true: 2026-09-26 22:01:20 UTC
- watcher detected: 2026-09-26 22:02:47 UTC (+87s)
- diagnosis finished: 2026-09-26 22:03:20 UTC (investigation took 32.6s)
- model: gpt-6-luna / prompt v3 · llm calls 32 · tool calls 36 · cost $0.0119

## Root cause (healthcheck_misconfig, confidence 0.67, service `lb`)

lb admin listener is unavailable while the data listener remains healthy, consistent with a tolerated bind/listen setup failure; no triggering config change or specific socket error is established (ev_216, ev_218, ev_223, ev_224).

## Evidence

- ev_216
- ev_217
- ev_218
- ev_219
- ev_223
- ev_224
- ev_212
- ev_221
- ev_213
- ev_214
- ev_215

## Ruled out

- Host resource contention or exhaustion is preventing the admin port from responding.
- A broad lb data-path outage or stalled data listener is causing the admin probe failure.
- A newly deployed lb code defect is established as the cause.

## Alternatives

- lb admin listener setup/configuration failure is tolerated independently of the data listener, leaving admin port unavailable; exact trigger/error is unknown. (healthcheck_misconfig, 0.67)
- lb-specific configuration change caused an invalid admin bind port or socket setup failure; timing and values are not verified. (config_change, 0.25)

## Proposed action (shadow mode: recorded, not executed)

`none` target `lb` params `{}` tier `read_only`
