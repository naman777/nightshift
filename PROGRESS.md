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
- [x] 10 fault modules (simulated form + declarative live steps), 6 red-herring types, config git repo (external git dir), deploy log, chaos CLI
- [x] Go services: orders-svc, payments-svc (real fault hooks: hot-reloaded config, flags, bad-deploy build arg), stand-ins for LB + Foreman (same contract)
- [x] docker-compose (target + Prometheus/Alertmanager/Loki/Promtail/Grafana/Jaeger + Temporal + gateway + worker + dashboard), recording + alert rules
- [ ] NOT executed here (no Go toolchain, docker daemon off): compile/vet in CI (`make go-check`), first `make demo` will likely need small fixes

## Phase 6 — Benchmark
- [x] 40 scenarios (10 faults x 4), 13 with red herrings, 1 prompt-injection, 25 dev / 15 held-out, 10 smoke
- [x] World simulator, alert rules (invalid-scenario detection caught 2 mislabeled alerts), runner, scoring (exact / top-3 / judge / remediation /
      unsafe / grounding / red-herring), judge calibration (20 hand-labelled cases), naive floor baselines, report + SVG, README injection
- [x] Configs: single, multi, multi-routed (cheap specialists), multi-nocite (ablation), 2 naive baselines

## Phase 7 — Dashboard, CI, docs
- [x] Next.js dashboard (builds; browser-tested: alert -> live lanes -> approve -> resolved -> audit row), benchmark page
- [x] GitHub Actions: tests, 10-scenario eval gate vs committed baseline (max 10-pt drop), Go build/vet, dashboard build, compose validation, nightly bench
- [x] docs/architecture.md, docs/benchmark.md, README with generated results tables + honest status section, LICENSE, terminal CLI, no-docker demo
- [x] Hard stress set (10 scenarios: decoys, concurrent faults, telemetry outages) — reference policy scores 30%
- [x] docs/writeup.md, docs/demo-script.md, live benchmark runner (bench/live.py, not exercised: no docker here)
- [x] Cost-ceiling degrade to single-agent (local + Temporal), OTel -> Jaeger exporter, Slack Bolt (Socket Mode) app, `--prompt-version`
- [x] Stretch: incident memory (verified recall, leave-one-out eval, poisoned-memory test); hard set 30% -> 90% with memory

- [x] Proactive change review (`/webhook/change`, reviewer agent, `bench.proactive`: 197 commits, recall/precision/FPR)
- [x] Prompt caching + cache-aware cost model, schema enums + output vocabulary in the commander prompt, optional bearer-token auth, static stack-consistency tests

- [x] Independent adversarial review: 9 issues fixed (fail-closed auth + dashboard proxy, wrapper escaping, pre-write audit row, no auto-retry of writes, target-aware remediation scoring, ...)

- [x] Dashboard redesign for demos: scenario launcher (50 scenarios, agent setup, offline vs real LLM), live stepper + "happening now / next", plan, agent cards, answer-key verdict, evidence / safety audit / activity tabs. Gateway `/demo/*` endpoints; commander plan/decision steps are now emitted. Fixed: launcher alerts use the scenario's clock; single-agent report no longer rejected for invented ruled-out evidence ids.

## Remaining ideas
- [x] Real-LLM benchmark (`gpt-6-luna`): smoke, dev (v1 and v2), held-out (v2, 3 repeats), hard (v2); README table via `python -m bench.real_report --write`.
      Held-out single 96% / multi 76%, 0% unsafe, 100% grounded. Prompt v2 (category definitions) roughly doubled dev accuracy. Single agent beat the team.
      Prompt v3 (commit to a mechanism, no `unknown` hedging) dev single 96% / multi 88%; held-out single 96% / multi 96% (lightly contaminated: v2 held-out failures had been inspected); held-out failures were inspected, so held-out is lightly contaminated.
- [x] `gpt-6-*` prices added to `agents/core/llm.py`; stored real-run costs recomputed from token counts
- [x] Tag-contract tests (`tests/test_tag_contract.py`) guard the scripted-policy tag interface (typed evidence schema deliberately not done)
- [x] kubectl MCP server (stretch; read verbs + gated writes, fake-backend tested, not run against a real cluster)
- [x] Voice paging summary + pluggable webhook (stretch)
- [ ] Swap in the real Foreman + C++ LB (user will provide) -> delete `target/stubs`, keep the contract

## Deferred (user will provide)
- Foreman (Go scheduler), C++ load balancer (sim uses generic `scheduler` / `lb` names)

## Decisions
- Slack approval is out of scope for now (code kept, unit-tested only, not tried in a real workspace); approvals go through the dashboard.
