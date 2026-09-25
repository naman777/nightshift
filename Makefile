.PHONY: test bench bench-smoke demo up down chaos lint
PY ?= python

test:
	$(PY) -m pytest -q

bench:
	$(PY) -m bench.runner --split all --config all --repeats 3

bench-smoke:
	$(PY) -m bench.runner --split smoke --config multi --repeats 1 --fail-below 0.6

report:
	$(PY) -m bench.report

up:
	docker compose up -d --build

down:
	docker compose down -v

demo: up
	@echo "Grafana http://localhost:3000  Temporal UI http://localhost:8233  Dashboard http://localhost:3001"

chaos:
	$(PY) -m chaos.cli inject $(FAULT) --target $(TARGET)
