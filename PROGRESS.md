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
- [x] Temporal InvestigationWorkflow / RemediationWorkflow (signals, 30-min timeout -> reject, dedupe by fingerprint), heartbeating activities, worker
- [x] Verified against the Temporal test server: worker killed mid-incident, replacement worker resumes with ZERO repeated LLM calls
- [x] Gateway (Alertmanager webhook, incident API, SSE stream, approve/reject, Slack interactive endpoint w/ signature check), LocalRunner (no-Temporal mode)
- [x] Slack Block Kit approval messages (no one-click path for destructive actions), notifier abstraction

## Phase 5 — Target stack + chaos
- [~] Fault modules (10) + red herrings + simulator done; Go services, compose, observability, chaos CLI todo

## Phase 6 — Benchmark
- [x] 40 scenarios (10 faults x 4), 13 with red herrings, 1 prompt-injection, 25 dev / 15 held-out, 10 smoke
- [x] World simulator, alert rules (invalid-scenario detection caught 2 mislabeled alerts), runner, scoring (exact / top-3 / judge / remediation /
      unsafe / grounding / red-herring), judge calibration (20 hand-labelled cases), naive floor baselines, report + SVG, README injection
- [x] Configs: single, multi, multi-routed (cheap specialists), multi-nocite (ablation), 2 naive baselines

## Phase 7 — Dashboard, CI, docs
- [ ] Next.js dashboard, GH Actions, docs, README

## Deferred (user will provide)
- Foreman (Go scheduler), C++ load balancer (sim uses generic `scheduler` / `lb` names)
