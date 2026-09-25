import os

from .backend import LokiBackend
from .server import build

build(LokiBackend(os.environ.get("LOKI_URL", "http://localhost:3100"))).serve_stdio()
