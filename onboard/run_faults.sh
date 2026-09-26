#!/usr/bin/env bash
# Runs each sandbox fault: inject -> wait for the alert -> wait for the watcher's report -> revert -> wait for recovery.
# Appends one JSON line per run to $OUT with the wall-clock timings. Needs the collectors + nightshift-watch.service running.
#   run_faults.sh [rounds] [fault ...]
set -uo pipefail
R="${ROOT:-$HOME/nightshift-run}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPORTS="$R/reports"
OUT="${OUT:-$R/fault_runs.jsonl}"
rounds="${1:-1}"; shift || true
faults=("$@"); [ ${#faults[@]} -eq 0 ] && faults=(crashed_backend config_break idle_client_stats service_stopped)  # hung_backend is latent under light load (see docs), run it explicitly

sandbox_alerts() { curl -s localhost:9090/api/v1/alerts | jq -r '[.data.alerts[] | select(.labels.service=="lb-sandbox" and .state=="firing") | .labels.alertname] | join(",")'; }
sandbox_any_alert() { curl -s localhost:9090/api/v1/alerts | jq -r '[.data.alerts[] | select(.labels.service=="lb-sandbox") | .labels.alertname] | join(",")'; }
report_count()   { ls "$REPORTS"/*_lb-sandbox.json 2>/dev/null | wc -l; }
wait_for() { # seconds, command that must print non-empty
  local end=$((SECONDS + $1)); while [ $SECONDS -lt $end ]; do out="$($2)"; [ -n "$out" ] && { echo "$out"; return 0; }; sleep 3; done; return 1; }

for round in $(seq 1 "$rounds"); do
  for f in "${faults[@]}"; do
    # start from a healthy sandbox with no sandbox alerts firing
    end=$((SECONDS + 240)); while [ $SECONDS -lt $end ] && [ -n "$(sandbox_any_alert)" ]; do sleep 3; done
    [ -n "$(sandbox_any_alert)" ] && echo "warning: alerts not clear before $f"
    before=$(report_count)
    t_inject=$(date +%s)
    "$HERE/faults.sh" "$f" inject
    alerts=$(wait_for 240 sandbox_alerts) && t_alert=$(date +%s) || { alerts=""; t_alert=0; }
    got=""; t_report=0
    if [ -n "$alerts" ]; then
      end=$((SECONDS + 300))
      while [ $SECONDS -lt $end ]; do
        # wait for reports for every distinct alert that fires in this fault: settle 45 s after the last new report
        n=$(report_count)
        if [ "$n" -gt "$before" ]; then got=1; t_report=$(date +%s); sleep 45; [ "$(report_count)" -eq "$n" ] && break; fi
        sleep 3
      done
    fi
    latest=$(ls -t "$REPORTS"/*_lb-sandbox.json 2>/dev/null | head -$(( $(report_count) - before )) | xargs -r -n1 basename | paste -sd, -)
    "$HERE/faults.sh" "$f" revert
    jq -nc --arg fault "$f" --argjson round "$round" --argjson t_inject "$t_inject" --argjson t_alert "$t_alert" --argjson t_report "$t_report" \
       --arg alerts "$alerts" --arg reports "$latest" \
       '{fault:$fault, round:$round, t_inject:$t_inject, alert_fired_after_s:(if $t_alert>0 then $t_alert-$t_inject else null end),
         report_after_s:(if $t_report>0 then $t_report-$t_inject else null end), alerts:$alerts, reports:$reports}' >> "$OUT"
    tail -1 "$OUT"
    sleep 20
  done
done
echo "all done"
