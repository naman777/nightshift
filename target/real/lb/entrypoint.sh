#!/bin/sh
# Runs the real C++ load balancer with the same shared config file the stub reads (/config/lb.yaml) and
# sends SIGHUP whenever that file changes, so `chaos config lb upstream_timeout_ms 50` takes effect within ~1 s.
#
# Config keys honoured (see docs/live-stack.md): upstream_timeout_ms, upstream_weight_orders_<n>, health_check_interval_ms.
# Backends are pinned on the command line (orders-svc replicas); everything else comes from the config file.
set -u
CONF=${LB_CONFIG:-/config/lb.yaml}
BACKENDS=${LB_BACKENDS:-orders-svc-1:8080,orders-svc-2:8080}

export LB_LOG_FORMAT=json LB_SERVICE=lb LB_REPLICA=lb-1

/usr/local/bin/load_balancer --config "$CONF" --port 8080 --backends "$BACKENDS" --algo rr --threads "${LB_THREADS:-64}" \
    --health-path /healthz &
LB_PID=$!
trap 'kill -TERM $LB_PID 2>/dev/null; wait $LB_PID; exit 0' TERM INT

last=$(md5sum "$CONF" 2>/dev/null | cut -d' ' -f1)
while kill -0 "$LB_PID" 2>/dev/null; do
    sleep 1
    now=$(md5sum "$CONF" 2>/dev/null | cut -d' ' -f1)
    if [ "$now" != "$last" ]; then
        last=$now
        kill -HUP "$LB_PID" 2>/dev/null
    fi
done
wait "$LB_PID"
