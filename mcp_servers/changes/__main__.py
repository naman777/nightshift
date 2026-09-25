import os

from .backend import GitChangesBackend
from .server import build

build(GitChangesBackend(os.environ.get("CONFIG_REPO", "target/config"), os.environ.get("DEPLOY_LOG", "target/deploys.jsonl"))).serve_stdio()
