import os

from .backend import FsCodeBackend
from .server import build

build(FsCodeBackend(os.environ.get("CODE_ROOT", "target/orders-svc"))).serve_stdio()
