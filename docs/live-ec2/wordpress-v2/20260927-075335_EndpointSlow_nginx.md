# EndpointSlow on `nginx`

- alert condition first true: 2026-09-27 07:51:08 UTC
- watcher detected: 2026-09-27 07:52:33 UTC (+85s)
- diagnosis finished: 2026-09-27 07:53:35 UTC (investigation took 61.9s)
- model: gpt-6-luna / prompt v4 · llm calls 44 · tool calls 59 · cost $0.0241

## Root cause (capacity, confidence 0.72, service `php8.5-fpm`)

php8.5-fpm’s www pool on the nginx :8200 FastCGI path repeatedly hit its single-child limit and restarted, producing intermittent latency and endpoint-down samples; the evidence does not establish what triggered the FPM exits or the live pool configuration.

## Evidence

- ev_2565
- ev_2566
- ev_2554
- ev_2577
- ev_2581
- ev_2584

## Ruled out

- Host CPU resource contention is the primary established cause.
- LB backend 127.0.0.1:8081 latency causes nginx :8200 latency.
- A nginx bad deploy or changed nginx config is established as the cause.

## Alternatives

- php8.5-fpm www pool reached its observed pm.max_children=1 capacity and repeatedly restarted on the FastCGI path serving nginx :8200. (capacity, 0.72)
- Host CPU contention of unidentified origin contributes to nginx :8200 latency; sampled CPU and latency rise together, with uncertain onset ordering. (resource_contention, 0.45)

## Proposed action (shadow mode: recorded, not executed)

`escalate` target `PHP-FPM / platform on-call team` params `{"reason": "Review php8.5-fpm lifecycle and www-pool configuration around 07:44\u201307:51 UTC; validate safe worker-capacity adjustment and determine why the process repeatedly exited. Do not change worker limits until host memory and active pool configuration are verified."}` tier `read_only`
