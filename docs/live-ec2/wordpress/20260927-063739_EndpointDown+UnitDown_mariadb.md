# EndpointDown+UnitDown on `mariadb`

- alert condition first true: 2026-09-27 06:35:28 UTC
- watcher detected: 2026-09-27 06:37:04 UTC (+96s)
- diagnosis finished: 2026-09-27 06:37:39 UTC (investigation took 34.8s)
- model: gpt-6-luna / prompt v4 · llm calls 26 · tool calls 43 · cost $0.0101

## Root cause (service_down, confidence 0.36, service `mariadb`)

The exact MariaDB instance at 127.0.0.1:3306 and its mariadb.service unit became unavailable together around 06:35 UTC, but available evidence does not distinguish a deliberate stop from a process failure or establish an effective configuration cause.

## Evidence

- ev_2281
- ev_2282
- ev_2279
- ev_2290
- ev_2288
- ev_2285
- ev_2286

## Ruled out

- Host resource pressure caused MariaDB to stop.
- A recent MariaDB-specific config change prevented the service from listening.
- The shop-api deploy caused the MariaDB outage.
- A MariaDB application-code defect caused the unit-down and port-down state.

## Alternatives

- MariaDB service on the exact instance 127.0.0.1:3306 became inactive; cause/actor cannot be resolved from available lifecycle logs. (service_down, 0.36)

## Proposed action (shadow mode: recorded, not executed)

`restart_replica` target `mariadb` params `{"service": "mariadb"}` tier `reversible`
