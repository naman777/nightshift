# Progress

Legend: [x] done · [~] in progress · [ ] todo

## Phase 0 — Scaffolding
- [x] PLAN.md, PROGRESS.md, pyproject, Makefile, .env.example, .gitignore, git init

## Phase 1 — Agent core
- [x] Pydantic models (alert, evidence, finding, report, action, tiers)
- [x] DB layer (SQLite + Postgres, append-only audit_log triggers/rules)
- [x] LLM adapter (Anthropic, OpenAI over httpx, deterministic mock) + token/cost accounting
- [x] Hand-written agent loop: budgets, stop rules (submit / budget / tokens / stalled), always returns a finding,
      untrusted-data wrapping, truncation + artifact store, claims must cite a real tool call
- [x] Evidence board + citation validator, checkpoints, step trace
- [x] MCP client (in-process via policy; real stdio client)
- [x] OTel tracing shim

## Phase 2 — Policy + MCP servers
- [x] Policy engine: 3 trust tiers, typed confirmation, benchmark mode (proposals only), kill switch, timeouts, audit log
- [x] Servers: metrics (query_range, top_anomalies, compare_windows), logs (search, cluster_errors, tail), changes
      (recent_deploys, config_diff, commit_diff), code (read_file, grep, run_tests; sandboxed), runtime (write tools, tiered)
- [x] Live backends (Prometheus, Loki, git+deploy log, filesystem, docker) and stdio entrypoints

## Phase 3 — Agents
- [x] Versioned prompts (agents/prompts/v1), service map
- [x] Commander (plan / converge, citation-validated report, follow-up rounds, fallback), 4 specialists, remediation, single-agent baseline
- [x] Offline reference policy ("heuristic brain") behind the mock LLM so everything runs with no API keys
- [x] Pipeline steps + LocalOrchestrator (checkpoint/resume, cost ceiling degrade)
- [x] Tests: loop, policy, pipeline, injection, red herring, crash-resume (42 passing)

## Phase 4 — Durability, gateway, Slack
- [ ] Temporal workflows/activities/worker, gateway (FastAPI), slackbot

## Phase 5 — Target stack + chaos
- [~] Fault modules (10) + red herrings + simulator done; Go services, compose, observability, chaos CLI todo

## Phase 6 — Benchmark
- [~] 40 scenarios + dev/held-out split + World simulator done; runner, scoring, report todo

## Phase 7 — Dashboard, CI, docs
- [ ] Next.js dashboard, GH Actions, docs, README

## Deferred (user will provide)
- Foreman (Go scheduler), C++ load balancer (sim uses generic `scheduler` / `lb` names)
