from .backend import DockerRuntimeBackend
from .server import build

build(DockerRuntimeBackend()).serve_stdio()
