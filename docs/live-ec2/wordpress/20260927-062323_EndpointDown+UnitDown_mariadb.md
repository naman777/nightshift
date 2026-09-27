# EndpointDown+UnitDown on `mariadb`

- alert condition first true: 2026-09-27 06:20:58 UTC
- watcher detected: 2026-09-27 06:22:41 UTC (+104s)
- diagnosis finished: 2026-09-27 06:23:23 UTC (investigation took 41.2s)
- model: gpt-6-luna / prompt v4 · llm calls 28 · tool calls 43 · cost $0.0121

## Root cause (service_down, confidence 0.54, service `mariadb`)

MariaDB on 127.0.0.1:3306 / mariadb.service was cleanly shut down at 06:20:40–41 UTC, leaving the unit and endpoint down at the later observed outage; the initiator is unknown, and the shutdown’s connection to the 06:20:56 state transition is not proven.

## Evidence

- ev_2206
- ev_2207
- ev_2193
- ev_2194
- ev_2201
- ev_2209

## Ruled out

- Host resource contention or exhaustion caused MariaDB to stop.
- A MariaDB-specific deploy or verified config change caused the outage.
- A MariaDB crash is established as the mechanism.

## Alternatives

- MariaDB service was cleanly stopped; exact actor/reason and whether this stop explains the final transition remain unknown. (service_down, 0.54)
- Host resource contention may have contributed, but CPU increase is not causal proof and pressure is not established. (resource_contention, 0.20)

## Proposed action (shadow mode: recorded, not executed)

`restart_replica` target `mariadb` params `{"service": "mariadb"}` tier `reversible`
