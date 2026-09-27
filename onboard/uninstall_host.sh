#!/usr/bin/env bash
# Removes the Nightshift collectors and (with --purge) the whole $ROOT directory. Does not touch the monitored services.
set -uo pipefail
ROOT="${ROOT:-$HOME/nightshift-run}"
for s in sandbox-load lbstats alloy loki prometheus blackbox node watch; do
  sudo -n systemctl disable --now "nightshift-$s.service" 2>/dev/null
  sudo -n rm -f "/etc/systemd/system/nightshift-$s.service"
done
sudo -n systemctl disable --now nsbox-lb.service 2>/dev/null
sudo -n rm -f /etc/systemd/system/nsbox-lb.service
sudo -n systemctl daemon-reload
[ "${1:-}" = "--purge" ] && rm -rf "$ROOT"
echo "done"
