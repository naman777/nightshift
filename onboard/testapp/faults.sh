#!/usr/bin/env bash
# Faults for the shop API target. Usage: faults.sh <fault> inject|revert
#   app_crash     kill -9 the gunicorn master (systemd restarts it after 45 s)
#   slow_config   config commit sets slow_ms=1500 (every request stalls)          -> cause: that config commit
#   bad_upstream  nginx conf commit points proxy_pass at a dead port (502s)        -> cause: that nginx commit
#   bad_deploy    code commit makes the home page raise; recorded as a deploy      -> cause: that deploy
set -uo pipefail
APP=~/shop
R="${ROOT:-$HOME/nightshift-run}"
fault="${1:?fault}"; action="${2:?inject|revert}"
cd "$APP"
deploy_log() { printf '{"ts": %s, "service": "shop-api", "sha": "%s", "author": "dev", "message": "%s"}\n' "$(date +%s)" "$(git rev-parse --short=8 HEAD)" "$1" >> "$R/deploys.jsonl"; }

case "$fault:$action" in
  app_crash:inject)   kill -9 "$(systemctl show -p MainPID --value shop-api.service)" ;;
  app_crash:revert)   sudo -n systemctl start shop-api.service ;;

  slow_config:inject) sed -i 's/"slow_ms": [0-9]*/"slow_ms": 1500/' config/app.json && git commit -qam "config: warm cache with 1500ms delay before serving" ;;
  slow_config:revert) git revert --no-edit HEAD >/dev/null ;;

  bad_upstream:inject) sed -i 's#proxy_pass http://127.0.0.1:5000;#proxy_pass http://127.0.0.1:5001;#' nginx/shop.conf && git commit -qam "nginx: move upstream to new app port 5001" && sudo -n nginx -s reload ;;
  bad_upstream:revert) git revert --no-edit HEAD >/dev/null && sudo -n nginx -s reload ;;

  bad_deploy:inject)
    sed -i 's#    n = db().execute("select count(\*) from orders").fetchone()\[0\]#    n = db().execute("select count(*) from orders").fetchone()[0] * cfg()["discount_factor"]#' app.py
    git commit -qam "feat: apply discount factor to order count on home page" && deploy_log "feat: apply discount factor to order count on home page" && sudo -n systemctl restart shop-api.service ;;
  bad_deploy:revert)  git revert --no-edit HEAD >/dev/null && sudo -n systemctl restart shop-api.service ;;

  *) echo "unknown: $fault $action" >&2; exit 2 ;;
esac
echo "$fault $action ok"
