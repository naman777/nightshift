# Nightshift: working notes for Claude

AI on-call engineer: multi-agent incident investigator (Python), Temporal durability, MCP tools behind a policy layer, 40-scenario benchmark. `PLAN.md` = phases, `PROGRESS.md` = state, `docs/` = architecture / benchmark / writeup.

## Commands
- `python -m pytest -q -p no:cacheprovider` (~15 s, 140+ tests, no docker/keys needed; includes a real Temporal test server crash-resume test)
- `python -m agents.cli investigate <scenario-id> [--mode single] [--provider anthropic]`
- `python -m bench.runner --split smoke|dev|heldout|hard --config all --repeats 3`, then `python -m bench.report` (rewrites README table between `BENCH:START/END`)
- `python -m bench.gen_scenarios` / `python -m bench.gen_hard` regenerate scenario YAML (do not hand-edit them)
- Dashboard: `python -m gateway.demo` then `cd dashboard && npm run dev` (http://localhost:3001; launch any scenario from the UI; OPENAI_API_KEY in .env enables the real-LLM option)

## Conventions that matter
- Everything runs offline by design: the mock LLM (`agents/scripted.py`, an offline reference policy, NOT an LLM) + simulated `World` backends (`bench/sim`). Never present numbers from it as language-model results.
- Agents never call tools directly: `InProcessClient -> PolicyEngine -> Server`. Tier lives on the tool; the remediation action tier comes from `ACTION_TIERS`, never from the model.
- A fault is defined once in `chaos/faults/<name>.py` (simulated form `apply_sim` + declarative `live_steps`). Change both together. Every scenario's alert must fire per `bench/alert_rules.py` (mirror of `observability/prometheus/rules/alerts.yml`).
- Claim tag format (`[metric name=... service=...]`, `[log ...]`, `[change ...]`, `[code ...]`) is an interface between `agents/scripted.py` builders and its diagnosis parser; changing one side silently breaks the reference policy.
- Held-out scenarios are only for the final table. Do not tune against them.
- `target/stubs/{lb,scheduler}` stand in for the user's C++ LB and Foreman (to be provided later); keep their config keys / metric names as the contract.
- Go and docker files were written without a Go toolchain / running Docker daemon: CI (`.github/workflows/ci.yml`) compiles them; `make go-check` does it in a container.
- File creation: bash heredocs with mixed quotes failed to parse in this environment; prefer the Write tool.
