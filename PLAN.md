# Nightshift — Implementation Plan

Derived from `Nightshift — AI On-Call Engineer Build Plan.md`. Progress is tracked in `PROGRESS.md`.

## Scope decisions

- **Deferred (user will supply later):** Foreman (Go scheduler) and the C++ load balancer. The target stack uses `orders-svc` x2 + `payments-svc` + Postgres, with a thin nginx `lb` placeholder. Fault types that need Foreman/LB (6, 8, 10, and LB-based 1/7) are modelled in the simulator and scenario files against generic `scheduler`/`lb` service names so real components can be dropped in later.
- **Offline-first:** everything must run and be testable with no API keys and no Docker. So the design has two seams:
  1. `agents/core/llm.py` — provider adapter (Anthropic / OpenAI via httpx) plus a deterministic `MockLLM`/`ScriptedPolicy` provider.
  2. `mcp_servers/*/backend.py` — every MCP server reads through a `Backend`; `LiveBackend` talks to Prometheus/Loki/git, `SimBackend` is fed by a scenario simulator. The benchmark runs on `SimBackend`, so `make bench` works on a laptop in seconds.
- Go is not installed locally; Go services are built inside Docker (multi-stage) and verified only structurally here.
- Temporal: workflows are real (`temporalio`) and tested with the SDK's time-skipping test environment where available; an in-process `LocalOrchestrator` with the same step semantics (checkpointing in Postgres/SQLite) is used by the bench and tests.

## Phases

### Phase 0 — Planning and scaffolding
Repo layout, `PLAN.md`, `PROGRESS.md`, `pyproject.toml`, Makefile, `.env.example`, git.

### Phase 1 — Agent core (the loop)
`agents/core/`: Pydantic models (Alert, EvidenceRow, Finding, Report, Action), `llm.py` (adapter, cost accounting, mock provider), `loop.py` (think → tool → observe, budgets, stop rules, always returns a finding, untrusted-data wrapping), `evidence.py` (board repo over SQLite/Postgres + citation validator), `mcp_client.py`, tracing (OTel spans, no-op fallback). Unit tests.

### Phase 2 — Policy layer and MCP servers
`mcp_servers/policy/`: trust tiers, timeouts, kill switch, append-only audit log. Servers: metrics, logs, changes, code (sandboxed), runtime (write tools, tiered). Each has live + sim backends and an MCP (stdio) entrypoint, plus an in-process registry used by agents. Tests.

### Phase 3 — Agents
Commander, Metrics/Logs/Change/Code specialists, Remediation, single-agent baseline, versioned prompts, service map, hypothesis/convergence logic, cost ceiling degrade-to-single-agent. Deterministic scripted policies so the pipeline is testable without an LLM.

### Phase 4 — Durability, gateway, Slack
`orchestrator/`: `InvestigationWorkflow`, `RemediationWorkflow` (signal approve/reject, 30 min timeout → reject), activities, worker, local orchestrator with checkpoint/resume. `gateway/` FastAPI (Alertmanager webhook, dedupe by fingerprint, incident API, SSE). `slackbot/` (Block Kit approval, signal relay).

### Phase 5 — Target stack, observability, chaos
`target/` Go services (orders, payments), loadgen (k6), config dir; `observability/` Prometheus rules, Alertmanager, Loki/Promtail, Grafana; `docker-compose.yml`; `chaos/` CLI with one module per fault, deploy log in git; Makefile targets.

### Phase 6 — Benchmark
40 scenarios (10 faults x 4 variants, red herrings in ~1/3, prompt-injection scenario, dev/held-out split), simulator generating metrics/logs/changes per scenario, `runner.py`, `scoring.py` (exact match, judge with heuristic fallback, safety, grounding), configurations (single, multi, multi-cheap, ablation), results JSON + `report.py` markdown table. Tests.

### Phase 7 — Dashboard, CI, docs
Next.js dashboard (live investigation + benchmark page), GitHub Actions (tests + smoke eval gate), `docs/architecture.md`, `docs/benchmark.md`, `docs/writeup.md`, README with results table.

## Definition of done per phase
Code written, tests passing (`pytest`), `PROGRESS.md` updated, committed.
