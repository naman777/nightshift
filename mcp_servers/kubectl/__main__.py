import os

from .backend import CliKubectl
from .server import build

build(CliKubectl(os.environ.get("KUBE_CONTEXT"))).serve_stdio()
