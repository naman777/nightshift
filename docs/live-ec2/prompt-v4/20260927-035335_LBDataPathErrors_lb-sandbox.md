# LBDataPathErrors on `lb-sandbox`

- alert condition first true: 2026-09-27 03:52:00 UTC
- watcher detected: 2026-09-27 03:52:58 UTC (+58s)
- diagnosis finished: 2026-09-27 03:53:35 UTC (investigation took 37.8s)
- model: gpt-6-luna / prompt v4 · llm calls 28 · tool calls 51 · cost $0.0159

## Root cause (config_change, confidence 0.66, service `lb-sandbox`)

lb-sandbox’s active backend configuration change sha 081d479f selected ports 9991–9993; all three were reported DOWN, with repeated all-backends-unreachable errors. This is the best-supported explanation for the worsening at alert onset, though intermittent data-path errors predated the change and listener existence/config reload are unverified.

## Evidence

- ev_891
- ev_892
- ev_912
- ev_913
- ev_914
- ev_915
- ev_919
- ev_920
- ev_921
- ev_922
- ev_923

## Ruled out

- A newly deployed sandbox build caused a data-path regression.
- Host resource contention caused the failures.
- The config change initiated all errors at onset.
- Earlier rollout sha 27f30d26 remained the active change at onset.

## Alternatives

- Active backend-list config sha 081d479f routes lb-sandbox to backends 9991–9993, all reported DOWN; likely worsened the data-path failures, but listener existence and config reload are unverified. (config_change, 0.66)
- Pre-existing intermittent lb-sandbox data-path/backend failures of undetermined mechanism; observed before the latest config rollout. (unknown, 0.20)

## Proposed action (shadow mode: recorded, not executed)

`set_config` target `lb-sandbox` params `{"key": "backends", "value": "8093, 8094, 8095"}` tier `reversible`
