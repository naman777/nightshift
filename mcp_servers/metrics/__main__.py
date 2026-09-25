from .server import build  # noqa: F401
import os
from .backend import PrometheusBackend

build(PrometheusBackend(os.environ.get("PROMETHEUS_URL", "http://localhost:9090"))).serve_stdio()
