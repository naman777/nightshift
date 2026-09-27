# EndpointDown on `nginx`

- alert condition first true: 2026-09-27 05:20:28 UTC
- watcher detected: 2026-09-27 05:21:23 UTC (+56s)
- diagnosis finished: 2026-09-27 05:22:11 UTC (investigation took 47.2s)
- model: gpt-6-luna / prompt v4 · llm calls 42 · tool calls 57 · cost $0.0163

## Root cause (dependency_outage, confidence 0.58, service `nginx`)

The nginx :80 endpoint went down shortly after nginx config sha 23b1b450 changed proxy_pass from shop-api port 5000 to 5001; the timing supports the change as the trigger, but config application and port-5001 health are unverified (ev_1754, ev_1755, ev_1762, ev_1766).

## Evidence

- ev_1754
- ev_1755
- ev_1762
- ev_1764
- ev_1766
- ev_1758
- ev_1761

## Ruled out

- nginx process/unit stopped or host resource saturation caused the endpoint failure
- shop-api port 5000 became unavailable or slow, causing the nginx failure
- A new nginx deployment caused a code regression

## Alternatives

- nginx proxy_pass change sha 23b1b450 redirected traffic to port 5001, which may have been unavailable; endpoint failure followed, but target health and reload status are unverified. (dependency_outage, 0.58)
- An nginx listener or probe-path fault independent of the upstream change; no direct listener/error evidence was found. (healthcheck_misconfig, 0.20)

## Proposed action (shadow mode: recorded, not executed)

`set_config` target `nginx` params `{"key": "proxy_pass", "value": "http://127.0.0.1:5000"}` tier `reversible`
