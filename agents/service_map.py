"""Static topology the commander can consult (in production this would be generated from service discovery)."""
from __future__ import annotations

SERVICE_MAP = {
    "services": {
        "loadgen": {"role": "traffic generator", "calls": ["lb"]},
        "lb": {"role": "load balancer; spreads traffic across orders-svc replicas (orders-svc-1, orders-svc-2)", "calls": ["orders-svc"],
               "config": "config/lb.yaml (upstream timeouts, weights, health checks)"},
        "orders-svc": {"role": "order API (Go); reads/writes postgres; calls payments-svc for charges", "calls": ["postgres", "payments-svc"],
                       "replicas": ["orders-svc-1", "orders-svc-2"], "config": "config/orders.yaml, config/flags.json"},
        "payments-svc": {"role": "payments API (Go); external dependency reached through toxiproxy", "calls": [], "config": "config/payments-svc.yaml"},
        "scheduler": {"role": "Foreman job scheduler; runs settlement / cache warm-up against orders and postgres",
                      "calls": ["postgres", "orders-svc"], "config": "config/scheduler.yaml"},
        "postgres": {"role": "shared database (connection limit shared by orders-svc and scheduler)", "calls": []},
    },
    "notes": "Symptoms usually appear in orders-svc/lb because they sit at the top of the call graph; trace dependencies downward for causes.",
}
