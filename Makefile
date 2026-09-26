.PHONY: setup-external up-real demo-real down-real start test lint bench bench-dev bench-heldout bench-smoke report scenarios investigate demo-sim up down demo chaos scenario chaos-revert go-check dashboard

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

# ---- the same stack with the REAL C++ load balancer and the REAL Foreman scheduler (opt-in; the stub stack above is unchanged) --------
COMPOSE_REAL = docker compose -f docker-compose.yml -f docker-compose.real.yml

setup-external:                               ## clone + patch external/load-balancer and external/foreman
	test -d external/foreman || git clone https://github.com/naman777/Foreman external/foreman
	test -d external/load-balancer || git clone https://github.com/naman777/Load-Balancer-CPP external/load-balancer
	git -C external/foreman config core.autocrlf false
	git -C external/load-balancer config core.autocrlf false
	git -C external/load-balancer log --oneline | grep -q "host:port backends" || git -C external/load-balancer am ../patches/*.patch

up-real: setup-external
	$(PY) -m chaos.cli init
	GIT_SHA=$$(git rev-parse --short HEAD 2>/dev/null || echo dev) $(COMPOSE_REAL) up -d --build

demo-real: up-real
	@echo "Real C++ load balancer + real Foreman. Grafana http://localhost:3000 | Temporal UI http://localhost:8233 | Dashboard http://localhost:3001"
	@echo "Then: make chaos SCENARIO=bad-config-push-lb-timeout-00   or   SCENARIO=scheduler-backlog-workers-1-00"

down-real:
	$(COMPOSE_REAL) down -v

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
