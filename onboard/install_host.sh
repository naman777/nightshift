#!/usr/bin/env bash
# Installs the Nightshift host-profile collectors as systemd units (prometheus, blackbox, node_exporter, loki, alloy).
# Idempotent. Everything lives under $ROOT (default ~/nightshift-run); `onboard/uninstall_host.sh` removes it.
set -euo pipefail
ROOT="${ROOT:-$HOME/nightshift-run}"
BIN="$ROOT/bin"
SRC="${PROFILE_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/host}"   # PROFILE_DIR = output of `python -m onboard.discover --out DIR`
R="${ROOT#/}"                       # ROOT without the leading slash, for the __ROOT__ placeholder
mkdir -p "$ROOT/host" "$ROOT/data/prometheus" "$ROOT/data/loki" "$ROOT/data/alloy"
cp "$SRC/catalogue.json" "$SRC/service_map.json" "$ROOT/host/"
[ -f "$SRC/watch.env" ] && cp "$SRC/watch.env" "$ROOT/host/watch.env"
UNIT_INC="$(cat "$SRC/unit_include.txt" 2>/dev/null || echo "(lb|nsbox-lb).service")"
# app-level log files discover.py found but this user can't read (e.g. a root-only daemon log): grant the adm group read access
# so alloy (which runs with SupplementaryGroups=adm) can tail them. Known limitation: a logrotate that recreates the file with
# fresh root-only permissions undoes this until the next install run.
if [ -f "$SRC/log_grants.txt" ] && [ -s "$SRC/log_grants.txt" ]; then
  while IFS= read -r f; do
    [ -f "$f" ] && sudo -n chgrp adm "$f" 2>/dev/null && sudo -n chmod g+r "$f" 2>/dev/null
  done < "$SRC/log_grants.txt"
fi
for f in prometheus.yml rules.yml blackbox.yml loki.yml config.alloy; do
  sed "s#/__ROOT__#/$R#g" "$SRC/$f" > "$ROOT/host/$f"
done
"$BIN/promtool" check config "$ROOT/host/prometheus.yml"

unit() { # name, description, exec, [extra service lines]
  sudo -n tee "/etc/systemd/system/nightshift-$1.service" >/dev/null <<EOF
[Unit]
Description=Nightshift collector: $2
After=network.target
[Service]
User=$USER
ExecStart=$3
Restart=always
RestartSec=3
${4:-}
[Install]
WantedBy=multi-user.target
EOF
}
unit node       "node_exporter"      "$BIN/node_exporter --web.listen-address=127.0.0.1:9100 --collector.systemd --collector.systemd.unit-include=$UNIT_INC"
unit blackbox   "blackbox_exporter"  "$BIN/blackbox_exporter --config.file=$ROOT/host/blackbox.yml --web.listen-address=127.0.0.1:9115"
unit prometheus "prometheus"         "$BIN/prometheus --config.file=$ROOT/host/prometheus.yml --storage.tsdb.path=$ROOT/data/prometheus --storage.tsdb.retention.time=7d --web.listen-address=127.0.0.1:9090 --web.enable-lifecycle"
unit loki       "loki"               "$BIN/loki -config.file=$ROOT/host/loki.yml"
unit alloy      "alloy (journald -> loki)" "$BIN/alloy run --server.http.listen-addr=127.0.0.1:12345 --storage.path=$ROOT/data/alloy $ROOT/host/config.alloy" "SupplementaryGroups=systemd-journal adm"

SVCS="node blackbox prometheus loki alloy"
if [ -z "${PROFILE_DIR:-}" ]; then   # LB-specific extras (stats exporter, sandbox load) belong to the hand-written profile only
  unit lbstats    "lb stats exporter"  "/usr/bin/python3 $ROOT/nightshift/onboard/lb_stats_exporter.py 9120" 'Environment="LB_STATS_TARGETS=lb=http://127.0.0.1:8081/stats,lb-sandbox=http://127.0.0.1:8091/stats"'
  unit sandbox-load "sandbox load generator" "/usr/bin/python3 $ROOT/nightshift/onboard/loadgen.py http://127.0.0.1:8090/ 6 3"
  SVCS="$SVCS lbstats sandbox-load"
fi

sudo -n systemctl daemon-reload
for s in $SVCS; do sudo -n systemctl enable "nightshift-$s.service" 2>/dev/null; sudo -n systemctl restart "nightshift-$s.service"; done
sleep 5
for s in $SVCS; do printf '%-12s %s\n' "$s" "$(systemctl is-active nightshift-$s.service)"; done
