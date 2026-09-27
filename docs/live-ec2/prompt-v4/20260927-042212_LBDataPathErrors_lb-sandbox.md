# LBDataPathErrors on `lb-sandbox`

- alert condition first true: 2026-09-27 04:20:40 UTC
- watcher detected: 2026-09-27 04:21:35 UTC (+55s)
- diagnosis finished: 2026-09-27 04:22:12 UTC (investigation took 37.1s)
- model: gpt-6-luna / prompt v4 · llm calls 31 · tool calls 40 · cost $0.0145

## Root cause (dependency_outage, confidence 0.78, service `lb-sandbox`)

lb-sandbox’s backend configuration change 62b6cafd switched the pool to unavailable ports 9991–9993 shortly before the renewed data-path errors; runtime loading of that config is not independently confirmed.

## Evidence

- ev_1175
- ev_1183
- ev_1186
- ev_1196
- ev_1197
- ev_1185

## Ruled out

- A bad deploy or code regression in lb-sandbox caused the failures.
- A latent data-path code defect triggered by fault injection is the leading cause.
- The 8093–8095 backend group was entirely down at the renewed error onset.
- The earlier backend-pool changes explain the current onset.

## Alternatives

- lb-sandbox configuration 62b6cafd selected unavailable backend ports 9991–9993, leaving the data path without its intended healthy pool. (dependency_outage, 0.78)
- The deliberate stop of nsbox-lb.service near onset may have contributed, but available lifecycle evidence does not establish its duration or restart sequence. (service_down, 0.18)

## Proposed action (shadow mode: recorded, not executed)

`set_config` target `lb-sandbox` params `{"key": "backends", "value": "8093,8094,8095"}` tier `reversible`
