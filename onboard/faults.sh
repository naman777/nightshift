#!/usr/bin/env bash
# Real fault injection against the SANDBOX copy of the balancer only (nsbox-lb.service, ports 8090/8091/8093-8095).
# Usage: faults.sh <fault> inject|revert        faults: crashed_backend hung_backend config_break idle_client_stats service_stopped
set -uo pipefail
R="${ROOT:-$HOME/nightshift-run}"
CFG="$R/sandbox-config"
LB_PID() { pgrep -f "load_balancer --config $CFG/sandbox.conf" | head -1; }
fault="${1:?fault}"; action="${2:?inject|revert}"

case "$fault:$action" in
  crashed_backend:inject)  pkill -f "echo_server 8094" ;;
  crashed_backend:revert)  sudo -n systemctl restart nsbox-lb.service ;;

  hung_backend:inject)     kill -STOP "$(pgrep -f 'echo_server 8095' | head -1)" ;;
  hung_backend:revert)     kill -CONT "$(pgrep -f 'echo_server 8095' | head -1)" ;;

  config_break:inject)
    cd "$CFG"
    sed -i 's/^backends *=.*/backends = 9991, 9992, 9993/' sandbox.conf
    git commit -qam "rollout: move upstream pool to new port range 9991-9993" && kill -HUP "$(LB_PID)" ;;
  config_break:revert)
    cd "$CFG" && git revert --no-edit HEAD >/dev/null && kill -HUP "$(LB_PID)" ;;

  idle_client_stats:inject)
    nohup python3 -c "import socket,time; s=socket.create_connection(('127.0.0.1',8091)); time.sleep(7200)" >/dev/null 2>&1 &
    echo $! > /tmp/nsbox-idle.pid ;;
  idle_client_stats:revert)
    [ -f /tmp/nsbox-idle.pid ] && kill "$(cat /tmp/nsbox-idle.pid)" 2>/dev/null; rm -f /tmp/nsbox-idle.pid ;;

  service_stopped:inject)  sudo -n systemctl stop nsbox-lb.service ;;
  service_stopped:revert)  sudo -n systemctl start nsbox-lb.service ;;

  *) echo "unknown: $fault $action" >&2; exit 2 ;;
esac
echo "$fault $action ok"
