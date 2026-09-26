# external/

Checkouts of the real components the Nightshift stubs stand in for. The checkouts themselves are git-ignored; recreate them with:

```bash
git clone https://github.com/naman777/Foreman        external/foreman
git clone https://github.com/naman777/Load-Balancer-CPP external/load-balancer
git -C external/foreman        config core.autocrlf false   # on Windows, before checkout, or shell scripts get CRLF endings
git -C external/load-balancer  config core.autocrlf false
git -C external/load-balancer  am ../patches/*.patch
```

## Verified (2026-09-26)

| Component | Result |
| --- | --- |
| C++ load balancer, unit tests | 26/26 pass (after the patch: `select_round_robin` was replaced by `select_weighted_rr`, and `make test` did not build `LoadBalancer.o` first) |
| C++ load balancer, `scripts/test.sh` | 4/4 pass (after the patch: `((PASS++))` under `set -e` aborted the script after its first pass; stats count matched the top-level `"port"` too; least-connections sends sequential requests to backend 0 by design, so the distribution check uses round-robin) |
| Foreman coordinator / worker tests | 31/31 and 12/12 pass |
| Foreman `node scripts/node-smoke.mjs` against `docker compose up` | all 6 checks pass (health, success, failure, timeout, artifact, 6 concurrent jobs, WebSocket) |

## Wired into the stack (opt-in)

`docker-compose.real.yml` runs both as the `lb` and `scheduler` services (`make demo-real`). What that took, what was verified and what was not:
see [docs/live-stack.md](../docs/live-stack.md#real-components-opt-in-overlay-docker-composerealyml).

The balancer needs the patches in `external/patches/` (`git am`); they add `host:port` backends, `upstream_timeout_ms`, Prometheus `/metrics`, JSON logs and fix a SIGHUP crash. Foreman is used unmodified.
