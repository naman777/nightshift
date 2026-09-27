# EndpointDown+UnitDown on `mariadb`

- alert condition first true: 2026-09-27 05:45:58 UTC
- watcher detected: 2026-09-27 05:47:59 UTC (+122s)
- diagnosis finished: 2026-09-27 05:48:40 UTC (investigation took 40.2s)
- model: gpt-6-luna / prompt v4 · llm calls 27 · tool calls 36 · cost $0.0113

## Root cause (service_down, confidence 0.91, service `mariadb`)

mariadb.service on 127.0.0.1:3306 was cleanly stopped at 05:45:43 UTC by an unidentified initiator and remained inactive, causing the endpoint-down alert; evidence does not identify the actor or reason.

## Evidence

- ev_1902
- ev_1903
- ev_1904
- ev_1916
- ev_1905

## Ruled out

- A MariaDB bad deploy or config change caused the stop.
- Host resource contention or exhaustion caused MariaDB to fail.
- MariaDB code defect caused the unit-down event.
- Recent shop-api deploys caused the MariaDB stop.

## Alternatives

- mariadb.service on 127.0.0.1:3306 was cleanly stopped at 05:45:43 UTC by an unidentified initiator and was not observed starting again; the initiator is unknown. (service_down, 0.91)

## Proposed action (shadow mode: recorded, not executed)

`restart_replica` target `mariadb` params `{"service": "mariadb"}` tier `reversible`
