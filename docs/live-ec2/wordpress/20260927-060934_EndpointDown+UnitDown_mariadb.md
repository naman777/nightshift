# EndpointDown+UnitDown on `mariadb`

- alert condition first true: 2026-09-27 06:07:58 UTC
- watcher detected: 2026-09-27 06:09:15 UTC (+77s)
- diagnosis finished: 2026-09-27 06:09:34 UTC (investigation took 19.2s)
- model: gpt-6-luna / prompt v4 · llm calls 17 · tool calls 25 · cost $0.0078

## Root cause (service_down, confidence 0.94, service `mariadb`)

mariadb.service on 127.0.0.1:9100 was deliberately stopped, taking its 127.0.0.1:3306 endpoint down from the alert onset until it started successfully again; the initiating operator or automation is not identified.

## Evidence

- ev_2067
- ev_2068
- ev_2073
- ev_2074

## Ruled out

- Host resource contention caused the MariaDB interruption.
- The lb :8081 failure was the MariaDB alert cause.
- A recent shop-api deploy caused the MariaDB outage.

## Alternatives

- mariadb.service on 127.0.0.1:9100 was cleanly and deliberately stopped, taking 127.0.0.1:3306 down; actor unknown. (service_down, 0.94)

## Proposed action (shadow mode: recorded, not executed)

`none` target `mariadb` params `{}` tier `read_only`
