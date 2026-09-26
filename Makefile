.PHONY: start test lint bench bench-dev bench-heldout bench-smoke report scenarios investigate demo-sim up down demo chaos scenario chaos-revert go-check dashboard

PY ?= python
SCENARIO ?= bad-config-push-lb-timeout-00
MODE ?= multi

# ---- everything below runs offline: no docker, no API keys ------------------------------------------
test:
	$(PY) -m pytest -q

scenarios:
	$(PY) -m bench.gen_scenarios

investigate:                                  ## make investigate SCENARIO=bad-deploy-n-plus-one-00 MODE=single
	$(PY) -m agents.cli investigate $(SCENARIO) --mode $(MODE)

bench-smoke:                                  ## the 10-scenario CI gate
	$(PY) -m bench.runner --split smoke --config single,multi --repeats 1 --baseline bench/baseline.json

bench-dev:
	$(PY) -m bench.runner --split dev --config all --repeats 3

bench-heldout:                                ## run only for the final table (see docs/benchmark.md)
	$(PY) -m bench.runner --split heldout --config all --repeats 3

bench: bench-dev bench-heldout report

report:
	$(PY) -m bench.report

demo-sim:                                     ## gateway + dashboard on a simulated incident (no docker)
	$(PY) -m gateway.demo

# ---- the full stack (needs docker) -------------------------------------------------------------------
up:
	$(PY) -m chaos.cli init
	GIT_SHA=$$(git rev-parse --short HEAD 2>/dev/null || echo dev) docker compose up -d --build

down:
	docker compose down -v

demo: up
	@echo "Grafana http://localhost:3000 | Temporal UI http://localhost:8233 | Dashboard http://localhost:3001 | Jaeger http://localhost:16686"
	@echo "Then: make chaos SCENARIO=bad-config-push-lb-timeout-00   (and: docker kill nightshift-worker)"

chaos scenario:
	$(PY) -m chaos.cli scenario $(SCENARIO)

chaos-revert:
	$(PY) -m chaos.cli revert

go-check:                                     ## compile + vet the Go services in a container (no local Go needed)
	docker run --rm -v "$$PWD/target:/src" -w /src golang:1.22 sh -c "go mod tidy && go build ./... && go vet ./..."

dashboard:
	cd dashboard && npm install && npm run dev

start:                                        ## gateway + dashboard in one command (no docker)
	$(PY) start.py
