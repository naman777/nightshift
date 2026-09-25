# 2-minute demo script

Record at 1080p. No narration filler: captions only. Have Grafana, the dashboard incident page, Temporal UI and a terminal tiled on screen.

| Time | On screen | Action |
| --- | --- | --- |
| 0:00 | Grafana "Nightshift: target stack" | Healthy traffic: flat error rate, p99 ~180 ms. Caption: "orders, payments, LB, scheduler under steady load". |
| 0:10 | Terminal | `make chaos SCENARIO=bad-config-push-lb-timeout-00` (LB upstream timeout lowered to 50 ms, plus an unrelated payments deploy 20 minutes earlier as a red herring). |
| 0:20 | Grafana, then dashboard | Error rate climbs; alert fires; the dashboard incident page opens with the commander's hypotheses and four agent lanes working in parallel. |
| 0:45 | Terminal | `docker kill nightshift-worker` while the lanes are mid-flight. Dashboard lanes freeze. Caption: "worker killed mid-investigation". |
| 0:55 | Terminal + Temporal UI | `docker start nightshift-worker`. Temporal UI shows the same workflow resuming at the same step; dashboard lanes continue. Caption: "resumed, zero repeated LLM calls" (show the LLM-call counter unchanged). |
| 1:10 | Slack (or dashboard report card) | Root-cause report: "lb upstream_timeout_ms 2000 -> 50 in commit ...", evidence ids, and the payments deploy explicitly struck through as ruled out. |
| 1:25 | Slack / dashboard | Click **Approve** on `revert_commit`. Audit row appears: allowed, approved by user, with evidence ids. |
| 1:35 | Grafana | Error rate drops back to baseline after the config revert. |
| 1:45 | README results section / dashboard Benchmark page | Results table: accuracy, unsafe-action rate 0%, single vs multi vs naive baselines, and the hard-set row. End. |

No docker? `make demo-sim` plus `cd dashboard && npm run dev` reproduces everything except Grafana and the kill/resume shot (`tests/test_temporal.py` covers that behaviour).
