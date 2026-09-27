# Nightshift: working notes for Claude

AI on-call engineer: multi-agent incident investigator (Python), Temporal durability, MCP tools behind a policy layer, 40-scenario benchmark. `PLAN.md` = phases, `PROGRESS.md` = state, `docs/` = architecture / benchmark / writeup.

## Commands
- `python -m pytest -q -p no:cacheprovider` (~15 s, 140+ tests, no docker/keys needed; includes a real Temporal test server crash-resume test)
- `python -m agents.cli investigate <scenario-id> [--mode single] [--provider anthropic]`
- `python -m bench.runner --split smoke|dev|heldout|hard --config all --repeats 3`, then `python -m bench.report` (rewrites README table between `BENCH:START/END`)
- `python -m bench.gen_scenarios` / `python -m bench.gen_hard` regenerate scenario YAML (do not hand-edit them)
- One-command demo: `python start.py` (gateway + dashboard, opens the browser). By hand: `python -m gateway.demo` then `cd dashboard && npm run dev` (http://localhost:3001; launch any scenario from the UI; OPENAI_API_KEY in .env enables the real-LLM option)

## Conventions that matter
- Everything runs offline by design: the mock LLM (`agents/scripted.py`, an offline reference policy, NOT an LLM) + simulated `World` backends (`bench/sim`). Never present numbers from it as language-model results.
- Agents never call tools directly: `InProcessClient -> PolicyEngine -> Server`. Tier lives on the tool; the remediation action tier comes from `ACTION_TIERS`, never from the model.
- A fault is defined once in `chaos/faults/<name>.py` (simulated form `apply_sim` + declarative `live_steps`). Change both together. Every scenario's alert must fire per `bench/alert_rules.py` (mirror of `observability/prometheus/rules/alerts.yml`).
- Claim tag format (`[metric name=... service=...]`, `[log ...]`, `[change ...]`, `[code ...]`) is an interface between `agents/scripted.py` builders and its diagnosis parser; changing one side silently breaks the reference policy.
- Held-out scenarios are only for the final table. Do not tune against them.
- `target/stubs/{lb,scheduler}` are the default stand-ins; the REAL C++ LB and Foreman run via `docker-compose.real.yml` (`make demo-real`, clones in git-ignored `external/`, LB patches in `external/patches/`, Foreman adapter in `target/real/foreman/`). Keep the stubs' config keys / metric names as the contract for both.
- Docker on this machine: the shell sets `DOCKER_HOST=tcp://127.0.0.1:8888` (dead); use `unset DOCKER_HOST; export DOCKER_CONTEXT=desktop-linux`. The gateway/worker use the real model via `NIGHTSHIFT_LLM_PROVIDER=openai` etc. in the git-ignored `.env`.
- Real-host onboarding (`onboard/`, `docs/onboarding.md`): `ssh naman-ec2` is the Ubuntu EC2 box running the live LB (`lb.service`), the collectors (`nightshift-*.service`), a sandbox LB (`nsbox-lb.service`) and the shadow-mode watcher; secrets only in its `~/nightshift-run/nightshift/.env` (the user places the key; do not copy `.env` from here). Sandbox faults: `onboard/run_faults.sh`.
- Go and docker files were written without a Go toolchain / running Docker daemon: CI (`.github/workflows/ci.yml`) compiles them; `make go-check` does it in a container.
- File creation: bash heredocs with mixed quotes failed to parse in this environment; prefer the Write tool.
