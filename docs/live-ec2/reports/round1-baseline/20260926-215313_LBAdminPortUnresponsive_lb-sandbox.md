# LBAdminPortUnresponsive on `lb-sandbox`

- alert condition first true: 2026-09-26 21:51:00 UTC
- watcher detected: 2026-09-26 21:52:23 UTC (+83s)
- diagnosis finished: 2026-09-26 21:53:13 UTC (investigation took 50.4s)
- model: gpt-6-luna / prompt v3 · llm calls 49 · tool calls 55 · cost $0.0173

## Root cause (bad_deploy, confidence 0.65, service `lb`)

lb-sandbox's stats handler can become unresponsive when a client holds its sole stats thread in a blocking read without sending a request; this code-path defect is supported, but no specific incident client or triggering deploy is identified.

## Evidence

- ev_173
- ev_174
- ev_157
- ev_170
- ev_183
- ev_184
- ev_175
- ev_163
- ev_164
- ev_165
- ev_179
- ev_180
- ev_181

## Ruled out

- Host resource exhaustion/contention caused the initial admin failure.
- The backend-pool configuration change directly disabled the admin listener.
- A recent sandbox deploy introduced the defect.
- A binding/port change caused the probe mismatch.

## Alternatives

- A stats client may block lb-sandbox's single stats handler in an unbounded read, preventing later admin probes from being served; direct observation of a stalled client is absent. (bad_deploy, 0.65)
- An unobserved admin listener or process fault; available logs do not identify one. (unknown, 0.18)

## Proposed action (shadow mode: recorded, not executed)

`none` target `` params `{}` tier `read_only`
