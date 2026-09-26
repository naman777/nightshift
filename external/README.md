# external/

Checkouts of the real components the Nightshift stubs stand in for. The checkouts themselves are git-ignored; recreate them with:

```bash
git clone https://github.com/naman777/Foreman        external/foreman
git clone https://github.com/naman777/Load-Balancer-CPP external/load-balancer
git -C external/foreman        config core.autocrlf false   # on Windows, before checkout, or shell scripts get CRLF endings
git -C external/load-balancer  config core.autocrlf false
git -C external/load-balancer  apply ../patches/load-balancer-test-fixes.patch
```

## Verified (2026-09-26)

| Component | Result |
| --- | --- |
| C++ load balancer, unit tests | 26/26 pass (after the patch: `select_round_robin` was replaced by `select_weighted_rr`, and `make test` did not build `LoadBalancer.o` first) |
| C++ load balancer, `scripts/test.sh` | 4/4 pass (after the patch: `((PASS++))` under `set -e` aborted the script after its first pass; stats count matched the top-level `"port"` too; least-connections sends sequential requests to backend 0 by design, so the distribution check uses round-robin) |
| Foreman coordinator / worker tests | 31/31 and 12/12 pass |
| Foreman `node scripts/node-smoke.mjs` against `docker compose up` | all 6 checks pass (health, success, failure, timeout, artifact, 6 concurrent jobs, WebSocket) |

## Not yet wired into the Nightshift stack, and why

The real components do not satisfy the stub contracts in `target/stubs/`, so a drop-in swap is not possible:

* **Load balancer**: no `/metrics` (JSON `/stats` only); backends are `127.0.0.1:<port>` only (no hostnames); no `upstream_timeout_ms` (idle timeout is hard-coded), health-check interval is fixed at 5 s; config is `port/backends/weights/algo/threads/max_conn`, reloaded with SIGHUP (weights and algo only).
* **Foreman**: a TypeScript coordinator + Docker workers (not Go); `/metrics` is JSON behind a dashboard session; no `worker_count`/`settlement_schedule`/`db_connections_in_use`/`POST /admin/jobs` contract.

Wiring them in means adapters (a Prometheus exporter for each, `socat` forwarders for the balancer) and re-expressing the LB and scheduler faults in terms of the keys they really have (`weights`, `algo`, `max_conn`, worker containers).
