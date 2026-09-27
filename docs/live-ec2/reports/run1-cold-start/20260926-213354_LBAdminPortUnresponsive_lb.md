# LBAdminPortUnresponsive on `lb`

- alert condition first true: 2026-09-26 21:28:20 UTC
- watcher detected: 2026-09-26 21:33:54 UTC (+334s)
- diagnosis finished: 2026-09-26 21:33:54 UTC (investigation took 0.0s)
- model: gpt-6-luna / prompt v3 · llm calls 18 · tool calls 23 · cost $0.0064

## Root cause (healthcheck_misconfig, confidence 0.56, service `lb`)

The lb stats listener can become unresponsive when a client connects to :8081 and sends no request, blocking its sole stats thread indefinitely (code finding; no triggering commit/deploy identified).

## Evidence

- ev_7
- ev_8
- ev_9
- ev_3
- ev_4
- ev_6
- ev_1
- ev_2

## Ruled out

- H2: LB host resource contention or exhaustion prevented admin responses.
- H3: A recent LB config or code change directly impaired the admin listener.
- H4: Host capacity pressure affected the admin listener.

## Alternatives

- An idle client can hold the only LB stats-listener thread in a blocking read, leaving subsequent admin requests unanswered. (healthcheck_misconfig, 0.56)
- Host resource contention or capacity pressure affecting LB administration; not established by available telemetry. (resource_contention, 0.12)
- Recent LB config/deploy change impairing the admin listener; no changes were returned in the queried window. (config_change, 0.08)

## Proposed action (shadow mode: recorded, not executed)

`set_config` target `lb` params `{"key": "stats_client_read_timeout", "value": "bounded timeout; validate supported setting before applying"}` tier `reversible`
