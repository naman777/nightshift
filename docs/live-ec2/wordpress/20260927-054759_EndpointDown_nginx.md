# EndpointDown on `nginx`

- alert condition first true: 2026-09-27 05:45:58 UTC
- watcher detected: 2026-09-27 05:47:04 UTC (+66s)
- diagnosis finished: 2026-09-27 05:47:59 UTC (investigation took 55.4s)
- model: gpt-6-luna / prompt v4 · llm calls 40 · tool calls 65 · cost $0.0171

## Root cause (service_down, confidence 0.64, service `mariadb`)

MariaDB on 127.0.0.1:3306 was deliberately shut down and mariadb.service stopped normally at 05:45:43, leaving the database unavailable around the incident; nginx's WordPress-backed :8200 endpoint went down in the same sampled interval, but available timing does not prove the dependency link or identify who initiated the stop.

## Evidence

- ev_1870
- ev_1885
- ev_1880
- ev_1881
- ev_1882
- ev_1892
- ev_1877
- ev_1878
- ev_1863
- ev_1864
- ev_1889

## Ruled out

- H1: nginx :8200 listener or probe misconfiguration is the established cause.
- H3: a recent nginx or MariaDB deploy caused the transition.
- H4: sustained host resource contention caused the failures.

## Alternatives

- MariaDB service on 127.0.0.1:3306 underwent an orderly stop at 05:45:43 and remained inactive in observed metrics; likely caused or contributed to failure of the WordPress-backed nginx :8200 endpoint, but the causal link and shutdown initiator are unconfirmed. (service_down, 0.64)
- A distinct nginx :8200 request-path or endpoint issue while nginx.service remained active; runtime listener/probe failure mode is not established. (healthcheck_misconfig, 0.25)
- Host resource contention preceding the transition, without evidence of sustained elevated CPU/memory after endpoint failures. (resource_contention, 0.11)

## Proposed action (shadow mode: recorded, not executed)

`restart_replica` target `mariadb` params `{"service": "mariadb"}` tier `reversible`
